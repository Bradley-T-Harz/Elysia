"""EngineeringForge orchestration: guards, static reports, preview plans, artifacts, and audit."""

from __future__ import annotations

from hashlib import sha256
from html import escape
from pathlib import Path
import re
import struct
from typing import Any
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_blend_service import inspect_blend
from app.api.coding_cad_service import inspect_cad
from app.api.coding_cam_service import inspect_gcode
from app.api.coding_engineering_artifact_service import create_engineering_json_artifact, create_engineering_text_artifact
from app.api.coding_engineering_job_service import finish_engineering_job, start_engineering_job
from app.api.coding_engineering_policy_service import (
    load_cam_gcode_safety,
    load_engineering_inspection_limits,
    load_engineering_preview_limits,
    load_robot_model_safety,
)
from app.api.coding_engineering_static import EngineeringInspectionError, hash_file, risk_counts
from app.api.coding_engineering_type_registry import (
    ENGINEERING_TYPE_POLICY_VERSION,
    descriptor_for_engineering_type,
    engineering_type_from_extension,
)
from app.api.coding_geometry_service import inspect_geometry
from app.api.coding_operation_hash_service import operation_plan_hash
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_robot_model_service import inspect_robot_model
from app.api.coding_trace_service import coding_request_id
from app.api.schemas.engineering import (
    EngineeringInspectRequest,
    EngineeringInspectResponse,
    EngineeringPreviewApplyRequest,
    EngineeringPreviewPlan,
    EngineeringPreviewPlanRequest,
    EngineeringPreviewResult,
)


_PREVIEW_TYPES = {"stl", "obj", "dxf", "gcode"}


def _operation_id(kind: str) -> str:
    return f"engineering_{kind}_{uuid4().hex[:16]}"


def _worker_truth(type_id: str) -> tuple[str, str]:
    if type_id in {"stl", "obj", "dae"}:
        return "geometryforge_worker", "configured_not_launched_static_module_live"
    if type_id in {"step", "iges", "dxf", "f3d", "f3z"}:
        return "cadforge_worker", "configured_not_launched_static_module_live"
    if type_id in {"urdf", "sdf"}:
        return "robotmodelforge_worker", "configured_not_launched_static_module_live"
    if type_id == "gcode":
        return "camforge_worker", "configured_not_launched_static_module_live"
    if type_id == "blend":
        return "blendforge_worker", "future_sandbox_required"
    return "engineeringforge", "metadata_only"


def _magic_type(path: Path, extension_type: str) -> tuple[str, str]:
    try:
        with path.open("rb") as stream:
            head = stream.read(8192)
    except OSError:
        return "unknown", "unreadable"
    upper = head.upper()
    stripped = head.lstrip()
    if head.startswith(b"BLENDER"):
        return "blend", "Blender file header"
    if b"ISO-10303-21" in upper[:4096]:
        return "step", "ISO 10303-21 STEP exchange"
    if stripped.startswith(b"<") and b"COLLADA" in upper[:4096]:
        return "dae", "COLLADA XML"
    if stripped.startswith(b"<") and re.search(rb"<\s*(?:[A-Z0-9_]+:)?ROBOT(?:\s|>)", upper[:4096]):
        return "urdf", "URDF robot XML"
    if stripped.startswith(b"<") and re.search(rb"<\s*(?:[A-Z0-9_]+:)?SDF(?:\s|>)", upper[:4096]):
        return "sdf", "SDF XML"
    if extension_type == "stl":
        size = path.stat().st_size
        if len(head) >= 84:
            count = struct.unpack("<I", head[80:84])[0]
            if 84 + count * 50 == size:
                return "stl", "binary STL"
        if stripped.lower().startswith(b"solid") and b"facet" in head.lower():
            return "stl", "ASCII STL"
        return "unknown", "STL extension without confirmed header"
    if extension_type == "obj" and re.search(rb"(?m)^\s*(?:v|f|o|g|mtllib)\s+", head):
        return "obj", "Wavefront OBJ text"
    if extension_type == "iges":
        lines = head.splitlines()
        if any(len(line) >= 73 and line[72:73].upper() == b"S" for line in lines):
            return "iges", "IGES fixed-record exchange"
    if extension_type == "dxf" and b"SECTION" in upper and (b"HEADER" in upper or b"ENTITIES" in upper):
        return "dxf", "DXF tagged text exchange"
    if extension_type == "gcode" and re.search(rb"(?im)^\s*(?:N\d+\s+)?[GMTFSXYZIJKR][+-]?(?:\d|\.)", head):
        return "gcode", "G-code machine instruction text"
    if extension_type == "f3z" and head.startswith(b"PK\x03\x04"):
        return "f3z", "F3Z ZIP-compatible container"
    if extension_type == "f3d":
        return "f3d", "opaque Fusion F3D data (extension-led metadata support)"
    return "unknown", "unrecognized content"


