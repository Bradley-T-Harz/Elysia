"""
Research evidence schema models for the Elysia local API bridge.

Sprint 8A defines evidence-packet truth before any live web research exists.

This module does not imply:
- SearXNG integration
- live web browsing
- page fetching
- HTTP client calls
- network use
- private context leaving the machine
- research worker execution
- automatic claim truth verification
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.ids import new_id

from .common import ElysiaSchemaModel


class EvidenceSourceType(str, Enum):
    """Compact source-type labels for future research evidence."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    REFERENCE = "reference"
    NEWS = "news"
    ACADEMIC = "academic"
    GOVERNMENT = "government"
    COMMERCIAL = "commercial"
    UNKNOWN = "unknown"


class EvidenceRetrievalMethod(str, Enum):
    """
    Retrieval method truth.

    Naming future_search or future_fetch does not make search/fetch live.
    searxng_search is reserved for verified bounded SearXNG worker output.
    public_page_fetch is reserved for explicit approved bounded fetch output.
    """

    NOT_LIVE = "not_live"
    USER_PROVIDED = "user_provided"
    LOCAL_CACHE = "local_cache"
    FUTURE_SEARCH = "future_search"
    FUTURE_FETCH = "future_fetch"
    SEARXNG_SEARCH = "searxng_search"
    PUBLIC_PAGE_FETCH = "public_page_fetch"


class EvidenceConfidence(str, Enum):
    """Modest confidence vocabulary for one evidence packet."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceBoundaryState(str, Enum):
    """Outward-boundary truth for research evidence."""

    LOCAL_CONTRACT_ONLY = "local_contract_only"
    EXTERNAL_BOUNDARY_PLANNED = "external_boundary_planned"
    EXTERNAL_BOUNDARY_CROSSED = "external_boundary_crossed"
    UNKNOWN = "unknown"


class ResearchEvidencePacket(ElysiaSchemaModel):
    """
    One structured evidence packet.

    An evidence packet is not proof by itself. It is a traceable unit of support,
    contradiction, or uncertainty for a claim.
    """

    evidence_id: str | None = Field(
        default_factory=lambda: new_id("evidence"),
        description="Stable time-sortable identifier for this evidence packet.",
    )
    source_url: str = Field(
        ...,
        min_length=1,
        description="Source URL or source locator associated with the packet.",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Human-readable source title.",
    )
    retrieved_at_utc: str = Field(
        ...,
        min_length=1,
        description="UTC timestamp when the source was retrieved, recorded, or supplied.",
    )
    snippet: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Bounded source snippet relevant to the claim.",
    )
    claim: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Claim this packet supports, limits, or contradicts.",
    )
    confidence: EvidenceConfidence = Field(
        default=EvidenceConfidence.UNKNOWN,
        description="Modest confidence judgment for the packet's evidentiary usefulness.",
    )
    contradiction_notes: list[str] = Field(
        default_factory=list,
        description="Known contradictions, caveats, or uncertainty notes.",
    )
    source_type: EvidenceSourceType = Field(
        default=EvidenceSourceType.UNKNOWN,
        description="Compact source-type label.",
    )
    retrieval_method: EvidenceRetrievalMethod = Field(
        default=EvidenceRetrievalMethod.NOT_LIVE,
        description="How this evidence was or will be retrieved.",
    )
    outward_boundary_state: EvidenceBoundaryState = Field(
        default=EvidenceBoundaryState.LOCAL_CONTRACT_ONLY,
        description="Whether an outward boundary was crossed.",
    )
    private_context_sent: bool = Field(
        default=False,
        description="Whether private user/project context was sent outward. Defaults false and must remain false for bounded SearXNG search.",
    )
    network_access_used: bool = Field(
        default=False,
        description="Whether network access was used. Defaults false; true is only valid for verified bounded worker results.",
    )
    page_fetch_used: bool = Field(
        default=False,
        description="Whether a page fetch was used. Defaults false and is not live for Sprint 9 search.",
    )
    live_web_research_used: bool = Field(
        default=False,
        description="Whether live web research was used. Defaults false; true is only valid for verified bounded worker results.",
    )
    source_rank: int | None = Field(
        default=None,
        ge=1,
        description="Optional rank/order from a future search result set.",
    )
    source_date: str | None = Field(
        default=None,
        description="Optional publication/source date when known.",
    )
    publisher: str | None = Field(
        default=None,
        description="Optional publisher or source organization.",
    )
    authors: list[str] = Field(
        default_factory=list,
        description="Optional authors when known.",
    )
    license_or_access_notes: str | None = Field(
        default=None,
        description="Optional notes about access, license, paywall, or availability.",
    )
    quote_span: str | None = Field(
        default=None,
        description="Optional compact locator such as paragraph, page, section, or timestamp.",
    )
    supports_claim: bool | None = Field(
        default=None,
        description="Whether this packet supports the claim. None means not classified yet.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal evidence warnings.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Evidence errors when relevant.",
    )
    contract_note: str = Field(
        default=(
            "Sprint 8A evidence packet contract only. This does not imply live web "
            "research, SearXNG, page fetching, network use, private context leaving "
            "local control, or automatic truth verification."
        ),
        description="Compact boundary note for this evidence packet.",
    )


__all__ = (
    "EvidenceBoundaryState",
    "EvidenceConfidence",
    "EvidenceRetrievalMethod",
    "EvidenceSourceType",
    "ResearchEvidencePacket",
)
