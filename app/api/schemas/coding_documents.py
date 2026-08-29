"""Schemas for governed Codev document stewardship."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingDocumentPathRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    file_path: str
    approval_granted: bool = False
    approval_reason: str | None = None
    max_chars: int | None = None
    max_tables: int | None = None
    max_rows: int | None = None


class CodingDocumentExportPlanRequest(CodingDocumentPathRequest):
    export_format: Literal["markdown", "text"] = "markdown"
    target_path: str | None = None


class CodingDocumentExportApplyRequest(CodingDocumentExportPlanRequest):
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    overwrite_existing: bool = False
    expected_source_hash: str | None = None
    expected_target_hash: str | None = None


class CodingDocumentEditPlanRequest(CodingDocumentPathRequest):
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CodingDocumentEditApplyRequest(CodingDocumentEditPlanRequest):
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    expected_source_hash: str | None = None


class CodingDocumentDescriptorResponse(ElysiaSchemaModel):
    type_id: str
    label: str
    extension: str
    family: str
    adapter: str
    readable: bool
    extractable: bool
    exportable: bool
    editable: bool
    stable_edit_operations: list[str] = Field(default_factory=list)
    risk_flags: dict[str, bool] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class CodingDocumentPreviewResponse(ElysiaSchemaModel):
    status: str
    file_label: str
    relative_path: str | None = None
    path_hash: str | None = None
    blocked_reason: str | None = None
    descriptor: CodingDocumentDescriptorResponse
    safety: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    text_preview: str | None = None
    tables: list[dict[str, Any]] = Field(default_factory=list)
    outline: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    redactions: list[str] = Field(default_factory=list)
    secret_scan_findings: list[str] = Field(default_factory=list)


class CodingDocumentPlanResponse(ElysiaSchemaModel):
    status: str
    action: str
    file_label: str
    relative_path: str | None = None
    target_relative_path: str | None = None
    blocked_reason: str | None = None
    plan_summary: str
    source_hash: str | None = None
    plan_hash: str | None = None
    preview: str | None = None
    operation_details: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    approval_required: bool = True


class CodingDocumentApplyResponse(ElysiaSchemaModel):
    status: str
    action: str
    file_label: str
    relative_path: str | None = None
    target_relative_path: str | None = None
    blocked_reason: str | None = None
    mutation_performed: bool = False
    audit_written: bool = False
    previous_hash: str | None = None
    new_hash: str | None = None
    approval_id: str | None = None
    backup_relative_path: str | None = None
    rollback_receipt_id: str | None = None
    operation_details: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    rollback_note: str = "No mutation was performed."


__all__ = (
    "CodingDocumentApplyResponse",
    "CodingDocumentDescriptorResponse",
    "CodingDocumentEditApplyRequest",
    "CodingDocumentEditPlanRequest",
    "CodingDocumentExportApplyRequest",
    "CodingDocumentExportPlanRequest",
    "CodingDocumentPathRequest",
    "CodingDocumentPlanResponse",
    "CodingDocumentPreviewResponse",
)
