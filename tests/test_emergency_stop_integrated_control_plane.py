from __future__ import annotations

from hashlib import sha256
from threading import Event, Thread
from time import monotonic, sleep

from app.api import (
    coding_operation_service,
    coding_process_service,
    project_capability_service,
    research_service,
)
from app.api.coding_operation_service import (
    approve_operation,
    consume_operation_approval,
)
from app.api.schemas.coding_operations import (
    CodingOperationApproveRequest,
)
from app.cognition import emergency_control
from app.cognition.compute_governor import (
    ComputeLedger,
    WorkloadDescriptor,
    decide_compute,
)
from app.memory import encryption_service
from sandbox.searxng_worker.contract import (
    SearxngWorkerResult,
    SearxngWorkerStatus,
)
from tests.test_codev_command_lifecycle import (
    request as command_request,
    wait_until,
)
from tests.test_part2d_cognition_governance import (
    make_store,
)


def test_one_central_stop_quenches_active_and_pending_authority(
    tmp_path,
    monkeypatch,
):
    store = make_store(
        tmp_path,
        monkeypatch,
    )
    paths = store.elysia_paths

    actor = {
        "user_id": "owner-integrated-stop",
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

    # Isolate this STOP proof from unrelated process-global test state.
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

    monkeypatch.setattr(
        encryption_service.MemoryEncryptionService,
        "relock_all",
        staticmethod(lambda: 0),
    )

    # ------------------------------------------------------------
    # Active sustained level-5 goal.
    # ------------------------------------------------------------

    goal_root = (
        paths.state_dir
        / "integrated-project-capabilities"
    )

    monkeypatch.setattr(
        project_capability_service,
        "_store_root",
        lambda: goal_root,
    )
    monkeypatch.setattr(
        project_capability_service,
        "_owner",
        lambda: "owner-integrated-stop",
    )
    monkeypatch.setattr(
        project_capability_service.project_service,
        "get_project_metadata",
        lambda project_id: {
            "project_id": project_id,
            "owner_user_id": (
                "owner-integrated-stop"
            ),
        },
    )
    monkeypatch.setattr(
        project_capability_service.project_service,
        "update_project_metadata",
        lambda *_args, **_kwargs: None,
    )

    goal = (
        project_capability_service
        .create_goal(
            "project-integrated-stop",
            project_capability_service.GoalCreateRequest(
                goal="Synthetic sustained stop proof",
                exact_scope=(
                    "Remain inside this synthetic test."
                ),
                steps=["Wait for emergency stop"],
                budget_steps=1,
                budget_minutes=5,
                max_tool_calls=1,
                max_network_requests=1,
            ),
            autonomy_level=5,
        )["goal"]
    )

    goal = (
        project_capability_service
        .transition_goal(
            "project-integrated-stop",
            goal["goal_id"],
            project_capability_service
            .GoalTransitionRequest(
                action="start"
            ),
        )["goal"]
    )

    assert goal["status"] == "active"
    assert goal["autonomy_level"] == 5

    # ------------------------------------------------------------
    # Active compute lease + active compute job.
    # ------------------------------------------------------------

    ledger = ComputeLedger(paths)

    workload = WorkloadDescriptor(
        workload_id="workload-integrated-stop",
        owner_user_id="owner-integrated-stop",
        task_kind="scientific_stop_probe",
        priority="normal",
        estimated_cpu_percent=10,
        estimated_gpu_percent=10,
        estimated_ram_mb=256,
        estimated_vram_mb=512,
        incremental_vram_mb=512,
        estimated_duration_ms=60_000,
        cancellable=True,
        preemptible=True,
    )

    lease_id, _reasons = ledger.acquire(
        workload,
        available_vram_mb=4096,
    )

    assert lease_id is not None

    reservation_id = ledger.reserve_job(
        workload
    )

    assert ledger.active_leases()
    assert ledger.active_jobs()

    # ------------------------------------------------------------
    # One unused exact approval that MUST die with STOP.
    # ------------------------------------------------------------

    unused_approval = approve_operation(
        CodingOperationApproveRequest(
            operation_kind="command_run",
            operation_summary=(
                "Synthetic unused authority for STOP proof"
            ),
            workspace_root=str(tmp_path),
            exact_files=[],
            plan_hash=sha256(
                b"unused-stop-authority"
            ).hexdigest()[:32],
            allowed_mutation_class="command_check",
            operator_approved=True,
            approval_phrase=(
                "Approve synthetic stop proof"
            ),
            rollback_note=(
                "No mutation; synthetic approval only."
            ),
        )
    )

    assert unused_approval.status == "approved"
    assert unused_approval.approval_token

    # ------------------------------------------------------------
    # Real child process. This is not a mocked process kill.
    # ------------------------------------------------------------

    command_payload = command_request(
        tmp_path,
        monkeypatch,
        "import time; time.sleep(20)",
        timeout=20,
    )

    started_command = (
        coding_process_service
        .start_approved_command(
            command_payload
        )
    )

    wait_until(
        lambda: (
            coding_process_service
            .get_command_status(
                started_command.run_id
            )
            .status
            == "running"
        )
    )

    # ------------------------------------------------------------
    # Active research operation waiting on its governed worker.
    # The lower-level socket closure is separately proven by the
    # transport regression. Here we prove the whole STOP chain.
    # ------------------------------------------------------------

    monkeypatch.setattr(
        research_service,
        "internet_master_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        research_service,
        "_authenticated_owner",
        lambda: None,
    )

    research_worker_entered = Event()
    research_observed = {
        "cancelled": False,
    }

    def blocking_research_worker(
        request,
        *,
        cancel_check=None,
    ):
        research_worker_entered.set()

        deadline = monotonic() + 5

        while monotonic() < deadline:
            if (
                cancel_check is not None
                and cancel_check()
            ):
                research_observed[
                    "cancelled"
                ] = True
                break

            sleep(0.01)

        return SearxngWorkerResult(
            status=SearxngWorkerStatus.FAILED,
            worker_used=True,
            searxng_used=True,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            queries_requested=list(
                request.queries
            ),
            queries_sent=[],
            query_outcomes=[
                {
                    "query": request.queries[0],
                    "state": (
                        "cancelled"
                        if research_observed[
                            "cancelled"
                        ]
                        else "failed"
                    ),
                    "outward_boundary_state": (
                        "unknown"
                    ),
                    "network_access_used": True,
                    "searxng_used": True,
                }
            ],
            network_access_used=True,
            errors=[
                (
                    "Synthetic research cancelled "
                    "by central STOP."
                    if research_observed[
                        "cancelled"
                    ]
                    else
                    "Synthetic research failed to "
                    "observe STOP."
                )
            ],
        )

    monkeypatch.setattr(
        research_service,
        "run_searxng_worker",
        blocking_research_worker,
    )

    request_event = (
        emergency_control
        .request_cancel_event(
            "request-integrated-web"
        )
    )

    research_result: dict[str, object] = {}

    def run_research() -> None:
        try:
            research_result["value"] = (
                research_service
                .WebResearchPort()
                .investigate(
                    question=(
                        "Research wetland nitrate "
                        "removal evidence."
                    ),
                    request_id=(
                        "request-integrated-web"
                    ),
                    conversation_id=None,
                    project_id=None,
                    reasoning_gear="standard",
                    autonomy_level=5,
                    cancel_check=(
                        request_event.is_set
                    ),
                )
            )
        except BaseException as exc:
            research_result[
                "error"
            ] = exc

    research_thread = Thread(
        target=run_research,
        name="integrated-stop-research",
        daemon=True,
    )
    research_thread.start()

    assert research_worker_entered.wait(
        2
    )

    # ------------------------------------------------------------
    # ONE CENTRAL STOP.
    # ------------------------------------------------------------

    stop_state = (
        emergency_control
        .activate_emergency_stop(
            reason=(
                "Synthetic integrated operator stop"
            ),
            paths=paths,
        )
    )

    assert stop_state["active"] is True
    assert (
        stop_state[
            "runtime_autonomy_override"
        ]
        == 1
    )

    cleanup = stop_state["cleanup"]

    assert cleanup["coding_commands"] >= 1
    assert (
        cleanup[
            "operation_approvals_revoked"
        ]
        >= 1
    )
    assert cleanup["gpu_leases_cancelled"] >= 1
    assert cleanup["sustained_goals"] >= 1
    assert (
        cleanup[
            "active_requests_signalled"
        ]
        >= 1
    )

    # ------------------------------------------------------------
    # Real process must reach an actual terminal cancellation.
    # ------------------------------------------------------------

    command_result = wait_until(
        lambda: (
            coding_process_service
            .get_command_result(
                started_command.run_id
            )
        )
    )

    assert command_result.status == "cancelled"
    assert command_result.execution_performed
    assert command_result.exit_code is not None

    # ------------------------------------------------------------
    # Research must return and report parent-level cancellation.
    # ------------------------------------------------------------

    research_thread.join(
        timeout=3
    )

    assert research_thread.is_alive() is False
    assert "error" not in research_result
    assert research_observed["cancelled"] is True
    assert request_event.is_set() is True

    research_value = research_result["value"]

    assert isinstance(
        research_value,
        dict,
    )
    assert (
        research_value["state"]
        == "cancelled"
    )
    assert (
        research_value[
            "research_attempted"
        ]
        is True
    )

    # ------------------------------------------------------------
    # Compute authority must be cancelled durably.
    # ------------------------------------------------------------

    assert ledger.active_leases() == []
    assert ledger.active_jobs() == []

    with ledger.connect() as conn:
        lease_row = conn.execute(
            """
            SELECT state, release_reason
            FROM gpu_leases
            WHERE lease_id = ?
            """,
            (lease_id,),
        ).fetchone()

        job_row = conn.execute(
            """
            SELECT state, release_reason
            FROM compute_jobs
            WHERE reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()

    assert lease_row is not None
    assert lease_row["state"] == "cancelled"
    assert (
        lease_row["release_reason"]
        == "emergency_stop"
    )

    assert job_row is not None
    assert job_row["state"] == "cancelled"
    assert (
        job_row["release_reason"]
        == "emergency_stop"
    )

    # New compute work is rejected while STOP is active.
    blocked = decide_compute(
        WorkloadDescriptor(
            workload_id=(
                "post-stop-workload"
            ),
            owner_user_id=(
                "owner-integrated-stop"
            ),
            task_kind="post_stop_probe",
            estimated_cpu_percent=5,
            estimated_ram_mb=64,
        ),
        stop_active=(
            emergency_control
            .emergency_active(paths)
        ),
        paths=paths,
        resource_state={
            "system": {
                "cpu_percent": 0,
                "ram_available_mb": 8192,
            },
            "gpu": {
                "available": False,
                "devices": [],
            },
            "ollama_residency": [],
        },
    )

    assert blocked.decision == "rejected"
    assert (
        "emergency_stop_active"
        in blocked.reasons
    )

    # ------------------------------------------------------------
    # Level-5 sustained goal must be irreversibly stopped.
    # ------------------------------------------------------------

    workbench = (
        project_capability_service
        .get_workbench(
            "project-integrated-stop"
        )
    )

    stopped_goal = next(
        item
        for item in workbench["goals"]
        if item["goal_id"]
        == goal["goal_id"]
    )

    assert (
        stopped_goal["status"]
        == "emergency_stopped"
    )
    assert (
        stopped_goal["receipts"][-1][
            "action"
        ]
        == "system_emergency_stop"
    )

    # ------------------------------------------------------------
    # Old approval authority must be dead.
    # ------------------------------------------------------------

    consumption = consume_operation_approval(
        approval_id=(
            unused_approval.approval_id
        ),
        approval_token=(
            unused_approval.approval_token
        ),
        operation_kind="command_run",
        workspace_root=str(tmp_path),
        exact_files=[],
        source_hash=None,
        plan_hash=sha256(
            b"unused-stop-authority"
        ).hexdigest()[:32],
        allowed_mutation_class=(
            "command_check"
        ),
    )

    assert consumption.allowed is False
    assert (
        consumption.reason
        == "approval_revoked"
    )

    # ------------------------------------------------------------
    # Reset removes emergency posture but MUST NOT resurrect stale
    # pre-stop authority.
    # ------------------------------------------------------------

    reset = (
        emergency_control
        .reset_emergency_stop(
            paths
        )
    )

    assert reset["active"] is False
    assert (
        emergency_control
        .emergency_active(paths)
        is False
    )

    after_reset = consume_operation_approval(
        approval_id=(
            unused_approval.approval_id
        ),
        approval_token=(
            unused_approval.approval_token
        ),
        operation_kind="command_run",
        workspace_root=str(tmp_path),
        exact_files=[],
        source_hash=None,
        plan_hash=sha256(
            b"unused-stop-authority"
        ).hexdigest()[:32],
        allowed_mutation_class=(
            "command_check"
        ),
    )

    assert after_reset.allowed is False
    assert (
        after_reset.reason
        == "approval_revoked"
    )

    emergency_control.release_request(
        "request-integrated-web"
    )
    coding_process_service.clear_process_state_for_tests()
    coding_operation_service._APPROVALS.clear()
