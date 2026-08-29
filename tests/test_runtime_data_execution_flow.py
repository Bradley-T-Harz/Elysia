from __future__ import annotations

from pathlib import Path

import pytest
from typing import Any

import core.runtime as runtime


def _write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _disable_runtime_side_effects(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        runtime,
        "write_runtime_log",
        lambda payload: tmp_path / "runtime_log.jsonl",
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


def _fake_invoke_model_factory(captured: dict[str, Any]):
    def fake_invoke_model(**kwargs):
        captured["kwargs"] = kwargs
        captured["message"] = kwargs.get("message")
        captured["context_summary"] = kwargs.get("context_summary", "")

        return {
            "status": "ok",
            "allowed": True,
            "stayed_local": True,
            "selected_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "fake-local-model",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "prompt_source": "runtime_data_execution_test",
            "response_text": (
                "I inspected the attached CSV locally and summarized its table shape."
            ),
            "error": "",
            "block_reasons": [],
            "unmet_requirements": [],
            "latency_ms": 0,
            "provider_metadata": {"mocked": True},
            "note": "Fake invoker used by runtime data execution tests.",
        }

    return fake_invoke_model


def _context_with_ready_attached_csv(message: str, csv_path: Path) -> dict[str, Any]:
    return {
        "request_summary": message,
        "retrieved_memory_count": 0,
        "retrieval_mode": "none",
        "attached_data_files": [
            {
                "file_id": "file_sites_001",
                "file_name": csv_path.name,
                "source_path": str(csv_path),
                "file_kind": "csv",
                "ready": True,
                "usable_as_context": True,
                "blocked": False,
                "processing_state": "ready",
            }
        ],
    }


def _context_without_attached_files(message: str) -> dict[str, Any]:
    return {
        "request_summary": message,
        "retrieved_memory_count": 0,
        "retrieval_mode": "none",
        "attached_data_files": [],
    }


def test_runtime_data_request_uses_bounded_local_data_execution(
    monkeypatch,
    tmp_path,
):
    _disable_runtime_side_effects(monkeypatch, tmp_path)

    csv_path = _write_csv(
        tmp_path / "sites.csv",
        "site,temperature_c,ph,notes\n"
        "A,12.5,7.1,clear\n"
        "B,18.5,7.3,\n"
        "C,20.0,7.6,cloudy\n",
    )

    captured_invocation: dict[str, Any] = {}

    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: (
            _context_with_ready_attached_csv(message, csv_path)
        ),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        "Summarize the attached CSV and show the basic table facts.",
        runtime.SessionState(active_mode="researcher"),
    )

    data_execution = result["data_execution"]

    assert result["status"] == "ok_local_runtime"
    assert result["plan"]["bounded_data_execution_candidate"] is True
    assert result["plan"]["data_execution_operation"] == "summarize_csv"
    assert result["plan"]["data_execution_source_kind"] == "attached_file"
    assert result["plan"]["data_execution_source_path"] == str(csv_path)
    assert result["plan"]["data_execution_file_id"] == "file_sites_001"
    assert result["plan"]["data_execution_file_name"] == "sites.csv"
    assert result["plan"]["execution_allowed"] is False
    assert result["plan"]["requires_tools"] is False
    assert result["plan"]["touches_external_network"] is False
    assert result["plan"]["writes_files"] is False

    assert result["policy_review"]["allowed"] is True
    assert result["policy_review"]["approval_required"] is False
    assert "bounded_local_data_execution" in result["policy_review"]["boundary_flags"]

    assert data_execution["used"] is True
    assert data_execution["status"] == "completed"
    assert data_execution["tool_kind"] == "data_executor"
    assert data_execution["operation"] == "summarize_csv"
    assert data_execution["source_kind"] == "attached_file"
    assert data_execution["file_id"] == "file_sites_001"
    assert data_execution["file_name"] == "sites.csv"
    assert data_execution["file_kind"] == "csv"
    assert data_execution["row_count"] == 3
    assert data_execution["column_count"] == 4
    assert data_execution["columns"] == ["site", "temperature_c", "ph", "notes"]
    assert data_execution["numeric_columns"] == ["temperature_c", "ph"]
    assert data_execution["text_columns"] == ["site", "notes"]
    assert data_execution["missing_values_by_column"]["notes"] == 1
    assert data_execution["stayed_local"] is True
    assert data_execution["approval_required"] is False
    assert data_execution["network_access_used"] is False
    assert data_execution["mutated_files"] is False
    assert data_execution["errors"] == []

    assert result["internal_result"]["data_execution"] == data_execution
    assert result["response"]["data_execution"] == data_execution
    assert result["verification"]["verified"] is True
    assert (
        "data_execution_completed_with_table_shape"
        in result["verification"]["checks_passed"]
    )

    context_summary = captured_invocation["context_summary"]
    assert "Bounded local data execution result:" in context_summary
    assert "Tool: data_executor" in context_summary
    assert "Status: completed" in context_summary
    assert "Operation: summarize_csv" in context_summary
    assert "Rows: 3" in context_summary
    assert "Columns: 4" in context_summary
    assert "Numeric columns: temperature_c, ph" in context_summary
    assert "Missing values: notes: 1" in context_summary
    assert "Boundary note:" in context_summary
    assert "not arbitrary Python" in context_summary
    assert "file mutation" in context_summary

    assert any(
        "Bounded local data inspection was used"
        in caveat
        for caveat in result["response"]["caveats"]
    )


