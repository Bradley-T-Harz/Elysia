"""Owner-bound, serial, governed ScientificForge workflow execution.

The model supplies mathematics only. This service owns source binding,
compute admission, cancellation, process invocation and receipt aggregation.
"""

from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import math
import time
from typing import Any, Callable

from pydantic import ValidationError

from app.api.file_ingest_service import get_file_status
from app.api.schemas.scientific_ir import Expression
from app.api.scientificforge_process_service import run_scientific_worker_process
from app.api.scientificforge_source_service import ScientificSourceError, resolve_owned_attached_scientific_source
from app.api.user_control_service import current_user_controls
from app.cognition.compute_governor import ComputeLedger, WorkloadDescriptor, decide_compute
from app.cognition.emergency_control import bind_request_owner, emergency_active, release_request, request_cancel_event
from app.ids import new_id
from app.ownership import current_user_id
from core.scientific_registry import BACKEND_MODULES, MAX_RESULT_BYTES, MAX_WORKFLOW_SECONDS, REGISTRY_VERSION, operation_spec
from core.scientific_validation import ScientificValidationError, _expression_check, validate_scientific_workflow


def _hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return sha256(data).hexdigest()


def _safe_reason(raw: Any) -> str:
    value = str(raw or "scientific_worker_failed")
    return value[:120] if value.replace("_", "").isalnum() else "scientific_worker_failed"


class _CombinedCancel:
    def __init__(self, own_event: Any, parent: Callable[[], bool] | None) -> None:
        self.own_event = own_event
        self.parent = parent

    def is_set(self) -> bool:
        return bool(self.own_event.is_set() or emergency_active() or (self.parent and self.parent()))


def _result(workflow_id: str, status: str, reason: str, receipts: list[dict[str, Any]],
            *, attempted: bool, outputs: dict[str, Any] | None = None,
            verification: str = "not_run") -> dict[str, Any]:
    completed = sum(receipt["status"] == "completed" for receipt in receipts)
    attempted = bool(attempted or any(receipt.get("worker_attempted") for receipt in receipts))
    return {
        "protocol_version": "scientific-ir-v0.2", "workflow_id": workflow_id,
        "status": status, "reason": reason, "used": attempted,
        "execution_attempted": attempted, "completed_node_count": completed,
        "attempted_node_count": sum(bool(receipt.get("worker_attempted")) for receipt in receipts),
        "partial_completion": bool(completed and status != "completed"),
        "node_receipts": receipts, "outputs": outputs or {},
        "verification": verification, "network_used": False,
        "source_mutated": False, "shell_used": False,
        "raw_absolute_path_exposed": False,
    }


def _output_shape(value: Any) -> str:
    if isinstance(value, bool): return "boolean"
    if isinstance(value, (int, float)) and math.isfinite(value): return "scalar"
    if isinstance(value, list) and value and all(isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in value): return "vector"
    if isinstance(value, list) and value and all(isinstance(row, list) and row and all(isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in row) for row in value): return "matrix"
    if isinstance(value, dict): return "expression" if value.get("kind") else "object"
    return "invalid"


def _node_inputs(node: Any, values: dict[str, dict[str, Any]], symbols: dict[str, Any],
                 sources: dict[str, Any]) -> tuple[dict[str, Any], Any | None, list[str]]:
    resolved: dict[str, Any] = {}
    source = None
    upstream: list[str] = []
    for port, item in node.inputs.items():
        if item.kind == "literal": resolved[port] = item.value
        elif item.kind == "symbol": resolved[port] = symbols[item.symbol].value
        elif item.kind == "node":
            prior = values[item.node_id]
            resolved[port] = prior["result"][item.port]
            upstream.append(prior["result_sha256"])
        else:
            chosen = sources[item.source_id]
            if source is not None and source.file_id != chosen.file_id:
                raise ScientificValidationError("multiple_sources_in_one_node_unsupported", "unsupported")
            source = chosen
            resolved[port] = []
    return resolved, source, upstream


