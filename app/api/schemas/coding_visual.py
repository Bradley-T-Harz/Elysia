"""Schemas for governed visual stewardship."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingVisualPathRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    file_path: str
    approval_granted: bool = False
    approval_reason: str | None = None


class CodingVisualOcrRequest(CodingVisualPathRequest):
    max_chars: int | None = None


class CodingVisualAnalysisRequest(CodingVisualPathRequest):
    include_semantic_provider: bool = False


class CodingVisualExportPlanRequest(CodingVisualPathRequest):
    export_format: Literal["markdown", "json", "png", "jpg", "jpeg", "webp", "tiff", "svg"] = "markdown"
    target_path: str | None = None


class CodingVisualExportApplyRequest(CodingVisualExportPlanRequest):
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    overwrite_existing: bool = False
    expected_source_hash: str | None = None
    expected_target_hash: str | None = None


class CodingVisualEditPlanRequest(CodingVisualPathRequest):
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CodingVisualApplyRequest(CodingVisualEditPlanRequest):
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    expected_source_hash: str | None = None
    expected_target_hash: str | None = None
    overwrite_existing: bool = False


class CodingVisualPlanResponse(ElysiaSchemaModel):
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


class CodingVisualApplyResponse(ElysiaSchemaModel):
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
    "CodingVisualAnalysisRequest",
    "CodingVisualApplyRequest",
    "CodingVisualApplyResponse",
    "CodingVisualEditPlanRequest",
    "CodingVisualExportApplyRequest",
    "CodingVisualExportPlanRequest",
    "CodingVisualOcrRequest",
    "CodingVisualPathRequest",
    "CodingVisualPlanResponse",
)
