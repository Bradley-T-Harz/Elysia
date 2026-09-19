from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from app.api import research_service
from app.api.request_trace_service import _REQUEST_TRACE_REGISTRY
from app.api.research_service import (
    WebResearchPort,
    _persist_research_result,
    _record_trace,
    build_research_ticket_from_request,
)
from app.api.schemas.common import EnvelopeStatus
from app.api.schemas.research import ResearchSearchRequest
from app.cognition.evidence_repository import EvidenceRepository
from app.install.paths import resolve_elysia_paths
import sandbox.searxng_worker.client as client_module
from core.evidence_verifier import verify_research_ticket_payload
from sandbox.searxng_worker.client import (
    SearxngProtocolError,
    search_searxng,
)
from sandbox.searxng_worker.contract import (
    SearxngWorkerRequest,
    SearxngWorkerResult,
    SearxngWorkerStatus,
)
from sandbox.searxng_worker.worker import run_searxng_worker


def _config(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "worker_key: searxng_research_worker",
                "worker_kind: governed_public_web_research_worker",
                "state: configured",
                "contract_doc: docs/research/searxng_worker_contract.md",
                "service:",
                "  enabled: true",
                "  base_url: http://127.0.0.1:8888",
                "  search_endpoint: /search",
                "  timeout_seconds: 10",
                "  safe_search: moderate",
                "  language: en",
                "  categories:",
                "    - general",
                "posture:",
                "  public_query_only: true",
                "  private_context_allowed: false",
                "  private_context_sent: false",
                "  cloud_search_allowed: false",
                "  cloud_model_allowed: false",
                "  page_fetch_allowed: false",
                "  network_access_allowed: true",
                "  network_access_scope: worker_public_search_only",
                "  core_network_access_allowed: false",
                "  search_results_first: true",
                "  approval_required_for_sensitive_queries: true",
                "limits:",
                "  max_queries_per_ticket: 3",
                "  max_results_per_query: 5",
                "  max_query_length: 300",
                "  max_total_query_length: 900",
                "  max_result_snippet_length: 1000",
                "blocked_schemes:",
                "  - file",
                "blocked_query_fragments:",
                "  - .env",
                "  - api_key",
                "  - token",
                "  - /home/",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _request(
    queries: list[str] | None = None,
) -> SearxngWorkerRequest:
    return SearxngWorkerRequest(
        request_id="req_truth_semantics",
        ticket_id="ticket_truth_semantics",
        question="Synthetic bounded research question",
        queries=queries or ["synthetic public query"],
    )


def _result(url: str = "https://example.org/source"):
    return [
        {
            "title": "Synthetic source",
            "url": url,
            "snippet": (
                "Synthetic public evidence with enough text "
                "for bounded research verification."
            ),
            "source_engine": "synthetic",
            "rank": 1,
        }
    ]


def _successful_search_envelope(
    payload,
    *,
    evidence_id: str = "evidence_search",
):
    query = payload["queries"][0]
    return {
        "status": "ok",
        "data": {
            "queries_sent": [query],
            "network_access_used": True,
            "worker_summary": {
                "worker_used": True,
                "searxng_used": True,
                "query_outcomes": [
                    {
                        "query": query,
                        "state": "completed",
                        "outward_boundary_state": (
                            "external_boundary_crossed"
                        ),
                        "network_access_used": True,
                        "searxng_used": True,
                    }
                ],
            },
            "durable_research": {
                "session_id": None,
                "evidence_ids": [evidence_id],
            },
            "evidence_packets": [
                {
                    "source_url": "https://agency.gov/report"
                }
            ],
        },
    }


def test_http_error_is_failed_not_unavailable_and_does_not_claim_public_egress(
    tmp_path,
):
    def failing_client(**kwargs):
        raise HTTPError(
            kwargs["base_url"],
            500,
            "synthetic HTTP failure",
            hdrs=None,
            fp=None,
        )

    result = run_searxng_worker(
        _request(),
        config_path=_config(tmp_path / "searxng.yaml"),
        search_client=failing_client,
    )

    assert result.status == SearxngWorkerStatus.FAILED
    assert result.worker_used is True
    assert result.searxng_used is True
    assert result.network_access_used is True
    assert result.queries_sent == []
    assert result.evidence_packets == []

    assert result.query_outcomes == [
        {
            "query": "synthetic public query",
            "state": "failed",
            "outward_boundary_state": "unknown",
            "network_access_used": True,
            "searxng_used": True,
        }
    ]


def test_protocol_error_is_failed_not_unavailable_and_does_not_claim_public_egress(
    tmp_path,
):
    def failing_client(**_kwargs):
        raise SearxngProtocolError(
            "synthetic malformed SearXNG response"
        )

    result = run_searxng_worker(
        _request(),
        config_path=_config(tmp_path / "searxng.yaml"),
        search_client=failing_client,
    )

    assert result.status == SearxngWorkerStatus.FAILED
    assert result.worker_used is True
    assert result.searxng_used is True
    assert result.network_access_used is True
    assert result.queries_sent == []
    assert result.query_outcomes[0]["state"] == "failed"
    assert (
        result.query_outcomes[0]["outward_boundary_state"]
        == "unknown"
    )


def test_actual_client_rejects_malformed_json_as_protocol_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        client_module,
        "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(b"not-json"),
    )

    with pytest.raises(
        SearxngProtocolError,
        match="invalid JSON",
    ):
        search_searxng(
            base_url="http://127.0.0.1:8888",
            search_endpoint="/search",
            query="synthetic",
            max_results=1,
            timeout_seconds=3,
            safe_search="moderate",
            categories=["general"],
            language="en",
        )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"unexpected": []},
        {"results": "not-a-list"},
    ],
)
def test_actual_client_rejects_wrong_json_contract(
    monkeypatch,
    payload,
):
    monkeypatch.setattr(
        client_module,
        "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(
            json.dumps(payload).encode("utf-8")
        ),
    )

    with pytest.raises(SearxngProtocolError):
        search_searxng(
            base_url="http://127.0.0.1:8888",
            search_endpoint="/search",
            query="synthetic",
            max_results=1,
            timeout_seconds=3,
            safe_search="moderate",
            categories=["general"],
            language="en",
        )


