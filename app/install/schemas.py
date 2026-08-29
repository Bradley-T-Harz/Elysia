"""Typed, UI-safe schemas for read-only install-profile runtime truth."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class DependencyStatus(str, Enum):
    """Presence/readiness vocabulary for one declarative dependency."""

    PRESENT = "present"
    MISSING = "missing"
    OPTIONAL_MISSING = "optional_missing"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    PROFILE_GATED = "profile_gated"
    LAB_GATED = "lab_gated"
    NOT_APPLICABLE = "not_applicable"


class DependencyCategory(str, Enum):
    """Public dependency categories independent of package-manager details."""

    SYSTEM = "system"
    PYTHON = "python"
    NODE = "node"
    RUST = "rust"
    MODEL = "model"
    WORKER = "worker"
    EXTERNAL = "external"


class ProfileResolutionState(str, Enum):
    RESOLVED = "resolved"
    DEGRADED = "degraded"
    INVALID = "invalid"


class ProfileReadiness(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    PROFILE_GATED = "profile_gated"
    LAB_GATED = "lab_gated"


class DependencyStatusEntry(ElysiaSchemaModel):
    dependency_id: str
    label: str
    profile_id: str
    category: DependencyCategory
    catalog_kind: str
    required: bool
    purpose: str
    status: DependencyStatus
    activation_state: str
    check_method: str
    version: str | None = None
    warning: str | None = None
    external_download_required: bool
    private_data_may_be_involved: bool = False
    allowed_in_core: bool


class ProfileSummary(ElysiaSchemaModel):
    profile_id: str
    display_name: str
    purpose: str
    selected: bool
    included: bool
    default_enabled: bool
    maturity: str
    risk_level: str
    readiness: ProfileReadiness
    dependency_count: int = 0
    required_missing_count: int = 0
    required_unknown_count: int = 0
    optional_missing_count: int = 0
    network_runtime_default: str
    large_downloads_may_occur: bool
    private_data_leaves_machine_by_default: bool
    doctor_checks: list[str] = Field(default_factory=list)


class LocalOverrideSummary(ElysiaSchemaModel):
    state: str
    selection_source: str
    model_override_source: str
    configured_labels: list[str] = Field(default_factory=list)
    configured_count: int = 0
    raw_values_exposed: bool = False
    authority_granted: bool = False
    warning: str | None = None


class ProviderProfileSummary(ElysiaSchemaModel):
    provider_id: str = "ollama"
    command_status: DependencyStatus
    configured_role_ids: list[str] = Field(default_factory=list)
    local_override_loaded: bool = False
    network_check_performed: bool = False
    model_loaded: bool = False
    selection_authority_available: bool = False
    note: str


class WorkerProfileSummary(ElysiaSchemaModel):
    worker_id: str
    label: str
    profile_id: str
    status: DependencyStatus
    configured: bool = False
    enabled: bool = False
    doctor_proof_required: bool = True
    note: str


class InstallProfileStatusData(ElysiaSchemaModel):
    resolution_state: ProfileResolutionState
    active_profile_id: str
    active_profile_label: str
    selected_profile_ids: list[str]
    resolved_profile_ids: list[str]
    available_profiles: list[ProfileSummary]
    dependencies: list[DependencyStatusEntry]
    dependency_summary: dict[str, int]
    missing_core_dependency_ids: list[str]
    resolved_capability_groups: list[str]
    capability_tiers: dict[str, list[str]]
    local_overrides: LocalOverrideSummary
    provider_summary: ProviderProfileSummary
    worker_summaries: list[WorkerProfileSummary]
    profile_selection_grants_approval: bool = False
    install_authority_available: bool = False
    download_authority_available: bool = False
    worker_start_authority_available: bool = False
    doctor_executed: bool = False
    generated_at_utc: str


class DoctorCheck(ElysiaSchemaModel):
    check_id: str
    label: str
    category: str
    status: DependencyStatus
    classification: str = Field(pattern=r"^(ready|degraded|blocked|missing|not_selected)$")
    required: bool
    summary: str
    remediation: str | None = None


class DoctorStatusData(ElysiaSchemaModel):
    doctor_version: str
    overall_status: DependencyStatus
    runtime_mode: str
    active_profile_id: str
    checks: list[DoctorCheck]
    status_counts: dict[str, int]
    core_ready: bool
    optional_profiles_ready: bool
    local_api_reachable: bool
    local_auth: dict[str, object]
    path_contract: dict[str, object]
    first_run: dict[str, object]
    desktop_api_compatible: bool
    worker_execution_enabled: bool = False
    install_authority_available: bool = False
    repair_authority_available: bool = False
    raw_paths_exposed: bool = False
    generated_at_utc: str


__all__ = (
    "DependencyCategory",
    "DependencyStatus",
    "DependencyStatusEntry",
    "DoctorCheck",
    "DoctorStatusData",
    "InstallProfileStatusData",
    "LocalOverrideSummary",
    "ProfileReadiness",
    "ProfileResolutionState",
    "ProfileSummary",
    "ProviderProfileSummary",
    "WorkerProfileSummary",
)
