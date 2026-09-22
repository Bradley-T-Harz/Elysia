from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from threading import Thread
import time

import pytest

from app.api import scientificforge_service as service
from app.api.scientificforge_source_service import (
    VerifiedScientificSource,
)
from app.api.schemas.execution import (
    ExecutionStatus,
)


class FakeLedger:
    def __init__(self):
        self.released_jobs = []
        self.released_leases = []

    def release_job(
        self,
        reservation_id,
        *,
        reason,
    ):
        self.released_jobs.append(
            (
                reservation_id,
                reason,
            )
        )
        return True

    def release(
        self,
        lease_id,
        *,
        reason,
        actual_vram_mb=None,
    ):
        self.released_leases.append(
            (
                lease_id,
                reason,
            )
        )
        return True


def _controls():
    return SimpleNamespace(
        cpu_percent_ceiling=90,
        ram_mb_ceiling=16_384,
        vram_mb_ceiling=12_288,
        max_background_jobs=2,
    )


def _decision(
    *,
    state="cpu",
    device="cpu",
    reservation="job-test",
):
    return SimpleNamespace(
        decision=state,
        selected_device=device,
        reservation_id=reservation,
        lease_id=None,
        reasons=(
            "policy_before_optimization",
            "cpu_earned",
        ),
    )


def _governance(
    monkeypatch,
    ledger,
    *,
    decision=None,
):
    monkeypatch.setattr(
        service,
        "current_user_id",
        lambda: "user-test",
    )

    monkeypatch.setattr(
        service,
        "current_user_controls",
        _controls,
    )

    monkeypatch.setattr(
        service,
        "emergency_active",
        lambda: False,
    )

    monkeypatch.setattr(
        service,
        "decide_compute",
        lambda *args, **kwargs: (
            decision
            or _decision()
        ),
    )

    monkeypatch.setattr(
        service,
        "ComputeLedger",
        lambda: ledger,
    )


def test_matrix_execution_runs_through_compute_governance(
    monkeypatch,
):
    ledger = FakeLedger()

    _governance(
        monkeypatch,
        ledger,
    )

    result = service.run_scientific_execution(
        {
            "operation": "matrix_multiply",
            "matrix_a": [
                [1, 2],
                [3, 4],
            ],
            "matrix_b": [
                [5, 6],
                [7, 8],
            ],
        }
    )

    assert result.ok is True

    assert (
        result.status
        == ExecutionStatus.COMPLETED
    )

    assert result.compute_device == "cpu"
    assert result.compute_governed is True

    assert result.result["matrix"] == [
        [19.0, 22.0],
        [43.0, 50.0],
    ]

    assert result.provenance is not None
    assert result.provenance.deterministic is True
    assert result.provenance.network_access_used is False
    assert result.provenance.source_mutated is False

    assert ledger.released_jobs == [
        (
            "job-test",
            "scientificforge_finished",
        )
    ]


def test_same_monte_carlo_request_has_same_scientific_hashes(
    monkeypatch,
):
    ledger = FakeLedger()

    _governance(
        monkeypatch,
        ledger,
    )

    payload = {
        "operation": "monte_carlo_normal",
        "seed": 3407,
        "monte_carlo_samples": 3000,
        "distribution_mean": 10.0,
        "distribution_stddev": 2.0,
    }

    first = service.run_scientific_execution(
        payload
    )

    second = service.run_scientific_execution(
        payload
    )

    assert first.ok is True
    assert second.ok is True

    assert first.result == second.result

    assert (
        first.provenance.parameter_sha256
        == second.provenance.parameter_sha256
    )

    assert (
        first.provenance.result_sha256
        == second.provenance.result_sha256
    )


def test_compute_rejection_prevents_worker_execution(
    monkeypatch,
):
    ledger = FakeLedger()

    _governance(
        monkeypatch,
        ledger,
        decision=_decision(
            state="rejected",
            device="none",
            reservation=None,
        ),
    )

    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "worker must not run"
        )

    monkeypatch.setattr(
        service,
        "run_scientific_worker_process",
        forbidden,
    )

    result = service.run_scientific_execution(
        {
            "operation": "descriptive_stats",
            "values": [1, 2, 3],
        }
    )

    assert called is False

    assert (
        result.status
        == ExecutionStatus.BLOCKED
    )

    assert (
        "compute_governor_declined_scientific_job"
        in result.errors
    )


def test_emergency_stop_rejects_new_work_before_compute(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "current_user_id",
        lambda: "user-test",
    )

    monkeypatch.setattr(
        service,
        "emergency_active",
        lambda: True,
    )

    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "compute must not run"
        )

    monkeypatch.setattr(
        service,
        "decide_compute",
        forbidden,
    )

    result = service.run_scientific_execution(
        {
            "operation": "descriptive_stats",
            "values": [1, 2, 3],
        }
    )

    assert called is False

    assert (
        result.status
        == ExecutionStatus.BLOCKED
    )

    assert (
        "emergency_stop_active"
        in result.errors
    )


