"""
Conversation mutation schema models for the Elysia local API bridge.

This module owns the compact request/response schema shapes for conversation
metadata mutations such as:

- Rename
- Move to project
- Pin chat
- Archive

It should stay narrow:
- PATCH /conversations/{conversation_id} request model
- PATCH /conversations/{conversation_id} response-data model

It should not contain:
- route logic
- storage logic
- thread/history transport
- delete transport
- UI logic
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import ElysiaSchemaModel
from .conversation import ConversationMetadata


class ConversationUpdateRequest(ElysiaSchemaModel):
    """
    Request body model for PATCH /conversations/{conversation_id}.

    This model represents the allowed compact metadata mutations for one stored
    conversation container.
    """

    title: str | None = Field(
        default=None,
        description="Optional new human-facing conversation title.",
    )
    project_id: str | None = Field(
        default=None,
        description="Optional project identifier to associate with the conversation.",
    )
    pinned: bool | None = Field(
        default=None,
        description="Optional pinned-state mutation.",
    )
    archived: bool | None = Field(
        default=None,
        description="Optional archived-state mutation.",
    )

    @model_validator(mode="after")
    def validate_at_least_one_field_present(self) -> "ConversationUpdateRequest":
        """
        Require that at least one allowed mutation field is actually provided.
        """
        if (
            self.title is None
            and self.project_id is None
            and self.pinned is None
            and self.archived is None
        ):
            raise ValueError(
                "Conversation update request must include at least one mutation field."
            )

        if self.title is not None and not self.title.strip():
            raise ValueError("Field 'title' must not be empty when provided.")

        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("Field 'project_id' must not be empty when provided.")

        return self


class ConversationUpdateResponseData(ElysiaSchemaModel):
    """
    Response data model for PATCH /conversations/{conversation_id}.

    This lives inside the standard response envelope's data field.
    """

    conversation_id: str = Field(
        ...,
        description="Conversation identifier that was updated.",
    )
    metadata: ConversationMetadata = Field(
        ...,
        description="Updated compact conversation metadata after the mutation.",
    )
    updated_fields: list[str] = Field(
        default_factory=list,
        description="List of metadata fields that were explicitly updated.",
    )


__all__ = (
    "ConversationUpdateRequest",
    "ConversationUpdateResponseData",
)
