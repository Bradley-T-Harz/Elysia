"""Exact-approved bounded command runner for the Codev Developer profile."""

from __future__ import annotations

from datetime import datetime, timezone
from contextvars import copy_context
from dataclasses import dataclass, field
import os
import selectors
import signal
from threading import Event, RLock, Thread
from hashlib import sha256
from pathlib import Path
import re
import subprocess
from time import monotonic
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from core.codev.identity import approval_actor
from app.api.coding_repo_registry import repository_revoked
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


class _ProcessInterrupted(OSError):
    pass


@dataclass
class _Run:
    actor: str
    status: CodingCommandStatus
    cancel: Event = field(default_factory=Event)
    result: CodingCommandRunResult | None = None


_RUNS: dict[str, _Run] = {}
_LOCK = RLock()
_MAX_RUNS = 128


def _reserve(run_id: str) -> _Run:
    with _LOCK:
        for key in list(_RUNS):
            if len(_RUNS) < _MAX_RUNS:
                break
            if _RUNS[key].result is not None:
                del _RUNS[key]
        if len(_RUNS) >= _MAX_RUNS:
            raise ValueError("command_capacity_reached")
        record = _Run(approval_actor(), CodingCommandStatus(run_id=run_id, status="queued"))
        _RUNS[run_id] = record
        return record


