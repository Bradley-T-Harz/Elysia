"""Focused approved command worker using argv and shell=False."""

from __future__ import annotations

from pathlib import Path
import subprocess
import time

from .command_guard import command_key_for_argv, validate_command_cwd
from .contract import CommandWorkerRequest, CommandWorkerResult, CommandWorkerStatus


def _preview(text: str, limit: int) -> tuple[str, bool]:
    if len(text) > limit:
        return text[:limit] + "\n...output truncated...", True
    return text, False


def _blocked(request: CommandWorkerRequest, errors: list[str]) -> CommandWorkerResult:
    return CommandWorkerResult(
        status=CommandWorkerStatus.BLOCKED,
        request_id=request.request_id,
        repo_key=request.repo_key,
        command_key=request.command_key,
        argv=list(request.argv),
        cwd=request.cwd,
        approved_by_user=request.approved_by_user,
        approval_reference=request.approval_reference,
        timeout_seconds=request.timeout_seconds,
        errors=errors,
    )


def run_command_worker(
    request: CommandWorkerRequest,
    *,
    repo_root: str | Path | None = None,
) -> CommandWorkerResult:
    """Run one exact allowlisted command after explicit approval."""
    if not request.approved_by_user or not request.approval_reference:
        return _blocked(request, ["Exact user approval is required before command execution."])

    detected_key, error = command_key_for_argv(request.argv)
    if error:
        return _blocked(request, [error])
    if request.command_key and detected_key != request.command_key:
        return _blocked(request, ["Command key does not match the approved argv allowlist."])

    root = Path(repo_root or request.cwd).expanduser().resolve(strict=False)
    cwd, cwd_error = validate_command_cwd(root, request.cwd)
    if cwd_error or cwd is None:
        return _blocked(request, [cwd_error or "Invalid command cwd."])

    timeout = max(1, min(int(request.timeout_seconds or 120), 600))
    limit = max(500, min(int(request.max_output_chars or 6000), 20_000))
    started = time.monotonic()
    try:
        completed = subprocess.run(
            request.argv,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
            close_fds=True,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, out_trunc = _preview(str(exc.stdout or ""), limit)
        stderr, err_trunc = _preview(str(exc.stderr or ""), limit)
        return CommandWorkerResult(
            status=CommandWorkerStatus.TIMEOUT,
            request_id=request.request_id,
            repo_key=request.repo_key,
            command_key=detected_key or request.command_key,
            argv=list(request.argv),
            cwd=str(cwd),
            allowlist_matched=True,
            approved_by_user=True,
            approval_reference=request.approval_reference,
            duration_ms=duration_ms,
            stdout_preview=stdout,
            stderr_preview=stderr,
            output_truncated=out_trunc or err_trunc,
            timeout_seconds=timeout,
            errors=[f"Command timed out after {timeout} seconds."],
        )
    except OSError as exc:
        return _blocked(request, [f"Command could not be started: {exc}"])

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout, out_trunc = _preview(completed.stdout or "", limit)
    stderr, err_trunc = _preview(completed.stderr or "", limit)
    return CommandWorkerResult(
        status=CommandWorkerStatus.COMPLETED if completed.returncode == 0 else CommandWorkerStatus.FAILED,
        request_id=request.request_id,
        repo_key=request.repo_key,
        command_key=detected_key or request.command_key,
        argv=list(request.argv),
        cwd=str(cwd),
        allowlist_matched=True,
        approved_by_user=True,
        approval_reference=request.approval_reference,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        stdout_preview=stdout,
        stderr_preview=stderr,
        output_truncated=out_trunc or err_trunc,
        timeout_seconds=timeout,
    )


__all__ = ("run_command_worker",)
