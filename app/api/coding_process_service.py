"""Exact-approved bounded command runner for the Codev Developer profile."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
import subprocess
from time import monotonic
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_approval_modes import approval_mode_policy, mode_required_message
from app.api.coding_command_allowlist_service import find_allowlist_match_by_id, load_command_allowlist
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_operation_service import consume_operation_approval
from app.api.schemas.coding_commands import (
    CodingCommandCancelRequest,
    CodingCommandRunApprovedRequest,
    CodingCommandRunResult,
    CodingCommandStatus,
)


_RUNS: dict[str, CodingCommandStatus] = {}
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|bearer|token|secret|password|api[_-]?key|credential)\b\s*[:=]\s*[^\s]+"
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitized_env() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/nonexistent",
        "XDG_CONFIG_HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "NO_COLOR": "1",
    }


def sanitize_command_output(text: str, *, workspace_root: Path, limit: int) -> tuple[str, bool]:
    sanitized = text.replace(str(workspace_root), "<approved-repo>")
    home = str(Path.home())
    if home and home != "/":
        sanitized = sanitized.replace(home, "<user-home>")
    sanitized = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", sanitized)
    sanitized = sanitized.replace("-----BEGIN PRIVATE KEY-----", "<private-key-redacted>")
    encoded = sanitized.encode("utf-8", errors="replace")
    truncated = len(encoded) > limit
    if truncated:
        sanitized = encoded[:limit].decode("utf-8", errors="replace") + "\n[output truncated]"
    return sanitized, truncated


def _base_result(payload: CodingCommandRunApprovedRequest, status: str, **values: object) -> CodingCommandRunResult:
    return CodingCommandRunResult(status=status, command_id=payload.command_id, **values)


def _timeout_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run_approved_command(payload: CodingCommandRunApprovedRequest) -> CodingCommandRunResult:
    mode_policy = approval_mode_policy(payload.approval_mode)
    if not mode_policy.can_run_tests:
        return _base_result(
            payload,
            "blocked_by_approval_mode",
            blocked_reason=f"{mode_policy.mode}_does_not_allow_command_execution",
            warnings=[mode_required_message("test_with_approval")],
        )
    if not payload.operator_approved:
        return _base_result(
            payload,
            "approval_required",
            blocked_reason="operator_approval_required",
            warnings=["Command execution requires explicit operator approval."],
        )
    policy = load_command_allowlist()
    if not policy.get("execution_enabled", False):
        return _base_result(payload, "blocked_execution_disabled", blocked_reason="execution_disabled_by_policy", warnings=["No process was launched."])
    entry = find_allowlist_match_by_id(payload.command_id, policy)
    if not entry:
        return _base_result(payload, "blocked", blocked_reason="command_id_not_allowlisted", warnings=["No process was launched."])
    command = [str(part) for part in entry.get("command") or []]
    if not bool(entry.get("execution_enabled", True)):
        return _base_result(
            payload,
            "blocked_execution_disabled",
            command=command,
            blocked_reason="command_disabled_by_policy",
            warnings=[
                str(entry.get("disabled_reason") or "This allowlist entry is disabled by command policy."),
                "No process was launched and the approval record was not consumed.",
            ],
        )
    workspace = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=".",
        require_existing=True,
        allow_directory=True,
    )
    if not workspace.allowed:
        return _base_result(
            payload,
            "blocked",
            command=command,
            blocked_reason=workspace.reason or "workspace_not_approved",
            warnings=["No process was launched."],
        )
    plan_hash = sha256(("command_check\n" + payload.command_id + "\n" + "\n".join(command)).encode("utf-8")).hexdigest()[:32]
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind="command_run",
        workspace_root=payload.workspace_root,
        exact_files=[],
        source_hash=None,
        plan_hash=plan_hash,
        allowed_mutation_class="command_check",
    )
    if not approval.allowed:
        return _base_result(
            payload,
            "approval_required",
            command=command,
            approval_id=payload.approval_id,
            blocked_reason=approval.reason,
            warnings=["A matching, unexpired, one-time command approval is required."],
        )

    run_id = f"cmd_{uuid4().hex[:16]}"
    timeout = int(entry.get("timeout_seconds", 120))
    output_limit = int(entry.get("output_limit_bytes", 20000))
    started = _utc_now_iso()
    start_clock = monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(workspace.workspace_root),
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
            close_fds=True,
            env=_sanitized_env(),
        )
        finished = _utc_now_iso()
        duration_ms = int((monotonic() - start_clock) * 1000)
        stdout, stdout_truncated = sanitize_command_output(completed.stdout or "", workspace_root=workspace.workspace_root, limit=output_limit)
        stderr, stderr_truncated = sanitize_command_output(completed.stderr or "", workspace_root=workspace.workspace_root, limit=output_limit)
        result_status = "completed" if completed.returncode == 0 else "failed"
        _RUNS[run_id] = CodingCommandStatus(run_id=run_id, status=result_status, execution_performed=True)
        audit_written = write_coding_audit_record(
            "command_run",
            run_id,
            {
                "command_id": payload.command_id,
                "exit_code": completed.returncode,
                "timeout_seconds": timeout,
                "output_limit_bytes": output_limit,
                "shell": False,
                "network": False,
                "approval_id": payload.approval_id,
                "workspace_root_hash": hash_path(workspace.workspace_root),
                "runtime_seconds": round(duration_ms / 1000, 3),
            },
        )
        return _base_result(
            payload,
            result_status,
            run_id=run_id,
            operation_id=run_id,
            approval_id=payload.approval_id,
            command=command,
            execution_performed=True,
            exit_code=completed.returncode,
            stdout_preview=stdout or None,
            stderr_preview=stderr or None,
            started_at_utc=started,
            finished_at_utc=finished,
            duration_ms=duration_ms,
            output_truncated=stdout_truncated or stderr_truncated,
            output_sanitized=True,
            audit_written=audit_written,
            warnings=["Approved allowlisted command ran with shell=False, stdin closed, sanitized environment, timeout, and bounded output."],
        )
    except subprocess.TimeoutExpired as exc:
        finished = _utc_now_iso()
        duration_ms = int((monotonic() - start_clock) * 1000)
        stdout, stdout_truncated = sanitize_command_output(_timeout_text(exc.stdout), workspace_root=workspace.workspace_root, limit=output_limit)
        stderr, stderr_truncated = sanitize_command_output(_timeout_text(exc.stderr), workspace_root=workspace.workspace_root, limit=output_limit)
        _RUNS[run_id] = CodingCommandStatus(run_id=run_id, status="timeout", execution_performed=True)
        audit_written = write_coding_audit_record(
            "command_timeout",
            run_id,
            {"command_id": payload.command_id, "approval_id": payload.approval_id, "timeout_seconds": timeout, "shell": False, "network": False},
        )
        return _base_result(
            payload,
            "timeout",
            run_id=run_id,
            operation_id=run_id,
            approval_id=payload.approval_id,
            command=command,
            execution_performed=True,
            blocked_reason="timeout",
            stdout_preview=stdout or None,
            stderr_preview=stderr or None,
            started_at_utc=started,
            finished_at_utc=finished,
            duration_ms=duration_ms,
            output_truncated=stdout_truncated or stderr_truncated,
            audit_written=audit_written,
            warnings=["Approved allowlisted command timed out and no continuation remains active."],
        )
    except OSError as exc:
        finished = _utc_now_iso()
        duration_ms = int((monotonic() - start_clock) * 1000)
        _RUNS[run_id] = CodingCommandStatus(run_id=run_id, status="failed_to_launch", execution_performed=False)
        audit_written = write_coding_audit_record(
            "command_failed_to_launch",
            run_id,
            {"command_id": payload.command_id, "approval_id": payload.approval_id, "error_type": type(exc).__name__, "shell": False, "network": False},
        )
        return _base_result(
            payload,
            "failed_to_launch",
            run_id=run_id,
            operation_id=run_id,
            approval_id=payload.approval_id,
            command=command,
            execution_performed=False,
            blocked_reason=f"launch_error:{type(exc).__name__}",
            started_at_utc=started,
            finished_at_utc=finished,
            duration_ms=duration_ms,
            audit_written=audit_written,
            warnings=["No package manager, Git mutation, shell, network, or arbitrary command expansion was used."],
        )


def get_command_status(run_id: str) -> CodingCommandStatus:
    return _RUNS.get(run_id) or CodingCommandStatus(run_id=run_id)


def cancel_command(payload: CodingCommandCancelRequest) -> CodingCommandRunResult:
    _RUNS[payload.run_id] = CodingCommandStatus(run_id=payload.run_id, status="cancelled_no_process")
    return CodingCommandRunResult(
        status="cancelled_no_process",
        run_id=payload.run_id,
        operation_id=payload.run_id,
        command_id="unknown",
        execution_performed=False,
        warnings=["No process was running; cancellation recorded as a local status update."],
    )


def clear_process_state_for_tests() -> None:
    _RUNS.clear()


__all__ = (
    "cancel_command",
    "clear_process_state_for_tests",
    "get_command_status",
    "run_approved_command",
    "sanitize_command_output",
)
