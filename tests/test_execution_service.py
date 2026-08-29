from __future__ import annotations

import pytest

from app.api.execution_service import (
    build_math_execution_context_block,
    run_math_execution,
)
from app.api.schemas.common import ApprovalState, LocalityState
from app.api.schemas.execution import (
    ExecutionStatus,
    ExecutionToolKind,
    MathExecutionRequest,
    MathOperation,
)
from core import math_executor


def test_run_math_execution_reports_missing_sympy_safely_when_unavailable():
    if math_executor.is_sympy_available():
        pytest.skip("SymPy is available, so missing-SymPy behavior is not active.")

    result = run_math_execution(
        {
            "operation": "evaluate",
            "expression": "2 + 2",
        }
    )

    assert result.ok is False
    assert result.status == ExecutionStatus.FAILED
    assert result.tool_kind == ExecutionToolKind.MATH_EXECUTOR
    assert result.locality == LocalityState.LOCAL
    assert result.approval_state == ApprovalState.NOT_NEEDED
    assert result.errors
    assert "SymPy is not installed" in result.errors[0]


@pytest.mark.skipif(
    not math_executor.is_sympy_available(),
    reason="SymPy is required for local math execution service success tests.",
)
def test_run_math_execution_evaluates_expression_from_dict():
    result = run_math_execution(
        {
            "operation": "evaluate",
            "expression": "2 + 2",
        }
    )

    assert result.ok is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.tool_kind == ExecutionToolKind.MATH_EXECUTOR
    assert result.operation == "evaluate"
    assert result.result == "4"
    assert result.numeric_result == 4.0
    assert result.locality == LocalityState.LOCAL
    assert result.approval_state == ApprovalState.NOT_NEEDED
    assert result.errors == []


@pytest.mark.skipif(
    not math_executor.is_sympy_available(),
    reason="SymPy is required for local math execution service success tests.",
)
def test_run_math_execution_accepts_schema_model_request():
    request = MathExecutionRequest(
        operation=MathOperation.DIFFERENTIATE,
        expression="x**2 + 3*x",
        variable="x",
    )

    result = run_math_execution(request)

    assert result.ok is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.operation == "differentiate"
    assert result.variable == "x"
    assert result.result == "2*x + 3"
    assert result.errors == []


@pytest.mark.skipif(
    not math_executor.is_sympy_available(),
    reason="SymPy is required for local math execution service success tests.",
)
def test_run_math_execution_checks_numeric_result():
    result = run_math_execution(
        {
            "operation": "check_numeric_result",
            "expression": "(4.0875 - 3.27) / 4.0875 * 100",
            "expected": "20",
            "tolerance": 1e-9,
        }
    )

    assert result.ok is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.operation == "check_numeric_result"
    assert result.numeric_result == pytest.approx(20.0)
    assert result.exact_match is True
    assert result.errors == []


def test_run_math_execution_rejects_unknown_operation_without_crashing():
    result = run_math_execution(
        {
            "operation": "plot",
            "expression": "x**2",
        }
    )

    assert result.ok is False
    assert result.status == ExecutionStatus.FAILED
    assert result.operation == "plot"
    assert result.locality == LocalityState.LOCAL
    assert result.approval_state == ApprovalState.NOT_NEEDED
    assert result.errors


def test_build_math_execution_context_block_is_local_and_bounded():
    result = run_math_execution(
        {
            "operation": "evaluate",
            "expression": "2 + 2",
        }
    )

    block = build_math_execution_context_block(result)

    assert "Bounded local math execution result:" in block
    assert "Tool: math_executor" in block
    assert "Locality: local" in block
    assert "Approval required: no" in block
    assert "not arbitrary Python, shell, web, or file mutation" in block
