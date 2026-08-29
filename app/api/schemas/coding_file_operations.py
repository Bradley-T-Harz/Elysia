"""Schemas for non-mutating file operation plans."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingFileOperationPlanRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    approval_mode: str = "plan_only"
    workspace_root: str
    operation_kind: str
    target_path: str
    destination_path: str | None = None
    content_hash: str | None = None
    summary: str
    new_text: str | None = None


class CodingFileOperationPlan(ElysiaSchemaModel):
    status: str
    operation_kind: str
    target_relative_path: str | None = None
    destination_relative_path: str | None = None
    blocked_reason: str | None = None
    mutation_performed: bool = False
    approval_required: bool = True
    source_hash: str | None = None
    plan_hash: str | None = None
    plan_steps: list[str] = Field(default_factory=list)
    risk_labels: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CodingFileOperationExecuteRequest(CodingFileOperationPlanRequest):
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    approval_phrase: str | None = None
    expected_content_hash: str | None = None


class CodingFileOperationExecuteResult(ElysiaSchemaModel):
    status: str
    operation_kind: str
    target_relative_path: str | None = None
    destination_relative_path: str | None = None
    previous_content_hash: str | None = None
    new_content_hash: str | None = None
    backup_relative_path: str | None = None
    rollback_receipt_id: str | None = None
    mutation_performed: bool = False
    audit_written: bool = False
    blocked_reason: str | None = None
    rollback_note: str
    warnings: list[str] = Field(default_factory=list)


__all__ = (
    "CodingFileOperationExecuteRequest",
    "CodingFileOperationExecuteResult",
    "CodingFileOperationPlan",
    "CodingFileOperationPlanRequest",
)
