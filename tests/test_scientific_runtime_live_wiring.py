from __future__ import annotations

import inspect

import pytest

from tests.test_runtime_invoker_integration import base_configs, runtime_skills

from core import runtime


def _handle_source() -> str:
    return inspect.getsource(
        runtime.handle_user_message
    )


def test_live_runtime_calls_scientific_helper():
    source = _handle_source()

    assert (
        "_run_bounded_scientific_execution_if_needed("
        in source
    )

    assert (
        '"request_id": workspace_request_id'
        in source
    )


def test_live_runtime_includes_scientific_tool_mismatch_truth():
    source = _handle_source()

    helper_index = source.index(
        "_run_bounded_scientific_execution_if_needed("
    )

    mismatch_index = source.index(
        "tool_checks = ("
    )

    assert helper_index < mismatch_index

    tool_section = source[
        mismatch_index:
        source.index(
            "research_expected =",
            mismatch_index,
        )
    ]

    assert (
        "bounded_scientific_execution_candidate"
        in tool_section
    )

    assert (
        "scientific_execution"
        in tool_section
    )

    assert (
        '"cancelled"'
        in tool_section
    )


def test_scientific_context_reaches_model_before_invocation(
    monkeypatch, base_configs, runtime_skills,
):
    from tests.test_runtime_invoker_integration import _install_runtime_environment

    _install_runtime_environment(monkeypatch, base_configs, runtime_skills)
    calls = []
    evidence = "Governed ScientificForge result: synthetic bounded evidence 649C"

    def execute(**kwargs):
        calls.append("scientific_execution")
        return {"used": True, "status": "completed", "tool_kind": "scientificforge"}, evidence

    def invoke(**kwargs):
        assert calls == ["scientific_execution"]
        assert evidence in kwargs["context_summary"]
        calls.append("model_invocation")
        return {
            "status": "ok", "allowed": True, "stayed_local": True,
            "response_text": "Interpretation of bounded scientific evidence.",
            "used_fallback": False,
        }

    monkeypatch.setattr(runtime, "_run_bounded_scientific_execution_if_needed", execute)
    monkeypatch.setattr(runtime, "invoke_model", invoke)
    result = runtime.handle_user_message(
        "Explain these existing numerical results.", runtime.SessionState(autonomy_level=1),
    )
    assert calls == ["scientific_execution", "model_invocation"]
    assert result["scientific_execution"]["status"] == "completed"


def test_scientific_receipt_is_attached_before_verifier():
    source = _handle_source()

    attach_index = source.index(
        'internal_result["scientific_execution"] = '
        "scientific_execution"
    )

    verifier_index = source.index(
        "verification = verify_result("
    )

    assert attach_index < verifier_index


def test_runtime_log_records_scientific_truth_without_workspace_root():
    source = _handle_source()

    assert (
        '"scientific_execution_used"'
        in source
    )

    assert (
        '"scientific_execution_status"'
        in source
    )

    assert (
        '"scientific_execution_operation"'
        in source
    )

    assert (
        '"scientific_execution_source_mutated"'
        in source
    )

    assert (
        '"scientific_execution_network_used"'
        in source
    )

    assert (
        '"scientific_execution_shell_used"'
        in source
    )

    # The raw authority-bearing root remains only inside request context and
    # request construction. It is never named as a runtime log field.
    log_start = source.index(
        "log_path = write_runtime_log("
    )

    log_end = source.index(
        "journal_status = write_session_journal_entry(",
        log_start,
    )

    log_section = source[
        log_start:log_end
    ]

    assert (
        '"scientific_workspace_root"'
        not in log_section
    )

    assert (
        '"workspace_root"'
        not in log_section
    )


def test_non_candidate_scientific_payload_is_explicit_not_needed():
    payload, block = (
        runtime._run_bounded_scientific_execution_if_needed(
            plan={
                "bounded_scientific_execution_candidate": False,
            },
            policy_review={
                "allowed": True,
                "boundary_flags": [],
            },
            context={},
        )
    )

    assert payload["used"] is False
    assert payload["status"] == "not_needed"
    assert payload["tool_kind"] == "scientificforge"
    assert block == ""


def test_cancelled_scientific_result_counts_as_tool_mismatch_state():
    source = _handle_source()

    assert (
        '{"blocked", "failed", "error", "unavailable", "cancelled"}'
        in source
    )