def _capability_truth(type_id: str) -> dict[str, str]:
    descriptor = descriptor_for_engineering_type(type_id)
    return {
        "level_0_identify": descriptor.identification_state,
        "level_1_basic_metadata": descriptor.metadata_state,
        "level_2_static_parse": descriptor.static_inspection_state,
        "level_3_report": descriptor.report_state,
        "level_4_preview": descriptor.preview_state,
        "level_5_conversion": descriptor.conversion_state,
        "level_6_repair": descriptor.repair_state,
        "level_7_simulation_dry_run": descriptor.simulation_state,
        "level_8_generation_modification": descriptor.generation_state,
        "level_9_physical_output": descriptor.physical_output_state,
    }


def _dispatch_report(path: Path, *, type_id: str, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    if type_id in {"stl", "obj", "dae"}:
        return inspect_geometry(path, type_id=type_id, workspace_root=workspace_root, limits=limits)
    if type_id in {"step", "iges", "dxf", "f3d", "f3z"}:
        return inspect_cad(path, type_id=type_id, workspace_root=workspace_root, limits=limits)
    if type_id in {"urdf", "sdf"}:
        report = inspect_robot_model(path, type_id=type_id, workspace_root=workspace_root, limits=limits)
        report["safety_policy_version"] = str(load_robot_model_safety().get("version") or "robot-model-safety-0.1")
        return report
    if type_id == "gcode":
        cam_policy = load_cam_gcode_safety()
        try:
            feedrate_warning = float(cam_policy.get("feedrate_warning", 20_000))
            temperature_warning = float(cam_policy.get("temperature_warning_celsius", 300))
        except (TypeError, ValueError):
            feedrate_warning, temperature_warning = 20_000.0, 300.0
        report = inspect_gcode(path, limits=limits, feedrate_warning=feedrate_warning, temperature_warning=temperature_warning)
        report["safety_policy_version"] = str(cam_policy.get("version") or "cam-gcode-safety-0.1")
        report["feedrate_warning_threshold"] = feedrate_warning
        report["temperature_warning_celsius"] = temperature_warning
        return report
    if type_id == "blend":
        return inspect_blend(path, workspace_root=workspace_root, limits=limits)
    raise EngineeringInspectionError("unsupported_engineering_format")


def _report_file_name(type_id: str) -> str:
    if type_id in {"stl", "obj", "dae"}:
        return "geometry_report.json"
    if type_id in {"step", "iges", "dxf", "f3d", "f3z"}:
        return "cad_report.json"
    if type_id in {"urdf", "sdf"}:
        return "robot_model_report.json"
    if type_id == "gcode":
        return "gcode_report.json"
    return "blend_report.json"


def _safe_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_") and key not in {"risk_flags", "external_references"}}


def _compact_audit(
    *,
    operation_kind: str,
    operation_id: str,
    status: str,
    payload: Any,
    source_hash: str | None = None,
    size_bytes: int | None = None,
    type_id: str | None = None,
    family: str | None = None,
    risk_total: int | None = None,
    reference_count: int | None = None,
    artifact_id: str | None = None,
    artifact_hash: str | None = None,
    plan_hash: str | None = None,
    approval_id: str | None = None,
) -> bool:
    worker_key, worker_state = _worker_truth(type_id or "unknown")
    record = {
        "operation_kind": operation_kind,
        "status": status,
        "workspace_root_hash": hash_path(getattr(payload, "workspace_root", "")),
        "path_hash": hash_path(getattr(payload, "file_path", "")),
        "source_hash": source_hash,
        "size_bytes": size_bytes,
        "engineering_format": type_id,
        "engineering_family": family,
        "risk_total": risk_total,
        "external_reference_count": reference_count,
        "artifact_id": artifact_id,
        "artifact_hash": artifact_hash,
        "plan_hash": plan_hash,
        "approval_id": approval_id or getattr(payload, "approval_id", None),
        "policy_version": ENGINEERING_TYPE_POLICY_VERSION,
        "worker_key": worker_key,
        "worker_state": worker_state,
        "operator_approved": bool(getattr(payload, "operator_approved", False)),
        "approval_required": operation_kind == "engineering_preview_apply",
        "mutation_performed": False,
        "source_mutated": False,
        "network": False,
        "shell": False,
        "scripts_executed": False,
        "plugins_loaded": False,
        "physical_output_performed": False,
        "raw_content_logged": False,
    }
    return write_coding_audit_record(operation_kind, operation_id, {key: value for key, value in record.items() if value is not None})


def _blocked_inspection(payload: EngineeringInspectRequest, operation_id: str, reason: str, *, relative_path: str | None = None, target: Path | None = None) -> EngineeringInspectResponse:
    extension_type = engineering_type_from_extension(target or payload.file_path)
    descriptor = descriptor_for_engineering_type(extension_type)
    worker_key, worker_state = _worker_truth(extension_type)
    status = "approval_required" if reason == "explicit_inspection_approval_required" else "blocked"
    audit = _compact_audit(operation_kind="engineering_inspect", operation_id=operation_id, status=status, payload=payload, type_id=extension_type, family=descriptor.family)
    finish_engineering_job(operation_id, status=status, compact_summary={"blocked_reason": reason})
    return EngineeringInspectResponse(
        status=status,
        operation_id=operation_id,
        request_id=coding_request_id(operation_id),
        file_label=(target or Path(payload.file_path)).name or "selected engineering file",
        relative_path=relative_path,
        path_hash=hash_path(target or payload.file_path),
        extension_type=extension_type,
        descriptor=descriptor,
        capability_truth=_capability_truth(extension_type),
        policy_version=ENGINEERING_TYPE_POLICY_VERSION,
        worker_policy_version=load_engineering_inspection_limits()["version"],
        worker_key=worker_key,
        worker_state=worker_state,
        audit_written=audit,
        blocked_reason=reason,
        warnings=["Engineering inspection is local, read-only, bounded, and requires an explicit user request."],
    )


def inspect_engineering(payload: EngineeringInspectRequest) -> EngineeringInspectResponse:
    operation_id = _operation_id("inspect")
    start_engineering_job(operation_id, "engineering_inspect")
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, require_existing=True, allow_directory=False)
    if not guarded.allowed:
        return _blocked_inspection(payload, operation_id, guarded.reason or "path_not_allowed", relative_path=guarded.relative_path, target=guarded.target_path)
    if not payload.approval_granted:
        return _blocked_inspection(payload, operation_id, "explicit_inspection_approval_required", relative_path=guarded.relative_path, target=guarded.target_path)
    policy = load_engineering_inspection_limits()
    size = guarded.target_path.stat().st_size
    extension_type = engineering_type_from_extension(guarded.target_path)
    descriptor = descriptor_for_engineering_type(extension_type)
    worker_key, worker_state = _worker_truth(extension_type)
    if size > policy["limits"]["max_input_bytes"]:
        return _blocked_inspection(payload, operation_id, "engineering_input_limit_exceeded", relative_path=guarded.relative_path, target=guarded.target_path)
    detected_type, magic_summary = _magic_type(guarded.target_path, extension_type)
    if detected_type == "unknown" and extension_type in {"f3d"}:
        detected_type = extension_type
    effective_type = detected_type if detected_type != "unknown" else extension_type
    descriptor = descriptor_for_engineering_type(effective_type)
    worker_key, worker_state = _worker_truth(effective_type)
    source_hash = hash_file(guarded.target_path)
    try:
        report = _dispatch_report(guarded.target_path, type_id=effective_type, workspace_root=guarded.workspace_root, limits=policy["limits"])
    except EngineeringInspectionError as exc:
        reason = str(exc) or "engineering_static_parse_failed"
        audit = _compact_audit(operation_kind="engineering_inspect", operation_id=operation_id, status="blocked", payload=payload, source_hash=source_hash, size_bytes=size, type_id=effective_type, family=descriptor.family)
        finish_engineering_job(operation_id, status="blocked", compact_summary={"engineering_format": effective_type, "blocked_reason": reason})
        return EngineeringInspectResponse(
            status="blocked",
            operation_id=operation_id,
            request_id=coding_request_id(operation_id),
            file_label=guarded.target_path.name,
            relative_path=guarded.relative_path,
            path_hash=hash_path(guarded.target_path),
            source_sha256=source_hash,
            size_bytes=size,
            extension_type=extension_type,
            detected_type=detected_type,
            extension_content_match=detected_type == extension_type,
            magic_summary=magic_summary,
            descriptor=descriptor,
            capability_truth=_capability_truth(effective_type),
            policy_version=ENGINEERING_TYPE_POLICY_VERSION,
            worker_policy_version=policy["version"],
            worker_key=worker_key,
            worker_state=worker_state,
            audit_written=audit,
            blocked_reason=reason,
            warnings=["The malformed or over-limit engineering file failed closed; no external references were followed and no source bytes were changed."],
        )
    flags = list(report.get("risk_flags") or [])
    references = list(report.get("external_references") or [])
    public_report = _safe_report(report)
    capability_truth = _capability_truth(effective_type)
    preview_kind = "safe_local_svg_projection" if effective_type in _PREVIEW_TYPES else None
    preview_plan_hash = operation_plan_hash(
        action="engineering_preview",
        source_relative_path=guarded.relative_path,
        target_relative_path=None,
        source_hash=source_hash,
        details={"engineering_format": effective_type, "preview_kind": preview_kind, "policy_version": load_engineering_preview_limits()["version"]},
    ) if preview_kind else None
    report_payload = {
        "source_sha256": source_hash,
        "source_size_bytes": size,
        "engineering_format": effective_type,
        "family": descriptor.family,
        "report": public_report,
        "risk_flags": [flag.to_payload() for flag in flags],
        "external_references": [reference.to_payload() for reference in references],
        "capability_truth": capability_truth,
        "policy_version": policy["version"],
        "source_mutated": False,
        "network_used": False,
        "scripts_executed": False,
        "plugins_loaded": False,
        "physical_output_performed": False,
    }
    report_artifact = create_engineering_json_artifact(f"{descriptor.family}_report", _report_file_name(effective_type), report_payload)
    manifest_artifact = create_engineering_json_artifact(
        "manifest",
        "engineering_manifest.json",
        {
            "source_sha256": source_hash,
            "source_size_bytes": size,
            "engineering_format": effective_type,
            "family": descriptor.family,
            "magic_summary": report.get("magic_summary") or magic_summary,
            "risk_counts": risk_counts(flags),
            "external_reference_count": len(references),
            "report_artifact": report_artifact.to_payload(),
            "preview_plan_hash": preview_plan_hash,
            "policy_version": ENGINEERING_TYPE_POLICY_VERSION,
        },
    )
    audit = _compact_audit(
        operation_kind="engineering_inspect",
        operation_id=operation_id,
        status="completed",
        payload=payload,
        source_hash=source_hash,
        size_bytes=size,
        type_id=effective_type,
        family=descriptor.family,
        risk_total=sum(risk_counts(flags).values()),
        reference_count=len(references),
        artifact_id=report_artifact.artifact_id,
        artifact_hash=report_artifact.sha256,
    )
    finish_engineering_job(operation_id, status="completed", artifact_id=report_artifact.artifact_id, compact_summary={"engineering_format": effective_type, "family": descriptor.family, "risk_total": sum(risk_counts(flags).values()), "external_reference_count": len(references)})
    warnings = [
        "Static engineering inspection is descriptive only and is not engineering, manufacturing, structural, robot, or machine safety certification.",
        "No source mutation, machine send, robot control, script/plugin execution, network fetch, cloud upload, or physical output occurred.",
    ]
    if effective_type == "blend":
        warnings.append("Blender was not launched; embedded scripts, drivers, add-ons, and linked libraries were not loaded.")
    if effective_type in {"urdf", "sdf"}:
        warnings.append("ROS, RViz, Gazebo, controllers, xacro expansion, and plugins were not launched or loaded.")
    if effective_type == "gcode":
        warnings.append("G-code was treated as dangerous inert text and was not sent to a printer, CNC, controller, serial port, or API.")
    return EngineeringInspectResponse(
        status="completed",
        operation_id=operation_id,
        request_id=coding_request_id(operation_id),
        file_label=guarded.target_path.name,
        relative_path=guarded.relative_path,
        path_hash=hash_path(guarded.target_path),
        source_sha256=source_hash,
        size_bytes=size,
        extension_type=extension_type,
        detected_type=effective_type,
        extension_content_match=extension_type == effective_type,
        magic_summary=str(report.get("magic_summary") or magic_summary),
        descriptor=descriptor,
        report=public_report,
        capability_truth=capability_truth,
        risk_flags=flags,
        risk_counts=risk_counts(flags),
        external_references=references,
        external_reference_count=len(references),
        artifacts=[report_artifact, manifest_artifact],
        preview_plan_hash=preview_plan_hash,
        preview_kind=preview_kind,
        policy_version=ENGINEERING_TYPE_POLICY_VERSION,
        worker_policy_version=policy["version"],
        worker_key=worker_key,
        worker_state=worker_state,
        audit_written=audit,
        warnings=warnings,
    )


