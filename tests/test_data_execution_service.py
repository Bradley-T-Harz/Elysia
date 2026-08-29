from pathlib import Path

import pytest

import core.data_executor as data_executor

from app.api.data_execution_service import (
    build_data_execution_context_block,
    run_data_execution,
)
from app.api.schemas.common import ApprovalState, LocalityState
from app.api.schemas.data_execution import (
    DataExecutionRequest,
    DataExecutionResult,
)
from app.api.schemas.execution import (
    ExecutionStatus,
    ExecutionToolKind,
)


def write_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_service_accepts_pydantic_request(tmp_path):
    csv_path = write_file(
        tmp_path / "sites.csv",
        "site,temperature_c,ph,notes\n"
        "A,12.5,7.1,clear\n"
        "B,18.5,7.3,\n"
        "C,20.0,7.6,cloudy\n",
    )

    request = DataExecutionRequest(source_path=str(csv_path))
    result = run_data_execution(request)

    assert isinstance(result, DataExecutionResult)
    assert result.ok is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.tool_kind == ExecutionToolKind.DATA_EXECUTOR
    assert result.operation == "summarize_csv"
    assert result.file_kind == "csv"
    assert result.row_count == 3
    assert result.column_count == 4
    assert result.columns == ["site", "temperature_c", "ph", "notes"]
    assert result.numeric_columns == ["temperature_c", "ph"]
    assert result.text_columns == ["site", "notes"]
    assert result.locality == LocalityState.LOCAL
    assert result.approval_state == ApprovalState.NOT_NEEDED
    assert result.network_access_used is False
    assert result.mutated_files is False
    assert result.errors == []


def test_service_accepts_plain_dict_request(tmp_path):
    csv_path = write_file(
        tmp_path / "measurements.csv",
        "site,value\nA,1\nB,2\n",
    )

    result = run_data_execution({"source_path": str(csv_path)})

    assert result.ok is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.row_count == 2
    assert result.column_count == 2
    assert result.numeric_columns == ["value"]


def test_service_preserves_missing_values_and_numeric_stats(tmp_path):
    csv_path = write_file(
        tmp_path / "missing.csv",
        "site,value_a,value_b\n"
        "A,1,\n"
        "B,NA,3\n"
        "C,null,4\n"
        "D,-,5\n",
    )

    result = run_data_execution({"source_path": str(csv_path)})

    assert result.ok is True
    assert result.missing_values_by_column == {
        "site": 0,
        "value_a": 3,
        "value_b": 1,
    }
    assert result.numeric_columns == ["value_a", "value_b"]
    assert result.numeric_stats["value_a"].count == 1
    assert result.numeric_stats["value_a"].missing == 3
    assert result.numeric_stats["value_b"].count == 3
    assert result.numeric_stats["value_b"].missing == 1
    assert result.numeric_stats["value_b"].mean == pytest.approx(4.0)


def test_unsupported_extension_is_blocked(tmp_path):
    text_path = write_file(tmp_path / "notes.txt", "a,b\n1,2\n")

    result = run_data_execution({"source_path": str(text_path)})

    assert result.ok is False
    assert result.status == ExecutionStatus.BLOCKED
    assert result.tool_kind == ExecutionToolKind.DATA_EXECUTOR
    assert "Unsupported data file type" in result.errors[0]


def test_missing_file_fails_safely(tmp_path):
    result = run_data_execution({"source_path": str(tmp_path / "missing.csv")})

    assert result.ok is False
    assert result.status == ExecutionStatus.FAILED
    assert "does not exist" in result.errors[0]


def test_invalid_request_returns_failed_schema_result():
    result = run_data_execution({"source_path": ""})

    assert result.ok is False
    assert result.status == ExecutionStatus.FAILED
    assert result.tool_kind == ExecutionToolKind.DATA_EXECUTOR
    assert result.operation == "summarize_csv"
    assert result.errors


def test_context_block_for_completed_result_includes_core_truth(tmp_path):
    csv_path = write_file(
        tmp_path / "sites.csv",
        "site,temperature_c,ph,notes\n"
        "A,12.5,7.1,clear\n"
        "B,18.5,7.3,\n"
        "C,20.0,7.6,cloudy\n",
    )

    result = run_data_execution({"source_path": str(csv_path)})
    context_block = build_data_execution_context_block(result)

    assert "Bounded local data execution result:" in context_block
    assert "Tool: data_executor" in context_block
    assert "Locality: local" in context_block
    assert "Approval required: no" in context_block
    assert "Status: completed" in context_block
    assert "Operation: summarize_csv" in context_block
    assert "File kind: csv" in context_block
    assert "Rows: 3" in context_block
    assert "Columns: 4" in context_block
    assert "Numeric columns: temperature_c, ph" in context_block
    assert "Missing values: notes: 1" in context_block
    assert "Boundary note:" in context_block


