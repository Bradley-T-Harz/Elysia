"""Content-free contracts for local installation governance.

These models deliberately contain no Memory, Conversation, Project, prompt,
query, file, or model-context fields. Installation authority is not content
ownership.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from app.api.schemas.account import LocalAccountRole
from app.api.schemas.common import ElysiaSchemaModel


class AdminChangeKind(str, Enum):
    SET_ROLE = "set_role"
    SET_MANAGED_POLICY = "set_managed_policy"
    SET_ACCOUNT_ENABLED = "set_account_enabled"


class ManagedProfilePolicy(ElysiaSchemaModel):
    """Ceilings only: a managed policy can narrow, never grant, authority."""

    autonomy_maximum: int = Field(default=3, ge=1, le=5)
    internet_allowed: bool = False
    addons_allowed: bool = False
    connectors_allowed: bool = False
    coding_execution_allowed: bool = False
    project_agent_limit: int = Field(default=1, ge=0, le=32)
    external_mutations_allowed: bool = False
    background_cognition_allowed: bool = False
    cpu_percent_ceiling: int = Field(default=70, ge=10, le=100)
    ram_mb_ceiling: int = Field(default=4096, ge=256, le=262_144)
    vram_mb_ceiling: int = Field(default=4096, ge=0, le=131_072)
    network_filter_level: str = Field(
        default="strict", pattern=r"^(strict|moderate|standard)$"
    )
    consolidation_allowed: bool = True
    managed_backups_allowed: bool = True
    cold_archive_allowed: bool = True
    storage_budget_mb_ceiling: int = Field(default=32768, ge=512, le=10_000_000)
    backup_retention_maximum: int = Field(default=5, ge=1, le=50)


class AdminChangePreviewRequest(ElysiaSchemaModel):
    change_kind: AdminChangeKind
    target_user_id: str = Field(..., min_length=1, max_length=160)
    target_role: LocalAccountRole | None = None
    managed: bool | None = None
    managed_policy: ManagedProfilePolicy | None = None
    enabled: bool | None = None
    reason: str = Field(..., min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_change(self) -> "AdminChangePreviewRequest":
        if self.change_kind == AdminChangeKind.SET_ROLE and self.target_role is None:
            raise ValueError("Role changes require target_role.")
        if self.change_kind == AdminChangeKind.SET_MANAGED_POLICY:
            if self.managed is None or (self.managed and self.managed_policy is None):
                raise ValueError("Managed-policy changes require managed and policy values.")
        if self.change_kind == AdminChangeKind.SET_ACCOUNT_ENABLED and self.enabled is None:
            raise ValueError("Account enabled changes require enabled.")
        return self


class AdminChangeApplyRequest(ElysiaSchemaModel):
    preview_id: str = Field(..., min_length=1, max_length=160)
    approval_token: str = Field(..., min_length=16, max_length=512)


class AdminRestoreRequest(ElysiaSchemaModel):
    target_user_id: str = Field(..., min_length=1, max_length=160)
    history_id: str = Field(..., min_length=1, max_length=160)
    reason: str = Field(..., min_length=3, max_length=500)


class AdminRosterEntry(ElysiaSchemaModel):
    user_id: str
    username: str
    role: LocalAccountRole
    managed: bool
    enabled: bool
    active_session_count: int = Field(default=0, ge=0)
    policy_version: int = Field(default=1, ge=1)
    created_at_utc: str
    managed_policy: ManagedProfilePolicy | None = None


class AdminEventView(ElysiaSchemaModel):
    event_id: str
    event_type: str
    created_at_utc: str
    actor_user_id: str | None = None
    target_user_id: str | None = None
    safe_summary: str
    safe_details: dict[str, Any] = Field(default_factory=dict)


__all__ = (
    "AdminChangeApplyRequest",
    "AdminChangeKind",
    "AdminChangePreviewRequest",
    "AdminEventView",
    "AdminRestoreRequest",
    "AdminRosterEntry",
    "ManagedProfilePolicy",
)
