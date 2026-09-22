"""Fixed ScientificForge operation metadata shared by validation and workers.

This is data about compiled adapters, never a caller-selected import target.
The five v0.1 names remain valid and keep their existing request contract.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OperationSpec:
    name: str
    inputs: tuple[tuple[str, str], ...]
    outputs: tuple[tuple[str, str], ...]
    backend: str
    estimate: tuple[int, int, int]  # CPU percent, RAM MiB, duration ms
    diagnostics: tuple[str, ...] = ()
    deterministic: bool = True
    source_allowed: bool = False

    @property
    def node_fields(self) -> tuple[str, ...]:
        """Mathematical fields meaningful for this registered adapter."""
        fields = ["node_id", "operation", "inputs", "controls", "verification"]
        if self.source_allowed:
            fields.append("columns")
        if self.backend == "sympy" or self.name in {"find_root", "numerical_integral", "minimize_scalar"}:
            fields.append("expression")
        if self.name in {"differentiate", "integrate", "find_root", "numerical_integral", "minimize_scalar", "solve_ode_ivp"}:
            fields.append("variable")
        if self.name in {"find_root", "numerical_integral", "minimize_scalar"}:
            fields.append("bounds")
        if self.name == "solve_ode_ivp":
            fields.extend(("relations", "initial_conditions", "time_range", "output_points"))
        if self.backend == "pint":
            fields.extend(("unit", "target_unit"))
        if self.name == "quantity_arithmetic":
            fields.append("arithmetic")
        return tuple(fields)


REGISTRY_VERSION = "scientific-registry-v0.2"
MAX_WORKFLOW_NODES = 12
MAX_WORKFLOW_SECONDS = 120
MAX_RESULT_BYTES = 512 * 1024
MAX_EXPRESSION_NODES = 256
MAX_EXPRESSION_DEPTH = 16

_SPECS = (
    OperationSpec("descriptive_stats", (("values", "vector"),), (("summary", "object"),), "numpy", (20, 512, 5_000), source_allowed=True),
    OperationSpec("correlation_matrix", (("values", "matrix"),), (("matrix", "matrix"),), "numpy", (35, 1024, 10_000), source_allowed=True),
    OperationSpec("bootstrap_mean_ci", (("values", "vector"),), (("interval", "object"),), "numpy", (45, 1536, 20_000), ("seed",), source_allowed=True),
    OperationSpec("matrix_multiply", (("matrix_a", "matrix"), ("matrix_b", "matrix")), (("matrix", "matrix"),), "numpy", (30, 1024, 5_000)),
    OperationSpec("monte_carlo_normal", (), (("summary", "object"),), "numpy", (35, 1024, 10_000), ("seed",)),
    OperationSpec("evaluate_expression", (), (("value", "scalar"),), "sympy", (25, 512, 10_000)),
    OperationSpec("substitute_expression", (), (("expression", "expression"),), "sympy", (25, 512, 10_000)),
    OperationSpec("differentiate", (), (("expression", "expression"),), "sympy", (35, 768, 15_000)),
    OperationSpec("simplify_expression", (), (("expression", "expression"),), "sympy", (35, 768, 15_000)),
    OperationSpec("integrate", (), (("expression", "expression"),), "sympy", (40, 1024, 20_000)),
    OperationSpec("solve_linear_system", (("matrix", "matrix"), ("rhs", "vector")), (("solution", "vector"),), "numpy", (35, 768, 10_000), ("residual", "condition")),
    OperationSpec("least_squares", (("matrix", "matrix"), ("rhs", "vector")), (("solution", "vector"), ("residuals", "vector")), "numpy", (40, 1024, 15_000), ("rank", "residual")),
    OperationSpec("matrix_rank", (("matrix", "matrix"),), (("rank", "scalar"),), "numpy", (30, 768, 10_000)),
    OperationSpec("determinant", (("matrix", "matrix"),), (("value", "scalar"),), "numpy", (30, 768, 10_000)),
    OperationSpec("pseudoinverse", (("matrix", "matrix"),), (("matrix", "matrix"),), "numpy", (40, 1024, 15_000), ("residual",)),
    OperationSpec("linear_regression", (("matrix", "matrix"), ("rhs", "vector")), (("coefficients", "vector"), ("residuals", "vector")), "numpy", (40, 1024, 15_000), ("rank", "residual")),
    OperationSpec("covariance_matrix", (("values", "matrix"),), (("matrix", "matrix"),), "numpy", (30, 768, 10_000)),
    OperationSpec("find_root", (), (("root", "scalar"),), "scipy", (35, 768, 15_000), ("convergence", "iterations", "residual")),
    OperationSpec("numerical_integral", (), (("value", "scalar"),), "scipy", (35, 768, 15_000), ("error_estimate",)),
    OperationSpec("minimize_scalar", (), (("minimum", "scalar"),), "scipy", (40, 768, 20_000), ("convergence", "iterations")),
    OperationSpec("solve_ode_ivp", (), (("times", "vector"), ("states", "matrix")), "scipy", (45, 1536, 30_000), ("convergence", "evaluations")),
    OperationSpec("unit_convert", (("value", "scalar"),), (("value", "scalar"),), "pint", (20, 512, 5_000), ("dimensions",)),
    OperationSpec("dimensional_check", (), (("compatible", "boolean"),), "pint", (20, 512, 5_000), ("dimensions",)),
    OperationSpec("quantity_arithmetic", (("left", "scalar"), ("right", "scalar")), (("value", "scalar"),), "pint", (20, 512, 5_000), ("dimensions",)),
    OperationSpec("linear_program", (("cost", "vector"), ("matrix", "matrix"), ("rhs", "vector"),
        ("lower", "vector"), ("upper", "vector")), (("solution", "vector"), ("objective", "scalar")),
        "highspy", (25, 1536, 20_000), ("convergence", "constraint")),
    OperationSpec("mixed_integer_linear_program", (("cost", "vector"), ("matrix", "matrix"), ("rhs", "vector"),
        ("lower", "vector"), ("upper", "vector"), ("integrality", "vector")),
        (("solution", "vector"), ("objective", "scalar")), "highspy", (25, 1536, 20_000), ("convergence", "constraint")),
)

OPERATIONS = {spec.name: spec for spec in _SPECS}
BACKEND_MODULES = {
    "numpy": "numpy",
    "sympy": "sympy",
    "scipy": "scipy",
    "pint": "pint",
    # Native families are reserved for separately launched fixed adapters.
    "highspy": "highspy",
    "ortools": "ortools",
}


def operation_spec(name: str) -> OperationSpec | None:
    return OPERATIONS.get(name)
