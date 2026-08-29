from __future__ import annotations

import app.api.status_service as status_service


def _approval_needed_snapshot() -> dict:
    return {
        "request_id": "req_packet4_approval_needed",
        "timestamp_utc": "2026-04-27T08:42:29Z",
        "session_state": {"active_mode": "writer"},
        "response": {
            "selected_model_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "mistral-small3.1:24b",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "invocation_status": "ok",
        },
        "policy_review": {
            "approval_required": True,
        },
        "internal_result": {
            "stayed_local": True,
            "error": "",
        },
        "model_routing": {
            "stayed_local": True,
        },
    }


def test_runtime_status_treats_approval_needed_as_gated_not_blocked(monkeypatch):
    monkeypatch.setattr(
        status_service,
        "_get_runtime_import_truth",
        lambda: (True, ""),
    )
    monkeypatch.setattr(
        status_service,
        "_load_runtime_bridge_snapshot",
        _approval_needed_snapshot,
    )

    payload = status_service.get_runtime_status()

    assert payload["status"] == "ok"
    assert payload["approval_state"] == "needed"
    assert payload["data"]["approval_needed"] is True
    assert payload["data"]["last_invocation_status"] == "ok"
    assert payload["data"]["runtime_state"] != "blocked"
    assert any(
        "awaiting approval" in warning
        for warning in payload["warnings"]
    )


def test_invoker_status_treats_approval_needed_as_gated_not_blocked(monkeypatch):
    monkeypatch.setattr(
        status_service,
        "_get_runtime_import_truth",
        lambda: (True, ""),
    )
    monkeypatch.setattr(
        status_service,
        "_load_runtime_bridge_snapshot",
        _approval_needed_snapshot,
    )

    payload = status_service.get_invoker_status()

    assert payload["status"] == "ok"
    assert payload["approval_state"] == "needed"
    assert payload["data"]["approval_needed"] is True
    assert payload["data"]["last_invocation_status"] == "ok"
    assert payload["data"]["invoker_state"] == "approval_needed"
    assert any(
        "awaiting approval" in warning
        for warning in payload["warnings"]
    )
