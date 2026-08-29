"""
Bounded local data execution service for the Elysia API bridge.

Sprint 5C v0 exposes a narrow service wrapper over core.data_executor.
This service does not expose routes, run shell commands, touch the network,
modify files, create plots, scan folders, or perform arbitrary Python execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.api.schemas.data_execution import (
    DataExecutionOperation,
    DataExecutionRequest,
    DataExecutionResult,
    data_result_from_executor_result,
)
from app.api.schemas.execution import (
    ExecutionStatus,
    ExecutionToolKind,
)
from core.data_executor import summarize_data_file


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _failed_result_from_validation_error(
    *,
    request: Any,
    error: ValidationError | Exception,
) -> DataExecutionResult:
    """
    Convert invalid service input into a schema-shaped failed result.
    """
    operation = DataExecutionOperation.SUMMARIZE_CSV.value
    source_path = ""

    if isinstance(request, dict):
        operation = str(request.get("operation") or operation)
        source_path = str(request.get("source_path") or "")

    return DataExecutionResult(
        ok=False,
        status=ExecutionStatus.FAILED,
        tool_kind=ExecutionToolKind.DATA_EXECUTOR,
        operation=operation,
        source_path=source_path,
        errors=[str(error)],
    )


def run_data_execution(
    request: DataExecutionRequest | dict[str, Any],
) -> DataExecutionResult:
    """
    Run one bounded local data execution request.

    This function is intentionally narrow:
    - local CSV/XLSX table summary only; XLSX requires optional local openpyxl
    - no pandas dependency
    - no shell
    - no arbitrary Python
    - no file mutation
    - no network
    - no plotting
    - no memory promotion
    """
    try:
        request_model = (
            request
            if isinstance(request, DataExecutionRequest)
            else DataExecutionRequest(**dict(request))
        )
    except (ValidationError, TypeError, ValueError) as exc:
        return _failed_result_from_validation_error(
            request=request,
            error=exc,
        )

    if request_model.operation != DataExecutionOperation.SUMMARIZE_CSV:
        return DataExecutionResult(
            ok=False,
            status=ExecutionStatus.BLOCKED,
            operation=_enum_value(request_model.operation),
            source_path=request_model.source_path,
            errors=[
                "Unsupported data execution operation for Sprint 5B v0. "
                "Only summarize_csv is supported."
            ],
        )

    executor_result = summarize_data_file(
        request_model.source_path,
        max_file_size_bytes=request_model.max_file_size_bytes,
        max_rows=request_model.max_rows,
        preview_row_limit=request_model.preview_row_limit,
    )

    return data_result_from_executor_result(executor_result)


def _format_list(values: list[str]) -> str:
    clean_values = [str(value).strip() for value in values if str(value).strip()]
    return ", ".join(clean_values) if clean_values else "none"


def _format_missing_values(values: dict[str, int]) -> str:
    nonzero = {
        column: count
        for column, count in values.items()
        if isinstance(count, int) and count > 0
    }

    if not nonzero:
        return "none recorded"

    return "; ".join(f"{column}: {count}" for column, count in nonzero.items())


def _format_numeric_stats(result: DataExecutionResult, *, limit: int = 5) -> str:
    if not result.numeric_stats:
        return "none"

    parts: list[str] = []

    for index, (column, stats) in enumerate(result.numeric_stats.items()):
        if index >= limit:
            remaining = len(result.numeric_stats) - limit
            if remaining > 0:
                parts.append(f"{remaining} more numeric columns not shown")
            break

        parts.append(
            (
                f"{column}: count {stats.count}, missing {stats.missing}, "
                f"min {stats.min}, max {stats.max}, mean {stats.mean}"
            )
        )

    return "; ".join(parts)


def build_data_execution_context_block(result: DataExecutionResult) -> str:
    """
    Build a compact model-facing context block from a data execution result.
    """
    lines = [
        "Bounded local data execution result:",
        "Tool: data_executor",
        "Locality: local",
        "Approval required: no",
        f"Status: {_enum_value(result.status)}",
        f"Operation: {result.operation}",
    ]

    if result.file_name:
        lines.append(f"File name: {result.file_name}")

    if result.file_kind:
        lines.append(f"File kind: {result.file_kind}")

    lines.extend(
        [
            f"Rows: {result.row_count}",
            f"Columns: {result.column_count}",
            f"Column names: {_format_list(result.columns)}",
            f"Numeric columns: {_format_list(result.numeric_columns)}",
            f"Text columns: {_format_list(result.text_columns)}",
            (
                "Missing values: "
                + _format_missing_values(result.missing_values_by_column)
            ),
            f"Numeric stats: {_format_numeric_stats(result)}",
            f"Preview rows: {len(result.preview_rows)} shown",
        ]
    )

    if result.warnings:
        lines.append("Warnings: " + "; ".join(result.warnings))

    if result.errors:
        lines.append("Errors: " + "; ".join(result.errors))

    lines.append(
        "Boundary note: this was bounded local table inspection, not arbitrary Python, shell, web, plotting, notebook behavior, file mutation, folder scanning, or memory promotion."
    )

    return "\n".join(lines)


__all__ = (
    "build_data_execution_context_block",
    "run_data_execution",
)
