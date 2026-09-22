"""Behavioral cancellation, numerical truth, and legacy coexistence proofs."""
from pathlib import Path
import sys
import time
from threading import Event

import pytest

pytestmark = pytest.mark.usefixtures("isolated_scientific_compute")

from app.api import scientific_workflow_service as service
from tests.test_scientific_workflow_v02 import flow, literal, number, symbol, binary


def rank_flow():
    return flow([{"node_id": "n", "operation": "matrix_rank", "inputs": {"matrix": literal([[1]])}}],
                [{"node_id": "n", "port": "rank"}])


def test_cancellation_inside_verification_never_marks_node_completed(isolated_account_store, monkeypatch):
    original = service._verify_result
    cancel = Event()

    def verifying(*args, **kwargs):
        cancel.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_verify_result", verifying)
    result = service.run_scientific_workflow(rank_flow(), parent_cancel_check=cancel.is_set)
    assert result["status"] == "cancelled"
    assert result["completed_node_count"] == 0
    assert result["node_receipts"][0]["verification"] == "cancelled"
    assert result["outputs"] == {}


def test_source_resolution_receives_parent_cancellation_before_worker(isolated_account_store, monkeypatch):
    from app.api.scientificforge_source_service import ScientificSourceError
    cancel = Event()
    calls = []

    def resolving(file_id, *, cancel_check):
        cancel.set()
        assert cancel_check()
        raise ScientificSourceError("source_verification_cancelled")

    monkeypatch.setattr(service, "resolve_owned_attached_scientific_source", resolving)
    monkeypatch.setattr(service, "run_scientific_worker_process", lambda *a, **k: calls.append(a))
    request = flow([{"node_id": "n", "operation": "descriptive_stats", "columns": ["value"],
                     "inputs": {"values": {"kind": "source", "source_id": "s"}}}],
                   [{"node_id": "n", "port": "summary"}], sources=[{"source_id": "s", "file_id": "file_0123456789abcdef"}])
    result = service.run_scientific_workflow(request, allowed_file_ids={"file_0123456789abcdef"}, parent_cancel_check=cancel.is_set)
    assert result["status"] == "cancelled"
    assert result["attempted_node_count"] == 0
    assert not calls


@pytest.mark.parametrize("cancelled", [False, True])
def test_worker_terminal_failure_cannot_publish_success(isolated_account_store, monkeypatch, cancelled):
    monkeypatch.setattr(service, "run_scientific_worker_process", lambda *a, **k:
        {"status": "cancelled" if cancelled else "failed", "blocked_reason": "operator_cancelled" if cancelled else "worker_timeout"})
    result = service.run_scientific_workflow(rank_flow())
    assert result["status"] == ("cancelled" if cancelled else "failed")
    assert result["node_receipts"][0]["reason"] == ("scientific_request_cancelled" if cancelled else "worker_timeout")
    assert result["completed_node_count"] == 0
    assert result["outputs"] == {}


def test_resource_cutoff_survives_node_and_parent_projection(isolated_account_store, monkeypatch):
    guard = {"reason": "cpu_thermal_cutoff", "peaks": {"cpu_c": 91},
             "hard_cpu_percentage_enforced": False}
    monkeypatch.setattr(service, "run_scientific_worker_process", lambda *a, **k:
                        {"status": "failed", "blocked_reason": "worker_resource_limited", "resource_guard": guard})
    request = flow([{"node_id": "rank", "operation": "matrix_rank", "inputs": {
        "matrix": literal([[1, 0], [0, 1]])}}], [{"node_id": "rank", "port": "rank"}])
    result = service.run_scientific_workflow(request)
    assert result["status"] == "failed" and result["reason"] == "worker_resource_limited"
    assert result["completed_node_count"] == 0 and result["outputs"] == {}
    assert result["node_receipts"][0]["resource_guard"] == guard
    assert result["node_receipts"][0]["verification"] == "not_run"


def test_forged_zero_residual_does_not_verify_wrong_linear_solution(isolated_account_store, monkeypatch):
    actual_worker = service.run_scientific_worker_process

    def corrupt(*args, **kwargs):
        result = actual_worker(*args, **kwargs)
        assert result["status"] == "completed"
        result["result"]["solution"] = [900, 900]
        result["diagnostics"]["residual"] = 0
        return result

    monkeypatch.setattr(service, "run_scientific_worker_process", corrupt)
    request = flow([{"node_id": "n", "operation": "solve_linear_system", "inputs": {
        "matrix": literal([[2, 1], [1, 3]]), "rhs": literal([5, 7])}}], [{"node_id": "n", "port": "solution"}])
    result = service.run_scientific_workflow(request)
    assert result["status"] == "failed"
    assert result["reason"] == "linear_residual_too_large"
    assert result["completed_node_count"] == 0


