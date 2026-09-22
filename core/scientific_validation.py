"""Deterministic, content-safe validation of proposed mathematical workflows.

Validation establishes mathematical shape and selected-input eligibility. The
workflow service separately binds the authenticated owner and actual sources.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import importlib.util
import json
import math
import re
from typing import Any

from pydantic import ValidationError

from app.api.schemas.scientific_ir import Expression, ScientificWorkflow
from core.scientific_registry import (
    MAX_EXPRESSION_DEPTH, MAX_EXPRESSION_NODES, MAX_WORKFLOW_NODES,
    OPERATIONS, operation_spec,
)


class ScientificValidationError(ValueError):
    def __init__(self, reason: str, state: str = "blocked") -> None:
        self.reason = reason
        self.state = state
        super().__init__(reason)


_ARITY = {
    "number": 0, "rational": 0, "symbol": 0,
    "negate": 1, "sin": 1, "cos": 1, "exp": 1, "log": 1, "sqrt": 1,
    "add": 2, "subtract": 2, "multiply": 2, "divide": 2, "power": 2,
}
_UNITS = re.compile(r"^[A-Za-z][A-Za-z0-9_*/^ .%-]{0,47}$")
_NUMBERS = re.compile(r"(?<![A-Za-z0-9_.])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?(?![A-Za-z0-9_.])")


def _expression_check(expression: Expression, symbols: set[str], *, depth: int = 1) -> int:
    if depth > MAX_EXPRESSION_DEPTH:
        raise ScientificValidationError("expression_depth_exceeded")
    if len(expression.args) != _ARITY[expression.kind]:
        raise ScientificValidationError("expression_arity_invalid")
    if expression.kind == "number":
        if expression.value is None or expression.symbol is not None or expression.numerator is not None:
            raise ScientificValidationError("expression_number_invalid")
    elif expression.kind == "rational":
        if (expression.numerator is None or expression.denominator is None
                or expression.denominator == 0 or abs(expression.numerator) > 10**30
                or abs(expression.denominator) > 10**30 or expression.value is not None
                or expression.symbol is not None):
            raise ScientificValidationError("expression_rational_invalid")
    elif expression.kind == "symbol":
        if expression.symbol not in symbols or expression.value is not None:
            raise ScientificValidationError("expression_symbol_unbound", "clarification_required")
    elif any(value is not None for value in (expression.value, expression.symbol, expression.numerator, expression.denominator)):
        raise ScientificValidationError("expression_payload_invalid")
    if expression.kind == "power":
        exponent = expression.args[1]
        if exponent.kind != "number" or not isinstance(exponent.value, int) or abs(exponent.value) > 16:
            raise ScientificValidationError("expression_power_unbounded")
    count = 1 + sum(_expression_check(arg, symbols, depth=depth + 1) for arg in expression.args)
    if count > MAX_EXPRESSION_NODES:
        raise ScientificValidationError("expression_nodes_exceeded")
    return count


def _shape(value: object) -> str:
    if isinstance(value, bool):
        raise ScientificValidationError("numeric_boolean_rejected")
    if isinstance(value, (float, int)) and math.isfinite(value):
        return "scalar"
    if isinstance(value, list) and value and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value):
        if len(value) > 100_000:
            raise ScientificValidationError("vector_length_exceeded")
        return "vector"
    if isinstance(value, list) and value and all(isinstance(row, list) for row in value):
        width = len(value[0])
        if not 1 <= len(value) <= 64 or not 1 <= width <= 64:
            raise ScientificValidationError("matrix_dimensions_exceeded")
        if any(len(row) != width or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in row) for row in value):
            raise ScientificValidationError("matrix_invalid")
        return "matrix"
    raise ScientificValidationError("numeric_input_invalid")


def _check_unit(text: str | None) -> bool:
    if text is None or text == "dimensionless":
        return False
    if not _UNITS.fullmatch(text) or ".." in text or "//" in text:
        raise ScientificValidationError("unit_syntax_invalid")
    return True


def _dimensions(expression: Expression, symbols: dict[str, Any], ureg: Any) -> Any:
    if expression.kind in {"number", "rational"}:
        return ureg.dimensionless
    if expression.kind == "symbol":
        return ureg.Unit(symbols[expression.symbol].unit)
    args = [_dimensions(arg, symbols, ureg) for arg in expression.args]
    if expression.kind in {"add", "subtract"}:
        if args[0].dimensionality != args[1].dimensionality:
            raise ScientificValidationError("dimension_mismatch")
        return args[0]
    if expression.kind == "multiply":
        return args[0] * args[1]
    if expression.kind == "divide":
        return args[0] / args[1]
    if expression.kind == "power":
        return args[0] ** int(expression.args[1].value)
    if expression.kind == "sqrt":
        return args[0] ** 0.5
    if expression.kind in {"sin", "cos", "exp", "log"}:
        if args[0].dimensionality != ureg.dimensionless.dimensionality:
            raise ScientificValidationError("transcendental_input_has_units")
        return ureg.dimensionless
    return args[0]


def _source_numbers(expression: Expression) -> list[Decimal]:
    if expression.kind == "number":
        return [Decimal(str(expression.value))]
    if expression.kind == "rational":
        return [Decimal(expression.numerator), Decimal(expression.denominator)]
    values: list[Decimal] = []
    for arg in expression.args:
        values.extend(_source_numbers(arg))
    return values


def _numeric_provenance(workflow: ScientificWorkflow, original_message: str) -> None:
    canonical = original_message[:8192].casefold()
    if any(assumption.casefold() not in canonical for assumption in workflow.assumptions):
        raise ScientificValidationError("assumption_not_user_authorized", "clarification_required")
    user_values: set[Decimal] = set()
    for match in _NUMBERS.finditer(original_message[:8192]):
        try:
            user_values.add(Decimal(match.group()))
        except InvalidOperation:
            pass
    proposed: list[Decimal] = []
    for symbol in workflow.symbols:
        if symbol.value is not None:
            if symbol.provenance in {"trusted_constant", "selected_source"}:
                raise ScientificValidationError("unbound_factual_constant", "reference_required")
            if symbol.provenance == "assumption":
                if not workflow.assumptions:
                    raise ScientificValidationError("assumption_not_declared", "clarification_required")
                continue
            stack = [symbol.value]
            while stack:
                item = stack.pop()
                if isinstance(item, list):
                    stack.extend(item)
                else:
                    proposed.append(Decimal(str(item)))
    for node in workflow.nodes:
        for item in node.inputs.values():
            if item.kind == "literal":
                if item.provenance == "assumption" and workflow.assumptions:
                    continue
                if item.provenance in {"trusted_constant", "selected_source"}:
                    raise ScientificValidationError("unbound_factual_constant", "reference_required")
                stack = [item.value]
                while stack:
                    value = stack.pop()
                    if isinstance(value, list):
                        stack.extend(value)
                    else:
                        proposed.append(Decimal(str(value)))
        for expression in (node.expression, node.objective):
            if expression is not None:
                proposed.extend(_source_numbers(expression))
        for relation in node.relations:
            proposed.extend(_source_numbers(relation.left))
            proposed.extend(_source_numbers(relation.right))
        proposed.extend(Decimal(str(value)) for value in node.initial_conditions.values())
        for pair in (node.bounds, node.time_range):
            if pair is not None:
                proposed.extend(Decimal(str(value)) for value in pair)
    if any(value not in user_values and value not in {Decimal(-1), Decimal(0), Decimal(1)} for value in proposed):
        raise ScientificValidationError("numeric_fact_not_in_user_request", "clarification_required")


def validate_scientific_workflow(
    proposed: ScientificWorkflow | dict[str, Any], *,
    allowed_file_ids: set[str] | frozenset[str] = frozenset(),
    original_message: str | None = None,
) -> ScientificWorkflow:
    """Return a bounded, structurally validated workflow; never grant authority."""
    try:
        if isinstance(proposed, dict):
            if len(json.dumps(proposed, allow_nan=False)) > 512 * 1024:
                raise ScientificValidationError("scientific_ir_too_large")
            workflow = ScientificWorkflow.model_validate(proposed)
        elif isinstance(proposed, ScientificWorkflow):
            workflow = proposed
        else:
            raise ScientificValidationError("scientific_ir_not_object")
    except (ValidationError, TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, ScientificValidationError):
            raise
        raise ScientificValidationError("scientific_ir_schema_invalid") from exc
    if len(workflow.nodes) > MAX_WORKFLOW_NODES:
        raise ScientificValidationError("workflow_node_limit_exceeded")
    symbols = {symbol.name: symbol for symbol in workflow.symbols}
    sources = {source.source_id: source for source in workflow.sources}
    if len(symbols) != len(workflow.symbols) or len(sources) != len(workflow.sources):
        raise ScientificValidationError("duplicate_symbol_or_source")
    if any(source.file_id not in allowed_file_ids for source in workflow.sources):
        raise ScientificValidationError("source_not_selected_or_authorized")
    seen: dict[str, dict[str, str]] = {}
    expression_count = 0
    uses_units = False
    for symbol in workflow.symbols:
        uses_units |= _check_unit(symbol.unit)
        if symbol.value is not None and _shape(symbol.value) != symbol.shape:
            raise ScientificValidationError("symbol_shape_mismatch")
        if symbol.lower is not None and symbol.upper is not None and symbol.lower > symbol.upper:
            raise ScientificValidationError("symbol_bounds_invalid")
        if symbol.value is not None and symbol.provenance is None:
            raise ScientificValidationError("symbol_provenance_required", "clarification_required")
    for node in workflow.nodes:
        if node.node_id in seen:
            raise ScientificValidationError("workflow_duplicate_node")
        spec = operation_spec(node.operation)
        if spec is None:
            raise ScientificValidationError("unsupported_scientific_operation", "unsupported")
        if any(check != "finite" and check not in spec.diagnostics for check in node.verification):
            raise ScientificValidationError("verification_expectation_unsupported", "unsupported")
        expected = dict(spec.inputs)
        if set(node.inputs) != set(expected):
            raise ScientificValidationError("operation_input_ports_invalid")
        for port, item in node.inputs.items():
            shape = expected[port]
            if item.kind == "literal":
                actual = _shape(item.value)
            elif item.kind == "symbol":
                if item.symbol not in symbols or symbols[item.symbol].value is None:
                    raise ScientificValidationError("symbol_value_required", "clarification_required")
                actual = symbols[item.symbol].shape
                uses_units |= _check_unit(symbols[item.symbol].unit)
            elif item.kind == "source":
                if not spec.source_allowed or item.source_id not in sources:
                    raise ScientificValidationError("source_port_not_allowed")
                actual = shape
            else:
                actual = seen.get(item.node_id, {}).get(item.port)
                if actual is None:
                    raise ScientificValidationError("workflow_forward_or_invalid_reference")
            if actual != shape:
                raise ScientificValidationError("workflow_port_shape_mismatch")
        if node.variable is not None and node.variable not in symbols:
            raise ScientificValidationError("operation_variable_undeclared", "clarification_required")
        if node.variable is not None and node.operation not in {"differentiate", "integrate", "find_root", "numerical_integral", "minimize_scalar", "solve_ode_ivp"}:
            raise ScientificValidationError("operation_variable_unsupported")
        if node.bounds is not None and node.operation not in {"find_root", "numerical_integral", "minimize_scalar"}:
            raise ScientificValidationError("operation_bounds_unsupported")
        if node.time_range is not None and node.operation != "solve_ode_ivp":
            raise ScientificValidationError("operation_time_range_unsupported")
        if node.output_points != 101 and node.operation != "solve_ode_ivp":
            raise ScientificValidationError("operation_output_points_unsupported")
        if (node.unit is not None or node.target_unit is not None) and node.operation not in {"unit_convert", "dimensional_check", "quantity_arithmetic"}:
            raise ScientificValidationError("operation_units_unsupported")
        if node.arithmetic is not None and node.operation != "quantity_arithmetic":
            raise ScientificValidationError("operation_arithmetic_unsupported")
        for expression in (node.expression, node.objective):
            if expression is not None:
                expression_count += _expression_check(expression, set(symbols))
        for relation in node.relations:
            expression_count += _expression_check(relation.left, set(symbols))
            expression_count += _expression_check(relation.right, set(symbols))
        if node.relations and node.operation != "solve_ode_ivp":
            raise ScientificValidationError("operation_relations_unsupported", "unsupported")
        if node.objective is not None:
            raise ScientificValidationError("separate_objective_unsupported", "unsupported")
        if node.initial_conditions and node.operation != "solve_ode_ivp":
            raise ScientificValidationError("initial_conditions_operation_mismatch")
        if node.expression is not None and node.operation not in {"evaluate_expression", "substitute_expression", "differentiate", "simplify_expression", "integrate", "find_root", "numerical_integral", "minimize_scalar"}:
            raise ScientificValidationError("operation_expression_unsupported")
        if expression_count > 2048:
            raise ScientificValidationError("workflow_expression_limit_exceeded")
        uses_units |= _check_unit(node.unit) | _check_unit(node.target_unit)
        if node.bounds is not None and not node.bounds[0] < node.bounds[1]:
            raise ScientificValidationError("solver_bounds_invalid")
        if node.time_range is not None and not node.time_range[0] < node.time_range[1]:
            raise ScientificValidationError("ode_time_range_invalid")
        if node.operation in {"evaluate_expression", "substitute_expression", "differentiate", "simplify_expression", "integrate", "find_root", "numerical_integral", "minimize_scalar"} and node.expression is None:
            raise ScientificValidationError("operation_expression_required")
        if node.operation in {"differentiate", "integrate", "find_root", "numerical_integral", "minimize_scalar", "solve_ode_ivp"} and not node.variable:
            raise ScientificValidationError("operation_variable_required")
        if node.operation in {"find_root", "numerical_integral", "minimize_scalar"} and node.bounds is None:
            raise ScientificValidationError("operation_bounds_required")
        if node.operation == "solve_ode_ivp":
            states = set(node.initial_conditions)
            if not states or len(states) > 8 or node.time_range is None or not node.relations:
                raise ScientificValidationError("ode_initial_conditions_required")
            if any(relation.relation != "equal" or relation.left.kind != "symbol" or relation.left.symbol not in states for relation in node.relations):
                raise ScientificValidationError("ode_state_equations_invalid")
            if {relation.left.symbol for relation in node.relations} != states or len(node.relations) != len(states):
                raise ScientificValidationError("ode_state_equations_incomplete")
        if node.operation in {"unit_convert", "dimensional_check", "quantity_arithmetic"}:
            if not node.unit or not node.target_unit:
                raise ScientificValidationError("unit_operation_units_required")
            uses_units = True
        if node.columns:
            if node.operation not in {"descriptive_stats", "correlation_matrix", "bootstrap_mean_ci"} or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_ .-]{0,63}", column) for column in node.columns):
                raise ScientificValidationError("source_columns_invalid")
        if node.operation in {"descriptive_stats", "bootstrap_mean_ci"} and any(item.kind == "source" for item in node.inputs.values()) and len(node.columns) != 1:
            raise ScientificValidationError("source_column_required")
        if node.operation == "correlation_matrix" and any(item.kind == "source" for item in node.inputs.values()) and not 2 <= len(node.columns) <= 16:
            raise ScientificValidationError("source_columns_required")
        if node.operation == "quantity_arithmetic" and not node.arithmetic:
            raise ScientificValidationError("quantity_arithmetic_kind_required")
        if node.operation in {"bootstrap_mean_ci", "monte_carlo_normal"} and node.controls.seed is None:
            raise ScientificValidationError("stochastic_seed_required")
        from core.scientific_linear_contract import LINEAR_PROGRAMS, validate_linear_inputs
        if node.operation in LINEAR_PROGRAMS and all(item.kind != "node" for item in node.inputs.values()):
            concrete = {port: item.value if item.kind == "literal" else symbols[item.symbol].value
                        for port, item in node.inputs.items()}
            try:
                validate_linear_inputs(concrete, node.operation)
            except ValueError as exc:
                raise ScientificValidationError(str(exc)) from exc
        seen[node.node_id] = dict(spec.outputs)
    for output in workflow.outputs:
        if output.port not in seen.get(output.node_id, {}):
            raise ScientificValidationError("requested_output_invalid")
        uses_units |= _check_unit(output.unit)
    if uses_units:
        if importlib.util.find_spec("pint") is None:
            raise ScientificValidationError("units_dependency_unavailable", "unsupported")
        import pint
        ureg = pint.UnitRegistry()
        try:
            output_units: dict[tuple[str, str], Any] = {}
            for symbol in workflow.symbols:
                ureg.Unit(symbol.unit)
            for node in workflow.nodes:
                referenced_symbols = set()
                for value in node.inputs.values():
                    if value.kind == "symbol":
                        referenced_symbols.add(value.symbol)
                expressions = [item for item in (node.expression, node.objective) if item is not None]
                expressions += [item for relation in node.relations for item in (relation.left, relation.right)]
                pending = list(expressions)
                while pending:
                    item = pending.pop()
                    if item.kind == "symbol":
                        referenced_symbols.add(item.symbol)
                    pending.extend(item.args)
                for unit in (node.unit, node.target_unit):
                    if unit:
                        ureg.Unit(unit)
                if node.operation == "unit_convert" or (node.operation == "quantity_arithmetic" and node.arithmetic in {"add", "subtract"}):
                    if ureg.Unit(node.unit).dimensionality != ureg.Unit(node.target_unit).dimensionality:
                        raise ScientificValidationError("dimension_mismatch")
                for expression in (node.expression, node.objective):
                    if expression is not None:
                        _dimensions(expression, symbols, ureg)
                for relation in node.relations:
                    if _dimensions(relation.left, symbols, ureg).dimensionality != _dimensions(relation.right, symbols, ureg).dimensionality and node.operation != "solve_ode_ivp":
                        raise ScientificValidationError("relation_dimension_mismatch")
                if node.operation == "solve_ode_ivp":
                    time_unit = ureg.Unit(symbols[node.variable].unit)
                    for relation in node.relations:
                        expected = ureg.Unit(symbols[relation.left.symbol].unit) / time_unit
                        actual = _dimensions(relation.right, symbols, ureg)
                        if actual.dimensionality != expected.dimensionality:
                            raise ScientificValidationError("ode_dimension_mismatch")
                unit_operation = node.operation in {"unit_convert", "dimensional_check", "quantity_arithmetic"}
                for port, item in node.inputs.items():
                    actual_unit = (ureg.Unit(symbols[item.symbol].unit) if item.kind == "symbol" else
                                   output_units.get((item.node_id, item.port), ureg.dimensionless) if item.kind == "node" else None)
                    if actual_unit is not None:
                        expected_unit = ureg.Unit(node.target_unit if port == "right" else node.unit) if unit_operation else ureg.dimensionless
                        if actual_unit.dimensionality != expected_unit.dimensionality:
                            raise ScientificValidationError("dimension_mismatch")
                        if actual_unit != expected_unit:
                            raise ScientificValidationError("explicit_unit_conversion_required", "clarification_required")
                if not unit_operation and any(_check_unit(symbols[name].unit) for name in referenced_symbols):
                    raise ScientificValidationError("unitful_operation_requires_verified_adapter", "unsupported")
                unit = ureg.dimensionless
                if node.operation == "unit_convert":
                    unit = ureg.Unit(node.target_unit)
                elif node.operation == "quantity_arithmetic":
                    left, right = ureg.Unit(node.unit), ureg.Unit(node.target_unit)
                    unit = left * right if node.arithmetic == "multiply" else left / right if node.arithmetic == "divide" else left
                for port, _ in operation_spec(node.operation).outputs:
                    output_units[(node.node_id, port)] = unit
            for output in workflow.outputs:
                if output.unit:
                    actual, requested = output_units[(output.node_id, output.port)], ureg.Unit(output.unit)
                    if actual.dimensionality != requested.dimensionality:
                        raise ScientificValidationError("dimension_mismatch")
                    if actual != requested:
                        raise ScientificValidationError("explicit_unit_conversion_required", "clarification_required")
        except ScientificValidationError:
            raise
        except Exception as exc:
            raise ScientificValidationError("unit_definition_invalid") from exc
    if original_message is not None:
        _numeric_provenance(workflow, original_message)
    return workflow
