"""Governed orchestration for read-only local media inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_media_adapter_service import inspect_media_path, thumbnail_media_path
from app.api.coding_media_type_registry import detect_media_type
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_trace_service import coding_request_id
from app.api.schemas.media import CodingMediaInspectResult, CodingMediaPathRequest


def _audit_payload(payload: CodingMediaPathRequest, result: dict[str, Any], *, operation_kind: str) -> dict[str, Any]:
    privacy = result.get("privacy_flags") if isinstance(result.get("privacy_flags"), dict) else {}
    return {
        "session_id": payload.session_id,
        "operation_kind": operation_kind,
        "status": result.get("status"),
        "relative_path": result.get("relative_path"),
        "workspace_root_hash": hash_path(payload.workspace_root),
        "source_hash": result.get("content_hash"),
        "format": result.get("container"),
        "media_family": result.get("media_family"),
        "size_bytes": result.get("size_bytes"),
        "duration_seconds": result.get("duration_seconds"),
        "stream_count": result.get("stream_count"),
        "thumbnail_status": result.get("thumbnail_status"),
        "privacy_flags_present": any(bool(value) for value in privacy.values()),
        "approval_required": True,
        "operator_approved": payload.approval_granted,
        "network": False,
        "shell": False,
        "mutation_performed": False,
    }


def _run_media_operation(
    payload: CodingMediaPathRequest,
    *,
    operation_kind: str,
    operation: Callable[[Path], dict[str, Any]],
) -> CodingMediaInspectResult:
    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.file_path,
        require_existing=True,
        allow_directory=False,
    )
    target = guarded.target_path if guarded.target_path else Path(payload.file_path)
    descriptor = detect_media_type(target)
    operation_id = f"media_{uuid4().hex[:16]}"
    result: dict[str, Any] = {
        "status": "blocked",
        "file_label": target.name or "selected media",
        "relative_path": guarded.relative_path,
        "path_hash": hash_path(target),
        "descriptor": descriptor.to_payload(),
        "media_family": descriptor.media_family,
        "blocked_reason": guarded.reason,
        "warnings": list(descriptor.notes),
    }
    if guarded.allowed and not payload.approval_granted:
        result.update(
            status="approval_required",
            blocked_reason="explicit_approval_required",
            warnings=["Media inspection requires explicit operator approval."],
        )
    elif guarded.allowed:
        result.update(operation(guarded.target_path))
        result.update(
            file_label=guarded.target_path.name,
            relative_path=guarded.relative_path,
            path_hash=hash_path(guarded.target_path),
        )

    audit_written = False
    try:
        audit_written = write_coding_audit_record(
            operation_kind,
            operation_id,
            _audit_payload(payload, result, operation_kind=operation_kind),
        )
    except OSError:
        result.setdefault("warnings", []).append("Compact media audit could not be persisted.")
    result.update(
        operation_id=operation_id,
        request_id=coding_request_id(operation_id),
        audit_written=audit_written,
    )
    return CodingMediaInspectResult(**result)


def inspect_governed_media(payload: CodingMediaPathRequest) -> CodingMediaInspectResult:
    return _run_media_operation(payload, operation_kind="media_inspect", operation=inspect_media_path)


def thumbnail_governed_media(payload: CodingMediaPathRequest) -> CodingMediaInspectResult:
    return _run_media_operation(payload, operation_kind="media_thumbnail", operation=thumbnail_media_path)


__all__ = ("inspect_governed_media", "thumbnail_governed_media")
