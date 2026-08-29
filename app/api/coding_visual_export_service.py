"""Export planning and approved execution for local visual stewardship."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_backup_service import create_coding_backup, hash_file_bytes
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_operation_hash_service import operation_plan_hash
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_svg_adapter import rasterize_sanitized_svg_to_png, sanitize_svg_text
from app.api.coding_visual_adapter_service import inspect_visual_path
from app.api.coding_visual_type_registry import detect_visual_type
from app.api.schemas.coding_visual import (
    CodingVisualApplyResponse,
    CodingVisualExportApplyRequest,
    CodingVisualExportPlanRequest,
    CodingVisualPlanResponse,
)


TEXT_EXPORT_FORMATS = {"markdown", "json"}
RASTER_EXPORT_FORMATS = {"png", "jpg", "jpeg", "webp", "tiff"}


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_target(relative_path: str | None, export_format: str) -> str:
    suffix = {
        "markdown": ".md",
        "json": ".json",
        "png": ".png",
        "jpg": ".jpg",
        "jpeg": ".jpg",
        "webp": ".webp",
        "tiff": ".tiff",
        "svg": ".svg",
    }.get(export_format, ".txt")
    return f"{Path(relative_path or 'visual').name}.visual-export{suffix}"


def _render_markdown(file_label: str, preview: dict[str, object]) -> str:
    descriptor = preview.get("descriptor") or {}
    lines = [
        f"# Visual stewardship summary: {file_label}",
        "",
        "> Generated locally by Elysia. Raw pixels, full OCR text, and precise EXIF GPS are not stored in audit.",
        "",
        "## Visual Type",
        f"- Type: {descriptor.get('label') if isinstance(descriptor, dict) else 'unknown'}",
        f"- Status: {preview.get('status')}",
        "",
    ]
    for title, key in (
        ("Metadata", "metadata"),
        ("EXIF Privacy", "exif_privacy"),
        ("SVG Safety", "svg_safety"),
        ("Deterministic Analysis", "analysis"),
    ):
        value = preview.get(key)
        if value:
            lines.extend([f"## {title}", "", "```json", json.dumps(value, indent=2, sort_keys=True, default=str)[:8000], "```", ""])
    warnings = preview.get("warnings") or []
    if warnings:
        lines.extend(["## Safety Notes", ""])
        lines.extend(f"- {warning}" for warning in warnings if isinstance(warning, str))
    return "\n".join(lines).strip() + "\n"


def _render_json(preview: dict[str, object]) -> str:
    safe = {key: value for key, value in preview.items() if key != "preview"}
    return json.dumps(safe, indent=2, sort_keys=True, default=str) + "\n"


def _render_export(file_label: str, preview: dict[str, object], export_format: str) -> str:
    if export_format == "markdown":
        return _render_markdown(file_label, preview)
    return _render_json(preview)


def plan_visual_export(payload: CodingVisualExportPlanRequest) -> CodingVisualPlanResponse:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=False)
    file_label = guarded.target_path.name
    if not guarded.allowed:
        return CodingVisualPlanResponse(status="blocked", action="visual_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason=guarded.reason, plan_summary="Visual export is blocked by workspace/path policy.")
    if not payload.approval_granted:
        return CodingVisualPlanResponse(status="approval_required", action="visual_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason="explicit_approval_required", plan_summary="Visual export planning requires approval before source content is parsed.")
    preview = inspect_visual_path(guarded.target_path)
    if preview.get("blocked_reason"):
        return CodingVisualPlanResponse(status="blocked", action="visual_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason=str(preview.get("blocked_reason")), plan_summary="Visual export is blocked by visual safety policy.", warnings=list(preview.get("warnings") or []))
    descriptor = detect_visual_type(guarded.target_path)
    export_format = payload.export_format.lower()
    if export_format == "svg" and descriptor.adapter != "svg":
        return CodingVisualPlanResponse(status="blocked", action="visual_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason="svg_export_requires_svg_source", plan_summary="Raster images cannot be exported as SVG by this governed adapter.")
    target_request = payload.target_path or _default_target(guarded.relative_path, export_format)
    target_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=target_request, require_existing=False, allow_directory=False)
    if not target_guard.allowed:
        return CodingVisualPlanResponse(status="blocked", action="visual_export", file_label=file_label, relative_path=guarded.relative_path, target_relative_path=target_guard.relative_path, blocked_reason=target_guard.reason, plan_summary="Visual export target is blocked by workspace/path policy.")
    target = target_guard.relative_path
    preview_text = _render_export(file_label, preview, export_format) if export_format in TEXT_EXPORT_FORMATS else f"Create derived visual copy {target} from {guarded.relative_path} as {export_format}."
    source_hash = str(preview.get("content_hash") or _hash_file(guarded.target_path))
    details = {"export_format": export_format, "visual_type_id": descriptor.type_id}
    return CodingVisualPlanResponse(
        status="planned",
        action="visual_export",
        file_label=file_label,
        relative_path=guarded.relative_path,
        target_relative_path=target,
        plan_summary=f"Export {descriptor.label} to {target}. Source image is not modified.",
        source_hash=source_hash,
        plan_hash=operation_plan_hash(action="visual_export", source_relative_path=guarded.relative_path, target_relative_path=target, source_hash=source_hash, details=details),
        preview=preview_text[:4000],
        operation_details=details,
        warnings=list(preview.get("warnings") or []) + ["Approved export writes a derived file; it does not mutate the source visual."],
    )


def _write_raster_export(source: Path, target: Path, export_format: str) -> None:
    with Image.open(source) as image:
        output = ImageOps.exif_transpose(image)
        fmt = "JPEG" if export_format in {"jpg", "jpeg"} else "TIFF" if export_format == "tiff" else export_format.upper()
        if fmt == "JPEG" and output.mode not in {"RGB", "L"}:
            output = output.convert("RGB")
        target.parent.mkdir(parents=True, exist_ok=True)
        output.save(target, format=fmt, optimize=fmt in {"JPEG", "PNG", "WEBP"})


def apply_visual_export(payload: CodingVisualExportApplyRequest) -> CodingVisualApplyResponse:
    plan = plan_visual_export(payload)
    if plan.status != "planned":
        return CodingVisualApplyResponse(status=plan.status, action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason=plan.blocked_reason, warnings=plan.warnings)
    if not payload.operator_approved:
        return CodingVisualApplyResponse(status="approval_required", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="operator_approval_required", warnings=["Visual export execution requires explicit operator approval."])
    if not payload.expected_source_hash:
        return CodingVisualApplyResponse(status="blocked", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="expected_source_hash_required", warnings=["Visual exports require the exact planned source hash."])
    if payload.expected_source_hash != plan.source_hash:
        return CodingVisualApplyResponse(status="blocked", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="source_hash_mismatch", warnings=["Re-inspect the visual file before exporting."])
    source = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=False)
    target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path or _default_target(plan.relative_path, payload.export_format), require_existing=False, allow_directory=False)
    if not source.allowed or not target.allowed:
        return CodingVisualApplyResponse(status="blocked", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason=source.reason or target.reason)
    if target.target_path.exists() and not payload.overwrite_existing:
        return CodingVisualApplyResponse(status="blocked", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason="target_exists", warnings=["Set overwrite_existing only after reviewing the target path."])
    previous_hash = hash_file_bytes(target.target_path) if target.target_path.exists() else None
    if previous_hash and payload.expected_target_hash != previous_hash:
        return CodingVisualApplyResponse(status="blocked", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason="target_hash_mismatch", previous_hash=previous_hash, warnings=["Overwriting a derived visual requires the exact target hash."])
    approval = consume_operation_approval(approval_id=payload.approval_id, approval_token=payload.approval_token, operation_kind="visual_export", workspace_root=payload.workspace_root, exact_files=[payload.file_path, plan.target_relative_path or ""], source_hash=plan.source_hash, plan_hash=plan.plan_hash or "", allowed_mutation_class="visual_export")
    if not approval.allowed:
        return CodingVisualApplyResponse(status="approval_required", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, approval_id=payload.approval_id, blocked_reason=approval.reason, warnings=["A matching one-time visual export approval is required."])
    backup = None
    if target.target_path.exists():
        backup = create_coding_backup(workspace_root=target.workspace_root, source_path=target.target_path, source_relative_path=target.relative_path or target.target_path.name, operation_kind="visual_export_overwrite", session_id=payload.session_id)
    export_format = payload.export_format.lower()
    if export_format in TEXT_EXPORT_FORMATS:
        output = _render_export(plan.file_label, inspect_visual_path(source.target_path), export_format)
        target.target_path.parent.mkdir(parents=True, exist_ok=True)
        target.target_path.write_text(output, encoding="utf-8")
        new_hash = _hash_text(output)
    elif export_format == "svg":
        sanitized, _removed = sanitize_svg_text(source.target_path.read_text(encoding="utf-8", errors="replace"))
        target.target_path.parent.mkdir(parents=True, exist_ok=True)
        target.target_path.write_text(sanitized, encoding="utf-8")
        new_hash = _hash_text(sanitized)
    elif detect_visual_type(source.target_path).adapter == "svg" and export_format == "png":
        target.target_path.parent.mkdir(parents=True, exist_ok=True)
        rasterize_sanitized_svg_to_png(source.target_path, target.target_path)
        new_hash = _hash_file(target.target_path)
    elif export_format in RASTER_EXPORT_FORMATS:
        _write_raster_export(source.target_path, target.target_path, export_format)
        new_hash = _hash_file(target.target_path)
    else:
        return CodingVisualApplyResponse(status="blocked", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason="unsupported_export_format")
    audit_written = write_coding_audit_record("visual_export", uuid4().hex[:16], {"session_id": payload.session_id, "approval_id": payload.approval_id, "plan_hash": plan.plan_hash, "source_path_hash": hash_path(payload.file_path), "target_relative_path": target.relative_path, "source_hash": plan.source_hash, "new_hash": new_hash, "format": export_format, "backup_relative_path": backup.backup_relative_path if backup else None})
    return CodingVisualApplyResponse(status="applied", action="visual_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, mutation_performed=True, audit_written=audit_written, previous_hash=previous_hash, new_hash=new_hash, approval_id=payload.approval_id, backup_relative_path=backup.backup_relative_path if backup else None, rollback_receipt_id=backup.receipt_id if backup else None, operation_details=plan.operation_details, warnings=["Derived visual export was written locally; source visual was not modified."], rollback_note=(f"Restore from {backup.backup_relative_path} using receipt {backup.receipt_id}." if backup else "Delete the derived export file if it was not desired."))


__all__ = ("apply_visual_export", "plan_visual_export")