def _preview_plan_values(path: Path, *, relative_path: str | None, workspace_root: Path) -> tuple[str, str, str, str]:
    extension_type = engineering_type_from_extension(path)
    detected_type, _ = _magic_type(path, extension_type)
    effective_type = detected_type if detected_type != "unknown" else extension_type
    source_hash = hash_file(path)
    preview_kind = "safe_local_svg_projection" if effective_type in _PREVIEW_TYPES else "unavailable"
    plan_hash = operation_plan_hash(
        action="engineering_preview",
        source_relative_path=relative_path,
        target_relative_path=None,
        source_hash=source_hash,
        details={"engineering_format": effective_type, "preview_kind": preview_kind, "policy_version": load_engineering_preview_limits()["version"]},
    )
    return effective_type, source_hash, preview_kind, plan_hash


def plan_engineering_preview(payload: EngineeringPreviewPlanRequest) -> EngineeringPreviewPlan:
    operation_id = _operation_id("preview")
    start_engineering_job(operation_id, "engineering_preview_plan")
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, require_existing=True, allow_directory=False)
    policy = load_engineering_preview_limits()
    if not guarded.allowed:
        reason = guarded.reason or "path_not_allowed"
        finish_engineering_job(operation_id, status="blocked", compact_summary={"blocked_reason": reason})
        return EngineeringPreviewPlan(status="blocked", operation_id=operation_id, request_id=coding_request_id(operation_id), file_label=guarded.target_path.name or "selected engineering file", relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), source_sha256="", size_bytes=0, detected_type=engineering_type_from_extension(payload.file_path), family=descriptor_for_engineering_type(engineering_type_from_extension(payload.file_path)).family, preview_kind="unavailable", plan_hash="", policy_version=policy["version"], blocked_reason=reason, warnings=["No preview artifact was created."])
    size = guarded.target_path.stat().st_size
    effective_type, source_hash, preview_kind, plan_hash = _preview_plan_values(guarded.target_path, relative_path=guarded.relative_path, workspace_root=guarded.workspace_root)
    descriptor = descriptor_for_engineering_type(effective_type)
    reason = None
    if not payload.approval_granted:
        reason = "explicit_preview_planning_approval_required"
    elif size > policy["limits"]["max_input_bytes"]:
        reason = "engineering_preview_input_limit_exceeded"
    elif effective_type not in _PREVIEW_TYPES:
        reason = "preview_not_live_for_format"
    if reason:
        status = "approval_required" if reason.startswith("explicit_") else "blocked"
        _compact_audit(operation_kind="engineering_preview_plan", operation_id=operation_id, status=status, payload=payload, source_hash=source_hash, size_bytes=size, type_id=effective_type, family=descriptor.family, plan_hash=plan_hash)
        finish_engineering_job(operation_id, status=status, compact_summary={"engineering_format": effective_type, "blocked_reason": reason})
        return EngineeringPreviewPlan(status=status, operation_id=operation_id, request_id=coding_request_id(operation_id), file_label=guarded.target_path.name, relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), source_sha256=source_hash, size_bytes=size, detected_type=effective_type, family=descriptor.family, preview_kind=preview_kind, plan_hash=plan_hash, policy_version=policy["version"], blocked_reason=reason, warnings=["Preview availability is format-specific; no source or project file was written."])
    artifact = create_engineering_json_artifact(
        "preview_plan",
        "preview_plan.json",
        {"source_sha256": source_hash, "source_size_bytes": size, "engineering_format": effective_type, "family": descriptor.family, "preview_kind": preview_kind, "plan_hash": plan_hash, "policy_version": policy["version"], "approval_required": True, "source_mutation": False, "project_write": False},
    )
    _compact_audit(operation_kind="engineering_preview_plan", operation_id=operation_id, status="planned", payload=payload, source_hash=source_hash, size_bytes=size, type_id=effective_type, family=descriptor.family, artifact_id=artifact.artifact_id, artifact_hash=artifact.sha256, plan_hash=plan_hash)
    finish_engineering_job(operation_id, status="planned", artifact_id=artifact.artifact_id, compact_summary={"engineering_format": effective_type, "preview_kind": preview_kind})
    return EngineeringPreviewPlan(
        status="planned",
        operation_id=operation_id,
        request_id=coding_request_id(operation_id),
        file_label=guarded.target_path.name,
        relative_path=guarded.relative_path,
        path_hash=hash_path(guarded.target_path),
        source_sha256=source_hash,
        size_bytes=size,
        detected_type=effective_type,
        family=descriptor.family,
        preview_kind=preview_kind,
        plan_hash=plan_hash,
        policy_version=policy["version"],
        exact_approval={"operation_kind": "engineering_preview", "allowed_mutation_class": "engineering_preview_artifact", "one_time": True, "source_hash_required": True, "plan_hash_required": True},
        artifact=artifact,
        warnings=["Applying this plan requires a fresh one-time exact approval and creates only a private local SVG artifact."],
    )


