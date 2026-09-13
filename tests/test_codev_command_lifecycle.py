from hashlib import sha256
import sys
from time import monotonic, sleep

from app.api import coding_process_service as service
from app.api.coding_operation_service import approve_operation
from app.api.schemas.coding_commands import CodingCommandRunApprovedRequest, CodingCommandCancelRequest
from app.api.schemas.coding_operations import CodingOperationApproveRequest
from core.codev.identity import bind_client


def request(tmp_path, monkeypatch, source, *, timeout=10, limit=2048):
    command = [sys.executable, "-c", source]
    monkeypatch.setattr(service, "load_command_allowlist", lambda: {
        "execution_enabled": True, "allowed_commands": [{"id": "fixture", "command": command,
            "timeout_seconds": timeout, "output_limit_bytes": limit}]})
    approval = approve_operation(CodingOperationApproveRequest(
        operation_kind="command_run", operation_summary="Fixture lifecycle check", workspace_root=str(tmp_path),
        exact_files=[], plan_hash=sha256(("command_check\nfixture\n" + "\n".join(command)).encode()).hexdigest()[:32],
        allowed_mutation_class="command_check", operator_approved=True, rollback_note="Disposable test only."))
    return CodingCommandRunApprovedRequest(approval_id=approval.approval_id, approval_token=approval.approval_token,
        approval_mode="test_with_approval", command_id="fixture", workspace_root=str(tmp_path), operator_approved=True)


def wait_until(callback):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        result = callback()
        if result:
            return result
        sleep(0.02)
    raise AssertionError("Worker did not reach expected terminal state")


def test_cancel_stops_real_process_and_is_client_bound(tmp_path, monkeypatch):
    with bind_client("native-A"):
        payload = request(tmp_path, monkeypatch, "import time; time.sleep(20)")
        started = service.start_approved_command(payload)
        wait_until(lambda: service.get_command_status(started.run_id).status == "running")
    with bind_client("website-B"):
        assert service.get_command_status(started.run_id).status == "not_found"
        assert service.cancel_command(CodingCommandCancelRequest(run_id=started.run_id)).status == "not_found"
    with bind_client("native-A"):
        assert service.cancel_command(CodingCommandCancelRequest(run_id=started.run_id)).status == "cancellation_requested"
        result = wait_until(lambda: service.get_command_result(started.run_id))
        assert result.status == "cancelled"
        assert result.execution_performed
        assert result.exit_code is not None


def test_output_flood_is_stopped_while_reading(tmp_path, monkeypatch):
    payload = request(tmp_path, monkeypatch, "import os\nwhile True: os.write(1, b'x' * 65536)", limit=1024)
    result = service.run_approved_command(payload)
    assert result.status == "output_limit"
    assert result.output_truncated
    assert len(result.stdout_preview.encode()) <= 1024
    assert result.duration_ms < 5000


def test_timeout_and_emergency_stop_have_terminal_receipts(tmp_path, monkeypatch):
    result = service.run_approved_command(request(tmp_path, monkeypatch, "import time; time.sleep(20)", timeout=1))
    assert result.status == "timeout"
    assert result.duration_ms < 5000
    started = service.start_approved_command(request(tmp_path, monkeypatch, "import time; time.sleep(20)"))
    service.cancel_all_commands()
    result = wait_until(lambda: service.get_command_result(started.run_id))
    assert result.status == "cancelled"