def test_runtime_normal_chat_does_not_run_data_execution(monkeypatch, tmp_path):
    _disable_runtime_side_effects(monkeypatch, tmp_path)

    csv_path = _write_csv(
        tmp_path / "sites.csv",
        "site,value\nA,1\nB,2\n",
    )

    captured_invocation: dict[str, Any] = {}

    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: (
            _context_with_ready_attached_csv(message, csv_path)
        ),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        "Hello. How are you today?",
        runtime.SessionState(active_mode="default"),
    )

    assert result["plan"]["bounded_data_execution_candidate"] is False
    assert result["plan"]["data_execution_reason"] == ""
    assert "bounded_local_data_execution" not in result["policy_review"]["boundary_flags"]

    data_execution = result["data_execution"]
    assert data_execution["used"] is False
    assert data_execution["status"] == "not_needed"
    assert data_execution["tool_kind"] == "data_executor"
    assert data_execution["row_count"] == 0
    assert data_execution["column_count"] == 0
    assert data_execution["errors"] == []

    context_summary = captured_invocation["context_summary"]
    assert "Bounded local data execution result:" not in context_summary
    assert "Mode-specific bounded data response guidance:" not in context_summary
    assert result["verification"]["verified"] is True
    assert "data_execution_not_required" in result["verification"]["checks_passed"]


def test_runtime_data_request_without_ready_attached_csv_does_not_run(
    monkeypatch,
    tmp_path,
):
    _disable_runtime_side_effects(monkeypatch, tmp_path)

    captured_invocation: dict[str, Any] = {}

    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: (
            _context_without_attached_files(message)
        ),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        "Summarize the attached CSV and show missing values.",
        runtime.SessionState(active_mode="researcher"),
    )

    assert result["plan"]["bounded_data_execution_candidate"] is False
    assert (
        result["plan"]["data_execution_reason"]
        == "data_summary_requested_but_no_ready_attached_data_file"
    )
    assert result["plan"]["data_execution_source_path"] == ""
    assert "bounded_local_data_execution" not in result["policy_review"]["boundary_flags"]

    data_execution = result["data_execution"]
    assert data_execution["used"] is False
    assert data_execution["status"] == "not_needed"
    assert data_execution["errors"] == []

    context_summary = captured_invocation["context_summary"]
    assert "Bounded local data execution result:" not in context_summary
    assert result["verification"]["verified"] is True
    assert "data_execution_not_required" in result["verification"]["checks_passed"]


