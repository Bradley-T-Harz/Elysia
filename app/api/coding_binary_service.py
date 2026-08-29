"""BinaryForge orchestration for bounded static metadata and private reports."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_binary_type_registry import binary_type_from_extension, descriptor_for_binary, detect_binary_format
from app.api.coding_data_binary_artifact_service import create_data_binary_artifact
from app.api.coding_data_binary_policy_service import load_binary_limits
from app.api.coding_data_binary_worker_service import run_data_binary_worker
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_trace_service import coding_request_id
from app.api.schemas.database_binary import BinaryInspectRequest, BinaryInspectResponse, BinaryRiskFlag


BINARY_TYPE_POLICY_VERSION = "binary-types-0.1"


def _operation_id() -> str:
    return f"binary_inspect_{uuid4().hex[:16]}"


def _audit(operation_id: str, payload: BinaryInspectRequest, *, status: str, values: dict[str, Any]) -> bool:
    compact = {
        "operation_kind": "binary_inspect",
        "status": status,
        "workspace_root_hash": hash_path(payload.workspace_root),
        "path_hash": hash_path(payload.binary_path),
        "binary_format": values.get("binary_format"),
        "source_hash": values.get("source_hash"),
        "size_bytes": values.get("size_bytes"),
        "section_count": values.get("section_count"),
        "import_count": values.get("import_count"),
        "export_count": values.get("export_count"),
        "symbol_count": values.get("symbol_count"),
        "string_count": values.get("string_count"),
        "risk_total": values.get("risk_total"),
        "artifact_id": values.get("artifact_id"),
        "artifact_hash": values.get("artifact_hash"),
        "policy_version": values.get("policy_version"),
        "approval_required": True,
        "operator_approved": payload.approval_granted,
        "execution_performed": False,
        "loading_performed": False,
        "mutation_performed": False,
        "raw_content_logged": False,
        "network": False,
        "shell": False,
    }
    return write_coding_audit_record("binary_inspect", operation_id, {key: value for key, value in compact.items() if value is not None})


def inspect_binary(payload: BinaryInspectRequest) -> BinaryInspectResponse:
    operation_id = _operation_id()
    request_id = coding_request_id(operation_id)
    policy = load_binary_limits()
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.binary_path, require_existing=True, allow_directory=False)
    extension_type = binary_type_from_extension(payload.binary_path)
    descriptor = descriptor_for_binary("unknown", extension_type=extension_type)
    if not guarded.allowed or not payload.approval_granted:
        status = "blocked" if not guarded.allowed else "approval_required"
        reason = guarded.reason if not guarded.allowed else "explicit_binary_static_inspection_approval_required"
        audit = _audit(operation_id, payload, status=status, values={"policy_version": policy["version"]})
        return BinaryInspectResponse(status=status, operation_id=operation_id, request_id=request_id, file_label=guarded.target_path.name or "selected binary", relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), extension_type=extension_type, descriptor=descriptor, policy_version=BINARY_TYPE_POLICY_VERSION, worker_policy_version=policy["version"], audit_written=audit, blocked_reason=reason, warnings=["BinaryForge is static only; execution, loading, installation, linking, mutation, and patching are unavailable by design."])
    worker = run_data_binary_worker("binary", operation="inspect", source=guarded.target_path, limits=policy["limits"])
    if worker.get("status") != "completed":
        reason = str(worker.get("reason") or "binary_static_worker_failed")
        audit = _audit(operation_id, payload, status="blocked", values={"policy_version": policy["version"]})
        return BinaryInspectResponse(status="blocked", operation_id=operation_id, request_id=request_id, file_label=guarded.target_path.name, relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), extension_type=extension_type, descriptor=descriptor, policy_version=BINARY_TYPE_POLICY_VERSION, worker_policy_version=policy["version"], audit_written=audit, blocked_reason=reason, warnings=["The file was not executed, loaded, linked, installed, imported, mutated, or patched."])
    detected = str(worker.get("detected_format") or "unknown")
    core_detected, core_magic = detect_binary_format(guarded.target_path)
    if core_detected != "unknown":
        detected = core_detected
    descriptor = descriptor_for_binary(detected, extension_type=extension_type)
    raw_flags = worker.get("risk_flags") if isinstance(worker.get("risk_flags"), list) else []
    risk_flags: list[BinaryRiskFlag] = []
    for value in raw_flags:
        if not isinstance(value, dict):
            continue
        try:
            risk_flags.append(BinaryRiskFlag(code=str(value.get("code") or "static_indicator"), severity=str(value.get("severity") or "info"), count=max(1, int(value.get("count") or 1)), summary=str(value.get("summary") or "Static indicator.")))
        except Exception:
            continue
    risk_counts: dict[str, int] = {}
    for flag in risk_flags:
        risk_counts[flag.code] = risk_counts.get(flag.code, 0) + flag.count
    artifact = create_data_binary_artifact("binary", "static_report", {"format": detected, "sha256": worker.get("sha256"), "blake3": worker.get("blake3"), "size_bytes": worker.get("size_bytes"), "magic_summary": worker.get("magic_summary"), "entropy": worker.get("entropy"), "headers": worker.get("headers"), "sections": worker.get("sections"), "imports": worker.get("imports"), "exports": worker.get("exports"), "symbols": worker.get("symbols"), "strings": worker.get("strings"), "strings_truncated": worker.get("strings_truncated"), "risk_flags": [flag.to_payload() for flag in risk_flags], "toolchain": worker.get("toolchain"), "policy_version": policy["version"], "lawfulness_note": "Static metadata inspection is not legal clearance or an antivirus/malware verdict.", "execution": "unavailable_by_design", "mutation": "unavailable_by_design"})
    match = detected == extension_type or (extension_type == "bin_unknown" and detected in {"unknown", "elf", "pe", "class", "wasm"})
    audit = _audit(operation_id, payload, status="completed", values={"binary_format": detected, "source_hash": worker.get("sha256"), "size_bytes": worker.get("size_bytes"), "section_count": worker.get("section_count"), "import_count": worker.get("import_count"), "export_count": worker.get("export_count"), "symbol_count": worker.get("symbol_count"), "string_count": worker.get("string_count"), "risk_total": sum(risk_counts.values()), "artifact_id": artifact.artifact_id, "artifact_hash": artifact.sha256, "policy_version": policy["version"]})
    return BinaryInspectResponse(status="completed", operation_id=operation_id, request_id=request_id, file_label=guarded.target_path.name, relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), source_sha256=str(worker.get("sha256") or ""), source_blake3=worker.get("blake3"), size_bytes=int(worker.get("size_bytes") or 0), extension_type=extension_type, detected_format=detected, extension_content_match=match, magic_summary=str(worker.get("magic_summary") or core_magic), descriptor=descriptor, architecture=worker.get("architecture"), bitness=worker.get("bitness"), endianness=worker.get("endianness"), section_count=int(worker.get("section_count") or 0), import_count=int(worker.get("import_count") or 0), export_count=int(worker.get("export_count") or 0), symbol_count=int(worker.get("symbol_count") or 0), string_count=int(worker.get("string_count") or 0), entropy=float(worker["entropy"]) if worker.get("entropy") is not None else None, executable_bit=bool(worker.get("executable_bit")), debug_symbols_present=worker.get("debug_symbols_present"), stripped=worker.get("stripped"), risk_flags=risk_flags, risk_counts=risk_counts, artifact=artifact, policy_version=BINARY_TYPE_POLICY_VERSION, worker_policy_version=policy["version"], toolchain=[str(value) for value in worker.get("toolchain") or []], audit_written=audit, warnings=["Static metadata only. This is not legal clearance, antivirus certification, or a malware verdict.", "Execution, loading, import, install, linking, mutation, patching, and trust are unavailable by design. Detailed strings/imports/exports remain in the private local artifact."])


__all__ = ("inspect_binary",)
