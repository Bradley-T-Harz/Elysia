"""Schemas for governed science/data stewardship."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingDataPathRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    file_path: str
    approval_granted: bool = False
    approval_reason: str | None = None
    max_rows: int | None = None
    max_features: int | None = None
    max_values: int | None = None


class CodingDataExportPlanRequest(CodingDataPathRequest):
    export_format: Literal["markdown", "json", "csv", "geojson"] = "markdown"
    target_path: str | None = None


class CodingDataExportApplyRequest(CodingDataExportPlanRequest):
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    overwrite_existing: bool = False
    expected_source_hash: str | None = None
    expected_target_hash: str | None = None


class CodingDataEditPlanRequest(CodingDataPathRequest):
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CodingDataApplyRequest(CodingDataEditPlanRequest):
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    expected_source_hash: str | None = None


class CodingDataDescriptorResponse(ElysiaSchemaModel):
    type_id: str
    label: str
    category: str
    adapter: str
    extensions: list[str] = Field(default_factory=list)
    readable: bool = True
    previewable: bool = True
    exportable: bool = True
    editable: bool = False
    mutation_supported: bool = False
    derived_copy_preferred: bool = False
    risk: str = "low"
    capabilities: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class CodingDataInspectResponse(ElysiaSchemaModel):
    status: str
    file_label: str
    relative_path: str | None = None
    path_hash: str | None = None
    content_hash: str | None = None
    blocked_reason: str | None = None
    descriptor: CodingDataDescriptorResponse
    size_bytes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_summary: dict[str, Any] = Field(default_factory=dict)
    preview: dict[str, Any] = Field(default_factory=dict)
    layers: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    bands: list[dict[str, Any]] = Field(default_factory=list)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    variables: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_flags: dict[str, Any] = Field(default_factory=dict)
    provenance_refs: list[dict[str, Any]] = Field(default_factory=list)
    redaction_count: int = 0
    preview_truncated: bool = False
    dependencies: dict[str, str] = Field(default_factory=dict)


class CodingDataPlanResponse(ElysiaSchemaModel):
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
    transaction: dict[str, Any] = Field(default_factory=dict)
    backup: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    approval_required: bool = True


class CodingDataApplyResponse(ElysiaSchemaModel):
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
    operation_details: dict[str, Any] = Field(default_factory=dict)
    transaction: dict[str, Any] = Field(default_factory=dict)
    backup: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    rollback_note: str = "No mutation was performed."


__all__ = (
    "CodingDataApplyRequest",
    "CodingDataApplyResponse",
    "CodingDataDescriptorResponse",
    "CodingDataEditPlanRequest",
    "CodingDataExportApplyRequest",
    "CodingDataExportPlanRequest",
    "CodingDataInspectResponse",
    "CodingDataPathRequest",
    "CodingDataPlanResponse",
)
