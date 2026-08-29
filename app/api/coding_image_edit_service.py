"""Approval-gated derived-copy visual edit planning and execution."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_backup_service import create_coding_backup, hash_file_bytes
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_operation_hash_service import operation_plan_hash
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_svg_adapter import sanitize_svg_text
from app.api.coding_visual_adapter_service import inspect_visual_path
from app.api.coding_visual_type_registry import detect_visual_type
from app.api.schemas.coding_visual import CodingVisualApplyRequest, CodingVisualApplyResponse, CodingVisualEditPlanRequest, CodingVisualPlanResponse


RASTER_OUTPUT_FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "tiff": "TIFF", "tif": "TIFF", "bmp": "BMP", "gif": "GIF"}


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _default_target(relative_path: str | None, operation: str, source_suffix: str) -> str:
    suffix = source_suffix or ".png"
    if operation == "convert_format":
        suffix = ".png"
    if operation == "rasterize_svg_png":
        suffix = ".png"
    return f"{Path(relative_path or 'visual').stem}.visual-{operation}{suffix}"


def _target_from_params(relative_path: str | None, operation: str, source_suffix: str, params: dict[str, Any]) -> str:
    target = params.get("target_path")
    if isinstance(target, str) and target.strip():
        return target
    if operation == "convert_format":
        export_format = str(params.get("format") or params.get("export_format") or "png").lower()
        return _default_target(relative_path, operation, "." + ("jpg" if export_format == "jpeg" else export_format))
    return _default_target(relative_path, operation, source_suffix)


def plan_visual_edit(payload: CodingVisualEditPlanRequest) -> CodingVisualPlanResponse:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=False)
    file_label = guarded.target_path.name
    action = payload.operation
    if not guarded.allowed:
        return CodingVisualPlanResponse(status="blocked", action=action, file_label=file_label, relative_path=guarded.relative_path, blocked_reason=guarded.reason, plan_summary="Visual edit is blocked by workspace/path policy.")
    if not payload.approval_granted:
        return CodingVisualPlanResponse(status="approval_required", action=action, file_label=file_label, relative_path=guarded.relative_path, blocked_reason="explicit_approval_required", plan_summary="Visual edit planning requires approval before source content is parsed.")
    preview = inspect_visual_path(guarded.target_path)
    descriptor = detect_visual_type(guarded.target_path)
    if preview.get("blocked_reason"):
        return CodingVisualPlanResponse(status="blocked", action=action, file_label=file_label, relative_path=guarded.relative_path, blocked_reason=str(preview.get("blocked_reason")), plan_summary="Visual edit is blocked by visual safety policy.", warnings=list(preview.get("warnings") or []))
    if action not in descriptor.stable_operations:
        return CodingVisualPlanResponse(status="blocked", action=action, file_label=file_label, relative_path=guarded.relative_path, blocked_reason="operation_not_supported_for_visual_type", plan_summary=f"{action} is not a stable governed operation for {descriptor.label}.", warnings=list(preview.get("warnings") or []))
    target_request = _target_from_params(guarded.relative_path, action, guarded.target_path.suffix, payload.parameters)
    target_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=target_request, require_existing=False, allow_directory=False)
    if not target_guard.allowed:
        return CodingVisualPlanResponse(status="blocked", action=action, file_label=file_label, relative_path=guarded.relative_path, target_relative_path=target_guard.relative_path, blocked_reason=target_guard.reason, plan_summary="Visual edit target is blocked by workspace/path policy.")
    target = target_guard.relative_path
    source_hash = str(preview.get("content_hash") or _hash_file(guarded.target_path))
    details = {"operation": action, "visual_type_id": descriptor.type_id, "parameters": payload.parameters}
    return CodingVisualPlanResponse(
        status="planned",
        action=action,
        file_label=file_label,
        relative_path=guarded.relative_path,
        target_relative_path=target,
        plan_summary=f"Plan governed {action} for {guarded.relative_path}; approval, source hash validation, derived-copy write, and audit are required.",
        source_hash=source_hash,
        plan_hash=operation_plan_hash(action="visual_edit", source_relative_path=guarded.relative_path, target_relative_path=target, source_hash=source_hash, details=details),
        operation_details=details,
        warnings=list(preview.get("warnings") or []) + ["No source mutation has been performed. Approved execution writes a derived visual copy."],
    )


def _save_image(image: Image.Image, target: Path, fmt: str | None = None, *, dpi: tuple[int, int] | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    out_fmt = fmt or RASTER_OUTPUT_FORMATS.get(target.suffix.lower().lstrip("."), "PNG")
    output = image
    if out_fmt == "JPEG" and output.mode not in {"RGB", "L"}:
        output = output.convert("RGB")
    kwargs: dict[str, Any] = {}
    if out_fmt in {"JPEG", "PNG", "WEBP"}:
        kwargs["optimize"] = True
    if dpi:
        kwargs["dpi"] = dpi
    output.save(target, format=out_fmt, **kwargs)


def _rect_tuple(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("rectangle_requires_four_numbers")
    left, top, right, bottom = (int(item) for item in value)
    if right <= left or bottom <= top:
        raise ValueError("invalid_rectangle")
    return left, top, right, bottom


def _apply_raster(source: Path, target: Path, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    with Image.open(source) as image:
        output = ImageOps.exif_transpose(image)
        details: dict[str, Any] = {}
        if operation == "resize":
            width = int(params["width"])
            height = int(params["height"])
            output = output.resize((width, height))
            details["size"] = [width, height]
        elif operation == "crop":
            box = _rect_tuple(params.get("box") or params.get("rectangle"))
            output = output.crop(box)
            details["box"] = list(box)
        elif operation == "rotate":
            degrees = float(params.get("degrees", 90))
            output = output.rotate(degrees, expand=True)
            details["degrees"] = degrees
        elif operation == "flip":
            axis = str(params.get("axis") or "horizontal")
            output = ImageOps.flip(output) if axis == "vertical" else ImageOps.mirror(output)
            details["axis"] = axis
        elif operation == "transpose":
            output = ImageOps.exif_transpose(output)
        elif operation in {"strip_exif", "strip_gps", "normalize_orientation", "optimize"}:
            output = ImageOps.exif_transpose(output)
            details["metadata_removed"] = operation in {"strip_exif", "strip_gps", "normalize_orientation"}
        elif operation == "convert_format":
            details["format"] = str(params.get("format") or params.get("export_format") or target.suffix.lstrip(".") or "png").lower()
        elif operation == "extract_frame":
            frame_index = int(params.get("frame_index", 0))
            image.seek(frame_index)
            output = image.copy()
            details["frame_index"] = frame_index
        elif operation == "make_thumbnail":
            size = int(params.get("size", 512))
            output.thumbnail((size, size))
            details["max_size"] = size
        elif operation in {"redact_rectangles", "blur_rectangles", "draw_rectangle"}:
            rectangles = params.get("rectangles") or [params.get("rectangle")]
            if not isinstance(rectangles, list) or not rectangles:
                raise ValueError("rectangles_required")
            output = output.convert("RGBA")
            draw = ImageDraw.Draw(output)
            for raw_rect in rectangles:
                rect = _rect_tuple(raw_rect)
                if operation == "redact_rectangles":
                    draw.rectangle(rect, fill=str(params.get("fill") or "black"))
                elif operation == "blur_rectangles":
                    region = output.crop(rect).filter(ImageFilter.GaussianBlur(radius=float(params.get("radius", 8))))
                    output.paste(region, rect)
                else:
                    draw.rectangle(rect, outline=str(params.get("outline") or "red"), width=int(params.get("width", 3)))
            details["rectangles"] = len(rectangles)
        elif operation == "add_text_overlay":
            output = output.convert("RGBA")
            draw = ImageDraw.Draw(output)
            position = params.get("position") or [20, 20]
            draw.text((int(position[0]), int(position[1])), str(params.get("text") or ""), fill=str(params.get("fill") or "red"))
            details["text_length"] = len(str(params.get("text") or ""))
        elif operation == "set_dpi":
            details["dpi"] = [int(params.get("x", 300)), int(params.get("y", 300))]
        else:
            raise ValueError("unsupported_raster_operation")
        export_format = str(params.get("format") or params.get("export_format") or target.suffix.lstrip(".") or "").lower()
        fmt = RASTER_OUTPUT_FORMATS.get(export_format) if export_format else None
        dpi = tuple(details["dpi"]) if "dpi" in details else None
        _save_image(output, target, fmt=fmt, dpi=dpi)  # type: ignore[arg-type]
        details["output_size"] = list(output.size)
        return details


def _apply_svg(source: Path, target: Path, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    sanitized, removed = sanitize_svg_text(source.read_text(encoding="utf-8", errors="replace"))
    if operation in {"sanitize_svg", "remove_unsafe_elements", "remove_external_references"}:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sanitized, encoding="utf-8")
        return {"sanitizer_removed": removed}
    if operation == "rasterize_svg_png":
        from app.api.coding_svg_adapter import rasterize_sanitized_svg_to_png

        rasterize_sanitized_svg_to_png(source, target)
        return {"format": "png", "sanitizer_removed": removed}
    root = ET.fromstring(sanitized)
    if operation == "set_dimensions":
        root.set("width", str(params["width"]))
        root.set("height", str(params["height"]))
    elif operation == "set_viewbox":
        root.set("viewBox", str(params["viewBox"]))
    elif operation == "edit_text":
        old = str(params.get("old") or "")
        new = str(params.get("new") or "")
        if not old:
            raise ValueError("old_text_required")
        replaced = 0
        for element in root.iter():
            if element.text and old in element.text:
                element.text = element.text.replace(old, new)
                replaced += 1
        if not replaced:
            raise ValueError("text_not_found")
    elif operation == "change_explicit_fill":
        old = str(params.get("old") or "")
        new = str(params.get("new") or "")
        changed = 0
        for element in root.iter():
            if element.get("fill") == old:
                element.set("fill", new)
                changed += 1
        if not changed:
            raise ValueError("fill_not_found")
    else:
        raise ValueError("unsupported_svg_operation")
    output = ET.tostring(root, encoding="unicode")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(output, encoding="utf-8")
    return {"sanitizer_removed": removed, "operation": operation}


def apply_visual_edit(payload: CodingVisualApplyRequest) -> CodingVisualApplyResponse:
    plan = plan_visual_edit(payload)
    if plan.status != "planned":
        return CodingVisualApplyResponse(status=plan.status, action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason=plan.blocked_reason, warnings=plan.warnings)
    if not payload.operator_approved:
        return CodingVisualApplyResponse(status="approval_required", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="operator_approval_required", warnings=["Visual edit execution requires explicit operator approval."])
    if not payload.expected_source_hash:
        return CodingVisualApplyResponse(status="blocked", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="expected_source_hash_required", warnings=["Visual edits require the exact planned source hash."])
    if payload.expected_source_hash != plan.source_hash:
        return CodingVisualApplyResponse(status="blocked", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="source_hash_mismatch", warnings=["Re-inspect the visual file before editing."])
    source = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=False)
    target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path or _default_target(plan.relative_path, plan.action, source.target_path.suffix), require_existing=False, allow_directory=False)
    if not source.allowed or not target.allowed:
        return CodingVisualApplyResponse(status="blocked", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason=source.reason or target.reason)
    if target.target_path.exists() and not payload.overwrite_existing:
        return CodingVisualApplyResponse(status="blocked", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason="target_exists", warnings=["Set overwrite_existing only after reviewing the target path."])
    previous_hash = hash_file_bytes(target.target_path) if target.target_path.exists() else None
    if previous_hash and payload.expected_target_hash != previous_hash:
        return CodingVisualApplyResponse(status="blocked", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason="target_hash_mismatch", previous_hash=previous_hash, warnings=["Overwriting a derived visual requires the exact target hash."])
    approval = consume_operation_approval(approval_id=payload.approval_id, approval_token=payload.approval_token, operation_kind="visual_edit", workspace_root=payload.workspace_root, exact_files=[payload.file_path, plan.target_relative_path or ""], source_hash=plan.source_hash, plan_hash=plan.plan_hash or "", allowed_mutation_class="visual_edit")
    if not approval.allowed:
        return CodingVisualApplyResponse(status="approval_required", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, approval_id=payload.approval_id, blocked_reason=approval.reason, warnings=["A matching one-time visual approval is required."])
    params = dict(payload.parameters)
    backup = None
    if target.target_path.exists():
        backup = create_coding_backup(workspace_root=target.workspace_root, source_path=target.target_path, source_relative_path=target.relative_path or target.target_path.name, operation_kind="visual_edit_overwrite", session_id=payload.session_id)
    try:
        descriptor = detect_visual_type(source.target_path)
        if descriptor.adapter == "svg":
            details = _apply_svg(source.target_path, target.target_path, plan.action, params)
            new_hash = _hash_text(target.target_path.read_text(encoding="utf-8", errors="replace"))
        else:
            details = _apply_raster(source.target_path, target.target_path, plan.action, params)
            new_hash = _hash_file(target.target_path)
    except Exception as exc:
        return CodingVisualApplyResponse(status="blocked", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason=f"visual_edit_failed:{exc.__class__.__name__}", warnings=[str(exc)])
    audit_written = write_coding_audit_record("visual_edit", uuid4().hex[:16], {"session_id": payload.session_id, "approval_id": payload.approval_id, "plan_hash": plan.plan_hash, "source_path_hash": hash_path(payload.file_path), "target_relative_path": target.relative_path, "source_hash": plan.source_hash, "new_hash": new_hash, "operation": plan.action, "details": details, "backup_relative_path": backup.backup_relative_path if backup else None})
    return CodingVisualApplyResponse(status="applied", action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, mutation_performed=True, audit_written=audit_written, previous_hash=previous_hash, new_hash=new_hash, approval_id=payload.approval_id, backup_relative_path=backup.backup_relative_path if backup else None, rollback_receipt_id=backup.receipt_id if backup else None, operation_details=details, warnings=["Derived visual edit was written locally; source visual was not modified."], rollback_note=(f"Restore from {backup.backup_relative_path} using receipt {backup.receipt_id}." if backup else "Delete the derived visual copy if this edit was not desired."))


__all__ = ("apply_visual_edit", "plan_visual_edit")
