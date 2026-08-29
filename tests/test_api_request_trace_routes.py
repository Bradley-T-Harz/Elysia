from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
import httpx

import app.api.routes.request_trace as request_trace_route
import app.api.routes.requests as requests_route
from app.api.request_trace_service import (
    get_request_summary,
    start_request_trace,
    update_request_trace_ledger_snapshot,
)
from app.api.main import create_app
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope


def _get(path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://elysia.local",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def _build_request_summary_envelope_payload(
    *,
    request_id: str = "req_summary_001",
    status: EnvelopeStatus = EnvelopeStatus.OK,
    capability_state: CapabilityState = CapabilityState.LIVE,
    locality: LocalityState = LocalityState.LOCAL,
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    data: dict | None = None,
) -> dict:
    envelope = build_response_envelope(
        status=status,
        request_id=request_id,
        api_version="1.0.0",
        contract_version="phase1-ui-contract-1.0",
        result_type="request_summary",
        capability_state=capability_state,
        locality=locality,
        approval_state=approval_state,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=TraceSummary(
            route_used="requests.summary",
            log_written=False,
            journal_written=False,
        ),
        data=data
        or {
            "request_id": "req_real_001",
            "request_state": "completed",
            "request_type": "local_runtime_request",
            "summary_text": "Local runtime request completed its current governed path.",
            "created_at_utc": "2026-04-18T06:00:00Z",
            "updated_at_utc": "2026-04-18T06:00:10Z",
            "approval_required": False,
            "approval_state": "not_needed",
            "locality": "local",
            "selected_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "mistral-small-3.1",
            "used_fallback": False,
            "resolution_status": None,
            "can_proceed": True,
            "related_conversation_id": "conv_001",
            "related_project_id": "project_001",
            "notes": ["Compact request summary available."],
        },
    )
    return envelope.to_payload()


def _build_request_trace_envelope_payload(
    *,
    request_id: str = "req_trace_001",
    status: EnvelopeStatus = EnvelopeStatus.OK,
    capability_state: CapabilityState = CapabilityState.LIVE,
    locality: LocalityState = LocalityState.LOCAL,
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    data: dict | None = None,
) -> dict:
    envelope = build_response_envelope(
        status=status,
        request_id=request_id,
        api_version="1.0.0",
        contract_version="phase1-ui-contract-1.0",
        result_type="request_trace",
        capability_state=capability_state,
        locality=locality,
        approval_state=approval_state,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=TraceSummary(
            route_used="request_trace.get_request_trace",
            selected_role="primary_general",
            selected_runtime="ollama",
            selected_model_runtime_tag="mistral-small-3.1",
            used_fallback=False,
            log_written=False,
            journal_written=False,
        ),
        data=data
        or {
            "request_id": "req_real_trace_001",
            "request_status": "completed",
            "current_phase": "completed",
            "current_phase_label": "Completed",
            "current_phase_detail": "The governed request completed its current bridge-visible path.",
            "created_at_utc": "2026-04-18T06:00:00Z",
            "updated_at_utc": "2026-04-18T06:00:20Z",
            "completed_at_utc": "2026-04-18T06:00:20Z",
            "trace_entries": [],
            "snapshot": {
                "route_used": "runtime_bridge.send_chat_request",
                "ui_surface": "conversation",
                "selected_mode": "default",
                "selected_role": "primary_general",
                "selected_runtime": "ollama",
                "selected_model_runtime_tag": "mistral-small-3.1",
                "locality_state": "local",
                "approval_state": "not_needed",
                "approval_needed": False,
                "used_fallback": False,
                "memory_classes": ["working", "conversation"],
                "skill_name": "tutoring.tutoring_helper",
                "tool_name": None,
                "app_name": None,
                "worker_name": None,
                "related_conversation_id": "conv_001",
                "related_project_id": "project_001",
                "errors": [],
                "warnings": [],
            },
        },
    )
    return envelope.to_payload()