def test_regression_quadrature_optimization_and_endpoint_diagnostics(isolated_account_store):
    request = flow([
        {"node_id": "fit", "operation": "linear_regression", "inputs": {
            "matrix": literal([[1, 0], [1, 1], [1, 2]]), "rhs": literal([1, 3, 5])}},
        {"node_id": "area", "operation": "numerical_integral", "expression": symbol("x"), "variable": "x", "bounds": [0, 1]},
        {"node_id": "minimum", "operation": "minimize_scalar", "expression": binary("power", symbol("x"), number(2)), "variable": "x", "bounds": [-1, 1]},
        {"node_id": "endpoint", "operation": "find_root", "expression": symbol("x"), "variable": "x", "bounds": [0, 1]},
    ], [{"node_id": "fit", "port": "coefficients"}, {"node_id": "area", "port": "value"},
        {"node_id": "minimum", "port": "minimum"}, {"node_id": "endpoint", "port": "root"}], symbols=[{"name": "x", "role": "variable"}])
    result = service.run_scientific_workflow(request)
    assert result["status"] == "completed", result
    assert result["outputs"]["fit.coefficients"] == pytest.approx([1, 2])
    assert result["outputs"]["area.value"] == pytest.approx(0.5)
    assert result["outputs"]["minimum.minimum"] == pytest.approx(0, abs=1e-7)
    assert result["node_receipts"][-1]["diagnostics"]["iterations"] == 0
    for row in result["node_receipts"]:
        assert row["resource_controls"]["hard_cpu_percentage_enforced"] is False
        assert row["resource_controls"]["native_threads"] == 1
        assert row["engine_versions"]
        assert row["diagnostics"]["tolerances"]


def test_unit_metadata_cannot_be_discarded_across_workflow_edges(isolated_account_store):
    request = flow([
        {"node_id": "convert", "operation": "unit_convert", "inputs": {"value": literal(2)},
         "unit": "meter", "target_unit": "centimeter"},
        {"node_id": "again", "operation": "unit_convert", "inputs": {
            "value": {"kind": "node", "node_id": "convert", "port": "value"}},
         "unit": "centimeter", "target_unit": "meter"},
        {"node_id": "independent", "operation": "matrix_rank", "inputs": {"matrix": literal([[1]])}},
    ], [{"node_id": "again", "port": "value", "unit": "meter"}],
       symbols=[{"name": "unrelated_distance", "role": "variable", "unit": "meter"}])
    result = service.run_scientific_workflow(request)
    assert result["status"] == "completed", result
    assert result["outputs"]["again.value"] == 2
    request["nodes"][1]["unit"] = "second"
    refused = service.run_scientific_workflow(request)
    assert refused["reason"] == "dimension_mismatch"
    assert refused["attempted_node_count"] == 0
    request["nodes"][1]["unit"] = "centimeter"
    request["outputs"][0]["unit"] = "second"
    refused = service.run_scientific_workflow(request)
    assert refused["reason"] == "dimension_mismatch"
    assert refused["attempted_node_count"] == 0


