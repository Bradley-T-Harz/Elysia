from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SearxngWorkerStatus(str, Enum):
    """Status vocabulary for the bounded public web research worker."""

    CONTRACT_ONLY = "contract_only"
    CONFIGURED = "configured"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class SearxngWorkerRequest:
    """Structured request for bounded public SearXNG search."""

    request_id: str
    ticket_id: str
    question: str
    queries: list[str]
    worker_key: str = "searxng_research_worker"
    max_results_per_query: int = 5
    public_query_only: bool = True
    private_context_allowed: bool = False
    private_context_sent: bool = False
    network_access_allowed: bool = True
    page_fetch_allowed: bool = False
    cloud_search_allowed: bool = False
    cloud_model_allowed: bool = False
    approval_token: str | None = None
    exact_approval_validated: bool = False
    safe_search_level: str = "strict"
    outward_boundary_state: str = "external_boundary_planned"
    allowed_source_types: list[str] = field(default_factory=list)
    disallowed_source_types: list[str] = field(default_factory=list)
    requires_recent_sources: bool = False
    requires_primary_sources: bool = False
    requires_peer_reviewed_sources: bool = False
    trace_parent_id: str | None = None


@dataclass
class SearxngSearchResult:
    """One normalized SearXNG search result."""

    title: str
    url: str
    snippet: str
    source_engine: str = ""
    rank: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_engine": self.source_engine,
            "rank": self.rank,
        }


@dataclass
class SearxngWorkerResult:
    """Structured result from the bounded SearXNG worker."""

    status: SearxngWorkerStatus
    worker_key: str = "searxng_research_worker"
    worker_used: bool = False
    searxng_used: bool = False
    request_id: str = ""
    ticket_id: str = ""
    queries_requested: list[str] = field(default_factory=list)
    queries_sent: list[str] = field(default_factory=list)
    query_hashes: list[str] = field(default_factory=list)
    blocked_query_preview: str = ""
    results_considered: list[dict[str, Any]] = field(default_factory=list)
    evidence_packets: list[dict[str, Any]] = field(default_factory=list)
    network_access_used: bool = False
    page_fetch_used: bool = False
    private_context_sent: bool = False
    cloud_search_used: bool = False
    cloud_model_used: bool = False
    approval_required: bool = False
    approval_reason: str = ""
    refusal_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    trace_summary: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-safe payload."""
        return {
            "status": self.status.value,
            "worker_key": self.worker_key,
            "worker_used": self.worker_used,
            "searxng_used": self.searxng_used,
            "request_id": self.request_id,
            "ticket_id": self.ticket_id,
            "queries_requested": list(self.queries_requested),
            "queries_sent": list(self.queries_sent),
            "query_hashes": list(self.query_hashes),
            "blocked_query_preview": self.blocked_query_preview,
            "results_considered": list(self.results_considered),
            "evidence_packets": list(self.evidence_packets),
            "network_access_used": self.network_access_used,
            "page_fetch_used": self.page_fetch_used,
            "private_context_sent": self.private_context_sent,
            "cloud_search_used": self.cloud_search_used,
            "cloud_model_used": self.cloud_model_used,
            "approval_required": self.approval_required,
            "approval_reason": self.approval_reason,
            "refusal_reasons": list(self.refusal_reasons),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "trace_summary": dict(self.trace_summary),
        }