def test_get_request_summary_is_mounted_and_passes_sync_service_payload_unchanged(
    monkeypatch,
):
    expected_payload = _build_request_summary_envelope_payload(
        request_id="req_summary_sync_001",
    )

    monkeypatch.setattr(
        requests_route,
        "_load_request_trace_service",
        lambda: SimpleNamespace(
            get_request_summary=lambda request_payload: expected_payload
        ),
    )

    response = _get("/requests/req_real_001/summary")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_get_request_summary_supports_async_service_callables(monkeypatch):
    expected_payload = _build_request_summary_envelope_payload(
        request_id="req_summary_async_001",
    )

    async def get_request_summary(request_payload):
        del request_payload
        return expected_payload

    monkeypatch.setattr(
        requests_route,
        "_load_request_trace_service",
        lambda: SimpleNamespace(get_request_summary=get_request_summary),
    )

    response = _get("/requests/req_async_001/summary")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_get_request_summary_rejects_blank_request_id(monkeypatch):
    monkeypatch.setattr(
        requests_route,
        "_load_request_trace_service",
        lambda: SimpleNamespace(
            get_request_summary=lambda request_payload: _build_request_summary_envelope_payload()
        ),
    )

    response = _get("/requests/%20/summary")

    assert response.status_code == 400

    payload = response.json()
    assert payload["status"] == "error"
    assert (
        "Path parameter 'request_id' is required and must be a non-empty string."
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 400


def test_get_request_summary_forwards_optional_query_flags_into_service_payload(
    monkeypatch,
):
    captured: dict[str, dict] = {}
    expected_payload = _build_request_summary_envelope_payload(
        request_id="req_summary_query_001",
    )

    def get_request_summary(request_payload):
        captured["request_payload"] = dict(request_payload)
        return expected_payload

    monkeypatch.setattr(
        requests_route,
        "_load_request_trace_service",
        lambda: SimpleNamespace(get_request_summary=get_request_summary),
    )

    response = _get(
        "/requests/req_query_001/summary?include_notes=true&include_resolution=false"
    )

    assert response.status_code == 200
    assert response.json() == expected_payload
    assert captured["request_payload"] == {
        "request_id": "req_query_001",
        "include_notes": True,
        "include_resolution": False,
    }


def test_get_request_summary_returns_503_when_service_import_fails(monkeypatch):
    def unavailable_request_trace_service():
        raise HTTPException(
            status_code=503,
            detail="Request trace service is not available yet: import failed",
        )

    monkeypatch.setattr(
        requests_route,
        "_load_request_trace_service",
        unavailable_request_trace_service,
    )

    response = _get("/requests/req_unavailable_001/summary")

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert (
        "Request trace service is not available yet: import failed"
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 503


def test_get_request_summary_returns_503_when_required_service_callable_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        requests_route,
        "_load_request_trace_service",
        lambda: SimpleNamespace(),
    )

    response = _get("/requests/req_missing_callable_001/summary")

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert (
        "Request trace service does not expose get_request_summary yet."
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 503


def test_get_request_summary_returns_500_when_service_returns_non_mapping(monkeypatch):
    monkeypatch.setattr(
        requests_route,
        "_load_request_trace_service",
        lambda: SimpleNamespace(get_request_summary=lambda request_payload: "not-a-dict"),
    )

    response = _get("/requests/req_bad_result_001/summary")

    assert response.status_code == 500

    payload = response.json()
    assert payload["status"] == "error"
    assert (
        "Request trace service returned a non-dictionary response."
        in payload["errors"][0]
    )
    assert payload["data"]["http_status_code"] == 500


def test_get_request_summary_passes_through_blocked_unknown_request_envelope_unchanged(
    monkeypatch,
):
    expected_payload = _build_request_summary_envelope_payload(
        request_id="req_summary_blocked_001",
        status=EnvelopeStatus.BLOCKED,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.UNKNOWN,
        approval_state=ApprovalState.UNKNOWN,
        errors=["No real governed request exists for this request_id."],
        data={
            "request_id": "req_unknown_001",
            "request_state": "unknown",
            "request_type": "unknown",
            "summary_text": "Requested summary could not be produced because the request_id is not valid or not currently known.",
            "created_at_utc": None,
            "updated_at_utc": None,
            "approval_required": False,
            "approval_state": "unknown",
            "locality": "unknown",
            "selected_role": None,
            "selected_runtime": None,
            "selected_model_runtime_tag": None,
            "used_fallback": False,
            "resolution_status": None,
            "can_proceed": False,
            "related_conversation_id": None,
            "related_project_id": None,
            "notes": [
                "No real governed request exists for this request_id.",
                "Current bridge-phase request tracking is intentionally modest.",
            ],
        },
    )

    monkeypatch.setattr(
        requests_route,
        "_load_request_trace_service",
        lambda: SimpleNamespace(
            get_request_summary=lambda request_payload: expected_payload
        ),
    )

    response = _get("/requests/req_unknown_001/summary")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_get_request_trace_rejects_blank_request_id(monkeypatch):
    monkeypatch.setattr(
        request_trace_route,
        "get_request_trace_record",
        lambda request_id: None,
    )

    response = _get("/request-trace/%20")

    assert response.status_code == 400

    payload = response.json()
    assert payload["status"] == "error"
    assert "request_id path parameter must not be empty." in payload["errors"][0]
    assert payload["data"]["http_status_code"] == 400


def test_get_request_trace_returns_pending_startup_fallback_for_req_like_unknown_id(
    monkeypatch,
):
    monkeypatch.setattr(
        request_trace_route,
        "get_request_trace_record",
        lambda request_id: None,
    )

    response = _get("/request-trace/req_abcd1234")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["capability_state"] == "live"
    assert payload["warnings"] == [
        "Live trace record has not appeared yet. Polling may still be correct while the governed request starts."
    ]
    assert payload["data"]["request_id"] == "req_abcd1234"
    assert payload["data"]["request_status"] == "pending_startup"
    assert payload["data"]["current_phase"] == "waiting_for_trace_startup"
    assert payload["data"]["trace_entries"] == []
    snapshot = payload["data"]["snapshot"]
    assert snapshot["files_attached_count"] == 0
    assert snapshot["files_attached"] == []
    assert snapshot["tools_available_count"] == 0
    assert snapshot["tools_used_count"] == 0
    assert snapshot["tools_available"] == []
    assert snapshot["tools_used"] == []
    assert snapshot["artifact_count"] == 0
    assert snapshot["artifacts"] == []
    assert snapshot["repo_context_files"] == []
    assert snapshot["patch_plan_files"] == []
    assert snapshot["mutated_files"] is False
    assert snapshot["shell_used"] is False
    assert snapshot["git_mutation_used"] is False
    assert snapshot["external_worker_used"] is False


def test_get_request_trace_returns_unknown_fallback_for_non_bridge_like_id(monkeypatch):
    monkeypatch.setattr(
        request_trace_route,
        "get_request_trace_record",
        lambda request_id: None,
    )

    response = _get("/request-trace/not-a-real-request")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["capability_state"] == "unknown"
    assert payload["warnings"] == [
        "No live request trace is currently known for this request_id."
    ]
    assert payload["data"]["request_id"] == "not-a-real-request"
    assert payload["data"]["request_status"] == "unknown"
    assert payload["data"]["current_phase"] == "unknown_request_id"
    assert payload["data"]["trace_entries"] == []


def test_get_request_trace_sanitizes_live_record_and_maps_degraded_status(monkeypatch):
    trace_record = {
        "request_id": "req_trace_live_001",
        "request_status": "degraded",
        "current_phase": "completed_degraded",
        "current_phase_label": "Completed in degraded path",
        "current_phase_detail": "The governed request completed, but the visible path was degraded.",
        "created_at_utc": "2026-04-18T06:00:00Z",
        "updated_at_utc": "2026-04-18T06:00:15Z",
        "completed_at_utc": "2026-04-18T06:00:15Z",
        "trace_entries": [
            {
                "entry_id": "trace_001",
                "request_id": "req_trace_live_001",
                "phase": "invoking_runtime",
                "label": "Invoking governed runtime",
                "detail": "The request is now inside the local runtime path.",
                "timestamp_utc": "2026-04-18T06:00:03Z",
                "selected_mode": "default",
                "selected_role": "primary_general",
                "selected_runtime": "ollama",
                "selected_model_runtime_tag": "mistral-small-3.1",
                "locality_state": "crossed_boundary",
                "approval_state": "needed",
                "used_fallback": True,
                "memory_classes": ["working", "conversation", ""],
                "skill_name": "tutoring.tutoring_helper",
                "tool_name": None,
                "app_name": None,
                "worker_name": None,
                "execution_tool_kind": "math_executor",
                "execution_status": "completed",
                "execution_operation": "evaluate_expression",
                "execution_summary": "result 4",
                "secret_field": "should_not_surface",
            }
        ],
        "snapshot": {
            "route_used": "runtime_bridge.send_chat_request",
            "ui_surface": "quick_invoke",
            "selected_mode": "default",
            "selected_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "mistral-small-3.1",
            "locality_state": "crossed_boundary",
            "approval_state": "needed",
            "approval_needed": True,
            "used_fallback": True,
            "memory_classes": ["working", "conversation", ""],
            "skill_name": "tutoring.tutoring_helper",
            "tool_name": None,
            "app_name": None,
            "worker_name": None,
            "execution_tool_kind": "math_executor",
            "execution_status": "completed",
            "execution_operation": "evaluate_expression",
            "execution_summary": "result 4",
            "files_attached_count": 1,
            "files_attached": [
                {
                    "file_id": "file_001",
                    "file_name": "notes.md",
                    "file_kind": "markdown",
                    "status": "ready",
                    "summary": "Selected notes.",
                    "source_path": "/home/private/notes.md",
                    "raw_file_contents": "secret contents",
                }
            ],
            "tools_available_count": 1,
            "tools_used_count": 1,
            "tools_available": [
                {
                    "tool_key": "math_executor",
                    "state": "available",
                    "available": True,
                    "prompt": "raw prompt should not surface",
                }
            ],
            "tools_used": [
                {
                    "tool_key": "math_executor",
                    "state": "used",
                    "used": True,
                    "summary": "Evaluated bounded math.",
                    "input_count": 1,
                    "output_count": 1,
                    "hidden_reasoning": "should_not_surface",
                    "payload": {"raw": "blob"},
                }
            ],
            "artifact_count": 1,
            "artifacts": [
                {
                    "artifact_id": "artifact_001",
                    "kind": "data_summary",
                    "title": "Summary",
                    "summary": "Compact artifact summary.",
                    "artifact_path": "/tmp/private/artifact.json",
                    "source_path": "/home/private/source.csv",
                    "svg_text": "<svg>raw</svg>",
                    "payload": {"rows": []},
                }
            ],
            "repo_context_status": "used",
            "repo_context_file_count": 1,
            "repo_context_files": ["core/example.py"],
            "patch_plan_status": "created",
            "patch_plan_file_count": 1,
            "patch_plan_files": ["core/example.py"],
            "mutated_files": False,
            "shell_used": False,
            "git_mutation_used": False,
            "external_worker_used": False,
            "related_conversation_id": "conv_trace_001",
            "related_project_id": "project_trace_001",
            "errors": ["One bounded degraded error"],
            "warnings": ["One bounded degraded warning"],
            "hidden_reasoning": "should_not_surface",
        },
    }

    monkeypatch.setattr(
        request_trace_route,
        "get_request_trace_record",
        lambda request_id: trace_record,
    )

    response = _get("/request-trace/req_trace_live_001")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["capability_state"] == "degraded"
    assert payload["locality"] == "crossed_boundary"
    assert payload["approval_state"] == "needed"

    data = payload["data"]
    assert data["request_id"] == "req_trace_live_001"
    assert data["request_status"] == "degraded"
    assert data["snapshot"]["route_used"] == "runtime_bridge.send_chat_request"
    assert data["snapshot"]["selected_role"] == "primary_general"
    assert data["snapshot"]["used_fallback"] is True
    assert data["snapshot"]["errors"] == ["One bounded degraded error"]
    assert data["snapshot"]["warnings"] == ["One bounded degraded warning"]
    assert "hidden_reasoning" not in data["snapshot"]
    assert data["snapshot"]["execution_tool_kind"] == "math_executor"
    assert data["snapshot"]["execution_status"] == "completed"
    assert data["snapshot"]["execution_operation"] == "evaluate_expression"
    assert data["snapshot"]["execution_summary"] == "result 4"
    assert data["snapshot"]["files_attached"][0]["file_name"] == "notes.md"
    assert "source_path" not in data["snapshot"]["files_attached"][0]
    assert "raw_file_contents" not in data["snapshot"]["files_attached"][0]
    assert data["snapshot"]["tools_used"][0]["tool_key"] == "math_executor"
    assert "hidden_reasoning" not in data["snapshot"]["tools_used"][0]
    assert "payload" not in data["snapshot"]["tools_used"][0]
    assert data["snapshot"]["artifacts"][0]["artifact_id"] == "artifact_001"
    assert "artifact_path" not in data["snapshot"]["artifacts"][0]
    assert "source_path" not in data["snapshot"]["artifacts"][0]
    assert "svg_text" not in data["snapshot"]["artifacts"][0]
    assert "payload" not in data["snapshot"]["artifacts"][0]
    assert data["snapshot"]["repo_context_files"] == ["core/example.py"]
    assert data["snapshot"]["patch_plan_files"] == ["core/example.py"]

    entry = data["trace_entries"][0]
    assert entry["entry_id"] == "trace_001"
    assert entry["selected_runtime"] == "ollama"
    assert entry["used_fallback"] is True
    assert entry["memory_classes"] == ["working", "conversation"]
    assert entry["execution_tool_kind"] == "math_executor"
    assert entry["execution_status"] == "completed"
    assert entry["execution_operation"] == "evaluate_expression"
    assert entry["execution_summary"] == "result 4"
    assert "secret_field" not in entry


def test_update_request_trace_ledger_snapshot_sanitizes_compact_fields():
    request_id = "req_ledger_service_001"
    start_request_trace(request_id=request_id, route_used="tests")

    record = update_request_trace_ledger_snapshot(
        request_id=request_id,
        files_attached=[
            {
                "file_id": "file_001",
                "file_name": "notes.md",
                "file_kind": "markdown",
                "status": "ready",
                "summary": "Selected notes.",
                "parser_used": "markdown_text_parser",
                "chunks_created_count": 2,
                "chunks_used_count": 1,
                "memory_promotion_allowed": False,
                "outward_sharing_allowed": False,
                "trust_zone": "user_selected_local_file",
                "source_path": "/home/private/notes.md",
                "raw_file_contents": "secret contents",
            }
        ],
        files_used_count=1,
        file_chunks_used_count=1,
        file_parsers_used=["markdown_text_parser"],
        file_memory_promotion=False,
        file_outward_sharing=False,
        tools_available=[
            {
                "tool_key": "repo_context",
                "state": "available",
                "available": True,
                "prompt": "raw prompt should not surface",
            }
        ],
        tools_used=[
            {
                "tool_key": "code_patch_plan",
                "state": "used",
                "used": True,
                "summary": "Patch plan created.",
                "payload": {"raw": "blob"},
                "hidden_reasoning": "should_not_surface",
            }
        ],
        artifacts=[
            {
                "artifact_id": "artifact_001",
                "kind": "data_summary",
                "title": "Summary",
                "artifact_path": "/tmp/private/artifact.json",
                "svg_text": "<svg>raw</svg>",
                "payload": {"rows": []},
            }
        ],
        repo_context_status="used",
        repo_context_files=["core/example.py"],
        patch_plan_status="created",
        patch_plan_files=["core/example.py"],
        mutated_files=False,
        shell_used=False,
        git_mutation_used=False,
        external_worker_used=True,
    )

    snapshot = record["snapshot"]

    assert snapshot["files_attached_count"] == 1
    assert snapshot["files_attached"][0]["file_name"] == "notes.md"
    assert snapshot["files_attached"][0]["parser_used"] == "markdown_text_parser"
    assert snapshot["files_attached"][0]["chunks_used_count"] == 1
    assert "source_path" not in snapshot["files_attached"][0]
    assert "raw_file_contents" not in snapshot["files_attached"][0]
    assert snapshot["files_used_count"] == 1
    assert snapshot["file_chunks_used_count"] == 1
    assert snapshot["file_parsers_used"] == ["markdown_text_parser"]
    assert snapshot["file_memory_promotion"] is False
    assert snapshot["file_outward_sharing"] is False
    assert snapshot["tools_available_count"] == 1
    assert snapshot["tools_used_count"] == 1
    assert snapshot["tools_used"][0]["tool_key"] == "code_patch_plan"
    assert "payload" not in snapshot["tools_used"][0]
    assert "hidden_reasoning" not in snapshot["tools_used"][0]
    assert snapshot["artifact_count"] == 1
    assert snapshot["artifacts"][0]["artifact_id"] == "artifact_001"
    assert "artifact_path" not in snapshot["artifacts"][0]
    assert "svg_text" not in snapshot["artifacts"][0]
    assert "payload" not in snapshot["artifacts"][0]
    assert snapshot["external_worker_used"] is True


def test_route_sanitizer_strips_raw_ledger_fields_without_test_client():
    payload = request_trace_route._sanitize_trace_payload(
        "req_direct_sanitize_001",
        {
            "request_id": "req_direct_sanitize_001",
            "request_status": "completed",
            "current_phase": "completed",
            "current_phase_label": "Completed",
            "current_phase_detail": "Done.",
            "created_at_utc": "2026-04-18T06:00:00Z",
            "updated_at_utc": "2026-04-18T06:00:01Z",
            "completed_at_utc": "2026-04-18T06:00:01Z",
            "trace_entries": [
                {
                    "entry_id": "trace_direct_001",
                    "request_id": "req_direct_sanitize_001",
                    "phase": "executing",
                    "label": "Executing bounded tool",
                    "execution_tool_kind": "math_executor",
                    "execution_status": "completed",
                    "execution_operation": "evaluate_expression",
                    "execution_summary": "result 4",
                    "secret_field": "should_not_surface",
                }
            ],
            "snapshot": {
                "files_attached": [
                    {
                        "file_id": "file_001",
                        "file_name": "notes.md",
                        "parser_used": "markdown_text_parser",
                        "chunks_created_count": 2,
                        "chunks_used_count": 1,
                        "memory_promotion_allowed": False,
                        "outward_sharing_allowed": False,
                        "trust_zone": "user_selected_local_file",
                        "raw_file_contents": "secret",
                    }
                ],
                "mode_profile_key": "writer",
                "mode_profile_label": "Writer",
                "mode_profile_used": True,
                "mode_profile_effects": ["tone:polished"],
                "authority_granted_by_mode": False,
                "files_used_count": 1,
                "file_chunks_used_count": 1,
                "file_parsers_used": ["markdown_text_parser"],
                "file_memory_promotion": False,
                "file_outward_sharing": False,
                "tools_used": [
                    {
                        "tool_key": "math_executor",
                        "state": "used",
                        "used": True,
                        "hidden_reasoning": "should_not_surface",
                    }
                ],
                "artifacts": [
                    {
                        "artifact_id": "artifact_001",
                        "title": "Summary",
                        "artifact_path": "/tmp/private/artifact.json",
                        "svg_text": "<svg>raw</svg>",
                    }
                ],
            },
        },
    )

    entry = payload["trace_entries"][0]
    snapshot = payload["snapshot"]

    assert entry["execution_tool_kind"] == "math_executor"
    assert "secret_field" not in entry
    assert snapshot["files_attached"][0]["file_name"] == "notes.md"
    assert snapshot["files_attached"][0]["parser_used"] == "markdown_text_parser"
    assert snapshot["files_attached"][0]["chunks_used_count"] == 1
    assert "raw_file_contents" not in snapshot["files_attached"][0]
    assert snapshot["mode_profile_key"] == "writer"
    assert snapshot["mode_profile_used"] is True
    assert snapshot["authority_granted_by_mode"] is False
    assert snapshot["files_used_count"] == 1
    assert snapshot["file_chunks_used_count"] == 1
    assert snapshot["file_parsers_used"] == ["markdown_text_parser"]
    assert snapshot["file_memory_promotion"] is False
    assert snapshot["file_outward_sharing"] is False
    assert snapshot["tools_used"][0]["tool_key"] == "math_executor"
    assert "hidden_reasoning" not in snapshot["tools_used"][0]
    assert snapshot["artifacts"][0]["artifact_id"] == "artifact_001"
    assert "artifact_path" not in snapshot["artifacts"][0]
    assert "svg_text" not in snapshot["artifacts"][0]


def test_request_summary_includes_compact_ledger_truth_from_trace_record():
    request_id = "req_ledger_summary_001"
    start_request_trace(request_id=request_id, route_used="tests")
    update_request_trace_ledger_snapshot(
        request_id=request_id,
        files_attached=[
            {
                "file_id": "file_001",
                "file_name": "notes.md",
                "parser_used": "markdown_text_parser",
                "chunks_used_count": 1,
            }
        ],
        files_used_count=1,
        file_chunks_used_count=1,
        file_parsers_used=["markdown_text_parser"],
        file_memory_promotion=False,
        file_outward_sharing=False,
        tools_used=[
            {
                "tool_key": "code_patch_plan",
                "state": "used",
                "used": True,
            }
        ],
        artifacts=[
            {
                "artifact_id": "artifact_001",
                "kind": "data_summary",
                "title": "Summary",
            }
        ],
        repo_context_status="used",
        repo_context_files=["core/example.py"],
        patch_plan_status="created",
        patch_plan_files=["core/example.py"],
    )

    payload = get_request_summary({"request_id": request_id})
    data = payload["data"]

    assert payload["status"] == "ok"
    assert data["files_attached_count"] == 1
    assert data["files_attached"][0]["file_name"] == "notes.md"
    assert data["files_attached"][0]["parser_used"] == "markdown_text_parser"
    assert data["files_used_count"] == 1
    assert data["file_chunks_used_count"] == 1
    assert data["file_parsers_used"] == ["markdown_text_parser"]
    assert data["file_memory_promotion"] is False
    assert data["file_outward_sharing"] is False
    assert data["tools_used_count"] == 1
    assert data["tools_used"][0]["tool_key"] == "code_patch_plan"
    assert data["artifact_count"] == 1
    assert data["artifacts"][0]["artifact_id"] == "artifact_001"
    assert data["repo_context_status"] == "used"
    assert data["repo_context_files"] == ["core/example.py"]
    assert data["patch_plan_status"] == "created"
    assert data["patch_plan_files"] == ["core/example.py"]
    assert any("Files attached: 1." == note for note in data["notes"])
    assert any("Tools used: code_patch_plan." == note for note in data["notes"])


def test_get_request_trace_returns_error_envelope_when_lookup_fails_unexpectedly(
    monkeypatch,
):
    def broken_trace_lookup(request_id):
        del request_id
        raise RuntimeError("trace registry exploded")

    monkeypatch.setattr(
        request_trace_route,
        "get_request_trace_record",
        broken_trace_lookup,
    )

    response = _get("/request-trace/req_lookup_boom_001")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "error"
    assert payload["result_type"] == "request_trace"
    assert payload["capability_state"] == "unknown"
    assert payload["locality"] == "unknown"
    assert payload["approval_state"] == "unknown"
    assert (
        "Request trace lookup failed unexpectedly: trace registry exploded"
        in payload["errors"][0]
    )
    assert payload["data"] == {}
