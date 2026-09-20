from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qs, urlparse

import pytest

from app.api import account_service, file_ingest_service, research_service, runtime_bridge
from app.api.account_service import AccountPaths, AccountStore
from app.api.routes.memory import get_settings, update_settings
from app.api.schemas.account import AccountCreateRequest
from app.cognition import workspace
from app.cognition.models import CognitionCandidate
from app.memory.canonical_models import MemorySettings
from core import runtime
from sandbox.fetch_worker.contract import FetchWorkerResult, FetchWorkerStatus
from sandbox.searxng_worker import client, worker
from tests.test_part2c_research_evidence import _paths
from tests.test_runtime_invoker_integration import (
    _install_runtime_environment,
    base_configs,
    runtime_skills,
)


@pytest.mark.parametrize("case,internet,attachment,available", [
    ("off", False, False, True),
    ("public", True, False, True),
    ("private_attachment", True, True, True),
    ("unavailable", True, False, False),
    ("transport_unavailable", True, False, True),
    ("zero_results", True, False, True),
    ("private_export", True, True, True),
])
def test_live_setting_to_outbound_http_partition(
    tmp_path, monkeypatch, base_configs, runtime_skills,
    case, internet, attachment, available,
):
    paths = _paths(tmp_path, monkeypatch)
    identity = paths.data_dir / "identity"
    store = AccountStore(AccountPaths(
        identity_root=identity,
        database_path=identity / "elysia_identity.sqlite",
        profile_photo_dir=identity / "profile_photos",
        current_session_path=identity / "current_session.json",
        elysia_paths=paths,
    ))
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    store.create_account(AccountCreateRequest(
        username="partition-test", password="synthetic partition account password",
    ))
    settings = asyncio.run(get_settings())["data"]["settings"]
    settings["internet_master_enabled"] = internet
    assert asyncio.run(update_settings(MemorySettings(**settings)))["status"] == "ok"

    _install_runtime_environment(monkeypatch, base_configs, runtime_skills)
    monkeypatch.setattr(runtime_bridge, "_load_runtime_module", lambda: runtime)
    monkeypatch.setattr(runtime_bridge, "_load_visible_profile_context", lambda: None)
    model_calls = []

    def invoke(**kwargs):
        model_calls.append(kwargs)
        return {"status": "ok", "allowed": True, "stayed_local": True,
                "selected_role": "primary_general", "selected_runtime": "ollama",
                "response_text": "Local synthesis.", "used_fallback": False,
                "note": "Local model fixture; real planner, governor and research path."}

    monkeypatch.setattr(runtime, "invoke_model", invoke)
    port_calls = []
    investigate = research_service.WebResearchPort.investigate

    def observe_port(self, **kwargs):
        port_calls.append(kwargs)
        return investigate(self, **kwargs)

    monkeypatch.setattr(research_service.WebResearchPort, "investigate", observe_port)
    config = worker.load_searxng_worker_config()
    config.service["enabled"] = available
    monkeypatch.setattr(worker, "load_searxng_worker_config", lambda *_a, **_k: config)
    # Capture the actual Request built by the real SearXNG HTTP client, not
    # the claimed private_context_sent flag. No test traffic leaves the process.
    outbound = []
    transport_attempts = []

    def http_capture(request, **kwargs):
        del kwargs
        outbound.append({
            "url": request.full_url,
            "data": request.data,
            "headers": dict(request.header_items()),
        })

        results = (
            []
            if case == "zero_results"
            else [{
                "url": "https://www.rfc-editor.org/rfc/rfc7946",
                "title": "GeoJSON RFC guidance",
                "content": "Public GeoJSON guidance",
            }]
        )

        return json.dumps(
            {"results": results}
        ).encode()

    def http_refused(request, **kwargs):
        del kwargs
        transport_attempts.append(request.full_url)
        raise ConnectionRefusedError(
            "synthetic SearXNG loopback refusal"
        )

    monkeypatch.setattr(
        client,
        "_cancellable_loopback_get",
        http_refused
        if case == "transport_unavailable"
        else http_capture,
    )
    monkeypatch.setattr(research_service, "run_fetch_worker", lambda request:
        FetchWorkerResult(status=FetchWorkerStatus.UNAVAILABLE,
                          request_id=request.request_id, ticket_id=request.ticket_id))

    canary = "PRIVATE_CANARY_DO_NOT_EGRESS_82F17A"
    sealed_canary = "SEALED_CANARY_DO_NOT_EGRESS_82F17A"
    contents = f"Private local analysis: {canary}\n/home/synthetic/private-analysis.txt\n"
    context = {}
    if attachment:
        source = tmp_path / "private-analysis.txt"
        source.write_text(contents)
        monkeypatch.setattr(file_ingest_service, "DEFAULT_INGEST_ROOT", paths.ingest_dir)
        attached = file_ingest_service.attach_file(str(source))
        assert attached.ready
        context["attached_file_ids"] = [attached.file.file_id]
        # A context hint cannot substitute attachment text for the canonical
        # user question selected by the bridge.
        context["public_research_question"] = contents
        if case == "private_attachment":
            # Exercise the admitted-sealed-context case as well as a real
            # attachment, through the existing explicit admission gate.
            class SealedSource:
                source_type = "memory_fusion"

                def __init__(self, **kwargs):
                    pass

                def read(self, request):
                    return [CognitionCandidate(
                        candidate_id="sealed-partition-canary", source_type=self.source_type,
                        source_id="sealed-fixture", owner_user_id=request.owner_user_id,
                        space_id=None, privacy="sealed", form="narrative", scope="profile",
                        content_excerpt_or_pointer=sealed_canary, estimated_tokens=20,
                    )]

            monkeypatch.setattr(workspace, "DEFAULT_SOURCES", (*workspace.DEFAULT_SOURCES, SealedSource))
            context["explicit_sealed_memory"] = True

    question = "Search the public web for the latest GeoJSON RFC guidance."
    if case == "private_attachment":
        question = "Using the attached local document for my analysis, " + question[0].lower() + question[1:]
    elif case == "private_export":
        question = f"Send my private attachment contents {canary} to public web search."
    result = runtime_bridge.send_chat_request({
        "message": question, "request_id": f"req_partition_{case}",
        "requested_mode": "researcher", "request_context": context,
        "ui_surface": "conversations_room",
    })
    data = result["data"]
    activity = data["research"]
    response = data["response_text"]
    if case == "zero_results":
        assert outbound
        assert activity["state"] == "degraded"
        assert activity["research_attempted"] is True
        assert activity["network_access_used"] is True
        assert activity["searxng_used"] is True
        assert activity["evidence_ids"] == []
        assert "no usable evidence packet was retained" in response
        assert "not web-supported" in response
    elif case in {"public", "private_attachment"}:
        # This fixture intentionally makes the bounded page-fetch worker
        # unavailable. Search succeeds and retains evidence, but the whole
        # iterative research operation is therefore degraded rather than
        # falsely reported as fully completed.
        assert outbound
        assert activity["state"] == "degraded"
        assert activity["research_attempted"] is True
        assert activity["worker_used"] is True
        assert activity["network_access_used"] is True
        assert activity["searxng_used"] is True
        assert activity["evidence_ids"]
        assert "completed only partially" in response
        assert "Some public evidence was retained" in response
        assert "research did not run" not in response
        for request in outbound:
            query = parse_qs(urlparse(request["url"]).query)["q"][0]
            assert "GeoJSON RFC guidance" in query
            payload = json.dumps(request)
            for private in (canary, sealed_canary, contents, "/home/synthetic/", str(tmp_path), "private-analysis.txt"):
                assert private not in payload
        if attachment:
            assert any(canary in call["message"] for call in model_calls)
            assert any(sealed_canary in call["context_summary"] for call in model_calls)
    else:
        assert outbound == []
        assert activity["network_access_used"] is False
        assert activity["searxng_used"] is False
        if case == "off":
            assert port_calls == []  # No governor bypass to manufacture OFF truth.
            assert activity["reason"] == "internet_master_off"
            assert activity["research_attempted"] is False
            assert "Internet setting is OFF" in response
            assert model_calls  # Internet OFF does not disable local reasoning.
        elif case in {"unavailable", "transport_unavailable"}:
            assert activity["state"] == "unavailable"
            assert activity["research_attempted"] is True
            assert activity["network_access_used"] is False
            assert activity["searxng_used"] is False

            if case == "transport_unavailable":
                # The governed worker did run and attempted transport, but the
                # local SearXNG endpoint refused the connection. That is
                # distinct from pre-execution worker/service unavailability.
                assert activity["worker_used"] is True
                assert "research was attempted" in response
                assert "could not be reached" in response
                assert "worker is unavailable" not in response
                assert transport_attempts
                assert "GeoJSON" in transport_attempts[0]
            else:
                assert activity["worker_used"] is False
                assert "worker is unavailable" in response
        else:
            assert activity["reason"] == "explicit_private_egress"
            assert activity["state"] == "blocked"