def test_runtime_data_execution_failure_is_surfaced_safely(
    monkeypatch,
    tmp_path,
):
    _disable_runtime_side_effects(monkeypatch, tmp_path)

    missing_csv_path = tmp_path / "missing.csv"
    captured_invocation: dict[str, Any] = {}

    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: (
            _context_with_ready_attached_csv(message, missing_csv_path)
        ),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        "Summarize the attached CSV.",
        runtime.SessionState(active_mode="researcher"),
    )

    data_execution = result["data_execution"]

    assert result["plan"]["bounded_data_execution_candidate"] is True
    assert "bounded_local_data_execution" in result["policy_review"]["boundary_flags"]

    assert data_execution["used"] is True
    assert data_execution["status"] == "failed"
    assert data_execution["tool_kind"] == "data_executor"
    assert data_execution["operation"] == "summarize_csv"
    assert data_execution["file_id"] == "file_sites_001"
    assert data_execution["file_name"] == "missing.csv"
    assert data_execution["stayed_local"] is True
    assert data_execution["approval_required"] is False
    assert data_execution["network_access_used"] is False
    assert data_execution["mutated_files"] is False
    assert data_execution["errors"]
    assert "does not exist" in data_execution["errors"][0]

    assert result["verification"]["verified"] is True
    assert "data_execution_failure_has_errors" in result["verification"]["checks_passed"]

    context_summary = captured_invocation["context_summary"]
    assert "Bounded local data execution result:" in context_summary
    assert "Status: failed" in context_summary
    assert "Errors:" in context_summary
    assert "does not exist" in context_summary
    assert "Boundary note:" in context_summary

    assert any(
        "Bounded local data inspection was attempted but did not complete successfully"
        in caveat
        for caveat in result["response"]["caveats"]
    )



def test_runtime_request_context_attached_csv_reaches_bounded_data_execution(
    monkeypatch,
    tmp_path,
):
    _disable_runtime_side_effects(monkeypatch, tmp_path)

    csv_path = _write_csv(
        tmp_path / "bridge_sites.csv",
        "site,pm25,category\n"
        "A,7.5,low\n"
        "B,15.0,moderate\n"
        "C,,missing\n",
    )

    captured_invocation: dict[str, Any] = {}

    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: (
            _context_without_attached_files(message)
        ),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        "Summarize the attached CSV. Give rows, columns, missing values, and basic stats.",
        runtime.SessionState(active_mode="researcher"),
        request_context={
            "attached_file_ids": ["file_bridge_sites_001"],
            "attached_files_are_memory": False,
            "attached_files_source": "user_selected_local_files",
            "attached_data_files": [
                {
                    "file_id": "file_bridge_sites_001",
                    "file_name": csv_path.name,
                    "display_name": csv_path.name,
                    "source_kind": "attached_file",
                    "source_path": str(csv_path),
                    "file_kind": "csv",
                    "ready": True,
                    "usable_as_context": True,
                    "blocked": False,
                    "processing_state": "ready",
                    "memory_posture": "not_memory",
                }
            ],
        },
    )

    data_execution = result["data_execution"]

    assert result["plan"]["bounded_data_execution_candidate"] is True
    assert result["plan"]["data_execution_operation"] == "summarize_csv"
    assert result["plan"]["data_execution_source_kind"] == "attached_file"
    assert result["plan"]["data_execution_source_path"] == str(csv_path)
    assert result["plan"]["data_execution_file_id"] == "file_bridge_sites_001"
    assert result["plan"]["data_execution_file_name"] == "bridge_sites.csv"

    assert result["policy_review"]["allowed"] is True
    assert result["policy_review"]["approval_required"] is False
    assert "bounded_local_data_execution" in result["policy_review"]["boundary_flags"]

    assert data_execution["used"] is True
    assert data_execution["status"] == "completed"
    assert data_execution["tool_kind"] == "data_executor"
    assert data_execution["operation"] == "summarize_csv"
    assert data_execution["source_kind"] == "attached_file"
    assert data_execution["file_id"] == "file_bridge_sites_001"
    assert data_execution["file_name"] == "bridge_sites.csv"
    assert data_execution["row_count"] == 3
    assert data_execution["column_count"] == 3
    assert data_execution["columns"] == ["site", "pm25", "category"]
    assert data_execution["numeric_columns"] == ["pm25"]
    assert data_execution["missing_values_by_column"]["pm25"] == 1
    assert data_execution["stayed_local"] is True
    assert data_execution["approval_required"] is False
    assert data_execution["network_access_used"] is False
    assert data_execution["mutated_files"] is False
    assert data_execution["errors"] == []

    context_summary = captured_invocation["context_summary"]

    assert "Bounded local data execution result:" in context_summary
    assert "Tool: data_executor" in context_summary
    assert "Status: completed" in context_summary
    assert "Operation: summarize_csv" in context_summary
    assert "Rows: 3" in context_summary
    assert "Columns: 3" in context_summary
    assert "Numeric columns: pm25" in context_summary
    assert "Missing values: pm25: 1" in context_summary
    assert "Boundary note:" in context_summary
    assert "not arbitrary Python" in context_summary
    assert "file mutation" in context_summary

    assert result["verification"]["verified"] is True
    assert (
        "data_execution_completed_with_table_shape"
        in result["verification"]["checks_passed"]
    )


