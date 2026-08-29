"""Schemas for approval and result records for coding operations."""

from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingOperationApproveRequest(ElysiaSchemaModel):
    session_id: str | None = None
    operation_kind: str
    operation_summary: str
    workspace_root: str
    exact_files: list[str] = Field(default_factory=list)
    source_hash: str | None = None
    plan_hash: str
    allowed_mutation_class: str
    expires_in_seconds: int = Field(default=600, ge=30, le=1800)
    operator_approved: bool = False
    approval_phrase: str | None = None
    rollback_note: str


class CodingOperationApproval(ElysiaSchemaModel):
    status: str
    approval_id: str
    approval_token: str | None = None
    operation_kind: str
    operation_summary: str
    exact_files: list[str] = Field(default_factory=list)
    workspace_root_hash: str | None = None
    source_hash: str | None = None
    plan_hash: str | None = None
    allowed_mutation_class: str | None = None
    expires_at_utc: str
    consumed_at_utc: str | None = None
    one_time_use: bool = True
    audit_written: bool = False
    warnings: list[str] = Field(default_factory=list)


class CodingOperationResultRequest(ElysiaSchemaModel):
    approval_id: str
    approval_token: str | None = None
    status: str
    result_summary: str
    files_changed: list[str] = Field(default_factory=list)
    execution_performed: bool = False


class CodingOperationResult(ElysiaSchemaModel):
    status: str
    approval_id: str
    result_summary: str
    files_changed: list[str] = Field(default_factory=list)
    execution_performed: bool = False
    audit_written: bool = False
    warnings: list[str] = Field(default_factory=list)


class CodingApprovalConsumption(ElysiaSchemaModel):
    allowed: bool
    approval_id: str
    reason: str | None = None
    consumed_at_utc: str | None = None


__all__ = (
    "CodingOperationApproval",
    "CodingApprovalConsumption",
    "CodingOperationApproveRequest",
    "CodingOperationResult",
    "CodingOperationResultRequest",
)
