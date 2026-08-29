"""Governed code service for approved patch and focused command workers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from app.api.request_trace_service import update_request_trace_ledger_snapshot
from app.api.schemas.code import (
    FocusedCommandRunRequest,
    FocusedCommandRunResponseData,
    PatchApplyRequest,
    PatchApplyResponseData,
)
from app.api.schemas.common import ApprovalState
from core.repo_context_gatherer import load_approved_repos_config
from sandbox.command_worker import CommandWorkerRequest, run_command_worker
from sandbox.patch_worker import PatchFileChange, PatchWorkerRequest, run_patch_worker


APPROVED_REPOS_CONFIG_PATH = Path("config/coder/approved_repos.yaml")


def _new_request_id(prefix: str = "code") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _approved_repo(repo_key: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        config = load_approved_repos_config(APPROVED_REPOS_CONFIG_PATH)
    except Exception as exc:
        return None, f"Approved repo config could not be loaded: {exc}"
    repos = config.get("repos", {})
    if not isinstance(repos, dict):
        return None, "Approved repo config has no repo mapping."
    repo = repos.get(repo_key)
    if not isinstance(repo, dict) or repo.get("allowed") is not True:
        return None, f"Repo key is not approved: {repo_key}"
    return repo, None


def _repo_root(repo: dict[str, Any]) -> str:
    return str(Path(str(repo.get("root") or ".")).expanduser().resolve(strict=False))


def apply_approved_patch(payload: dict[str, Any] | PatchApplyRequest) -> PatchApplyResponseData:
    request = payload if isinstance(payload, PatchApplyRequest) else PatchApplyRequest(**payload)
    request_id = request.request_id or _new_request_id("patch")
    repo, repo_error = _approved_repo(request.repo_key)

    if repo_error or repo is None:
        return PatchApplyResponseData(
            request_id=request_id,
            repo_key=request.repo_key,
            patch_id=request.patch_id,
            patch_hash="",
            status="blocked",
            approval_state=ApprovalState.DENIED,
            errors=[repo_error or "Approved repo lookup failed."],
        )

    changes = [
        PatchFileChange(
            file_path=change.file_path,
            old_text=change.old_text,
            new_text=change.new_text,
        )
        for change in request.changes
    ]
    worker_request = PatchWorkerRequest(
        request_id=request_id,
        repo_key=request.repo_key,
        repo_root=_repo_root(repo),
        patch_id=request.patch_id,
        expected_patch_hash=request.expected_patch_hash,
        changes=changes,
        approved_files=list(request.approved_files),
        approval_reference=request.approval_reference,
        approved_by_user=request.approved_by_user,
        rollback_note=request.rollback_note or "",
    )
    result = run_patch_worker(worker_request)
    approval_state = ApprovalState.APPROVED if result.ok else ApprovalState.NEEDED

    update_request_trace_ledger_snapshot(
        request_id=request_id,
        tools_used=[
            {
                "tool_key": "approved_patch_worker",
                "tool_label": "Approved patch worker",
                "tool_kind": "patch_worker",
                "state": result.status.value,
                "available": True,
                "used": result.ok,
                "approval_required": True,
                "approval_state": approval_state.value,
                "locality": "local",
                "boundary_kind": "file_mutation",
                "operation": "apply_exact_patch",
                "summary": result.post_apply_summary or "Patch worker evaluated an approved patch request.",
                "input_count": len(changes),
                "output_count": len(result.files_changed),
                "mutated_files": result.mutated_files,
                "network_access_used": False,
                "private_context_sent": False,
                "shell_used": False,
                "git_mutation_used": False,
                "cloud_used": False,
                "warnings": result.warnings,
                "errors": result.errors,
            }
        ],
        patch_plan_status=result.status.value,
        patch_plan_files=result.files_changed or request.approved_files,
        patch_id=result.patch_id,
        patch_hash=result.patch_hash,
        patch_diff_preview=result.diff_preview,
        patch_preview_truncated=result.diff_preview_truncated,
        rollback_note=result.rollback_note,
        mutated_files=result.mutated_files,
        shell_used=False,
        git_mutation_used=False,
        external_worker_used=False,
    )

    return PatchApplyResponseData(
        request_id=request_id,
        repo_key=request.repo_key,
        patch_id=result.patch_id,
        patch_hash=result.patch_hash,
        status=result.status.value,
        files_changed=result.files_changed,
        files_refused=result.files_refused,
        diff_preview=result.diff_preview,
        diff_preview_truncated=result.diff_preview_truncated,
        rollback_note=result.rollback_note,
        post_apply_summary=result.post_apply_summary,
        approval_state=approval_state,
        mutated_files=result.mutated_files,
        shell_used=False,
        git_mutation_used=False,
        network_access_used=False,
        warnings=result.warnings,
        errors=result.errors,
    )


def run_approved_focused_command(
    payload: dict[str, Any] | FocusedCommandRunRequest,
) -> FocusedCommandRunResponseData:
    request = (
        payload
        if isinstance(payload, FocusedCommandRunRequest)
        else FocusedCommandRunRequest(**payload)
    )
    request_id = request.request_id or _new_request_id("cmd")
    repo, repo_error = _approved_repo(request.repo_key)
    if repo_error or repo is None:
        return FocusedCommandRunResponseData(
            request_id=request_id,
            repo_key=request.repo_key,
            command_key=request.command_key,
            status="blocked",
            approval_state=ApprovalState.DENIED,
            errors=[repo_error or "Approved repo lookup failed."],
        )

    repo_root = _repo_root(repo)
    worker_request = CommandWorkerRequest(
        request_id=request_id,
        repo_key=request.repo_key,
        cwd=repo_root,
        command_key=request.command_key,
        argv=list(request.argv),
        approval_reference=request.approval_reference,
        approved_by_user=request.approved_by_user,
        timeout_seconds=request.timeout_seconds,
    )
    result = run_command_worker(worker_request, repo_root=repo_root)
    approval_state = ApprovalState.APPROVED if result.approved_by_user else ApprovalState.NEEDED

    update_request_trace_ledger_snapshot(
        request_id=request_id,
        tools_used=[
            {
                "tool_key": "approved_command_worker",
                "tool_label": "Approved focused command worker",
                "tool_kind": "command_worker",
                "state": result.status.value,
                "available": True,
                "used": result.status.value not in {"blocked"},
                "approval_required": True,
                "approval_state": approval_state.value,
                "locality": "local",
                "boundary_kind": "host_or_sandbox",
                "operation": result.command_key,
                "summary": f"Command worker evaluated: {' '.join(result.argv)}",
                "input_count": len(result.argv),
                "output_count": 1 if result.exit_code is not None else 0,
                "mutated_files": False,
                "network_access_used": False,
                "private_context_sent": False,
                "shell_used": False,
                "git_mutation_used": False,
                "cloud_used": False,
                "warnings": result.warnings,
                "errors": result.errors,
            }
        ],
        command_key=result.command_key,
        command_argv=result.argv,
        command_exit_code=result.exit_code,
        command_duration_ms=result.duration_ms,
        command_output_preview=result.stdout_preview or result.stderr_preview,
        command_output_truncated=result.output_truncated,
        mutated_files=False,
        shell_used=False,
        git_mutation_used=False,
        external_worker_used=False,
    )

    return FocusedCommandRunResponseData(
        request_id=request_id,
        repo_key=request.repo_key,
        command_key=result.command_key,
        argv=result.argv,
        cwd_label=request.repo_key,
        status=result.status.value,
        allowlist_matched=result.allowlist_matched,
        approved_by_user=result.approved_by_user,
        approval_state=approval_state,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        stdout_preview=result.stdout_preview,
        stderr_preview=result.stderr_preview,
        output_truncated=result.output_truncated,
        timeout_seconds=result.timeout_seconds,
        shell_used=False,
        broad_shell_used=False,
        network_access_used=False,
        mutated_files=False,
        git_mutation_used=False,
        warnings=result.warnings,
        errors=result.errors,
    )


__all__ = ("apply_approved_patch", "run_approved_focused_command")