def _write_xlsx(path: Path, rows: list[list[object]]) -> Path:
    openpyxl = pytest.importorskip("openpyxl")

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Data"

    for row in rows:
        worksheet.append(row)

    workbook.save(path)
    workbook.close()

    return path


def test_runtime_request_context_attached_xlsx_reaches_bounded_data_execution(
    monkeypatch,
    tmp_path,
):
    _disable_runtime_side_effects(monkeypatch, tmp_path)

    xlsx_path = _write_xlsx(
        tmp_path / "bridge_sites.xlsx",
        [
            ["site", "pm25", "category"],
            ["A", 7.5, "low"],
            ["B", 15.0, "moderate"],
            ["C", None, "missing"],
        ],
    )

    captured_invocation: dict[str, Any] = {}

    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: (
            _context_without_attached_files(message)
        ),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        "Summarize the attached CSV/XLSX data file. Give rows, columns, missing values, and basic stats.",
        runtime.SessionState(active_mode="researcher"),
        request_context={
            "attached_file_ids": ["file_bridge_sites_xlsx_001"],
            "attached_files_are_memory": False,
            "attached_files_source": "user_selected_local_files",
            "attached_data_files": [
                {
                    "file_id": "file_bridge_sites_xlsx_001",
                    "file_name": xlsx_path.name,
                    "display_name": xlsx_path.name,
                    "source_kind": "attached_file",
                    "source_path": str(xlsx_path),
                    "file_kind": "xlsx",
                    "ready": True,
                    "usable_as_context": True,
                    "blocked": False,
                    "processing_state": "ready",
                    "memory_posture": "not_memory",
                }
            ],
        },
    )

    data_execution = result["data_execution"]

    assert result["plan"]["bounded_data_execution_candidate"] is True
    assert result["plan"]["data_execution_operation"] == "summarize_csv"
    assert result["plan"]["data_execution_source_kind"] == "attached_file"
    assert result["plan"]["data_execution_source_path"] == str(xlsx_path)
    assert result["plan"]["data_execution_file_id"] == "file_bridge_sites_xlsx_001"
    assert result["plan"]["data_execution_file_name"] == "bridge_sites.xlsx"

    assert result["policy_review"]["allowed"] is True
    assert result["policy_review"]["approval_required"] is False
    assert "bounded_local_data_execution" in result["policy_review"]["boundary_flags"]

    assert data_execution["used"] is True
    assert data_execution["status"] == "completed"
    assert data_execution["tool_kind"] == "data_executor"
    assert data_execution["operation"] == "summarize_csv"
    assert data_execution["source_kind"] == "attached_file"
    assert data_execution["file_id"] == "file_bridge_sites_xlsx_001"
    assert data_execution["file_name"] == "bridge_sites.xlsx"
    assert data_execution["file_kind"] == "xlsx"
    assert data_execution["row_count"] == 3
    assert data_execution["column_count"] == 3
    assert data_execution["columns"] == ["site", "pm25", "category"]
    assert data_execution["numeric_columns"] == ["pm25"]
    assert data_execution["missing_values_by_column"]["pm25"] == 1
    assert data_execution["stayed_local"] is True
    assert data_execution["approval_required"] is False
    assert data_execution["network_access_used"] is False
    assert data_execution["mutated_files"] is False
    assert data_execution["errors"] == []

    context_summary = captured_invocation["context_summary"]

    assert "Bounded local data execution result:" in context_summary
    assert "Tool: data_executor" in context_summary
    assert "Status: completed" in context_summary
    assert "Operation: summarize_csv" in context_summary
    assert "File kind: xlsx" in context_summary
    assert "Rows: 3" in context_summary
    assert "Columns: 3" in context_summary
    assert "Numeric columns: pm25" in context_summary
    assert "Missing values: pm25: 1" in context_summary
    assert "Boundary note:" in context_summary
    assert "not arbitrary Python" in context_summary
    assert "file mutation" in context_summary

    assert result["verification"]["verified"] is True
    assert (
        "data_execution_completed_with_table_shape"
        in result["verification"]["checks_passed"]
    )
