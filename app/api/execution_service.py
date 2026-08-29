"""
Bounded local execution service for the Elysia API bridge.

Sprint 3 v0 exposes a narrow math execution service over core.math_executor.
This service does not expose routes, run shell commands, touch the network,
read or write files, or perform arbitrary Python execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.api.schemas.execution import (
    ExecutionStatus,
    MathExecutionRequest,
    MathExecutionResult,
    MathOperation,
    math_result_from_executor_payload,
)
from core.math_executor import (
    is_sympy_available,
    run_math_operation,
)


def _failed_result_from_validation_error(
    *,
    request: Any,
    error: ValidationError | Exception,
) -> MathExecutionResult:
    """
    Convert invalid service input into a schema-shaped failed result.
    """
    operation = "unknown"
    expression = ""

    if isinstance(request, dict):
        operation = str(request.get("operation") or "unknown")
        expression = str(request.get("expression") or "")

    return MathExecutionResult(
        ok=False,
        status=ExecutionStatus.FAILED,
        operation=operation,
        input=expression,
        errors=[str(error)],
    )


def run_math_execution(
    request: MathExecutionRequest | dict[str, Any],
) -> MathExecutionResult:
    """
    Run one bounded local math execution request.

    This function is intentionally narrow:
    - local SymPy-backed math only
    - no shell
    - no arbitrary Python
    - no file mutation
    - no network
    """
    try:
        request_model = (
            request
            if isinstance(request, MathExecutionRequest)
            else MathExecutionRequest(**dict(request))
        )
    except (ValidationError, TypeError, ValueError) as exc:
        return _failed_result_from_validation_error(
            request=request,
            error=exc,
        )

    if not is_sympy_available():
        return MathExecutionResult(
            ok=False,
            status=ExecutionStatus.FAILED,
            operation=str(request_model.operation),
            input=request_model.expression,
            variable=request_model.variable,
            expected=(
                str(request_model.expected)
                if request_model.expected is not None
                else None
            ),
            tolerance=request_model.tolerance,
            errors=[
                "SymPy is not installed in the current Python environment. "
                "Install sympy before enabling local math execution."
            ],
        )

    payload = run_math_operation(
        operation=str(request_model.operation),
        expression=request_model.expression,
        variable=request_model.variable,
        expected=request_model.expected,
        tolerance=request_model.tolerance,
    )

    return math_result_from_executor_payload(payload)


def build_math_execution_context_block(result: MathExecutionResult) -> str:
    """
    Build a compact model-facing context block from a math execution result.
    """
    lines = [
        "Bounded local math execution result:",
        "Tool: math_executor",
        "Locality: local",
        "Approval required: no",
        f"Status: {result.status}",
        f"Operation: {result.operation}",
        f"Input: {result.input}",
    ]

    if result.variable:
        lines.append(f"Variable: {result.variable}")

    if result.expected is not None:
        lines.append(f"Expected: {result.expected}")

    if result.result is not None:
        lines.append(f"Result: {result.result}")

    if result.numeric_result is not None:
        lines.append(f"Numeric result: {result.numeric_result}")

    if result.exact_match is not None:
        lines.append(f"Exact/tolerance match: {result.exact_match}")

    if result.warnings:
        lines.append("Warnings: " + "; ".join(result.warnings))

    if result.errors:
        lines.append("Errors: " + "; ".join(result.errors))

    lines.append(
        "Boundary note: this was bounded local math execution, not arbitrary Python, shell, web, or file mutation."
    )

    return "\n".join(lines)


__all__ = (
    "build_math_execution_context_block",
    "run_math_execution",
)
