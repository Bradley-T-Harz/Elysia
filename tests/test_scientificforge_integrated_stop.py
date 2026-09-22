from __future__ import annotations

import sys
from threading import Event, Thread
from time import monotonic, sleep
from types import SimpleNamespace

from app.api import scientificforge_service
from app.api.scientificforge_process_service import (
    _bounded_process,
    _minimal_environment,
)
from app.api.schemas.execution import ExecutionStatus
from app.cognition import emergency_control
from app.cognition.compute_governor import (
    ComputeLedger,
    decide_compute,
)
from tests.test_part2d_cognition_governance import (
    make_store,
)


def _wait_until(
    callback,
    *,
    timeout: float = 5.0,
):
    deadline = monotonic() + timeout

    while monotonic() < deadline:
        value = callback()

        if value:
            return value

        sleep(0.01)

    raise AssertionError(
        "Timed out waiting for integrated ScientificForge state."
    )


def test_central_stop_cancels_real_scientific_process_and_compute_job(
    tmp_path,
    monkeypatch,
):
    # ------------------------------------------------------------
    # Isolated real ElysiaPaths + real ComputeLedger.
    # ------------------------------------------------------------

    store = make_store(
        tmp_path,
        monkeypatch,
    )

    paths = store.elysia_paths

    owner = "owner-scientific-stop"

    actor = {
        "user_id": owner,
        "role": "installation_owner",
    }

    monkeypatch.setattr(
        emergency_control.account_service,
        "get_active_elysia_paths",
        lambda: paths,
    )

    monkeypatch.setattr(
        emergency_control.account_service,
        "get_authenticated_governance",
        lambda: actor,
    )

    # Isolate process-global emergency state from every other test.
    monkeypatch.setattr(
        emergency_control,
        "_STOP_EVENT",
        Event(),
    )

    monkeypatch.setattr(
        emergency_control,
        "_REQUEST_EVENTS",
        {},
    )

    monkeypatch.setattr(
        emergency_control,
        "_REQUEST_OWNERS",
        {},
    )

    monkeypatch.setattr(
        emergency_control,
        "_CANCELLERS",
        {},
    )

    # No real sealed-memory state is needed for this execution proof.
    from app.memory import encryption_service

    monkeypatch.setattr(
        encryption_service.MemoryEncryptionService,
        "relock_all",
        staticmethod(lambda: 0),
    )

    # ------------------------------------------------------------
    # ScientificForge owns the request as this authenticated owner.
    # ------------------------------------------------------------

    monkeypatch.setattr(
        scientificforge_service,
        "current_user_id",
        lambda: owner,
    )

    monkeypatch.setattr(
        scientificforge_service,
        "current_user_controls",
        lambda: SimpleNamespace(
            cpu_percent_ceiling=90,
            ram_mb_ceiling=16_384,
            vram_mb_ceiling=12_288,
            max_background_jobs=2,
        ),
    )

    monkeypatch.setattr(
        scientificforge_service,
        "emergency_active",
        lambda: emergency_control.emergency_active(
            paths
        ),
    )

    # Service cancellation calls remain the real emergency-control
    # functions. Those functions observe the monkeypatched isolated
    # global state above.
    monkeypatch.setattr(
        scientificforge_service,
        "bind_request_owner",
        emergency_control.bind_request_owner,
    )

    monkeypatch.setattr(
        scientificforge_service,
        "request_cancel_event",
        emergency_control.request_cancel_event,
    )

    monkeypatch.setattr(
        scientificforge_service,
        "release_request",
        emergency_control.release_request,
    )

    # ------------------------------------------------------------
    # Force deterministic resource telemetry while retaining the
    # real decide_compute() implementation and real SQLite ledger.
    # ------------------------------------------------------------

    resource_state = {
        "system": {
            "cpu_percent": 0.0,
            "logical_cpus": 16,
            "ram_total_mb": 65_536,
            "ram_available_mb": 60_000,
            "load_1m": 0.0,
            "process_rss_mb": 100,
            "process_threads": 4,
            "process_count": 100,
            "telemetry": "synthetic_test_fixture",
        },
        "gpu": {
            "available": False,
            "devices": [],
        },
        "ollama_residency": [],
    }

    def real_decide(
        workload,
        **kwargs,
    ):
        return decide_compute(
            workload,
            paths=paths,
            resource_state=resource_state,
            **kwargs,
        )

    monkeypatch.setattr(
        scientificforge_service,
        "decide_compute",
        real_decide,
    )

    monkeypatch.setattr(
        scientificforge_service,
        "ComputeLedger",
        lambda: ComputeLedger(paths),
    )

    ledger = ComputeLedger(paths)

    # ------------------------------------------------------------
    # Replace only the scientific calculation payload with a real
    # sleeping child process. This preserves the actual ScientificForge
    # service cancellation event -> process-group kill chain.
    #
    # The fixed real ScientificForge worker is already separately proven
    # by its worker/process tests. This probe deliberately needs a process
    # that stays alive long enough for STOP to strike it.
    # ------------------------------------------------------------

    worker_entered = Event()

    def real_sleeping_worker(
        job,
        *,
        source=None,
        cancel_event=None,
        timeout_seconds=30.0,
    ):
        worker_entered.set()

        exit_code, stdout, stderr, failure = _bounded_process(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(20)",
            ],
            cwd=tmp_path,
            environment=_minimal_environment(
                tmp_path
            ),
            cancel_event=cancel_event,
            timeout_seconds=20,
        )

        if failure == "worker_cancelled":
            return {
                "status": "cancelled",
                "blocked_reason": "operator_cancelled",
                "exit_code": exit_code,
                "stdout_bytes": len(stdout),
                "stderr_bytes": len(stderr),
            }

        return {
            "status": "failed",
            "blocked_reason": (
                failure
                or "sleeping_worker_failed_to_cancel"
            ),
            "exit_code": exit_code,
        }

    monkeypatch.setattr(
        scientificforge_service,
        "run_scientific_worker_process",
        real_sleeping_worker,
    )

    # ------------------------------------------------------------
    # Start one governed ScientificForge request.
    # ------------------------------------------------------------

    result_holder = {}

    def run_science():
        try:
            result_holder["value"] = (
                scientificforge_service
                .run_scientific_execution(
                    {
                        "operation": "descriptive_stats",
                        "values": [1, 2, 3, 4],
                        "request_id": (
                            "caller-correlation-only"
                        ),
                    }
                )
            )

        except BaseException as exc:
            result_holder["error"] = exc

    thread = Thread(
        target=run_science,
        name="scientificforge-integrated-stop",
        daemon=True,
    )

    thread.start()

    assert worker_entered.wait(
        3
    )

    # ------------------------------------------------------------
    # A real ComputeLedger reservation must exist before STOP.
    # ------------------------------------------------------------

    active_jobs = _wait_until(
        lambda: ledger.active_jobs()
    )

    assert len(active_jobs) == 1

    scientific_job_row = active_jobs[0]

    assert scientific_job_row[
        "owner_user_id"
    ] == owner

    assert str(
        scientific_job_row[
            "task_kind"
        ]
    ).startswith(
        "local_scientific_compute:"
    )

    reservation_id = scientific_job_row[
        "reservation_id"
    ]

    # CPU-only ScientificForge v0 must not hold a GPU lease.
    assert ledger.active_leases() == []

    # There must also be one active cancellable request.
    assert (
        emergency_control.active_request_count()
        >= 1
    )

    # ------------------------------------------------------------
    # ONE ACTUAL CENTRAL STOP.
    # ------------------------------------------------------------

    stopped = (
        emergency_control
        .activate_emergency_stop(
            reason=(
                "Synthetic integrated ScientificForge stop"
            ),
            paths=paths,
        )
    )

    assert stopped["active"] is True

    assert (
        stopped[
            "runtime_autonomy_override"
        ]
        == 1
    )

    cleanup = stopped["cleanup"]

    assert (
        cleanup[
            "active_requests_signalled"
        ]
        >= 1
    )

    # ------------------------------------------------------------
    # The real child process must terminate and service must report
    # a cancellation, not a successful result or hanging thread.
    # ------------------------------------------------------------

    thread.join(
        timeout=5
    )

    assert thread.is_alive() is False
    assert "error" not in result_holder

    result = result_holder[
        "value"
    ]

    assert (
        result.status
        == ExecutionStatus.CANCELLED
    )

    assert result.ok is False

    assert (
        result.request_id
        == "caller-correlation-only"
    )

    assert result.job_id
    assert (
        result.job_id
        != result.request_id
    )

    assert (
        "operator_cancelled"
        in result.errors
    )

    # ScientificForge releases its request registration.
    assert (
        emergency_control.active_request_count()
        == 0
    )

    # ------------------------------------------------------------
    # Central STOP must durably cancel the compute reservation.
    # ScientificForge's finally block must NOT overwrite that durable
    # cancellation with an ordinary release state.
    # ------------------------------------------------------------

    assert ledger.active_jobs() == []

    with ledger.connect() as conn:
        row = conn.execute(
            """
            SELECT
                state,
                release_reason,
                owner_user_id,
                task_kind
            FROM compute_jobs
            WHERE reservation_id = ?
            """,
            (
                reservation_id,
            ),
        ).fetchone()

    assert row is not None

    assert row[
        "state"
    ] == "cancelled"

    assert row[
        "release_reason"
    ] == "emergency_stop"

    assert row[
        "owner_user_id"
    ] == owner

    assert str(
        row[
            "task_kind"
        ]
    ).startswith(
        "local_scientific_compute:"
    )

    # ------------------------------------------------------------
    # STOP remains authoritative over NEW ScientificForge work.
    # ------------------------------------------------------------

    denied_after_stop = (
        scientificforge_service
        .run_scientific_execution(
            {
                "operation": "descriptive_stats",
                "values": [5, 6, 7],
            }
        )
    )

    assert (
        denied_after_stop.status
        == ExecutionStatus.BLOCKED
    )

    assert (
        "emergency_stop_active"
        in denied_after_stop.errors
    )

    assert ledger.active_jobs() == []
    assert ledger.active_leases() == []
