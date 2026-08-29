"""
Chat request/response schema models for the Elysia local API bridge.

This module is the Python-side implementation shape for the Stage 2 /chat/send
contract. It should keep chat request/response data aligned with the frozen
schema so the bridge does not drift into loose dictionaries or ad hoc fields.

This file should stay narrow:
- POST /chat/send request model
- POST /chat/send response-data model
- small chat-specific enums/literals

It should not contain:
- route logic
- runtime logic
- governance logic
- capability logic
- service/business rules
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from .artifacts import ArtifactSummary
from .common import ElysiaSchemaModel


class ChatResponseSource(str, Enum):
    """
    Canonical chat response-source values.

    Meanings:
    - live_invoker: response text came from the governed live local invoker path
    - scaffold_fallback: response text came from scaffold fallback composition
    """

    LIVE_INVOKER = "live_invoker"
    SCAFFOLD_FALLBACK = "scaffold_fallback"


class ChatInvocationStatus(str, Enum):
    """
    Canonical chat invocation-status values.

    These mirror the governed runtime/invoker truth surface without letting
    the route or schema layer invent new runtime states.
    """

    OK = "ok"
    BLOCKED = "blocked"
    ERROR = "error"
    NOT_INVOKED = "not_invoked"
    UNKNOWN = "unknown"


class ChatSendRequest(ElysiaSchemaModel):
    """
    Request body model for POST /chat/send.

    This model mirrors the Stage 2 schema while remaining modest about which
    fields are authoritative. requested_mode and requested_role are advisory
    request-shape fields only; governed routing remains authoritative.
    """

    message: str = Field(
        ...,
        min_length=1,
        description="Required user message to send into the governed body path.",
    )
    request_id: str | None = Field(
        default=None,
        description=(
            "Optional client-supplied request identifier for end-to-end continuity "
            "and live request-trace polling."
        ),
    )
    conversation_id: str | None = Field(
        default=None,
        description="Optional conversation container identifier.",
    )
    project_id: str | None = Field(
        default=None,
        description="Optional project linkage identifier.",
    )
    requested_mode: str | None = Field(
        default=None,
        description=(
            "Optional requested mode posture. Advisory only; governed runtime "
            "selection remains authoritative."
        ),
    )
    mode_requested: str | None = Field(
        default=None,
        description=(
            "Optional alias for requested_mode. Advisory only; governed runtime "
            "selection remains authoritative."
        ),
    )
    requested_role: str | None = Field(
        default=None,
        description=(
            "Optional requested role posture. Advisory only; governed routing "
            "remains authoritative."
        ),
    )
    requested_gear: str | None = Field(
        default=None,
        pattern=r"^(automatic|reflex|quick|standard|deep|deliberative|research_engineering)$",
        description="Optional per-request effort override; it never grants authority.",
    )
    request_context: dict[str, Any] | None = Field(
        default=None,
        description="Optional compact request-context mapping.",
    )
    ui_surface: str | None = Field(
        default=None,
        description="Optional UI surface metadata such as conversations_room or quick_invoke.",
    )


class ChatSendResponseData(ElysiaSchemaModel):
    """
    Response data model for POST /chat/send.

    This is the endpoint-specific payload that will live inside the standard
    response envelope's data field.
    """

    user_message: str = Field(
        ...,
        description="The user message that was submitted into the governed body path.",
    )
    response_text: str = Field(
        ...,
        description="User-facing response text produced by the governed body path.",
    )
    response_source: ChatResponseSource = Field(
        ...,
        description="Whether the returned response text came from live invoker output or scaffold fallback.",
    )
    invocation_status: ChatInvocationStatus = Field(
        ...,
        description="Governed invocation outcome associated with this chat request.",
    )
    selected_model_role: str | None = Field(
        default=None,
        description="Governed role expression selected for this chat request when known.",
    )
    selected_runtime: str | None = Field(
        default=None,
        description="Governed runtime selected for this chat request when known.",
    )
    selected_model_runtime_tag: str | None = Field(
        default=None,
        description="Concrete model/runtime tag selected for this chat request when known.",
    )
    used_fallback: bool = Field(
        default=False,
        description="Whether an allowed fallback path was used for this chat request.",
    )
    fallback_from: str | None = Field(
        default=None,
        description="Preferred runtime tag that could not be used when fallback occurred.",
    )
    fallback_to: str | None = Field(
        default=None,
        description="Runtime tag actually used after fallback when fallback occurred.",
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="Compact user-visible caveats associated with this chat response.",
    )
    approval_needed: bool = Field(
        default=False,
        description="Broad trust-surface indicator for whether continuing this path is approval-bound.",
    )
    approval_token: str | None = Field(
        default=None,
        description="Optional compact approval token/reference when approval tracking is surfaced.",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Conversation identifier associated with this chat request when known.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project identifier associated with this chat request when known.",
    )
    attached_context_summary: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact truth summary for attached local context used in this response. "
            "Attached files remain context only and are not memory."
        ),
    )
    mode_profile: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact mode-profile posture truth. Modes shape response posture and "
            "tool preference weighting; they do not grant authority."
        ),
    )
    profile_context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact truth about the sealed account visible-profile projection. "
            "This may include only the explicit Elysia-visible account fields."
        ),
    )
    continuity: dict[str, Any] | None = Field(
        default=None,
        description="Sanitized conversation/project continuity restored for this response.",
    )
    workspace: dict[str, Any] | None = Field(
        default=None,
        description="Content-free Global Working Workspace assembly truth.",
    )
    context_receipt: dict[str, Any] | None = Field(
        default=None,
        description="Sanitized retrieval/admission/exclusion and token-budget receipt.",
    )
    research: dict[str, Any] | None = Field(
        default=None,
        description="Sanitized governed ResearchPort activity and durable evidence truth.",
    )
    governor: dict[str, Any] | None = Field(
        default=None,
        description="Content-free deterministic cognition decision receipt.",
    )
    compute: dict[str, Any] | None = Field(
        default=None,
        description="Sanitized compute/device/lease decision truth.",
    )
    operational_self_model: dict[str, Any] | None = Field(
        default=None,
        description="Bounded objective capability/limit/recovery truth without hidden reasoning.",
    )
    data_execution: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact truth payload for bounded local data execution when a request "
            "uses an attached CSV/XLSX data file."
        ),
    )
    math_execution: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact truth payload for bounded local math execution when a request "
            "uses the local math checker."
        ),
    )
    repo_context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact truth payload for read-only approved repository context "
            "gathering in Coder mode."
        ),
    )
    code_patch_plan: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact truth payload for proposal-only code patch planning in "
            "Coder mode. This does not mean a patch was applied or files changed."
        ),
    )
    aider_worker: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact truth payload for Aider worker skeleton dry-run validation. "
            "This does not mean Aider was invoked, a worker executed, or files changed."
        ),
    )
    artifacts: list[ArtifactSummary] = Field(
        default_factory=list,
        description=(
            "Compact UI-safe summaries for local artifacts generated from this "
            "chat response. Sprint 5B supports saved local data_summary artifacts."
        ),
    )


__all__ = (
    "ChatInvocationStatus",
    "ChatResponseSource",
    "ChatSendRequest",
    "ChatSendResponseData",
)
