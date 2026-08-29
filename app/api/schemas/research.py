"""
Research ticket schema models for the Elysia local API bridge.

Sprint 8B defines planned research-ticket truth before any live web research
worker exists.

A research ticket is not a search. It is a structured plan or record for future
evidence-gathering work.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import ElysiaSchemaModel
from .evidence import (
    EvidenceBoundaryState,
    EvidenceSourceType,
    ResearchEvidencePacket,
)


class ResearchTicketStatus(str, Enum):
    """Canonical research-ticket states."""

    PLANNED = "planned"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchScope(str, Enum):
    """Compact research scope labels."""

    GENERAL = "general"
    ACADEMIC = "academic"
    TECHNICAL = "technical"
    LEGAL_POLICY = "legal_policy"
    ENVIRONMENTAL = "environmental"
    MEDICAL_HEALTH = "medical_health"
    FINANCIAL = "financial"
    UNKNOWN = "unknown"


class ResearchTicket(ElysiaSchemaModel):
    """
    One planned or recorded research ticket.

    Sprint 8 tickets default to planned/no-web/no-private-context.
    """

    ticket_id: str = Field(
        ...,
        min_length=1,
        description="Stable research-ticket identifier.",
    )
    question: str = Field(
        ...,
        min_length=1,
        description="Research question or claim being investigated.",
    )
    status: ResearchTicketStatus = Field(
        default=ResearchTicketStatus.PLANNED,
        description="Current ticket status.",
    )
    research_scope: ResearchScope = Field(
        default=ResearchScope.UNKNOWN,
        description="Compact scope label for the research request.",
    )
    allowed_source_types: list[EvidenceSourceType] = Field(
        default_factory=list,
        description="Source types allowed or preferred for this ticket.",
    )
    disallowed_source_types: list[EvidenceSourceType] = Field(
        default_factory=list,
        description="Source types disallowed for this ticket.",
    )
    requires_peer_reviewed_sources: bool = Field(
        default=False,
        description="Whether peer-reviewed sources are required.",
    )
    requires_primary_sources: bool = Field(
        default=False,
        description="Whether primary sources are required.",
    )
    requires_recent_sources: bool = Field(
        default=False,
        description="Whether recency matters for this research question.",
    )
    evidence_packets: list[ResearchEvidencePacket] = Field(
        default_factory=list,
        description="Evidence packets attached to this ticket.",
    )
    created_at_utc: str | None = Field(
        default=None,
        description="UTC creation timestamp when known.",
    )
    completed_at_utc: str | None = Field(
        default=None,
        description="UTC completion timestamp when known.",
    )
    requires_live_research: bool = Field(
        default=False,
        description="Whether answering the ticket would require future live research.",
    )
    live_research_enabled: bool = Field(
        default=False,
        description="Whether live research is enabled. Sprint 8 must keep this false.",
    )
    query_execution_allowed: bool = Field(
        default=False,
        description="Whether query execution is allowed. Sprint 8 must keep this false.",
    )
    retrieval_allowed: bool = Field(
        default=False,
        description="Whether source retrieval/fetching is allowed. Sprint 8 must keep this false.",
    )
    private_context_allowed: bool = Field(
        default=False,
        description="Whether private context may be sent outward. Sprint 8 must keep this false.",
    )
    private_context_sent: bool = Field(
        default=False,
        description="Whether private context was sent outward. Sprint 8 must keep this false.",
    )
    outward_boundary_state: EvidenceBoundaryState = Field(
        default=EvidenceBoundaryState.LOCAL_CONTRACT_ONLY,
        description="Outward-boundary truth for this ticket.",
    )
    network_access_used: bool = Field(
        default=False,
        description="Whether network access was used. Sprint 8 must keep this false.",
    )
    page_fetch_used: bool = Field(
        default=False,
        description="Whether page fetching was used. Sprint 8 must keep this false.",
    )
    page_fetch_allowed: bool = Field(
        default=False,
        description="Whether page fetching is allowed. Sprint 9 search keeps this false.",
    )
    live_web_research_used: bool = Field(
        default=False,
        description="Whether live web research was used. Sprint 8 must keep this false.",
    )
    worker_key: str | None = Field(
        default=None,
        description="Research worker key when a bounded worker path was used.",
    )
    worker_used: bool = Field(
        default=False,
        description="Whether a bounded research worker was used.",
    )
    queries_requested: list[str] = Field(
        default_factory=list,
        description="Sanitized or compact query text requested for bounded research.",
    )
    queries_sent: list[str] = Field(
        default_factory=list,
        description="Sanitized public query text actually sent outward.",
    )
    query_hashes: list[str] = Field(
        default_factory=list,
        description="SHA-256 hashes of query text sent or considered for traceability.",
    )
    blocked_query_preview: str | None = Field(
        default=None,
        description="Redacted preview of a blocked query. Must not contain raw private text.",
    )
    query_count: int = Field(
        default=0,
        ge=0,
        description="Count of queries sent outward when known.",
    )
    result_count: int = Field(
        default=0,
        ge=0,
        description="Count of search results considered when known.",
    )
    evidence_packet_count: int = Field(
        default=0,
        ge=0,
        description="Count of evidence packets attached when known.",
    )
    cloud_search_used: bool = Field(
        default=False,
        description="Whether direct cloud search was used. Sprint 9 SearXNG path keeps this false.",
    )
    cloud_model_used: bool = Field(
        default=False,
        description="Whether a cloud model was used for research. Sprint 9 keeps this false.",
    )
    approval_required: bool = Field(
        default=False,
        description="Whether approval is required before a future outward action.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Compact UI-safe ticket notes.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal ticket warnings.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Ticket errors when relevant.",
    )
    contract_note: str = Field(
        default=(
            "Sprint 8B research ticket contract only. This is not live web "
            "research, SearXNG, page fetching, network use, private context "
            "leaving local control, or a research worker."
        ),
        description="Compact boundary note for this research ticket.",
    )


class ResearchSearchRequest(ElysiaSchemaModel):
    """API request shape for bounded public SearXNG search."""

    request_id: str | None = Field(
        default=None,
        description="Optional existing request trace id.",
    )
    ticket_id: str | None = Field(
        default=None,
        description="Optional research ticket id.",
    )
    project_id: str | None = None
    conversation_id: str | None = None
    reasoning_gear: str = "standard"
    research_session_id: str | None = None
    keep_session_open: bool = False
    question: str = Field(
        ...,
        min_length=1,
        description="Public research question.",
    )
    queries: list[str] = Field(
        ...,
        min_length=1,
        description="Public query terms proposed for search.",
    )
    max_results_per_query: int = Field(
        default=5,
        ge=1,
        le=5,
        description="Bounded result count per query.",
    )
    requires_recent_sources: bool = False
    requires_primary_sources: bool = False
    requires_peer_reviewed_sources: bool = False
    allowed_source_types: list[EvidenceSourceType] = Field(default_factory=list)
    disallowed_source_types: list[EvidenceSourceType] = Field(default_factory=list)
    approval_id: str | None = None
    approval_token: str | None = None


class ResearchFetchRequest(ElysiaSchemaModel):
    """API request shape for one explicit bounded public page fetch."""

    request_id: str | None = None
    ticket_id: str | None = None
    research_session_id: str | None = None
    project_id: str | None = None
    conversation_id: str | None = None
    question: str = Field(
        default="Fetch approved public page for evidence support.",
        min_length=1,
        description="Research question or reason for the approved fetch.",
    )
    url: str = Field(..., min_length=1, description="Approved public HTTP(S) URL.")
    approval_id: str | None = None
    approval_token: str | None = None
    approval_reference: str | None = None
    approved_by_user: bool = False


__all__ = (
    "ResearchFetchRequest",
    "ResearchScope",
    "ResearchSearchRequest",
    "ResearchTicket",
    "ResearchTicketStatus",
)
