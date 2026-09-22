"""Bounded decision optimization through real, isolated ScientificForge workers."""
import pytest
from app.api import scientific_workflow_service as service
from tests.test_scientific_workflow_v02 import flow, literal

pytestmark = pytest.mark.usefixtures("isolated_scientific_compute")


def problem(integer=False):
    values = {"cost": [-3, -4], "matrix": [[1, 0], [0, 1], [1, 1]],
              "rhs": [10, 2, 12], "lower": [0, 0], "upper": [20, 20]}
    if integer:
        values["integrality"] = [1, 1]
    node = {"node_id": "decision", "operation": "mixed_integer_linear_program" if integer else "linear_program",
            "inputs": {name: literal(value) for name, value in values.items()},
            "verification": ["convergence", "constraint"]}
    return flow([node], [{"node_id": "decision", "port": "solution"}, {"node_id": "decision", "port": "objective"}])


@pytest.mark.parametrize("integer", [False, True])
def test_real_linear_decision_worker_and_independent_verification(isolated_account_store, integer):
    result = service.run_scientific_workflow(problem(integer))
    assert result["status"] == "completed", result
    assert result["outputs"]["decision.solution"] == pytest.approx([10, 2])
    assert result["outputs"]["decision.objective"] == pytest.approx(-38)
    receipt = result["node_receipts"][0]
    assert receipt["backend_family"] == "highspy"
    assert receipt["verification"] == "passed"
    assert receipt["parameter_sha256"] and receipt["result_sha256"]
    assert receipt["diagnostics"]["constraint_violation"] <= 1e-8
    assert receipt["diagnostics"]["native_threads"] == 1
    assert not result["network_used"]


@pytest.mark.parametrize("bad", ["shape", "bounds", "integrality", "size"])
def test_invalid_program_rejected_before_worker(isolated_account_store, monkeypatch, bad):
    request = problem(True)
    values = request["nodes"][0]["inputs"]
    if bad == "shape":values["rhs"] = literal([1])
    elif bad == "bounds":values["lower"] = literal([21, 0])
    elif bad == "integrality":values["integrality"] = literal([0, 2])
    else:values["cost"] = literal([1]*33)
    monkeypatch.setattr(service, "run_scientific_worker_process", lambda *a, **k: pytest.fail("invalid IR launched worker"))
    result = service.run_scientific_workflow(request)
    assert result["status"] == "blocked", result
    assert not result["execution_attempted"] and not result["outputs"]


def test_infeasible_program_is_not_a_completed_result(isolated_account_store):
    request = problem()
    request["nodes"][0]["inputs"]["rhs"] = literal([-1, 2, 12])
    result = service.run_scientific_workflow(request)
    assert result["status"] == "failed", result
    assert not result["outputs"]
    assert result["completed_node_count"] == 0
    assert result["node_receipts"][0]["worker_attempted"] is True


def test_forged_solver_success_does_not_prove_feasibility(isolated_account_store, monkeypatch):
    from copy import deepcopy
    actual = service.run_scientific_worker_process
    def forged(*args, **kwargs):
        result = deepcopy(actual(*args, **kwargs))
        result["result"]["solution"] = [100, 100]
        return result
    monkeypatch.setattr(service, "run_scientific_worker_process", forged)
    result = service.run_scientific_workflow(problem())
    assert result["status"] == "failed"
    assert not result["outputs"]
    assert result["reason"] == "linear_program_constraint_violation"
