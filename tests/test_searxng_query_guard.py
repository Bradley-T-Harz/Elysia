from __future__ import annotations

from sandbox.searxng_worker.config import load_searxng_worker_config
from sandbox.searxng_worker.query_guard import guard_public_queries


def config():
    return load_searxng_worker_config("config/workers/searxng_worker.yaml")


def test_safe_public_query_allowed():
    result = guard_public_queries(["wetland restoration nitrate removal"], config=config())

    assert result.allowed is True
    assert result.approval_required is False
    assert result.queries_sent == ["wetland restoration nitrate removal"]
    assert len(result.query_hashes) == 1


def test_empty_query_blocked():
    result = guard_public_queries(["   "], config=config())

    assert result.allowed is False
    assert result.queries_sent == []
    assert any("non-empty" in reason for reason in result.refusal_reasons)


def test_too_many_queries_blocked():
    result = guard_public_queries(["one", "two", "three", "four"], config=config())

    assert result.allowed is False
    assert result.queries_sent == []
    assert any("Query count exceeds" in reason for reason in result.refusal_reasons)


def test_secret_and_private_path_queries_blocked_with_redacted_preview():
    result = guard_public_queries(
        ["find docs for /home/me/project/.env api_key token"],
        config=config(),
    )

    assert result.allowed is False
    assert result.queries_sent == []
    assert result.blocked_query_preview
    assert "/home/" not in result.blocked_query_preview
    assert "api_key" not in result.blocked_query_preview.lower()
    assert any("credential" in reason.lower() or "private" in reason.lower() for reason in result.refusal_reasons)


def test_email_phone_and_sensitive_topics_require_approval():
    result = guard_public_queries(
        ["legal strategy for jane@example.com 303-555-1212"],
        config=config(),
    )

    assert result.allowed is False
    assert result.approval_required is True
    assert result.queries_sent == []
    assert "jane@example.com" not in result.blocked_query_preview
    assert "303-555-1212" not in result.blocked_query_preview


def test_only_service_validated_exact_approval_allows_sensitive_query():
    arbitrary = guard_public_queries(
        ["legal strategy climate policy public briefing"],
        config=config(),
        approval_token="approved",
    )
    assert arbitrary.allowed is False
    assert arbitrary.approval_required is True

    result = guard_public_queries(
        ["legal strategy climate policy public briefing"],
        config=config(),
        exact_approval_validated=True,
    )

    assert result.allowed is True
    assert result.queries_sent == ["legal strategy climate policy public briefing"]
    assert result.warnings
