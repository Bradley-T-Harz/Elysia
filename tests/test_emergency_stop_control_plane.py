from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib

from app.api import coding_operation_service
from app.cognition import emergency_control
from app.memory import encryption_service


def test_emergency_revocation_invalidates_unconsumed_operation_approval(
    monkeypatch,
    tmp_path,
):
    coding_operation_service._APPROVALS.clear()

    monkeypatch.setattr(
        coding_operation_service,
        "approval_actor",
        lambda: "owner-synthetic",
    )

    approval_id = "approval_stop_test"

    coding_operation_service._APPROVALS[approval_id] = (
        coding_operation_service._ApprovalRecord(
            approval=None,
            token="synthetic-one-time-token",
            workspace_root=tmp_path,
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(minutes=5)
            ),
            actor="owner-synthetic",
        )
    )

    revoked = (
        coding_operation_service
        .revoke_all_operation_approvals(
            "emergency_stop",
        )
    )

    assert revoked == 1

    consumption = (
        coding_operation_service
        .consume_operation_approval(
            approval_id=approval_id,
            approval_token="synthetic-one-time-token",
            operation_kind="command_run",
            workspace_root=str(tmp_path),
            exact_files=[],
            source_hash=None,
            plan_hash="synthetic-plan",
            allowed_mutation_class="command_check",
        )
    )

    assert consumption.allowed is False
    assert consumption.reason == "approval_revoked"

    # Idempotent repeat must not count the same grant twice.
    assert (
        coding_operation_service
        .revoke_all_operation_approvals(
            "emergency_stop",
        )
        == 0
    )

    coding_operation_service._APPROVALS.clear()


def test_central_emergency_path_includes_real_process_and_approval_kills(
    monkeypatch,
):
    calls: list[str] = []

    class StubModule:
        def __getattr__(self, name):
            def callback(*_args, **_kwargs):
                calls.append(name)
                return 1

            return callback

    class StubLedger:
        def __init__(self, *_args, **_kwargs):
            pass

        def cancel_all(self, reason="emergency_stop"):
            calls.append(f"compute:{reason}")
            return 1

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _name: StubModule(),
    )

    monkeypatch.setattr(
        emergency_control,
        "ComputeLedger",
        StubLedger,
    )

    monkeypatch.setattr(
        emergency_control,
        "_CANCELLERS",
        {},
    )

    monkeypatch.setattr(
        encryption_service.MemoryEncryptionService,
        "relock_all",
        staticmethod(lambda: 1),
    )

    cleanup = emergency_control._cancel_known_subsystems(
        object()
    )

    assert cleanup["coding_commands"] == 1
    assert cleanup["operation_approvals_revoked"] == 1

    assert "cancel_all_commands" in calls
    assert "revoke_all_operation_approvals" in calls
    assert "compute:emergency_stop" in calls


def test_level_five_still_cannot_bypass_approval_or_stop_law():
    from app.cognition.governor import resolve_autonomy_policy

    _domains, policy = resolve_autonomy_policy(
        5,
        {},
    )

    assert policy["bypass_approval"] is False
    assert policy["self_increase_authority"] is False
    assert policy["bypass_internet_master"] is False
    assert (
        policy[
            "mutate_external_systems_without_approval"
        ]
        is False
    )
    assert (
        policy[
            "destructive_actions_without_approval"
        ]
        is False
    )
