"""
Execution schema models for the Elysia local API bridge.

This module defines narrow schema vocabulary for bounded local execution lanes.

Sprint 3 v0 supports only local math execution. It does not imply arbitrary
Python execution, shell execution, file writes, notebook behavior, web access,
or external services.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from .common import (
    ApprovalState,
    ElysiaSchemaModel,
    LocalityState,
)


class ExecutionToolKind(str, Enum):
    """
    Canonical execution tool names.

    Naming a tool here does not mean it is live. Capability truth must still
    come from the capability catalog/service.
    """

    MATH_EXECUTOR = "math_executor"
    DATA_EXECUTOR = "data_executor"
    CODE_WORKER = "code_worker"


class ExecutionStatus(str, Enum):
    """
    Canonical execution status for bounded local execution attempts.
    """

    NOT_NEEDED = "not_needed"
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class MathOperation(str, Enum):
    """
    Supported math operations for local math execution v0.
    """

    EVALUATE = "evaluate"
    SIMPLIFY = "simplify"
    DIFFERENTIATE = "differentiate"
    INTEGRATE = "integrate"
    SOLVE = "solve"
    CHECK_NUMERIC_RESULT = "check_numeric_result"


class MathExecutionRequest(ElysiaSchemaModel):
    """
    Request shape for one bounded local math execution attempt.
    """

    operation: MathOperation = Field(
        ...,
        description="Supported math operation to run.",
    )
    expression: str = Field(
        ...,
        min_length=1,
        description="Math expression or equation to execute locally.",
    )
    variable: str = Field(
        default="x",
        min_length=1,
        description="Symbolic variable for differentiation, integration, or solving.",
    )
    expected: str | float | int | None = Field(
        default=None,
        description="Expected numeric result for check_numeric_result operations.",
    )
    tolerance: float = Field(
        default=1e-9,
        ge=0,
        description="Absolute tolerance for numeric result checking.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional request identifier associated with this execution.",
    )


class MathExecutionResult(ElysiaSchemaModel):
    """
    Result shape for one bounded local math execution attempt.
    """

    ok: bool = Field(
        default=False,
        description="Whether execution completed successfully.",
    )
    status: ExecutionStatus = Field(
        default=ExecutionStatus.FAILED,
        description="Execution status for this attempt.",
    )
    tool_kind: ExecutionToolKind = Field(
        default=ExecutionToolKind.MATH_EXECUTOR,
        description="Execution tool used or attempted.",
    )
    operation: str = Field(
        ...,
        min_length=1,
        description="Math operation requested or attempted.",
    )
    engine: str = Field(
        default="sympy",
        description="Local execution engine used by the math executor.",
    )
    input: str = Field(
        default="",
        description="Original math expression or equation.",
    )
    variable: str | None = Field(
        default=None,
        description="Symbolic variable used for the operation when relevant.",
    )
    expected: str | None = Field(
        default=None,
        description="Expected value when numeric checking was requested.",
    )
    result: str | None = Field(
        default=None,
        description="Plain-text symbolic or exact result when available.",
    )
    numeric_result: float | None = Field(
        default=None,
        description="Numeric result when available.",
    )
    exact_match: bool | None = Field(
        default=None,
        description="Whether a numeric check matched within tolerance.",
    )
    tolerance: float | None = Field(
        default=None,
        ge=0,
        description="Tolerance used for numeric checking.",
    )
    locality: LocalityState = Field(
        default=LocalityState.LOCAL,
        description="Execution locality. Math execution v0 must remain local.",
    )
    approval_state: ApprovalState = Field(
        default=ApprovalState.NOT_NEEDED,
        description="Approval posture for bounded local math execution.",
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
            "Bounded local math execution v0. This is not arbitrary Python, "
            "shell execution, web access, or file mutation."
        ),
        description="Compact execution truth note.",
    )


class ExecutionTraceSummary(ElysiaSchemaModel):
    """
    Compact trace summary for a bounded execution attempt.
    """

    tool_kind: ExecutionToolKind = Field(
        ...,
        description="Execution tool considered or used.",
    )
    status: ExecutionStatus = Field(
        ...,
        description="Execution status for the request.",
    )
    operation: str | None = Field(
        default=None,
        description="Operation attempted when applicable.",
    )
    stayed_local: bool = Field(
        default=True,
        description="Whether execution stayed local.",
    )
    approval_required: bool = Field(
        default=False,
        description="Whether approval was required.",
    )
    summary: str | None = Field(
        default=None,
        description="Compact UI-safe execution summary.",
    )


def math_result_from_executor_payload(
    payload: dict[str, Any],
    *,
    status: ExecutionStatus | None = None,
) -> MathExecutionResult:
    """
    Convert core.math_executor payloads into the API execution-result schema.
    """
    ok = bool(payload.get("ok", False))
    resolved_status = status or (
        ExecutionStatus.COMPLETED if ok else ExecutionStatus.FAILED
    )

    return MathExecutionResult(
        ok=ok,
        status=resolved_status,
        operation=str(payload.get("operation") or "unknown"),
        engine=str(payload.get("engine") or "sympy"),
        input=str(payload.get("input") or ""),
        variable=payload.get("variable"),
        expected=(
            str(payload.get("expected"))
            if payload.get("expected") is not None
            else None
        ),
        result=(
            str(payload.get("result"))
            if payload.get("result") is not None
            else None
        ),
        numeric_result=payload.get("numeric_result"),
        exact_match=payload.get("exact_match"),
        tolerance=payload.get("tolerance"),
        warnings=list(payload.get("warnings") or []),
        errors=list(payload.get("errors") or []),
    )


__all__ = (
    "ExecutionStatus",
    "ExecutionToolKind",
    "ExecutionTraceSummary",
    "MathExecutionRequest",
    "MathExecutionResult",
    "MathOperation",
    "math_result_from_executor_payload",
)
