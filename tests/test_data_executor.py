from pathlib import Path

import pytest

import core.data_executor as data_executor

from core.data_executor import (
    DATA_EXECUTOR_TOOL_KIND,
    DATA_OPERATION_SUMMARIZE_CSV,
    DataExecutionStatus,
    summarize_csv_file,
    summarize_data_file,
    summarize_xlsx_file,
)


def write_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_valid_csv_summary_reports_shape_columns_and_boundary_truth(tmp_path):
    csv_path = write_file(
        tmp_path / "sites.csv",
        "site,temperature_c,ph,notes\n"
        "A,12.5,7.1,clear\n"
        "B,18.5,7.3,\n"
        "C,20.0,7.6,cloudy\n",
    )

    result = summarize_csv_file(csv_path)

    assert result.ok is True
    assert result.status == DataExecutionStatus.COMPLETED
    assert result.tool_kind == DATA_EXECUTOR_TOOL_KIND
    assert result.operation == DATA_OPERATION_SUMMARIZE_CSV
    assert result.file_kind == "csv"
    assert result.row_count == 3
    assert result.column_count == 4
    assert result.columns == ["site", "temperature_c", "ph", "notes"]
    assert result.numeric_columns == ["temperature_c", "ph"]
    assert result.text_columns == ["site", "notes"]
    assert result.missing_values_by_column["notes"] == 1
    assert len(result.preview_rows) == 3
    assert result.locality == "local"
    assert result.approval_required is False
    assert result.network_access_used is False
    assert result.mutated_files is False
    assert result.errors == []


def test_numeric_stats_are_computed_for_numeric_columns(tmp_path):
    csv_path = write_file(
        tmp_path / "measurements.csv",
        "site,temperature_c,ph\n"
        "A,12.5,7.1\n"
        "B,18.5,7.3\n"
        "C,20.0,7.6\n",
    )

    result = summarize_csv_file(csv_path)

    temperature = result.numeric_stats["temperature_c"]
    assert temperature["count"] == 3
    assert temperature["missing"] == 0
    assert temperature["min"] == 12.5
    assert temperature["max"] == 20.0
    assert temperature["mean"] == pytest.approx(17.0)

    ph = result.numeric_stats["ph"]
    assert ph["count"] == 3
    assert ph["min"] == 7.1
    assert ph["max"] == 7.6
    assert ph["mean"] == pytest.approx((7.1 + 7.3 + 7.6) / 3)


def test_missing_values_are_counted_and_missing_tokens_remain_numeric_when_safe(tmp_path):
    csv_path = write_file(
        tmp_path / "missing.csv",
        "site,value_a,value_b\n"
        "A,1,\n"
        "B,NA,3\n"
        "C,null,4\n"
        "D,-,5\n",
    )

    result = summarize_csv_file(csv_path)

    assert result.ok is True
    assert result.missing_values_by_column == {
        "site": 0,
        "value_a": 3,
        "value_b": 1,
    }
    assert result.numeric_columns == ["value_a", "value_b"]
    assert result.numeric_stats["value_a"]["count"] == 1
    assert result.numeric_stats["value_a"]["missing"] == 3
    assert result.numeric_stats["value_b"]["count"] == 3
    assert result.numeric_stats["value_b"]["missing"] == 1


def test_text_columns_are_identified(tmp_path):
    csv_path = write_file(
        tmp_path / "mixed.csv",
        "site,category,value\n"
        "A,riparian,1.5\n"
        "B,dryland,2.5\n",
    )

    result = summarize_csv_file(csv_path)

    assert result.numeric_columns == ["value"]
    assert result.text_columns == ["site", "category"]


def test_preview_rows_are_limited_but_row_count_is_complete(tmp_path):
    rows = ["index,value"]
    rows.extend(f"{index},{index * 2}" for index in range(10))
    csv_path = write_file(tmp_path / "many_rows.csv", "\n".join(rows) + "\n")

    result = summarize_csv_file(csv_path, preview_row_limit=5)

    assert result.ok is True
    assert result.row_count == 10
    assert len(result.preview_rows) == 5
    assert result.preview_rows[0] == {"index": "0", "value": "0"}


def test_unsupported_extension_is_blocked(tmp_path):
    text_path = write_file(tmp_path / "notes.txt", "a,b\n1,2\n")

    result = summarize_data_file(text_path)

    assert result.ok is False
    assert result.status == DataExecutionStatus.BLOCKED
    assert "Unsupported data file type" in result.errors[0]


def test_missing_file_fails_safely(tmp_path):
    result = summarize_csv_file(tmp_path / "missing.csv")

    assert result.ok is False
    assert result.status == DataExecutionStatus.FAILED
    assert "does not exist" in result.errors[0]


def test_directory_path_is_blocked(tmp_path):
    result = summarize_csv_file(tmp_path)

    assert result.ok is False
    assert result.status == DataExecutionStatus.BLOCKED
    assert "Directory paths are not accepted" in result.errors[0]


def test_empty_csv_fails_with_missing_header_error(tmp_path):
    csv_path = write_file(tmp_path / "empty.csv", "")

    result = summarize_csv_file(csv_path)

    assert result.ok is False
    assert result.status == DataExecutionStatus.FAILED
    assert "empty or missing a header" in result.errors[0]


def test_header_only_csv_completes_honestly(tmp_path):
    csv_path = write_file(tmp_path / "header_only.csv", "site,value\n")

    result = summarize_csv_file(csv_path)

    assert result.ok is True
    assert result.status == DataExecutionStatus.COMPLETED
    assert result.row_count == 0
    assert result.column_count == 2
    assert result.columns == ["site", "value"]
    assert result.numeric_columns == []
    assert result.text_columns == []
    assert result.preview_rows == []
    assert any("no data rows" in warning for warning in result.warnings)