def _verify_result(operation: str, inputs: dict[str, Any], result: dict[str, Any],
                   diagnostics: dict[str, Any], expectations: list[str], controls: Any,
                   symbols: set[str], node: Any, cancel_check: Callable[[], bool] | None = None) -> str | None:
    if cancel_check and cancel_check():
        return "scientific_request_cancelled"
    spec = operation_spec(operation)
    if spec is None or any(port not in result or _output_shape(result[port]) != shape for port, shape in spec.outputs):
        return "result_ports_invalid"
    try:
        encoded = json.dumps({"result": result, "diagnostics": diagnostics}, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return "result_not_finite_json"
    if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
        return "result_size_exceeded"
    if any(shape == "expression" for _, shape in spec.outputs):
        try:
            for port, shape in spec.outputs:
                if shape == "expression":
                    _expression_check(Expression.model_validate(result[port]), symbols)
        except (ValidationError, ScientificValidationError):
            return "symbolic_result_invalid"
    if "convergence" in expectations or operation in {"find_root", "minimize_scalar", "solve_ode_ivp"}:
        if diagnostics.get("converged") is not True:
            return "solver_convergence_not_proven"
    if operation == "solve_linear_system":
        residual = diagnostics.get("residual")
        scale = max(1.0, math.sqrt(sum(float(v)**2 for v in inputs["rhs"])))
        if not isinstance(residual, (int, float)) or not math.isfinite(residual) or residual < 0 or residual > controls.absolute_tolerance + controls.relative_tolerance * scale:
            return "linear_residual_too_large"
        solution = result["solution"]
        if len(solution) != len(inputs["matrix"][0]):
            return "linear_solution_shape_invalid"
        # Recompute from the actual returned values, independently of the worker's claim.
        residual = math.sqrt(sum((sum(a*x for a, x in zip(row, solution)) - b)**2
                                 for row, b in zip(inputs["matrix"], inputs["rhs"])))
        if residual > controls.absolute_tolerance + controls.relative_tolerance * scale:
            return "linear_residual_too_large"
    from core.scientific_linear_contract import LINEAR_PROGRAMS, linear_solution_diagnostics
    if operation in LINEAR_PROGRAMS:
        if diagnostics.get("converged") is not True:
            return "linear_program_optimality_not_reported"
        try:
            checks = linear_solution_diagnostics(inputs, result["solution"])
        except ValueError as exc:
            return str(exc)
        if checks["constraint_violation"] > controls.absolute_tolerance:
            return "linear_program_constraint_violation"
        if checks["integrality_violation"] > controls.absolute_tolerance:
            return "linear_program_integrality_violation"
        if abs(checks["objective"] - result["objective"]) > controls.absolute_tolerance + controls.relative_tolerance * abs(checks["objective"]):
            return "linear_program_objective_mismatch"
    if operation == "find_root":
        residual = diagnostics.get("residual")
        if not isinstance(residual, (int, float)) or not math.isfinite(residual) or residual < 0 or residual > max(controls.absolute_tolerance, 1e-7):
            return "root_residual_too_large"
    if operation in {"least_squares", "linear_regression"}:
        normal = diagnostics.get("normal_equation_residual")
        if not isinstance(normal, (int, float)) or not math.isfinite(normal) or normal < 0:
            return "least_squares_verification_missing"
        solution = result["coefficients" if operation == "linear_regression" else "solution"]
        matrix, rhs = inputs["matrix"], inputs["rhs"]
        if len(solution) != len(matrix[0]) or len(result["residuals"]) != len(rhs):
            return "least_squares_shape_invalid"
        residuals = [b - sum(a*x for a, x in zip(row, solution)) for row, b in zip(matrix, rhs)]
        normal = math.sqrt(sum(sum(row[j]*r for row, r in zip(matrix, residuals))**2
                               for j in range(len(solution))))
        scale = max(1.0, sum(abs(a) for row in matrix for a in row) * max(abs(b) for b in rhs))
        if normal > controls.absolute_tolerance + controls.relative_tolerance * scale:
            return "least_squares_normal_residual_too_large"
        if any(abs(actual-reported) > controls.absolute_tolerance + controls.relative_tolerance*max(1.0, abs(actual))
               for actual, reported in zip(residuals, result["residuals"])):
            return "least_squares_residual_payload_mismatch"
    if operation == "numerical_integral":
        error = diagnostics.get("error_estimate")
        if not isinstance(error, (float, int)) or error < 0 or error > max(controls.absolute_tolerance, controls.relative_tolerance*abs(result["value"])):
            return "integration_error_exceeds_tolerance"
    if operation == "minimize_scalar" and not node.bounds[0] <= result["minimum"] <= node.bounds[1]:
        return "optimization_bound_violation"
    if operation == "pseudoinverse":
        error = diagnostics.get("reconstruction_residual")
        scale = max(1.0, sum(abs(x) for row in inputs["matrix"] for x in row))
        if not isinstance(error, (float, int)) or error < 0 or error > controls.absolute_tolerance + controls.relative_tolerance*scale:
            return "pseudoinverse_reconstruction_failed"
    if operation == "solve_ode_ivp":
        times, states = result["times"], result["states"]
        names = sorted(node.initial_conditions)
        if (result.get("state_names") != names
                or len(times) != len(states) or len(times) != node.output_points
                or any(len(row) != len(node.initial_conditions) for row in states)
                or abs(times[0] - node.time_range[0]) > controls.absolute_tolerance
                or abs(times[-1] - node.time_range[1]) > controls.absolute_tolerance):
            return "ode_trajectory_invalid"
        for index, name in enumerate(names):
            if cancel_check and cancel_check():
                return "scientific_request_cancelled"
            if abs(states[0][index] - node.initial_conditions[name]) > controls.absolute_tolerance:
                return "ode_initial_state_mismatch"
    if "dimensions" in expectations and operation in {"unit_convert", "dimensional_check", "quantity_arithmetic"} and "dimensions" not in diagnostics:
        return "dimensional_verification_missing"
    if cancel_check and cancel_check():
        return "scientific_request_cancelled"
    return None


def run_scientific_workflow(
    proposed: dict[str, Any], *,
    allowed_file_ids: set[str] | frozenset[str] = frozenset(),
    original_message: str | None = None,
    project_id: str | None = None,
    request_id: str | None = None,
    parent_cancel_check: Callable[[], bool] | None = None,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    """Execute a validated workflow; request_id is correlation, not authority."""
    workflow_id = new_id("scientificflow")
    owner = current_user_id()
    if not owner:
        return _result(workflow_id, "blocked", "authenticated_local_owner_required", [], attempted=False)
    if emergency_active() or (parent_cancel_check and parent_cancel_check()):
        return _result(workflow_id, "cancelled", "scientific_request_cancelled", [], attempted=False)
    try:
        workflow = validate_scientific_workflow(proposed, allowed_file_ids=allowed_file_ids,
                                                 original_message=original_message)
    except ScientificValidationError as exc:
        return _result(workflow_id, exc.state, exc.reason, [], attempted=False)
    try:
        controls = current_user_controls()
    except Exception:
        return _result(workflow_id, "blocked", "compute_governance_unavailable", [], attempted=False)
    for node in workflow.nodes:
        spec = operation_spec(node.operation)
        if spec is None or importlib.util.find_spec(BACKEND_MODULES[spec.backend]) is None:
            return _result(workflow_id, "unsupported", "scientific_backend_unavailable", [], attempted=False)
        if spec.estimate[0] > controls.cpu_percent_ceiling or spec.estimate[1] > controls.ram_mb_ceiling:
            return _result(workflow_id, "blocked", "workflow_exceeds_user_compute_ceiling", [], attempted=False)
    control_id = workflow_id
    bind_request_owner(control_id, owner)
    cancel = _CombinedCancel(request_cancel_event(control_id), parent_cancel_check)
    started = time.monotonic()
    receipts: list[dict[str, Any]] = []
    completed_values: dict[str, dict[str, Any]] = {}
    sources: dict[str, Any] = {}
    symbols = {symbol.name: symbol for symbol in workflow.symbols}
    try:
        for selected in workflow.sources:
            if cancel.is_set():
                return _result(workflow_id, "cancelled", "scientific_request_cancelled", receipts, attempted=bool(receipts))
            try:
                source = resolve_owned_attached_scientific_source(selected.file_id, cancel_check=cancel.is_set)
                status = get_file_status(selected.file_id)
                if project_id and (status is None or status.file is None or str(status.file.source_project_id or "") != project_id):
                    raise ScientificSourceError("scientific_source_project_mismatch")
                sources[selected.source_id] = source
            except ScientificSourceError as exc:
                return _result(workflow_id, "cancelled" if cancel.is_set() else "blocked",
                               "scientific_source_cancelled" if cancel.is_set() else _safe_reason(exc), receipts,
                               attempted=bool(receipts))
        for node in workflow.nodes:
            if cancel.is_set() or time.monotonic() - started >= MAX_WORKFLOW_SECONDS or (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic):
                reason = "scientific_request_cancelled" if cancel.is_set() else "workflow_deadline_exceeded"
                return _result(workflow_id, "cancelled" if cancel.is_set() else "failed", reason, receipts,
                               attempted=bool(receipts))
            spec = operation_spec(node.operation)
            try:
                inputs, source, upstream_hashes = _node_inputs(node, completed_values, symbols, sources)
                from core.scientific_linear_contract import LINEAR_PROGRAMS, validate_linear_inputs
                if node.operation in LINEAR_PROGRAMS:
                    try:
                        validate_linear_inputs(inputs, node.operation)
                    except ValueError as exc:
                        raise ScientificValidationError(str(exc)) from exc
            except ScientificValidationError as exc:
                return _result(workflow_id, exc.state, exc.reason, receipts, attempted=bool(receipts))
            node_job_id = new_id("scientificjob")
            node_payload = node.model_dump(mode="json", exclude_none=True)
            node_payload.update(ir_version="scientific-ir-v0.2", inputs=inputs,
                                backend_family=spec.backend,
                                symbols=[symbol.model_dump(mode="json", exclude_none=True) for symbol in workflow.symbols])
            plan_hash = _hash({"registry": REGISTRY_VERSION, "node": node_payload,
                               "upstream_hashes": upstream_hashes,
                               "source_sha256": source.sha256 if source else None})
            receipt: dict[str, Any] = {
                "workflow_id": workflow_id, "node_id": node.node_id, "job_id": node_job_id,
                "operation": node.operation, "backend_family": spec.backend,
                "status": "running", "parameter_sha256": plan_hash,
                "source_sha256": source.sha256 if source else None,
                "source_file_id": source.file_id if source else None,
                "upstream_result_hashes": upstream_hashes,
                "compute_governed": False, "verification": "not_run",
            }
            receipts.append(receipt)
            workload = WorkloadDescriptor(
                workload_id=node_job_id, owner_user_id=owner,
                task_kind="local_scientific_compute:" + node.operation,
                priority="normal", interactive=True, privacy="private" if source else "normal",
                estimated_cpu_percent=spec.estimate[0], estimated_ram_mb=spec.estimate[1],
                estimated_duration_ms=spec.estimate[2], estimated_gpu_percent=0,
                estimated_vram_mb=0, hard_vram_limit_mb=0,
                required_resources=("scientificforge_cpu", spec.backend),
                estimate_source=REGISTRY_VERSION, cancellable=True, preemptible=False,
            )
            decision = decide_compute(workload, preference="cpu",
                cpu_percent_ceiling=controls.cpu_percent_ceiling,
                ram_mb_ceiling=controls.ram_mb_ceiling,
                vram_mb_ceiling=controls.vram_mb_ceiling,
                max_background_jobs=controls.max_background_jobs,
                stop_active=cancel.is_set())
            ledger = ComputeLedger()
            try:
                receipt["compute_governed"] = True
                if decision.decision not in {"cpu", "background"} or decision.selected_device != "cpu":
                    receipt.update(status="blocked", reason="compute_governor_declined_scientific_node")
                    return _result(workflow_id, "blocked", receipt["reason"], receipts, attempted=False)
                if cancel.is_set():
                    receipt.update(status="cancelled", reason="scientific_request_cancelled")
                    return _result(workflow_id, "cancelled", receipt["reason"], receipts, attempted=False)
                remaining = max(0.1, MAX_WORKFLOW_SECONDS - (time.monotonic() - started))
                if deadline_monotonic is not None:
                    remaining = min(remaining, max(0.1, deadline_monotonic - time.monotonic()))
                receipt["worker_attempted"] = True
                try:
                    worker = run_scientific_worker_process(
                        node_payload, source=source, cancel_event=cancel,
                        timeout_seconds=min(remaining, spec.estimate[2] / 1000, 30.0),
                        memory_limit_mb=spec.estimate[1],
                    )
                except Exception:
                    state = "cancelled" if cancel.is_set() else "failed"
                    receipt.update(status=state, reason=("scientific_request_cancelled" if state == "cancelled"
                                                         else "scientific_worker_process_failed"))
                    return _result(workflow_id, state, receipt["reason"], receipts, attempted=True)
                receipt["resource_guard"] = worker.get("resource_guard", {})
                status = str(worker.get("status") or "failed")
                if cancel.is_set() or status == "cancelled":
                    receipt.update(status="cancelled", reason="scientific_request_cancelled")
                    return _result(workflow_id, "cancelled", receipt["reason"], receipts, attempted=True)
                if status != "completed":
                    receipt.update(status="blocked" if status == "blocked" else "failed",
                                   reason=_safe_reason(worker.get("blocked_reason")))
                    if node.operation in LINEAR_PROGRAMS and isinstance(worker.get("diagnostics"), dict):
                        receipt["diagnostics"] = {key: value for key, value in worker["diagnostics"].items()
                            if key in {"solver_method", "termination", "converged", "iterations", "mip_nodes",
                                       "solver_tolerance", "solver_wall_limit_seconds", "native_threads", "optimality"}}
                    return _result(workflow_id, receipt["status"], receipt["reason"], receipts, attempted=True)
                if worker.get("operation") != node.operation or worker.get("exit_code") not in {None, 0} or any(worker.get(flag) is not False for flag in
                    ("network_access_used", "source_mutated", "arbitrary_python_used", "shell_used", "package_install_used")):
                    receipt.update(status="failed", reason="scientific_worker_boundary_or_identity_mismatch")
                    return _result(workflow_id, "failed", receipt["reason"], receipts, attempted=True)
                result = worker.get("result")
                diagnostics = worker.get("diagnostics")
                if not isinstance(result, dict) or not isinstance(diagnostics, dict):
                    receipt.update(status="failed", reason="scientific_worker_result_invalid")
                    return _result(workflow_id, "failed", receipt["reason"], receipts, attempted=True)
                reason = _verify_result(node.operation, inputs, result, diagnostics, node.verification,
                                        node.controls, set(symbols), node, cancel_check=cancel.is_set)
                if reason:
                    terminal = "cancelled" if reason == "scientific_request_cancelled" else "failed"
                    receipt.update(status=terminal, reason=reason, diagnostics=diagnostics, verification="cancelled" if terminal == "cancelled" else "failed")
                    return _result(workflow_id, terminal, reason, receipts, attempted=True)
                receipt.update(status="completed", result=result, result_sha256=_hash(result),
                               diagnostics=diagnostics, verification="passed",
                               engine_versions=worker.get("engine_versions", {}),
                               resource_controls=worker.get("resource_controls", {}),
                               seed=node.controls.seed, solver_method=("RK45" if node.operation == "solve_ode_ivp" else node.operation))
                completed_values[node.node_id] = receipt
                if len(json.dumps(receipts, allow_nan=False, separators=(",", ":")).encode("utf-8")) > MAX_RESULT_BYTES:
                    receipt.update(status="failed", reason="workflow_result_limit_exceeded")
                    completed_values.pop(node.node_id, None)
                    return _result(workflow_id, "failed", receipt["reason"], receipts, attempted=True)
            finally:
                if decision.lease_id:
                    ledger.release(decision.lease_id, reason="scientific_workflow_node_finished")
                if decision.reservation_id:
                    ledger.release_job(decision.reservation_id, reason="scientific_workflow_node_finished")
        if cancel.is_set():
            return _result(workflow_id, "cancelled", "scientific_request_cancelled", receipts, attempted=True)
        selected_outputs = {f"{output.node_id}.{output.port}": completed_values[output.node_id]["result"][output.port]
                            for output in workflow.outputs}
        return _result(workflow_id, "completed", "workflow_verified", receipts,
                       attempted=True, outputs=selected_outputs, verification="passed")
    finally:
        release_request(control_id)