@pytest.mark.parametrize("approved,public_research", [(True, False), (False, False), (True, True)])
def test_bridge_runtime_executes_scientific_selection_under_authority(
    tmp_path, monkeypatch, base_configs, runtime_skills, approved, public_research,
):
    """Execute the handoff; source-text presence cannot prove selection propagation."""
    import asyncio
    import json

    from app.api import (
        account_service, conversation_service, file_ingest_service,
        project_service, runtime_bridge, scientificforge_source_service,
        scientific_workspace_service,
    )
    from app.api.routes.memory import get_settings, update_settings
    from app.api.schemas.account import AccountCreateRequest
    from app.memory.canonical_models import MemorySettings
    from sandbox.searxng_worker import client, worker
    from tests.test_part2d_cognition_governance import make_store
    from tests.test_runtime_invoker_integration import _install_runtime_environment
    from tests.test_scientific_workspace_execution_service import _approve

    monkeypatch.setattr(scientific_workspace_service, "_PLANS", {})
    store = make_store(tmp_path, monkeypatch)
    paths = store.elysia_paths
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    store.create_account(AccountCreateRequest(
        username="scientific-handoff", password="synthetic scientific test password",
    ))
    monkeypatch.setattr(project_service, "PROJECTS_DIR", paths.project_dir)
    monkeypatch.setattr(project_service, "ACTIVE_PROJECT_PATH", paths.project_dir / "_active_project.json")
    monkeypatch.setattr(conversation_service, "CONVERSATIONS_DIR", paths.conversation_dir)
    monkeypatch.setattr(file_ingest_service, "DEFAULT_INGEST_ROOT", paths.ingest_dir)
    monkeypatch.setattr(scientificforge_source_service, "DEFAULT_INGEST_ROOT", paths.ingest_dir)
    project_id = project_service.create_project(name="Scientific handoff")["project_id"]
    root = tmp_path / "private-scientific-workspace"
    root.mkdir()
    canary = "PRIVATE_SCIENTIFIC_CANARY_DO_NOT_EGRESS_649C"
    (root / "measurements.csv").write_text(f"value,note\n1,{canary}\n3,local\n")
    if approved:
        _approve(project_id=project_id, root=root)

    settings = asyncio.run(get_settings())["data"]["settings"]
    settings["internet_master_enabled"] = public_research
    assert asyncio.run(update_settings(MemorySettings(**settings)))["status"] == "ok"
    captured = _install_runtime_environment(monkeypatch, base_configs, runtime_skills)
    monkeypatch.setattr(runtime_bridge, "_load_runtime_module", lambda: runtime)
    monkeypatch.setattr(runtime_bridge, "_load_visible_profile_context", lambda: None)
    model_calls = []

    def invoke(**kwargs):
        model_calls.append(kwargs)
        return {
            "status": "ok", "allowed": True, "stayed_local": True,
            "selected_role": "primary_general", "selected_runtime": "ollama",
            "response_text": "Local synthesis from the governed receipt.",
            "used_fallback": False,
        }

    monkeypatch.setattr(runtime, "invoke_model", invoke)
    # Keep real query preparation, guarding, and Request construction. Only the
    # HTTP transport is replaced; no test payload leaves the process.
    outbound = []

    def capture_http(request, **kwargs):
        outbound.append({"url": request.full_url, "data": request.data,
                         "headers": dict(request.header_items())})
        return b'{"results": []}'

    config = worker.load_searxng_worker_config()
    config.service["enabled"] = True
    monkeypatch.setattr(worker, "load_searxng_worker_config", lambda *_a, **_k: config)
    monkeypatch.setattr(client, "_cancellable_loopback_get", capture_http)
    message = "Compute descriptive statistics for the selected dataset."
    if public_research:
        message += " Search the public web for GeoJSON guidance."
    result = runtime_bridge.send_chat_request({
        "message": message, "requested_mode": "researcher",
        "request_id": f"req_scientific_handoff_{approved}_{public_research}",
        "project_id": project_id,
        "request_context": {"scientific_workspace_selection": {
            "workspace_root": str(root), "relative_path": "measurements.csv",
            "operation": "descriptive_stats", "columns": ["value"],
        }},
    })
    data = result["data"]
    science = data["scientific_execution"]
    assert science["used"] is True, science
    assert science["status"] == ("completed" if approved else "blocked"), science
    assert model_calls
    assert "Governed ScientificForge result:" in model_calls[0]["context_summary"]
    assert str(root) not in model_calls[0]["context_summary"]
    assert str(root) not in json.dumps(captured["log_payload"])
    from app.api.request_trace_service import get_request_trace_record

    trace = get_request_trace_record(result["request_id"])["snapshot"]
    science_tool = next(item for item in trace["tools_used"]
                        if item["tool_key"] == "scientificforge")
    assert science_tool["state"] == science["status"]
    assert science_tool["network_access_used"] is False
    assert str(root) not in json.dumps(trace)
    if approved:
        assert science_tool["operation_id"] == science["scientific_job_id"]
        assert science_tool["result_hash"] == science["provenance"]["result_sha256"]
    if approved:
        assert science["result"]["statistics"]["count"] == 2
        assert science["result"]["statistics"]["mean"] == 2.0
        assert science["provenance"]["source_sha256"]
        assert any(item["kind"] == "scientific_result" for item in data["artifacts"])
    else:
        assert "scientific_workspace_not_approved" in science["errors"]
        assert data["artifacts"] == []
    if public_research:
        assert outbound
        assert data["research"]["searxng_used"] is True
        assert "GeoJSON" in json.dumps(outbound)
        for private in (str(root), canary, "measurements.csv"):
            assert private not in json.dumps(outbound)
    else:
        assert outbound == []
