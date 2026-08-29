from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import search_searxng
from .config import (
    DEFAULT_SEARXNG_WORKER_CONFIG_PATH,
    load_searxng_worker_config,
    validate_searxng_worker_config,
)
from .contract import SearxngWorkerRequest, SearxngWorkerResult, SearxngWorkerStatus
from .query_guard import guard_public_queries


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _trace_summary(
    request: SearxngWorkerRequest,
    *,
    status: SearxngWorkerStatus,
    queries_sent: list[str] | None = None,
    result_count: int = 0,
    evidence_packet_count: int = 0,
) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "trace_parent_id": request.trace_parent_id,
        "ticket_id": request.ticket_id,
        "status": status.value,
        "worker_key": request.worker_key,
        "query_count": len(queries_sent or []),
        "result_count": result_count,
        "evidence_packet_count": evidence_packet_count,
        "outward_boundary_state": "external_boundary_crossed" if queries_sent else "external_boundary_planned",
        "private_context_sent": False,
        "network_access_used": bool(queries_sent),
        "page_fetch_used": False,
        "cloud_search_used": False,
        "cloud_model_used": False,
    }


def _terminal_result(
    *,
    request: SearxngWorkerRequest,
    status: SearxngWorkerStatus,
    refusal_reasons: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    approval_required: bool = False,
    approval_reason: str = "",
    queries_requested: list[str] | None = None,
    query_hashes: list[str] | None = None,
    blocked_query_preview: str = "",
) -> SearxngWorkerResult:
    return SearxngWorkerResult(
        status=status,
        worker_key=request.worker_key,
        worker_used=False,
        searxng_used=False,
        request_id=request.request_id,
        ticket_id=request.ticket_id,
        queries_requested=list(queries_requested or request.queries),
        queries_sent=[],
        query_hashes=list(query_hashes or []),
        blocked_query_preview=blocked_query_preview,
        network_access_used=False,
        page_fetch_used=False,
        private_context_sent=False,
        cloud_search_used=False,
        cloud_model_used=False,
        approval_required=approval_required,
        approval_reason=approval_reason,
        refusal_reasons=list(refusal_reasons or []),
        warnings=list(warnings or []),
        errors=list(errors or []),
        trace_summary=_trace_summary(request, status=status),
    )


def _request_refusal_reasons(request: SearxngWorkerRequest) -> list[str]:
    reasons: list[str] = []
    if request.worker_key != "searxng_research_worker":
        reasons.append(f"Unexpected worker key for SearXNG worker: {request.worker_key}")
    if request.public_query_only is not True:
        reasons.append("SearXNG worker requires public_query_only true.")
    if request.private_context_allowed is not False:
        reasons.append("SearXNG worker must not allow private context outward.")
    if request.private_context_sent is not False:
        reasons.append("SearXNG worker request claims private context was sent.")
    if request.network_access_allowed is not True:
        reasons.append("SearXNG worker requires explicit bounded network allowance.")
    if request.page_fetch_allowed is not False:
        reasons.append("Page fetching is not allowed for Sprint 9 SearXNG search.")
    if request.cloud_search_allowed is not False:
        reasons.append("Cloud search is not allowed for Sprint 9 SearXNG search.")
    if request.cloud_model_allowed is not False:
        reasons.append("Cloud model use is not allowed for Sprint 9 SearXNG search.")
    return reasons


def _packet_from_result(
    *,
    request: SearxngWorkerRequest,
    query: str,
    result: dict[str, Any],
    max_snippet_length: int,
) -> dict[str, Any]:
    snippet = str(result.get("snippet") or "").strip()[:max_snippet_length]
    title = str(result.get("title") or "Untitled search result").strip()
    source_engine = str(result.get("source_engine") or "").strip()
    rank = result.get("rank")
    return {
        "source_url": str(result.get("url") or "").strip(),
        "title": title or "Untitled search result",
        "retrieved_at_utc": _utc_now_iso(),
        "snippet": snippet or "SearXNG returned this result without a snippet.",
        "claim": (
            f"Search result for query '{query}' may be relevant to: "
            f"{request.question}"
        )[:1000],
        "confidence": "low",
        "contradiction_notes": [],
        "source_type": "unknown",
        "retrieval_method": "searxng_search",
        "outward_boundary_state": "external_boundary_crossed",
        "private_context_sent": False,
        "network_access_used": True,
        "page_fetch_used": False,
        "live_web_research_used": True,
        "source_rank": rank if isinstance(rank, int) and rank > 0 else None,
        "publisher": source_engine or None,
        "warnings": ["Search snippets are evidence candidates, not final proof."],
        "errors": [],
    }


