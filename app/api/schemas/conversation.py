"""
Conversation metadata schema models for the Elysia local API bridge.

This module is the Python-side implementation shape for the Stage 2 conversation
metadata contract. It is for compact conversation-container metadata only.

This file should stay narrow:
- conversation metadata model
- small conversation-specific enums/literals

It should not contain:
- route logic
- service logic
- runtime logic
- storage logic
- full thread/message-history models
- endpoint-specific business rules
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import (
    ApprovalState,
    CapabilityState,
    ElysiaSchemaModel,
    LocalityState,
)


class ConversationState(str, Enum):
    """
    Canonical state of the conversation container itself.

    Meanings:
    - active: the conversation container is active
    - inactive: the conversation container exists but is intentionally not active
    - archived: the conversation container is archived from the primary active view
    - planned: the conversation container shape is designed but not yet truly live
    - unknown: the conversation-container state has not yet been confirmed
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    PLANNED = "planned"
    UNKNOWN = "unknown"


class ConversationMetadata(ElysiaSchemaModel):
    """
    Compact shared metadata object describing a conversation container.

    This is not a message-history schema. It is the metadata shape for:
    - conversations list items
    - conversation headers
    - recent conversations
    - chat linkage
    - later request/project linkage surfaces
    """

    conversation_id: str = Field(
        ...,
        min_length=1,
        description="Stable identifier for the conversation container.",
    )
    owner_user_id: str | None = Field(
        default=None,
        description="Stable Identity authority identifier for the owning local account.",
    )
    title: str | None = Field(
        default=None,
        description="Human-facing conversation title for list and header use.",
    )
    created_at_utc: str | None = Field(
        default=None,
        description="UTC timestamp for when the conversation container was created.",
    )
    updated_at_utc: str | None = Field(
        default=None,
        description="UTC timestamp for the most recent meaningful update to the conversation container.",
    )
    last_message_preview: str | None = Field(
        default=None,
        description="Short preview text representing the latest user-visible exchange.",
    )
    message_count: int | None = Field(
        default=None,
        ge=0,
        description="Count of messages associated with the conversation container when available.",
    )
    current_mode: str | None = Field(
        default=None,
        description="Most recent or currently relevant mode posture associated with the conversation.",
    )
    current_role: str | None = Field(
        default=None,
        description="Most recent or currently relevant routed role expression associated with the conversation.",
    )
    capability_state: CapabilityState = Field(
        ...,
        description="Capability truth relevant to how this conversation should be rendered or resumed.",
    )
    locality: LocalityState = Field(
        ...,
        description="Whether the conversation's current/resumable path is local, crossed a boundary, or unknown.",
    )
    approval_state: ApprovalState = Field(
        ...,
        description="Broad approval posture relevant to resuming or continuing work in this conversation.",
    )
    project_id: str | None = Field(
        default=None,
        description="Optional project linkage identifier for future project-aware conversation views.",
    )
    archived: bool = Field(
        default=False,
        description="Whether the conversation is archived from the primary active view.",
    )
    pinned: bool = Field(
        default=False,
        description="Whether the conversation is pinned for UI prominence.",
    )
    conversation_state: ConversationState = Field(
        ...,
        description="State of the conversation container itself.",
    )


__all__ = (
    "ConversationMetadata",
    "ConversationState",
)
