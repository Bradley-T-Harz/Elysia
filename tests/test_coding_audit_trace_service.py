from __future__ import annotations

import asyncio
import stat

from app.api.coding_audit_service import coding_audit_root, get_coding_audit_record, list_coding_audit_records, write_coding_audit_record
from app.api.coding_trace_service import coding_request_id
from app.api.request_trace_service import get_request_trace_record
from app.api.routes.request_trace import get_recent_request_traces


def test_coding_audit_is_compact_and_joins_request_trace():
    operation_id = "operation_test_001"
    payload = {
        "session_id": "session_001",
        "approval_id": "approval_001",
        "operation": "patch_apply",
        "target_relative_path": "src/app.py",
        "source_hash": "source-hash",
        "plan_hash": "plan-hash",
        "new_hash": "result-hash",
        "operator_approved": True,
        "raw_content": "THIS MUST NEVER SURFACE",
        "details": {"secret": "THIS MUST NEVER SURFACE"},
    }

    assert write_coding_audit_record("patch_apply", operation_id, payload) is True

    compact = get_coding_audit_record(operation_id)
    assert compact is not None
    assert compact["payload"]["target_relative_path"] == "src/app.py"
    assert compact["target_relative_path"] == "src/app.py"
    assert "raw_content" not in compact["payload"]
    assert "details" not in compact["payload"]
    request_id = coding_request_id(operation_id, "approval_001")
    assert compact["request_id"] == request_id

    trace = get_request_trace_record(request_id)
    assert trace is not None
    tool = trace["snapshot"]["tools_used"][0]
    assert tool["operation_id"] == operation_id
    assert tool["approval_id"] == "approval_001"
    assert tool["relative_paths"] == ["src/app.py"]
    assert tool["source_hash"] == "source-hash"
    assert tool["plan_hash"] == "plan-hash"
    assert tool["result_hash"] == "result-hash"
    assert tool["audit_persisted"] is True


def test_coding_audit_list_is_bounded_and_sanitized():
    for index in range(3):
        write_coding_audit_record("file_operation", f"operation_{index}", {"relative_path": f"file-{index}.txt", "raw_content": "private"})

    records = list_coding_audit_records(limit=2, kind="file_operation")

    assert len(records) == 2
    assert all("raw_content" not in record["payload"] for record in records)


def test_coding_audit_files_and_directory_are_owner_private():
    assert write_coding_audit_record("repo_approval", "operation_private_001", {}) is True

    root = coding_audit_root()
    record = root / "repo_approval_operation_private_001.json"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(record.stat().st_mode) == 0o600

    root.chmod(0o775)
    record.chmod(0o664)
    assert write_coding_audit_record("file_preview", "operation_private_002", {}) is True

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(record.stat().st_mode) == 0o600


def test_recent_request_trace_surface_lists_sanitized_coding_operation():
    operation_id = "operation_recent_001"
    write_coding_audit_record(
        "file_operation",
        operation_id,
        {
            "approval_id": "approval_recent_001",
            "operation_kind": "delete",
            "target_relative_path": "src/old.txt",
            "source_hash": "source-hash",
            "raw_content": "must-not-surface",
        },
    )

    envelope = asyncio.run(get_recent_request_traces(project_id=None, conversation_id=None, limit=50))

    summaries = envelope["data"]["request_traces"]
    assert any(item["request_id"] == coding_request_id(operation_id, "approval_recent_001") for item in summaries)
    assert "must-not-surface" not in str(envelope)
