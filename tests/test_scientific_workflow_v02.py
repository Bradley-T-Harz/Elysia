"""Behavioral Scientific IR, governed workflow, and native-worker boundaries."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("isolated_scientific_compute")

from app.api import scientific_workflow_service as workflow_service
from core.scientific_validation import ScientificValidationError, validate_scientific_workflow


def number(value):
    return {"kind": "number", "value": value}


def symbol(name):
    return {"kind": "symbol", "symbol": name}


def binary(kind, left, right):
    return {"kind": kind, "args": [left, right]}


def literal(value):
    return {"kind": "literal", "value": value, "provenance": "user"}


def flow(nodes, outputs, symbols=(), sources=()):
    return {"ir_version": "scientific-ir-v0.2", "symbols": list(symbols),
            "sources": list(sources), "nodes": nodes, "outputs": outputs}


def test_linear_system_and_composed_matrix_rank_use_real_workers(isolated_account_store):
    request = flow([
        {"node_id": "solve", "operation": "solve_linear_system", "inputs": {
            "matrix": literal([[2, 1], [1, 3]]), "rhs": literal([5, 7])},
            "verification": ["residual"]},
        {"node_id": "cov", "operation": "covariance_matrix", "inputs": {
            "values": literal([[1, 2], [2, 4], [3, 6]])}},
        {"node_id": "rank", "operation": "matrix_rank", "inputs": {
            "matrix": {"kind": "node", "node_id": "cov", "port": "matrix"}}},
    ], [{"node_id": "solve", "port": "solution"}, {"node_id": "rank", "port": "rank"}])
    result = workflow_service.run_scientific_workflow(request)
    assert result["status"] == "completed", result
    assert result["completed_node_count"] == 3
    assert result["outputs"]["rank.rank"] == 1
    assert result["outputs"]["solve.solution"] == pytest.approx([1.6, 1.8])
    assert all(row["parameter_sha256"] and row["result_sha256"] and row["verification"] == "passed" for row in result["node_receipts"])
    assert not result["network_used"]


def test_symbolic_calculus_and_numeric_root_are_same_governed_vocabulary(isolated_account_store):
    x = symbol("x")
    polynomial = binary("power", x, number(2))
    request = flow([
        {"node_id": "derivative", "operation": "differentiate", "expression": polynomial, "variable": "x"},
        {"node_id": "integral", "operation": "integrate", "expression": x, "variable": "x"},
        {"node_id": "root", "operation": "find_root", "expression": binary("subtract", polynomial, number(4)), "variable": "x", "bounds": [0, 3], "verification": ["convergence", "residual"]},
    ], [{"node_id": "derivative", "port": "expression"}, {"node_id": "integral", "port": "expression"}, {"node_id": "root", "port": "root"}],
        symbols=[{"name": "x", "role": "variable"}])
    result = workflow_service.run_scientific_workflow(request)
    assert result["status"] == "completed", result
    assert result["outputs"]["root.root"] == pytest.approx(2.0, abs=1e-6)
    assert result["outputs"]["derivative.expression"]["kind"] == "multiply"
    assert result["outputs"]["integral.expression"]["kind"] == "multiply"


@pytest.mark.parametrize("rate,initial,terminal", [(-1, 1, 0.3679), (-2, 1, 0.1353)])
def test_decay_ode_reuses_one_adapter_for_chemistry_and_environment(isolated_account_store, rate, initial, terminal):
    x = symbol("x")
    request = flow([{"node_id": "dynamics", "operation": "solve_ode_ivp", "variable": "t", "time_range": [0, 1],
        "initial_conditions": {"x": initial}, "relations": [{"relation": "equal", "left": x,
        "right": binary("multiply", number(rate), x)}],
        "verification": ["convergence"]}], [{"node_id": "dynamics", "port": "states"}],
        symbols=[{"name": "x", "role": "state"}, {"name": "t", "role": "variable"}])
    result = workflow_service.run_scientific_workflow(request)
    assert result["status"] == "completed", result
    assert result["outputs"]["dynamics.states"][-1][0] == pytest.approx(terminal, abs=1e-3)


def test_units_convert_and_dimensional_mismatch_refuse(isolated_account_store):
    good = flow([{"node_id": "convert", "operation": "unit_convert", "unit": "meter", "target_unit": "centimeter",
        "inputs": {"value": literal(2)}}], [{"node_id": "convert", "port": "value"}])
    result = workflow_service.run_scientific_workflow(good)
    assert result["status"] == "completed", result
    assert result["outputs"]["convert.value"] == 200
    bad = flow([{"node_id": "wrong", "operation": "evaluate_expression", "expression":
        binary("add", symbol("distance"), symbol("time"))}], [{"node_id": "wrong", "port": "value"}],
        symbols=[{"name": "distance", "role": "parameter", "unit": "meter", "value": 2, "provenance": "user"},
                 {"name": "time", "role": "parameter", "unit": "second", "value": 2, "provenance": "user"}])
    blocked = workflow_service.run_scientific_workflow(bad)
    assert blocked["status"] in {"blocked", "unsupported"}
    assert blocked["attempted_node_count"] == 0


def test_partial_failure_retains_first_node_without_promoting_parent(isolated_account_store):
    request = flow([
        {"node_id": "first", "operation": "matrix_rank", "inputs": {"matrix": literal([[1, 0], [0, 1]])}},
        {"node_id": "second", "operation": "solve_linear_system", "inputs": {
            "matrix": literal([[1, 1], [1, 1]]), "rhs": literal([1, 2])}},
    ], [{"node_id": "first", "port": "rank"}, {"node_id": "second", "port": "solution"}])
    result = workflow_service.run_scientific_workflow(request)
    assert result["status"] == "failed", result
    assert result["partial_completion"] is True
    assert result["completed_node_count"] == 1
    assert result["node_receipts"][0]["result"]["rank"] == 2
    assert result["node_receipts"][1]["status"] == "failed"
    assert result["outputs"] == {}


def test_untrusted_ir_has_no_python_paths_cycles_or_invented_numbers(isolated_account_store):
    malicious = flow([{"node_id": "n", "operation": "evaluate_expression", "expression":
        {"kind": "number", "value": 2, "python": "__import__('os')"}}], [{"node_id": "n", "port": "value"}])
    assert workflow_service.run_scientific_workflow(malicious)["status"] == "blocked"
    cyclic = flow([{"node_id": "n", "operation": "matrix_rank", "inputs": {
        "matrix": {"kind": "node", "node_id": "n", "port": "matrix"}}}], [{"node_id": "n", "port": "rank"}])
    assert workflow_service.run_scientific_workflow(cyclic)["reason"] == "workflow_forward_or_invalid_reference"
    invented = flow([{"node_id": "n", "operation": "evaluate_expression", "expression": number(127)}], [{"node_id": "n", "port": "value"}])
    assert workflow_service.run_scientific_workflow(invented, original_message="Calculate the requested value.")["status"] == "clarification_required"
    unsanctioned = flow([{"node_id": "n", "operation": "evaluate_expression", "expression": number(9)}],
                       [{"node_id": "n", "port": "value"}])
    unsanctioned["assumptions"] = ["Assume the factor is 9"]
    assert workflow_service.run_scientific_workflow(
        unsanctioned, original_message="Calculate the factor.")["reason"] == "assumption_not_user_authorized"
    ignored_unit = flow([{"node_id": "n", "operation": "matrix_rank", "unit": "meter",
                          "inputs": {"matrix": literal([[1]])}}], [{"node_id": "n", "port": "rank"}])
    assert workflow_service.run_scientific_workflow(ignored_unit)["reason"] == "operation_units_unsupported"


def test_real_parent_cancel_prevents_execution(isolated_account_store):
    request = flow([{"node_id": "n", "operation": "matrix_rank", "inputs": {"matrix": literal([[1]])}}], [{"node_id": "n", "port": "rank"}])
    result = workflow_service.run_scientific_workflow(request, parent_cancel_check=lambda: True)
    assert result["status"] == "cancelled"
    assert result["attempted_node_count"] == 0


@pytest.mark.parametrize("last_node", [False, True])
def test_parent_cancel_after_first_worker_retains_verified_partial_receipt(isolated_account_store, monkeypatch, last_node):
    request = flow([
        {"node_id": "first", "operation": "matrix_rank", "inputs": {"matrix": literal([[1, 0], [0, 1]])}},
        {"node_id": "second", "operation": "matrix_rank", "inputs": {"matrix": literal([[2, 0], [0, 3]])}},
    ], [{"node_id": "first", "port": "rank"}, {"node_id": "second", "port": "rank"}])
    if last_node:
        request["nodes"] = request["nodes"][:1]
        request["outputs"] = request["outputs"][:1]
    original = workflow_service._verify_result
    cancelled = False

    def verify_first_then_cancel(*args, **kwargs):
        nonlocal cancelled
        result = original(*args, **kwargs)
        cancelled = True
        return result

    monkeypatch.setattr(workflow_service, "_verify_result", verify_first_then_cancel)
    result = workflow_service.run_scientific_workflow(request, parent_cancel_check=lambda: cancelled)
    assert result["status"] == "cancelled"
    assert result["partial_completion"] is True
    assert result["completed_node_count"] == 1
    assert result["attempted_node_count"] == 1
    assert result["outputs"] == {}
    assert result["node_receipts"][0]["verification"] == "passed"


def test_user_compute_ceiling_refuses_work_before_worker(isolated_account_store, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(workflow_service, "current_user_controls", lambda: SimpleNamespace(
        cpu_percent_ceiling=1, ram_mb_ceiling=128, vram_mb_ceiling=0,
        max_background_jobs=0))
    monkeypatch.setattr(workflow_service, "run_scientific_worker_process", lambda *args, **kwargs:
                        pytest.fail("resource-refused workflow invoked worker"))
    request = flow([{"node_id": "n", "operation": "matrix_rank", "inputs": {"matrix": literal([[1]])}}],
                   [{"node_id": "n", "port": "rank"}])
    result = workflow_service.run_scientific_workflow(request)
    assert result["status"] == "blocked"
    assert result["reason"] == "workflow_exceeds_user_compute_ceiling"
    assert result["attempted_node_count"] == 0


def test_owner_bound_private_source_is_read_locally_and_root_stays_out_of_receipt(
    isolated_project_store, tmp_path, monkeypatch,
):
    from app.api import file_ingest_service, project_service, scientificforge_source_service
    monkeypatch.setattr(file_ingest_service, "DEFAULT_INGEST_ROOT", isolated_project_store.elysia_paths.ingest_dir)
    monkeypatch.setattr(scientificforge_source_service, "DEFAULT_INGEST_ROOT", isolated_project_store.elysia_paths.ingest_dir)
    project_id = project_service.create_project(name="Private scientific observations")["project_id"]
    source = tmp_path / "private-canary-measurements.csv"
    canary = "PRIVATE_SCIENTIFIC_SOURCE_CANARY_74B1"
    source.write_text(f"value,note\n1,{canary}\n3,local\n", encoding="utf-8")
    attached = file_ingest_service.attach_file(source, project_id=project_id)
    assert attached.ready is True
    request = flow([{
        "node_id": "summary", "operation": "descriptive_stats",
        "inputs": {"values": {"kind": "source", "source_id": "observations"}},
        "columns": ["value"],
    }], [{"node_id": "summary", "port": "summary"}],
        sources=[{"source_id": "observations", "file_id": attached.file_id}])
    denied = workflow_service.run_scientific_workflow(request, project_id=project_id)
    assert denied["status"] == "blocked"
    assert denied["attempted_node_count"] == 0
    result = workflow_service.run_scientific_workflow(
        request, allowed_file_ids={attached.file_id}, project_id=project_id,
        original_message="Summarize the attached selected dataset.",
    )
    assert result["status"] == "completed", result
    assert result["outputs"]["summary.summary"]["statistics"]["mean"] == 2
    assert result["node_receipts"][0]["source_sha256"] == attached.file.sha256
    encoded = json.dumps(result)
    assert str(source) not in encoded
    assert canary not in encoded


def test_coupled_oscillator_and_logistic_ode_share_the_same_bounded_adapter(isolated_account_store):
    physics = flow([{
        "node_id": "oscillator", "operation": "solve_ode_ivp", "variable": "t",
        "time_range": [0, 1], "initial_conditions": {"x": 1, "v": 0},
        "relations": [
            {"relation": "equal", "left": symbol("x"), "right": symbol("v")},
            {"relation": "equal", "left": symbol("v"), "right": binary("multiply", number(-1), symbol("x"))},
        ], "verification": ["convergence"],
    }], [{"node_id": "oscillator", "port": "states"}],
        symbols=[{"name": "x", "role": "state"}, {"name": "v", "role": "state"},
                 {"name": "t", "role": "variable"}])
    physics_result = workflow_service.run_scientific_workflow(physics)
    assert physics_result["status"] == "completed", physics_result["reason"]
    physics_row = physics_result["node_receipts"][0]["result"]
    terminal = dict(zip(physics_row["state_names"], physics_row["states"][-1]))
    assert terminal == pytest.approx({"x": 0.5403, "v": -0.84147}, abs=1e-3)

    population = symbol("population")
    biology = flow([{
        "node_id": "growth", "operation": "solve_ode_ivp", "variable": "t",
        "time_range": [0, 1], "initial_conditions": {"population": 1},
        "relations": [{"relation": "equal", "left": population,
                       "right": binary("multiply", population,
                           binary("subtract", number(1),
                               binary("divide", population, number(10))))}],
        "verification": ["convergence"],
    }], [{"node_id": "growth", "port": "states"}],
        symbols=[{"name": "population", "role": "state"}, {"name": "t", "role": "variable"}])
    biology_result = workflow_service.run_scientific_workflow(biology)
    assert biology_result["status"] == "completed", biology_result
    assert biology_result["outputs"]["growth.states"][-1][0] == pytest.approx(2.31969, abs=1e-3)


def test_conflicting_native_families_probe_in_distinct_worker_processes():
    import os
    import sys
    if importlib.util.find_spec("highspy") is None or importlib.util.find_spec("ortools") is None:
        pytest.skip("optional native backends are not installed in this environment")
    from app.api.scientificforge_process_service import run_scientific_worker_process
    results = []
    processes = []
    before = {name for name in ("highspy", "ortools") if name in sys.modules}
    for family in ("highspy", "ortools", "highspy"):
        result = run_scientific_worker_process({
            "ir_version": "scientific-ir-v0.2", "internal_backend_probe": True,
            "operation": "backend_probe", "backend_family": family,
        }, timeout_seconds=15, memory_limit_mb=2048)
        assert result["status"] == "completed", result
        assert result["diagnostics"]["separate_process"] is True
        assert result["result"]["native_version"]
        processes.append(result["result"]["process_id"])
        results.append(result["result"]["backend_family"])
    assert results == ["highspy", "ortools", "highspy"]
    assert len(set(processes)) == 3 and os.getpid() not in processes
    assert {name for name in ("highspy", "ortools") if name in sys.modules} == before