def test_client_validation_failure_is_failed_without_network_claim(
    tmp_path,
):
    def invalid_client(**_kwargs):
        raise ValueError(
            "synthetic pre-transport validation failure"
        )

    result = run_searxng_worker(
        _request(),
        config_path=_config(tmp_path / "searxng.yaml"),
        search_client=invalid_client,
    )

    assert result.status == SearxngWorkerStatus.FAILED
    assert result.worker_used is True
    assert result.searxng_used is False
    assert result.network_access_used is False
    assert result.queries_sent == []
    assert (
        result.query_outcomes[0]["outward_boundary_state"]
        == "external_boundary_planned"
    )


def test_first_query_success_later_transport_unavailable_is_degraded(
    tmp_path,
):
    calls = 0

    def mixed_client(**_kwargs):
        nonlocal calls
        calls += 1

        if calls == 1:
            return _result()

        raise ConnectionRefusedError(
            "synthetic later refusal"
        )

    result = run_searxng_worker(
        _request(
            [
                "synthetic first query",
                "synthetic second query",
            ]
        ),
        config_path=_config(tmp_path / "searxng.yaml"),
        search_client=mixed_client,
    )

    assert result.status == SearxngWorkerStatus.DEGRADED
    assert result.worker_used is True
    assert result.searxng_used is True
    assert result.network_access_used is True
    assert result.queries_sent == [
        "synthetic first query"
    ]
    assert [
        item["state"]
        for item in result.query_outcomes
    ] == [
        "completed",
        "unavailable",
    ]
    assert result.evidence_packets


def test_first_query_success_later_protocol_failure_is_degraded(
    tmp_path,
):
    calls = 0

    def mixed_client(**_kwargs):
        nonlocal calls
        calls += 1

        if calls == 1:
            return _result()

        raise SearxngProtocolError(
            "synthetic later protocol failure"
        )

    result = run_searxng_worker(
        _request(
            [
                "synthetic first query",
                "synthetic second query",
            ]
        ),
        config_path=_config(tmp_path / "searxng.yaml"),
        search_client=mixed_client,
    )

    assert result.status == SearxngWorkerStatus.DEGRADED
    assert result.queries_sent == [
        "synthetic first query"
    ]
    assert [
        item["state"]
        for item in result.query_outcomes
    ] == [
        "completed",
        "failed",
    ]
    assert result.evidence_packets


