from __future__ import annotations

from sandbox.fetch_worker import FetchWorkerRequest, FetchWorkerStatus, run_fetch_worker
from sandbox.fetch_worker.config import load_fetch_worker_config
from sandbox.fetch_worker.url_guard import guard_fetch_url
import sandbox.fetch_worker.url_guard as fetch_url_guard


def test_fetch_url_guard_blocks_loopback():
    config = load_fetch_worker_config()

    result = guard_fetch_url(
        "http://127.0.0.1:8000/private",
        config=config,
        approved_by_user=True,
    )

    assert result.allowed is False
    assert result.approval_required is False
    assert result.refusal_reasons
    assert result.resolved_public_ips == []


def test_fetch_url_guard_blocks_credentials_file_and_documentation_ranges(monkeypatch):
    config = load_fetch_worker_config()
    monkeypatch.setattr(fetch_url_guard, "_resolved_ips", lambda _host: ["192.0.2.10"])
    credentialed = guard_fetch_url("https://user:pass@example.com/private", config=config)
    local_file = guard_fetch_url("file:///home/synthetic/private.txt", config=config)
    documentation = guard_fetch_url("https://example.com/", config=config)
    assert credentialed.allowed is False
    assert local_file.allowed is False
    assert documentation.allowed is False
    assert any("private/local" in reason for reason in documentation.refusal_reasons)


def test_fetch_url_guard_allows_harmless_public_get_without_blanket_approval(monkeypatch):
    config = load_fetch_worker_config()
    monkeypatch.setattr(fetch_url_guard, "_resolved_ips", lambda _host: ["93.184.216.34"])

    result = guard_fetch_url("https://example.com/", config=config)

    assert result.allowed is True
    assert result.approval_required is False
    assert result.url_hash
    assert result.resolved_public_ips == ["93.184.216.34"]


def test_fetch_worker_uses_harmless_public_get_without_blanket_approval(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch_url_guard, "_resolved_ips", lambda _host: ["93.184.216.34"])

    def fake_client(**kwargs):
        calls.append(kwargs)
        return {}

    result = run_fetch_worker(
        FetchWorkerRequest(
            request_id="req_fetch_approval",
            ticket_id="ticket_fetch_approval",
            url="https://example.com/",
        ),
        fetch_client=fake_client,
    )

    assert result.status == FetchWorkerStatus.COMPLETED
    assert result.network_access_used is True
    assert result.page_fetch_used is True
    assert len(calls) == 1


def test_fetch_worker_public_url_returns_evidence_packet(monkeypatch):
    monkeypatch.setattr(fetch_url_guard, "_resolved_ips", lambda _host: ["93.184.216.34"])
    def fake_client(**kwargs):
        assert "allowed_public_ips" in kwargs
        return {
            "status_code": 200,
            "content_type": "text/html",
            "title": "Example",
            "snippet": "Example public page snippet for evidence.",
            "bytes_read": 128,
            "warnings": [],
            "errors": [],
        }

    result = run_fetch_worker(
        FetchWorkerRequest(
            request_id="req_fetch_ok",
            ticket_id="ticket_fetch_ok",
            url="https://example.com/",
        ),
        fetch_client=fake_client,
    )

    assert result.status == FetchWorkerStatus.COMPLETED
    assert result.network_access_used is True
    assert result.page_fetch_used is True
    assert result.private_context_sent is False
    assert result.evidence_packets[0]["retrieval_method"] == "public_page_fetch"
    assert result.evidence_packets[0]["page_fetch_used"] is True
