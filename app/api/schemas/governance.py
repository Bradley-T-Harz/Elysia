"""
Governance schema models for the Elysia local API bridge.

The original Stage 2 scalar contract is retained below as
LegacyGovernanceStateData for compatibility. The live GET /governance/state
contract is the richer canonical GovernanceStateData re-exported from
app.governance.schemas.governance_state.

This file should stay narrow:
- governance-state response-data models
- small governance-specific enums/literals

It should not contain:
- route logic
- service logic
- runtime logic
- policy-engine logic
- endpoint-specific business rules
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import ElysiaSchemaModel
from app.governance.schemas.governance_state import (
    GovernanceStateData as GovernanceStateData,
)


class GovernanceState(str, Enum):
    """
    State of the governance surface itself.

    Meanings:
    - live: actually available now
    - partial: present but incomplete
    - planned: designed/not yet live
    - unknown: not yet confirmed
    - unavailable: should exist but currently unreachable/unusable
    - degraded: present but reduced/impaired
    """

    LIVE = "live"
    PARTIAL = "partial"
    PLANNED = "planned"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class BoundaryMode(str, Enum):
    """
    Canonical boundary posture values for governance-state reporting.
    """

    LOCAL_ONLY = "local_only"
    LOCAL_PREFERRED = "local_preferred"
    APPROVAL_BOUND_EXTERNAL = "approval_bound_external"
    EXTERNAL_ALLOWED = "external_allowed"
    UNKNOWN = "unknown"


class AutonomyLevel(str, Enum):
    """
    Compact autonomy-posture values for governance-state reporting.
    """

    MINIMAL = "minimal"
    BOUNDED = "bounded"
    APPROVAL_BOUND = "approval_bound"
    SUPERVISED = "supervised"


class PolicySummary(ElysiaSchemaModel):
    """
    Compact policy-summary mapping suitable for UI inspection.
    """

    routing_governed: bool = Field(
        ...,
        description="Whether routing is governed rather than ad hoc.",
    )
    verification_required: bool = Field(
        ...,
        description="Whether verification is required in the governed body path.",
    )
    logging_required: bool = Field(
        ...,
        description="Whether runtime logging is required.",
    )
    journaling_required: bool = Field(
        ...,
        description="Whether session journaling is required.",
    )
    memory_discipline_enforced: bool = Field(
        ...,
        description="Whether memory discipline is actively enforced.",
    )
    external_actions_revocable: bool = Field(
        ...,
        description="Whether external actions are governed as revocable/narrow rather than unconstrained.",
    )


class LegacyGovernanceStateData(ElysiaSchemaModel):
    """
    Response data model for GET /governance/state.
    """

    governance_state: GovernanceState = Field(
        ...,
        description="State of the governance surface itself, distinct from the envelope request outcome.",
    )
    governance_available: bool = Field(
        ...,
        description="Whether the governance-truth surface is currently available for inspection.",
    )
    operator_identity: str | None = Field(
        default=None,
        description="Compact human-readable operator identity for the current governed relationship.",
    )
    owner_identity: str | None = Field(
        default=None,
        description="Compact human-readable owner/governing principal identity for Elysia.",
    )
    autonomy_level: AutonomyLevel | str | None = Field(
        default=None,
        description="Current autonomy posture relevant to governed runtime behavior.",
    )
    approval_required: bool = Field(
        ...,
        description="Whether current governance requires approval for certain classes of action.",
    )
    boundary_mode: BoundaryMode = Field(
        ...,
        description="Current boundary posture for local/external action.",
    )
    local_first_enforced: bool = Field(
        ...,
        description="Whether local-first posture is actively enforced by governance.",
    )
    silent_cloud_fallback_allowed: bool = Field(
        ...,
        description="Whether silent cloud fallback is permitted by current governance.",
    )
    governance_controls_live: bool = Field(
        ...,
        description="Whether editable/live governance controls are actually available right now.",
    )
    policy_summary: PolicySummary = Field(
        ...,
        description="Compact policy-summary mapping suitable for UI inspection.",
    )
    active_constraints: list[str] = Field(
        default_factory=list,
        description="Compact list of currently important governance constraints safe for UI display.",
    )
    last_updated_utc: str = Field(
        ...,
        description="UTC timestamp for when this governance snapshot was produced.",
    )


__all__ = (
    "AutonomyLevel",
    "BoundaryMode",
    "GovernanceState",
    "GovernanceStateData",
    "LegacyGovernanceStateData",
    "PolicySummary",
)