def _stop_group(process: subprocess.Popen) -> None:
    # A terminated parent may leave descendants holding pipes or running work.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def _bounded_process(command: list[str], root: Path, timeout: int, output_limit: int, record: _Run):
    if record.cancel.is_set():
        return "cancelled", None, b"", b"", False, False
    process = subprocess.Popen(command, cwd=str(root), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                               close_fds=True, env=_sanitized_env(), start_new_session=True)
    record.status = CodingCommandStatus(run_id=record.status.run_id, status="running", execution_performed=True)
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = monotonic() + timeout
    status = "completed"
    truncated = False
    cleaned = False
    try:
        with selectors.DefaultSelector() as selector:
            for pipe, key in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, key)
            while selector.get_map() or process.poll() is None:
                if record.cancel.is_set() or record.actor != approval_actor() or repository_revoked(root):
                    status = "cancelled"
                    break
                if monotonic() >= deadline:
                    status = "timeout"
                    break
                for item, _ in selector.select(timeout=0.05):
                    chunk = os.read(item.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(item.fileobj)
                        continue
                    remaining = output_limit - sum(len(value) for value in streams.values())
                    streams[item.data].extend(chunk[:max(remaining, 0)])
                    if len(chunk) > remaining:
                        truncated = True
                        status = "output_limit"
                        break
                if truncated:
                    break
        if process.poll() is None or status != "completed":
            _stop_group(process)
        else:
            # Kill any surviving process-group descendants even after parent exit.
            _stop_group(process)
        cleaned = True
        if status == "completed" and process.returncode != 0:
            status = "failed"
        return status, process.returncode, bytes(streams["stdout"]), bytes(streams["stderr"]), truncated, True
    except OSError as exc:
        raise _ProcessInterrupted("worker_io_interrupted") from exc
    finally:
        if not cleaned:
            _stop_group(process)
        process.stdout.close()
        process.stderr.close()

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


def run_approved_command(payload: CodingCommandRunApprovedRequest, *, _run_id: str | None = None) -> CodingCommandRunResult:
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

    run_id = _run_id or f"cmd_{uuid4().hex[:16]}"
    try:
        record = _RUNS[run_id] if _run_id else _reserve(run_id)
    except ValueError:
        return _base_result(payload, "blocked", blocked_reason="command_capacity_reached")
    timeout = max(1, min(int(entry.get("timeout_seconds", 120)), 300))
    output_limit = max(256, min(int(entry.get("output_limit_bytes", 20000)), 1_000_000))
    started = _utc_now_iso()
    start_clock = monotonic()
    try:
        status, exit_code, raw_out, raw_err, truncated, launched = _bounded_process(
            command, workspace.workspace_root, timeout, output_limit, record)
        stdout, out_cut = sanitize_command_output(raw_out.decode("utf-8", errors="replace"), workspace_root=workspace.workspace_root, limit=output_limit)
        stderr, err_cut = sanitize_command_output(raw_err.decode("utf-8", errors="replace"), workspace_root=workspace.workspace_root, limit=output_limit)
        duration_ms = int((monotonic() - start_clock) * 1000)
        try:
            audit_written = write_coding_audit_record("command_run", run_id, {
                "command_id": payload.command_id, "status": status, "exit_code": exit_code,
                "timeout_seconds": timeout, "output_limit_bytes": output_limit,
                "shell": False, "network": False, "approval_id": payload.approval_id,
                "workspace_root_hash": hash_path(workspace.workspace_root), "runtime_seconds": round(duration_ms / 1000, 3),
            })
        except (OSError, ValueError):
            audit_written = False
        result = _base_result(payload, status, run_id=run_id, operation_id=run_id,
            approval_id=payload.approval_id, command=command, execution_performed=launched,
            exit_code=exit_code, stdout_preview=stdout or None, stderr_preview=stderr or None,
            started_at_utc=started, finished_at_utc=_utc_now_iso(), duration_ms=duration_ms,
            output_truncated=truncated or out_cut or err_cut, output_sanitized=True, audit_written=audit_written,
            blocked_reason=status if status in {"timeout", "output_limit", "cancelled"} else None,
            warnings=["Exact allowlisted command; closed stdin, sanitized environment, bounded output and process-group cleanup."])
    except _ProcessInterrupted:
        result = _base_result(payload, "failed_execution", run_id=run_id, command=command, execution_performed=True,
            approval_id=payload.approval_id, blocked_reason="worker_io_interrupted",
            warnings=["Process cleanup completed after an I/O failure; review the operation before retrying."])
    except OSError as exc:
        audit_written = write_coding_audit_record("command_failed_to_launch", run_id, {
            "command_id": payload.command_id, "approval_id": payload.approval_id, "error_type": type(exc).__name__})
        result = _base_result(payload, "failed_to_launch", run_id=run_id, command=command,
            approval_id=payload.approval_id, blocked_reason=f"launch_error:{type(exc).__name__}", audit_written=audit_written)
    with _LOCK:
        record.result = result
        record.status = CodingCommandStatus(run_id=run_id, status=result.status, execution_performed=result.execution_performed)
    return result


def start_approved_command(payload: CodingCommandRunApprovedRequest) -> CodingCommandStatus:
    run_id = f"cmd_{uuid4().hex[:16]}"
    record = _reserve(run_id)
    context = copy_context()
    def work():
        try:
            result = context.run(run_approved_command, payload, _run_id=run_id)
            with _LOCK:
                record.result = result
                record.status = CodingCommandStatus(run_id=run_id, status=result.status, execution_performed=result.execution_performed)
        except Exception:
            with _LOCK:
                record.result = _base_result(payload, "verification_required", run_id=run_id,
                    blocked_reason="worker_interrupted", warnings=["Inspect the audit before retrying."])
                record.status = CodingCommandStatus(run_id=run_id, status="verification_required")
    Thread(target=work, name=f"codev-{run_id}", daemon=True).start()
    return CodingCommandStatus(run_id=run_id, status="queued")


def get_command_status(run_id: str) -> CodingCommandStatus:
    with _LOCK:
        record = _RUNS.get(run_id)
        return record.status if record and record.actor == approval_actor() else CodingCommandStatus(run_id=run_id)


def get_command_result(run_id: str) -> CodingCommandRunResult | None:
    with _LOCK:
        record = _RUNS.get(run_id)
        return record.result if record and record.actor == approval_actor() else None


def cancel_command(payload: CodingCommandCancelRequest) -> CodingCommandRunResult:
    with _LOCK:
        record = _RUNS.get(payload.run_id)
        if not record or record.actor != approval_actor():
            return CodingCommandRunResult(status="not_found", run_id=payload.run_id, command_id="unknown")
        if record.result:
            return record.result
        record.cancel.set()
        return CodingCommandRunResult(status="cancellation_requested", run_id=payload.run_id,
            command_id="pending", execution_performed=record.status.execution_performed,
            warnings=["Cancellation requested. Poll until the worker confirms process cleanup."])


def cancel_all_commands() -> int:
    """Signal every still-active approved command and return the count."""
    cancelled = 0

    with _LOCK:
        for record in _RUNS.values():
            if record.result is not None:
                continue

            if record.cancel.is_set():
                continue

            record.cancel.set()
            cancelled += 1

    return cancelled


def clear_process_state_for_tests() -> None:
    with _LOCK:
        for record in _RUNS.values():
            record.cancel.set()
        _RUNS.clear()


__all__ = (
    "cancel_all_commands",
    "cancel_command",
    "clear_process_state_for_tests",
    "get_command_status",
    "get_command_result",
    "run_approved_command",
    "start_approved_command",
    "sanitize_command_output",
)
