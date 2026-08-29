from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import app.api.routes.chat as chat_route
from app.api import runtime_bridge
from app.api.conversation_service import ConversationServiceError
import core.runtime as runtime
from core.repo_context_gatherer import RepoContextResult, RepoContextStatus
from app.api.schemas.artifacts import (
    ArtifactKind,
    ArtifactMemoryPosture,
    ArtifactSummary,
)
from app.api.schemas.chat import (
    ChatInvocationStatus,
    ChatResponseSource,
    ChatSendRequest,
    ChatSendResponseData,
)
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope


class DirectChatRouteResponse:
    def __init__(self, *, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class DirectChatRouteClient:
    """
    Tiny in-process client for chat-route unit tests.

    Starlette's TestClient currently hangs in this environment before these
    route tests can assert anything. This keeps the suite focused on the chat
    route module and its structured envelope behavior without crossing the
    blocking ASGI harness.
    """

    def post(self, path: str, *, json: Any) -> DirectChatRouteResponse:
        assert path == "/chat/send"

        try:
            payload = asyncio.run(chat_route.send_chat(json))
        except chat_route.HTTPException as exc:
            return _build_http_exception_response(exc)
        except Exception:
            envelope = build_response_envelope(
                status=EnvelopeStatus.ERROR,
                request_id="req_route_test_error",
                api_version="1.0.0",
                contract_version="phase1-ui-contract-1.0",
                result_type="bridge_error",
                capability_state=CapabilityState.UNKNOWN,
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.UNKNOWN,
                warnings=[],
                errors=["Local API bridge encountered an unexpected error."],
                trace_summary=TraceSummary(
                    route_used="unhandled_exception_handler",
                    log_written=False,
                    journal_written=False,
                ),
                data={
                    "path": path,
                    "method": "POST",
                },
            )
            return DirectChatRouteResponse(
                status_code=500,
                payload=envelope.to_payload(),
            )

        return DirectChatRouteResponse(status_code=200, payload=payload)


def _build_http_exception_response(
    exc: chat_route.HTTPException,
) -> DirectChatRouteResponse:
    status = EnvelopeStatus.ERROR
    approval_state = ApprovalState.UNKNOWN
    capability_state = CapabilityState.UNKNOWN

    if exc.status_code == 403:
        status = EnvelopeStatus.BLOCKED
        approval_state = ApprovalState.DENIED
    elif exc.status_code == 503:
        status = EnvelopeStatus.UNAVAILABLE
        capability_state = CapabilityState.UNAVAILABLE

    envelope = build_response_envelope(
        status=status,
        request_id="req_route_test_http_error",
        api_version="1.0.0",
        contract_version="phase1-ui-contract-1.0",
        result_type="http_error",
        capability_state=capability_state,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=[],
        errors=[str(exc.detail)],
        trace_summary=TraceSummary(
            route_used="http_exception_handler",
            log_written=False,
            journal_written=False,
        ),
        data={
            "http_status_code": exc.status_code,
        },
    )
    return DirectChatRouteResponse(
        status_code=exc.status_code,
        payload=envelope.to_payload(),
    )


def _build_chat_envelope_payload(
    *,
    request_id: str = "req_bridge_123",
    conversation_id: str | None = None,
    project_id: str | None = None,
    status: EnvelopeStatus = EnvelopeStatus.OK,
    capability_state: CapabilityState = CapabilityState.LIVE,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    data_execution: dict | None = None,
    repo_context: dict | None = None,
    code_patch_plan: dict | None = None,
    aider_worker: dict | None = None,
    artifacts: list | None = None,
) -> dict:
    chat_data = ChatSendResponseData(
        user_message="Explain derivatives step by step.",
        response_text="Here is a careful local answer.",
        response_source=ChatResponseSource.LIVE_INVOKER,
        invocation_status=ChatInvocationStatus.OK,
        selected_model_role="primary_general",
        selected_runtime="ollama",
        selected_model_runtime_tag="mistral-small-3.1",
        used_fallback=False,
        fallback_from=None,
        fallback_to=None,
        caveats=[],
        approval_needed=False,
        approval_token=None,
        conversation_id=conversation_id,
        project_id=project_id,
        data_execution=data_execution,
        repo_context=repo_context,
        code_patch_plan=code_patch_plan,
        aider_worker=aider_worker,
        artifacts=artifacts or [],
    )

    envelope = build_response_envelope(
        status=status,
        request_id=request_id,
        api_version="1.0.0",
        contract_version="phase1-ui-contract-1.0",
        result_type="chat_response",
        capability_state=capability_state,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=TraceSummary(
            route_used="runtime_bridge.send_chat_request",
            selected_role="primary_general",
            selected_runtime="ollama",
            selected_model_runtime_tag="mistral-small-3.1",
            used_fallback=False,
            log_written=False,
            journal_written=False,
        ),
        data=chat_data,
    )
    return envelope.to_payload()


def _fake_runtime_repo_context_result() -> RepoContextResult:
    return RepoContextResult(
        ok=True,
        status=RepoContextStatus.COMPLETED,
        repo_key="elysia",
        repo_label="Elysia local repository",
        repo_root="/project/Elysia",
        trust_zone="project_local",
        appears_git_repo=True,
        current_branch="main",
        git_head_read=True,
        changed_files_live=False,
        changed_files_note="Git status detection is not live in repo context v0.",
        important_top_level_files=["README.md"],
        top_level_directories=["app", "core", "tests"],
        safe_tree_entries=["core/runtime.py", "tests/test_api_chat_routes.py"],
        language_hints=["Python"],
        framework_hints=["FastAPI local API bridge", "Pytest backend tests"],
        test_command_hints=["./scripts/test_backend.sh tests/test_api_chat_routes.py -q"],
        boundary_notes=[
            "Read-only local repo context v0.",
            "No shell commands were run.",
            "No network access was used.",
            "No files were mutated.",
        ],
    )


def _install_runtime_bridge_live_path_mocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_bridge,
        "_safe_trace_call",
        lambda action_name, func, **kwargs: None,
    )
    monkeypatch.setattr(
        runtime,
        "write_runtime_log",
        lambda payload: "logs/runtime/test-runtime.jsonl",
    )
    monkeypatch.setattr(
        runtime,
        "write_session_journal_entry",
        lambda payload, journal_policy: {
            "status": "skipped_for_test",
            "path": "",
            "written": False,
        },
    )
    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: {
            "request_summary": message,
            "retrieved_memory_count": 0,
            "retrieval_mode": "none",
        },
    )
    monkeypatch.setattr(
        runtime,
        "gather_repo_context",
        lambda repo_key="elysia": _fake_runtime_repo_context_result(),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        lambda **kwargs: _fake_live_path_invoker_result(kwargs),
    )
    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(send_chat_request=runtime_bridge.send_chat_request),
    )


