"""Fixed mathematical adapters for validated Scientific IR nodes.

Each invocation runs in its own ScientificForge child address space. Imports
are selected from the trusted registry; model data never names a module.
"""

from __future__ import annotations

from importlib.metadata import version
import math
from typing import Any

from core.scientific_registry import BACKEND_MODULES, operation_spec


class ScientificAdapterError(ValueError):
    pass


class ScientificDependencyUnavailable(ScientificAdapterError):
    pass


def _finite(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ScientificAdapterError("nonfinite_numerical_result")
        return float(value) if isinstance(value, float) else int(value)
    if isinstance(value, list):
        return [_finite(item) for item in value]
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    return value


def _eval(tree: dict[str, Any], values: dict[str, float]) -> float:
    kind = tree["kind"]
    if kind == "number":
        answer = float(tree["value"])
    elif kind == "rational":
        answer = float(tree["numerator"]) / float(tree["denominator"])
    elif kind == "symbol":
        name = tree["symbol"]
        if name not in values:
            raise ScientificAdapterError("expression_symbol_value_missing")
        answer = float(values[name])
    else:
        args = [_eval(child, values) for child in tree["args"]]
        try:
            if kind == "add": answer = args[0] + args[1]
            elif kind == "subtract": answer = args[0] - args[1]
            elif kind == "multiply": answer = args[0] * args[1]
            elif kind == "divide": answer = args[0] / args[1]
            elif kind == "power": answer = args[0] ** args[1]
            elif kind == "negate": answer = -args[0]
            elif kind == "sin": answer = math.sin(args[0])
            elif kind == "cos": answer = math.cos(args[0])
            elif kind == "exp": answer = math.exp(args[0])
            elif kind == "log": answer = math.log(args[0])
            elif kind == "sqrt": answer = math.sqrt(args[0])
            else: raise ScientificAdapterError("expression_operation_invalid")
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise ScientificAdapterError("expression_domain_failure") from exc
    if isinstance(answer, complex) or not math.isfinite(answer):
        raise ScientificAdapterError("expression_nonfinite_result")
    return float(answer)


def _sympy(tree: dict[str, Any], symbols: dict[str, Any], sp: Any) -> Any:
    kind = tree["kind"]
    if kind == "number":
        value = tree["value"]
        return sp.Integer(value) if isinstance(value, int) else sp.Float(value)
    if kind == "rational":
        return sp.Rational(tree["numerator"], tree["denominator"])
    if kind == "symbol":
        return symbols[tree["symbol"]]
    args = [_sympy(child, symbols, sp) for child in tree["args"]]
    if kind == "add": return sp.Add(args[0], args[1], evaluate=False)
    if kind == "subtract": return sp.Add(args[0], -args[1], evaluate=False)
    if kind == "multiply": return sp.Mul(args[0], args[1], evaluate=False)
    if kind == "divide": return sp.Mul(args[0], sp.Pow(args[1], -1, evaluate=False), evaluate=False)
    if kind == "power": return sp.Pow(args[0], args[1], evaluate=False)
    if kind == "negate": return -args[0]
    return {"sin": sp.sin, "cos": sp.cos, "exp": sp.exp, "log": sp.log, "sqrt": sp.sqrt}[kind](args[0])


def _from_sympy(value: Any, sp: Any, depth: int = 0) -> dict[str, Any]:
    if depth > 16:
        raise ScientificAdapterError("symbolic_output_too_deep")
    if value.is_Integer:
        if abs(int(value)) > 10**30: raise ScientificAdapterError("symbolic_integer_excessive")
        return {"kind": "number", "value": int(value)}
    if value.is_Rational:
        if abs(int(value.p)) > 10**30 or abs(int(value.q)) > 10**30:
            raise ScientificAdapterError("symbolic_rational_excessive")
        return {"kind": "rational", "numerator": int(value.p), "denominator": int(value.q)}
    if value.is_Float:
        return {"kind": "number", "value": _finite(float(value))}
    if value.is_Symbol:
        return {"kind": "symbol", "symbol": str(value)}
    if value.is_Add or value.is_Mul:
        kind = "add" if value.is_Add else "multiply"
        parts = [_from_sympy(part, sp, depth + 1) for part in value.args]
        result = parts[0]
        for part in parts[1:]:
            result = {"kind": kind, "args": [result, part]}
        return result
    if value.is_Pow and value.exp.is_Integer and abs(int(value.exp)) <= 16:
        return {"kind": "power", "args": [_from_sympy(value.base, sp, depth + 1), _from_sympy(value.exp, sp, depth + 1)]}
    for name in ("sin", "cos", "exp", "log"):
        if value.func is getattr(sp, name):
            return {"kind": name, "args": [_from_sympy(value.args[0], sp, depth + 1)]}
    raise ScientificAdapterError("symbolic_output_not_in_typed_vocabulary")


def _arrays(job: dict[str, Any], np: Any) -> tuple[Any, Any]:
    a = np.asarray(job["inputs"]["matrix"], dtype=float)
    b = np.asarray(job["inputs"]["rhs"], dtype=float)
    if a.ndim != 2 or b.ndim != 1 or a.shape[0] != b.size or a.size > 4096:
        raise ScientificAdapterError("linear_system_shape_invalid")
    return a, b


def run_typed_operation(job: dict[str, Any]) -> dict[str, Any]:
    operation = str(job["operation"])
    spec = operation_spec(operation)
    if spec is None:
        raise ScientificAdapterError("unsupported_scientific_operation")
    backend = spec.backend
    if job.get("backend_family", backend) != backend:
        raise ScientificAdapterError("backend_family_operation_mismatch")
    if backend not in BACKEND_MODULES:
        raise ScientificAdapterError("backend_not_registered")
    inputs = job.get("inputs") or {}
    symbols = {item["name"]: item for item in job.get("symbols", [])}
    values = {name: float(item["value"]) for name, item in symbols.items() if isinstance(item.get("value"), (int, float))}
    controls = job.get("controls") or {}
    diagnostics: dict[str, Any] = {}
    if operation in {"evaluate_expression", "substitute_expression", "differentiate", "simplify_expression", "integrate"}:
        try: import sympy as sp
        except ImportError as exc: raise ScientificDependencyUnavailable("sympy_unavailable") from exc
        declared = {name: sp.Symbol(name, real=True) for name in symbols}
        expression = _sympy(job["expression"], declared, sp)
        replacements = {declared[name]: sp.Integer(value) if float(value).is_integer() else sp.Float(value) for name, value in values.items()}
        if operation == "evaluate_expression":
            symbolic = expression.subs(replacements)
            if symbolic.free_symbols: raise ScientificAdapterError("expression_values_required")
            result = {"value": _finite(float(symbolic))}
        elif operation == "substitute_expression":
            result = {"expression": _from_sympy(expression.subs(replacements), sp)}
        elif operation == "differentiate":
            result = {"expression": _from_sympy(sp.diff(expression, declared[job["variable"]]), sp)}
        elif operation == "simplify_expression":
            result = {"expression": _from_sympy(sp.cancel(expression), sp)}
        else:
            variable = declared[job["variable"]]
            integral = sp.integrate(expression, variable, risch=True)
            if integral.has(sp.Integral): raise ScientificAdapterError("integral_unevaluated")
            result = {"expression": _from_sympy(integral, sp)}
    elif backend == "numpy":
        try: import numpy as np
        except ImportError as exc: raise ScientificDependencyUnavailable("numpy_unavailable") from exc
        if operation in {"solve_linear_system", "least_squares", "linear_regression"}:
            a, b = _arrays(job, np)
            if operation == "solve_linear_system":
                if a.shape[0] != a.shape[1]: raise ScientificAdapterError("linear_system_not_square")
                condition = float(np.linalg.cond(a))
                if not math.isfinite(condition) or condition > 1e12:
                    raise ScientificAdapterError("linear_system_ill_conditioned")
                solution = np.linalg.solve(a, b)
                residual = float(np.linalg.norm(a @ solution - b))
                diagnostics.update(condition=condition, residual=residual)
                result = {"solution": solution.tolist()}
            else:
                solution, _, rank, _ = np.linalg.lstsq(a, b, rcond=None)
                residuals = b - a @ solution
                diagnostics.update(rank=int(rank), residual=float(np.linalg.norm(residuals)),
                    normal_equation_residual=float(np.linalg.norm(a.T @ residuals)),
                    rank_deficient=bool(rank < a.shape[1]))
                result = {("coefficients" if operation == "linear_regression" else "solution"): solution.tolist(), "residuals": residuals.tolist()}
        elif operation in {"matrix_rank", "determinant", "pseudoinverse"}:
            a = np.asarray(inputs["matrix"], dtype=float)
            if a.ndim != 2 or a.size > 4096: raise ScientificAdapterError("matrix_shape_invalid")
            if operation == "matrix_rank": result = {"rank": int(np.linalg.matrix_rank(a))}
            elif operation == "determinant":
                if a.shape[0] != a.shape[1]: raise ScientificAdapterError("determinant_not_square")
                result = {"value": float(np.linalg.det(a))}
            else:
                result = {"matrix": np.linalg.pinv(a).tolist()}
                diagnostics["reconstruction_residual"] = float(np.linalg.norm(a @ np.asarray(result["matrix"]) @ a - a))
        elif operation == "covariance_matrix":
            a = np.asarray(inputs["values"], dtype=float)
            if a.ndim != 2 or a.shape[0] < 2 or a.shape[1] < 2: raise ScientificAdapterError("covariance_needs_observations")
            result = {"matrix": np.cov(a, rowvar=False).tolist()}
        elif operation == "correlation_matrix" and not job.get("source_snapshot"):
            a = np.asarray(inputs["values"], dtype=float)
            if a.ndim != 2 or a.shape[0] < 2 or a.shape[1] < 2:
                raise ScientificAdapterError("correlation_needs_observations")
            result = {"matrix": np.corrcoef(a, rowvar=False).tolist()}
        else:
            from sandbox.scientificforge_worker.worker import run_scientific_job
            legacy_inputs = dict(inputs)
            if operation == "matrix_multiply":
                legacy_inputs = {"matrix_a": inputs["matrix_a"], "matrix_b": inputs["matrix_b"]}
            legacy = run_scientific_job({"operation": operation, **legacy_inputs,
                "columns": job.get("columns", []), "seed": controls.get("seed"),
                "source_snapshot": job.get("source_snapshot"),
                "expected_source_sha256": job.get("expected_source_sha256")})
            raw = legacy["result"]
            if operation == "descriptive_stats": result = {"summary": raw}
            elif operation == "correlation_matrix": result = {"matrix": raw["matrix"]}
            elif operation == "bootstrap_mean_ci": result = {"interval": raw}
            elif operation == "matrix_multiply": result = {"matrix": raw["matrix"]}
            else: result = {"summary": raw}
            diagnostics["legacy_result_contract"] = True
    elif backend == "scipy":
        try:
            import numpy as np
            from scipy import integrate, optimize
        except ImportError as exc:
            raise ScientificDependencyUnavailable("scipy_unavailable") from exc
        expression = job.get("expression")
        variable = job.get("variable")
        a, b = (job.get("bounds") or job.get("time_range") or (None, None))
        if operation in {"find_root", "numerical_integral", "minimize_scalar"}:
            calls = 0
            def function(x: float) -> float:
                nonlocal calls
                calls += 1
                if calls > int(controls.get("maximum_evaluations", 2000)):
                    raise ScientificAdapterError("evaluation_budget_exceeded")
                return _eval(expression, {**values, variable: float(x)})
            if operation == "find_root":
                value, info = optimize.brentq(function, a, b, xtol=controls.get("absolute_tolerance", 1e-8), rtol=max(controls.get("relative_tolerance", 1e-8), 1e-14), maxiter=controls.get("maximum_iterations", 200), full_output=True, disp=False)
                residual = abs(function(value))
                # SciPy does not define its iteration counter for an endpoint root.
                diagnostics.update(converged=bool(info.converged), iterations=0 if value in (a, b) else int(info.iterations), evaluations=calls, residual=residual)
                if not info.converged: raise ScientificAdapterError("root_not_converged")
                result = {"root": float(value)}
            elif operation == "numerical_integral":
                value, error = integrate.quad(function, a, b, epsabs=controls.get("absolute_tolerance", 1e-8), epsrel=controls.get("relative_tolerance", 1e-8), limit=min(100, controls.get("maximum_iterations", 200)))
                diagnostics.update(error_estimate=float(error), evaluations=calls)
                result = {"value": float(value)}
            else:
                fit = optimize.minimize_scalar(function, bounds=(a, b), method="bounded", options={"xatol": controls.get("absolute_tolerance", 1e-8), "maxiter": controls.get("maximum_iterations", 200)})
                diagnostics.update(converged=bool(fit.success), iterations=int(fit.nit), evaluations=calls, termination=str(fit.message)[:120])
                if not fit.success: raise ScientificAdapterError("minimization_not_converged")
                result = {"minimum": float(fit.x), "objective_value": float(fit.fun)}
        elif operation == "solve_ode_ivp":
            state_names = sorted(job["initial_conditions"])
            relations = {item["left"]["symbol"]: item["right"] for item in job["relations"]}
            calls = 0
            def derivative(t: float, y: Any) -> list[float]:
                nonlocal calls
                calls += 1
                if calls > int(controls.get("maximum_evaluations", 2000)):
                    raise ScientificAdapterError("ode_evaluation_budget_exceeded")
                current = {**values, variable: float(t), **dict(zip(state_names, y))}
                return [_eval(relations[name], current) for name in state_names]
            sample = np.linspace(a, b, int(job["output_points"]))
            solution = integrate.solve_ivp(derivative, (a, b), [job["initial_conditions"][name] for name in state_names], method="RK45", t_eval=sample, rtol=controls.get("relative_tolerance", 1e-8), atol=controls.get("absolute_tolerance", 1e-8), max_step=(b-a)/10)
            diagnostics.update(converged=bool(solution.success), evaluations=int(solution.nfev), termination=str(solution.message)[:120])
            if not solution.success: raise ScientificAdapterError("ode_not_converged")
            result = {"times": solution.t.tolist(), "states": solution.y.T.tolist(), "state_names": state_names}
        else:
            raise ScientificAdapterError("scipy_operation_unsupported")
    elif backend == "highspy":
        from sandbox.scientificforge_worker.linear_programs import solve_linear_program
        try:
            result, diagnostics = solve_linear_program(inputs, operation, controls)
        except ImportError as exc:
            raise ScientificDependencyUnavailable("highspy_unavailable") from exc
        except ValueError as exc:
            raise ScientificAdapterError(str(exc)) from exc
        if result is None:
            return {"status": "failed", "operation": operation,
                    "blocked_reason": "linear_program_not_optimal", "diagnostics": diagnostics,
                    "engine_versions": {"highspy": version("highspy")},
                    "network_access_used": False, "source_mutated": False,
                    "arbitrary_python_used": False, "shell_used": False, "package_install_used": False}
    elif backend == "pint":
        try: import pint
        except ImportError as exc: raise ScientificDependencyUnavailable("pint_unavailable") from exc
        ureg = pint.UnitRegistry()
        left_unit = ureg.Unit(job["unit"])
        right_unit = ureg.Unit(job["target_unit"])
        if operation == "unit_convert":
            amount = ureg.Quantity(float(inputs["value"]), left_unit).to(right_unit)
            result = {"value": float(amount.magnitude), "unit": str(amount.units)}
            diagnostics["dimensions"] = str(amount.dimensionality)
        elif operation == "dimensional_check":
            result = {"compatible": bool(left_unit.dimensionality == right_unit.dimensionality)}
            diagnostics["dimensions"] = [str(left_unit.dimensionality), str(right_unit.dimensionality)]
        else:
            left = ureg.Quantity(float(inputs["left"]), left_unit)
            right = ureg.Quantity(float(inputs["right"]), right_unit)
            action = job["arithmetic"]
            if action == "add": amount = left + right
            elif action == "subtract": amount = left - right
            elif action == "multiply": amount = left * right
            elif action == "divide": amount = left / right
            else: raise ScientificAdapterError("quantity_arithmetic_invalid")
            result = {"value": float(amount.magnitude), "unit": str(amount.units)}
            diagnostics["dimensions"] = str(amount.dimensionality)
    else:
        raise ScientificAdapterError("backend_family_not_executable")
    diagnostics["tolerances"] = {"absolute": controls.get("absolute_tolerance", 1e-8),
                                 "relative": controls.get("relative_tolerance", 1e-8)}
    result = _finite(result)
    diagnostics = _finite(diagnostics)
    return {
        "status": "completed", "operation": operation, "result": result,
        "diagnostics": diagnostics, "seed_used": controls.get("seed"),
        "engine_versions": {backend: version(BACKEND_MODULES[backend])},
        "network_access_used": False, "source_mutated": False,
        "arbitrary_python_used": False, "shell_used": False,
        "package_install_used": False,
    }
