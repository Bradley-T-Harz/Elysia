from __future__ import annotations

from app.api.research_service import run_bounded_public_fetch, run_bounded_public_research
from sandbox.fetch_worker.contract import FetchWorkerResult, FetchWorkerStatus
from sandbox.searxng_worker.contract import SearxngWorkerResult, SearxngWorkerStatus


def completed_worker(request):
    return SearxngWorkerResult(
        status=SearxngWorkerStatus.COMPLETED,
        worker_used=True,
        searxng_used=True,
        request_id=request.request_id,
        ticket_id=request.ticket_id,
        queries_requested=list(request.queries),
        queries_sent=["wetland nitrate removal"],
        query_hashes=["abc123"],
        results_considered=[
            {
                "title": "Wetlands",
                "url": "https://example.test/wetlands",
                "snippet": "Wetlands remove nitrate through microbial processes.",
                "rank": 1,
            }
        ],
        evidence_packets=[
            {
                "source_url": "https://example.test/wetlands",
                "title": "Wetlands",
                "retrieved_at_utc": "2026-05-27T12:00:00Z",
                "snippet": "Wetlands remove nitrate through microbial processes.",
                "claim": "Search result for query 'wetland nitrate removal' may be relevant to: What helps wetlands remove nitrates?",
                "confidence": "low",
                "contradiction_notes": [],
                "source_type": "unknown",
                "retrieval_method": "searxng_search",
                "outward_boundary_state": "external_boundary_crossed",
                "private_context_sent": False,
                "network_access_used": True,
                "page_fetch_used": False,
                "live_web_research_used": True,
                "source_rank": 1,
            }
        ],
        network_access_used=True,
    )


def test_safe_worker_result_becomes_verified_ticket():
    payload = run_bounded_public_research(
        {
            "request_id": "req_research_service_ok",
            "question": "What helps wetlands remove nitrates?",
            "queries": ["wetland nitrate removal"],
        },
        worker_runner=completed_worker,
        internet_enabled_reader=lambda: True,
    )

    assert payload["status"] == "ok"
    data = payload["data"]
    assert data["research_ticket"]["worker_key"] == "searxng_research_worker"
    assert data["research_ticket"]["queries_sent"] == ["wetland nitrate removal"]
    assert data["research_ticket"]["private_context_sent"] is False
    assert data["evidence_verification"]["verified"] is True
    assert data["network_access_used"] is True
    assert data["page_fetch_used"] is False


def test_blocked_worker_result_returns_blocked_truth():
    def blocked_worker(request):
        return SearxngWorkerResult(
            status=SearxngWorkerStatus.BLOCKED,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            queries_requested=list(request.queries),
            query_hashes=["blockedhash"],
            blocked_query_preview="[redacted]",
            refusal_reasons=["Query appears to contain credentials."],
        )

    payload = run_bounded_public_research(
        {
            "request_id": "req_research_service_blocked",
            "question": "Find docs",
            "queries": ["/home/me/.env api_key"],
        },
        worker_runner=blocked_worker,
        internet_enabled_reader=lambda: True,
    )

    assert payload["status"] == "blocked"
    data = payload["data"]
    assert data["queries_sent"] == []
    assert "redacted" in data["blocked_query_preview"]
    assert "/home/" not in data["blocked_query_preview"]
    assert "api_key" not in data["blocked_query_preview"]
    assert data["private_context_sent"] is False
    assert data["network_access_used"] is False


def test_unavailable_worker_result_returns_unavailable_truth():
    def unavailable_worker(request):
        return SearxngWorkerResult(
            status=SearxngWorkerStatus.UNAVAILABLE,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            refusal_reasons=["SearXNG worker service is configured but disabled."],
        )

    payload = run_bounded_public_research(
        {
            "request_id": "req_research_service_unavailable",
            "question": "What helps wetlands remove nitrates?",
            "queries": ["wetland nitrate removal"],
        },
        worker_runner=unavailable_worker,
        internet_enabled_reader=lambda: True,
    )

    assert payload["status"] == "unavailable"
    assert payload["locality"] == "local"
    assert payload["data"]["network_access_used"] is False


def test_approved_fetch_worker_result_becomes_verified_ticket():
    def fetch_worker(request):
        return FetchWorkerResult(
            status=FetchWorkerStatus.COMPLETED,
            worker_used=True,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            requested_url=request.url,
            sanitized_url="https://example.com/",
            url_hash="urlhash",
            title="Example",
            snippet="Example public page snippet for evidence.",
            content_type="text/html",
            status_code=200,
            bytes_read=128,
            evidence_packets=[
                {
                    "source_url": "https://example.com/",
                    "title": "Example",
                    "retrieved_at_utc": "2026-05-31T12:00:00Z",
                    "snippet": "Example public page snippet for evidence.",
                    "claim": "Fetched public page may be relevant to approved URL: https://example.com/",
                    "confidence": "low",
                    "contradiction_notes": [],
                    "source_type": "unknown",
                    "retrieval_method": "public_page_fetch",
                    "outward_boundary_state": "external_boundary_crossed",
                    "private_context_sent": False,
                    "network_access_used": True,
                    "page_fetch_used": True,
                    "live_web_research_used": True,
                }
            ],
            network_access_used=True,
            page_fetch_used=True,
        )

    payload = run_bounded_public_fetch(
        {
            "request_id": "req_fetch_service_ok",
            "question": "Fetch an approved public page.",
            "url": "https://example.com/",
            "approved_by_user": True,
            "approval_reference": "approval",
        },
        worker_runner=fetch_worker,
        internet_enabled_reader=lambda: True,
    )

    assert payload["status"] == "ok"
    data = payload["data"]
    assert data["research_ticket"]["worker_key"] == "bounded_fetch_worker"
    assert data["research_ticket"]["page_fetch_used"] is True
    assert data["evidence_verification"]["verified"] is True
    assert data["network_access_used"] is True
    assert data["private_context_sent"] is False
