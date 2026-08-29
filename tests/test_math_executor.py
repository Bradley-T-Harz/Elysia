from __future__ import annotations

import pytest

from core import math_executor


pytestmark = pytest.mark.skipif(
    not math_executor.is_sympy_available(),
    reason="SymPy is required for local math executor tests.",
)


def test_evaluate_expression_returns_exact_and_numeric_result():
    result = math_executor.evaluate_expression("2 + 2")

    assert result["ok"] is True
    assert result["operation"] == "evaluate"
    assert result["engine"] == "sympy"
    assert result["result"] == "4"
    assert result["numeric_result"] == 4.0
    assert result["errors"] == []


def test_evaluate_reduction_percentage_matches_expected_value():
    result = math_executor.evaluate_expression(
        "(4.0875 - 3.27) / 4.0875 * 100"
    )

    assert result["ok"] is True
    assert result["numeric_result"] == pytest.approx(20.0)


def test_differentiate_expression_returns_plain_text_result():
    result = math_executor.differentiate_expression("x**2 + 3*x", "x")

    assert result["ok"] is True
    assert result["operation"] == "differentiate"
    assert result["variable"] == "x"
    assert result["result"] == "2*x + 3"
    assert result["errors"] == []


def test_differentiate_expression_accepts_caret_power_notation():
    result = math_executor.differentiate_expression("x^2 + 3*x", "x")

    assert result["ok"] is True
    assert result["result"] == "2*x + 3"


def test_integrate_expression_returns_plain_text_result():
    result = math_executor.integrate_expression("2*x", "x")

    assert result["ok"] is True
    assert result["operation"] == "integrate"
    assert result["variable"] == "x"
    assert result["result"] == "x**2"
    assert "arbitrary constant" in result["warnings"][0]


def test_simplify_expression_returns_plain_text_result():
    result = math_executor.simplify_expression("(x**2 + 2*x + 1) / (x + 1)")

    assert result["ok"] is True
    assert result["operation"] == "simplify"
    assert result["result"] == "x + 1"
    assert result["errors"] == []


def test_solve_equation_returns_solution():
    result = math_executor.solve_equation("x + 2 = 5", "x")

    assert result["ok"] is True
    assert result["operation"] == "solve"
    assert result["variable"] == "x"
    assert result["result"] == "3"
    assert result["errors"] == []


def test_check_numeric_result_accepts_correct_value():
    result = math_executor.check_numeric_result(
        "(4.0875 - 3.27) / 4.0875 * 100",
        "20",
        tolerance=1e-9,
    )

    assert result["ok"] is True
    assert result["operation"] == "check_numeric_result"
    assert result["numeric_result"] == pytest.approx(20.0)
    assert result["exact_match"] is True
    assert result["errors"] == []


def test_check_numeric_result_reports_mismatch_without_crashing():
    result = math_executor.check_numeric_result(
        "(4.0875 - 3.27) / 4.0875 * 100",
        "80",
        tolerance=1e-9,
    )

    assert result["ok"] is True
    assert result["numeric_result"] == pytest.approx(20.0)
    assert result["exact_match"] is False
    assert result["warnings"]
    assert result["errors"] == []


def test_bad_input_returns_structured_error():
    result = math_executor.evaluate_expression("__import__(os)")

    assert result["ok"] is False
    assert result["operation"] == "evaluate"
    assert result["errors"]


def test_unsupported_operation_returns_structured_error():
    result = math_executor.run_math_operation(
        operation="plot",
        expression="x**2",
    )

    assert result["ok"] is False
    assert result["operation"] == "plot"
    assert "Unsupported math operation" in result["errors"][0]
