"""
Data execution schema models for the Elysia local API bridge.

Sprint 5C v0 supports bounded local CSV inspection and optional local
XLSX inspection through the core.data_executor organ. XLSX support depends
on openpyxl being installed locally. This does not imply arbitrary Python
execution, shell execution, web access, plotting, notebook behavior, file
mutation, folder scanning, or memory promotion.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from core.data_executor import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_MAX_ROWS,
    DEFAULT_PREVIEW_ROW_LIMIT,
)

from .common import (
    ApprovalState,
    ElysiaSchemaModel,
    LocalityState,
)
from .execution import (
    ExecutionStatus,
    ExecutionToolKind,
)


class DataExecutionOperation(str, Enum):
    """
    Supported bounded data execution operations.

    v0 intentionally supports one compatible table-summary operation. The
    operation name remains summarize_csv for compatibility while the executor
    can summarize CSV and, when openpyxl is available, XLSX.
    """

    SUMMARIZE_CSV = "summarize_csv"


class DataExecutionRequest(ElysiaSchemaModel):
    """
    Request shape for one bounded local data execution attempt.
    """

    operation: DataExecutionOperation = Field(
        default=DataExecutionOperation.SUMMARIZE_CSV,
        description="Supported bounded data operation to run.",
    )
    source_path: str = Field(
        ...,
        min_length=1,
        description="Local user-selected data file path. Elysia supports bounded CSV and optional local XLSX table summaries.",
    )
    max_file_size_bytes: int = Field(
        default=DEFAULT_MAX_FILE_SIZE_BYTES,
        ge=1,
        description="Maximum local file size allowed for this bounded execution attempt.",
    )
    max_rows: int = Field(
        default=DEFAULT_MAX_ROWS,
        ge=0,
        description="Maximum number of data rows allowed for this bounded execution attempt.",
    )
    preview_row_limit: int = Field(
        default=DEFAULT_PREVIEW_ROW_LIMIT,
        ge=0,
        le=100,
        description="Maximum number of preview rows to include in the structured result.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional request identifier associated with this execution.",
    )


class DataNumericColumnStats(ElysiaSchemaModel):
    """
    Basic descriptive statistics for one numeric column.
    """

    count: int = Field(
        default=0,
        ge=0,
        description="Number of non-missing numeric values used for stats.",
    )
    missing: int = Field(
        default=0,
        ge=0,
        description="Number of missing values in the column.",
    )
    min: float | None = Field(
        default=None,
        description="Minimum numeric value when available.",
    )
    max: float | None = Field(
        default=None,
        description="Maximum numeric value when available.",
    )
    mean: float | None = Field(
        default=None,
        description="Arithmetic mean when available.",
    )


class DataExecutionResult(ElysiaSchemaModel):
    """
    Result shape for one bounded local data execution attempt.
    """

    ok: bool = Field(
        default=False,
        description="Whether data execution completed successfully.",
    )
    status: ExecutionStatus = Field(
        default=ExecutionStatus.FAILED,
        description="Execution status for this attempt.",
    )
    tool_kind: ExecutionToolKind = Field(
        default=ExecutionToolKind.DATA_EXECUTOR,
        description="Execution tool used or attempted.",
    )
    operation: str = Field(
        default=DataExecutionOperation.SUMMARIZE_CSV.value,
        description="Data operation requested or attempted.",
    )
    source_path: str = Field(
        default="",
        description="Local path that was inspected or attempted.",
    )
    file_name: str | None = Field(
        default=None,
        description="File name extracted from the local path when available.",
    )
    file_kind: str | None = Field(
        default=None,
        description="Detected or requested file kind.",
    )
    row_count: int = Field(
        default=0,
        ge=0,
        description="Number of data rows summarized.",
    )
    column_count: int = Field(
        default=0,
        ge=0,
        description="Number of columns in the table.",
    )
    columns: list[str] = Field(
        default_factory=list,
        description="Column names in source order.",
    )
    numeric_columns: list[str] = Field(
        default_factory=list,
        description="Columns conservatively classified as numeric.",
    )
    text_columns: list[str] = Field(
        default_factory=list,
        description="Columns conservatively classified as text/categorical.",
    )
    missing_values_by_column: dict[str, int] = Field(
        default_factory=dict,
        description="Missing value counts by column.",
    )
    preview_rows: list[dict[str, str]] = Field(
        default_factory=list,
        description="Small preview of table rows. This must not contain the full dataset.",
    )
    numeric_stats: dict[str, DataNumericColumnStats] = Field(
        default_factory=dict,
        description="Basic stats for numeric columns.",
    )
    locality: LocalityState = Field(
        default=LocalityState.LOCAL,
        description="Execution locality. Data execution v0 must remain local.",
    )
    approval_state: ApprovalState = Field(
        default=ApprovalState.NOT_NEEDED,
        description="Approval posture for bounded local read-only data execution.",
    )
    network_access_used: bool = Field(
        default=False,
        description="Whether network access was used. Sprint 5B v0 must keep this false.",
    )
    mutated_files: bool = Field(
        default=False,
        description="Whether any files were modified. Sprint 5B v0 must keep this false.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings from the execution attempt.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Fatal or blocking errors from the execution attempt.",
    )
    execution_note: str = Field(
        default=(
            "Bounded local data execution v0. This is local CSV/XLSX table inspection, "
            "not arbitrary Python, shell execution, web access, plotting, notebook "
            "behavior, file mutation, folder scanning, or memory promotion."
        ),
        description="Compact execution truth note.",
    )


def _execution_status_from_value(value: Any, *, ok: bool) -> ExecutionStatus:
    status_value = getattr(value, "value", value)

    try:
        return ExecutionStatus(str(status_value))
    except ValueError:
        return ExecutionStatus.COMPLETED if ok else ExecutionStatus.FAILED


def _numeric_stats_from_payload(
    payload: dict[str, Any],
) -> dict[str, DataNumericColumnStats]:
    normalized: dict[str, DataNumericColumnStats] = {}

    for column, stats in payload.items():
        if not isinstance(stats, dict):
            continue

        normalized[str(column)] = DataNumericColumnStats(
            count=int(stats.get("count") or 0),
            missing=int(stats.get("missing") or 0),
            min=stats.get("min"),
            max=stats.get("max"),
            mean=stats.get("mean"),
        )

    return normalized


def data_result_from_executor_result(result: Any) -> DataExecutionResult:
    """
    Convert a core.data_executor.DataExecutionResult into the API schema.
    """
    ok = bool(getattr(result, "ok", False))
    status = _execution_status_from_value(
        getattr(result, "status", None),
        ok=ok,
    )

    approval_required = bool(getattr(result, "approval_required", False))

    return DataExecutionResult(
        ok=ok,
        status=status,
        operation=str(
            getattr(result, "operation", DataExecutionOperation.SUMMARIZE_CSV.value)
            or DataExecutionOperation.SUMMARIZE_CSV.value
        ),
        source_path=str(getattr(result, "source_path", "") or ""),
        file_name=getattr(result, "file_name", None),
        file_kind=getattr(result, "file_kind", None),
        row_count=int(getattr(result, "row_count", 0) or 0),
        column_count=int(getattr(result, "column_count", 0) or 0),
        columns=list(getattr(result, "columns", []) or []),
        numeric_columns=list(getattr(result, "numeric_columns", []) or []),
        text_columns=list(getattr(result, "text_columns", []) or []),
        missing_values_by_column=dict(
            getattr(result, "missing_values_by_column", {}) or {}
        ),
        preview_rows=list(getattr(result, "preview_rows", []) or []),
        numeric_stats=_numeric_stats_from_payload(
            dict(getattr(result, "numeric_stats", {}) or {})
        ),
        locality=LocalityState.LOCAL,
        approval_state=(
            ApprovalState.NEEDED if approval_required else ApprovalState.NOT_NEEDED
        ),
        network_access_used=bool(getattr(result, "network_access_used", False)),
        mutated_files=bool(getattr(result, "mutated_files", False)),
        warnings=list(getattr(result, "warnings", []) or []),
        errors=list(getattr(result, "errors", []) or []),
    )


__all__ = (
    "DataExecutionOperation",
    "DataExecutionRequest",
    "DataExecutionResult",
    "DataNumericColumnStats",
    "data_result_from_executor_result",
)
