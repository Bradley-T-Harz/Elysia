"""
Request-summary schema models for the Elysia local API bridge.

This module is the Python-side implementation shape for the Stage 2 contract
behind:
- GET /requests/{request_id}/summary

This file should stay narrow:
- request-summary lookup model
- request-summary response-data model
- small request-summary-specific enums/literals

It should not contain:
- route logic
- service logic
- runtime logic
- tracing/log-reading logic
- endpoint-specific business rules
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .approval import ApprovalResolutionStatus
from .common import (
    ApprovalState,
    ElysiaSchemaModel,
    LocalityState,
)
from .tools import ToolLedgerEntry


class RequestSummaryState(str, Enum):
    """
    Canonical request-state values for request-summary response data.

    Meanings:
    - pending: request exists and is awaiting a final outcome
    - approved: request has been approved under current governance
    - denied: request has been denied under current governance
    - cancelled: request has been explicitly cancelled
    - completed: request reached its intended completion state
    - blocked: request remains blocked by policy/boundary/approval posture
    - expired: request is no longer valid for action or resolution
    - unknown: request state has not yet been confirmed
    """

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class RequestSummaryLookup(ElysiaSchemaModel):
    """
    Compact lookup shape for request-summary retrieval.

    This is useful as the service-side validated input shape for the
    /requests/{request_id}/summary path and its small optional query flags.
    """

    request_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the real governed request to summarize.",
    )
    include_notes: bool | None = Field(
        default=None,
        description="Optional future flag for extra compact notes.",
    )
    include_resolution: bool | None = Field(
        default=None,
        description="Optional future flag for extra compact resolution detail.",
    )


class RequestFileSummary(ElysiaSchemaModel):
    """
    Compact UI-safe attached-file truth for request summaries.

    This deliberately excludes absolute local paths, raw extracted text, hashes,
    and file contents.
    """

    file_id: str | None = Field(default=None)
    file_name: str | None = Field(default=None)
    file_kind: str | None = Field(default=None)
    status: str | None = Field(default=None)
    summary: str | None = Field(default=None)
    parser_used: str | None = Field(default=None)
    chunks_created_count: int = Field(default=0, ge=0)
    chunks_used_count: int = Field(default=0, ge=0)
    memory_promotion_allowed: bool = Field(default=False)
    outward_sharing_allowed: bool = Field(default=False)
    trust_zone: str | None = Field(default=None)
    blocked_reason: str | None = Field(default=None)


class RequestArtifactSummary(ElysiaSchemaModel):
    """
    Compact UI-safe artifact truth for request summaries.

    This deliberately excludes raw payloads, artifact paths, source paths, and
    inline SVG text.
    """

    artifact_id: str | None = Field(default=None)
    kind: str | None = Field(default=None)
    title: str | None = Field(default=None)
    summary: str | None = Field(default=None)
    created_at_utc: str | None = Field(default=None)
    locality: str | None = Field(default=None)
    memory_posture: str | None = Field(default=None)
    producer_tool_kind: str | None = Field(default=None)
    producer_operation: str | None = Field(default=None)
    source_file_id: str | None = Field(default=None)
    source_file_name: str | None = Field(default=None)
    source_file_kind: str | None = Field(default=None)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class RequestSummaryData(ElysiaSchemaModel):
    """
    Response data model for GET /requests/{request_id}/summary.

    This is the endpoint-specific payload that lives inside the standard
    response envelope's data field.
    """

    request_id: str = Field(
        ...,
        description="Identifier of the governed request being summarized.",
    )
    request_state: RequestSummaryState = Field(
        ...,
        description="Current state of the governed request itself.",
    )
    request_type: str | None = Field(
        default=None,
        description="Compact type/category label for the governed request.",
    )
    summary_text: str = Field(
        ...,
        description="Compact human-readable summary of what the request was about and what its current state means.",
    )
    created_at_utc: str | None = Field(
        default=None,
        description="UTC timestamp for when the request record was created.",
    )
    updated_at_utc: str | None = Field(
        default=None,
        description="UTC timestamp for the most recent meaningful update to the request record.",
    )
    approval_required: bool = Field(
        ...,
        description="Formal governance truth about whether this request type is approval-bound.",
    )
    approval_state: ApprovalState = Field(
        ...,
        description="Broad approval posture currently associated with the request.",
    )
    locality: LocalityState = Field(
        ...,
        description="Whether the request path is local, crossed a boundary, or is currently unknown.",
    )
    selected_role: str | None = Field(
        default=None,
        description="Governed role expression associated with the request when known.",
    )
    selected_runtime: str | None = Field(
        default=None,
        description="Runtime associated with the request when known.",
    )
    selected_model_runtime_tag: str | None = Field(
        default=None,
        description="Concrete model/runtime tag associated with the request when known.",
    )
    used_fallback: bool = Field(
        default=False,
        description="Whether an allowed fallback path was used for this request.",
    )
    mode_profile_key: str | None = Field(default=None)
    mode_profile_label: str | None = Field(default=None)
    mode_profile_used: bool = Field(default=False)
    mode_profile_effects: list[str] = Field(default_factory=list)
    mode_profile_warnings: list[str] = Field(default_factory=list)
    authority_granted_by_mode: bool = Field(default=False)
    execution_tool_kind: str | None = Field(
        default=None,
        description="Compact execution tool kind used by the request when known, such as math_executor.",
    )
    execution_status: str | None = Field(
        default=None,
        description="Compact execution status when bounded execution was used or attempted.",
    )
    execution_operation: str | None = Field(
        default=None,
        description="Compact operation name for bounded execution when known.",
    )
    execution_summary: str | None = Field(
        default=None,
        description="UI-safe bounded execution summary. This must not contain raw logs or unsafe internals.",
    )
    research_ticket_id: str | None = Field(default=None)
    research_status: str | None = Field(default=None)
    research_worker_name: str | None = Field(default=None)
    research_query_count: int | None = Field(default=None, ge=0)
    evidence_packet_count: int | None = Field(default=None, ge=0)
    outward_boundary_state: str | None = Field(default=None)
    private_context_sent: bool | None = Field(default=None)
    network_access_used: bool | None = Field(default=None)
    page_fetch_used: bool | None = Field(default=None)
    cloud_search_used: bool | None = Field(default=None)
    cloud_model_used: bool | None = Field(default=None)
    files_attached_count: int = Field(default=0, ge=0)
    files_attached: list[RequestFileSummary] = Field(default_factory=list)
    files_used_count: int = Field(default=0, ge=0)
    file_chunks_used_count: int = Field(default=0, ge=0)
    file_parsers_used: list[str] = Field(default_factory=list)
    file_memory_promotion: bool = Field(default=False)
    file_outward_sharing: bool = Field(default=False)
    tools_available_count: int = Field(default=0, ge=0)
    tools_used_count: int = Field(default=0, ge=0)
    tools_available: list[ToolLedgerEntry] = Field(default_factory=list)
    tools_used: list[ToolLedgerEntry] = Field(default_factory=list)
    artifact_count: int = Field(default=0, ge=0)
    artifacts: list[RequestArtifactSummary] = Field(default_factory=list)
    repo_context_status: str | None = Field(default=None)
    repo_context_file_count: int = Field(default=0, ge=0)
    repo_context_files: list[str] = Field(default_factory=list)
    patch_plan_status: str | None = Field(default=None)
    patch_plan_file_count: int = Field(default=0, ge=0)
    patch_plan_files: list[str] = Field(default_factory=list)
    patch_id: str | None = Field(default=None)
    patch_hash: str | None = Field(default=None)
    patch_diff_preview: str | None = Field(default=None)
    patch_preview_truncated: bool = Field(default=False)
    rollback_note: str | None = Field(default=None)
    command_key: str | None = Field(default=None)
    command_argv: list[str] = Field(default_factory=list)
    command_exit_code: int | None = Field(default=None)
    command_duration_ms: int = Field(default=0, ge=0)
    command_output_preview: str | None = Field(default=None)
    command_output_truncated: bool = Field(default=False)
    mutated_files: bool = Field(default=False)
    shell_used: bool = Field(default=False)
    git_mutation_used: bool = Field(default=False)
    external_worker_used: bool = Field(default=False)
    resolution_status: ApprovalResolutionStatus | None = Field(
        default=None,
        description="Resolution outcome associated with the request when a formal approval resolution exists.",
    )
    can_proceed: bool = Field(
        ...,
        description="Whether current governance now allows the request to move forward.",
    )
    related_conversation_id: str | None = Field(
        default=None,
        description="Related conversation identifier when the request is associated with a conversation.",
    )
    related_project_id: str | None = Field(
        default=None,
        description="Related project identifier when the request is associated with a project.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Compact request-summary notes safe for UI display.",
    )


__all__ = (
    "RequestArtifactSummary",
    "RequestFileSummary",
    "RequestSummaryData",
    "RequestSummaryLookup",
    "RequestSummaryState",
)