def test_request_cancellation_reaches_running_worker(
    monkeypatch,
):
    ledger = FakeLedger()

    _governance(
        monkeypatch,
        ledger,
    )

    correlation_id = (
        "caller-correlation-id"
    )

    scientific_control_id = (
        "scientificjob-control-test"
    )

    original_new_id = service.new_id

    def controlled_new_id(prefix):
        if prefix == "scientificjob":
            return scientific_control_id
        return original_new_id(prefix)

    monkeypatch.setattr(
        service,
        "new_id",
        controlled_new_id,
    )

    def cancellable_worker(
        job,
        *,
        source=None,
        cancel_event=None,
        timeout_seconds=30.0,
    ):
        deadline = (
            time.monotonic()
            + 5
        )

        while time.monotonic() < deadline:
            if (
                cancel_event is not None
                and cancel_event.is_set()
            ):
                return {
                    "status": "cancelled",
                    "blocked_reason": "operator_cancelled",
                }

            time.sleep(
                0.01
            )

        raise AssertionError(
            "cancellation did not reach worker"
        )

    monkeypatch.setattr(
        service,
        "run_scientific_worker_process",
        cancellable_worker,
    )

    holder = {}

    def run():
        holder["result"] = (
            service.run_scientific_execution(
                {
                    "operation": "descriptive_stats",
                    "values": [1, 2, 3],
                    "request_id": correlation_id,
                }
            )
        )

    thread = Thread(
        target=run,
    )

    thread.start()

    from app.cognition.emergency_control import (
        cancel_request,
    )

    deadline = (
        time.monotonic()
        + 2
    )

    cancelled = False

    while time.monotonic() < deadline:
        # The caller-controlled correlation id must own no cancellation
        # authority.
        assert (
            cancel_request(
                correlation_id,
                "user-test",
            )
            is False
        )

        cancelled = cancel_request(
            scientific_control_id,
            "user-test",
        )

        if cancelled:
            break

        time.sleep(
            0.01
        )

    thread.join(
        timeout=5
    )

    assert cancelled is True
    assert not thread.is_alive()

    result = holder["result"]

    assert (
        result.status
        == ExecutionStatus.CANCELLED
    )

    assert result.request_id == correlation_id
    assert result.job_id == scientific_control_id

    assert ledger.released_jobs == [
        (
            "job-test",
            "scientificforge_cancelled",
        )
    ]


def test_verified_source_receipt_exposes_no_raw_path(
    monkeypatch,
    tmp_path,
):
    ledger = FakeLedger()

    _governance(
        monkeypatch,
        ledger,
    )

    source_path = (
        tmp_path / "private.csv"
    )

    source_path.write_text(
        "value\n1\n2\n3\n",
        encoding="utf-8",
    )

    raw = source_path.read_bytes()
    digest = sha256(
        raw
    ).hexdigest()

    verified = VerifiedScientificSource(
        file_id=(
            "file_"
            + digest[:16]
        ),
        display_name="private.csv",
        file_kind="csv",
        source_path=source_path,
        sha256=digest,
        size_bytes=len(raw),
    )

    monkeypatch.setattr(
        service,
        "resolve_owned_attached_scientific_source",
        lambda *args, **kwargs: verified,
    )

    result = service.run_scientific_execution(
        {
            "operation": "descriptive_stats",
            "source_file_id": verified.file_id,
            "columns": ["value"],
        }
    )

    assert result.ok is True
    assert result.source is not None

    public_source = (
        result.source.model_dump()
    )

    assert "source_path" not in public_source
    assert public_source["raw_path_exposed"] is False
    assert public_source["source_sha256"] == digest

    assert (
        str(source_path)
        not in result.model_dump_json()
    )


def test_operation_specific_authority_fails_closed(
    monkeypatch,
):
    ledger = FakeLedger()

    _governance(
        monkeypatch,
        ledger,
    )

    result = service.run_scientific_execution(
        {
            "operation": "bootstrap_mean_ci",
            "values": [1, 2, 3],
        }
    )

    assert (
        result.status
        == ExecutionStatus.BLOCKED
    )

    assert (
        "explicit_seed_required"
        in result.errors
    )



def test_caller_request_id_never_becomes_control_authority(
    monkeypatch,
):
    ledger = FakeLedger()

    _governance(
        monkeypatch,
        ledger,
    )

    bound = []
    released = []

    monkeypatch.setattr(
        service,
        "bind_request_owner",
        lambda control_id, owner: bound.append(
            (control_id, owner)
        ),
    )

    from threading import Event

    monkeypatch.setattr(
        service,
        "request_cancel_event",
        lambda control_id: Event(),
    )

    monkeypatch.setattr(
        service,
        "release_request",
        lambda control_id: released.append(
            control_id
        ),
    )

    result = service.run_scientific_execution(
        {
            "operation": "descriptive_stats",
            "values": [1, 2, 3],
            "request_id": "caller-selected-id",
        }
    )

    assert result.ok is True

    assert result.request_id == "caller-selected-id"

    assert result.job_id
    assert result.job_id != "caller-selected-id"

    assert bound == [
        (
            result.job_id,
            "user-test",
        )
    ]

    assert released == [
        result.job_id
    ]
