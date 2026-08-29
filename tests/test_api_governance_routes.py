from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import app.api.routes.governance as governance_route
from app.api.main import create_app
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from tests.asgi_test_client import ASGITestClient


def _build_governance_envelope_payload(
    *,
    request_id: str = "req_gov_123",
) -> dict:
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version="1.0.0",
        contract_version="phase1-ui-contract-1.0",
        result_type="governance_state",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=TraceSummary(
            route_used="get_governance_state",
            log_written=False,
            journal_written=False,
        ),
        data={
            "governance_state": "live",
            "governance_available": True,
            "governance_note": "Governance truth is visible.",
            "control_count": 12,
        },
    )
    return envelope.to_payload()


def _make_client() -> ASGITestClient:
    return ASGITestClient(create_app())


def test_get_governance_state_is_mounted_and_returns_service_payload_unchanged(
    monkeypatch,
):
    expected_payload = _build_governance_envelope_payload(
        request_id="req_gov_sync_001",
    )

    monkeypatch.setattr(
        governance_route,
        "_load_governance_service",
        lambda: SimpleNamespace(get_governance_state=lambda: expected_payload),
    )

    with _make_client() as client:
        response = client.get("/governance/state")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_get_governance_state_supports_async_service_callables(monkeypatch):
    expected_payload = _build_governance_envelope_payload(
        request_id="req_gov_async_001",
    )

    async def get_governance_state():
        return expected_payload

    monkeypatch.setattr(
        governance_route,
        "_load_governance_service",
        lambda: SimpleNamespace(get_governance_state=get_governance_state),
    )

    with _make_client() as client:
        response = client.get("/governance/state")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_get_governance_state_returns_503_when_service_import_fails(monkeypatch):
    def unavailable_governance_service():
        raise HTTPException(
            status_code=503,
            detail="Governance service is not available yet: import failed",
        )

    monkeypatch.setattr(
        governance_route,
        "_load_governance_service",
        unavailable_governance_service,
    )

    with _make_client() as client:
        response = client.get("/governance/state")

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert (
        "Governance service is not available yet: import failed"
        in payload["errors"][0]
    )


def test_get_governance_state_returns_503_when_required_service_callable_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        governance_route,
        "_load_governance_service",
        lambda: SimpleNamespace(),
    )

    with _make_client() as client:
        response = client.get("/governance/state")

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert (
        "Required service function 'get_governance_state' is not available yet."
        in payload["errors"][0]
    )


def test_get_governance_state_returns_500_when_service_returns_non_mapping(
    monkeypatch,
):
    monkeypatch.setattr(
        governance_route,
        "_load_governance_service",
        lambda: SimpleNamespace(get_governance_state=lambda: "not-a-dict"),
    )

    with _make_client() as client:
        response = client.get("/governance/state")

    assert response.status_code == 500

    payload = response.json()
    assert payload["status"] == "error"
    assert (
        "Service function 'get_governance_state' returned a non-dictionary response."
        in payload["errors"][0]
    )


def test_get_governance_state_preserves_key_envelope_fields_from_service(monkeypatch):
    expected_payload = _build_governance_envelope_payload(
        request_id="req_gov_fields_001",
    )

    monkeypatch.setattr(
        governance_route,
        "_load_governance_service",
        lambda: SimpleNamespace(get_governance_state=lambda: expected_payload),
    )

    with _make_client() as client:
        response = client.get("/governance/state")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["request_id"] == "req_gov_fields_001"
    assert payload["api_version"] == "1.0.0"
    assert payload["contract_version"] == "phase1-ui-contract-1.0"
    assert payload["result_type"] == "governance_state"
    assert payload["capability_state"] == "live"
    assert payload["locality"] == "local"
    assert payload["approval_state"] == "not_needed"
    assert payload["trace_summary"]["route_used"] == "get_governance_state"
    assert payload["data"]["governance_state"] == "live"
    assert payload["data"]["governance_available"] is True
