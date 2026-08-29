"""
Conversation history/list transport schemas for the Elysia local API bridge.

Scope:
- typed message-history transport for Stage 8 conversation routes
- typed conversation-list transport for Stage 8 conversation routes
- clean separation from compact metadata-only conversation schema

This module should not become:
- the canonical storage layer
- a route module
- a response-envelope builder
- a runtime bridge abstraction
- a dumping ground for unrelated governance/request-trace models
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.conversation import ConversationMetadata


class ConversationMessage(BaseModel):
    """
    One persisted conversation message as exposed through thread/history routes.

    This intentionally mirrors the Stage 8 local conversation store closely so
    the route layer can remain thin and honest.
    """

    message_id: str = Field(..., description="Stable local message identifier.")
    conversation_id: str = Field(..., description="Owning conversation identifier.")
    role: str = Field(..., description="Message role, e.g. user or assistant.")
    content: str = Field(..., description="Rendered message text content.")
    created_at_utc: str = Field(..., description="UTC timestamp for the message record.")

    request_id: Optional[str] = Field(
        default=None,
        description="Associated bridge request identifier when available.",
    )
    invocation_status: Optional[str] = Field(
        default=None,
        description="Invocation status attached to the message when relevant.",
    )
    response_source: Optional[str] = Field(
        default=None,
        description="Origin/source tag for assistant output when available.",
    )

    selected_role: Optional[str] = Field(
        default=None,
        description="Resolved model role used for the response when known.",
    )
    selected_runtime: Optional[str] = Field(
        default=None,
        description="Resolved runtime used for the response when known.",
    )
    selected_model_runtime_tag: Optional[str] = Field(
        default=None,
        description="Resolved model/runtime tag for trust rendering when known.",
    )

    used_fallback: Optional[bool] = Field(
        default=None,
        description="Whether fallback routing was used for this message.",
    )
    fallback_from: Optional[str] = Field(
        default=None,
        description="Original role/runtime path before fallback when known.",
    )
    fallback_to: Optional[str] = Field(
        default=None,
        description="Resolved fallback role/runtime path when known.",
    )

    approval_needed: Optional[bool] = Field(
        default=None,
        description="Whether approval was required for the associated action.",
    )
    approval_state: Optional[str] = Field(
        default=None,
        description="Approval truth-state attached to the message when known.",
    )
    locality_state: Optional[str] = Field(
        default=None,
        description="Locality truth-state attached to the message when known.",
    )
    capability_state: Optional[str] = Field(
        default=None,
        description="Capability truth-state attached to the message when known.",
    )

    blocked: Optional[bool] = Field(
        default=None,
        description="Whether the associated request was blocked.",
    )
    degraded: Optional[bool] = Field(
        default=None,
        description="Whether the associated response or path was degraded.",
    )

    error: Optional[str] = Field(
        default=None,
        description="Primary error string when the message reflects a failure path.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warning messages associated with the exchange.",
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="Non-fatal caveat messages associated with the exchange.",
    )

    model_config = ConfigDict(extra="forbid")


class ConversationListItem(ConversationMetadata):
    """
    One conversation summary row for the conversation list surface.

    This extends the compact metadata model with only the additional thread/list
    signal that Stage 8 currently needs.
    """

    last_message_role: Optional[str] = Field(
        default=None,
        description="Role of the most recent stored message, when known.",
    )

    model_config = ConfigDict(extra="forbid")


class ConversationListResponseData(BaseModel):
    """
    Route-level data payload for GET /conversations.

    The envelope stays elsewhere. This model only describes the data field.
    """

    conversations: list[ConversationListItem] = Field(
        default_factory=list,
        description="Conversation summaries available to the UI.",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Total number of returned conversation summaries.",
    )
    active_conversation_id: Optional[str] = Field(
        default=None,
        description="Conversation to treat as active by default, when applicable.",
    )

    model_config = ConfigDict(extra="forbid")


class ConversationThreadResponseData(BaseModel):
    """
    Route-level data payload for GET /conversations/{conversation_id}.

    The envelope stays elsewhere. This model only describes the data field.
    """

    conversation_id: str = Field(..., description="Requested conversation identifier.")
    metadata: ConversationMetadata = Field(
        ...,
        description="Compact metadata for the requested conversation.",
    )
    messages: list[ConversationMessage] = Field(
        default_factory=list,
        description="Ordered persisted message history for the conversation.",
    )
    last_message_role: Optional[str] = Field(
        default=None,
        description="Role of the most recent stored message, when known.",
    )
    message_count: int = Field(
        default=0,
        ge=0,
        description="Count of messages included for the conversation.",
    )
    storage_version: int = Field(
        default=1,
        ge=1,
        description="Local storage payload version for compatibility awareness.",
    )

    model_config = ConfigDict(extra="forbid")


__all__ = (
    "ConversationListItem",
    "ConversationListResponseData",
    "ConversationMessage",
    "ConversationThreadResponseData",
)
