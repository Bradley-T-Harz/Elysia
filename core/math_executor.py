"""
Bounded local math execution organ for Elysia.

This module provides narrow, local, non-side-effecting symbolic/numeric math
helpers. It does not run shell commands, does not read or write files, does not
touch the network, and does not use Python eval directly.

The implementation is intentionally small for v0:
- evaluate expressions
- simplify expressions
- differentiate expressions
- integrate expressions
- solve one equation for one variable
- check a numeric result

SymPy is the execution engine when installed. If SymPy is unavailable, functions
return structured errors instead of crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable


ENGINE_NAME = "sympy"
SUPPORTED_OPERATIONS = {
    "evaluate",
    "simplify",
    "differentiate",
    "integrate",
    "solve",
    "check_numeric_result",
}

_ALLOWED_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9_\s+\-*/^().=,]+$")


@dataclass
class MathExecutionResult:
    """
    Structured result for local math execution.
    """

    ok: bool
    operation: str
    engine: str = ENGINE_NAME
    input: str = ""
    variable: str | None = None
    expected: str | None = None
    result: str | None = None
    numeric_result: float | None = None
    exact_match: bool | None = None
    tolerance: float | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """
        Return a JSON-safe payload.
        """
        return {
            "ok": self.ok,
            "operation": self.operation,
            "engine": self.engine,
            "input": self.input,
            "variable": self.variable,
            "expected": self.expected,
            "result": self.result,
            "numeric_result": self.numeric_result,
            "exact_match": self.exact_match,
            "tolerance": self.tolerance,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _load_sympy() -> tuple[Any | None, str | None]:
    """
    Import SymPy lazily so the module fails safely when SymPy is unavailable.
    """
    try:
        import sympy
        from sympy.parsing.sympy_parser import (
            convert_xor,
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )

        return {
            "sympy": sympy,
            "parse_expr": parse_expr,
            "transformations": standard_transformations
            + (
                implicit_multiplication_application,
                convert_xor,
            ),
        }, None
    except Exception as exc:
        return None, str(exc)


def is_sympy_available() -> bool:
    """
    Return True when the local SymPy engine is available.
    """
    sympy_bundle, _ = _load_sympy()
    return sympy_bundle is not None


def _unavailable_result(operation: str, input_text: str) -> MathExecutionResult:
    """
    Build a structured result when SymPy is not installed.
    """
    return MathExecutionResult(
        ok=False,
        operation=operation,
        input=input_text,
        errors=[
            "SymPy is not installed in the current Python environment. "
            "Install sympy before enabling local math execution."
        ],
    )


def _validate_math_text(text: str) -> str:
    """
    Validate simple math text before sending it to SymPy parsing.

    This is not a full security sandbox. It is a conservative v0 guardrail that
    only permits ordinary symbolic/numeric math characters and blocks obvious
    Python/meta-programming tokens.
    """
    cleaned = str(text or "").strip()

    if not cleaned:
        raise ValueError("Math expression is empty.")

    lowered = cleaned.lower()
    blocked_tokens = (
        "__",
        "import",
        "lambda",
        "exec",
        "eval",
        "open",
        "read",
        "write",
        "system",
        "subprocess",
        "os.",
        "sys.",
    )

    if any(token in lowered for token in blocked_tokens):
        raise ValueError("Math expression contains blocked non-math syntax.")

    if not _ALLOWED_TEXT_PATTERN.match(cleaned):
        raise ValueError(
            "Math expression contains unsupported characters for the v0 executor."
        )

    return cleaned


def _sympy_globals(sympy: Any) -> dict[str, Any]:
    """
    Provide the minimal global names SymPy parsing needs.
    """
    return {
        "__builtins__": {},
        "Integer": sympy.Integer,
        "Float": sympy.Float,
        "Rational": sympy.Rational,
        "Symbol": sympy.Symbol,
        "Add": sympy.Add,
        "Mul": sympy.Mul,
        "Pow": sympy.Pow,
        "sin": sympy.sin,
        "cos": sympy.cos,
        "tan": sympy.tan,
        "asin": sympy.asin,
        "acos": sympy.acos,
        "atan": sympy.atan,
        "sqrt": sympy.sqrt,
        "exp": sympy.exp,
        "log": sympy.log,
        "ln": sympy.log,
        "pi": sympy.pi,
        "E": sympy.E,
    }


def _parse_expression(
    expression: str,
    *,
    sympy_bundle: dict[str, Any],
    variable: str | None = None,
) -> Any:
    """
    Parse a bounded math expression with SymPy.
    """
    sympy = sympy_bundle["sympy"]
    parse_expr = sympy_bundle["parse_expr"]
    transformations = sympy_bundle["transformations"]

    cleaned = _validate_math_text(expression)
    local_dict: dict[str, Any] = {}

    if variable:
        variable_name = _validate_variable(variable)
        local_dict[variable_name] = sympy.Symbol(variable_name)

    return parse_expr(
        cleaned,
        local_dict=local_dict,
        global_dict=_sympy_globals(sympy),
        transformations=transformations,
        evaluate=True,
    )


def _validate_variable(variable: str) -> str:
    """
    Validate one symbolic variable name.
    """
    cleaned = str(variable or "").strip()

    if not cleaned:
        raise ValueError("Variable is required.")

    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", cleaned):
        raise ValueError("Variable must be a simple symbol name such as x.")

    return cleaned


def _stringify(value: Any) -> str:
    """
    Return a plain-text SymPy string.
    """
    sympy_bundle, _ = _load_sympy()
    if sympy_bundle is None:
        return str(value)

    sympy = sympy_bundle["sympy"]
    return sympy.sstr(value)


def _as_float_or_none(value: Any) -> float | None:
    """
    Convert a SymPy/numeric value to float when possible.
    """
    try:
        return float(value)
    except Exception:
        return None


def _operation_failure(
    *,
    operation: str,
    input_text: str,
    variable: str | None = None,
    expected: str | None = None,
    exc: Exception,
) -> MathExecutionResult:
    """
    Convert an exception into a structured math execution result.
    """
    return MathExecutionResult(
        ok=False,
        operation=operation,
        input=input_text,
        variable=variable,
        expected=expected,
        errors=[str(exc)],
    )


def evaluate_expression(expression: str) -> dict[str, Any]:
    """
    Evaluate or simplify one numeric/symbolic expression.
    """
    operation = "evaluate"
    sympy_bundle, error = _load_sympy()

    if sympy_bundle is None:
        return _unavailable_result(operation, expression).to_payload()

    try:
        sympy = sympy_bundle["sympy"]
        parsed = _parse_expression(expression, sympy_bundle=sympy_bundle)
        simplified = sympy.simplify(parsed)
        numeric_result = _as_float_or_none(simplified)

        return MathExecutionResult(
            ok=True,
            operation=operation,
            input=str(expression),
            result=_stringify(simplified),
            numeric_result=numeric_result,
        ).to_payload()
    except Exception as exc:
        return _operation_failure(
            operation=operation,
            input_text=str(expression),
            exc=exc,
        ).to_payload()


def simplify_expression(expression: str) -> dict[str, Any]:
    """
    Simplify one symbolic/numeric expression.
    """
    operation = "simplify"
    sympy_bundle, error = _load_sympy()

    if sympy_bundle is None:
        return _unavailable_result(operation, expression).to_payload()

    try:
        sympy = sympy_bundle["sympy"]
        parsed = _parse_expression(expression, sympy_bundle=sympy_bundle)
        simplified = sympy.simplify(parsed)
        numeric_result = _as_float_or_none(simplified)

        return MathExecutionResult(
            ok=True,
            operation=operation,
            input=str(expression),
            result=_stringify(simplified),
            numeric_result=numeric_result,
        ).to_payload()
    except Exception as exc:
        return _operation_failure(
            operation=operation,
            input_text=str(expression),
            exc=exc,
        ).to_payload()


def differentiate_expression(expression: str, variable: str = "x") -> dict[str, Any]:
    """
    Differentiate one expression with respect to one variable.
    """
    operation = "differentiate"
    sympy_bundle, error = _load_sympy()

    if sympy_bundle is None:
        return _unavailable_result(operation, expression).to_payload()

    try:
        sympy = sympy_bundle["sympy"]
        variable_name = _validate_variable(variable)
        symbol = sympy.Symbol(variable_name)
        parsed = _parse_expression(
            expression,
            sympy_bundle=sympy_bundle,
            variable=variable_name,
        )
        result = sympy.simplify(sympy.diff(parsed, symbol))

        return MathExecutionResult(
            ok=True,
            operation=operation,
            input=str(expression),
            variable=variable_name,
            result=_stringify(result),
        ).to_payload()
    except Exception as exc:
        return _operation_failure(
            operation=operation,
            input_text=str(expression),
            variable=variable,
            exc=exc,
        ).to_payload()


def integrate_expression(expression: str, variable: str = "x") -> dict[str, Any]:
    """
    Integrate one expression with respect to one variable.
    """
    operation = "integrate"
    sympy_bundle, error = _load_sympy()

    if sympy_bundle is None:
        return _unavailable_result(operation, expression).to_payload()

    try:
        sympy = sympy_bundle["sympy"]
        variable_name = _validate_variable(variable)
        symbol = sympy.Symbol(variable_name)
        parsed = _parse_expression(
            expression,
            sympy_bundle=sympy_bundle,
            variable=variable_name,
        )
        result = sympy.simplify(sympy.integrate(parsed, symbol))

        return MathExecutionResult(
            ok=True,
            operation=operation,
            input=str(expression),
            variable=variable_name,
            result=_stringify(result),
            warnings=[
                "Indefinite integral returned without an arbitrary constant in v0."
            ],
        ).to_payload()
    except Exception as exc:
        return _operation_failure(
            operation=operation,
            input_text=str(expression),
            variable=variable,
            exc=exc,
        ).to_payload()


def solve_equation(equation: str, variable: str = "x") -> dict[str, Any]:
    """
    Solve one equation for one variable.

    Accepts either:
    - x + 2 = 5
    - x + 2 - 5
    """
    operation = "solve"
    sympy_bundle, error = _load_sympy()

    if sympy_bundle is None:
        return _unavailable_result(operation, equation).to_payload()

    try:
        sympy = sympy_bundle["sympy"]
        variable_name = _validate_variable(variable)
        symbol = sympy.Symbol(variable_name)
        cleaned = _validate_math_text(equation)

        if "=" in cleaned:
            left_text, right_text = cleaned.split("=", 1)
            left = _parse_expression(
                left_text,
                sympy_bundle=sympy_bundle,
                variable=variable_name,
            )
            right = _parse_expression(
                right_text,
                sympy_bundle=sympy_bundle,
                variable=variable_name,
            )
            equation_object = sympy.Eq(left, right)
        else:
            expression = _parse_expression(
                cleaned,
                sympy_bundle=sympy_bundle,
                variable=variable_name,
            )
            equation_object = sympy.Eq(expression, 0)

        solutions = sympy.solve(equation_object, symbol)
        result = ", ".join(_stringify(solution) for solution in solutions)

        return MathExecutionResult(
            ok=True,
            operation=operation,
            input=str(equation),
            variable=variable_name,
            result=result,
            warnings=[] if solutions else ["No symbolic solution was returned."],
        ).to_payload()
    except Exception as exc:
        return _operation_failure(
            operation=operation,
            input_text=str(equation),
            variable=variable,
            exc=exc,
        ).to_payload()


def check_numeric_result(
    expression: str,
    expected: str | float | int,
    *,
    tolerance: float = 1e-9,
) -> dict[str, Any]:
    """
    Evaluate an expression and compare it with an expected numeric value.
    """
    operation = "check_numeric_result"
    sympy_bundle, error = _load_sympy()

    if sympy_bundle is None:
        return _unavailable_result(operation, expression).to_payload()

    try:
        sympy = sympy_bundle["sympy"]
        parsed_expression = _parse_expression(
            expression,
            sympy_bundle=sympy_bundle,
        )
        parsed_expected = _parse_expression(
            str(expected),
            sympy_bundle=sympy_bundle,
        )

        expression_value = sympy.N(parsed_expression)
        expected_value = sympy.N(parsed_expected)
        difference = abs(float(expression_value) - float(expected_value))
        exact_match = difference <= tolerance

        return MathExecutionResult(
            ok=True,
            operation=operation,
            input=str(expression),
            expected=str(expected),
            result=_stringify(sympy.simplify(parsed_expression)),
            numeric_result=float(expression_value),
            exact_match=exact_match,
            tolerance=tolerance,
            warnings=[] if exact_match else [f"Difference was {difference}."],
        ).to_payload()
    except Exception as exc:
        return _operation_failure(
            operation=operation,
            input_text=str(expression),
            expected=str(expected),
            exc=exc,
        ).to_payload()


def run_math_operation(
    *,
    operation: str,
    expression: str,
    variable: str = "x",
    expected: str | float | int | None = None,
    tolerance: float = 1e-9,
) -> dict[str, Any]:
    """
    Dispatch a supported v0 math operation.
    """
    normalized_operation = str(operation or "").strip().lower()

    dispatch: dict[str, Callable[..., dict[str, Any]]] = {
        "evaluate": evaluate_expression,
        "simplify": simplify_expression,
        "differentiate": differentiate_expression,
        "integrate": integrate_expression,
        "solve": solve_equation,
    }

    if normalized_operation == "check_numeric_result":
        if expected is None:
            return MathExecutionResult(
                ok=False,
                operation=normalized_operation,
                input=str(expression),
                errors=["Expected value is required for check_numeric_result."],
            ).to_payload()

        return check_numeric_result(
            expression,
            expected,
            tolerance=tolerance,
        )

    if normalized_operation not in dispatch:
        return MathExecutionResult(
            ok=False,
            operation=normalized_operation or "unknown",
            input=str(expression),
            errors=[
                f"Unsupported math operation '{normalized_operation}'. "
                f"Supported operations: {', '.join(sorted(SUPPORTED_OPERATIONS))}."
            ],
        ).to_payload()

    if normalized_operation in {"differentiate", "integrate", "solve"}:
        return dispatch[normalized_operation](expression, variable)

    return dispatch[normalized_operation](expression)


__all__ = (
    "ENGINE_NAME",
    "SUPPORTED_OPERATIONS",
    "MathExecutionResult",
    "check_numeric_result",
    "differentiate_expression",
    "evaluate_expression",
    "integrate_expression",
    "is_sympy_available",
    "run_math_operation",
    "simplify_expression",
    "solve_equation",
)