def _svg_projection(segments: list[Any], *, type_id: str, width: int, height: int, max_segments: int) -> str:
    clean: list[tuple[float, float, float, float]] = []
    for segment in segments[:max_segments]:
        try:
            x1, y1 = float(segment[0][0]), float(segment[0][1])
            x2, y2 = float(segment[1][0]), float(segment[1][1])
        except (IndexError, TypeError, ValueError):
            continue
        if all(value == value and abs(value) != float("inf") for value in (x1, y1, x2, y2)):
            clean.append((x1, y1, x2, y2))
    if not clean:
        raise EngineeringInspectionError("no_previewable_geometry")
    xs = [value for item in clean for value in (item[0], item[2])]
    ys = [value for item in clean for value in (item[1], item[3])]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    margin = 24.0
    scale = min((width - margin * 2) / span_x, (height - margin * 2) / span_y)
    lines = []
    for x1, y1, x2, y2 in clean:
        px1 = margin + (x1 - min_x) * scale
        py1 = height - margin - (y1 - min_y) * scale
        px2 = margin + (x2 - min_x) * scale
        py2 = height - margin - (y2 - min_y) * scale
        lines.append(f'<line x1="{px1:.3f}" y1="{py1:.3f}" x2="{px2:.3f}" y2="{py2:.3f}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="#0b1017"/>'
        f'<g fill="none" stroke="#54d6c2" stroke-width="1" vector-effect="non-scaling-stroke">{"".join(lines)}</g>'
        f'<text x="18" y="22" fill="#d6dee8" font-family="sans-serif" font-size="13">EngineeringForge local {escape(type_id.upper())} projection · not a safety or manufacturing verdict</text>'
        '</svg>'
    )


