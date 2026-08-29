"""Approved, bounded selected-file preview service for Elysia Codev."""

from __future__ import annotations

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_file_adapter_service import build_adapter_preview, capability_flags, risk_flags
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_policy_service import coding_boundary_flags, file_preview_limits, load_coding_policy
from app.api.schemas.coding_file_types import CodingFileCapabilityFlags, CodingFileRiskFlags
from app.api.schemas.coding_files import CodingFileReadPreviewRequest, CodingFileReadPreviewResult


def read_selected_file_preview(payload: CodingFileReadPreviewRequest) -> CodingFileReadPreviewResult:
    policy = load_coding_policy()
    flags = coding_boundary_flags(policy)
    flags.selected_file_read_allowed = bool((policy.get("capabilities") or {}).get("selected_file_read", False))

    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.file_path,
        require_existing=True,
        allow_directory=False,
    )
    file_label = guarded.target_path.name or "selected file"
    path_hash = hash_path(guarded.target_path)

    if not flags.selected_file_read_allowed:
        return CodingFileReadPreviewResult(
            status="blocked",
            file_label=file_label,
            relative_path=guarded.relative_path,
            path_hash=path_hash,
            blocked_reason="selected_file_read_disabled",
            boundaries=flags,
        )

    if not payload.approval_granted:
        return CodingFileReadPreviewResult(
            status="approval_required",
            file_label=file_label,
            relative_path=guarded.relative_path,
            path_hash=path_hash,
            blocked_reason="explicit_approval_required",
            warnings=["Selected file preview requires explicit operator approval."],
            boundaries=flags,
        )

    if not guarded.allowed:
        return CodingFileReadPreviewResult(
            status="blocked",
            file_label=file_label,
            relative_path=guarded.relative_path,
            path_hash=path_hash,
            blocked_reason=guarded.reason,
            boundaries=flags,
        )

    max_bytes, max_lines = file_preview_limits(policy)
    if payload.max_bytes:
        max_bytes = min(max(1, int(payload.max_bytes)), max_bytes)
    if payload.max_lines:
        max_lines = min(max(1, int(payload.max_lines)), max_lines)

    adapter_preview = build_adapter_preview(
        guarded.target_path,
        max_bytes=max_bytes,
        max_lines=max_lines,
        max_file_bytes=int((policy.get("limits") or {}).get("max_text_file_bytes", 1024 * 1024)),
    )
    descriptor = adapter_preview.descriptor
    compact_audit_only = descriptor.adapter in {"archive", "database", "binary", "engineering"}
    if adapter_preview.blocked_reason:
        write_coding_audit_record(
            "file_preview_blocked",
            path_hash,
            {
                **({} if compact_audit_only else {"session_id": payload.session_id}),
                **({"path_hash": path_hash} if compact_audit_only else {"relative_path": guarded.relative_path}),
                "file_type": descriptor.type_id,
                "blocked_reason": adapter_preview.blocked_reason,
            },
        )
        return CodingFileReadPreviewResult(
            status="blocked",
            file_label=file_label,
            relative_path=guarded.relative_path,
            path_hash=path_hash,
            file_type_id=descriptor.type_id,
            file_type_label=descriptor.label,
            category=descriptor.category,
            adapter=descriptor.adapter,
            language_id=descriptor.language_id,
            capabilities=CodingFileCapabilityFlags(**capability_flags(descriptor)),
            risk_flags=CodingFileRiskFlags(**risk_flags(descriptor)),
            blocked_reason=adapter_preview.blocked_reason,
            warnings=list(descriptor.notes),
            boundaries=flags,
        )

    source_contents_included = adapter_preview.text_preview is not None
    result_flags = flags.model_copy() if hasattr(flags, "model_copy") else flags.copy()
    result_flags.source_contents_included = source_contents_included
    text_preview = adapter_preview.text_preview
    content_preview = adapter_preview.content_preview or ""
    write_coding_audit_record(
        "file_preview",
        path_hash,
        {
            **({} if compact_audit_only else {"session_id": payload.session_id}),
            **({"path_hash": path_hash} if compact_audit_only else {"relative_path": guarded.relative_path}),
            "file_type": descriptor.type_id,
            "adapter": descriptor.adapter,
            "content_hash": text_preview.decoded_text_hash if text_preview else None,
            "byte_hash": text_preview.raw_byte_hash if text_preview else None,
            "truncated": bool(text_preview.truncated) if text_preview else False,
            "secret_findings": adapter_preview.secret_scan_findings,
        },
    )

    return CodingFileReadPreviewResult(
        status="completed",
        file_label=file_label,
        relative_path=guarded.relative_path,
        path_hash=path_hash,
        content_hash=text_preview.decoded_text_hash if text_preview else None,
        byte_hash=text_preview.raw_byte_hash if text_preview else None,
        language_hint=descriptor.language_id,
        file_type_id=descriptor.type_id,
        file_type_label=descriptor.label,
        category=descriptor.category,
        adapter=descriptor.adapter,
        language_id=descriptor.language_id,
        encoding=text_preview.encoding if text_preview else None,
        line_ending=text_preview.line_ending if text_preview else None,
        line_count=text_preview.line_count if text_preview else 0,
        byte_count=text_preview.byte_count if text_preview else 0,
        parse_status=adapter_preview.parse_status,
        parse_summary=adapter_preview.parse_summary,
        capabilities=CodingFileCapabilityFlags(**capability_flags(descriptor)),
        risk_flags=CodingFileRiskFlags(**risk_flags(descriptor)),
        redactions=adapter_preview.redactions,
        source_contents_included=source_contents_included,
        content_preview=content_preview,
        bytes_returned=text_preview.bytes_returned if text_preview else 0,
        lines_returned=text_preview.lines_returned if text_preview else 0,
        truncated=text_preview.truncated if text_preview else False,
        warnings=(["Potential secret lines were redacted."] if adapter_preview.secret_scan_findings else []) + list(descriptor.notes),
        secret_scan_findings=adapter_preview.secret_scan_findings,
        boundaries=result_flags,
    )


__all__ = ("read_selected_file_preview",)
