"""
Schema models for the Governance room state surface.

These models define the backend truth contract for GET /governance/state.

They are intentionally summary-oriented and card-friendly:
- explicit control state
- explicit control source
- explicit trust-zone posture
- explicit authority/routing/memory/approval/journaling summaries

This module is schema-only.
It must not:
- read config files
- inspect runtime directly
- resolve policy
- build envelopes
- act as a service layer
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.governance.governance_control_registry import (
    GovernanceMutationClassification,
    GovernanceMutationRisk,
)


class GovernanceControlState(str, Enum):
    """How real or editable a governance surface currently is."""

    LIVE_EDITABLE = "live_editable"
    DISPLAY_ONLY = "display_only"
    INACTIVE = "inactive"
    PLANNED = "planned"


class GovernanceSourceKind(str, Enum):
    """Where a governance truth surface comes from."""

    CONFIG_FILE = "config_file"
    POLICY_FILE = "policy_file"
    RUNTIME_STATE = "runtime_state"
    BRIDGE_CONSTANT = "bridge_constant"
    SERVICE_SUMMARY = "service_summary"
    ROUTE_SURFACE = "route_surface"
    DERIVED_SUMMARY = "derived_summary"
    PLANNED_SURFACE = "planned_surface"


class GovernanceAuthorityLevel(str, Enum):
    """How authoritative a control source should be treated."""

    CANONICAL = "canonical"
    AUTHORITATIVE = "authoritative"
    DERIVED = "derived"
    INFORMATIVE = "informative"


class TrustZoneAccessState(str, Enum):
    """High-level access posture for one trust zone."""

    OPEN = "open"
    BOUNDED = "bounded"
    REVIEW_REQUIRED = "review_required"
    SEALED = "sealed"
    PLANNED = "planned"


class GovernanceControlSource(BaseModel):
    """Where one governance truth surface comes from."""

    model_config = ConfigDict(extra="ignore")

    kind: GovernanceSourceKind
    label: str
    path: str | None = None
    authority_level: GovernanceAuthorityLevel = GovernanceAuthorityLevel.AUTHORITATIVE
    note: str | None = None

class GovernanceControl(BaseModel):
    """
    One governance control or governance truth card.

    This is the main atomic unit the Governance room can render.
    """

    model_config = ConfigDict(extra="ignore")

    control_id: str
    label: str
    value: str | bool | int | float | None = None
    detail: str | None = None
    state: GovernanceControlState
    source: GovernanceControlSource
    category: str | None = None
    authority_note: str | None = None
    mutation_classification: GovernanceMutationClassification = (
        GovernanceMutationClassification.READ_ONLY_CONSTITUTIONAL
    )
    mutation_risk: GovernanceMutationRisk = GovernanceMutationRisk.CRITICAL
    mutation_allowed: bool = False
    approval_required: bool = False
    mutation_reason: str | None = None
    mutation_later_gate: str | None = None

class TrustZoneSummary(BaseModel):
    """Summary of one trust zone or sealed domain."""

    model_config = ConfigDict(extra="ignore")

    zone_id: str
    label: str
    description: str | None = None
    access_state: TrustZoneAccessState
    assistant_can_read: bool = False
    assistant_can_write: bool = False
    user_can_read: bool = True
    user_can_write: bool = False
    sealed: bool = False
    state: GovernanceControlState
    source: GovernanceControlSource
    detail: str | None = None

class LocalityGovernanceSummary(BaseModel):
    """Summary of bridge locality and outward-boundary posture."""

    model_config = ConfigDict(extra="ignore")

    local_only_by_default: bool | None = None
    outbound_networking_posture: str | None = None
    crossed_boundary_default: str | None = None
    state: GovernanceControlState
    source: GovernanceControlSource
    controls: list[GovernanceControl] = Field(default_factory=list)
    detail: str | None = None

class RoleAuthorityEntry(BaseModel):
    """One role-authority record, usually derived from model role canon/config."""

    model_config = ConfigDict(extra="ignore")

    role_key: str
    label: str
    preferred_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)
    runtime: str | None = None
    local_only: bool | None = None
    enabled_by_default: bool | None = None
    state: GovernanceControlState
    source: GovernanceControlSource
    detail: str | None = None

class RoleAuthoritySummary(BaseModel):
    """Summary of role/model authority currently in force."""

    model_config = ConfigDict(extra="ignore")

    authority_label: str | None = None
    default_role: str | None = None
    roles: list[RoleAuthorityEntry] = Field(default_factory=list)
    controls: list[GovernanceControl] = Field(default_factory=list)
    detail: str | None = None

class RoutingPolicySummary(BaseModel):
    """Summary of routing posture and fallback law."""

    model_config = ConfigDict(extra="ignore")

    routing_mode: str | None = None
    local_first: bool | None = None
    silent_cloud_fallback_allowed: bool | None = None
    sensitive_work_must_remain_local: bool | None = None
    selected_default_role: str | None = None
    state: GovernanceControlState
    source: GovernanceControlSource
    controls: list[GovernanceControl] = Field(default_factory=list)
    detail: str | None = None

class MemoryGovernanceSummary(BaseModel):
    """Summary of memory-writing and memory-policy posture."""

    model_config = ConfigDict(extra="ignore")

    autonomous_updates_enabled: bool | None = None
    review_required_for_sensitive_mutations: bool | None = None
    known_memory_classes: list[str] = Field(default_factory=list)
    sealed_memory_posture: str | None = None
    retention_posture: str | None = None
    promotion_posture: str | None = None
    state: GovernanceControlState
    source: GovernanceControlSource
    controls: list[GovernanceControl] = Field(default_factory=list)
    detail: str | None = None

class ApprovalGovernanceSummary(BaseModel):
    """Summary of approval levels and action-gating posture."""

    model_config = ConfigDict(extra="ignore")

    approval_mode: str | None = None
    risky_actions_require_approval: bool | None = None
    destructive_actions_require_approval: bool | None = None
    outbound_actions_allowed: bool | None = None
    state: GovernanceControlState
    source: GovernanceControlSource
    controls: list[GovernanceControl] = Field(default_factory=list)
    detail: str | None = None

class JournalingGovernanceSummary(BaseModel):
    """Summary of journaling, trace, and audit posture."""

    model_config = ConfigDict(extra="ignore")

    journaling_enabled: bool | None = None
    journal_mode: str | None = None
    request_trace_enabled: bool | None = None
    audit_append_only: bool | None = None
    state: GovernanceControlState
    source: GovernanceControlSource
    controls: list[GovernanceControl] = Field(default_factory=list)
    detail: str | None = None

class GovernanceStateData(BaseModel):
    """
    Top-level governance-state payload for GET /governance/state.

    This is the backend truth surface the Governance room should render.
    """

    model_config = ConfigDict(extra="ignore")

    locality_summary: LocalityGovernanceSummary
    trust_zones: list[TrustZoneSummary] = Field(default_factory=list)
    role_authority: RoleAuthoritySummary
    routing_summary: RoutingPolicySummary
    memory_summary: MemoryGovernanceSummary
    approval_summary: ApprovalGovernanceSummary
    journaling_summary: JournalingGovernanceSummary
    control_states: list[GovernanceControl] = Field(default_factory=list)
    control_sources: list[GovernanceControlSource] = Field(default_factory=list)
    generated_at_utc: str | None = None
    governance_note: str | None = None
    governance_config_hash: str | None = None
    mutation_contract_version: str | None = None
    mutation_summary: dict[str, int] = Field(default_factory=dict)
