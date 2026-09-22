"""
Bounded public research service for the local API bridge.

This service is the single governed WebResearchPort.  It delegates loopback
search to the established SearXNG worker and public-page retrieval to the
bounded fetch worker, persists quarantined evidence, and integrates with the
existing runtime.  It never reads private memory/files or calls a model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from sandbox.cancellation import cancellation_requested

from app.ids import new_id
from app.cognition.evidence_repository import EvidenceRepository

from app.api.request_trace_service import (
    mark_request_trace_blocked,
    mark_request_trace_completed,
    mark_request_trace_degraded,
    mark_request_trace_error,
    start_request_trace,
    update_request_trace_research_snapshot,
)
from app.api.user_control_service import current_user_controls, internet_master_enabled
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.evidence import EvidenceBoundaryState
from app.api.schemas.research import (
    ResearchFetchRequest,
    ResearchScope,
    ResearchSearchRequest,
    ResearchTicket,
    ResearchTicketStatus,
)
from core.evidence_verifier import verify_research_ticket_payload
from sandbox.searxng_worker.contract import (
    SearxngWorkerRequest,
    SearxngWorkerResult,
    SearxngWorkerStatus,
)
from sandbox.searxng_worker.worker import run_searxng_worker
from sandbox.searxng_worker.config import load_searxng_worker_config
from sandbox.searxng_worker.query_guard import QueryGuardResult, guard_public_queries
from sandbox.fetch_worker.contract import (
    FetchWorkerRequest,
    FetchWorkerResult,
    FetchWorkerStatus,
)
from sandbox.fetch_worker.worker import run_fetch_worker


API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"


@dataclass(frozen=True)
class ResearchBudget:
    max_queries: int
    max_results_per_query: int
    max_fetches: int
    max_domains: int
    min_authority_classes: int
    max_elapsed_seconds: int
    max_bytes: int

    def to_payload(self) -> dict[str, int]:
        return {
            "max_queries": self.max_queries,
            "max_results_per_query": self.max_results_per_query,
            "max_fetches": self.max_fetches,
            "max_domains": self.max_domains,
            "min_authority_classes": self.min_authority_classes,
            "max_elapsed_seconds": self.max_elapsed_seconds,
            "max_bytes": self.max_bytes,
        }


def _combined_cancel_check(
    cancel_check: Callable[[], bool] | None,
) -> Callable[[], bool]:
    """
    Combine per-request cancellation with the system emergency STOP event.

    Failure to inspect emergency state fails closed for outward research.
    """
    def check() -> bool:
        if cancellation_requested(cancel_check):
            return True

        try:
            from app.cognition.emergency_control import emergency_stop_event

            return emergency_stop_event().is_set()
        except Exception:
            return True

    return check


def research_budget_for(
    *, reasoning_gear: str, autonomy_level: int, initiative: str
) -> ResearchBudget:
    gear = str(reasoning_gear or "standard")
    depth = {
        "reflex": 0,
        "quick": 0,
        "standard": 1,
        "deep": 2,
        "deliberative": 2,
        "research_engineering": 3,
    }.get(gear, 1)
    if initiative == "manual":
        depth = min(depth, 1)
    elif initiative == "proactive" and autonomy_level >= 3:
        depth = min(3, depth + 1)
    return ResearchBudget(
        max_queries=max(1, min(3, 1 + depth)),
        max_results_per_query=5,
        max_fetches=max(1, min(4, depth + max(0, autonomy_level - 2))),
        max_domains=max(2, min(6, 2 + depth)),
        min_authority_classes=2 if depth >= 2 else 1,
        max_elapsed_seconds=20 + depth * 15,
        max_bytes=120000 * max(1, min(4, depth + 1)),
    )


_PUBLIC_QUERY_REDACTIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email_address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("phone_number", re.compile(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}")),
    ("home_address", re.compile(r"\b\d{2,6}\s+[A-Za-z0-9 .'-]+\s+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd)\b", re.IGNORECASE)),
    ("local_path", re.compile(r"(?:/home/[^\s]+|~/[^\s]+|[A-Za-z]:\\\\[^\s]+)")),
    ("account_identifier", re.compile(r"\b(?:my\s+)?(?:account|profile|customer|patient|member)\s+(?:id|number|username)\s*(?:is|:)?\s*[A-Za-z0-9._-]+", re.IGNORECASE)),
    ("declared_name", re.compile(r"\b(?:my name is|I am called)\s+[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,2}", re.IGNORECASE)),
)


def prepare_minimum_necessary_public_queries(
    question: str, *, limit: int
) -> tuple[list[str], dict[str, Any]]:
    """Derive bounded public-only queries from the current user question.

    Local project/profile/memory/file material is never accepted as an input to
    this function. The query guard still blocks secrets, paths, sealed content,
    and exactly gates sensitive categories before any outbound construction.
    """
    # An explicit request to export private material is a separate privacy
    # decision. Never turn it into automatic public permission by redaction.
    egress_request = re.sub(
        r"\b(?:do not|don't|never|must not)\s+(?:send|upload|publish|post|export|transmit|copy)\b[^.;!?\n]*",
        "", str(question or ""), flags=re.IGNORECASE,
    )
    if re.search(
        r"\b(?:send|upload|publish|post|export|transmit|copy)\b[^.;!?\n]*\b(?:private|vault|sealed|local file|local log|memory|attachment)\b"
        r"[^.;!?\n]*\b(?:(?:to|via|on|into)\s+[^.;!?\n]*\b(?:public|web|internet|online|searxng|external)|externally)\b"
        r"|\b(?:search the web|search the public web|research online)\b[^.;!?\n]*\busing\s+(?:my|our|the)\s+(?:private|vault|sealed)\b",
        egress_request, flags=re.IGNORECASE,
    ):
        return [], {"version": "minimum-necessary-query-v1",
                    "local_context_included": False, "removed_categories": [],
                    "outbound_query_count": 0, "blocked_reason": "explicit_private_egress"}
    compact = " ".join(str(question or "").split())
    compact = re.sub(
        r"^(please\s+)?(research|look up|search(?: the web)? for|investigate)\s+",
        "",
        compact,
        flags=re.IGNORECASE,
    )
    removed: list[str] = []
    for category, pattern in _PUBLIC_QUERY_REDACTIONS:
        compact, count = pattern.subn(" ", compact)
        if count:
            removed.append(category)
    # Phrases that explicitly point at local authority are useful to Elysia's
    # local understanding but not necessary search-engine payload.  Remove the
    # phrase rather than inserting a reversible placeholder.
    compact, local_count = re.subn(
        r"\b(?:from|using|based on|according to)\s+(?:my|our)\s+(?:private\s+)?(?:profile|memory|conversation|project file|local file|notes|vault)\b[^.;!?]{0,160}",
        " ",
        compact,
        flags=re.IGNORECASE,
    )
    if local_count:
        removed.append("local_context_clause")
    # Discard explicitly local/private clauses as whole units. Their arbitrary
    # contents cannot be made public merely by deleting the privacy label.
    compact, private_count = re.subn(
        r"[^.;!?]*\b(?:private|vault|local files?|local logs?)\b[^.;!?]*(?:[.;!?]|$)",
        " ", compact, flags=re.IGNORECASE,
    )
    if private_count:
        removed.append("private_context_clause")
    compact = " ".join(compact.split())
    compact = compact[:240].strip(" .")
    if not compact:
        return [], {
            "version": "minimum-necessary-query-v1",
            "local_context_included": False,
            "removed_categories": sorted(set(removed)),
            "outbound_query_count": 0,
        }
    candidates = [compact]
    if limit >= 2:
        candidates.append(f"{compact} primary sources")
    if limit >= 3:
        candidates.append(f"{compact} independent analysis evidence")
    queries = candidates[: max(1, min(limit, 3))]
    return queries, {
        "version": "minimum-necessary-query-v1",
        "local_context_included": False,
        "removed_categories": sorted(set(removed)),
        "outbound_query_count": len(queries),
    }


def minimum_necessary_public_queries(question: str, *, limit: int) -> list[str]:
    """Compatibility wrapper returning only prepared outbound query text."""
    queries, _ = prepare_minimum_necessary_public_queries(question, limit=limit)
    return queries


def _high_stakes_question(question: str) -> bool:
    lowered = str(question or "").casefold()
    return any(
        marker in lowered
        for marker in (
            "medical", "diagnosis", "treatment", "legal", "lawsuit", "financial",
            "investment", "identity", "security", "vulnerability", "credential",
        )
    )


def source_authority_class(url: str) -> str:
    """Deterministic public-source class used for diversity, never truth rank."""
    host = str(urlparse(str(url or "")).hostname or "").casefold()
    if not host:
        return "unknown"
    if host.endswith(".gov") or ".gov." in host:
        return "government"
    if host.endswith(".edu") or ".edu." in host or host.endswith(".ac.uk"):
        return "academic"
    if any(marker in host for marker in ("docs.", "developer.", "standards.", "w3.org", "ietf.org")):
        return "primary_documentation"
    if any(marker in host for marker in ("reuters.", "apnews.", "bbc.", "npr.", "news.")):
        return "news"
    if any(marker in host for marker in ("reddit.", "stackoverflow.", "forum.", "community.")):
        return "community"
    if host.endswith(".org"):
        return "organization"
    return "general_public"


def _new_request_id(prefix: str = "req") -> str:
    return new_id(prefix)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ticket_id() -> str:
    return new_id("research_ticket")


def _status_to_ticket_status(status: SearxngWorkerStatus) -> ResearchTicketStatus:
    if status in {SearxngWorkerStatus.COMPLETED, SearxngWorkerStatus.DEGRADED}:
        return ResearchTicketStatus.COMPLETED
    if status in {SearxngWorkerStatus.BLOCKED, SearxngWorkerStatus.APPROVAL_REQUIRED}:
        return ResearchTicketStatus.BLOCKED
    return ResearchTicketStatus.FAILED


def _status_to_envelope_status(status: SearxngWorkerStatus, verified: bool) -> EnvelopeStatus:
    if status == SearxngWorkerStatus.COMPLETED and verified:
        return EnvelopeStatus.OK
    if status == SearxngWorkerStatus.DEGRADED or (status == SearxngWorkerStatus.COMPLETED and not verified):
        return EnvelopeStatus.DEGRADED
    if status in {SearxngWorkerStatus.BLOCKED, SearxngWorkerStatus.APPROVAL_REQUIRED}:
        return EnvelopeStatus.BLOCKED
    if status == SearxngWorkerStatus.UNAVAILABLE:
        return EnvelopeStatus.UNAVAILABLE
    return EnvelopeStatus.ERROR


def _status_to_capability_state(status: SearxngWorkerStatus) -> CapabilityState:
    if status == SearxngWorkerStatus.COMPLETED:
        return CapabilityState.LIVE
    if status == SearxngWorkerStatus.DEGRADED:
        return CapabilityState.DEGRADED
    if status == SearxngWorkerStatus.UNAVAILABLE:
        return CapabilityState.UNAVAILABLE
    if status in {SearxngWorkerStatus.BLOCKED, SearxngWorkerStatus.APPROVAL_REQUIRED}:
        return CapabilityState.LIVE
    return CapabilityState.DEGRADED


def _status_to_approval_state(worker_result: SearxngWorkerResult) -> ApprovalState:
    if worker_result.approval_required:
        return ApprovalState.NEEDED
    if worker_result.status == SearxngWorkerStatus.BLOCKED:
        return ApprovalState.DENIED
    return ApprovalState.NOT_NEEDED


def _worker_query_outcomes(
    worker_result: SearxngWorkerResult,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []

    for item in list(
        getattr(worker_result, "query_outcomes", [])
        or []
    ):
        if not isinstance(item, dict):
            continue

        query = " ".join(
            str(item.get("query") or "").split()
        )

        state = str(
            item.get("state") or ""
        ).casefold()

        if (
            not query
            or state
            not in {"completed", "unavailable", "failed"}
        ):
            continue

        outcomes.append(
            {
                "query": query,
                "state": state,
                "outward_boundary_state": str(
                    item.get("outward_boundary_state")
                    or "unknown"
                ),
                "network_access_used": bool(
                    item.get("network_access_used")
                ),
                "searxng_used": bool(
                    item.get("searxng_used")
                ),
            }
        )

    return outcomes


def _worker_boundary_state(
    worker_result: SearxngWorkerResult,
) -> EvidenceBoundaryState:
    outcomes = _worker_query_outcomes(worker_result)

    boundary_states = {
        str(
            item.get("outward_boundary_state")
            or ""
        )
        for item in outcomes
    }

    if (
        EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED.value
        in boundary_states
    ):
        return (
            EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED
        )

    if (
        EvidenceBoundaryState.UNKNOWN.value
        in boundary_states
    ):
        return EvidenceBoundaryState.UNKNOWN

    # Compatibility for injected/legacy worker results that
    # predate query_outcomes.
    if worker_result.queries_sent:
        if worker_result.status in {
            SearxngWorkerStatus.COMPLETED,
            SearxngWorkerStatus.DEGRADED,
        }:
            return (
                EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED
            )

        return EvidenceBoundaryState.UNKNOWN

    return EvidenceBoundaryState.EXTERNAL_BOUNDARY_PLANNED


def _worker_locality_state(
    worker_result: SearxngWorkerResult,
) -> LocalityState:
    boundary = _worker_boundary_state(worker_result)

    if (
        boundary
        == EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED
    ):
        return LocalityState.CROSSED_BOUNDARY

    if boundary == EvidenceBoundaryState.UNKNOWN:
        return LocalityState.UNKNOWN

    return LocalityState.LOCAL


def _worker_completed_queries(
    worker_result: SearxngWorkerResult,
) -> list[str]:
    outcomes = _worker_query_outcomes(worker_result)

    if outcomes:
        return [
            str(item["query"])
            for item in outcomes
            if item.get("state") == "completed"
        ]

    # Compatibility for existing injected test workers.
    if worker_result.status in {
        SearxngWorkerStatus.COMPLETED,
        SearxngWorkerStatus.DEGRADED,
    }:
        return list(worker_result.queries_sent)

    return []


def build_research_ticket_from_request(
    request_model: ResearchSearchRequest,
    worker_result: SearxngWorkerResult,
) -> ResearchTicket:
    """Build a ResearchTicket from one worker result."""
    evidence_packets = list(worker_result.evidence_packets)
    ticket_status = _status_to_ticket_status(worker_result.status)
    boundary_state = _worker_boundary_state(worker_result)
    completed_queries = _worker_completed_queries(worker_result)

    return ResearchTicket(
        ticket_id=request_model.ticket_id or worker_result.ticket_id or _ticket_id(),
        question=request_model.question,
        status=ticket_status,
        research_scope=ResearchScope.UNKNOWN,
        allowed_source_types=request_model.allowed_source_types,
        disallowed_source_types=request_model.disallowed_source_types,
        requires_peer_reviewed_sources=request_model.requires_peer_reviewed_sources,
        requires_primary_sources=request_model.requires_primary_sources,
        requires_recent_sources=request_model.requires_recent_sources,
        evidence_packets=evidence_packets,
        created_at_utc=_utc_now_iso(),
        completed_at_utc=_utc_now_iso() if ticket_status == ResearchTicketStatus.COMPLETED else None,
        requires_live_research=True,
        live_research_enabled=bool(worker_result.worker_used),
        query_execution_allowed=bool(worker_result.worker_used),
        retrieval_allowed=False,
        private_context_allowed=False,
        private_context_sent=False,
        outward_boundary_state=boundary_state,
        network_access_used=worker_result.network_access_used,
        page_fetch_allowed=False,
        page_fetch_used=False,
        live_web_research_used=bool(completed_queries),
        approval_required=worker_result.approval_required,
        worker_key=worker_result.worker_key,
        worker_used=worker_result.worker_used,
        queries_requested=worker_result.queries_requested,
        queries_sent=worker_result.queries_sent,
        query_hashes=worker_result.query_hashes,
        blocked_query_preview=worker_result.blocked_query_preview or None,
        query_count=len(worker_result.queries_sent),
        result_count=len(worker_result.results_considered),
        evidence_packet_count=len(evidence_packets),
        cloud_search_used=False,
        cloud_model_used=False,
        notes=[
            "Bounded public web research uses a local SearXNG worker.",
            "Search query terms may cross the external public web boundary.",
            "Search snippets are evidence candidates, not final proof.",
        ],
        warnings=worker_result.warnings,
        errors=worker_result.errors or worker_result.refusal_reasons,
    )


def build_fetch_ticket_from_request(
    request_model: ResearchFetchRequest,
    worker_result: FetchWorkerResult,
) -> ResearchTicket:
    evidence_packets = list(worker_result.evidence_packets)
    completed = worker_result.status == FetchWorkerStatus.COMPLETED
    blocked = worker_result.status in {
        FetchWorkerStatus.BLOCKED,
        FetchWorkerStatus.APPROVAL_REQUIRED,
    }
    return ResearchTicket(
        ticket_id=request_model.ticket_id or worker_result.ticket_id or _ticket_id(),
        question=request_model.question,
        status=(
            ResearchTicketStatus.COMPLETED
            if completed
            else ResearchTicketStatus.BLOCKED
            if blocked
            else ResearchTicketStatus.FAILED
        ),
        research_scope=ResearchScope.UNKNOWN,
        evidence_packets=evidence_packets,
        created_at_utc=_utc_now_iso(),
        completed_at_utc=_utc_now_iso() if completed else None,
        requires_live_research=True,
        live_research_enabled=completed,
        query_execution_allowed=False,
        retrieval_allowed=completed,
        private_context_allowed=False,
        private_context_sent=False,
        outward_boundary_state=(
            EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED
            if completed
            else EvidenceBoundaryState.EXTERNAL_BOUNDARY_PLANNED
        ),
        network_access_used=worker_result.network_access_used,
        page_fetch_allowed=completed,
        page_fetch_used=worker_result.page_fetch_used,
        live_web_research_used=worker_result.network_access_used,
        approval_required=worker_result.approval_required,
        worker_key=worker_result.worker_key,
        worker_used=worker_result.worker_used,
        query_count=0,
        result_count=1 if completed else 0,
        evidence_packet_count=len(evidence_packets),
        cloud_search_used=False,
        cloud_model_used=False,
        notes=[
            "A harmless public GET is bounded by Internet policy and fetch safety; sensitive egress is exactly approved before worker construction.",
            "Fetched snippets are evidence candidates, not final proof.",
            "No private context is sent outward.",
        ],
        warnings=worker_result.warnings,
        errors=worker_result.errors or worker_result.refusal_reasons,
        contract_note=(
            "Bounded public page fetch worker result. This is not crawling, "
            "browser automation, login scraping, private context export, or "
            "cloud research."
        ),
    )


def _build_worker_request(
    request_model: ResearchSearchRequest,
    *,
    exact_approval_validated: bool = False,
    safe_search_level: str = "strict",
) -> SearxngWorkerRequest:
    request_id = request_model.request_id or _new_request_id("req")
    ticket_id = request_model.ticket_id or _ticket_id()
    return SearxngWorkerRequest(
        request_id=request_id,
        ticket_id=ticket_id,
        question=request_model.question,
        queries=list(request_model.queries),
        max_results_per_query=request_model.max_results_per_query,
        approval_token=None,
        exact_approval_validated=exact_approval_validated,
        safe_search_level=safe_search_level,
        allowed_source_types=[str(getattr(item, "value", item)) for item in request_model.allowed_source_types],
        disallowed_source_types=[str(getattr(item, "value", item)) for item in request_model.disallowed_source_types],
        requires_recent_sources=request_model.requires_recent_sources,
        requires_primary_sources=request_model.requires_primary_sources,
        requires_peer_reviewed_sources=request_model.requires_peer_reviewed_sources,
    )


def _build_fetch_worker_request(request_model: ResearchFetchRequest) -> FetchWorkerRequest:
    request_id = request_model.request_id or _new_request_id("req")
    ticket_id = request_model.ticket_id or _ticket_id()
    return FetchWorkerRequest(
        request_id=request_id,
        ticket_id=ticket_id,
        url=request_model.url,
        approval_token=None,
        approval_reference=None,
        approved_by_user=False,
    )


def _authenticated_owner() -> str | None:
    try:
        from app.api.account_service import get_authenticated_principal

        return str(get_authenticated_principal()["user_id"])
    except Exception:
        return None


def _research_controls() -> tuple[str, str]:
    try:
        controls = current_user_controls()
        return controls.safe_search_level, controls.research_initiative
    except Exception:
        return "strict", "manual"


def _validate_research_scope_links(
    *, project_id: str | None, conversation_id: str | None
) -> str | None:
    """Validate new project/conversation provenance before public egress."""
    from app.memory.source_adapters import (
        MemorySourceReferenceError,
        validate_source_reference,
    )

    try:
        if project_id:
            validate_source_reference("project", project_id)
        if conversation_id:
            validate_source_reference("conversation", conversation_id)
    except MemorySourceReferenceError as exc:
        return str(exc)
    return None


def _validate_sensitive_search_approval(
    request_model: ResearchSearchRequest,
    guard: QueryGuardResult,
) -> tuple[bool, dict[str, Any] | None, str]:
    """Consume an exact approval, or create a pending sanitized preview."""
    if guard.sealed_egress_denied:
        return False, None, "sealed_egress_denied"
    if not guard.allowed and not guard.approval_required:
        return False, None, "query_policy_blocked"
    if not guard.approval_required:
        return True, None, "not_needed"
    owner = _authenticated_owner()
    if owner is None:
        return False, None, "authenticated_account_required_for_sensitive_egress"
    repository = EvidenceRepository()
    categories = list(guard.sensitive_categories)
    if request_model.approval_id and request_model.approval_token:
        allowed, reason = repository.consume_egress(
            owner_user_id=owner,
            approval_id=request_model.approval_id,
            approval_token=request_model.approval_token,
            operation="public_search",
            destination_class="public_search_engines_via_local_searxng",
            data_categories=categories,
            request_hash=guard.request_hash,
        )
        return allowed, None, reason
    preview = repository.preview_egress(
        owner_user_id=owner,
        operation="public_search",
        destination_class="public_search_engines_via_local_searxng",
        data_categories=categories,
        request_hash=guard.request_hash,
        preview={
            "query_preview": guard.blocked_query_preview,
            "query_count": len(request_model.queries),
            "private_content_included": False,
            "sealed_content_included": False,
        },
        execution_payload={
            "request_id": request_model.request_id,
            "ticket_id": request_model.ticket_id,
            "question": request_model.question,
            "queries": list(request_model.queries),
            "max_results_per_query": request_model.max_results_per_query,
            "requires_recent_sources": request_model.requires_recent_sources,
            "requires_primary_sources": request_model.requires_primary_sources,
            "requires_peer_reviewed_sources": request_model.requires_peer_reviewed_sources,
            "allowed_source_types": [str(getattr(item, "value", item)) for item in request_model.allowed_source_types],
            "disallowed_source_types": [str(getattr(item, "value", item)) for item in request_model.disallowed_source_types],
            "project_id": request_model.project_id,
            "conversation_id": request_model.conversation_id,
            "reasoning_gear": request_model.reasoning_gear,
            "research_session_id": request_model.research_session_id,
            "keep_session_open": request_model.keep_session_open,
        },
    )
    return False, preview, "exact_approval_required"


def _blocked_sensitive_egress_response(
    *,
    request_id: str,
    reason: str,
    approval: dict[str, Any] | None,
    blocked_query_preview: str = "",
) -> dict[str, Any]:
    errors = {
        "sealed_egress_denied": "Sealed content is never allowed into research egress.",
        "query_policy_blocked": "The proposed public query failed local query/privacy policy.",
        "authenticated_account_required_for_sensitive_egress": "A valid local account session is required for sensitive research approval.",
        "exact_approval_required": "Sensitive public research requires the exact pending approval shown in Governance.",
    }
    return build_response_envelope(
        status=EnvelopeStatus.BLOCKED,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="bounded_public_research",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NEEDED if approval else ApprovalState.DENIED,
        warnings=["No public query was sent."],
        errors=[errors.get(reason, f"Sensitive research approval failed: {reason}")],
        trace_summary=TraceSummary(route_used="research.search", log_written=False, journal_written=False),
        data={
            "queries_sent": [],
            "query_hashes": [],
            "blocked_query_preview": blocked_query_preview,
            "outward_boundary_state": EvidenceBoundaryState.LOCAL_CONTRACT_ONLY.value,
            "network_access_used": False,
            "private_context_sent": False,
            "cloud_search_used": False,
            "cloud_model_used": False,
            "page_fetch_used": False,
            "approval": approval,
            "approval_reason": reason,
        },
    ).to_payload()


def _local_research_response(
    *, result_type: str, data: dict[str, Any], approval_state: ApprovalState = ApprovalState.NOT_NEEDED
) -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id("research_local"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=[],
        errors=[],
        trace_summary=TraceSummary(route_used=f"research.{result_type}", log_written=False, journal_written=True),
        data=data,
    ).to_payload()


def list_durable_research(*, project_id: str | None = None, conversation_id: str | None = None) -> dict[str, Any]:
    owner = _authenticated_owner()
    if owner is None:
        return _blocked_sensitive_egress_response(
            request_id=_new_request_id("research_list"),
            reason="authenticated_account_required_for_sensitive_egress",
            approval=None,
        )
    repository = EvidenceRepository()
    return _local_research_response(
        result_type="durable_research_list",
        data={
            "sessions": repository.list_sessions(owner, project_id=project_id, conversation_id=conversation_id),
            "evidence": repository.list_evidence(owner, project_id=project_id, conversation_id=conversation_id),
        },
    )


def list_context_receipts(
    *, project_id: str | None = None, conversation_id: str | None = None, limit: int = 50
) -> dict[str, Any]:
    owner = _authenticated_owner()
    if owner is None:
        return _blocked_sensitive_egress_response(
            request_id=_new_request_id("context_receipts"),
            reason="authenticated_account_required_for_sensitive_egress",
            approval=None,
        )
    receipts = EvidenceRepository().list_context_receipts(
        owner,
        project_id=project_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return _local_research_response(
        result_type="context_receipt_list",
        data={"context_receipts": receipts, "content_free": True},
    )


def list_pending_egress_approvals() -> dict[str, Any]:
    owner = _authenticated_owner()
    if owner is None:
        return _blocked_sensitive_egress_response(
            request_id=_new_request_id("egress_pending"),
            reason="authenticated_account_required_for_sensitive_egress",
            approval=None,
        )
    return _local_research_response(
        result_type="research_egress_pending",
        data={"approvals": EvidenceRepository().pending_egress(owner)},
        approval_state=ApprovalState.NEEDED,
    )


def resolve_egress_approval(payload: dict[str, Any]) -> dict[str, Any]:
    owner = _authenticated_owner()
    if owner is None:
        raise ValueError("A valid local account session is required.")
    approval_id = str(payload.get("approval_id") or "")
    if not approval_id or not isinstance(payload.get("approve"), bool):
        raise ValueError("approval_id and a boolean approve decision are required.")
    repository = EvidenceRepository()
    execute = bool(payload.get("execute", False))
    execution_payload = (
        repository.get_egress_execution_payload(owner, approval_id)
        if execute and bool(payload["approve"])
        else None
    )
    resolution = repository.resolve_egress(
        owner_user_id=owner,
        approval_id=approval_id,
        approve=bool(payload["approve"]),
    )
    if execution_payload is not None:
        execution_payload["approval_id"] = approval_id
        execution_payload["approval_token"] = resolution["approval_token"]
        result = run_bounded_public_research(execution_payload)
        result_data = result.get("data")
        if isinstance(result_data, dict):
            result_data["approval_resolution"] = {
                "approval_id": approval_id,
                "state": "consumed" if result.get("status") != "blocked" else "approved",
                "executed": True,
                "approval_token_exposed": False,
            }
        return result
    return _local_research_response(
        result_type="research_egress_resolution",
        data={"approval": resolution},
        approval_state=ApprovalState.APPROVED if payload["approve"] else ApprovalState.DENIED,
    )


def review_evidence(evidence_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    owner = _authenticated_owner()
    if owner is None:
        raise ValueError("A valid local account session is required.")
    evidence = EvidenceRepository().set_verification(
        owner,
        evidence_id,
        verification_status=str(payload.get("verification_status") or ""),
        contradiction_notes=[str(item) for item in payload.get("contradiction_notes", [])],
    )
    return _local_research_response(result_type="research_evidence_review", data={"evidence": evidence})


def correct_evidence(evidence_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    owner = _authenticated_owner()
    if owner is None:
        raise ValueError("A valid local account session is required.")
    evidence = EvidenceRepository().correct_evidence(
        owner,
        evidence_id,
        claim=str(payload.get("claim") or ""),
        excerpt=str(payload.get("excerpt") or ""),
        reason=str(payload.get("reason") or "User corrected research evidence."),
    )
    return _local_research_response(result_type="research_evidence_correction", data={"evidence": evidence})


def promote_evidence(evidence_id: str) -> dict[str, Any]:
    owner = _authenticated_owner()
    if owner is None:
        raise ValueError("A valid local account session is required.")
    promotion = EvidenceRepository().promote_to_memory_candidate(owner, evidence_id)
    return _local_research_response(
        result_type="research_evidence_promotion",
        data={"promotion": promotion},
        approval_state=ApprovalState.NEEDED,
    )


def _persist_research_result(
    *,
    owner_user_id: str | None,
    request_model: ResearchSearchRequest,
    worker_result: SearxngWorkerResult,
    reasoning_gear: str = "standard",
) -> dict[str, Any]:
    if owner_user_id is None:
        return {"state": "not_persisted", "reason": "no_authenticated_account"}
    repository = EvidenceRepository()
    budget = {
        "max_queries": len(request_model.queries),
        "max_results_per_query": request_model.max_results_per_query,
        "safe_search_level": _research_controls()[0],
        "deterministic": True,
    }
    if request_model.research_session_id:
        repository.get_session(owner_user_id, request_model.research_session_id)
        session_id = request_model.research_session_id
    else:
        session = repository.create_session(
            owner_user_id=owner_user_id,
            question=request_model.question,
            request_id=worker_result.request_id,
            project_id=request_model.project_id,
            conversation_id=request_model.conversation_id,
            reasoning_gear=reasoning_gear,
            budget=budget,
        )
        session_id = str(session["session_id"])
    sent = {
        " ".join(str(query).split())
        for query in worker_result.queries_sent
        if str(query).strip()
    }

    outcome_by_query = {
        str(item["query"]): str(item["state"])
        for item in _worker_query_outcomes(worker_result)
    }

    for query in request_model.queries:
        query_key = " ".join(str(query).split())

        matching = [
            item
            for item in worker_result.results_considered
            if " ".join(
                str(item.get("query") or "").split()
            )
            == query_key
        ]

        domains = {
            str(
                item.get("url") or ""
            ).split("/", 3)[2].casefold()
            for item in matching
            if "/" in str(item.get("url") or "")
        }

        query_state = outcome_by_query.get(query_key)

        if query_state is None:
            if (
                query_key in sent
                and worker_result.status
                in {
                    SearxngWorkerStatus.COMPLETED,
                    SearxngWorkerStatus.DEGRADED,
                }
            ):
                query_state = "completed"

            elif query_key in sent:
                query_state = "failed"

            elif (
                worker_result.status
                == SearxngWorkerStatus.UNAVAILABLE
            ):
                query_state = "unavailable"

            elif worker_result.status in {
                SearxngWorkerStatus.BLOCKED,
                SearxngWorkerStatus.APPROVAL_REQUIRED,
            }:
                query_state = "blocked"

            else:
                query_state = "failed"

        repository.record_query(
            owner_user_id=owner_user_id,
            session_id=session_id,
            query=query,
            state=query_state,
            result_count=len(matching),
            domain_count=len(domains),
        )
    evidence_ids = [
        repository.record_evidence(
            owner_user_id=owner_user_id,
            packet={
                **dict(packet),
                "source_type": source_authority_class(str(packet.get("source_url") or "")),
                "high_stakes": _high_stakes_question(request_model.question),
            },
            session_id=session_id,
            request_id=worker_result.request_id,
            project_id=request_model.project_id,
            conversation_id=request_model.conversation_id,
            verification_status="candidate",
            quarantine_state="untrusted_web_evidence",
        )
        for packet in worker_result.evidence_packets
    ]
    terminal = (
        "completed"
        if worker_result.status in {SearxngWorkerStatus.COMPLETED, SearxngWorkerStatus.DEGRADED}
        else "failed"
    )
    if request_model.keep_session_open:
        persisted = repository.get_session(owner_user_id, session_id)
    else:
        persisted = repository.transition_session(
            owner_user_id,
            session_id,
            terminal,
            working_conclusion=(
                f"{len(evidence_ids)} quarantined evidence candidates retained."
                if evidence_ids
                else "No durable evidence candidate was produced."
            ),
            contradiction_state="not_evaluated",
        )
    return {
        "state": "persisted",
        "session_id": session_id,
        "evidence_ids": evidence_ids,
        "status": persisted["status"],
    }


def _persist_fetch_result(
    *,
    owner_user_id: str | None,
    request_model: ResearchFetchRequest,
    worker_result: FetchWorkerResult,
) -> dict[str, Any]:
    if owner_user_id is None:
        return {"state": "not_persisted", "reason": "no_authenticated_account"}
    repository = EvidenceRepository()
    session_id = request_model.research_session_id
    if session_id:
        try:
            repository.get_session(owner_user_id, session_id)
        except Exception:
            return {"state": "not_persisted", "reason": "research_session_unavailable"}
    else:
        session = repository.create_session(
            owner_user_id=owner_user_id,
            question=request_model.question,
            request_id=worker_result.request_id,
            project_id=request_model.project_id,
            conversation_id=request_model.conversation_id,
            reasoning_gear="standard",
            budget={"max_fetches": 1, "max_bytes": worker_result.bytes_read, "deterministic": True},
        )
        session_id = str(session["session_id"])
    evidence_ids = [
        repository.record_evidence(
            owner_user_id=owner_user_id,
            packet={
                **dict(packet),
                "source_type": source_authority_class(str(packet.get("source_url") or "")),
                "high_stakes": _high_stakes_question(request_model.question),
            },
            session_id=session_id,
            request_id=worker_result.request_id,
            project_id=request_model.project_id,
            conversation_id=request_model.conversation_id,
            verification_status="candidate",
            quarantine_state="untrusted_web_evidence",
        )
        for packet in worker_result.evidence_packets
    ]
    if not request_model.research_session_id:
        repository.transition_session(
            owner_user_id,
            session_id,
            "completed" if evidence_ids else "failed",
            working_conclusion=f"{len(evidence_ids)} fetched evidence candidates retained.",
            contradiction_state="not_evaluated",
        )
    return {"state": "persisted", "session_id": session_id, "evidence_ids": evidence_ids}


def _record_trace(
    *,
    request_id: str,
    ticket: ResearchTicket,
    worker_result: SearxngWorkerResult,
    envelope_status: EnvelopeStatus,
) -> None:
    start_request_trace(
        request_id=request_id,
        route_used="research.search",
        ui_surface="requests_room",
        phase="bounded_public_research",
        label="Bounded public research",
        detail="Research delegated to the local SearXNG worker boundary.",
    )
    update_request_trace_research_snapshot(
        request_id=request_id,
        research_ticket_id=ticket.ticket_id,
        research_worker_name=worker_result.worker_key,
        research_status=worker_result.status.value,
        research_query_count=len(worker_result.queries_sent),
        research_queries_sent=worker_result.queries_sent,
        research_query_hashes=worker_result.query_hashes,
        blocked_query_preview=worker_result.blocked_query_preview or None,
        evidence_packet_count=len(worker_result.evidence_packets),
        outward_boundary_state=str(getattr(ticket.outward_boundary_state, "value", ticket.outward_boundary_state)),
        private_context_sent=False,
        network_access_used=worker_result.network_access_used,
        page_fetch_used=False,
        cloud_search_used=False,
        cloud_model_used=False,
    )

    marker = {
        EnvelopeStatus.OK: mark_request_trace_completed,
        EnvelopeStatus.DEGRADED: mark_request_trace_degraded,
        EnvelopeStatus.BLOCKED: mark_request_trace_blocked,
        EnvelopeStatus.UNAVAILABLE: mark_request_trace_error,
        EnvelopeStatus.ERROR: mark_request_trace_error,
    }[envelope_status]
    marker(
        request_id=request_id,
        phase="bounded_public_research_done",
        label="Bounded public research recorded",
        detail="Research worker truth and evidence packet counts were recorded.",
        locality_state=(
            _worker_locality_state(worker_result).value
        ),
        approval_state=_status_to_approval_state(worker_result).value,
        approval_needed=worker_result.approval_required,
        worker_name=worker_result.worker_key,
        execution_tool_kind="searxng_worker",
        execution_status=worker_result.status.value,
        execution_operation="public_search",
        execution_summary=(
            f"{len(worker_result.queries_sent)} queries confirmed sent; "
            f"{len(_worker_completed_queries(worker_result))} "
            "queries completed; "
            f"{len(worker_result.evidence_packets)} "
            "evidence packets produced."
        ),
        errors=worker_result.errors or worker_result.refusal_reasons,
        warnings=worker_result.warnings,
    )


def build_research_response_data(
    *,
    ticket: ResearchTicket,
    worker_result: SearxngWorkerResult,
    evidence_verification: dict[str, Any],
) -> dict[str, Any]:
    contradiction_scan = evidence_verification.get("contradiction_scan")
    return {
        "research_ticket": ticket.to_payload(),
        "worker_summary": worker_result.to_payload(),
        "evidence_packets": [packet.to_payload() for packet in ticket.evidence_packets],
        "evidence_verification": evidence_verification,
        "contradiction_scan": contradiction_scan,
        "queries_sent": list(worker_result.queries_sent),
        "query_hashes": list(worker_result.query_hashes),
        "blocked_query_preview": worker_result.blocked_query_preview,
        "outward_boundary_state": str(getattr(ticket.outward_boundary_state, "value", ticket.outward_boundary_state)),
        "network_access_used": worker_result.network_access_used,
        "private_context_sent": False,
        "cloud_search_used": False,
        "cloud_model_used": False,
        "page_fetch_used": False,
        "warnings": list(worker_result.warnings) + list(evidence_verification.get("warnings", [])),
        "errors": list(worker_result.errors or worker_result.refusal_reasons) + list(evidence_verification.get("issues", [])),
    }


def _fetch_status_to_envelope_status(
    status: FetchWorkerStatus,
    verified: bool,
) -> EnvelopeStatus:
    if status == FetchWorkerStatus.COMPLETED and verified:
        return EnvelopeStatus.OK
    if status == FetchWorkerStatus.APPROVAL_REQUIRED:
        return EnvelopeStatus.BLOCKED
    if status == FetchWorkerStatus.BLOCKED:
        return EnvelopeStatus.BLOCKED
    if status == FetchWorkerStatus.UNAVAILABLE:
        return EnvelopeStatus.UNAVAILABLE
    if status == FetchWorkerStatus.DEGRADED:
        return EnvelopeStatus.DEGRADED
    return EnvelopeStatus.ERROR


def _fetch_status_to_capability_state(status: FetchWorkerStatus) -> CapabilityState:
    if status == FetchWorkerStatus.COMPLETED:
        return CapabilityState.LIVE
    if status == FetchWorkerStatus.UNAVAILABLE:
        return CapabilityState.UNAVAILABLE
    if status in {FetchWorkerStatus.BLOCKED, FetchWorkerStatus.APPROVAL_REQUIRED}:
        return CapabilityState.LIVE
    return CapabilityState.DEGRADED


def _fetch_approval_state(worker_result: FetchWorkerResult) -> ApprovalState:
    if worker_result.approval_required:
        return ApprovalState.NEEDED
    if worker_result.status == FetchWorkerStatus.BLOCKED:
        return ApprovalState.DENIED
    return ApprovalState.NOT_NEEDED


def _record_fetch_trace(
    *,
    request_id: str,
    ticket: ResearchTicket,
    worker_result: FetchWorkerResult,
    envelope_status: EnvelopeStatus,
) -> None:
    start_request_trace(
        request_id=request_id,
        route_used="research.fetch",
        ui_surface="requests_room",
        phase="bounded_public_fetch",
        label="Bounded public fetch",
        detail="Public URL fetch delegated to the bounded fetch worker.",
    )
    update_request_trace_research_snapshot(
        request_id=request_id,
        research_ticket_id=ticket.ticket_id,
        research_worker_name=worker_result.worker_key,
        research_status=worker_result.status.value,
        research_query_count=0,
        research_queries_sent=[],
        research_query_hashes=[worker_result.url_hash] if worker_result.url_hash else [],
        blocked_query_preview=None,
        evidence_packet_count=len(worker_result.evidence_packets),
        outward_boundary_state=str(
            getattr(ticket.outward_boundary_state, "value", ticket.outward_boundary_state)
        ),
        private_context_sent=False,
        network_access_used=worker_result.network_access_used,
        page_fetch_used=worker_result.page_fetch_used,
        cloud_search_used=False,
        cloud_model_used=False,
    )
    marker = {
        EnvelopeStatus.OK: mark_request_trace_completed,
        EnvelopeStatus.DEGRADED: mark_request_trace_degraded,
        EnvelopeStatus.BLOCKED: mark_request_trace_blocked,
        EnvelopeStatus.UNAVAILABLE: mark_request_trace_error,
        EnvelopeStatus.ERROR: mark_request_trace_error,
    }[envelope_status]
    marker(
        request_id=request_id,
        phase="bounded_public_fetch_done",
        label="Bounded public fetch recorded",
        detail="Fetch worker boundary truth and evidence packet count were recorded.",
        locality_state=(
            LocalityState.CROSSED_BOUNDARY.value
            if worker_result.network_access_used
            else LocalityState.LOCAL.value
        ),
        approval_state=_fetch_approval_state(worker_result).value,
        approval_needed=worker_result.approval_required,
        worker_name=worker_result.worker_key,
        execution_tool_kind="fetch_worker",
        execution_status=worker_result.status.value,
        execution_operation="public_page_fetch",
        execution_summary=(
            f"Fetched URL evidence packets: {len(worker_result.evidence_packets)}."
        ),
        errors=worker_result.errors or worker_result.refusal_reasons,
        warnings=worker_result.warnings,
    )


def build_fetch_response_data(
    *,
    ticket: ResearchTicket,
    worker_result: FetchWorkerResult,
    evidence_verification: dict[str, Any],
) -> dict[str, Any]:
    return {
        "research_ticket": ticket.to_payload(),
        "worker_summary": worker_result.to_payload(),
        "evidence_packets": [packet.to_payload() for packet in ticket.evidence_packets],
        "evidence_verification": evidence_verification,
        "requested_url": worker_result.requested_url,
        "sanitized_url": worker_result.sanitized_url,
        "url_hash": worker_result.url_hash,
        "title": worker_result.title,
        "snippet": worker_result.snippet,
        "content_type": worker_result.content_type,
        "status_code": worker_result.status_code,
        "bytes_read": worker_result.bytes_read,
        "outward_boundary_state": str(
            getattr(ticket.outward_boundary_state, "value", ticket.outward_boundary_state)
        ),
        "network_access_used": worker_result.network_access_used,
        "private_context_sent": False,
        "cloud_search_used": False,
        "cloud_model_used": False,
        "page_fetch_used": worker_result.page_fetch_used,
        "warnings": list(worker_result.warnings)
        + list(evidence_verification.get("warnings", [])),
        "errors": list(worker_result.errors or worker_result.refusal_reasons)
        + list(evidence_verification.get("issues", [])),
    }


def run_bounded_public_research(
    request_payload: dict[str, Any],
    *,
    worker_runner: Callable[[SearxngWorkerRequest], SearxngWorkerResult] | None = None,
    internet_enabled_reader: Callable[[], bool] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Validate request data, run the worker, verify evidence, and build envelope."""
    envelope_request_id = _new_request_id("research")

    try:
        request_model = ResearchSearchRequest(**request_payload)
    except ValidationError as exc:
        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bounded_public_research",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Research request validation failed: {exc}"],
            trace_summary=TraceSummary(route_used="research.search", log_written=False, journal_written=False),
            data={},
        )
        return envelope.to_payload()

    effective_cancel_check = _combined_cancel_check(
        cancel_check
    )

    internet_is_enabled = (internet_enabled_reader or internet_master_enabled)()
    invalid_link = _validate_research_scope_links(
        project_id=request_model.project_id,
        conversation_id=request_model.conversation_id,
    )
    if invalid_link:
        return build_response_envelope(
            status=EnvelopeStatus.BLOCKED,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bounded_public_research",
            capability_state=CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.DENIED,
            warnings=["No public query was sent."],
            errors=[invalid_link],
            trace_summary=TraceSummary(route_used="research.search", log_written=False, journal_written=False),
            data={"network_access_used": False, "private_context_sent": False, "invalid_authority_link": True},
        ).to_payload()
    if not internet_is_enabled:
        return build_response_envelope(
            status=EnvelopeStatus.BLOCKED,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bounded_public_research",
            capability_state=CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.DENIED,
            warnings=["No query was sent and no non-local network request occurred."],
            errors=["Internet master switch is OFF."],
            trace_summary=TraceSummary(route_used="research.search", log_written=False, journal_written=False),
            data={"network_access_used": False, "private_context_sent": False, "internet_master_enabled": False},
        ).to_payload()

    try:
        guard = guard_public_queries(
            request_model.queries,
            config=load_searxng_worker_config(),
            exact_approval_validated=False,
        )
    except Exception:
        guard = QueryGuardResult(
            allowed=False,
            refusal_reasons=["Public query policy could not be loaded; egress failed closed."],
        )
    exact_approval, approval_preview, approval_reason = _validate_sensitive_search_approval(
        request_model, guard
    )
    if not exact_approval:
        return _blocked_sensitive_egress_response(
            request_id=request_model.request_id or envelope_request_id,
            reason=approval_reason,
            approval=approval_preview,
            blocked_query_preview=guard.blocked_query_preview,
        )
    safe_search_level, _initiative = _research_controls()
    worker_request = _build_worker_request(
        request_model,
        exact_approval_validated=guard.approval_required,
        safe_search_level=safe_search_level,
    )
    if worker_runner is None:
        worker_result = run_searxng_worker(
            worker_request,
            cancel_check=effective_cancel_check,
        )
    else:
        worker_result = worker_runner(
            worker_request
        )
    ticket = build_research_ticket_from_request(request_model, worker_result)
    evidence_verification = verify_research_ticket_payload(ticket)
    envelope_status = _status_to_envelope_status(
        worker_result.status,
        bool(evidence_verification.get("verified")),
    )
    data = build_research_response_data(
        ticket=ticket,
        worker_result=worker_result,
        evidence_verification=evidence_verification,
    )
    data["durable_research"] = _persist_research_result(
        owner_user_id=_authenticated_owner(),
        request_model=request_model,
        worker_result=worker_result,
        reasoning_gear=request_model.reasoning_gear,
    )
    data["safe_search_level"] = safe_search_level

    _record_trace(
        request_id=worker_request.request_id,
        ticket=ticket,
        worker_result=worker_result,
        envelope_status=envelope_status,
    )

    envelope = build_response_envelope(
        status=envelope_status,
        request_id=worker_request.request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="bounded_public_research",
        capability_state=_status_to_capability_state(worker_result.status),
        locality=_worker_locality_state(worker_result),
        approval_state=_status_to_approval_state(worker_result),
        warnings=data["warnings"],
        errors=(
            data["errors"]
            if envelope_status
            in {
                EnvelopeStatus.BLOCKED,
                EnvelopeStatus.ERROR,
                EnvelopeStatus.UNAVAILABLE,
            }
            else []
        ),
        trace_summary=TraceSummary(
            route_used="research.search",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    )
    return envelope.to_payload()


def run_bounded_public_fetch(
    request_payload: dict[str, Any],
    *,
    worker_runner: Callable[[FetchWorkerRequest], FetchWorkerResult] | None = None,
    internet_enabled_reader: Callable[[], bool] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Validate request data, run the bounded fetch worker, and build envelope."""
    envelope_request_id = _new_request_id("fetch")

    try:
        request_model = ResearchFetchRequest(**request_payload)
    except ValidationError as exc:
        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bounded_public_fetch",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Fetch request validation failed: {exc}"],
            trace_summary=TraceSummary(
                route_used="research.fetch",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()

    effective_cancel_check = _combined_cancel_check(
        cancel_check
    )

    internet_is_enabled = (internet_enabled_reader or internet_master_enabled)()
    invalid_link = _validate_research_scope_links(
        project_id=request_model.project_id,
        conversation_id=request_model.conversation_id,
    )
    if invalid_link:
        return build_response_envelope(
            status=EnvelopeStatus.BLOCKED,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bounded_public_fetch",
            capability_state=CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.DENIED,
            warnings=["No page request was sent."],
            errors=[invalid_link],
            trace_summary=TraceSummary(route_used="research.fetch", log_written=False, journal_written=False),
            data={"network_access_used": False, "private_context_sent": False, "invalid_authority_link": True},
        ).to_payload()
    if not internet_is_enabled:
        return build_response_envelope(
            status=EnvelopeStatus.BLOCKED,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bounded_public_fetch",
            capability_state=CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.DENIED,
            warnings=["No page request was sent and no non-local network request occurred."],
            errors=["Internet master switch is OFF."],
            trace_summary=TraceSummary(route_used="research.fetch", log_written=False, journal_written=False),
            data={"network_access_used": False, "private_context_sent": False, "internet_master_enabled": False},
        ).to_payload()

    worker_request = _build_fetch_worker_request(request_model)
    if worker_runner is None:
        try:
            worker_result = run_fetch_worker(
                worker_request,
                cancel_check=effective_cancel_check,
            )
        except TypeError:
            # Compatibility for injected workers that implement the original
            # single-argument contract.
            worker_result = run_fetch_worker(worker_request)
    else:
        worker_result = worker_runner(worker_request)
    ticket = build_fetch_ticket_from_request(request_model, worker_result)
    evidence_verification = verify_research_ticket_payload(ticket)
    envelope_status = _fetch_status_to_envelope_status(
        worker_result.status,
        bool(evidence_verification.get("verified")),
    )
    data = build_fetch_response_data(
        ticket=ticket,
        worker_result=worker_result,
        evidence_verification=evidence_verification,
    )
    data["durable_research"] = _persist_fetch_result(
        owner_user_id=_authenticated_owner(),
        request_model=request_model,
        worker_result=worker_result,
    )
    _record_fetch_trace(
        request_id=worker_request.request_id,
        ticket=ticket,
        worker_result=worker_result,
        envelope_status=envelope_status,
    )
    envelope = build_response_envelope(
        status=envelope_status,
        request_id=worker_request.request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="bounded_public_fetch",
        capability_state=_fetch_status_to_capability_state(worker_result.status),
        locality=(
            LocalityState.CROSSED_BOUNDARY
            if worker_result.network_access_used
            else LocalityState.LOCAL
        ),
        approval_state=_fetch_approval_state(worker_result),
        warnings=data["warnings"],
        errors=(
            data["errors"]
            if envelope_status
            in {
                EnvelopeStatus.BLOCKED,
                EnvelopeStatus.ERROR,
                EnvelopeStatus.UNAVAILABLE,
            }
            else []
        ),
        trace_summary=TraceSummary(
            route_used="research.fetch",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    )
    return envelope.to_payload()


class WebResearchPort:
    """One governed iterative research port built on the established routes."""

    def investigate(
        self,
        *,
        question: str,
        request_id: str,
        conversation_id: str | None,
        project_id: str | None,
        reasoning_gear: str,
        autonomy_level: int,
        approval_id: str | None = None,
        approval_token: str | None = None,
        cancel_check: Callable[[], bool] | None = None,
        search_runner: Callable[
            ...,
            dict[str, Any],
        ] = run_bounded_public_research,
        fetch_runner: Callable[
            ...,
            dict[str, Any],
        ] = run_bounded_public_fetch,
    ) -> dict[str, Any]:
        started = perf_counter()

        safe_search, initiative = _research_controls()

        budget = research_budget_for(
            reasoning_gear=reasoning_gear,
            autonomy_level=autonomy_level,
            initiative=initiative,
        )

        queries, query_privacy = (
            prepare_minimum_necessary_public_queries(
                question,
                limit=budget.max_queries,
            )
        )

        progress: list[dict[str, Any]] = []
        evidence_ids: list[str] = []
        evidence_packets: list[dict[str, Any]] = []

        session_id: str | None = None

        network_used = False
        bytes_read = 0
        query_count = 0
        fetch_count = 0

        cancelled = False
        budget_exhausted = False

        approval: dict[str, Any] | None = None

        errors: list[str] = []
        terminal_search_status: str | None = None
        attempted = False
        searxng_used = False

        terminal_search_status: str | None = None

        attempted = False
        worker_used = False
        searxng_used = False
        completed_search_count = 0
        degraded = False

        if not internet_master_enabled():
            return {
                "state": "blocked",
                "reason": "internet_master_off",
                "network_access_used": False,
                "private_context_sent": False,
                "budget": budget.to_payload(),
                "progress": [],
                "evidence_ids": [],
                "session_id": None,
                "query_privacy": query_privacy,
                "research_attempted": False,
                "worker_used": False,
                "searxng_used": False,
                "internet_master_enabled": False,
                "budget_exhausted": False,
            }

        if not queries:
            return {
                "state": "blocked",
                "reason": query_privacy.get(
                    "blocked_reason",
                    "no_public_safe_query",
                ),
                "research_attempted": False,
                "worker_used": False,
                "searxng_used": False,
                "internet_master_enabled": True,
                "network_access_used": False,
                "private_context_sent": False,
                "evidence_ids": [],
                "query_privacy": query_privacy,
                "budget_exhausted": False,
            }

        for sequence, query in enumerate(
            queries,
            start=1,
        ):
            if (
                cancel_check
                and cancel_check()
            ):
                cancelled = True
                break

            if (
                perf_counter() - started
                >= budget.max_elapsed_seconds
            ):
                budget_exhausted = True
                errors.append(
                    "Research budget elapsed before all planned "
                    "search work completed."
                )
                break

            payload = {
                "request_id": (
                    f"{request_id}:search:{sequence}"
                ),
                "question": query,
                "queries": [query],
                "max_results_per_query": (
                    budget.max_results_per_query
                ),
                "project_id": project_id,
                "conversation_id": conversation_id,
                "reasoning_gear": reasoning_gear,
                "research_session_id": session_id,
                "keep_session_open": True,
            }

            if (
                sequence == 1
                and approval_id
                and approval_token
            ):
                payload["approval_id"] = approval_id
                payload["approval_token"] = approval_token

            attempted = True

            if search_runner is run_bounded_public_research:
                result = search_runner(
                    payload,
                    cancel_check=cancel_check,
                )
            else:
                result = search_runner(
                    payload
                )

            data = dict(
                result.get("data") or {}
            )

            raw_status = str(
                result.get("status") or "error"
            ).casefold()

            status = (
                "failed"
                if raw_status == "error"
                else raw_status
            )

            progress.append(
                {
                    "stage": "search",
                    "sequence": sequence,
                    "state": status,
                }
            )

            worker_summary = dict(
                data.get("worker_summary") or {}
            )

            worker_used = (
                worker_used
                or bool(
                    worker_summary.get(
                        "worker_used"
                    )
                )
            )

            searxng_used = (
                searxng_used
                or bool(
                    worker_summary.get(
                        "searxng_used"
                    )
                )
            )

            query_outcomes = [
                dict(item)
                for item in worker_summary.get(
                    "query_outcomes",
                    [],
                )
                if isinstance(item, dict)
            ]

            completed_search_count += sum(
                1
                for item in query_outcomes
                if item.get("state") == "completed"
            )

            query_count += len(
                data.get("queries_sent") or []
            )

            network_used = (
                network_used
                or bool(
                    data.get("network_access_used")
                )
            )

            durable = dict(
                data.get("durable_research") or {}
            )

            session_id = (
                str(
                    durable.get("session_id")
                    or session_id
                    or ""
                )
                or None
            )

            evidence_ids.extend(
                str(item)
                for item in durable.get(
                    "evidence_ids",
                    [],
                )
                if str(item)
            )

            evidence_packets.extend(
                dict(item)
                for item in data.get(
                    "evidence_packets",
                    [],
                )
                if isinstance(item, dict)
            )

            search_cancelled = any(
                item.get("state") == "cancelled"
                for item in query_outcomes
            )

            if (
                search_cancelled
                or (
                    cancel_check
                    and cancel_check()
                )
            ):
                cancelled = True
                progress[-1]["state"] = "cancelled"

                errors.extend(
                    str(item)
                    for item in (
                        data.get("errors")
                        or result.get("errors")
                        or []
                    )
                    if str(item)
                )

                break

            if raw_status == "blocked":
                terminal_search_status = "blocked"

                approval = (
                    data.get("approval")
                    if isinstance(
                        data.get("approval"),
                        dict,
                    )
                    else None
                )

                errors.extend(
                    str(item)
                    for item in result.get(
                        "errors",
                        [],
                    )
                    if str(item)
                )

                break

            if raw_status == "unavailable":
                terminal_search_status = "unavailable"

                errors.extend(
                    str(item)
                    for item in result.get(
                        "errors",
                        [],
                    )
                    if str(item)
                )

                break

            if raw_status == "error":
                terminal_search_status = "failed"

                errors.extend(
                    str(item)
                    for item in result.get(
                        "errors",
                        [],
                    )
                    if str(item)
                )

                break

            if raw_status == "degraded":
                degraded = True

                errors.extend(
                    str(item)
                    for item in data.get(
                        "errors",
                        [],
                    )
                    if str(item)
                )

            elif raw_status != "ok":
                terminal_search_status = "failed"

                errors.append(
                    "Unrecognized research search state: "
                    f"{raw_status}"
                )

                break

            owner = _authenticated_owner()

            if owner and session_id:
                EvidenceRepository().record_progress(
                    owner_user_id=owner,
                    session_id=session_id,
                    stage="search",
                    state=status,
                    detail={
                        "query_sequence": sequence,
                        "result_count": len(
                            data.get(
                                "evidence_packets"
                            )
                            or []
                        ),
                    },
                )

            if (
                sequence == 1
                and approval_id
                and approval_token
            ):
                # The exact grant covers only the first
                # bound query hash.
                break

        # Prefer authority-class diversity, then domain
        # diversity, before filling remaining slots.
        selected_urls: list[
            tuple[str, str]
        ] = []

        seen_domains: set[str] = set()
        seen_authorities: set[str] = set()

        candidates_by_authority: dict[
            str,
            list[str],
        ] = {}

        for packet in evidence_packets:
            url = str(
                packet.get("source_url") or ""
            )

            domain = str(
                urlparse(url).hostname or ""
            ).casefold()

            if not url or not domain:
                continue

            authority = source_authority_class(url)

            candidates_by_authority.setdefault(
                authority,
                [],
            ).append(url)

        for authority in sorted(
            candidates_by_authority
        ):
            url = next(
                (
                    candidate
                    for candidate
                    in candidates_by_authority[
                        authority
                    ]
                    if str(
                        urlparse(
                            candidate
                        ).hostname
                        or ""
                    ).casefold()
                    not in seen_domains
                ),
                "",
            )

            if not url:
                continue

            domain = str(
                urlparse(url).hostname or ""
            ).casefold()

            seen_domains.add(domain)
            seen_authorities.add(authority)

            selected_urls.append(
                (url, authority)
            )

            if (
                len(selected_urls)
                >= min(
                    budget.max_fetches,
                    budget.max_domains,
                )
            ):
                break

        if (
            len(selected_urls)
            < min(
                budget.max_fetches,
                budget.max_domains,
            )
        ):
            for packet in evidence_packets:
                url = str(
                    packet.get("source_url")
                    or ""
                )

                domain = str(
                    urlparse(url).hostname
                    or ""
                ).casefold()

                if (
                    not url
                    or not domain
                    or domain in seen_domains
                ):
                    continue

                authority = (
                    source_authority_class(url)
                )

                seen_domains.add(domain)
                seen_authorities.add(
                    authority
                )

                selected_urls.append(
                    (url, authority)
                )

                if (
                    len(selected_urls)
                    >= min(
                        budget.max_fetches,
                        budget.max_domains,
                    )
                ):
                    break

        # A governance block or approval interruption
        # ends further outward work.
        #
        # A non-policy search failure may leave earlier
        # valid public evidence eligible for bounded fetch,
        # but the parent result remains degraded.
        if (
            terminal_search_status != "blocked"
            and approval is None
        ):
            for sequence, (
                url,
                authority_class,
            ) in enumerate(
                selected_urls,
                start=1,
            ):
                if (
                    cancel_check
                    and cancel_check()
                ):
                    cancelled = True
                    break

                if (
                    perf_counter() - started
                    >= budget.max_elapsed_seconds
                ):
                    budget_exhausted = True

                    errors.append(
                        "Research budget elapsed before "
                        "all planned fetch work completed."
                    )

                    break

                if bytes_read >= budget.max_bytes:
                    budget_exhausted = True

                    errors.append(
                        "Research byte budget was exhausted "
                        "before all planned fetch work completed."
                    )

                    break

                fetch_payload = {
                    "request_id": (
                        f"{request_id}:fetch:{sequence}"
                    ),
                    "question": queries[0],
                    "url": url,
                    "research_session_id": (
                        session_id
                    ),
                    "project_id": project_id,
                    "conversation_id": (
                        conversation_id
                    ),
                }

                try:
                    result = fetch_runner(
                        fetch_payload,
                        cancel_check=cancel_check,
                    )

                except TypeError:
                    result = fetch_runner(
                        fetch_payload
                    )

                data = dict(
                    result.get("data") or {}
                )

                raw_status = str(
                    result.get("status") or "error"
                ).casefold()

                status = (
                    "failed"
                    if raw_status == "error"
                    else raw_status
                )

                # Catch cancellation that occurs inside
                # a bounded fetch call.
                if (
                    cancel_check
                    and cancel_check()
                ):
                    cancelled = True
                    status = "cancelled"

                progress.append(
                    {
                        "stage": "fetch",
                        "sequence": sequence,
                        "state": status,
                        "domain": str(
                            urlparse(url).hostname
                            or ""
                        ),
                        "authority_class": (
                            authority_class
                        ),
                    }
                )

                bytes_read += int(
                    data.get("bytes_read") or 0
                )

                fetch_count += int(
                    bool(
                        data.get(
                            "page_fetch_used"
                        )
                    )
                )

                network_used = (
                    network_used
                    or bool(
                        data.get(
                            "network_access_used"
                        )
                    )
                )

                durable = dict(
                    data.get(
                        "durable_research"
                    )
                    or {}
                )

                evidence_ids.extend(
                    str(item)
                    for item in durable.get(
                        "evidence_ids",
                        [],
                    )
                    if str(item)
                )

                if cancelled:
                    errors.extend(
                        str(item)
                        for item in result.get(
                            "errors",
                            [],
                        )
                        if str(item)
                    )

                elif raw_status == "degraded":
                    degraded = True

                    errors.extend(
                        str(item)
                        for item in data.get(
                            "errors",
                            [],
                        )
                        if str(item)
                    )

                elif raw_status != "ok":
                    degraded = True

                    errors.extend(
                        str(item)
                        for item in result.get(
                            "errors",
                            [],
                        )
                        if str(item)
                    )

                owner = _authenticated_owner()

                if owner and session_id:
                    EvidenceRepository().record_progress(
                        owner_user_id=owner,
                        session_id=session_id,
                        stage="fetch",
                        state=status,
                        detail={
                            "fetch_sequence": (
                                sequence
                            ),
                            "domain": str(
                                urlparse(
                                    url
                                ).hostname
                                or ""
                            ),
                            "authority_class": (
                                authority_class
                            ),
                            "bytes_read": int(
                                data.get(
                                    "bytes_read"
                                )
                                or 0
                            ),
                        },
                    )

                if cancelled:
                    break

        if cancelled:
            final_state = "cancelled"

        elif approval is not None:
            final_state = "approval_required"

        elif terminal_search_status == "blocked":
            final_state = "blocked"

        elif terminal_search_status in {
            "unavailable",
            "failed",
        }:
            final_state = (
                "degraded"
                if (
                    completed_search_count > 0
                    or bool(evidence_ids)
                )
                else terminal_search_status
            )

        elif budget_exhausted or degraded:
            final_state = "degraded"

        elif evidence_ids:
            final_state = "completed"

        elif (
            completed_search_count > 0
            or searxng_used
            or network_used
        ):
            final_state = "degraded"

        else:
            final_state = "failed"

        owner = _authenticated_owner()

        if owner and session_id:
            repository = EvidenceRepository()

            repository.update_session_budget(
                owner,
                session_id,
                {
                    **budget.to_payload(),
                    "safe_search_level": (
                        safe_search
                    ),
                    "research_initiative": (
                        initiative
                    ),
                    "actual_queries": (
                        query_count
                    ),
                    "actual_fetches": (
                        fetch_count
                    ),
                    "actual_domains": len(
                        seen_domains
                    ),
                    "actual_authority_classes": len(
                        seen_authorities
                    ),
                    "authority_classes": sorted(
                        seen_authorities
                    ),
                    "actual_bytes": bytes_read,
                },
            )

            if final_state in {
                "completed",
                "degraded",
            }:
                durable_state = "completed"

            elif final_state == "cancelled":
                durable_state = "cancelled"

            elif (
                final_state
                == "approval_required"
            ):
                durable_state = "paused"

            else:
                durable_state = "failed"

            repository.transition_session(
                owner,
                session_id,
                durable_state,
                working_conclusion=(
                    f"{len(set(evidence_ids))} "
                    "quarantined evidence records retained "
                    f"across {len(seen_domains)} domains."
                ),
                contradiction_state=(
                    "not_evaluated"
                ),
            )

        return {
            "state": final_state,
            "session_id": session_id,
            "evidence_ids": list(
                dict.fromkeys(evidence_ids)
            ),
            "query_count": query_count,
            "fetch_count": fetch_count,
            "domain_count": len(
                seen_domains
            ),
            "authority_class_count": len(
                seen_authorities
            ),
            "authority_classes": sorted(
                seen_authorities
            ),
            "bytes_read": bytes_read,
            "elapsed_ms": round(
                (
                    perf_counter()
                    - started
                )
                * 1000,
                3,
            ),
            "budget": budget.to_payload(),
            "safe_search_level": (
                safe_search
            ),
            "research_initiative": (
                initiative
            ),
            "progress": progress,
            "approval": approval,
            "network_access_used": (
                network_used
            ),
            "research_attempted": (
                attempted
            ),
            "worker_used": worker_used,
            "searxng_used": searxng_used,
            "internet_master_enabled": True,
            "private_context_sent": False,
            "untrusted_content_quarantined": True,
            "query_privacy": query_privacy,
            "budget_exhausted": (
                budget_exhausted
            ),
            "errors": errors,
        }


__all__ = (
    "ResearchBudget",
    "WebResearchPort",
    "build_research_response_data",
    "build_research_ticket_from_request",
    "run_bounded_public_fetch",
    "run_bounded_public_research",
    "research_budget_for",
    "minimum_necessary_public_queries",
    "source_authority_class",
)
