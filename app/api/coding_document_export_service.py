"""Markdown/text export planning and approved execution for documents."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_backup_service import create_coding_backup, hash_file_bytes
from app.api.coding_document_adapter_service import extract_document_preview
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_operation_hash_service import operation_plan_hash
from app.api.coding_operation_service import consume_operation_approval
from app.api.schemas.coding_documents import (
    CodingDocumentApplyResponse,
    CodingDocumentExportApplyRequest,
    CodingDocumentExportPlanRequest,
    CodingDocumentPlanResponse,
)


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _render_markdown(file_label: str, preview) -> str:
    lines = [
        f"# Extracted document preview: {file_label}",
        "",
        "> Generated locally by Elysia document stewardship. Provenance is preview-bounded; embedded content and macros were not executed.",
        "",
        "## Document Type",
        "",
        f"- Type: {preview.descriptor.label}",
        f"- Family: {preview.descriptor.family}",
        f"- Adapter: {preview.descriptor.adapter}",
        "",
    ]
    if preview.metadata:
        lines.append("## Metadata")
        for key, value in preview.metadata.items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    if preview.outline:
        lines.append("## Outline")
        for item in preview.outline[:100]:
            label = item.get("text") or item.get("sheet") or item.get("kind")
            lines.append(f"- {label}")
        lines.append("")
    if preview.text_preview:
        lines.extend(["## Text Preview", "", preview.text_preview, ""])
    if preview.tables:
        lines.append("## Table Previews")
        for table in preview.tables[:10]:
            lines.append(f"### {table.get('kind', 'table')} {table.get('table') or table.get('sheet') or ''}".strip())
            for row in table.get("rows", [])[:25]:
                lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
            lines.append("")
    if preview.provenance:
        lines.append("## Provenance")
        for item in preview.provenance[:100]:
            label = ", ".join(f"{key}={value}" for key, value in item.items())
            lines.append(f"- {label}")
        lines.append("")
    if preview.warnings:
        lines.append("## Safety Notes")
        for warning in preview.warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines).strip() + "\n"


def _render_text(file_label: str, preview) -> str:
    lines = [
        f"Extracted document preview: {file_label}",
        "Generated locally by Elysia document stewardship.",
        f"Document type: {preview.descriptor.label}",
        f"Document family: {preview.descriptor.family}",
        f"Adapter: {preview.descriptor.adapter}",
        "",
    ]
    if preview.text_preview:
        lines.extend(["Text Preview:", preview.text_preview, ""])
    if preview.tables:
        lines.append("Table Previews:")
        for table in preview.tables[:10]:
            lines.append(f"- {table.get('kind', 'table')} {table.get('table') or table.get('sheet') or table.get('page') or ''}".strip())
            for row in table.get("rows", [])[:25]:
                lines.append("  " + "\t".join(str(cell).replace("\n", " ") for cell in row))
        lines.append("")
    if preview.provenance:
        lines.append("Provenance:")
        for item in preview.provenance[:100]:
            lines.append("- " + ", ".join(f"{key}={value}" for key, value in item.items()))
        lines.append("")
    if preview.warnings:
        lines.append("Safety Notes:")
        for warning in preview.warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines).strip() + "\n"


def _default_target(relative_path: str | None, export_format: str) -> str:
    stem = Path(relative_path or "document").name
    suffix = ".md" if export_format == "markdown" else ".txt"
    return f"{stem}.export{suffix}"


def plan_document_export(payload: CodingDocumentExportPlanRequest) -> CodingDocumentPlanResponse:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path)
    file_label = guarded.target_path.name
    if not guarded.allowed:
        return CodingDocumentPlanResponse(
            status="blocked",
            action="document_export",
            file_label=file_label,
            relative_path=guarded.relative_path,
            blocked_reason=guarded.reason,
            plan_summary="Document export is blocked by workspace/path policy.",
        )
    if not payload.approval_granted:
        return CodingDocumentPlanResponse(
            status="approval_required",
            action="document_export",
            file_label=file_label,
            relative_path=guarded.relative_path,
            blocked_reason="explicit_approval_required",
            plan_summary="Document export planning requires approval before source content is parsed.",
        )
    preview = extract_document_preview(guarded.target_path, max_chars=payload.max_chars or 12000)
    if preview.blocked_reason:
        return CodingDocumentPlanResponse(
            status="blocked",
            action="document_export",
            file_label=file_label,
            relative_path=guarded.relative_path,
            blocked_reason=preview.blocked_reason,
            plan_summary="Document export is blocked by document safety policy.",
            warnings=preview.warnings,
        )
    rendered = _render_markdown(file_label, preview) if payload.export_format == "markdown" else _render_text(file_label, preview)
    source_hash = preview.safety.byte_hash
    target_request = payload.target_path or _default_target(guarded.relative_path, payload.export_format)
    target_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=target_request, require_existing=False, allow_directory=False)
    if not target_guard.allowed:
        return CodingDocumentPlanResponse(status="blocked", action="document_export", file_label=file_label, relative_path=guarded.relative_path, target_relative_path=target_guard.relative_path, blocked_reason=target_guard.reason, plan_summary="Document export target is blocked by workspace/path policy.")
    target = target_guard.relative_path
    return CodingDocumentPlanResponse(
        status="planned",
        action="document_export",
        file_label=file_label,
        relative_path=guarded.relative_path,
        target_relative_path=target,
        plan_summary=f"Export bounded extracted {preview.descriptor.label} preview to {target}.",
        source_hash=source_hash,
        plan_hash=operation_plan_hash(
            action="document_export",
            source_relative_path=guarded.relative_path,
            target_relative_path=target,
            source_hash=source_hash,
            details={"export_format": payload.export_format},
        ),
        preview=rendered[:4000],
        warnings=preview.warnings + ["Approved export writes a derived Markdown/text file; it does not mutate the source document."],
    )


def apply_document_export(payload: CodingDocumentExportApplyRequest) -> CodingDocumentApplyResponse:
    plan = plan_document_export(payload)
    if plan.status != "planned":
        return CodingDocumentApplyResponse(
            status=plan.status,
            action="document_export",
            file_label=plan.file_label,
            relative_path=plan.relative_path,
            target_relative_path=plan.target_relative_path,
            blocked_reason=plan.blocked_reason,
            warnings=plan.warnings,
        )
    if not payload.operator_approved:
        return CodingDocumentApplyResponse(
            status="approval_required",
            action="document_export",
            file_label=plan.file_label,
            relative_path=plan.relative_path,
            target_relative_path=plan.target_relative_path,
            blocked_reason="operator_approval_required",
            warnings=["Document export execution requires explicit operator approval."],
        )
    if not payload.expected_source_hash:
        return CodingDocumentApplyResponse(status="blocked", action="document_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="expected_source_hash_required", warnings=["Document exports require the exact planned source hash."])
    if payload.expected_source_hash != plan.source_hash:
        return CodingDocumentApplyResponse(
            status="blocked",
            action="document_export",
            file_label=plan.file_label,
            relative_path=plan.relative_path,
            target_relative_path=plan.target_relative_path,
            blocked_reason="source_hash_mismatch",
            warnings=["Re-inspect the document before exporting."],
        )
    target_guard = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=plan.target_relative_path or _default_target(plan.relative_path, payload.export_format),
        require_existing=False,
        allow_directory=False,
    )
    if not target_guard.allowed:
        return CodingDocumentApplyResponse(
            status="blocked",
            action="document_export",
            file_label=plan.file_label,
            relative_path=plan.relative_path,
            target_relative_path=target_guard.relative_path,
            blocked_reason=target_guard.reason,
        )
    if target_guard.target_path.exists() and not payload.overwrite_existing:
        return CodingDocumentApplyResponse(
            status="blocked",
            action="document_export",
            file_label=plan.file_label,
            relative_path=plan.relative_path,
            target_relative_path=target_guard.relative_path,
            blocked_reason="target_exists",
            warnings=["Set overwrite_existing only after reviewing the target path."],
        )
    previous_hash = hash_file_bytes(target_guard.target_path) if target_guard.target_path.exists() else None
    if previous_hash and payload.expected_target_hash != previous_hash:
        return CodingDocumentApplyResponse(
            status="blocked",
            action="document_export",
            file_label=plan.file_label,
            relative_path=plan.relative_path,
            target_relative_path=target_guard.relative_path,
            blocked_reason="target_hash_mismatch",
            previous_hash=previous_hash,
            warnings=["Overwriting a derived target requires its exact current hash."],
        )
    source_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path)
    if not source_guard.allowed:
        return CodingDocumentApplyResponse(
            status="blocked",
            action="document_export",
            file_label=plan.file_label,
            relative_path=source_guard.relative_path,
            target_relative_path=target_guard.relative_path,
            blocked_reason=source_guard.reason,
        )
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind="document_export",
        workspace_root=payload.workspace_root,
        exact_files=[payload.file_path, plan.target_relative_path or ""],
        source_hash=plan.source_hash,
        plan_hash=plan.plan_hash or "",
        allowed_mutation_class="document_export",
    )
    if not approval.allowed:
        return CodingDocumentApplyResponse(status="approval_required", action="document_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target_guard.relative_path, approval_id=payload.approval_id, blocked_reason=approval.reason, warnings=["A matching one-time document export approval is required."])
    full_preview = extract_document_preview(source_guard.target_path, max_chars=payload.max_chars or 12000)
    output = _render_markdown(plan.file_label, full_preview) if payload.export_format == "markdown" else _render_text(plan.file_label, full_preview)
    backup = None
    if target_guard.target_path.exists():
        backup = create_coding_backup(
            workspace_root=target_guard.workspace_root,
            source_path=target_guard.target_path,
            source_relative_path=target_guard.relative_path or target_guard.target_path.name,
            operation_kind="document_export_overwrite",
            session_id=payload.session_id,
        )
    target_guard.target_path.parent.mkdir(parents=True, exist_ok=True)
    target_guard.target_path.write_text(output, encoding="utf-8")
    new_hash = _hash_text(output)
    audit_written = write_coding_audit_record(
        "document_export",
        uuid4().hex[:16],
        {
            "session_id": payload.session_id,
            "source_path_hash": hash_path(payload.file_path),
            "target_relative_path": target_guard.relative_path,
            "source_hash": plan.source_hash,
            "new_hash": new_hash,
            "format": payload.export_format,
            "approval_id": payload.approval_id,
            "plan_hash": plan.plan_hash,
            "backup_relative_path": backup.backup_relative_path if backup else None,
        },
    )
    return CodingDocumentApplyResponse(
        status="applied",
        action="document_export",
        file_label=plan.file_label,
        relative_path=plan.relative_path,
        target_relative_path=target_guard.relative_path,
        mutation_performed=True,
        audit_written=audit_written,
        previous_hash=previous_hash,
        new_hash=new_hash,
        approval_id=payload.approval_id,
        backup_relative_path=backup.backup_relative_path if backup else None,
        rollback_receipt_id=backup.receipt_id if backup else None,
        warnings=["Derived export file was written locally; source document was not modified."],
        rollback_note=(f"Restore from {backup.backup_relative_path} using receipt {backup.receipt_id}." if backup else "Delete the derived export file if it was not desired."),
    )


__all__ = ("apply_document_export", "plan_document_export")
