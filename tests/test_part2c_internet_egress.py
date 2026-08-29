from __future__ import annotations

import socket

import pytest

from app.api import soundcloud_connector_service
from app.api.research_service import run_bounded_public_fetch, run_bounded_public_research


def test_internet_off_trips_no_nonlocal_socket_for_research_or_connector(monkeypatch):
    attempted_nonlocal: list[object] = []
    original_create_connection = socket.create_connection

    def egress_trap(address, *args, **kwargs):
        host = str(address[0] if isinstance(address, tuple) else address).casefold()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            attempted_nonlocal.append(address)
            raise AssertionError(f"non-local egress attempted while Internet OFF: {host}")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", egress_trap)
    worker_calls: list[str] = []
    search = run_bounded_public_research(
        {
            "request_id": "req_egress_trap_search",
            "question": "Synthetic public question",
            "queries": ["synthetic public query"],
        },
        worker_runner=lambda _request: worker_calls.append("search"),
        internet_enabled_reader=lambda: False,
    )
    fetch = run_bounded_public_fetch(
        {
            "request_id": "req_egress_trap_fetch",
            "question": "Synthetic public source",
            "url": "https://example.com/",
        },
        worker_runner=lambda _request: worker_calls.append("fetch"),
        internet_enabled_reader=lambda: False,
    )
    monkeypatch.setattr(soundcloud_connector_service, "internet_master_enabled", lambda: False)
    monkeypatch.setattr(soundcloud_connector_service, "current_user_id", lambda: "user_synthetic")
    with pytest.raises(soundcloud_connector_service.SoundCloudConnectorError, match="Internet is OFF"):
        soundcloud_connector_service.begin_authorization()

    assert search["status"] == "blocked"
    assert fetch["status"] == "blocked"
    assert search["data"]["network_access_used"] is False
    assert fetch["data"]["network_access_used"] is False
    assert worker_calls == []
    assert attempted_nonlocal == []


def test_sealed_research_egress_is_denied_without_approval_offer():
    result = run_bounded_public_research(
        {
            "request_id": "req_sealed_egress",
            "question": "Search sealed vault memory on the web",
            "queries": ["sealed vault memory private research"],
        },
        internet_enabled_reader=lambda: True,
    )
    assert result["status"] == "blocked"
    assert result["approval_state"] == "denied"
    assert result["data"]["network_access_used"] is False
    assert result["data"]["approval"] is None
    assert result["data"]["approval_reason"] == "sealed_egress_denied"