def _blocked_preview_result(payload: EngineeringPreviewApplyRequest, *, guarded: Any, effective_type: str, source_hash: str, plan_hash: str, reason: str, approval_id: str | None = None) -> EngineeringPreviewResult:
    descriptor = descriptor_for_engineering_type(effective_type)
    policy = load_engineering_preview_limits()
    audit = _compact_audit(operation_kind="engineering_preview_apply", operation_id=payload.operation_id, status="approval_required" if "approval" in reason else "blocked", payload=payload, source_hash=source_hash, size_bytes=guarded.target_path.stat().st_size if guarded.target_path.is_file() else 0, type_id=effective_type, family=descriptor.family, plan_hash=plan_hash, approval_id=approval_id)
    finish_engineering_job(payload.operation_id, status="approval_required" if "approval" in reason else "blocked", approval_id=approval_id, compact_summary={"blocked_reason": reason})
    return EngineeringPreviewResult(status="approval_required" if "approval" in reason else "blocked", operation_id=payload.operation_id, request_id=coding_request_id(payload.operation_id, approval_id or payload.approval_id), approval_id=approval_id or payload.approval_id, file_label=guarded.target_path.name or "selected engineering file", relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path), source_sha256=source_hash, detected_type=effective_type, family=descriptor.family, preview_kind="safe_local_svg_projection" if effective_type in _PREVIEW_TYPES else "unavailable", plan_hash=plan_hash, policy_version=policy["version"], audit_written=audit, blocked_reason=reason, warnings=["No preview was created; the source remained unchanged and no project, device, network, script, plugin, or cloud boundary was crossed."])


