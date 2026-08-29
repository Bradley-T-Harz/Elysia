from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import app.api.routes.status as status_route
import app.api.status_service as status_service
from core.math_executor import is_sympy_available
from app.api.main import create_app
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from tests.asgi_test_client import ASGITestClient


def _make_client() -> ASGITestClient:
    return ASGITestClient(create_app())


def _build_status_envelope_payload(
    *,
    request_id: str,
    result_type: str,
    capability_state: CapabilityState = CapabilityState.LIVE,
    locality: LocalityState = LocalityState.LOCAL,
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    data: dict | None = None,
) -> dict:
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version="1.0.0",
        contract_version="phase1-ui-contract-1.0",
        result_type=result_type,
        capability_state=capability_state,
        locality=locality,
        approval_state=approval_state,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=TraceSummary(
            route_used=f"status.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data or {},
    )
    return envelope.to_payload()


def test_get_runtime_status_passes_sync_service_payload_unchanged(monkeypatch):
    expected_payload = _build_status_envelope_payload(
        request_id="req_status_runtime_001",
        result_type="runtime_status",
        data={
            "runtime_state": "idle",
            "runtime_available": True,
            "active_mode": "default",
            "selected_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "mistral-small-3.1",
            "stayed_local": True,
            "used_fallback": False,
            "fallback_from": None,
            "fallback_to": None,
            "approval_needed": False,
            "last_request_id": "req_last_runtime_001",
            "last_invocation_status": "ok",
            "last_error": None,
            "last_updated_utc": "2026-04-18T06:00:00Z",
        },
    )

    monkeypatch.setattr(
        status_route,
        "_load_status_service",
        lambda: SimpleNamespace(get_runtime_status=lambda: expected_payload),
    )

    with _make_client() as client:
        response = client.get("/status/runtime")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_get_health_status_supports_async_service_callables(monkeypatch):
    expected_payload = _build_status_envelope_payload(
        request_id="req_status_health_001",
        result_type="health_status",
        capability_state=CapabilityState.DEGRADED,
        warnings=["Local model service is not reachable."],
        data={
            "health_state": "degraded",
            "healthy": False,
            "startup_state": "warming",
            "api_reachable": True,
            "runtime_reachable": True,
            "ollama_reachable": False,
            "config_loadable": True,
            "logging_writable": True,
            "journaling_writable": True,
            "memory_path_available": True,
            "last_health_check_utc": "2026-04-18T06:00:00Z",
            "health_notes": ["Local model service is not reachable."],
            "subsystems": {
                "api": {"state": "healthy", "healthy": True, "note": ""},
                "runtime": {"state": "healthy", "healthy": True, "note": ""},
                "ollama": {
                    "state": "unavailable",
                    "healthy": False,
                    "note": "Local model service is not reachable.",
                },
                "config": {"state": "healthy", "healthy": True, "note": ""},
                "logging": {"state": "healthy", "healthy": True, "note": ""},
                "journaling": {"state": "healthy", "healthy": True, "note": ""},
                "memory": {"state": "healthy", "healthy": True, "note": ""},
            },
        },
    )

    async def get_health_status():
        return expected_payload

    monkeypatch.setattr(
        status_route,
        "_load_status_service",
        lambda: SimpleNamespace(get_health_status=get_health_status),
    )

    with _make_client() as client:
        response = client.get("/status/health")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_health_status_includes_searxng_loopback_truth(monkeypatch):
    monkeypatch.setattr(status_service, "_ping_ollama", lambda: True)
    monkeypatch.setattr(status_service, "_ping_searxng_loopback", lambda: False)

    payload = status_service.get_health_status()

    assert payload["result_type"] == "health_status"
    assert payload["data"]["searxng_reachable"] is False
    assert payload["data"]["subsystems"]["searxng"]["healthy"] is False
    assert "no search query was sent" in payload["data"]["subsystems"]["searxng"]["note"]


