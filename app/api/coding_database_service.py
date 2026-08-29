"""DatabaseForge orchestration: path guard, exact approval, snapshots, artifacts, and compact audit."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_data_binary_artifact_service import create_data_binary_artifact
from app.api.coding_data_binary_policy_service import load_database_limits
from app.api.coding_data_binary_worker_service import run_data_binary_worker
from app.api.coding_database_type_registry import database_type_from_extension, descriptor_for_database, detect_database_engine
from app.api.coding_operation_hash_service import operation_plan_hash
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_trace_service import coding_request_id
from app.api.schemas.database_binary import DatabaseInspectRequest, DatabaseInspectResponse, DatabaseSchemaPreviewRequest, DatabaseSchemaPreviewResponse


DATABASE_TYPE_POLICY_VERSION = "database-types-0.1"


def _operation_id(kind: str) -> str:
    return f"database_{kind}_{uuid4().hex[:16]}"


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sidecar_state(path: Path) -> tuple[dict[str, Any], str, bool]:
    records: dict[str, Any] = {}
    digest = sha256()
    unsafe = False
    for kind, candidate in (("wal", Path(f"{path}-wal")), ("shm", Path(f"{path}-shm")), ("journal", Path(f"{path}-journal"))):
        present = candidate.exists() or candidate.is_symlink()
        record: dict[str, Any] = {"present": present, "size_bytes": 0, "regular_file": False, "symlink": candidate.is_symlink()}
        if present and candidate.is_file() and not candidate.is_symlink():
            record["regular_file"] = True
            record["size_bytes"] = candidate.stat().st_size
            record["sha256"] = _sha256_file(candidate)
        elif present:
            unsafe = True
        records[kind] = record
        digest.update(kind.encode("ascii"))
        # SQLite SHM is transient lock/index state and may change during a
        # legitimate read-only connection. Bind approval to its presence and
        # file type, while binding WAL/journal state to exact bytes.
        digest_record = (
            {key: record[key] for key in ("present", "regular_file", "symlink")}
            if kind == "shm"
            else record
        )
        digest.update(str(digest_record).encode("utf-8"))
    return records, digest.hexdigest(), unsafe


def _metadata(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    worker = run_data_binary_worker("database", operation="metadata", source=path, limits=limits)
    if worker.get("status") != "completed":
        return worker
    core_engine, core_magic = detect_database_engine(path)
    worker["engine"] = core_engine if core_engine != "unknown" else str(worker.get("engine") or "unknown")
    if not worker.get("magic_summary") or worker.get("magic_summary") == "magic_unavailable":
        worker["magic_summary"] = core_magic
    return worker


def _schema_plan(relative_path: str | None, source_sha256: str, source_state_digest: str, engine: str) -> str:
    return operation_plan_hash(action="database_schema_preview", source_relative_path=relative_path, target_relative_path=None, source_hash=source_sha256, details={"engine": engine, "source_state_digest": source_state_digest, "snapshot_first": True, "row_preview": False})


def _audit(operation_kind: str, operation_id: str, *, status: str, workspace_root: str, database_path: str, values: dict[str, Any]) -> bool:
    compact = {
        "operation_kind": operation_kind,
        "status": status,
        "workspace_root_hash": hash_path(workspace_root),
        "path_hash": hash_path(database_path),
        "database_engine": values.get("database_engine"),
        "source_hash": values.get("source_hash"),
        "snapshot_hash": values.get("snapshot_hash"),
        "source_state_digest": values.get("source_state_digest"),
        "size_bytes": values.get("size_bytes"),
        "table_count": values.get("table_count"),
        "view_count": values.get("view_count"),
        "index_count": values.get("index_count"),
        "trigger_count": values.get("trigger_count"),
        "schema_object_count": values.get("schema_object_count"),
        "risk_total": values.get("risk_total"),
        "artifact_id": values.get("artifact_id"),
        "artifact_hash": values.get("artifact_hash"),
        "approval_id": values.get("approval_id"),
        "approval_required": True,
        "operator_approved": bool(values.get("operator_approved")),
        "policy_version": values.get("policy_version"),
        "mutation_performed": False,
        "row_data_returned": False,
        "arbitrary_sql_executed": False,
        "raw_content_logged": False,
        "network": False,
        "shell": False,
    }
    return write_coding_audit_record(operation_kind, operation_id, {key: value for key, value in compact.items() if value is not None})


def inspect_database(payload: DatabaseInspectRequest) -> DatabaseInspectResponse:
    operation_id = _operation_id("inspect")
    request_id = coding_request_id(operation_id)
    limits_policy = load_database_limits()
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.database_path, require_existing=True, allow_directory=False)
    extension_type = database_type_from_extension(payload.database_path)
    descriptor = descriptor_for_database("unknown", extension_type=extension_type)
    if not guarded.allowed or not payload.approval_granted:
        status = "blocked" if not guarded.allowed else "approval_required"
        reason = guarded.reason if not guarded.allowed else "explicit_database_metadata_approval_required"
        audit = _audit("database_inspect", operation_id, status=status, workspace_root=payload.workspace_root, database_path=payload.database_path, values={"operator_approved": payload.approval_granted, "policy_version": limits_policy["version"]})
        return DatabaseInspectResponse(status=status, operation_id=operation_id, request_id=request_id, file_label=guarded.target_path.name or "selected database", relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), extension_type=extension_type, descriptor=descriptor, policy_version=DATABASE_TYPE_POLICY_VERSION, worker_policy_version=limits_policy["version"], audit_written=audit, blocked_reason=reason, warnings=["Database metadata is local and read-only; schema names remain privacy-gated."])
    metadata = _metadata(guarded.target_path, limits_policy["limits"])
    if metadata.get("status") != "completed":
        reason = str(metadata.get("reason") or "database_metadata_worker_failed")
        audit = _audit("database_inspect", operation_id, status="blocked", workspace_root=payload.workspace_root, database_path=payload.database_path, values={"operator_approved": payload.approval_granted, "policy_version": limits_policy["version"]})
        return DatabaseInspectResponse(status="blocked", operation_id=operation_id, request_id=request_id, file_label=guarded.target_path.name, relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), extension_type=extension_type, descriptor=descriptor, policy_version=DATABASE_TYPE_POLICY_VERSION, worker_policy_version=limits_policy["version"], audit_written=audit, blocked_reason=reason, warnings=["No schema was opened and no data was returned."])
    engine = str(metadata.get("engine") or "unknown")
    descriptor = descriptor_for_database(engine, extension_type=extension_type)
    source_sha256 = str(metadata["sha256"])
    sidecars, sidecar_digest, unsafe_sidecar = _sidecar_state(guarded.target_path)
    source_state_digest = sha256(f"{source_sha256}:{sidecar_digest}".encode("utf-8")).hexdigest()
    plan_hash = None if engine == "unknown" or unsafe_sidecar else _schema_plan(guarded.relative_path, source_sha256, source_state_digest, engine)
    artifact = create_data_binary_artifact("database", "metadata", {"engine": engine, "sha256": source_sha256, "blake3": metadata.get("blake3"), "size_bytes": metadata.get("size_bytes"), "magic_summary": metadata.get("magic_summary"), "sidecars": sidecars, "source_state_digest": source_state_digest, "schema_preview_plan_hash": plan_hash, "policy_version": limits_policy["version"], "row_preview": "unavailable_by_design", "mutation": "unavailable_by_design"})
    match = engine == extension_type or (extension_type == "db_unknown" and engine in {"sqlite", "duckdb"})
    audit = _audit("database_inspect", operation_id, status="completed", workspace_root=payload.workspace_root, database_path=payload.database_path, values={"database_engine": engine, "source_hash": source_sha256, "source_state_digest": source_state_digest, "size_bytes": metadata.get("size_bytes"), "artifact_id": artifact.artifact_id, "artifact_hash": artifact.sha256, "operator_approved": payload.approval_granted, "policy_version": limits_policy["version"]})
    warnings = ["Static database metadata only. Schema preview requires exact approval; row preview and mutation are unavailable by design."]
    if any(value["present"] for value in sidecars.values()):
        warnings.append("SQLite journal/WAL sidecars were detected; schema preview will use the consistent read-only backup snapshot path.")
    if unsafe_sidecar:
        warnings.append("A non-regular or symlink sidecar blocks schema preview.")
    if engine == "unknown":
        warnings.append("Unknown database-like file: metadata only because the engine could not be safely identified.")
    return DatabaseInspectResponse(status="completed", operation_id=operation_id, request_id=request_id, file_label=guarded.target_path.name, relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), source_sha256=source_sha256, source_blake3=metadata.get("blake3"), size_bytes=int(metadata.get("size_bytes") or 0), extension_type=extension_type, detected_engine=engine, extension_content_match=match, magic_summary=str(metadata.get("magic_summary") or "unknown"), descriptor=descriptor, sidecars=sidecars, source_state_digest=source_state_digest, schema_preview_plan_hash=plan_hash, artifact=artifact, policy_version=DATABASE_TYPE_POLICY_VERSION, worker_policy_version=limits_policy["version"], audit_written=audit, warnings=warnings)


def _blocked_preview(payload: DatabaseSchemaPreviewRequest, *, operation_id: str, guarded: Any, engine: str, source_hash: str, policy_version: str, reason: str, approval_id: str | None = None) -> DatabaseSchemaPreviewResponse:
    audit = _audit("database_schema_preview", operation_id, status="approval_required" if "approval" in reason else "blocked", workspace_root=payload.workspace_root, database_path=payload.database_path, values={"database_engine": engine, "source_hash": source_hash, "approval_id": approval_id or payload.approval_id, "operator_approved": payload.operator_approved, "policy_version": policy_version})
    return DatabaseSchemaPreviewResponse(status="approval_required" if "approval" in reason else "blocked", operation_id=operation_id, request_id=coding_request_id(operation_id, approval_id or payload.approval_id), approval_id=approval_id or payload.approval_id, file_label=guarded.target_path.name or "selected database", relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), detected_engine=engine, source_sha256=source_hash, policy_version=policy_version, audit_written=audit, blocked_reason=reason, warnings=["No row data was returned, no arbitrary SQL ran, and the source database was not mutated."])


def preview_database_schema(payload: DatabaseSchemaPreviewRequest) -> DatabaseSchemaPreviewResponse:
    operation_id = _operation_id("schema_preview")
    policy = load_database_limits()
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.database_path, require_existing=True, allow_directory=False)
    if not guarded.allowed:
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine="unknown", source_hash=payload.expected_source_sha256, policy_version=policy["version"], reason=guarded.reason or "path_not_allowed")
    metadata = _metadata(guarded.target_path, policy["limits"])
    if metadata.get("status") != "completed":
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine="unknown", source_hash=payload.expected_source_sha256, policy_version=policy["version"], reason=str(metadata.get("reason") or "database_metadata_worker_failed"))
    engine = str(metadata.get("engine") or "unknown")
    source_hash = str(metadata.get("sha256") or "")
    sidecars, sidecar_digest, unsafe_sidecar = _sidecar_state(guarded.target_path)
    del sidecars
    source_state_digest = sha256(f"{source_hash}:{sidecar_digest}".encode("utf-8")).hexdigest()
    current_plan = _schema_plan(guarded.relative_path, source_hash, source_state_digest, engine) if engine in {"sqlite", "duckdb"} and not unsafe_sidecar else ""
    if engine not in {"sqlite", "duckdb"}:
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine=engine, source_hash=source_hash, policy_version=policy["version"], reason="schema_preview_unavailable_for_unknown_database")
    if unsafe_sidecar:
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine=engine, source_hash=source_hash, policy_version=policy["version"], reason="unsafe_database_sidecar")
    if source_hash != payload.expected_source_sha256 or current_plan != payload.expected_plan_hash:
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine=engine, source_hash=source_hash, policy_version=policy["version"], reason="database_hash_or_plan_changed")
    if not payload.operator_approved:
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine=engine, source_hash=source_hash, policy_version=policy["version"], reason="exact_approval_required")
    approval = consume_operation_approval(approval_id=payload.approval_id, approval_token=payload.approval_token, operation_kind="database_schema_preview", workspace_root=payload.workspace_root, exact_files=[payload.database_path], source_hash=source_hash, plan_hash=current_plan, allowed_mutation_class="database_schema_preview")
    if not approval.allowed:
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine=engine, source_hash=source_hash, policy_version=policy["version"], reason=approval.reason or "exact_approval_required", approval_id=approval.approval_id)
    with tempfile.TemporaryDirectory(prefix="elysia-databaseforge-snapshot-") as temporary:
        temporary_root = Path(temporary)
        temporary_root.chmod(0o700)
        snapshot = temporary_root / f"snapshot.{engine}"
        worker = run_data_binary_worker("database", operation="snapshot_schema", source=guarded.target_path, snapshot=snapshot, engine=engine, limits=policy["limits"])
    if worker.get("status") != "completed":
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine=engine, source_hash=source_hash, policy_version=policy["version"], reason=str(worker.get("reason") or "database_schema_worker_failed"), approval_id=approval.approval_id)
    after = _metadata(guarded.target_path, policy["limits"])
    _, after_sidecar_digest, _ = _sidecar_state(guarded.target_path)
    after_state = sha256(f"{after.get('sha256')}:{after_sidecar_digest}".encode("utf-8")).hexdigest()
    if after.get("sha256") != source_hash or after_state != source_state_digest:
        return _blocked_preview(payload, operation_id=operation_id, guarded=guarded, engine=engine, source_hash=str(after.get("sha256") or source_hash), policy_version=policy["version"], reason="database_changed_during_snapshot", approval_id=approval.approval_id)
    schema = worker.get("schema") if isinstance(worker.get("schema"), dict) else {}
    counts = schema.get("counts") if isinstance(schema.get("counts"), dict) else {}
    risks = schema.get("risk_counts") if isinstance(schema.get("risk_counts"), dict) else {}
    artifact = create_data_binary_artifact("database", "schema", {"engine": engine, "source_sha256": source_hash, "snapshot_sha256": worker.get("snapshot_sha256"), "snapshot_strategy": worker.get("snapshot_strategy"), "schema": schema, "policy_version": policy["version"], "approval_id": approval.approval_id})
    audit = _audit("database_schema_preview", operation_id, status="completed", workspace_root=payload.workspace_root, database_path=payload.database_path, values={"database_engine": engine, "source_hash": source_hash, "snapshot_hash": worker.get("snapshot_sha256"), "source_state_digest": source_state_digest, "table_count": counts.get("table", 0), "view_count": counts.get("view", 0), "index_count": counts.get("index", 0), "trigger_count": counts.get("trigger", 0), "schema_object_count": schema.get("schema_object_count", 0), "risk_total": sum(int(value) for value in risks.values()), "artifact_id": artifact.artifact_id, "artifact_hash": artifact.sha256, "approval_id": approval.approval_id, "operator_approved": True, "policy_version": policy["version"]})
    return DatabaseSchemaPreviewResponse(status="completed", operation_id=operation_id, request_id=coding_request_id(operation_id, approval.approval_id), approval_id=approval.approval_id, file_label=guarded.target_path.name, relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), detected_engine=engine, source_sha256=source_hash, snapshot_sha256=str(worker.get("snapshot_sha256") or ""), snapshot_strategy=str(worker.get("snapshot_strategy") or ""), table_count=int(counts.get("table") or 0), view_count=int(counts.get("view") or 0), index_count=int(counts.get("index") or 0), trigger_count=int(counts.get("trigger") or 0), schema_object_count=int(schema.get("schema_object_count") or 0), risk_counts={str(key): int(value) for key, value in risks.items()}, artifact=artifact, policy_version=policy["version"], audit_written=audit, warnings=["Schema names and definitions are stored only in the private local artifact. No rows were read or returned.", "Mutation and arbitrary SQL are unavailable by design."])


__all__ = ("inspect_database", "preview_database_schema")
