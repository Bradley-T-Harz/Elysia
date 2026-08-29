from __future__ import annotations

from pathlib import Path

from sandbox.searxng_worker.contract import SearxngWorkerRequest, SearxngWorkerStatus
from sandbox.searxng_worker.worker import run_searxng_worker


def write_config(path: Path, *, enabled: bool) -> Path:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "worker_key: searxng_research_worker",
                "worker_kind: governed_public_web_research_worker",
                "state: configured",
                "contract_doc: docs/research/searxng_worker_contract.md",
                "service:",
                f"  enabled: {'true' if enabled else 'false'}",
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


def make_request(**overrides) -> SearxngWorkerRequest:
    values = {
        "request_id": "req-research",
        "ticket_id": "ticket-research",
        "question": "What helps wetlands remove nitrates?",
        "queries": ["wetland nitrate removal research"],
    }
    values.update(overrides)
    return SearxngWorkerRequest(**values)


def fake_client(**kwargs):
    del kwargs
    return [
        {
            "title": "Wetland nitrate removal",
            "url": "https://example.test/wetlands",
            "snippet": "Constructed wetlands can remove nitrates through plant and microbial processes.",
            "source_engine": "fake",
            "rank": 1,
        }
    ]


def test_disabled_config_returns_unavailable_and_no_network(tmp_path):
    result = run_searxng_worker(
        make_request(),
        config_path=write_config(tmp_path / "searxng_worker.yaml", enabled=False),
        search_client=fake_client,
    )

    assert result.status == SearxngWorkerStatus.UNAVAILABLE
    assert result.worker_used is False
    assert result.searxng_used is False
    assert result.network_access_used is False
    assert result.queries_sent == []


def test_safe_query_with_fake_client_returns_completed(tmp_path):
    result = run_searxng_worker(
        make_request(),
        config_path=write_config(tmp_path / "searxng_worker.yaml", enabled=True),
        search_client=fake_client,
    )

    assert result.status == SearxngWorkerStatus.COMPLETED
    assert result.worker_used is True
    assert result.searxng_used is True
    assert result.network_access_used is True
    assert result.page_fetch_used is False
    assert result.private_context_sent is False
    assert result.cloud_search_used is False
    assert result.cloud_model_used is False
    packet = result.evidence_packets[0]
    assert packet["retrieval_method"] == "searxng_search"
    assert packet["outward_boundary_state"] == "external_boundary_crossed"
    assert packet["page_fetch_used"] is False


def test_risky_request_flags_block_before_client(tmp_path):
    calls = []

    def client(**kwargs):
        calls.append(kwargs)
        return []

    for override in [
        {"private_context_sent": True},
        {"cloud_search_allowed": True},
        {"cloud_model_allowed": True},
        {"page_fetch_allowed": True},
    ]:
        result = run_searxng_worker(
            make_request(**override),
            config_path=write_config(tmp_path / f"{len(calls)}.yaml", enabled=True),
            search_client=client,
        )
        assert result.status == SearxngWorkerStatus.BLOCKED
        assert result.network_access_used is False

    assert calls == []


def test_secret_query_blocked_before_client(tmp_path):
    calls = []

    result = run_searxng_worker(
        make_request(queries=["/home/me/.env api_key token"]),
        config_path=write_config(tmp_path / "searxng_worker.yaml", enabled=True),
        search_client=lambda **kwargs: calls.append(kwargs) or [],
    )

    assert result.status == SearxngWorkerStatus.BLOCKED
    assert result.network_access_used is False
    assert result.queries_sent == []
    assert calls == []


def test_approval_required_query_does_not_call_client_without_token(tmp_path):
    calls = []

    result = run_searxng_worker(
        make_request(queries=["legal strategy for jane@example.com"]),
        config_path=write_config(tmp_path / "searxng_worker.yaml", enabled=True),
        search_client=lambda **kwargs: calls.append(kwargs) or [],
    )

    assert result.status == SearxngWorkerStatus.APPROVAL_REQUIRED
    assert result.approval_required is True
    assert result.network_access_used is False
    assert result.queries_sent == []
    assert calls == []