def _fake_live_path_invoker_result(kwargs: dict[str, Any]) -> dict[str, Any]:
    is_coding = kwargs.get("task_type") == "coding"
    return {
        "status": "ok",
        "allowed": True,
        "stayed_local": True,
        "selected_role": "primary_code" if is_coding else "primary_general",
        "selected_runtime": "ollama",
        "selected_model_runtime_tag": (
            "fake-local-code-model" if is_coding else "fake-local-general-model"
        ),
        "used_fallback": False,
        "fallback_from": "",
        "fallback_to": "",
        "prompt_source": "test_api_chat_routes_live_path",
        "response_text": "Generic model text that should be overridden by structured coder truth.",
        "error": "",
        "block_reasons": [],
        "unmet_requirements": [],
        "latency_ms": 0,
        "provider_metadata": {"mocked": True},
        "note": "Fake invoker used by API chat route live-path tests.",
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> DirectChatRouteClient:
    async def direct_mock_threadpool(function, *args, **kwargs):
        # This unit harness drives the async route with a fresh asyncio.run per
        # call. Execute mocked bridge functions inline here; real ASGI tests
        # separately prove the production thread-pool path and responsive stop.
        return function(*args, **kwargs)

    def default_ensure_conversation(
        *,
        conversation_id=None,
        project_id=None,
        requested_mode=None,
        requested_role=None,
    ):
        del conversation_id, project_id, requested_mode, requested_role
        return SimpleNamespace(conversation_id="conv_ensured_001")

    def default_record_chat_exchange_from_bridge_result(*, request_payload, bridge_result):
        del request_payload, bridge_result
        return {"conversation_id": "conv_ensured_001"}

    def default_send_chat_request(payload):
        del payload
        return _build_chat_envelope_payload(
            request_id="req_bridge_123",
            conversation_id="conv_ensured_001",
        )

    monkeypatch.setattr(chat_route, "ensure_conversation", default_ensure_conversation)
    monkeypatch.setattr(
        chat_route,
        "record_chat_exchange_from_bridge_result",
        default_record_chat_exchange_from_bridge_result,
    )
    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(send_chat_request=default_send_chat_request),
    )
    monkeypatch.setattr(
        chat_route,
        "_load_request_trace_service_optional",
        lambda: None,
    )
    monkeypatch.setattr(chat_route, "run_in_threadpool", direct_mock_threadpool)

    return DirectChatRouteClient()


def test_post_chat_send_is_registered_and_rejects_non_mapping_body(
    client: DirectChatRouteClient,
):
    response = client.post("/chat/send", json=["not", "a", "mapping"])

    assert response.status_code == 400

    payload = response.json()
    assert payload["status"] == "error"
    assert (
        "Request body for /chat/send must be a JSON object."
        in payload["errors"][0]
    )


def test_post_chat_send_rejects_missing_message_field(client: DirectChatRouteClient):
    response = client.post("/chat/send", json={})

    assert response.status_code == 400

    payload = response.json()
    assert payload["status"] == "error"
    assert "failed schema validation" in payload["errors"][0]
    assert "message" in payload["errors"][0]


def test_post_chat_send_rejects_blank_message(client: DirectChatRouteClient):
    response = client.post("/chat/send", json={"message": "   "})

    assert response.status_code == 400

    payload = response.json()
    assert payload["status"] == "error"
    assert "Request body for /chat/send failed schema validation" in payload["errors"][0]
    assert "message" in payload["errors"][0]
    assert "string_too_short" in payload["errors"][0]