def test_remaining_small_symbolic_and_matrix_adapters_use_real_workers(isolated_account_store):
    expression = binary("add", binary("power", symbol("x"), number(2)), number(1))
    request = flow([
        {"node_id": "evaluate", "operation": "evaluate_expression", "expression": expression},
        {"node_id": "substitute", "operation": "substitute_expression", "expression": expression},
        {"node_id": "simplify", "operation": "simplify_expression", "expression": binary("add", symbol("x"), number(0))},
        {"node_id": "inverse", "operation": "pseudoinverse", "inputs": {"matrix": literal([[2, 0], [0, 4]])}, "verification": ["residual"]},
        {"node_id": "determinant", "operation": "determinant", "inputs": {"matrix": literal([[2, 0], [0, 4]])}},
        {"node_id": "fit", "operation": "least_squares", "inputs": {"matrix": literal([[1, 0], [1, 1], [1, 2]]), "rhs": literal([1, 3, 5])}},
        {"node_id": "residuals", "operation": "descriptive_stats", "inputs": {"values": {"kind": "node", "node_id": "fit", "port": "residuals"}}},
        {"node_id": "correlation", "operation": "correlation_matrix", "inputs": {"values": literal([[1, 2], [2, 4], [3, 6]])}},
    ], [{"node_id": "evaluate", "port": "value"}, {"node_id": "substitute", "port": "expression"},
        {"node_id": "simplify", "port": "expression"}, {"node_id": "inverse", "port": "matrix"},
        {"node_id": "determinant", "port": "value"}, {"node_id": "fit", "port": "solution"},
        {"node_id": "residuals", "port": "summary"}, {"node_id": "correlation", "port": "matrix"}],
       symbols=[{"name": "x", "role": "parameter", "value": 3, "provenance": "user"}])
    result = service.run_scientific_workflow(request)
    assert result["status"] == "completed", result
    outputs = result["outputs"]
    assert outputs["evaluate.value"] == 10
    assert outputs["substitute.expression"] == {"kind": "number", "value": 10}
    assert outputs["simplify.expression"] == {"kind": "symbol", "symbol": "x"}
    assert outputs["inverse.matrix"] == [[0.5, 0.0], [0.0, 0.25]]
    assert outputs["determinant.value"] == pytest.approx(8)
    assert outputs["fit.solution"] == pytest.approx([1, 2])
    assert outputs["residuals.summary"]["statistics"]["mean"] == pytest.approx(0, abs=1e-10)
    assert outputs["correlation.matrix"][0][1] == pytest.approx(1)
    assert result["node_receipts"][6]["upstream_result_hashes"] == [result["node_receipts"][5]["result_sha256"]]


def test_exited_group_leader_cannot_leave_computing_child(tmp_path):
    from app.api.scientificforge_process_service import _bounded_process, _minimal_environment
    # This controlled test program is not user-supplied IR. Its child holds the pipe.
    child = "import time;time.sleep(30)"
    program = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c'," + repr(child) + "]);print(p.pid,flush=True)"
    start = time.monotonic()
    _, stdout, _, failure = _bounded_process([sys.executable, "-c", program], cwd=tmp_path,
        environment=_minimal_environment(tmp_path), cancel_event=None, timeout_seconds=0.5)
    assert failure == "worker_timeout"
    assert time.monotonic() - start < 3
    child_pid = int(stdout.strip())
    for _ in range(100):
        try:
            state = Path(f"/proc/{child_pid}/stat").read_text().split()[2]
        except FileNotFoundError:
            break
        if state == "Z":
            break  # Dead, awaiting the host's parent reaper; no computation survives.
        time.sleep(0.01)
    else:
        pytest.fail("scientific child survived its group deadline")


def test_all_five_v01_operations_use_original_authenticated_service(isolated_project_store, tmp_path, monkeypatch):
    from app.api import scientificforge_service, file_ingest_service, scientificforge_source_service, project_service
    monkeypatch.setattr(file_ingest_service, "DEFAULT_INGEST_ROOT", isolated_project_store.elysia_paths.ingest_dir)
    monkeypatch.setattr(scientificforge_source_service, "DEFAULT_INGEST_ROOT", isolated_project_store.elysia_paths.ingest_dir)
    source = tmp_path / "observations.csv"
    source.write_text("x,y\n1,2\n2,4\n3,6\n")
    project_id = project_service.create_project(name="Legacy scientific preservation")["project_id"]
    attached = file_ingest_service.attach_file(source, project_id=project_id)
    assert attached.ready
    cases = [
        {"operation": "descriptive_stats", "values": [1, 2, 3]},
        {"operation": "correlation_matrix", "source_file_id": attached.file_id, "columns": ["x", "y"]},
        {"operation": "bootstrap_mean_ci", "values": [1, 2, 3], "seed": 7, "bootstrap_samples": 100},
        {"operation": "matrix_multiply", "matrix_a": [[2]], "matrix_b": [[3]]},
        {"operation": "monte_carlo_normal", "seed": 7, "monte_carlo_samples": 100},
    ]
    results = []
    for payload in cases:
        result = scientificforge_service.run_scientific_execution(payload)
        assert result.ok, (payload["operation"], result.errors)
        assert result.status == "completed"
        assert result.compute_governed
        assert result.provenance.network_access_used is False
        results.append(result.result)
    assert results[0]["statistics"]["mean"] == 2
    assert results[1]["matrix"][0][1] == pytest.approx(1)
    assert results[3]["matrix"] == [[6.0]]
    assert scientificforge_service.run_scientific_execution(cases[-1]).result == results[-1]
