from __future__ import annotations

import sys
from hashlib import sha256

from app.api import coding_process_service
from app.api.coding_operation_service import approve_operation
from app.api.schemas.coding_commands import CodingCommandRunApprovedRequest
from app.api.schemas.coding_operations import CodingOperationApproveRequest


def _approve_command(tmp_path, command_id: str, command: list[str]):
    plan_hash = sha256(("command_check\n" + command_id + "\n" + "\n".join(command)).encode("utf-8")).hexdigest()[:32]
    return approve_operation(
        CodingOperationApproveRequest(
            operation_kind="command_run",
            operation_summary="Run exact allowlisted check",
            workspace_root=str(tmp_path),
            exact_files=[],
            plan_hash=plan_hash,
            allowed_mutation_class="command_check",
            operator_approved=True,
            approval_phrase="approve exact check",
            rollback_note="No file mutation is authorized.",
        )
    )


def test_command_run_requires_operator_approval(tmp_path):
    result = coding_process_service.run_approved_command(
        CodingCommandRunApprovedRequest(
            approval_id="approval",
            approval_mode="test_with_approval",
            command_id="safe_python",
            workspace_root=str(tmp_path),
        )
    )

    assert result.status == "approval_required"
    assert result.execution_performed is False


def test_command_run_executes_exact_allowlisted_command_with_shell_false(tmp_path, monkeypatch):
    policy = {
        "execution_enabled": True,
        "allowed_commands": [
            {
                "id": "safe_python",
                "command": [sys.executable, "-c", "print('ok')"],
                "timeout_seconds": 10,
                "output_limit_bytes": 2000,
            }
        ],
    }
    monkeypatch.setattr(coding_process_service, "load_command_allowlist", lambda: policy)
    approval = _approve_command(tmp_path, "safe_python", policy["allowed_commands"][0]["command"])

    result = coding_process_service.run_approved_command(
        CodingCommandRunApprovedRequest(
            approval_id=approval.approval_id,
            approval_token=approval.approval_token,
            approval_mode="test_with_approval",
            command_id="safe_python",
            workspace_root=str(tmp_path),
            operator_approved=True,
        )
    )

    assert result.status == "completed"
    assert result.execution_performed is True
    assert result.exit_code == 0
    assert result.stdout_preview == "ok\n"


def test_command_run_blocks_outside_test_mode_even_with_operator_approval(tmp_path, monkeypatch):
    policy = {
        "execution_enabled": True,
        "allowed_commands": [
            {
                "id": "safe_python",
                "command": [sys.executable, "-c", "print('ok')"],
                "timeout_seconds": 10,
                "output_limit_bytes": 2000,
            }
        ],
    }
    monkeypatch.setattr(coding_process_service, "load_command_allowlist", lambda: policy)

    result = coding_process_service.run_approved_command(
        CodingCommandRunApprovedRequest(
            approval_id="approval",
            approval_mode="apply_with_approval",
            command_id="safe_python",
            workspace_root=str(tmp_path),
            operator_approved=True,
        )
    )

    assert result.status == "blocked_by_approval_mode"
    assert result.execution_performed is False


def test_command_run_does_not_launch_policy_disabled_workspace_script(tmp_path, monkeypatch):
    policy = {
        "execution_enabled": True,
        "allowed_commands": [
            {
                "id": "unsafe_workspace_script",
                "command": [sys.executable, "-c", "print('must not run')"],
                "execution_enabled": False,
                "disabled_reason": "workspace script is not isolated",
            }
        ],
    }
    monkeypatch.setattr(coding_process_service, "load_command_allowlist", lambda: policy)

    result = coding_process_service.run_approved_command(
        CodingCommandRunApprovedRequest(
            approval_id="unused-approval",
            approval_token="unused-token",
            approval_mode="test_with_approval",
            command_id="unsafe_workspace_script",
            workspace_root=str(tmp_path),
            operator_approved=True,
        )
    )

    assert result.status == "blocked_execution_disabled"
    assert result.blocked_reason == "command_disabled_by_policy"
    assert result.execution_performed is False
