"""Exercise the real ledger producer -> strict user-facing summary boundary."""
import json
import uuid

import pytest

from app.api import runtime_bridge
from app.api.coding_trace_service import record_coding_trace
from app.api.request_trace_service import get_request_summary, start_request_trace
from app.api.schemas.artifacts import ArtifactSummary
from app.api.schemas.chat import ChatSendResponseData


def _summary(**fields):
    request_id = "req_contract_" + uuid.uuid4().hex
    chat = ChatSendResponseData(user_message="Synthetic ledger fixture", response_text="",
        response_source="scaffold_fallback", invocation_status="not_invoked", **fields)
    start_request_trace(request_id=request_id, route_used="tests")
    runtime_bridge._update_request_ledger_from_chat_data(request_id=request_id, chat_data=chat)
    result = get_request_summary({"request_id": request_id})
    assert result["status"] == "ok", result
    return result["data"]


@pytest.mark.parametrize("lane", ["math_execution", "data_execution", "repo_context", "code_patch_plan"])
@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_summary_retains_observed_execution_outcome(lane, status, isolated_account_store):
    data = _summary(**{lane: {"used": True, "status": status}})
    assert data["tools_used"][0]["state"] == status
    assert data["tools_used"][0]["used"] is True


def test_summary_retains_scientific_workspace_and_artifact_provenance(isolated_account_store):
    artifact = ArtifactSummary(artifact_id="artifact-science", kind="scientific_result",
        title="Synthetic scientific result", created_at_utc="2026-09-21T00:00:00Z",
        request_id="req-source", project_id="project-source", scientific_operation="descriptive_stats",
        scientific_job_id="job-science", parameter_sha256="a" * 64, result_sha256="b" * 64,
        source_sha256="c" * 64, workspace_root_hash="d" * 64)
    data = _summary(scientific_execution={"used": True, "status": "completed",
        "scientific_operation": "descriptive_stats", "scientific_job_id": "job-science",
        "source_type_id": "csv_table", "workspace_root_hash": "d" * 64,
        "workspace_root": "/private/ROOT_CANARY", "relative_path": "observations.csv",
        "provenance": {"parameter_sha256": "a" * 64, "result_sha256": "b" * 64,
                       "source_sha256": "c" * 64}}, artifacts=[artifact])
    tool = data["tools_used"][0]
    assert tool["boundary_kind"] == "approved_scientific_workspace"
    assert tool["parameter_hash"] == "a" * 64 and tool["source_type_id"] == "csv_table"
    assert data["artifacts"][0]["parameter_sha256"] == "a" * 64
    assert data["artifacts"][0]["scientific_job_id"] == "job-science"
    assert "ROOT_CANARY" not in json.dumps(data)


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "blocked",
                                    "clarification_required", "reference_required", "unsupported"])
def test_summary_preserves_workflow_and_independent_completed_node(status, isolated_account_store):
    executed = status in {"completed", "failed", "cancelled"}
    data = _summary(scientific_execution={"protocol_version": "scientific-ir-v0.2",
        "status": status, "used": executed, "attempted_node_count": int(executed),
        "completed_node_count": int(executed), "workflow_id": "workflow-example",
        "node_receipts": [{"status": "completed", "worker_attempted": True,
            "operation": "matrix_rank", "parameter_sha256": "a" * 64, "result": {"rank": 2}}]
            if executed else []})
    workflow = data["tools_used"][0]
    assert workflow["state"] == status and workflow["used"] is executed
    assert workflow["boundary_kind"] == "typed_scientific_workflow"
    if executed:
        assert data["tools_used"][1]["state"] == "completed"
    assert data["artifacts"] == []


@pytest.mark.parametrize("status", ["running", "completed", "cancelled"])
def test_existing_coding_trace_remains_readable_with_media_truth(status, isolated_account_store):
    request_id = record_coding_trace(kind="database_inspect", record_id=uuid.uuid4().hex,
        payload={"status": status, "model_id": "fixed-test-backend", "artifact_id": "artifact-test",
                 "runtime_seconds": 1.25, "peak_gpu_memory_mib": 12.5,
                 "synthetic_media": False, "raw_content_logged": False}, audit_persisted=True)
    result = get_request_summary({"request_id": request_id})
    assert result["status"] == "ok", result
    tool = result["data"]["tools_used"][0]
    assert tool["state"] == {"running": "pending", "completed": "used", "cancelled": "blocked"}[status]
    assert tool["boundary_kind"] == "private_snapshot_or_static_worker"
    assert tool["runtime_seconds"] == 1.25 and tool["peak_gpu_memory_mib"] == 12.5
    assert tool["raw_content_logged"] is False
