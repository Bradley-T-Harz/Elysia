"""Strict mathematical data contract for ScientificForge v0.2.

No model-owned field is an executable program, import, or filesystem path.
"""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, field_validator, model_validator


IR_VERSION = "scientific-ir-v0.2"
Number = StrictInt | StrictFloat
NumericValue = Number | list[Number] | list[list[Number]]
Identifier = str


class StrictIR(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


def _finite(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("boolean_is_not_numeric")
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError("nonfinite_or_excessive_number")
    elif isinstance(value, list):
        for item in value:
            _finite(item)
    elif isinstance(value, dict):
        for item in value.values():
            _finite(item)
    return value


class Expression(StrictIR):
    kind: Literal["number", "rational", "symbol", "add", "subtract", "multiply", "divide", "power", "negate", "sin", "cos", "exp", "log", "sqrt"]
    value: Number | None = None
    numerator: StrictInt | None = None
    denominator: StrictInt | None = None
    symbol: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    args: list[Expression] = Field(default_factory=list, max_length=2)

    @field_validator("value")
    @classmethod
    def finite_number(cls, value: Number | None) -> Number | None:
        return _finite(value) if value is not None else None


class ScientificSymbol(StrictIR):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    role: Literal["variable", "parameter", "constant", "state", "observation"]
    shape: Literal["scalar", "vector", "matrix"] = "scalar"
    unit: str = Field(default="dimensionless", max_length=48)
    value: NumericValue | None = None
    provenance: Literal["user", "selected_source", "trusted_constant", "assumption"] | None = None
    lower: Number | None = None
    upper: Number | None = None
    uncertainty: Number | None = None

    @field_validator("value", "lower", "upper", "uncertainty")
    @classmethod
    def finite_value(cls, value: object) -> object:
        return _finite(value)


class ScientificRelation(StrictIR):
    relation: Literal["equal", "less_equal", "greater_equal"]
    left: Expression
    right: Expression


class ScientificSource(StrictIR):
    source_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    file_id: str = Field(pattern=r"^file_[0-9a-f]{16}$")


class ScientificInput(StrictIR):
    kind: Literal["literal", "symbol", "node", "source"]
    value: NumericValue | None = None
    symbol: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    node_id: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    port: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    source_id: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    provenance: Literal["user", "selected_source", "trusted_constant", "assumption"] | None = None

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: NumericValue | None) -> NumericValue | None:
        return _finite(value)  # type: ignore[return-value]

    @model_validator(mode="after")
    def one_payload(self) -> Self:
        fields = {"value": self.value, "symbol": self.symbol, "node": self.node_id, "source": self.source_id}
        selected = {"literal": "value", "node": "node", "symbol": "symbol", "source": "source"}[self.kind]
        if fields[selected] is None or any(value is not None for key, value in fields.items() if key != selected):
            raise ValueError("input_kind_payload_mismatch")
        if self.kind == "node" and not self.port:
            raise ValueError("node_output_port_required")
        if self.kind != "node" and self.port is not None:
            raise ValueError("unexpected_output_port")
        return self


class SolverControls(StrictIR):
    absolute_tolerance: StrictFloat = Field(default=1e-8, gt=0, le=1e-3)
    relative_tolerance: StrictFloat = Field(default=1e-8, gt=0, le=1e-3)
    maximum_evaluations: StrictInt = Field(default=2000, ge=1, le=20_000)
    maximum_iterations: StrictInt = Field(default=200, ge=1, le=500)
    seed: StrictInt | None = Field(default=None, ge=0, le=4_294_967_295)


class ScientificNode(StrictIR):
    node_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    operation: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    inputs: dict[str, ScientificInput] = Field(default_factory=dict, max_length=8)
    columns: list[str] = Field(default_factory=list, max_length=16)
    expression: Expression | None = None
    variable: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    relations: list[ScientificRelation] = Field(default_factory=list, max_length=8)
    objective: Expression | None = None
    initial_conditions: dict[str, Number] = Field(default_factory=dict, max_length=8)
    bounds: list[Number] | None = Field(default=None, min_length=2, max_length=2)
    time_range: list[Number] | None = Field(default=None, min_length=2, max_length=2)
    output_points: StrictInt = Field(default=101, ge=2, le=1000)
    unit: str | None = Field(default=None, max_length=48)
    target_unit: str | None = Field(default=None, max_length=48)
    arithmetic: Literal["add", "subtract", "multiply", "divide"] | None = None
    controls: SolverControls = Field(default_factory=SolverControls)
    verification: list[Literal["finite", "residual", "convergence", "dimensions", "constraint"]] = Field(default_factory=list, max_length=5)

    @field_validator("bounds", "time_range", "initial_conditions")
    @classmethod
    def finite_bounds(cls, value: object) -> object:
        return _finite(value)


class ScientificOutput(StrictIR):
    node_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    port: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    unit: str | None = Field(default=None, max_length=48)


class ScientificWorkflow(StrictIR):
    ir_version: Literal["scientific-ir-v0.2"] = IR_VERSION
    symbols: list[ScientificSymbol] = Field(default_factory=list, max_length=64)
    sources: list[ScientificSource] = Field(default_factory=list, max_length=4)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    nodes: list[ScientificNode] = Field(min_length=1, max_length=12)
    outputs: list[ScientificOutput] = Field(min_length=1, max_length=12)

    @field_validator("assumptions")
    @classmethod
    def bounded_assumptions(cls, values: list[str]) -> list[str]:
        if any(len(value) > 160 for value in values):
            raise ValueError("assumption_too_long")
        return values


class ScientificFormulation(StrictIR):
    status: Literal["proposed", "clarification_required", "reference_required", "unsupported"]
    workflow: ScientificWorkflow | None = None
    reason: str = Field(default="", max_length=160)

    @model_validator(mode="after")
    def proposal_or_reason(self) -> Self:
        if self.status == "proposed" and self.workflow is None:
            raise ValueError("proposed_workflow_missing")
        if self.status != "proposed" and self.workflow is not None:
            raise ValueError("nonexecution_state_cannot_carry_workflow")
        return self


def formulation_json_schema() -> dict:
    """Compact model-facing view of the same strict server contract."""
    from core.scientific_registry import OPERATIONS
    schema = ScientificFormulation.model_json_schema()

    def compact(value):
        if isinstance(value, dict):
            return {key: compact(item) for key, item in value.items()
                    if key not in {"title", "description", "default"}}
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    schema = compact(schema)
    properties = schema["$defs"]["ScientificNode"]["properties"]
    variants = []
    for spec in OPERATIONS.values():
        fields = {name: properties[name] for name in spec.node_fields}
        fields["operation"] = {"const": spec.name, "type": "string"}
        fields["inputs"] = {"type": "object", "additionalProperties": False,
                            "properties": {name: {"$ref": "#/$defs/ScientificInput"} for name, _ in spec.inputs},
                            "required": [name for name, _ in spec.inputs]}
        supported_checks = ["finite"] + [name for name in ("residual", "convergence", "dimensions", "constraint") if name in spec.diagnostics]
        fields["verification"] = {"type": "array", "items": {"enum": supported_checks}, "maxItems": 5}
        variants.append({"type": "object", "additionalProperties": False,
                         "properties": fields, "required": ["node_id", "operation", "inputs"]})
    schema["$defs"]["ScientificNode"] = {"oneOf": variants}
    schema["$defs"]["ScientificOutput"]["properties"]["port"]["enum"] = sorted({port for spec in OPERATIONS.values() for port, _ in spec.outputs})
    return schema
