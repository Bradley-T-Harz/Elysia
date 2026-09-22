"""Governed service boundary for bounded local ScientificForge execution."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from pydantic import ValidationError

from app.api.scientificforge_process_service import (
    run_scientific_worker_process,
)
from app.api.scientificforge_source_service import (
    ScientificSourceError,
    VerifiedScientificSource,
    resolve_owned_attached_scientific_source,
)
from app.api.schemas.execution import (
    ExecutionStatus,
)
from app.api.schemas.scientificforge import (
    ScientificExecutionRequest,
    ScientificExecutionResult,
    ScientificProvenance,
    ScientificSourceReceipt,
)
from app.api.user_control_service import (
    current_user_controls,
)
from app.cognition.compute_governor import (
    ComputeLedger,
    WorkloadDescriptor,
    decide_compute,
)
from app.cognition.emergency_control import (
    bind_request_owner,
    emergency_active,
    release_request,
    request_cancel_event,
)
from app.ids import new_id
from app.ownership import current_user_id


def _canonical_hash(
    payload: Any,
) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

    return sha256(raw).hexdigest()


def _request_parameters(
    request: ScientificExecutionRequest,
) -> dict[str, Any]:
    payload = request.model_dump(
        mode="json"
    )

    payload.pop(
        "request_id",
        None,
    )

    payload.pop(
        "source_file_id",
        None,
    )

    return payload


def _worker_job(
    request: ScientificExecutionRequest,
) -> dict[str, Any]:
    payload = _request_parameters(
        request
    )

    return payload


def _workload_estimate(
    request: ScientificExecutionRequest,
) -> tuple[int, int, int]:
    operation = str(
        getattr(
            request.operation,
            "value",
            request.operation,
        )
    )

    from core.scientific_registry import operation_spec
    spec = operation_spec(operation)
    return spec.estimate if spec is not None else (25, 1_024, 10_000)


def _source_receipt(
    source: VerifiedScientificSource,
) -> ScientificSourceReceipt:
    return ScientificSourceReceipt(
        source_file_id=source.file_id,
        source_file_name=source.display_name,
        source_file_kind=source.file_kind,
        source_sha256=source.sha256,
        size_bytes=source.size_bytes,
    )


def _result(
    *,
    request: ScientificExecutionRequest,
    job_id: str,
    status: ExecutionStatus,
    source: VerifiedScientificSource | None = None,
    compute_device: str = "cpu",
    compute_governed: bool = False,
    payload: dict[str, Any] | None = None,
    provenance: ScientificProvenance | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> ScientificExecutionResult:
    operation = str(
        getattr(
            request.operation,
            "value",
            request.operation,
        )
    )

    return ScientificExecutionResult(
        ok=(
            status
            == ExecutionStatus.COMPLETED
        ),
        status=status,
        operation=operation,
        request_id=request.request_id,
        job_id=job_id,
        source=(
            _source_receipt(source)
            if source is not None
            else None
        ),
        seed_used=(
            request.seed
            if status
            == ExecutionStatus.COMPLETED
            else None
        ),
        compute_device=compute_device,
        compute_governed=compute_governed,
        result=dict(
            payload or {}
        ),
        provenance=provenance,
        warnings=list(
            warnings or []
        ),
        errors=list(
            errors or []
        ),
    )


def _validate_request_authority(
    request: ScientificExecutionRequest,
) -> str | None:
    operation = str(
        getattr(
            request.operation,
            "value",
            request.operation,
        )
    )

    has_source = bool(
        request.source_file_id
    )

    has_values = bool(
        request.values
    )

    if operation == "descriptive_stats":
        if has_source == has_values:
            return (
                "descriptive_stats_requires_exactly_one_of_"
                "source_file_id_or_values"
            )

        if (
            has_source
            and len(request.columns) != 1
        ):
            return (
                "descriptive_stats_source_requires_one_column"
            )

    elif operation == "correlation_matrix":
        if (
            not has_source
            or has_values
            or not 2 <= len(
                request.columns
            ) <= 16
        ):
            return (
                "correlation_matrix_requires_source_and_"
                "2_to_16_columns"
            )

    elif operation == "bootstrap_mean_ci":
        if has_source == has_values:
            return (
                "bootstrap_requires_exactly_one_of_"
                "source_file_id_or_values"
            )

        if (
            has_source
            and len(request.columns) != 1
        ):
            return (
                "bootstrap_source_requires_one_column"
            )

        if request.seed is None:
            return "explicit_seed_required"

    elif operation == "matrix_multiply":
        if (
            has_source
            or has_values
            or request.columns
        ):
            return (
                "matrix_multiply_accepts_inline_matrices_only"
            )

        if (
            not request.matrix_a
            or not request.matrix_b
        ):
            return (
                "matrix_multiply_requires_two_matrices"
            )

    elif operation == "monte_carlo_normal":
        if (
            has_source
            or has_values
            or request.columns
            or request.matrix_a
            or request.matrix_b
        ):
            return (
                "monte_carlo_normal_accepts_distribution_"
                "parameters_only"
            )

        if request.seed is None:
            return "explicit_seed_required"

    else:
        return "unsupported_scientific_operation"

    return None


def run_scientific_execution(
    request: ScientificExecutionRequest | dict[str, Any],
) -> ScientificExecutionResult:
    """Run one fixed, local, governed ScientificForge job."""

    try:
        request_model = (
            request
            if isinstance(
                request,
                ScientificExecutionRequest,
            )
            else ScientificExecutionRequest(
                **dict(request)
            )
        )

    except (
        ValidationError,
        TypeError,
        ValueError,
    ) as exc:
        fallback = ScientificExecutionRequest(
            operation="descriptive_stats",
            values=[0.0],
        )

        return _result(
            request=fallback,
            job_id=new_id(
                "scientificjob"
            ),
            status=ExecutionStatus.FAILED,
            errors=[
                "scientific_request_validation_failed:"
                + type(exc).__name__
            ],
        )

    job_id = new_id(
        "scientificjob"
    )

    authority_error = (
        _validate_request_authority(
            request_model
        )
    )

    if authority_error:
        return _result(
            request=request_model,
            job_id=job_id,
            status=ExecutionStatus.BLOCKED,
            errors=[
                authority_error
            ],
        )

    owner = current_user_id()

    if not owner:
        return _result(
            request=request_model,
            job_id=job_id,
            status=ExecutionStatus.BLOCKED,
            errors=[
                "authenticated_local_owner_required"
            ],
        )

    if emergency_active():
        return _result(
            request=request_model,
            job_id=job_id,
            status=ExecutionStatus.BLOCKED,
            errors=[
                "emergency_stop_active"
            ],
        )

    # Caller request_id is correlation metadata only. Never let caller input
    # select, replace, or collide with a global cancellation authority key.
    control_id = job_id

    bind_request_owner(
        control_id,
        owner,
    )

    cancel_event = request_cancel_event(
        control_id
    )

    source: VerifiedScientificSource | None = None
    decision = None
    ledger: ComputeLedger | None = None
    release_reason = "scientificforge_finished"

    try:
        if cancel_event.is_set():
            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.CANCELLED,
                errors=[
                    "scientific_execution_cancelled"
                ],
            )

        if request_model.source_file_id:
            try:
                source = (
                    resolve_owned_attached_scientific_source(
                        request_model.source_file_id,
                        cancel_check=cancel_event.is_set,
                    )
                )

            except ScientificSourceError as exc:
                reason = str(exc)

                if reason == (
                    "source_verification_cancelled"
                ):
                    return _result(
                        request=request_model,
                        job_id=job_id,
                        status=ExecutionStatus.CANCELLED,
                        errors=[reason],
                    )

                return _result(
                    request=request_model,
                    job_id=job_id,
                    status=ExecutionStatus.BLOCKED,
                    errors=[reason],
                )

        if cancel_event.is_set():
            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.CANCELLED,
                source=source,
                errors=[
                    "scientific_execution_cancelled"
                ],
            )

        try:
            controls = current_user_controls()

        except Exception:
            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.BLOCKED,
                source=source,
                errors=[
                    "compute_governance_unavailable"
                ],
            )

        cpu_percent, ram_mb, duration_ms = (
            _workload_estimate(
                request_model
            )
        )

        workload = WorkloadDescriptor(
            workload_id=new_id(
                "scientificworkload"
            ),
            owner_user_id=owner,
            task_kind=(
                "local_scientific_compute:"
                + str(
                    getattr(
                        request_model.operation,
                        "value",
                        request_model.operation,
                    )
                )
            ),
            priority="normal",
            interactive=True,
            privacy="normal",
            estimated_cpu_percent=cpu_percent,
            estimated_gpu_percent=0,
            estimated_ram_mb=ram_mb,
            estimated_vram_mb=0,
            incremental_vram_mb=0,
            estimated_duration_ms=duration_ms,
            batchable=False,
            cancellable=True,
            preemptible=False,
            cpu_fallback_allowed=True,
            required_model=None,
            required_resources=(
                "scientificforge_cpu",
            ),
            hard_vram_limit_mb=0,
            estimate_source=(
                "scientificforge_fixed_operation_profile_v0"
            ),
        )

        decision = decide_compute(
            workload,
            # v0 is deliberately CPU-only even when the
            # account generally prefers GPU compute.
            preference="cpu",
            cpu_percent_ceiling=(
                controls.cpu_percent_ceiling
            ),
            ram_mb_ceiling=(
                controls.ram_mb_ceiling
            ),
            vram_mb_ceiling=(
                controls.vram_mb_ceiling
            ),
            max_background_jobs=(
                controls.max_background_jobs
            ),
            stop_active=emergency_active(),
        )

        if decision.decision in {
            "rejected",
            "deferred",
        }:
            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.BLOCKED,
                source=source,
                compute_device=(
                    decision.selected_device
                    or "none"
                ),
                compute_governed=True,
                errors=[
                    "compute_governor_declined_scientific_job"
                ],
                warnings=list(
                    decision.reasons
                ),
            )

        if (
            decision.selected_device
            != "cpu"
            or decision.decision
            not in {
                "cpu",
                "background",
            }
        ):
            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.BLOCKED,
                source=source,
                compute_device=(
                    decision.selected_device
                    or "none"
                ),
                compute_governed=True,
                errors=[
                    "scientificforge_v0_cpu_only"
                ],
                warnings=list(
                    decision.reasons
                ),
            )

        ledger = ComputeLedger()

        if cancel_event.is_set():
            release_reason = (
                "scientificforge_cancelled"
            )

            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.CANCELLED,
                source=source,
                compute_device="cpu",
                compute_governed=True,
                errors=[
                    "scientific_execution_cancelled"
                ],
            )

        parameters = _request_parameters(
            request_model
        )

        parameter_sha256 = _canonical_hash(
            parameters
        )

        worker_result = (
            run_scientific_worker_process(
                _worker_job(
                    request_model
                ),
                source=source,
                cancel_event=cancel_event,
            )
        )

        worker_status = str(
            worker_result.get(
                "status"
            )
            or "failed"
        )

        if worker_status == "cancelled":
            release_reason = (
                "scientificforge_cancelled"
            )

            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.CANCELLED,
                source=source,
                compute_device="cpu",
                compute_governed=True,
                errors=[
                    str(
                        worker_result.get(
                            "blocked_reason"
                        )
                        or "scientific_execution_cancelled"
                    )
                ],
            )

        if worker_status == "blocked":
            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.BLOCKED,
                source=source,
                compute_device="cpu",
                compute_governed=True,
                errors=[
                    str(
                        worker_result.get(
                            "blocked_reason"
                        )
                        or "scientific_worker_blocked"
                    )
                ],
            )

        if worker_status != "completed":
            release_reason = (
                "scientificforge_failed"
            )

            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.FAILED,
                source=source,
                compute_device="cpu",
                compute_governed=True,
                errors=[
                    str(
                        worker_result.get(
                            "blocked_reason"
                        )
                        or "scientific_worker_failed"
                    )
                ],
            )

        boundary_flags = (
            "network_access_used",
            "source_mutated",
            "arbitrary_python_used",
            "shell_used",
            "package_install_used",
        )

        if any(
            bool(
                worker_result.get(flag)
            )
            for flag in boundary_flags
        ):
            release_reason = (
                "scientificforge_boundary_violation"
            )

            return _result(
                request=request_model,
                job_id=job_id,
                status=ExecutionStatus.FAILED,
                source=source,
                compute_device="cpu",
                compute_governed=True,
                errors=[
                    "scientific_worker_boundary_violation"
                ],
            )

        result_payload = dict(
            worker_result.get(
                "result"
            )
            or {}
        )

        result_sha256 = _canonical_hash(
            result_payload
        )

        provenance = ScientificProvenance(
            operation=str(
                getattr(
                    request_model.operation,
                    "value",
                    request_model.operation,
                )
            ),
            source_sha256=(
                source.sha256
                if source is not None
                else None
            ),
            parameter_sha256=parameter_sha256,
            result_sha256=result_sha256,
            seed=worker_result.get(
                "seed_used"
            ),
            deterministic=True,
            engine_versions={
                str(key): str(value)
                for key, value in dict(
                    worker_result.get(
                        "engine_versions"
                    )
                    or {}
                ).items()
            },
        )

        return _result(
            request=request_model,
            job_id=job_id,
            status=ExecutionStatus.COMPLETED,
            source=source,
            compute_device="cpu",
            compute_governed=True,
            payload=result_payload,
            provenance=provenance,
            warnings=list(
                decision.reasons
            ),
        )

    finally:
        if (
            decision is not None
            and ledger is None
            and (
                decision.reservation_id
                or decision.lease_id
            )
        ):
            ledger = ComputeLedger()

        if (
            ledger is not None
            and decision is not None
        ):
            if decision.lease_id:
                ledger.release(
                    decision.lease_id,
                    reason=release_reason,
                )

            if decision.reservation_id:
                ledger.release_job(
                    decision.reservation_id,
                    reason=release_reason,
                )

        release_request(
            control_id
        )


__all__ = (
    "run_scientific_execution",
)
