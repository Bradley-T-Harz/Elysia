from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import app.api.research_service as research_service
from app.api.routes.research import fetch_bounded_public_page, search_bounded_public_research
from sandbox.searxng_worker.contract import SearxngWorkerResult, SearxngWorkerStatus
from sandbox.fetch_worker.contract import FetchWorkerResult, FetchWorkerStatus


def test_post_research_search_rejects_bad_body():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(search_bounded_public_research(["not", "object"]))

    assert exc.value.status_code == 400
    assert "JSON object" in exc.value.detail


def test_post_research_fetch_rejects_bad_body():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fetch_bounded_public_page(["not", "object"]))

    assert exc.value.status_code == 400
    assert "JSON object" in exc.value.detail


def test_post_research_search_is_blocked_by_default_internet_master():
    payload = asyncio.run(
        search_bounded_public_research(
            {
                "request_id": "req_api_research_unavailable",
                "question": "What helps wetlands remove nitrates?",
                "queries": ["wetland nitrate removal"],
            }
        )
    )

    assert payload["status"] == "blocked"
    assert payload["result_type"] == "bounded_public_research"
    assert payload["data"]["network_access_used"] is False
    assert payload["data"]["private_context_sent"] is False
    assert payload["data"]["internet_master_enabled"] is False


def test_post_research_search_blocks_unsafe_query_before_network(monkeypatch):
    def fake_enabled_worker(request):
        return SearxngWorkerResult(
            status=SearxngWorkerStatus.BLOCKED,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            queries_requested=list(request.queries),
            query_hashes=["hash"],
            blocked_query_preview="[redacted]",
            refusal_reasons=["Query appears to contain credentials."],
        )

    monkeypatch.setattr(research_service, "run_searxng_worker", fake_enabled_worker)
    monkeypatch.setattr(research_service, "internet_master_enabled", lambda: True)

    payload = asyncio.run(
        search_bounded_public_research(
            {
                "request_id": "req_api_research_blocked",
                "question": "Find docs",
                "queries": ["/home/me/.env api_key"],
            }
        )
    )

    assert payload["status"] == "blocked"
    assert payload["data"]["queries_sent"] == []
    assert payload["data"]["network_access_used"] is False


def test_post_research_fetch_allows_harmless_public_get_without_blanket_approval(monkeypatch):
    monkeypatch.setattr(research_service, "internet_master_enabled", lambda: True)
    monkeypatch.setattr(
        research_service,
        "run_fetch_worker",
        lambda request: FetchWorkerResult(
            status=FetchWorkerStatus.COMPLETED,
            worker_used=True,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            requested_url=request.url,
            sanitized_url=request.url,
            url_hash="public-url-hash",
            title="Example",
            snippet="Bounded public evidence.",
            content_type="text/html",
            status_code=200,
            bytes_read=128,
            evidence_packets=[
                {
                    "source_url": request.url,
                    "title": "Example",
                    "retrieved_at_utc": "2026-08-22T00:00:00Z",
                    "snippet": "Bounded public evidence.",
                    "claim": "Example is a bounded public source.",
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
        ),
    )
    payload = asyncio.run(
        fetch_bounded_public_page(
            {
                "request_id": "req_api_fetch_approval",
                "question": "Fetch approved public source.",
                "url": "https://example.com/",
            }
        )
    )

    assert payload["status"] in {"ok", "degraded"}
    assert payload["result_type"] == "bounded_public_fetch"
    assert payload["approval_state"] == "not_needed"
    assert payload["data"]["network_access_used"] is True
    assert payload["data"]["page_fetch_used"] is True
