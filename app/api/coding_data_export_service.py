"""Export planning and approved execution for science/data previews."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_backup_service import create_coding_backup, hash_file_bytes
from app.api.coding_data_adapter_service import inspect_data_path
from app.api.coding_data_type_registry import detect_data_type
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_operation_hash_service import operation_plan_hash
from app.api.coding_operation_service import consume_operation_approval
from app.api.schemas.coding_data import CodingDataApplyResponse, CodingDataExportApplyRequest, CodingDataExportPlanRequest, CodingDataPlanResponse


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _default_target(relative_path: str | None, export_format: str) -> str:
    suffix = {"markdown": ".md", "json": ".json", "csv": ".csv", "geojson": ".geojson"}.get(export_format, ".txt")
    return f"{Path(relative_path or 'data').name}.data-export{suffix}"


def _render_markdown(file_label: str, preview) -> str:
    lines = [
        f"# Data stewardship summary: {file_label}",
        "",
        "> Generated locally by Elysia. Preview is bounded; full raw datasets are not stored in audit.",
        "",
        "## Data Type",
        f"- Type: {preview.descriptor.label}",
        f"- Adapter: {preview.descriptor.adapter}",
        f"- Status: {preview.status}",
        "",
    ]
    for title, value in (("Metadata", preview.metadata), ("Schema", preview.schema_summary), ("Preview", preview.preview)):
        if value:
            lines.extend([f"## {title}", "", "```json", json.dumps(value, indent=2, sort_keys=True, default=str)[:8000], "```", ""])
    if preview.tables:
        lines.extend(["## Tables", ""])
        for table in preview.tables[:20]:
            lines.append(f"- {table.get('name') or table.get('table')}: {table.get('row_count', 'unknown')} rows")
    if preview.layers:
        lines.extend(["", "## Layers"])
        for layer in preview.layers[:20]:
            lines.append(f"- {layer.get('name')}: {layer.get('feature_count', 'unknown')} features")
    if preview.warnings:
        lines.extend(["", "## Safety Notes"])
        lines.extend(f"- {warning}" for warning in preview.warnings)
    return "\n".join(lines).strip() + "\n"


def _render_json(preview) -> str:
    return json.dumps(
        {
            "data_type": preview.descriptor.to_payload(),
            "status": preview.status,
            "metadata": preview.metadata,
            "schema_summary": preview.schema_summary,
            "preview": preview.preview,
            "tables": preview.tables,
            "layers": preview.layers,
            "bands": preview.bands,
            "dimensions": preview.dimensions,
            "variables": preview.variables,
            "warnings": preview.warnings,
            "provenance_refs": preview.provenance_refs,
            "redaction_count": preview.redaction_count,
        },
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"


def _render_export(file_label: str, preview, export_format: str) -> str:
    if export_format == "markdown":
        return _render_markdown(file_label, preview)
    return _render_json(preview)


def plan_data_export(payload: CodingDataExportPlanRequest) -> CodingDataPlanResponse:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=True)
    file_label = guarded.target_path.name
    if not guarded.allowed:
        return CodingDataPlanResponse(status="blocked", action="data_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason=guarded.reason, plan_summary="Data export is blocked by workspace/path policy.")
    if not payload.approval_granted:
        return CodingDataPlanResponse(status="approval_required", action="data_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason="explicit_approval_required", plan_summary="Data export planning requires approval before source content is parsed.")
    descriptor = detect_data_type(guarded.target_path)
    if descriptor.database or descriptor.adapter == "databaseforge":
        return CodingDataPlanResponse(status="blocked", action="data_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason="database_export_unavailable_by_design", plan_summary="Database export is unavailable in Chunk 7; only exact-approved snapshot-first schema preview is live.", warnings=["No rows, SQL, or database contents were read."])
    if payload.export_format in {"csv", "geojson"}:
        return CodingDataPlanResponse(status="blocked", action="data_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason="export_format_not_implemented", plan_summary=f"{payload.export_format} export is blocked because no format-correct serializer is implemented.", warnings=["Use Markdown or JSON summary export."])
    preview = inspect_data_path(guarded.target_path, max_rows=payload.max_rows or 50, max_features=payload.max_features or 25)
    if preview.blocked_reason:
        return CodingDataPlanResponse(status="blocked", action="data_export", file_label=file_label, relative_path=guarded.relative_path, blocked_reason=preview.blocked_reason, plan_summary="Data export is blocked by data safety policy.", warnings=preview.warnings)
    rendered = _render_export(file_label, preview, payload.export_format)
    target_request = payload.target_path or _default_target(guarded.relative_path, payload.export_format)
    target_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=target_request, require_existing=False, allow_directory=False)
    if not target_guard.allowed:
        return CodingDataPlanResponse(status="blocked", action="data_export", file_label=file_label, relative_path=guarded.relative_path, target_relative_path=target_guard.relative_path, blocked_reason=target_guard.reason, plan_summary="Data export target is blocked by workspace/path policy.")
    target = target_guard.relative_path
    details = {"export_format": payload.export_format, "data_type_id": preview.descriptor.type_id}
    return CodingDataPlanResponse(
        status="planned",
        action="data_export",
        file_label=file_label,
        relative_path=guarded.relative_path,
        target_relative_path=target,
        plan_summary=f"Export bounded {preview.descriptor.label} metadata/schema/preview to {target}.",
        source_hash=preview.content_hash,
        plan_hash=operation_plan_hash(action="data_export", source_relative_path=guarded.relative_path, target_relative_path=target, source_hash=preview.content_hash, details=details),
        preview=rendered[:4000],
        operation_details=details,
        warnings=preview.warnings + ["Approved export writes a derived summary file; it does not mutate the source dataset."],
    )


def apply_data_export(payload: CodingDataExportApplyRequest) -> CodingDataApplyResponse:
    plan = plan_data_export(payload)
    if plan.status != "planned":
        return CodingDataApplyResponse(status=plan.status, action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason=plan.blocked_reason, warnings=plan.warnings)
    if not payload.operator_approved:
        return CodingDataApplyResponse(status="approval_required", action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="operator_approval_required", warnings=["Data export execution requires explicit operator approval."])
    if not payload.expected_source_hash:
        return CodingDataApplyResponse(status="blocked", action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="expected_source_hash_required", warnings=["Data exports require the exact planned source hash."])
    if payload.expected_source_hash != plan.source_hash:
        return CodingDataApplyResponse(status="blocked", action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, blocked_reason="source_hash_mismatch", warnings=["Re-inspect the data file before exporting."])
    target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path or _default_target(plan.relative_path, payload.export_format), require_existing=False, allow_directory=False)
    if not target.allowed:
        return CodingDataApplyResponse(status="blocked", action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason=target.reason)
    if target.target_path.exists() and not payload.overwrite_existing:
        return CodingDataApplyResponse(status="blocked", action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason="target_exists", warnings=["Set overwrite_existing only after reviewing the target path."])
    previous_hash = hash_file_bytes(target.target_path) if target.target_path.exists() else None
    if previous_hash and payload.expected_target_hash != previous_hash:
        return CodingDataApplyResponse(status="blocked", action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, blocked_reason="target_hash_mismatch", previous_hash=previous_hash, warnings=["Overwriting an export requires the exact target hash."])
    source = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=True)
    approval = consume_operation_approval(approval_id=payload.approval_id, approval_token=payload.approval_token, operation_kind="data_export", workspace_root=payload.workspace_root, exact_files=[payload.file_path, plan.target_relative_path or ""], source_hash=plan.source_hash, plan_hash=plan.plan_hash or "", allowed_mutation_class="data_export")
    if not approval.allowed:
        return CodingDataApplyResponse(status="approval_required", action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, approval_id=payload.approval_id, blocked_reason=approval.reason, warnings=["A matching one-time data export approval is required."])
    preview = inspect_data_path(source.target_path, max_rows=payload.max_rows or 50, max_features=payload.max_features or 25)
    output = _render_export(plan.file_label, preview, payload.export_format)
    backup = None
    if target.target_path.exists():
        backup = create_coding_backup(workspace_root=target.workspace_root, source_path=target.target_path, source_relative_path=target.relative_path or target.target_path.name, operation_kind="data_export_overwrite", session_id=payload.session_id)
    target.target_path.parent.mkdir(parents=True, exist_ok=True)
    target.target_path.write_text(output, encoding="utf-8")
    new_hash = _hash_text(output)
    audit_written = write_coding_audit_record("data_export", uuid4().hex[:16], {"session_id": payload.session_id, "approval_id": payload.approval_id, "plan_hash": plan.plan_hash, "source_path_hash": hash_path(payload.file_path), "target_relative_path": target.relative_path, "source_hash": plan.source_hash, "new_hash": new_hash, "format": payload.export_format, "backup_relative_path": backup.backup_relative_path if backup else None})
    return CodingDataApplyResponse(status="applied", action="data_export", file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=target.relative_path, mutation_performed=True, audit_written=audit_written, previous_hash=previous_hash, new_hash=new_hash, approval_id=payload.approval_id, operation_details=plan.operation_details, backup=({"created": True, "backup_relative_path": backup.backup_relative_path, "receipt_id": backup.receipt_id} if backup else {"created": False}), warnings=["Derived data summary export was written locally; source dataset was not modified."], rollback_note=(f"Restore from {backup.backup_relative_path} using receipt {backup.receipt_id}." if backup else "Delete the derived export file if it was not desired."))


__all__ = ("apply_data_export", "plan_data_export")