def run_searxng_worker(
    request: SearxngWorkerRequest,
    *,
    config_path: str | Path = DEFAULT_SEARXNG_WORKER_CONFIG_PATH,
    search_client: Callable[..., list[dict[str, Any]]] | None = None,
) -> SearxngWorkerResult:
    """
    Run bounded public SearXNG search through the worker boundary.

    This function never fetches result pages and never sends private context.
    """
    try:
        config = load_searxng_worker_config(config_path)
    except Exception as exc:
        return _terminal_result(
            request=request,
            status=SearxngWorkerStatus.UNAVAILABLE,
            refusal_reasons=[f"SearXNG worker config could not be loaded: {exc}"],
            errors=[str(exc)],
        )

    config_reasons = validate_searxng_worker_config(config)
    request_reasons = _request_refusal_reasons(request)
    if config_reasons or request_reasons:
        return _terminal_result(
            request=request,
            status=SearxngWorkerStatus.BLOCKED,
            refusal_reasons=config_reasons + request_reasons,
        )

    if config.service.get("enabled") is not True:
        return _terminal_result(
            request=request,
            status=SearxngWorkerStatus.UNAVAILABLE,
            refusal_reasons=["SearXNG worker service is configured but disabled."],
            warnings=["No query was sent. Enable local SearXNG explicitly before live search."],
        )

    guard = guard_public_queries(
        request.queries,
        config=config,
        exact_approval_validated=request.exact_approval_validated,
    )
    if guard.refusal_reasons and guard.approval_required:
        return _terminal_result(
            request=request,
            status=SearxngWorkerStatus.APPROVAL_REQUIRED,
            refusal_reasons=guard.refusal_reasons,
            warnings=guard.warnings,
            approval_required=True,
            approval_reason="Sensitive public-web research query requires approval before network use.",
            queries_requested=guard.queries_requested,
            query_hashes=guard.query_hashes,
            blocked_query_preview=guard.blocked_query_preview,
        )
    if not guard.allowed:
        return _terminal_result(
            request=request,
            status=SearxngWorkerStatus.BLOCKED,
            refusal_reasons=guard.refusal_reasons,
            warnings=guard.warnings,
            queries_requested=guard.queries_requested,
            query_hashes=guard.query_hashes,
            blocked_query_preview=guard.blocked_query_preview,
        )

    client = search_client or search_searxng
    all_results: list[dict[str, Any]] = []
    evidence_packets: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings = list(guard.warnings)
    max_results = min(
        int(request.max_results_per_query or 5),
        int(config.limits.get("max_results_per_query") or 5),
    )
    max_snippet_length = int(config.limits.get("max_result_snippet_length") or 1000)

    for query in guard.queries_sent:
        try:
            results = client(
                base_url=str(config.service.get("base_url") or "http://127.0.0.1:8888"),
                search_endpoint=str(config.service.get("search_endpoint") or "/search"),
                query=query,
                max_results=max_results,
                timeout_seconds=int(config.service.get("timeout_seconds") or 10),
                safe_search=(
                    request.safe_search_level
                    if request.safe_search_level in {"strict", "moderate", "off"}
                    else str(config.service.get("safe_search") or "strict")
                ),
                categories=list(config.service.get("categories") or ["general"]),
                language=str(config.service.get("language") or "en"),
            )
        except Exception as exc:
            errors.append(f"SearXNG search failed for one query: {exc}")
            continue

        for result in results[:max_results]:
            if not isinstance(result, dict):
                continue
            normalized = {
                "title": str(result.get("title") or "").strip(),
                "url": str(result.get("url") or "").strip(),
                "snippet": str(result.get("snippet") or "").strip()[:max_snippet_length],
                "source_engine": str(result.get("source_engine") or "").strip(),
                "rank": result.get("rank"),
                "query": query,
            }
            if not normalized["url"]:
                continue
            all_results.append(normalized)
            evidence_packets.append(
                _packet_from_result(
                    request=request,
                    query=query,
                    result=normalized,
                    max_snippet_length=max_snippet_length,
                )
            )

    if evidence_packets:
        status = SearxngWorkerStatus.DEGRADED if errors else SearxngWorkerStatus.COMPLETED
    else:
        status = SearxngWorkerStatus.FAILED if errors else SearxngWorkerStatus.DEGRADED
        if not errors:
            warnings.append("SearXNG returned no usable search results.")

    return SearxngWorkerResult(
        status=status,
        worker_key=request.worker_key,
        worker_used=bool(guard.queries_sent),
        searxng_used=bool(guard.queries_sent),
        request_id=request.request_id,
        ticket_id=request.ticket_id,
        queries_requested=guard.queries_requested,
        queries_sent=guard.queries_sent,
        query_hashes=guard.query_hashes,
        results_considered=all_results,
        evidence_packets=evidence_packets,
        network_access_used=bool(guard.queries_sent),
        page_fetch_used=False,
        private_context_sent=False,
        cloud_search_used=False,
        cloud_model_used=False,
        approval_required=False,
        refusal_reasons=[],
        warnings=warnings,
        errors=errors,
        trace_summary=_trace_summary(
            request,
            status=status,
            queries_sent=guard.queries_sent,
            result_count=len(all_results),
            evidence_packet_count=len(evidence_packets),
        ),
    )


__all__ = ("run_searxng_worker",)
