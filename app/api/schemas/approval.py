"""
Approval schema models for the Elysia local API bridge.

This module is the Python-side implementation shape for the Stage 2 contract
behind:
- POST /approval/resolve

This file should stay narrow:
- approval-resolution request model
- approval-resolution response-data model
- small approval-specific enums/literals

It should not contain:
- route logic
- service logic
- runtime logic
- governance-engine logic
- endpoint-specific business rules
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import ElysiaSchemaModel


class ApprovalDecision(str, Enum):
    """
    Canonical incoming approval-decision values.

    Meanings:
    - approved: governance explicitly permits the request to proceed
    - denied: governance explicitly refuses the request
    - cancelled: governance explicitly cancels the request
    """

    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"


class ApprovalResolutionStatus(str, Enum):
    """
    Canonical resolution-status values for /approval/resolve response data.

    Meanings:
    - accepted: the resolution payload was valid, accepted, and recorded
    - rejected: the resolution payload was invalid or disallowed
    - ignored: the request was already resolved, expired, or no longer actionable
    - error: an unexpected failure occurred during resolution handling
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IGNORED = "ignored"
    ERROR = "error"


class ApprovalRequestState(str, Enum):
    """
    Canonical request-state values for approval-resolution response data.

    These describe the governed request after the resolution attempt, not the
    outer API-envelope outcome.
    """

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class ApprovalResolveRequest(ElysiaSchemaModel):
    """
    Request body model for POST /approval/resolve.

    This model mirrors the Stage 2 schema while keeping approval explicit,
    narrow, and governance-shaped.
    """

    request_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the real governed request being resolved.",
    )
    decision: ApprovalDecision = Field(
        ...,
        description="Explicit governance decision for the targeted request.",
    )
    resolver_identity: str | None = Field(
        default=None,
        max_length=80,
        description="Compact human-readable identity for who resolved the request.",
    )
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional compact explanation for the governance decision.",
    )
    ui_surface: str | None = Field(
        default=None,
        max_length=80,
        description="Optional UI surface metadata such as right_drawer or governance_room.",
    )
    resolution_context: dict[str, object] | None = Field(
        default=None,
        description="Optional compact structured context for future-proofing the resolution flow.",
    )


class ApprovalResolveResponseData(ElysiaSchemaModel):
    """
    Response data model for POST /approval/resolve.

    This is the endpoint-specific payload that lives inside the standard
    response envelope's data field.
    """

    request_id: str = Field(
        ...,
        description="Identifier of the governed request that was resolved.",
    )
    resolution_status: ApprovalResolutionStatus = Field(
        ...,
        description="Outcome of the resolution attempt itself.",
    )
    decision: ApprovalDecision = Field(
        ...,
        description="The explicit governance decision that was applied or attempted.",
    )
    resolver_identity: str | None = Field(
        default=None,
        description="Compact human-readable identity for who resolved the request.",
    )
    reason: str | None = Field(
        default=None,
        description="Optional human-readable reason stored with the resolution.",
    )
    resolved_at_utc: str = Field(
        ...,
        description="UTC timestamp for when the resolution outcome was recorded.",
    )
    request_state: ApprovalRequestState = Field(
        ...,
        description="Resulting state of the governed request after resolution.",
    )
    approval_required: bool = Field(
        ...,
        description="Formal governance truth about whether this request type is approval-bound.",
    )
    can_proceed: bool = Field(
        ...,
        description="Whether current governance now allows the request to move forward.",
    )
    next_action: str = Field(
        ...,
        description="Compact next-step signal for the UI after the resolution is processed.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Compact UI-safe notes about the resolution outcome.",
    )
    approval_id: str | None = Field(
        default=None,
        description="Exact approval identifier when an approved request may proceed.",
    )
    approval_token: str | None = Field(
        default=None,
        description="Expiring one-time token bound to the approved exact request.",
    )
    expires_at_utc: str | None = Field(
        default=None,
        description="Expiry for an issued one-time approval token.",
    )


__all__ = (
    "ApprovalDecision",
    "ApprovalRequestState",
    "ApprovalResolutionStatus",
    "ApprovalResolveRequest",
    "ApprovalResolveResponseData",
)
