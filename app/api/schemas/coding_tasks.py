"""Schemas for bounded, checkpoint-only Developer Lab task contracts."""

from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingTaskPlanRequest(ElysiaSchemaModel):
    session_id: str | None = None
    objective: str = Field(min_length=1, max_length=2000)
    workspace_label: str | None = None
    workspace_root: str | None = None
    allowed_files: list[str] = Field(default_factory=list, max_length=20)
    max_steps: int = Field(default=4, ge=1, le=8)
    max_minutes: int = Field(default=15, ge=1, le=30)


class CodingTaskPlan(ElysiaSchemaModel):
    status: str
    task_id: str | None = None
    task_hash: str | None = None
    objective: str
    workspace_root_hash: str | None = None
    allowed_files: list[str] = Field(default_factory=list)
    allowed_tool_ids: list[str] = Field(default_factory=list)
    max_steps: int = 0
    max_minutes: int = 0
    current_step: int = 0
    expires_at_utc: str | None = None
    plan_steps: list[str] = Field(default_factory=list)
    autonomous_loop_allowed: bool = False
    background_execution_allowed: bool = False
    mutation_allowed: bool = False
    command_execution_allowed: bool = False
    human_approval_required: bool = True
    stop_available: bool = True
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CodingTaskApproveRequest(ElysiaSchemaModel):
    task_id: str
    task_hash: str
    operator_approved: bool = False
    confirmation_phrase: str | None = None


class CodingTaskApproval(ElysiaSchemaModel):
    status: str
    task_id: str
    task_hash: str | None = None
    task_token: str | None = None
    expires_at_utc: str | None = None
    next_step_requires_operator: bool = True
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CodingTaskCheckpointRequest(ElysiaSchemaModel):
    task_id: str
    task_token: str | None = None
    operator_approved: bool = False


class CodingTaskStopRequest(ElysiaSchemaModel):
    task_id: str
    reason: str = Field(default="operator_stop", max_length=200)


class CodingTaskCheckpoint(ElysiaSchemaModel):
    status: str
    task_id: str
    current_step: int = 0
    max_steps: int = 0
    step_label: str | None = None
    receipt_id: str | None = None
    execution_performed: bool = False
    mutation_performed: bool = False
    command_performed: bool = False
    continuation_scheduled: bool = False
    stopped: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


__all__ = (
    "CodingTaskApproval",
    "CodingTaskApproveRequest",
    "CodingTaskCheckpoint",
    "CodingTaskCheckpointRequest",
    "CodingTaskPlan",
    "CodingTaskPlanRequest",
    "CodingTaskStopRequest",
)
