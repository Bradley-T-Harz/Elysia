"""Schemas for governed command planning and disabled execution surfaces."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingCommandPlanRequest(ElysiaSchemaModel):
    session_id: str | None = None
    approval_mode: str = "plan_only"
    workspace_root: str
    command: list[str] = Field(default_factory=list)
    purpose: str


class CodingCommandPlan(ElysiaSchemaModel):
    status: str
    command_id: str | None = None
    command: list[str] = Field(default_factory=list)
    purpose: str
    allowlist_match: bool = False
    approval_required: bool = True
    execution_enabled: bool = False
    timeout_seconds: int | None = None
    output_limit_bytes: int | None = None
    plan_hash: str | None = None
    risk_labels: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CodingCommandRunApprovedRequest(ElysiaSchemaModel):
    approval_id: str
    approval_token: str | None = None
    approval_mode: str = "plan_only"
    command_id: str
    workspace_root: str
    operator_approved: bool = False


class CodingCommandRunResult(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    status: str
    run_id: str | None = None
    command_id: str
    command: list[str] = Field(default_factory=list)
    cwd_label: str = "approved repository"
    execution_performed: bool = False
    exit_code: int | None = None
    stdout_preview: str | None = None
    stderr_preview: str | None = None
    blocked_reason: str | None = None
    audit_written: bool = False
    approval_id: str | None = None
    operation_id: str | None = None
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    duration_ms: int | None = None
    output_truncated: bool = False
    output_sanitized: bool = True
    warnings: list[str] = Field(default_factory=list)


class CodingCommandStatus(ElysiaSchemaModel):
    run_id: str
    status: str = "not_found"
    execution_performed: bool = False


class CodingCommandCancelRequest(ElysiaSchemaModel):
    run_id: str


__all__ = (
    "CodingCommandCancelRequest",
    "CodingCommandPlan",
    "CodingCommandPlanRequest",
    "CodingCommandRunApprovedRequest",
    "CodingCommandRunResult",
    "CodingCommandStatus",
)