def apply_engineering_preview(payload: EngineeringPreviewApplyRequest) -> EngineeringPreviewResult:
    start_engineering_job(payload.operation_id, "engineering_preview_apply")
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, require_existing=True, allow_directory=False)
    if not guarded.allowed:
        return _blocked_preview_result(payload, guarded=guarded, effective_type=engineering_type_from_extension(payload.file_path), source_hash=payload.expected_source_sha256, plan_hash=payload.expected_plan_hash, reason=guarded.reason or "path_not_allowed")
    effective_type, source_hash, preview_kind, plan_hash = _preview_plan_values(guarded.target_path, relative_path=guarded.relative_path, workspace_root=guarded.workspace_root)
    if effective_type not in _PREVIEW_TYPES:
        return _blocked_preview_result(payload, guarded=guarded, effective_type=effective_type, source_hash=source_hash, plan_hash=plan_hash, reason="preview_not_live_for_format")
    if source_hash != payload.expected_source_sha256 or plan_hash != payload.expected_plan_hash:
        return _blocked_preview_result(payload, guarded=guarded, effective_type=effective_type, source_hash=source_hash, plan_hash=plan_hash, reason="engineering_hash_or_plan_changed")
    if not payload.operator_approved:
        return _blocked_preview_result(payload, guarded=guarded, effective_type=effective_type, source_hash=source_hash, plan_hash=plan_hash, reason="exact_approval_required")
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind="engineering_preview",
        workspace_root=payload.workspace_root,
        exact_files=[payload.file_path],
        source_hash=source_hash,
        plan_hash=plan_hash,
        allowed_mutation_class="engineering_preview_artifact",
    )
    if not approval.allowed:
        return _blocked_preview_result(payload, guarded=guarded, effective_type=effective_type, source_hash=source_hash, plan_hash=plan_hash, reason=approval.reason or "exact_approval_required", approval_id=approval.approval_id)
    inspection_policy = load_engineering_inspection_limits()
    preview_policy = load_engineering_preview_limits()
    try:
        report = _dispatch_report(guarded.target_path, type_id=effective_type, workspace_root=guarded.workspace_root, limits=inspection_policy["limits"])
        svg = _svg_projection(report.get("_preview_segments") or [], type_id=effective_type, width=preview_policy["limits"]["width_pixels"], height=preview_policy["limits"]["height_pixels"], max_segments=preview_policy["limits"]["max_segments"])
    except EngineeringInspectionError as exc:
        return _blocked_preview_result(payload, guarded=guarded, effective_type=effective_type, source_hash=source_hash, plan_hash=plan_hash, reason=str(exc) or "preview_generation_failed", approval_id=approval.approval_id)
    if len(svg.encode("utf-8")) > preview_policy["limits"]["max_output_bytes"]:
        return _blocked_preview_result(payload, guarded=guarded, effective_type=effective_type, source_hash=source_hash, plan_hash=plan_hash, reason="preview_output_limit_exceeded", approval_id=approval.approval_id)
    after_hash = hash_file(guarded.target_path)
    if after_hash != source_hash:
        return _blocked_preview_result(payload, guarded=guarded, effective_type=effective_type, source_hash=after_hash, plan_hash=plan_hash, reason="engineering_source_changed_during_preview", approval_id=approval.approval_id)
    artifact = create_engineering_text_artifact("preview", "engineering_preview.svg", svg, media_type="image/svg+xml")
    receipt = create_engineering_json_artifact(
        "preview_receipt",
        "preview_receipt.json",
        {"approval_id": approval.approval_id, "source_sha256": source_hash, "engineering_format": effective_type, "preview_kind": preview_kind, "plan_hash": plan_hash, "preview_artifact": artifact.to_payload(), "local_only": True, "source_mutated": False, "project_root_written": False, "network_used": False, "scripts_executed": False, "plugins_loaded": False, "physical_output_performed": False, "policy_version": preview_policy["version"]},
    )
    descriptor = descriptor_for_engineering_type(effective_type)
    audit = _compact_audit(operation_kind="engineering_preview_apply", operation_id=payload.operation_id, status="completed", payload=payload, source_hash=source_hash, size_bytes=guarded.target_path.stat().st_size, type_id=effective_type, family=descriptor.family, artifact_id=artifact.artifact_id, artifact_hash=artifact.sha256, plan_hash=plan_hash, approval_id=approval.approval_id)
    finish_engineering_job(payload.operation_id, status="completed", approval_id=approval.approval_id, artifact_id=artifact.artifact_id, compact_summary={"engineering_format": effective_type, "preview_kind": preview_kind})
    return EngineeringPreviewResult(
        status="completed",
        operation_id=payload.operation_id,
        request_id=coding_request_id(payload.operation_id, approval.approval_id),
        approval_id=approval.approval_id,
        file_label=guarded.target_path.name,
        relative_path=guarded.relative_path,
        path_hash=hash_path(guarded.target_path),
        source_sha256=source_hash,
        detected_type=effective_type,
        family=descriptor.family,
        preview_kind=preview_kind,
        plan_hash=plan_hash,
        artifact=artifact,
        receipt_artifact=receipt,
        policy_version=preview_policy["version"],
        audit_written=audit,
        warnings=["The SVG is a bounded local 2D projection for review only; it is not a simulation, toolpath validation, printability verdict, or safety certification."],
    )


__all__ = ("apply_engineering_preview", "inspect_engineering", "plan_engineering_preview")