def test_get_invoker_status_passes_sync_service_payload_unchanged(monkeypatch):
    expected_payload = _build_status_envelope_payload(
        request_id="req_status_invoker_001",
        result_type="invoker_status",
        approval_state=ApprovalState.NEEDED,
        data={
            "invoker_state": "blocked",
            "invoker_available": True,
            "selected_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "mistral-small-3.1",
            "stayed_local": True,
            "used_fallback": False,
            "fallback_from": None,
            "fallback_to": None,
            "approval_needed": True,
            "last_request_id": "req_last_invoker_001",
            "last_invocation_status": "blocked",
            "last_error": None,
            "last_updated_utc": "2026-04-18T06:00:00Z",
        },
    )

    monkeypatch.setattr(
        status_route,
        "_load_status_service",
        lambda: SimpleNamespace(get_invoker_status=lambda: expected_payload),
    )

    with _make_client() as client:
        response = client.get("/status/invoker")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_get_capabilities_status_uses_capability_service_payload_unchanged(monkeypatch):
    expected_payload = _build_status_envelope_payload(
        request_id="req_status_capabilities_001",
        result_type="capability_manifest",
        data={
            "capability_catalog_state": "live",
            "capability_count": 2,
            "last_updated_utc": "2026-04-18T06:00:00Z",
            "capability_groups": ["core_chat", "status_surfaces"],
            "capabilities": [
                {
                    "capability_key": "chat_send",
                    "display_name": "Chat send",
                    "group": "core_chat",
                    "state": "live",
                    "summary": "Main governed body-facing chat submission path.",
                    "locality": "local",
                    "approval_state": "not_needed",
                    "read_only": False,
                    "ui_surfaces": ["conversations_room", "quick_invoke"],
                    "supporting_endpoint": "/chat/send",
                    "notes": [],
                },
                {
                    "capability_key": "status_runtime",
                    "display_name": "Runtime status",
                    "group": "status_surfaces",
                    "state": "live",
                    "summary": "Runtime truth surface for active role, runtime, locality, and fallback state.",
                    "locality": "local",
                    "approval_state": "not_needed",
                    "read_only": True,
                    "ui_surfaces": ["bottom_status_bar", "right_drawer"],
                    "supporting_endpoint": "/status/runtime",
                    "notes": [],
                },
            ],
        },
    )

    monkeypatch.setattr(
        status_route,
        "_load_capability_service",
        lambda: SimpleNamespace(get_capabilities_status=lambda: expected_payload),
    )

    with _make_client() as client:
        response = client.get("/status/capabilities")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_status_routes_return_503_when_status_service_import_fails(monkeypatch):
    def unavailable_status_service():
        raise HTTPException(
            status_code=503,
            detail="Status service is not available yet: import failed",
        )

    monkeypatch.setattr(
        status_route,
        "_load_status_service",
        unavailable_status_service,
    )

    with _make_client() as client:
        response = client.get("/status/runtime")

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert (
        "Status service is not available yet: import failed"
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 503


def test_capabilities_route_returns_503_when_capability_service_import_fails(monkeypatch):
    def unavailable_capability_service():
        raise HTTPException(
            status_code=503,
            detail="Capability service is not available yet: import failed",
        )

    monkeypatch.setattr(
        status_route,
        "_load_capability_service",
        unavailable_capability_service,
    )

    with _make_client() as client:
        response = client.get("/status/capabilities")

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert (
        "Capability service is not available yet: import failed"
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 503


def test_status_routes_return_503_when_required_service_callable_is_missing(monkeypatch):
    monkeypatch.setattr(
        status_route,
        "_load_status_service",
        lambda: SimpleNamespace(),
    )

    with _make_client() as client:
        response = client.get("/status/health")

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert (
        "Required service function 'get_health_status' is not available yet."
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 503


def test_capabilities_route_returns_503_when_required_service_callable_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        status_route,
        "_load_capability_service",
        lambda: SimpleNamespace(),
    )

    with _make_client() as client:
        response = client.get("/status/capabilities")

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert (
        "Required service function 'get_capabilities_status' is not available yet."
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 503


def test_status_routes_return_500_when_service_returns_non_mapping(monkeypatch):
    monkeypatch.setattr(
        status_route,
        "_load_status_service",
        lambda: SimpleNamespace(get_runtime_status=lambda: "not-a-dict"),
    )

    with _make_client() as client:
        response = client.get("/status/runtime")

    assert response.status_code == 500

    payload = response.json()
    assert payload["status"] == "error"
    assert (
        "Service function 'get_runtime_status' returned a non-dictionary response."
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 500


def test_live_capability_manifest_names_part3_organs_with_current_truth():
    with _make_client() as client:
        response = client.get("/status/capabilities")

    assert response.status_code == 200

    payload = response.json()
    capabilities = {
        entry["capability_key"]: entry
        for entry in payload["data"]["capabilities"]
    }

    expected_capability_keys = {
        "file_context_retrieval",
        "identity_account",
        "coder_mode",
        "mode_profiles",
        "repo_context",
        "patch_review",
        "patch_application",
        "focused_test_execution",
        "aider_worker",
        "evidence_packets",
        "artifact_outputs",
        "tool_ledger",
    }
    expected_research_keys = {
        "bounded_public_web_research",
        "searxng_research_worker",
        "bounded_public_page_fetch",
    }

    assert expected_capability_keys.issubset(set(capabilities))
    assert expected_research_keys.issubset(set(capabilities))

    file_ingestion = capabilities["file_ingestion"]
    try:
        import docx  # noqa: F401
        import openpyxl  # noqa: F401

        try:
            import pypdf  # noqa: F401
        except Exception:
            import pdfplumber  # noqa: F401

        expected_file_ingestion_state = "live"
    except Exception:
        expected_file_ingestion_state = "degraded"

    assert file_ingestion["state"] == expected_file_ingestion_state
    assert file_ingestion["locality"] == "local"
    assert file_ingestion["approval_state"] == "not_needed"
    assert file_ingestion["read_only"] is False
    assert file_ingestion["supporting_endpoint"] == "/files/attach"
    file_ingestion_notes = " ".join(file_ingestion["notes"])

    assert "TXT/Markdown/JSON/saved HTML/PDF/DOCX" in file_ingestion["summary"]
    assert "CSV/XLSX" in file_ingestion["summary"]
    assert "PDF text extraction is dependency-gated" in file_ingestion_notes
    assert "DOCX text extraction is dependency-gated" in file_ingestion_notes
    assert "scripts are not executed" in file_ingestion_notes
    assert "links/resources are not fetched" in file_ingestion_notes
    assert "bounded data inputs" in file_ingestion_notes
    assert "not promoted into memory" in file_ingestion_notes
    assert "not shared outward" in file_ingestion_notes
    assert "No cloud parsing" in file_ingestion_notes

    math_execution = capabilities["math_execution"]
    expected_math_state = "live" if is_sympy_available() else "degraded"
    math_notes = " ".join(math_execution["notes"])

    assert math_execution["state"] == expected_math_state
    assert math_execution["locality"] == "local"
    assert math_execution["approval_state"] == "not_needed"
    assert math_execution["read_only"] is False
    assert math_execution["supporting_endpoint"] == "/execution/math"
    assert "symbolic/numeric math execution" in math_execution["summary"]
    assert "SymPy" in math_notes
    assert "not arbitrary Python" in math_notes
    assert "shell execution" in math_notes
    assert "web access" in math_notes
    assert "file mutation" in math_notes

    data_execution = capabilities["data_execution"]
    data_notes = " ".join(data_execution["notes"])

    try:
        import openpyxl  # noqa: F401

        expected_data_execution_state = "live"
    except Exception:
        expected_data_execution_state = "degraded"

    assert data_execution["state"] == expected_data_execution_state
    assert data_execution["locality"] == "local"
    assert data_execution["approval_state"] == "not_needed"
    assert data_execution["read_only"] is True
    assert data_execution["supporting_endpoint"] == "/execution/data"
    assert "CSV/XLSX" in data_execution["summary"]
    assert "CSV" in data_notes
    assert "read-only" in data_notes
    assert "XLSX" in data_notes
    assert "openpyxl" in data_notes
    assert "arbitrary Python" in data_notes
    assert "shell execution" in data_notes
    assert "web access" in data_notes
    assert "file mutation" in data_notes
    assert "memory promotion" in data_notes

    file_context_retrieval = capabilities["file_context_retrieval"]
    file_context_notes = " ".join(file_context_retrieval["notes"])

    assert file_context_retrieval["state"] == "live"
    assert file_context_retrieval["locality"] == "local"
    assert file_context_retrieval["approval_state"] == "not_needed"
    assert file_context_retrieval["read_only"] is True
    assert file_context_retrieval["supporting_endpoint"] == "/files/{file_id}/context-summary"
    assert "bounded local request context" in file_context_retrieval["summary"]
    assert "not memory" in file_context_notes
    assert "memory_promotion_allowed remains false" in file_context_notes
    assert "not shared outward" in file_context_notes
    assert "not be sent to SearXNG" in file_context_notes
    assert "not raw absolute source paths" in file_context_notes

    identity_account = capabilities["identity_account"]
    identity_account_notes = " ".join(identity_account["notes"])
    assert identity_account["state"] == "live"
    assert identity_account["locality"] == "local"
    assert identity_account["approval_state"] == "not_needed"
    assert identity_account["read_only"] is False
    assert identity_account["supporting_endpoint"] == "/account/state"
    assert "Sealed local account" in identity_account_notes
    assert "not normal Memory" in identity_account_notes
    assert "Runtime receives only username/name" in identity_account_notes
    assert "Password hashes" in identity_account_notes

    mode_profiles = capabilities["mode_profiles"]
    mode_profile_notes = " ".join(mode_profiles["notes"])
    assert mode_profiles["state"] == "live"
    assert mode_profiles["locality"] == "local"
    assert mode_profiles["approval_state"] == "not_needed"
    assert mode_profiles["read_only"] is True
    assert "Mode profiles define posture" in mode_profile_notes
    assert "do not grant tools" in mode_profile_notes

    coder_mode = capabilities["coder_mode"]
    coder_notes = " ".join(coder_mode["notes"])
    assert coder_mode["state"] == "live"
    assert coder_mode["approval_state"] == "needed"
    assert coder_mode["read_only"] is True
    assert "does not grant mutation" in coder_notes

    repo_context = capabilities["repo_context"]
    repo_notes = " ".join(repo_context["notes"])
    assert repo_context["state"] == "live"
    assert repo_context["locality"] == "local"
    assert repo_context["approval_state"] == "needed"
    assert "Read-only selected-repo" in repo_notes
    assert "no mutation" in repo_notes

    patch_review = capabilities["patch_review"]
    patch_notes = " ".join(patch_review["notes"])
    assert patch_review["state"] == "live"
    assert patch_review["approval_state"] == "needed"
    assert patch_review["read_only"] is True
    assert "Proposal-only patch planning" in patch_notes
    assert "Patch application is not live" in patch_notes

    patch_application = capabilities["patch_application"]
    patch_application_notes = " ".join(patch_application["notes"])
    assert patch_application["state"] == "live"
    assert patch_application["approval_state"] == "needed"
    assert patch_application["read_only"] is False
    assert "approval-gated" in patch_application_notes.lower()
    assert "does not grant shell" in patch_application_notes

    focused_test_execution = capabilities["focused_test_execution"]
    focused_notes = " ".join(focused_test_execution["notes"])
    assert focused_test_execution["state"] == "live"
    assert focused_test_execution["approval_state"] == "needed"
    assert "shell=False" in focused_notes

    aider_worker = capabilities["aider_worker"]
    aider_notes = " ".join(aider_worker["notes"])
    assert aider_worker["state"] == "degraded"
    assert aider_worker["approval_state"] == "needed"
    assert aider_worker["read_only"] is True
    assert "dry-run validation skeleton" in aider_notes
    assert "subprocess invocation is not live" in aider_notes

    evidence_notes = " ".join(capabilities["evidence_packets"]["notes"])
    assert capabilities["evidence_packets"]["state"] == "live"
    assert "schemas and verifier exist" in evidence_notes
    assert "Search snippets are evidence candidates" in evidence_notes

    artifact_outputs = capabilities["artifact_outputs"]
    artifact_notes = " ".join(artifact_outputs["notes"])
    assert artifact_outputs["state"] == "live"
    assert "Artifacts are local outputs" in artifact_notes
    assert "do not become memory by default" in artifact_notes

    tool_ledger = capabilities["tool_ledger"]
    tool_ledger_notes = " ".join(tool_ledger["notes"])
    assert tool_ledger["state"] == "live"
    assert "Compact request ledger" in tool_ledger_notes
    assert "Raw logs" in tool_ledger_notes

    assert capabilities["file_ingestion"]["approval_state"] == "not_needed"
    assert capabilities["math_execution"]["approval_state"] == "not_needed"
    assert capabilities["data_execution"]["approval_state"] == "not_needed"
    assert capabilities["coder_mode"]["approval_state"] == "needed"
    assert capabilities["bounded_public_web_research"]["approval_state"] == "not_needed"
    assert capabilities["bounded_public_page_fetch"]["approval_state"] == "needed"
    research_notes = " ".join(capabilities["bounded_public_web_research"]["notes"])
    assert "local SearXNG worker" in research_notes
    assert "external public web" in research_notes
    assert "Private context is blocked" in research_notes
    fetch_notes = " ".join(capabilities["bounded_public_page_fetch"]["notes"])
    assert "approval-gated" in fetch_notes
    assert "browser automation" in fetch_notes
