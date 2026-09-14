"""Coder response compatibility without the retired boolean-approval executor.

Proposal-only Conversations remains unchanged. Consequential operations use the
canonical Codev facade and the existing exact-approved /coding contracts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.api.schemas.code import (
    FocusedCommandRunRequest, FocusedCommandRunResponseData,
    PatchApplyRequest, PatchApplyResponseData,
)
from app.api.schemas.common import ApprovalState
from core.codev.service import refuse_legacy_execution

# Retained for source compatibility with callers which inspect this setting.
APPROVED_REPOS_CONFIG_PATH = Path("config/coder/approved_repos.yaml")


def apply_approved_patch(payload: dict[str, Any] | PatchApplyRequest) -> PatchApplyResponseData:
    request = payload if isinstance(payload, PatchApplyRequest) else PatchApplyRequest(**payload)
    request_id, reason = refuse_legacy_execution("patch_apply", request.request_id)
    return PatchApplyResponseData(
        request_id=request_id, repo_key=request.repo_key, patch_id=request.patch_id,
        patch_hash=request.expected_patch_hash, status="blocked",
        approval_state=ApprovalState.NEEDED, errors=[reason],
        rollback_note="No files were changed.",
    )


def run_approved_focused_command(payload: dict[str, Any] | FocusedCommandRunRequest) -> FocusedCommandRunResponseData:
    request = payload if isinstance(payload, FocusedCommandRunRequest) else FocusedCommandRunRequest(**payload)
    request_id, reason = refuse_legacy_execution("command_run", request.request_id)
    return FocusedCommandRunResponseData(
        request_id=request_id, repo_key=request.repo_key, command_key=request.command_key,
        argv=request.argv, status="blocked", approval_state=ApprovalState.NEEDED,
        errors=[reason], warnings=["No process was launched."],
    )
