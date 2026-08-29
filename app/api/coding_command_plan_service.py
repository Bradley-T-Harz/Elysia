"""Preview-only command planner for Elysia Codev."""

from __future__ import annotations

from hashlib import sha256

from app.api.coding_command_allowlist_service import (
    command_has_blocked_term,
    find_allowlist_match,
    load_command_allowlist,
    normalize_command,
)
from app.api.coding_approval_modes import approval_mode_policy, mode_required_message
from app.api.coding_path_guard_service import guard_workspace_path
from app.api.coding_risk_service import command_risk_labels
from app.api.schemas.coding_commands import CodingCommandPlan, CodingCommandPlanRequest


def plan_command(payload: CodingCommandPlanRequest) -> CodingCommandPlan:
    policy = load_command_allowlist()
    mode_policy = approval_mode_policy(payload.approval_mode)
    command = normalize_command(payload.command)
    if not command:
        return CodingCommandPlan(
            status="blocked",
            command=command,
            purpose=payload.purpose,
            blocked_reason="empty_command",
            warnings=["No command execution was performed."],
        )
    blocked_term = command_has_blocked_term(command, list(policy.get("blocked_terms") or []))
    if blocked_term:
        return CodingCommandPlan(
            status="blocked",
            command=command,
            purpose=payload.purpose,
            blocked_reason=f"blocked_term:{blocked_term}",
            risk_labels=command_risk_labels(command),
            warnings=["No command execution was performed."],
        )
    workspace = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=".",
        require_existing=True,
        allow_directory=True,
    )
    if not workspace.allowed:
        return CodingCommandPlan(
            status="blocked",
            command=command,
            purpose=payload.purpose,
            blocked_reason=workspace.reason or "workspace_not_approved",
            warnings=["No command execution was performed."],
        )

    match = find_allowlist_match(command, policy)
    if not match:
        return CodingCommandPlan(
            status="not_allowlisted",
            command=command,
            purpose=payload.purpose,
            allowlist_match=False,
            execution_enabled=False,
            risk_labels=command_risk_labels(command),
            blocked_reason="command_not_allowlisted",
            warnings=["No command execution was performed."],
        )

    entry_execution_enabled = bool(match.get("execution_enabled", True))
    execution_enabled = (
        bool(policy.get("execution_enabled", False))
        and entry_execution_enabled
        and mode_policy.can_run_tests
    )
    warnings = ["No command was run by this planning endpoint."]
    if not entry_execution_enabled:
        warnings.append(
            str(match.get("disabled_reason") or "This allowlist entry is disabled by command policy.")
        )
    elif not mode_policy.can_run_tests:
        warnings.append(mode_required_message("test_with_approval"))
    elif execution_enabled:
        warnings.append("Exact allowlisted command may run only after explicit operator approval.")

    return CodingCommandPlan(
        status="approval_required" if execution_enabled else "execution_disabled",
        command_id=str(match.get("id")),
        command=command,
        purpose=payload.purpose,
        allowlist_match=True,
        approval_required=True,
        execution_enabled=execution_enabled,
        timeout_seconds=int(match.get("timeout_seconds", 120)),
        output_limit_bytes=int(match.get("output_limit_bytes", 20000)),
        plan_hash=sha256(("command_check\n" + str(match.get("id")) + "\n" + "\n".join(command)).encode("utf-8")).hexdigest()[:32],
        risk_labels=command_risk_labels(command),
        blocked_reason=(
            None
            if execution_enabled
            else "command_disabled_by_policy"
            if not entry_execution_enabled
            else "approval_mode_does_not_allow_command_execution"
        ),
        warnings=warnings,
    )


__all__ = ("plan_command",)
