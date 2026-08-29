"""Schemas for preview-only Marketplace add-on action planning."""

from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class AddonDependencySummary(ElysiaSchemaModel):
    ecosystem: str = ""
    package_name: str = ""
    source: str | None = None
    version_constraint: str | None = None
    required: bool = True


class AddonActionManifest(ElysiaSchemaModel):
    action_key: str
    action_label: str
    action_kind: str
    allowed: bool = False
    risk_level: str = "unknown"
    requires_local_operator_password: bool = True
    network_access: bool = False
    notes: list[str] = Field(default_factory=list)


class AddonActionPlanRequest(ElysiaSchemaModel):
    addon_id: str = Field(..., min_length=1, max_length=180)
    addon_name: str = Field(..., min_length=1, max_length=240)
    publisher: str | None = Field(default=None, max_length=240)
    action: AddonActionManifest
    dependencies: list[AddonDependencySummary] = Field(default_factory=list)
    trust_tier: str = "unknown"
    local_only: bool = True
    network_access: bool = False


class AddonActionPlan(ElysiaSchemaModel):
    addon_id: str
    addon_name: str
    action_key: str
    action_label: str
    action_kind: str
    plan_state: str = "preview_only"
    execution_enabled: bool = False
    mutation_allowed: bool = False
    command_execution_allowed: bool = False
    package_manager_allowed: bool = False
    shell_allowed: bool = False
    subprocess_allowed: bool = False
    requires_local_operator_password: bool = True
    requires_future_approval: bool = True
    trust_tier: str = "unknown"
    risk_level: str = "unknown"
    network_boundary: str = "local_only"
    dependency_count: int = 0
    dependency_summary: list[str] = Field(default_factory=list)
    plan_summary: str
    rollback_note: str
    refusal_reason: str
    private_data_sent: bool = False
    local_files_sent: bool = False
    memory_sent: bool = False
    request_traces_sent: bool = False
    dependency_inventory_sent: bool = False


class AddonActionPlanResult(ElysiaSchemaModel):
    plan: AddonActionPlan


__all__ = (
    "AddonActionManifest",
    "AddonActionPlan",
    "AddonActionPlanRequest",
    "AddonActionPlanResult",
    "AddonDependencySummary",
)
