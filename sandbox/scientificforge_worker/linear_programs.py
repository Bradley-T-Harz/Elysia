"""Fixed HiGHS adapter, imported only in its fresh scientific worker process.

No OR-Tools import, arbitrary model files, callbacks, or solver commands.
"""
from core.scientific_linear_contract import validate_linear_inputs, linear_solution_diagnostics


def solve_linear_program(values, operation, controls):
    validate_linear_inputs(values, operation)
    import highspy as hs
    solver = hs.Highs()
    tolerance = max(1e-10, controls.get("absolute_tolerance", 1e-8))
    options = {"output_flag": False, "threads": 1, "parallel": "off",
               "time_limit": 15., "simplex_iteration_limit": controls.get("maximum_iterations", 200),
               "ipm_iteration_limit": controls.get("maximum_iterations", 200),
               "primal_feasibility_tolerance": tolerance, "dual_feasibility_tolerance": tolerance,
               "random_seed": (controls.get("seed") or 0) % 2147483647}
    if operation == "mixed_integer_linear_program":
        options.update(mip_max_nodes=2048, mip_feasibility_tolerance=tolerance,
                       mip_rel_gap=0., mip_abs_gap=0.)
    for key, value in options.items():
        if solver.setOptionValue(key, value) != hs.HighsStatus.kOk:
            raise ValueError("linear_program_solver_option_rejected")
    model = hs.HighsLp()
    n, m = len(values["cost"]), len(values["matrix"])
    model.num_col_, model.num_row_ = n, m
    model.col_cost_ = values["cost"]
    model.col_lower_, model.col_upper_ = values["lower"], values["upper"]
    model.row_lower_, model.row_upper_ = [-hs.kHighsInf] * m, values["rhs"]
    model.a_matrix_.format_ = hs.MatrixFormat.kRowwise
    model.a_matrix_.num_col_, model.a_matrix_.num_row_ = n, m
    model.a_matrix_.start_ = [i*n for i in range(m+1)]
    model.a_matrix_.index_ = list(range(n)) * m
    model.a_matrix_.value_ = [v for row in values["matrix"] for v in row]
    if operation == "mixed_integer_linear_program":
        model.integrality_ = [hs.HighsVarType.kInteger if flag else hs.HighsVarType.kContinuous
                              for flag in values["integrality"]]
    if solver.passModel(model) != hs.HighsStatus.kOk:
        raise ValueError("linear_program_model_rejected")
    solver.run()
    status = solver.getModelStatus()
    info = solver.getInfo()
    diagnostics = {"solver_method": "highs", "termination": status.name,
                   "converged": status == hs.HighsModelStatus.kOptimal,
                   "iterations": info.simplex_iteration_count + info.ipm_iteration_count,
                   "mip_nodes": info.mip_node_count if operation == "mixed_integer_linear_program" else 0,
                   "solver_tolerance": tolerance, "solver_wall_limit_seconds": 15.,
                   "native_threads": 1, "optimality": "solver_reported"}
    if not diagnostics["converged"]:
        return None, diagnostics
    solution = solver.getSolution().col_value
    checks = linear_solution_diagnostics(values, solution)
    diagnostics.update(checks)
    return {"solution": solution, "objective": checks["objective"]}, diagnostics