def test_blank_header_is_blocked(tmp_path):
    csv_path = write_file(tmp_path / "blank_header.csv", "site,,value\nA,x,1\n")

    result = summarize_csv_file(csv_path)

    assert result.ok is False
    assert result.status == DataExecutionStatus.BLOCKED
    assert "blank column name" in result.errors[0]


def test_duplicate_header_is_blocked(tmp_path):
    csv_path = write_file(
        tmp_path / "duplicate_header.csv",
        "site,value,value\nA,1,2\n",
    )

    result = summarize_csv_file(csv_path)

    assert result.ok is False
    assert result.status == DataExecutionStatus.BLOCKED
    assert "duplicate column names" in result.errors[0]


def test_file_too_large_is_blocked(tmp_path):
    csv_path = write_file(tmp_path / "small.csv", "a,b\n1,2\n")

    result = summarize_csv_file(csv_path, max_file_size_bytes=5)

    assert result.ok is False
    assert result.status == DataExecutionStatus.BLOCKED
    assert "file size exceeds" in result.errors[0]


def test_too_many_rows_is_blocked(tmp_path):
    csv_path = write_file(
        tmp_path / "too_many.csv",
        "a,b\n1,2\n3,4\n5,6\n",
    )

    result = summarize_csv_file(csv_path, max_rows=2)

    assert result.ok is False
    assert result.status == DataExecutionStatus.BLOCKED
    assert "row count exceeds" in result.errors[0]


def test_malformed_row_lengths_produce_warnings(tmp_path):
    csv_path = write_file(
        tmp_path / "ragged.csv",
        "a,b,c\n"
        "1,2,3\n"
        "4,5\n"
        "6,7,8,9\n",
    )

    result = summarize_csv_file(csv_path)

    assert result.ok is True
    assert result.row_count == 3
    assert any("fewer cells" in warning for warning in result.warnings)
    assert any("more cells" in warning for warning in result.warnings)
    assert result.preview_rows[1] == {"a": "4", "b": "5", "c": ""}
    assert result.preview_rows[2] == {"a": "6", "b": "7", "c": "8"}


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


def test_valid_xlsx_summary_reports_shape_columns_and_boundary_truth(tmp_path):
    xlsx_path = write_xlsx_file(
        tmp_path / "sites.xlsx",
        [
            ["site", "temperature_c", "ph", "notes"],
            ["A", 12.5, 7.1, "clear"],
            ["B", 18.5, 7.3, None],
            ["C", 20.0, 7.6, "cloudy"],
        ],
    )

    result = summarize_xlsx_file(xlsx_path)

    assert result.ok is True
    assert result.status == DataExecutionStatus.COMPLETED
    assert result.tool_kind == DATA_EXECUTOR_TOOL_KIND
    assert result.operation == DATA_OPERATION_SUMMARIZE_CSV
    assert result.file_kind == "xlsx"
    assert result.row_count == 3
    assert result.column_count == 4
    assert result.columns == ["site", "temperature_c", "ph", "notes"]
    assert result.numeric_columns == ["temperature_c", "ph"]
    assert result.text_columns == ["site", "notes"]
    assert result.missing_values_by_column["notes"] == 1
    assert len(result.preview_rows) == 3
    assert result.locality == "local"
    assert result.approval_required is False
    assert result.network_access_used is False
    assert result.mutated_files is False
    assert result.errors == []
    assert any("formulas are not evaluated" in warning for warning in result.warnings)


def test_summarize_data_file_dispatches_xlsx_when_openpyxl_is_available(tmp_path):
    xlsx_path = write_xlsx_file(
        tmp_path / "measurements.xlsx",
        [
            ["site", "value"],
            ["A", 1],
            ["B", 2],
        ],
    )

    result = summarize_data_file(xlsx_path)

    assert result.ok is True
    assert result.status == DataExecutionStatus.COMPLETED
    assert result.file_kind == "xlsx"
    assert result.row_count == 2
    assert result.column_count == 2
    assert result.numeric_columns == ["value"]


def test_xlsx_multiple_sheets_warns_and_uses_first_sheet(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    xlsx_path = tmp_path / "multi_sheet.xlsx"
    workbook = openpyxl.Workbook()
    first = workbook.active
    first.title = "First"
    first.append(["site", "value"])
    first.append(["A", 1])

    second = workbook.create_sheet("Second")
    second.append(["ignored", "value"])
    second.append(["B", 2])

    workbook.save(xlsx_path)
    workbook.close()

    result = summarize_xlsx_file(xlsx_path)

    assert result.ok is True
    assert result.file_kind == "xlsx"
    assert result.columns == ["site", "value"]
    assert result.row_count == 1
    assert any("first worksheet" in warning for warning in result.warnings)


def test_xlsx_missing_openpyxl_is_blocked_honestly(monkeypatch, tmp_path):
    xlsx_path = tmp_path / "workbook.xlsx"
    xlsx_path.write_bytes(b"pretend xlsx content")

    monkeypatch.setattr(
        data_executor,
        "_load_openpyxl_load_workbook",
        lambda: (None, "No module named 'openpyxl'"),
    )

    result = summarize_xlsx_file(xlsx_path)

    assert result.ok is False
    assert result.status == DataExecutionStatus.BLOCKED
    assert result.file_kind == "xlsx"
    assert "openpyxl" in result.errors[0]
    assert result.network_access_used is False
    assert result.mutated_files is False
