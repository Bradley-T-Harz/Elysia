"""Backend-independent bounds and verification for finite linear programs."""
import math

LINEAR_PROGRAMS = {"linear_program", "mixed_integer_linear_program"}


def validate_linear_inputs(values, operation):
    names = {"cost", "matrix", "rhs", "lower", "upper"}
    if operation == "mixed_integer_linear_program":
        names.add("integrality")
    if set(values) != names:
        raise ValueError("linear_program_ports_invalid")
    cost, matrix, rhs = values["cost"], values["matrix"], values["rhs"]
    if not isinstance(cost, list) or not 1 <= len(cost) <= 32:
        raise ValueError("linear_program_variable_limit")
    n = len(cost)
    if (not isinstance(matrix, list) or not 1 <= len(matrix) <= 64
            or not isinstance(rhs, list) or len(rhs) != len(matrix)
            or any(not isinstance(row, list) or len(row) != n for row in matrix)
            or any(not isinstance(values[key], list) or len(values[key]) != n for key in {"lower", "upper"})):
        raise ValueError("linear_program_shape_invalid")
    flat = cost + rhs + values["lower"] + values["upper"] + [x for row in matrix for x in row]
    if any(type(v) not in {int, float} or not math.isfinite(v) or abs(v) > 1e12 for v in flat):
        raise ValueError("linear_program_number_invalid")
    if any(a > b for a, b in zip(values["lower"], values["upper"])):
        raise ValueError("linear_program_bounds_invalid")
    if operation == "mixed_integer_linear_program":
        integral = values["integrality"]
        if (not isinstance(integral, list) or len(integral) != n
                or any(type(x) is not int or x not in {0, 1} for x in integral)):
            raise ValueError("linear_program_integrality_invalid")


def linear_solution_diagnostics(values, solution):
    if not isinstance(solution, list) or len(solution) != len(values["cost"]):
        raise ValueError("linear_program_solution_shape_invalid")
    if any(type(x) not in {int, float} or not math.isfinite(x) for x in solution):
        raise ValueError("linear_program_solution_nonfinite")
    residuals = [sum(a*x for a, x in zip(row, solution)) - b
                 for row, b in zip(values["matrix"], values["rhs"])]
    violations = residuals + [lo-x for lo, x in zip(values["lower"], solution)] + [
        x-hi for hi, x in zip(values["upper"], solution)]
    integral = max([0.] + [abs(x-round(x)) for x, flag in zip(solution, values.get("integrality", [])) if flag])
    return {"constraint_violation": max([0.] + violations), "integrality_violation": integral,
            "objective": sum(c*x for c, x in zip(values["cost"], solution))}
