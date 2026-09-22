"""A typed workflow must survive the real chat bridge, receipts and artifacts."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.usefixtures("isolated_scientific_compute")

from tests.test_runtime_invoker_integration import base_configs, runtime_skills


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
def test_scientific_interpretation_preserves_admitted_telemetry_requirement(
    isolated_account_store, monkeypatch, base_configs, runtime_skills, device,
):
    from dataclasses import replace
    from app.api import runtime_bridge
    from core import runtime
    from tests.test_runtime_invoker_integration import _install_runtime_environment
    _install_runtime_environment(monkeypatch, base_configs, runtime_skills)
    monkeypatch.setattr(runtime_bridge, "_load_runtime_module", lambda: runtime)
    monkeypatch.setattr(runtime_bridge, "_load_visible_profile_context", lambda: None)
    # Exercise the consumer of an admitted placement. Actual GPU admission is
    # covered by the governor tests; this fixture must not allocate a real GPU.
    admission = runtime.decide_compute
    monkeypatch.setattr(runtime, "decide_compute", lambda *a, **k:
        replace(admission(*a, **k), selected_device=device))
    calls = []
    def invoke(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "allowed": True, "stayed_local": True,
                "response_text": "{}", "used_fallback": False}
    monkeypatch.setattr(runtime, "invoke_model", invoke)
    runtime_bridge.send_chat_request({
        "message": "Use a scientific workflow to solve 2*x + y = 5 and x + 3*y = 7.",
        "requested_mode": "researcher", "request_id": "req_telemetry_placement_bridge",
    })
    assert len(calls) == 2
    assert calls[0].get("scientific_schema") and not calls[1].get("scientific_schema")
    assert all(call["limits"].require_gpu is (device == "cuda:0") for call in calls)


def test_formulation_resource_cutoff_never_starts_interpretation(
    isolated_account_store, monkeypatch, base_configs, runtime_skills,
):
    from app.api import runtime_bridge
    from core import runtime
    from tests.test_runtime_invoker_integration import _install_runtime_environment
    _install_runtime_environment(monkeypatch, base_configs, runtime_skills)
    monkeypatch.setattr(runtime_bridge, "_load_runtime_module", lambda: runtime)
    monkeypatch.setattr(runtime_bridge, "_load_visible_profile_context", lambda: None)
    calls = []
    def invoke(**kwargs):
        calls.append(kwargs)
        return {"status": "error", "provider_metadata": {"resource_limited": True},
                "block_reasons": ["local_resource_safety_cutoff"]}
    monkeypatch.setattr(runtime, "invoke_model", invoke)
    response = runtime_bridge.send_chat_request({
        "message": "Use a scientific workflow to solve 2*x + y = 5 and x + 3*y = 7.",
        "requested_mode": "researcher", "request_id": "req_resource_cutoff_bridge",
    })
    science = response["data"]["scientific_execution"]
    assert len(calls) == 1 and calls[0].get("scientific_schema")
    assert science["reason"] == "scientific_formulation_resource_limited"
    assert science["interpretation_status"] == "resource_limited"
    assert science["node_receipts"] == []
    assert not science["used"]


@pytest.mark.parametrize("later_node_fails,cancel_interpretation", [(False, False), (True, False), (False, True)])
def test_chat_bridge_executes_and_records_verified_nodes(
    isolated_account_store, monkeypatch, base_configs, runtime_skills,
    later_node_fails, cancel_interpretation,
):
    from app.api import runtime_bridge
    from app.api.request_trace_service import get_request_trace_record
    from core import runtime
    from tests.test_runtime_invoker_integration import _install_runtime_environment

    _install_runtime_environment(monkeypatch, base_configs, runtime_skills)
    monkeypatch.setattr(runtime_bridge, "_load_runtime_module", lambda: runtime)
    monkeypatch.setattr(runtime_bridge, "_load_visible_profile_context", lambda: None)
    workflow = {
        "ir_version": "scientific-ir-v0.2", "nodes": [{
            "node_id": "solve", "operation": "solve_linear_system",
            "inputs": {
                "matrix": {"kind": "literal", "value": [[2, 1], [1, 3]], "provenance": "user"},
                "rhs": {"kind": "literal", "value": [5, 7], "provenance": "user"},
            }, "verification": ["residual"],
        }], "outputs": [{"node_id": "solve", "port": "solution"}],
    }
    if later_node_fails:
        workflow["nodes"].append({
            "node_id": "singular", "operation": "solve_linear_system",
            "inputs": {
                "matrix": {"kind": "literal", "value": [[1, 1], [1, 1]], "provenance": "user"},
                "rhs": {"kind": "literal", "value": [1, 2], "provenance": "user"},
            },
        })
        workflow["outputs"].append({"node_id": "singular", "port": "solution"})
    calls = []

    def invoke(**kwargs):
        calls.append(kwargs)
        if cancel_interpretation and not kwargs.get("scientific_schema"):
            from app.cognition import emergency_control
            from app.ownership import current_user_id
            # Cancel the actual authenticated request after completed child execution.
            assert emergency_control.cancel_request("req_scientific_v02_bridge_complete", current_user_id())
            assert kwargs["cancel_check"]()
        response_text = (json.dumps({"status": "proposed", "workflow": workflow})
                         if kwargs.get("scientific_schema") else
                         "The governed ScientificForge receipt gives the linear-system result.")
        return {
            "status": "ok", "allowed": True, "stayed_local": True,
            "selected_role": "primary_general", "selected_runtime": "ollama",
            "response_text": response_text, "used_fallback": False,
        }

    monkeypatch.setattr(runtime, "invoke_model", invoke)
    message = "Use a scientific workflow to solve the linear system with matrix [[2,1],[1,3]] and rhs [5,7]."
    if later_node_fails:
        message += " Then solve a second system with matrix [[1,1],[1,1]] and rhs [1,2]."
    if cancel_interpretation:
        from app.cognition.emergency_control import bind_request_owner
        from app.ownership import current_user_id
        # The authenticated HTTP route normally establishes this parent ownership.
        bind_request_owner("req_scientific_v02_bridge_complete", current_user_id())
    response = runtime_bridge.send_chat_request({
        "message": message, "requested_mode": "researcher",
        "request_id": "req_scientific_v02_bridge_partial" if later_node_fails else "req_scientific_v02_bridge_complete",
    })
    data = response["data"]
    science = data["scientific_execution"]
    assert science["protocol_version"] == "scientific-ir-v0.2"
    assert science["status"] == ("cancelled" if cancel_interpretation else "failed" if later_node_fails else "completed"), science
    assert science["completed_node_count"] == 1
    assert science["node_receipts"][0]["verification"] == "passed"
    assert science["node_receipts"][0]["result"]["solution"] == pytest.approx([1.6, 1.8])
    assert len(calls) == 2
    assert calls[0].get("scientific_schema") is not None
    assert calls[1].get("scientific_schema") is None
    assert "Governed ScientificForge workflow receipt" in calls[1]["context_summary"]
    assert science["partial_completion"] is (later_node_fails or cancel_interpretation)
    if cancel_interpretation:
        assert science["interpretation_status"] == "cancelled"
        assert science["outputs"] == {}
    assert len([item for item in data["artifacts"] if item["kind"] == "scientific_result"]) == 1
    from app.api.artifact_service import get_artifact_detail
    artifact = next(item for item in data["artifacts"] if item["kind"] == "scientific_result")
    detail = get_artifact_detail(artifact["artifact_id"])
    assert detail.safe_preview["verification"] == "passed"
    assert detail.safe_preview["diagnostics"]["residual"] == 0
    assert detail.safe_preview["resource_controls"]["native_threads"] == 1
    assert detail.safe_preview["workflow_id"] == science["workflow_id"]
    trace = get_request_trace_record(response["request_id"])["snapshot"]
    workflow_tool = next(item for item in trace["tools_used"] if item["tool_key"] == "scientificforge_workflow")
    assert workflow_tool["state"] == science["status"]
    assert workflow_tool["network_access_used"] is False
    node_tools = [item for item in trace["tools_used"] if item["tool_key"] == "scientificforge"]
    assert len(node_tools) == (2 if later_node_fails else 1)
    assert node_tools[0]["result_hash"] == science["node_receipts"][0]["result_sha256"]


@pytest.mark.parametrize("invalid_kind,expected_reason", [
    ("structure", "scientific_formulation_invalid"),
    ("dimensions", "dimension_mismatch"),
])
def test_chat_bridge_rejects_invalid_ir_before_any_worker_or_artifact(
    isolated_account_store, monkeypatch, base_configs, runtime_skills,
    invalid_kind, expected_reason,
):
    from app.api import runtime_bridge, scientific_workflow_service
    from app.api.request_trace_service import get_request_trace_record
    from core import runtime
    from tests.test_runtime_invoker_integration import _install_runtime_environment

    _install_runtime_environment(monkeypatch, base_configs, runtime_skills)
    monkeypatch.setattr(runtime_bridge, "_load_runtime_module", lambda: runtime)
    monkeypatch.setattr(runtime_bridge, "_load_visible_profile_context", lambda: None)
    launches = []
    monkeypatch.setattr(scientific_workflow_service, "run_scientific_worker_process",
                        lambda *args, **kwargs: launches.append((args, kwargs)))
    if invalid_kind == "structure":
        workflow = {"ir_version": "scientific-ir-v0.2", "nodes": [{
            "node_id": "n", "operation": "matrix_rank", "python": "print('untrusted')",
            "inputs": {"matrix": {"kind": "literal", "value": [[1]], "provenance": "user"}},
        }], "outputs": [{"node_id": "n", "port": "rank"}]}
    else:
        workflow = {"ir_version": "scientific-ir-v0.2", "nodes": [{
            "node_id": "n", "operation": "quantity_arithmetic", "arithmetic": "add",
            "unit": "meter", "target_unit": "second",
            "inputs": {"left": {"kind": "literal", "value": 2, "provenance": "user"},
                       "right": {"kind": "literal", "value": 3, "provenance": "user"}},
        }], "outputs": [{"node_id": "n", "port": "value"}]}

    def invoke(**kwargs):
        return {"status": "ok", "allowed": True, "stayed_local": True,
                "selected_role": "primary_general", "selected_runtime": "ollama",
                "response_text": json.dumps({"status": "proposed", "workflow": workflow})
                if kwargs.get("scientific_schema") else "No computation ran.",
                "used_fallback": False}

    monkeypatch.setattr(runtime, "invoke_model", invoke)
    response = runtime_bridge.send_chat_request({
        "message": "Use a scientific workflow to evaluate distance 2 meters plus elapsed time 3 seconds.",
        "requested_mode": "researcher", "request_id": "req_scientific_invalid_" + invalid_kind,
    })
    science = response["data"]["scientific_execution"]
    assert science["status"] == "blocked", science
    assert science["reason"] == expected_reason
    assert science.get("attempted_node_count", 0) == 0
    assert launches == []
    assert not [item for item in response["data"]["artifacts"] if item["kind"] == "scientific_result"]
    tools = get_request_trace_record(response["request_id"])["snapshot"]["tools_used"]
    workflow_tool = next(item for item in tools if item["tool_key"] == "scientificforge_workflow")
    assert workflow_tool["state"] == "blocked"
    assert workflow_tool["used"] is False
    assert expected_reason in workflow_tool["errors"]