def test_failed_fetch_degrades_parent_and_preserves_search_evidence(
    monkeypatch,
):
    monkeypatch.setattr(
        research_service,
        "internet_master_enabled",
        lambda: True,
    )

    monkeypatch.setattr(
        research_service,
        "_research_controls",
        lambda: ("strict", "manual"),
    )

    def fetch_runner(_payload, **_kwargs):
        return {
            "status": "error",
            "errors": [
                "Synthetic bounded fetch failure."
            ],
            "data": {
                "network_access_used": True,
                "page_fetch_used": True,
                "bytes_read": 0,
                "durable_research": {
                    "evidence_ids": []
                },
            },
        }

    result = WebResearchPort().investigate(
        question="Synthetic fetch failure",
        request_id="req_fetch_failure",
        conversation_id=None,
        project_id=None,
        reasoning_gear="reflex",
        autonomy_level=1,
        search_runner=_successful_search_envelope,
        fetch_runner=fetch_runner,
    )

    assert result["state"] == "degraded"
    assert result["evidence_ids"] == [
        "evidence_search"
    ]
    assert any(
        "Synthetic bounded fetch failure" in error
        for error in result["errors"]
    )


def test_cancellation_after_search_during_fetch_preserves_evidence(
    monkeypatch,
):
    monkeypatch.setattr(
        research_service,
        "internet_master_enabled",
        lambda: True,
    )

    monkeypatch.setattr(
        research_service,
        "_research_controls",
        lambda: ("strict", "manual"),
    )

    cancellation = {"active": False}

    def fetch_runner(_payload, **_kwargs):
        cancellation["active"] = True

        return {
            "status": "error",
            "errors": [
                "Public page fetch was cancelled."
            ],
            "data": {
                "network_access_used": False,
                "page_fetch_used": False,
                "bytes_read": 0,
                "durable_research": {
                    "evidence_ids": []
                },
            },
        }

    result = WebResearchPort().investigate(
        question="Synthetic cancellation",
        request_id="req_fetch_cancel",
        conversation_id=None,
        project_id=None,
        reasoning_gear="reflex",
        autonomy_level=1,
        cancel_check=lambda: cancellation["active"],
        search_runner=_successful_search_envelope,
        fetch_runner=fetch_runner,
    )

    assert result["state"] == "cancelled"
    assert result["evidence_ids"] == [
        "evidence_search"
    ]


def test_degraded_search_quality_closes_durable_session_as_completed(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "XDG_CONFIG_HOME",
        str(tmp_path / "config"),
    )
    monkeypatch.setenv(
        "XDG_DATA_HOME",
        str(tmp_path / "data"),
    )
    monkeypatch.setenv(
        "XDG_STATE_HOME",
        str(tmp_path / "state"),
    )
    monkeypatch.setenv(
        "XDG_CACHE_HOME",
        str(tmp_path / "cache"),
    )

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    monkeypatch.setenv(
        "XDG_RUNTIME_DIR",
        str(runtime_dir),
    )

    request = ResearchSearchRequest(
        request_id="req_durable_degraded",
        question="Synthetic zero-evidence search",
        queries=["synthetic query"],
    )

    worker_result = SearxngWorkerResult(
        status=SearxngWorkerStatus.DEGRADED,
        worker_used=True,
        searxng_used=True,
        request_id=request.request_id,
        ticket_id="ticket_durable_degraded",
        queries_requested=list(request.queries),
        queries_sent=list(request.queries),
        query_outcomes=[
            {
                "query": request.queries[0],
                "state": "completed",
                "outward_boundary_state": (
                    "external_boundary_crossed"
                ),
                "network_access_used": True,
                "searxng_used": True,
            }
        ],
        network_access_used=True,
        warnings=[
            "SearXNG returned no usable search results."
        ],
    )

    persisted = _persist_research_result(
        owner_user_id="user_semantic_test",
        request_model=request,
        worker_result=worker_result,
    )

    assert persisted["status"] == "completed"

    repository = EvidenceRepository(
        paths=resolve_elysia_paths()
    )

    session = repository.get_session(
        "user_semantic_test",
        persisted["session_id"],
    )

    assert session["status"] == "completed"
    assert session["evidence"] == []


