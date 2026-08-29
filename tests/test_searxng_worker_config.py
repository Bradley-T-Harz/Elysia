from __future__ import annotations

from pathlib import Path

import pytest

from sandbox.searxng_worker.config import (
    is_loopback_base_url,
    load_searxng_worker_config,
    validate_searxng_worker_config,
)


def test_loads_config_defaults(tmp_path: Path):
    config = load_searxng_worker_config(
        "config/workers/searxng_worker.yaml",
        local_override_path=tmp_path / "absent.yaml",
    )

    assert config.worker_key == "searxng_research_worker"
    assert config.service["enabled"] is False
    assert config.service["base_url"] == "http://127.0.0.1:8888"
    assert config.posture["private_context_allowed"] is False
    assert config.posture["cloud_search_allowed"] is False
    assert config.posture["cloud_model_allowed"] is False
    assert config.posture["page_fetch_allowed"] is False
    assert config.limits["max_queries_per_ticket"] == 3
    assert config.limits["max_results_per_query"] == 5
    assert validate_searxng_worker_config(config) == []


def test_loopback_url_validation_rejects_non_loopback():
    assert is_loopback_base_url("http://127.0.0.1:8888") is True
    assert is_loopback_base_url("http://localhost:8888") is True
    assert is_loopback_base_url("http://0.0.0.0:8888") is False
    assert is_loopback_base_url("https://search.example.com") is False
    assert is_loopback_base_url("file:///tmp/search") is False


def test_explicit_local_override_enables_only_loopback_service(tmp_path: Path):
    override = tmp_path / "searxng.yaml"
    override.write_text(
        "version: 1\nservice:\n  enabled: true\n  base_url: http://127.0.0.1:8888\n",
        encoding="utf-8",
    )
    config = load_searxng_worker_config(
        "config/workers/searxng_worker.yaml",
        local_override_path=override,
    )
    assert config.service["enabled"] is True
    assert config.service["base_url"] == "http://127.0.0.1:8888"
    assert validate_searxng_worker_config(config) == []


def test_local_override_rejects_non_loopback_or_extra_authority(tmp_path: Path):
    override = tmp_path / "searxng.yaml"
    override.write_text(
        "version: 1\nservice:\n  enabled: true\n  base_url: https://search.example.com\n  private_context_allowed: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported fields"):
        load_searxng_worker_config(
            "config/workers/searxng_worker.yaml",
            local_override_path=override,
        )


def test_validate_rejects_unsafe_config(tmp_path: Path):
    config_path = tmp_path / "searxng_worker.yaml"
    config_path.write_text(
        "\n".join(
            [
                "version: 1",
                "worker_key: searxng_research_worker",
                "worker_kind: governed_public_web_research_worker",
                "state: configured",
                "contract_doc: docs/research/searxng_worker_contract.md",
                "service:",
                "  enabled: true",
                "  base_url: http://0.0.0.0:8888",
                "  search_endpoint: /search",
                "posture:",
                "  public_query_only: true",
                "  private_context_allowed: true",
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
                "  max_queries_per_ticket: 4",
                "  max_results_per_query: 6",
                "blocked_schemes:",
                "  - file",
            ]
        ),
        encoding="utf-8",
    )

    config = load_searxng_worker_config(config_path)
    reasons = validate_searxng_worker_config(config)

    assert any("base_url must be loopback" in reason for reason in reasons)
    assert any("private_context_allowed" in reason for reason in reasons)
    assert any("max_queries_per_ticket" in reason for reason in reasons)
    assert any("max_results_per_query" in reason for reason in reasons)