def test_post_chat_send_returns_503_when_conversation_continuity_cannot_be_ensured(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    def broken_ensure_conversation(
        *,
        conversation_id=None,
        project_id=None,
        requested_mode=None,
        requested_role=None,
    ):
        del conversation_id, project_id, requested_mode, requested_role
        raise ConversationServiceError("conversation store offline")

    monkeypatch.setattr(chat_route, "ensure_conversation", broken_ensure_conversation)

    response = client.post("/chat/send", json={"message": "Hello there"})

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert "Conversation service is not available yet: conversation store offline" in payload["errors"][0]


def test_post_chat_send_returns_503_when_runtime_bridge_cannot_load(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    def unavailable_runtime_bridge():
        raise chat_route.HTTPException(
            status_code=503,
            detail="Runtime bridge is not available yet: import failed",
        )

    monkeypatch.setattr(chat_route, "_load_runtime_bridge", unavailable_runtime_bridge)

    response = client.post("/chat/send", json={"message": "Hello there"})

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert "Runtime bridge is not available yet: import failed" in payload["errors"][0]


def test_post_chat_send_returns_503_when_runtime_bridge_has_no_send_function(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(),
    )

    response = client.post("/chat/send", json={"message": "Hello there"})

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "unavailable"
    assert "Runtime bridge does not expose send_chat_request yet." in payload["errors"][0]


def test_post_chat_send_returns_500_when_runtime_bridge_returns_non_mapping(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(send_chat_request=lambda payload: "not-a-dict"),
    )

    response = client.post("/chat/send", json={"message": "Hello there"})

    assert response.status_code == 500

    payload = response.json()
    assert payload["status"] == "error"
    assert "Runtime bridge returned a non-dictionary response." in payload["errors"][0]


def test_post_chat_send_preserves_request_id_enriches_context_and_updates_persisted_conversation_id(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, dict] = {}

    def ensure_conversation(
        *,
        conversation_id=None,
        project_id=None,
        requested_mode=None,
        requested_role=None,
    ):
        captured["ensure_conversation"] = {
            "conversation_id": conversation_id,
            "project_id": project_id,
            "requested_mode": requested_mode,
            "requested_role": requested_role,
        }
        return SimpleNamespace(conversation_id="conv_ensured_002")

    def send_chat_request(payload):
        captured["bridge_payload"] = dict(payload)
        return _build_chat_envelope_payload(
            request_id="",
            conversation_id=None,
            project_id=None,
        )

    def record_chat_exchange_from_bridge_result(*, request_payload, bridge_result):
        captured["persistence_request_payload"] = dict(request_payload)
        captured["persistence_bridge_result"] = dict(bridge_result)
        return {"conversation_id": "conv_persisted_777"}

    monkeypatch.setattr(chat_route, "ensure_conversation", ensure_conversation)
    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(send_chat_request=send_chat_request),
    )
    monkeypatch.setattr(
        chat_route,
        "record_chat_exchange_from_bridge_result",
        record_chat_exchange_from_bridge_result,
    )

    response = client.post(
        "/chat/send",
        json={
            "message": "Explain derivatives step by step.",
            "request_id": "req_client_456",
            "project_id": "project_oak",
            "requested_mode": "tutor",
            "requested_role": "primary_general",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["request_id"] == "req_client_456"
    assert payload["data"]["conversation_id"] == "conv_persisted_777"
    assert payload["data"]["project_id"] == "project_oak"

    assert captured["ensure_conversation"] == {
        "conversation_id": None,
        "project_id": "project_oak",
        "requested_mode": "tutor",
        "requested_role": "primary_general",
    }
    assert captured["bridge_payload"]["conversation_id"] == "conv_ensured_002"
    assert captured["bridge_payload"]["request_id"] == "req_client_456"
    assert captured["persistence_request_payload"]["conversation_id"] == "conv_ensured_002"


def test_post_chat_send_degrades_honestly_when_persistence_fails_after_successful_runtime_response(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(
            send_chat_request=lambda payload: _build_chat_envelope_payload(
                request_id="req_bridge_999",
                conversation_id=None,
                project_id=None,
                status=EnvelopeStatus.OK,
                capability_state=CapabilityState.LIVE,
            )
        ),
    )

    def broken_persistence(*, request_payload, bridge_result):
        del request_payload, bridge_result
        raise ConversationServiceError("journal write path unavailable")

    monkeypatch.setattr(
        chat_route,
        "record_chat_exchange_from_bridge_result",
        broken_persistence,
    )

    response = client.post(
        "/chat/send",
        json={
            "message": "Hello there",
            "conversation_id": "conv_inbound_1",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["capability_state"] == "degraded"
    assert payload["data"]["conversation_id"] == "conv_ensured_001"
    assert any(
        "Conversation exchange was returned, but local conversation persistence did not complete"
        in warning
        for warning in payload["warnings"]
    )
    assert payload["errors"] == []


def test_post_chat_send_supports_async_runtime_bridge_send_function(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, dict] = {}

    async def async_send_chat_request(payload):
        captured["bridge_payload"] = dict(payload)
        return _build_chat_envelope_payload(
            request_id="req_async_123",
            conversation_id="conv_async_123",
            project_id="project_async_1",
        )

    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(send_chat_request=async_send_chat_request),
    )

    response = client.post(
        "/chat/send",
        json={
            "message": "Async path please",
            "request_id": "req_async_client",
            "project_id": "project_async_1",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["request_id"] == "req_async_123"
    assert payload["data"]["conversation_id"] == "conv_ensured_001"
    assert payload["data"]["project_id"] == "project_async_1"
    assert captured["bridge_payload"]["conversation_id"] == "conv_ensured_001"
    assert captured["bridge_payload"]["request_id"] == "req_async_client"


def test_post_chat_send_preserves_attached_file_request_context(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, dict] = {}

    def send_chat_request(payload):
        captured["bridge_payload"] = dict(payload)
        return _build_chat_envelope_payload(
            request_id="req_attached_context",
            conversation_id=payload.get("conversation_id"),
            project_id=payload.get("project_id"),
        )

    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(send_chat_request=send_chat_request),
    )

    response = client.post(
        "/chat/send",
        json={
            "message": "Please summarize the attached file.",
            "request_id": "req_client_attached_context",
            "project_id": "project_attached",
            "request_context": {
                "attached_file_ids": ["file_alpha_001", "file_alpha_001", "file_beta_002"],
                "attached_files_are_memory": False,
                "attached_files_source": "user_selected_local_files",
            },
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "ok"
    assert captured["bridge_payload"]["request_context"]["attached_file_ids"] == [
        "file_alpha_001",
        "file_alpha_001",
        "file_beta_002",
    ]
    assert captured["bridge_payload"]["request_context"]["attached_files_are_memory"] is False
    assert captured["bridge_payload"]["request_context"]["attached_files_source"] == (
        "user_selected_local_files"
    )


def test_post_chat_send_accepts_mode_requested_as_advisory_input(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, dict] = {}

    def send_chat_request(payload):
        captured["bridge_payload"] = dict(payload)
        return _build_chat_envelope_payload(
            request_id=payload.get("request_id"),
            conversation_id=payload.get("conversation_id"),
            project_id=payload.get("project_id"),
        )

    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(send_chat_request=send_chat_request),
    )

    response = client.post(
        "/chat/send",
        json={
            "message": "Use Aider dry-run validation for core/runtime.py.",
            "request_id": "req_mode_requested_001",
            "mode_requested": "coder",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert captured["bridge_payload"]["mode_requested"] == "coder"


def test_post_chat_send_mode_requested_coder_surfaces_aider_dry_run_ready(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_runtime_bridge_live_path_mocks(monkeypatch)

    response = client.post(
        "/chat/send",
        json={
            "message": "Use Aider dry-run validation for core/runtime.py and tests/test_api_chat_routes.py.",
            "request_id": "req_aider_safe_api_001",
            "mode_requested": "coder",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    aider_worker = payload["data"]["aider_worker"]

    assert payload["data"]["selected_model_role"] == "primary_code"
    assert payload["data"]["repo_context"]["used"] is True
    assert payload["data"]["code_patch_plan"]["used"] is True
    assert aider_worker["used"] is True
    assert aider_worker["status"] == "dry_run_ready"
    assert aider_worker["worker_used"] is False
    assert aider_worker["aider_invoked"] is False
    assert aider_worker["mutated_files"] is False
    assert aider_worker["shell_used"] is False
    assert aider_worker["network_used"] is False
    assert aider_worker["test_execution_used"] is False
    assert aider_worker["commands_run"] == []
    assert aider_worker["tests_run"] == []


def test_post_chat_send_mode_requested_coder_blocks_vault_and_env_paths(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_runtime_bridge_live_path_mocks(monkeypatch)

    response = client.post(
        "/chat/send",
        json={
            "message": "Use Aider dry-run validation for vault/private.md and .env.",
            "request_id": "req_aider_unsafe_api_001",
            "mode_requested": "coder",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    aider_worker = payload["data"]["aider_worker"]
    response_text = payload["data"]["response_text"].lower()

    assert payload["data"]["selected_model_role"] == "primary_code"
    assert aider_worker["used"] is True
    assert aider_worker["status"] == "blocked"
    assert aider_worker["refusal_reasons"]
    assert any("vault/private.md" in reason for reason in aider_worker["refusal_reasons"])
    assert any(".env" in reason for reason in aider_worker["refusal_reasons"])
    assert aider_worker["worker_used"] is False
    assert aider_worker["aider_invoked"] is False
    assert aider_worker["mutated_files"] is False
    assert aider_worker["shell_used"] is False
    assert aider_worker["network_used"] is False
    assert aider_worker["test_execution_used"] is False
    assert "aider " not in response_text or "aider worker skeleton" in response_text
    assert "aider --" not in response_text
    assert "vault/private.md" in response_text
    assert ".env" in response_text


def test_post_chat_send_in_coder_mode_text_triggers_aider_dry_run(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_runtime_bridge_live_path_mocks(monkeypatch)

    response = client.post(
        "/chat/send",
        json={
            "message": "In Coder mode, use Aider dry-run validation for core/runtime.py.",
            "request_id": "req_in_coder_mode_api_001",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    aider_worker = payload["data"]["aider_worker"]

    assert payload["data"]["selected_model_role"] == "primary_code"
    assert payload["data"]["repo_context"]["used"] is True
    assert payload["data"]["code_patch_plan"]["used"] is True
    assert aider_worker["used"] is True
    assert aider_worker["status"] == "dry_run_ready"
    assert aider_worker["aider_invoked"] is False
    assert aider_worker["mutated_files"] is False


def test_post_chat_send_default_chat_does_not_run_aider_validation(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_runtime_bridge_live_path_mocks(monkeypatch)

    response = client.post(
        "/chat/send",
        json={
            "message": "Hello, how are you today?",
            "request_id": "req_default_no_aider_api_001",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["data"]["selected_model_role"] != "primary_code"
    assert payload["data"]["aider_worker"]["used"] is False
    assert payload["data"]["aider_worker"]["status"] == "not_needed"




def test_post_chat_send_preserves_data_execution_truth_from_bridge_response(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    data_execution = {
        "used": True,
        "status": "completed",
        "tool_kind": "data_executor",
        "operation": "summarize_csv",
        "source_kind": "attached_file",
        "file_id": "file_sites_001",
        "file_name": "sites.csv",
        "file_kind": "csv",
        "row_count": 2,
        "column_count": 2,
        "columns": ["site", "value"],
        "numeric_columns": ["value"],
        "text_columns": ["site"],
        "stayed_local": True,
        "approval_required": False,
        "network_access_used": False,
        "mutated_files": False,
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(
            send_chat_request=lambda payload: _build_chat_envelope_payload(
                request_id="req_data_execution_001",
                conversation_id=payload.get("conversation_id"),
                project_id=payload.get("project_id"),
                data_execution=data_execution,
            )
        ),
    )

    response = client.post(
        "/chat/send",
        json={
            "message": "Summarize the attached CSV.",
            "request_id": "req_client_data_execution_001",
            "project_id": "project_data",
            "request_context": {
                "attached_file_ids": ["file_sites_001"],
                "attached_files_are_memory": False,
                "attached_files_source": "user_selected_local_files",
            },
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["data"]["data_execution"]["used"] is True
    assert payload["data"]["data_execution"]["status"] == "completed"
    assert payload["data"]["data_execution"]["tool_kind"] == "data_executor"
    assert payload["data"]["data_execution"]["operation"] == "summarize_csv"
    assert payload["data"]["data_execution"]["file_id"] == "file_sites_001"
    assert payload["data"]["data_execution"]["file_name"] == "sites.csv"
    assert payload["data"]["data_execution"]["row_count"] == 2
    assert payload["data"]["data_execution"]["column_count"] == 2



def test_post_chat_send_preserves_artifact_summaries_from_bridge_response(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    artifact_summary = {
        "artifact_id": "artifact_data_summary_001",
        "kind": "data_summary",
        "title": "Data summary: sites.csv",
        "summary": "Saved bounded local data summary for sites.csv: 2 rows, 2 columns.",
        "created_at_utc": "2026-05-24T00:00:00Z",
        "locality": "local",
        "memory_posture": "not_memory",
        "producer_tool_kind": "data_executor",
        "producer_operation": "summarize_csv",
        "source_file_id": "file_sites_001",
        "source_file_name": "sites.csv",
        "source_file_kind": "csv",
        "row_count": 2,
        "column_count": 2,
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(
            send_chat_request=lambda payload: _build_chat_envelope_payload(
                request_id="req_artifact_summary_001",
                conversation_id=payload.get("conversation_id"),
                project_id=payload.get("project_id"),
                artifacts=[artifact_summary],
            )
        ),
    )

    response = client.post(
        "/chat/send",
        json={
            "message": "Summarize the attached CSV.",
            "request_id": "req_client_artifact_summary_001",
            "project_id": "project_data",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    artifact = payload["data"]["artifacts"][0]

    assert payload["status"] == "ok"
    assert artifact["artifact_id"] == "artifact_data_summary_001"
    assert artifact["kind"] == "data_summary"
    assert artifact["locality"] == "local"
    assert artifact["memory_posture"] == "not_memory"
    assert artifact["producer_tool_kind"] == "data_executor"
    assert artifact["producer_operation"] == "summarize_csv"
    assert artifact["source_file_id"] == "file_sites_001"
    assert artifact["source_file_name"] == "sites.csv"
    assert artifact["row_count"] == 2
    assert artifact["column_count"] == 2


def test_runtime_bridge_creates_data_summary_artifact_for_completed_data_execution(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    data_execution = {
        "used": True,
        "status": "completed",
        "tool_kind": "data_executor",
        "operation": "summarize_csv",
        "source_kind": "attached_file",
        "file_id": "file_sites_001",
        "file_name": "sites.csv",
        "file_kind": "csv",
        "row_count": 2,
        "column_count": 2,
        "columns": ["site", "value"],
        "numeric_columns": ["value"],
        "text_columns": ["site"],
        "missing_values_by_column": {"site": 0, "value": 0},
        "numeric_stats": {"value": {"count": 2, "missing": 0, "mean": 1.5}},
        "stayed_local": True,
        "approval_required": False,
        "network_access_used": False,
        "mutated_files": False,
        "warnings": [],
        "errors": [],
    }

    def fake_create_data_summary_artifact(
        received_data_execution,
        *,
        request_id=None,
        conversation_id=None,
        project_id=None,
        artifact_root=None,
    ):
        captured["data_execution"] = dict(received_data_execution)
        captured["request_id"] = request_id
        captured["conversation_id"] = conversation_id
        captured["project_id"] = project_id
        captured["artifact_root"] = artifact_root
        return SimpleNamespace(artifact_id="artifact_data_summary_001")

    def fake_artifact_summary_from_record(record):
        assert record.artifact_id == "artifact_data_summary_001"
        return ArtifactSummary(
            artifact_id="artifact_data_summary_001",
            kind=ArtifactKind.DATA_SUMMARY,
            title="Data summary: sites.csv",
            summary="Saved bounded local data summary for sites.csv: 2 rows, 2 columns.",
            created_at_utc="2026-05-24T00:00:00Z",
            locality=LocalityState.LOCAL,
            memory_posture=ArtifactMemoryPosture.NOT_MEMORY,
            producer_tool_kind="data_executor",
            producer_operation="summarize_csv",
            source_file_id="file_sites_001",
            source_file_name="sites.csv",
            source_file_kind="csv",
            row_count=2,
            column_count=2,
        )

    monkeypatch.setattr(
        runtime_bridge,
        "create_data_summary_artifact",
        fake_create_data_summary_artifact,
    )
    monkeypatch.setattr(
        runtime_bridge,
        "artifact_summary_from_record",
        fake_artifact_summary_from_record,
    )

    request_model = ChatSendRequest(
        message="Summarize the attached CSV.",
        request_id="req_bridge_artifact_001",
        conversation_id="conv_bridge_artifact_001",
        project_id="project_bridge_artifact_001",
    )

    chat_data = runtime_bridge._translate_runtime_packet_to_chat_data(
        request_model,
        {
            "status": "ok_local_runtime",
            "response": {
                "response_text": "I inspected the attached CSV locally.",
                "response_source": "live_invoker",
                "invocation_status": "ok",
                "selected_model_role": "primary_general",
                "selected_runtime": "ollama",
                "selected_model_runtime_tag": "fake-local-model",
                "used_fallback": False,
                "caveats": [],
            },
            "data_execution": data_execution,
        },
    )

    assert captured["request_id"] == "req_bridge_artifact_001"
    assert captured["conversation_id"] == "conv_bridge_artifact_001"
    assert captured["project_id"] == "project_bridge_artifact_001"
    assert captured["data_execution"] == data_execution

    assert len(chat_data.artifacts) == 1
    artifact = chat_data.artifacts[0]
    assert artifact.artifact_id == "artifact_data_summary_001"
    assert artifact.kind == ArtifactKind.DATA_SUMMARY
    assert artifact.locality == LocalityState.LOCAL
    assert artifact.memory_posture == ArtifactMemoryPosture.NOT_MEMORY
    assert artifact.source_file_name == "sites.csv"
    assert artifact.row_count == 2
    assert artifact.column_count == 2


def test_runtime_bridge_exposes_csv_data_files_without_prompt_chunk_injection():
    packet = {
        "attached_files_are_memory": False,
        "source": "user_selected_local_files",
        "locality": "local",
        "bounded": True,
        "requested_file_ids": ["file_sites_001"],
        "used_file_ids": ["file_sites_001"],
        "used_text_file_ids": [],
        "used_data_file_ids": ["file_sites_001"],
        "requested_file_count": 1,
        "file_count": 1,
        "text_file_count": 0,
        "data_file_count": 1,
        "files": [],
        "data_files": [
            {
                "file_id": "file_sites_001",
                "display_name": "sites.csv",
                "file_name": "sites.csv",
                "file_kind": "csv",
                "source_kind": "attached_file",
                "source_path": "/local/ingest/raw/file_sites_001/sites.csv",
                "ready": True,
                "usable_as_context": True,
                "blocked": False,
                "memory_posture": "not_memory",
            }
        ],
        "warnings": [],
        "errors": [],
    }

    context = runtime_bridge._build_runtime_request_context(
        is_quick_invoke=False,
        ui_surface_hint="conversations_room",
        inbound_request_context={
            "attached_file_ids": ["file_sites_001"],
            "attached_files_are_memory": False,
            "attached_files_source": "user_selected_local_files",
        },
        attached_context_packet=packet,
    )

    assert context is not None
    assert context["attached_files_are_memory"] is False
    assert context["attached_files_source"] == "user_selected_local_files"
    assert context["attached_data_files"] == packet["data_files"]

    effective_message = runtime_bridge._build_effective_runtime_message(
        user_message="Summarize the attached CSV.",
        attached_context_packet=packet,
    )

    assert effective_message == "Summarize the attached CSV."

    summary = runtime_bridge._build_attached_context_summary(packet)

    assert summary is not None
    assert summary["files_in_use"] == ["sites.csv"]
    assert summary["text_files_in_use"] == []
    assert summary["data_files_in_use"] == ["sites.csv"]
    assert summary["attached_text_file_ids"] == []
    assert summary["attached_data_file_ids"] == ["file_sites_001"]
    assert summary["file_count"] == 1
    assert summary["text_file_count"] == 0
    assert summary["data_file_count"] == 1
    assert summary["attached_files_are_memory"] is False
    assert "CSV/XLSX files may be used as bounded local data-execution inputs" in summary["active_context_note"]


def test_runtime_bridge_translates_coder_runtime_truth_into_chat_data():
    repo_context = {
        "used": True,
        "status": "completed",
        "tool_kind": "repo_context_gatherer",
        "operation": "gather_repo_context",
        "repo_key": "elysia",
        "repo_label": "Elysia local repository",
        "repo_root": "/project/Elysia",
        "trust_zone": "project_local",
        "appears_git_repo": True,
        "current_branch": "main",
        "git_head_read": True,
        "changed_files_live": False,
        "changed_files_note": "Git status detection is not live in repo context v0.",
        "important_top_level_files": ["README.md"],
        "top_level_directories": ["app", "apps", "core", "tests"],
        "safe_tree_entries": ["core/runtime.py", "tests/test_runtime_coder_mode_flow.py"],
        "language_hints": ["Python", "TypeScript"],
        "framework_hints": ["FastAPI local API bridge", "React desktop UI"],
        "test_command_hints": ["./scripts/test_backend.sh tests/test_runtime_coder_mode_flow.py -q"],
        "read_only": True,
        "approval_required": False,
        "network_access_used": False,
        "shell_used": False,
        "mutated_files": False,
        "warnings": [],
        "errors": [],
    }
    code_patch_plan = {
        "used": True,
        "status": "completed",
        "tool_kind": "code_patch_formatter",
        "operation": "format_patch_plan",
        "summary": "Proposal-only patch plan.",
        "repo_key": "elysia",
        "repo_root": "/project/Elysia",
        "files_to_touch": ["core/runtime.py"],
        "patch_plan": ["Inspect current runtime seam.", "Patch only the narrow Coder branch."],
        "tests_to_run": ["./scripts/test_backend.sh tests/test_runtime_coder_mode_flow.py -q"],
        "risk_notes": ["Runtime path is central; keep patch narrow."],
        "rollback_notes": ["Revert the touched file if tests fail."],
        "approval_needed": True,
        "approval_reason": "File mutation is not live in Coder v0.",
        "can_apply_patch": False,
        "patch_application_live": False,
        "shell_execution_used": False,
        "network_access_used": False,
        "mutated_files": False,
        "external_workers_used": False,
        "warnings": [],
        "errors": [],
    }
    aider_worker = {
        "used": True,
        "status": "dry_run_ready",
        "state": "skeleton",
        "mode": "dry_run_validation",
        "worker_key": "aider_worker",
        "worker_used": False,
        "aider_invoked": False,
        "repo_key": "elysia",
        "repo_root": "/project/Elysia",
        "trust_zone": "project_local",
        "files_considered": ["core/runtime.py"],
        "files_proposed": ["core/runtime.py"],
        "diff_preview": "",
        "diff_preview_hash": "",
        "commands_requested": [],
        "commands_run": [],
        "tests_requested": [],
        "tests_run": [],
        "mutated_files": False,
        "network_used": False,
        "shell_used": False,
        "test_execution_used": False,
        "git_mutation_used": False,
        "package_install_used": False,
        "external_model_used": False,
        "approval_required": True,
        "approval_reason": "Approval is required before any future mutation.",
        "refusal_reasons": [],
        "warnings": ["Aider subprocess invocation is not live."],
        "errors": [],
        "trace_summary": {},
    }

    request_model = ChatSendRequest(
        message="Make a patch plan for core/runtime.py.",
        request_id="req_coder_truth_001",
        conversation_id="conv_coder_truth_001",
        requested_mode="coder",
    )
    runtime_packet = {
        "status": "ok_local_runtime",
        "response": {
            "response_text": "Coder response generated locally.",
            "response_source": ChatResponseSource.LIVE_INVOKER.value,
            "invocation_status": ChatInvocationStatus.OK.value,
            "selected_model_role": "primary_code",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "fake-local-code-model",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "caveats": [],
        },
        "repo_context": repo_context,
        "code_patch_plan": code_patch_plan,
        "aider_worker": aider_worker,
    }

    chat_data = runtime_bridge._translate_runtime_packet_to_chat_data(
        request_model,
        runtime_packet,
    )

    assert chat_data.repo_context == repo_context
    assert chat_data.code_patch_plan == code_patch_plan
    assert chat_data.aider_worker == aider_worker
    assert chat_data.approval_needed is False
    assert chat_data.repo_context["read_only"] is True
    assert chat_data.repo_context["shell_used"] is False
    assert chat_data.code_patch_plan["approval_needed"] is True
    assert chat_data.code_patch_plan["can_apply_patch"] is False
    assert chat_data.code_patch_plan["patch_application_live"] is False
    assert chat_data.code_patch_plan["external_workers_used"] is False
    assert chat_data.aider_worker["worker_used"] is False
    assert chat_data.aider_worker["aider_invoked"] is False
    assert chat_data.aider_worker["mutated_files"] is False
    assert chat_data.aider_worker["shell_used"] is False
    assert chat_data.aider_worker["network_used"] is False
    assert chat_data.aider_worker["test_execution_used"] is False
    assert chat_data.aider_worker["git_mutation_used"] is False
    assert chat_data.aider_worker["package_install_used"] is False
    assert chat_data.aider_worker["external_model_used"] is False


def test_runtime_bridge_translates_math_execution_truth_into_chat_data_and_ledger():
    math_execution = {
        "used": True,
        "status": "completed",
        "tool_kind": "math_executor",
        "operation": "evaluate",
        "input": "3600 * (1 - 15/100)",
        "result": "3060.00000000000",
        "numeric_result": 3060.0,
        "stayed_local": True,
        "approval_required": False,
        "network_access_used": False,
        "mutated_files": False,
        "warnings": [],
        "errors": [],
    }
    request_model = ChatSendRequest(
        message="Write a paragraph after calculating a 15 percent reduction from 3600.",
        request_id="req_math_truth_001",
        conversation_id="conv_math_truth_001",
        requested_mode="writer",
    )
    runtime_packet = {
        "status": "ok_local_runtime",
        "response": {
            "response_text": "3,600 reduced by 15 percent is 3,060.",
            "response_source": ChatResponseSource.LIVE_INVOKER.value,
            "invocation_status": ChatInvocationStatus.OK.value,
            "selected_model_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "fake-local-general-model",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "caveats": [
                "Bounded local math execution was used to check part of this response."
            ],
        },
        "math_execution": math_execution,
    }

    chat_data = runtime_bridge._translate_runtime_packet_to_chat_data(
        request_model,
        runtime_packet,
    )
    tools_used, extra = runtime_bridge._build_tool_ledger_from_chat_data(chat_data)

    assert chat_data.math_execution == math_execution
    assert extra["mutated_files"] is False
    assert tools_used == [
        {
            "tool_key": "bounded_math_execution",
            "tool_label": "Bounded math execution",
            "tool_kind": "math_executor",
            "state": "completed",
            "available": True,
            "used": True,
            "approval_required": False,
            "approval_state": "not_needed",
            "locality": "local",
            "boundary_kind": "local",
            "operation": "evaluate",
            "summary": "Bounded local math execution truth from chat response.",
            "input_count": 1,
            "output_count": 1,
            "mutated_files": False,
            "network_access_used": False,
            "private_context_sent": False,
            "shell_used": False,
            "git_mutation_used": False,
            "cloud_used": False,
            "warnings": [],
            "errors": [],
        }
    ]


def test_post_chat_send_preserves_coder_runtime_truth_from_bridge_response(
    client: DirectChatRouteClient,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_context = {
        "used": True,
        "status": "completed",
        "tool_kind": "repo_context_gatherer",
        "operation": "gather_repo_context",
        "repo_key": "elysia",
        "repo_label": "Elysia local repository",
        "repo_root": "/project/Elysia",
        "trust_zone": "project_local",
        "appears_git_repo": True,
        "current_branch": "main",
        "git_head_read": True,
        "changed_files_live": False,
        "changed_files_note": "Git status detection is not live in repo context v0.",
        "important_top_level_files": ["README.md"],
        "top_level_directories": ["app", "apps", "core", "tests"],
        "safe_tree_entries": ["core/runtime.py", "tests/test_runtime_coder_mode_flow.py"],
        "language_hints": ["Python", "TypeScript"],
        "framework_hints": ["FastAPI local API bridge", "React desktop UI"],
        "test_command_hints": ["./scripts/test_backend.sh tests/test_runtime_coder_mode_flow.py -q"],
        "read_only": True,
        "approval_required": False,
        "network_access_used": False,
        "shell_used": False,
        "mutated_files": False,
        "warnings": [],
        "errors": [],
    }
    code_patch_plan = {
        "used": True,
        "status": "completed",
        "tool_kind": "code_patch_formatter",
        "operation": "format_patch_plan",
        "summary": "Proposal-only patch plan.",
        "repo_key": "elysia",
        "repo_root": "/project/Elysia",
        "files_to_touch": ["core/runtime.py"],
        "patch_plan": ["Inspect current runtime seam.", "Patch only the narrow Coder branch."],
        "tests_to_run": ["./scripts/test_backend.sh tests/test_runtime_coder_mode_flow.py -q"],
        "risk_notes": ["Runtime path is central; keep patch narrow."],
        "rollback_notes": ["Revert the touched file if tests fail."],
        "approval_needed": True,
        "approval_reason": "File mutation is not live in Coder v0.",
        "can_apply_patch": False,
        "patch_application_live": False,
        "shell_execution_used": False,
        "network_access_used": False,
        "mutated_files": False,
        "external_workers_used": False,
        "warnings": [],
        "errors": [],
    }
    aider_worker = {
        "used": True,
        "status": "dry_run_ready",
        "state": "skeleton",
        "mode": "dry_run_validation",
        "worker_key": "aider_worker",
        "worker_used": False,
        "aider_invoked": False,
        "repo_key": "elysia",
        "repo_root": "/project/Elysia",
        "trust_zone": "project_local",
        "files_considered": ["core/runtime.py"],
        "files_proposed": ["core/runtime.py"],
        "diff_preview": "",
        "diff_preview_hash": "",
        "commands_requested": [],
        "commands_run": [],
        "tests_requested": [],
        "tests_run": [],
        "mutated_files": False,
        "network_used": False,
        "shell_used": False,
        "test_execution_used": False,
        "git_mutation_used": False,
        "package_install_used": False,
        "external_model_used": False,
        "approval_required": True,
        "approval_reason": "Approval is required before any future mutation.",
        "refusal_reasons": [],
        "warnings": ["Aider subprocess invocation is not live."],
        "errors": [],
        "trace_summary": {},
    }

    def send_coder_truth_response(payload):
        assert payload["requested_mode"] == "coder"
        return _build_chat_envelope_payload(
            request_id="req_coder_bridge_001",
            conversation_id="conv_ensured_001",
            repo_context=repo_context,
            code_patch_plan=code_patch_plan,
            aider_worker=aider_worker,
        )

    monkeypatch.setattr(
        chat_route,
        "_load_runtime_bridge",
        lambda: SimpleNamespace(send_chat_request=send_coder_truth_response),
    )

    response = client.post(
        "/chat/send",
        json={
            "message": "Make a patch plan for core/runtime.py.",
            "request_id": "req_client_coder_001",
            "requested_mode": "coder",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"

    assert payload["data"]["repo_context"]["used"] is True
    assert payload["data"]["repo_context"]["status"] == "completed"
    assert payload["data"]["repo_context"]["tool_kind"] == "repo_context_gatherer"
    assert payload["data"]["repo_context"]["read_only"] is True
    assert payload["data"]["repo_context"]["shell_used"] is False
    assert payload["data"]["repo_context"]["network_access_used"] is False
    assert payload["data"]["repo_context"]["mutated_files"] is False

    assert payload["data"]["code_patch_plan"]["used"] is True
    assert payload["data"]["code_patch_plan"]["status"] == "completed"
    assert payload["data"]["code_patch_plan"]["tool_kind"] == "code_patch_formatter"
    assert payload["data"]["code_patch_plan"]["approval_needed"] is True
    assert payload["data"]["code_patch_plan"]["can_apply_patch"] is False
    assert payload["data"]["code_patch_plan"]["patch_application_live"] is False
    assert payload["data"]["code_patch_plan"]["shell_execution_used"] is False
    assert payload["data"]["code_patch_plan"]["external_workers_used"] is False

    assert payload["data"]["aider_worker"]["used"] is True
    assert payload["data"]["aider_worker"]["status"] == "dry_run_ready"
    assert payload["data"]["aider_worker"]["worker_used"] is False
    assert payload["data"]["aider_worker"]["aider_invoked"] is False
    assert payload["data"]["aider_worker"]["mutated_files"] is False
    assert payload["data"]["aider_worker"]["shell_used"] is False
    assert payload["data"]["aider_worker"]["network_used"] is False
    assert payload["data"]["aider_worker"]["test_execution_used"] is False
    assert payload["data"]["aider_worker"]["git_mutation_used"] is False
    assert payload["data"]["aider_worker"]["package_install_used"] is False
    assert payload["data"]["aider_worker"]["external_model_used"] is False
    assert payload["data"]["aider_worker"]["commands_run"] == []
    assert payload["data"]["aider_worker"]["tests_run"] == []