@pytest.mark.parametrize(
    (
        "network_used",
        "boundary",
    ),
    [
        (
            False,
            "external_boundary_planned",
        ),
        (
            True,
            "unknown",
        ),
    ],
)
def test_verifier_accepts_truthful_failed_worker_attempt_without_evidence(
    network_used,
    boundary,
):
    result = verify_research_ticket_payload(
        {
            "ticket_id": "ticket_failed_attempt",
            "question": "Synthetic failed search",
            "status": "failed",
            "worker_key": "searxng_research_worker",
            "worker_used": True,
            "live_research_enabled": True,
            "query_execution_allowed": True,
            "retrieval_allowed": False,
            "network_access_used": network_used,
            "live_web_research_used": False,
            "outward_boundary_state": boundary,
            "queries_requested": [
                "synthetic query"
            ],
            "queries_sent": [],
            "evidence_packets": [],
            "errors": [
                "Synthetic bounded-search failure."
            ],
        }
    )

    assert result["verified"] is True


@pytest.mark.parametrize(
    "payload_update",
    [
        {
            "network_access_used": True,
            "outward_boundary_state": (
                "external_boundary_planned"
            ),
        },
        {
            "network_access_used": False,
            "queries_sent": [
                "synthetic query"
            ],
            "outward_boundary_state": (
                "external_boundary_planned"
            ),
        },
    ],
)
def test_verifier_rejects_inconsistent_failed_worker_boundary_truth(
    payload_update,
):
    payload = {
        "ticket_id": "ticket_inconsistent",
        "question": "Synthetic inconsistent search",
        "status": "failed",
        "worker_key": "searxng_research_worker",
        "worker_used": True,
        "live_research_enabled": True,
        "query_execution_allowed": True,
        "retrieval_allowed": False,
        "network_access_used": False,
        "live_web_research_used": False,
        "outward_boundary_state": (
            "external_boundary_planned"
        ),
        "queries_requested": [
            "synthetic query"
        ],
        "queries_sent": [],
        "evidence_packets": [],
        "errors": [
            "Synthetic bounded-search failure."
        ],
    }

    payload.update(payload_update)

    result = verify_research_ticket_payload(
        payload
    )

    assert result["verified"] is False


def test_unknown_boundary_survives_ticket_and_trace_projection():
    request = ResearchSearchRequest(
        request_id="req_unknown_boundary",
        question="Synthetic failed public search",
        queries=["synthetic public query"],
    )

    worker_result = SearxngWorkerResult(
        status=SearxngWorkerStatus.FAILED,
        worker_used=True,
        searxng_used=True,
        request_id=request.request_id,
        ticket_id="ticket_unknown_boundary",
        queries_requested=list(request.queries),
        queries_sent=[],
        query_outcomes=[
            {
                "query": request.queries[0],
                "state": "failed",
                "outward_boundary_state": "unknown",
                "network_access_used": True,
                "searxng_used": True,
            }
        ],
        network_access_used=True,
        errors=[
            "Synthetic protocol failure."
        ],
    )

    ticket = build_research_ticket_from_request(
        request,
        worker_result,
    )

    assert (
        str(
            getattr(
                ticket.outward_boundary_state,
                "value",
                ticket.outward_boundary_state,
            )
        )
        == "unknown"
    )

    _record_trace(
        request_id=request.request_id,
        ticket=ticket,
        worker_result=worker_result,
        envelope_status=EnvelopeStatus.ERROR,
    )

    snapshot = _REQUEST_TRACE_REGISTRY[
        request.request_id
    ]["snapshot"]

    assert (
        snapshot["outward_boundary_state"]
        == "unknown"
    )
    assert snapshot["locality_state"] == "unknown"