def test_context_block_for_blocked_result_includes_errors(tmp_path):
    text_path = write_file(tmp_path / "notes.txt", "a,b\n1,2\n")

    result = run_data_execution({"source_path": str(text_path)})
    context_block = build_data_execution_context_block(result)

    assert "Status: blocked" in context_block
    assert "Errors:" in context_block
    assert "Unsupported data file type" in context_block
    assert "Boundary note:" in context_block


def test_service_respects_limit_parameters(tmp_path):
    csv_path = write_file(
        tmp_path / "too_many.csv",
        "a,b\n1,2\n3,4\n5,6\n",
    )

    result = run_data_execution(
        {
            "source_path": str(csv_path),
            "max_rows": 2,
        }
    )

    assert result.ok is False
    assert result.status == ExecutionStatus.BLOCKED
    assert "row count exceeds" in result.errors[0]


def write_xlsx_file(path: Path, rows: list[list[object]]) -> Path:
    openpyxl = pytest.importorskip("openpyxl")

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Data"

    for row in rows:
        worksheet.append(row)

    workbook.save(path)
    workbook.close()

    return path


def test_service_accepts_xlsx_when_openpyxl_is_available(tmp_path):
    xlsx_path = write_xlsx_file(
        tmp_path / "sites.xlsx",
        [
            ["site", "temperature_c", "ph", "notes"],
            ["A", 12.5, 7.1, "clear"],
            ["B", 18.5, 7.3, None],
            ["C", 20.0, 7.6, "cloudy"],
        ],
    )

    result = run_data_execution({"source_path": str(xlsx_path)})

    assert isinstance(result, DataExecutionResult)
    assert result.ok is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.tool_kind == ExecutionToolKind.DATA_EXECUTOR
    assert result.operation == "summarize_csv"
    assert result.file_kind == "xlsx"
    assert result.row_count == 3
    assert result.column_count == 4
    assert result.numeric_columns == ["temperature_c", "ph"]
    assert result.text_columns == ["site", "notes"]
    assert result.missing_values_by_column["notes"] == 1
    assert result.locality == LocalityState.LOCAL
    assert result.approval_state == ApprovalState.NOT_NEEDED
    assert result.network_access_used is False
    assert result.mutated_files is False
    assert result.errors == []


def test_context_block_for_xlsx_includes_local_table_truth(tmp_path):
    xlsx_path = write_xlsx_file(
        tmp_path / "sites.xlsx",
        [
            ["site", "value"],
            ["A", 1],
            ["B", 2],
        ],
    )

    result = run_data_execution({"source_path": str(xlsx_path)})
    context_block = build_data_execution_context_block(result)

    assert "Bounded local data execution result:" in context_block
    assert "Tool: data_executor" in context_block
    assert "Locality: local" in context_block
    assert "Status: completed" in context_block
    assert "Operation: summarize_csv" in context_block
    assert "File kind: xlsx" in context_block
    assert "Rows: 2" in context_block
    assert "Columns: 2" in context_block
    assert "Numeric columns: value" in context_block
    assert "Boundary note:" in context_block
    assert "bounded local table inspection" in context_block


def test_service_surfaces_missing_openpyxl_for_xlsx(monkeypatch, tmp_path):
    xlsx_path = tmp_path / "workbook.xlsx"
    xlsx_path.write_bytes(b"pretend xlsx content")

    monkeypatch.setattr(
        data_executor,
        "_load_openpyxl_load_workbook",
        lambda: (None, "No module named 'openpyxl'"),
    )

    result = run_data_execution({"source_path": str(xlsx_path)})

    assert result.ok is False
    assert result.status == ExecutionStatus.BLOCKED
    assert result.tool_kind == ExecutionToolKind.DATA_EXECUTOR
    assert result.file_kind == "xlsx"
    assert "openpyxl" in result.errors[0]
    assert result.network_access_used is False
    assert result.mutated_files is False
