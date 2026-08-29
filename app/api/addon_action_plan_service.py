"""Preview-only add-on action planner.

This module deliberately does not execute commands, install packages, mutate
files, call workers, or inspect the host dependency state. It converts a
Marketplace manifest action into an auditable plan for a future operator-gated
executor.
"""

from __future__ import annotations

from app.api.schemas.addon_actions import AddonActionPlan, AddonActionPlanRequest


SUPPORTED_LATER_ACTION_KINDS = {
    "python_package_install",
    "python_package_uninstall",
    "docker_compose_setup",
    "docker_compose_start",
    "docker_compose_stop",
    "docker_compose_restart",
    "config_toggle",
    "open_external_manager",
    "manual_instruction",
}


def _dependency_summary(request: AddonActionPlanRequest) -> list[str]:
    summary: list[str] = []
    for dependency in request.dependencies:
        label = f"{dependency.ecosystem}:{dependency.package_name}".strip(":")
        if dependency.version_constraint:
            label = f"{label} {dependency.version_constraint}"
        if dependency.source:
            label = f"{label} from {dependency.source}"
        if not dependency.required:
            label = f"{label} (optional)"
        summary.append(label)
    return summary


def build_addon_action_plan(request: AddonActionPlanRequest) -> AddonActionPlan:
    action = request.action
    dependency_summary = _dependency_summary(request)
    supported_later = action.action_kind in SUPPORTED_LATER_ACTION_KINDS
    network_boundary = "network_declared" if (request.network_access or action.network_access) else "local_only"
    plan_state = "execution_not_implemented" if supported_later and action.allowed else "unsupported_action_kind"
    refusal_reason = (
        "Local execution is not implemented yet. Future execution requires exact manifest validation, "
        "local Elysia password/operator approval, ledger write, and rollback notes."
    )
    if not action.allowed:
        plan_state = "blocked_by_manifest"
        refusal_reason = "The manifest marks this action as not allowed."
    if action.action_kind == "developer_action_missing" or action.action_key == "developer_action_missing":
        plan_state = "developer_action_missing"
        refusal_reason = "The Marketplace manifest does not declare this action."

    return AddonActionPlan(
        addon_id=request.addon_id,
        addon_name=request.addon_name,
        action_key=action.action_key,
        action_label=action.action_label,
        action_kind=action.action_kind,
        plan_state=plan_state,
        execution_enabled=False,
        mutation_allowed=False,
        command_execution_allowed=False,
        package_manager_allowed=False,
        shell_allowed=False,
        subprocess_allowed=False,
        requires_local_operator_password=True,
        requires_future_approval=True,
        trust_tier=request.trust_tier,
        risk_level=action.risk_level,
        network_boundary=network_boundary,
        dependency_count=len(request.dependencies),
        dependency_summary=dependency_summary,
        plan_summary=(
            f"Preview-only plan for {request.addon_name}: {action.action_label}. "
            "No local command, package manager, worker, file mutation, or service control will run."
        ),
        rollback_note=(
            "Rollback is not executable in this preview. A future executor must provide a concrete rollback story "
            "before any local mutation is allowed."
        ),
        refusal_reason=refusal_reason,
        private_data_sent=False,
        local_files_sent=False,
        memory_sent=False,
        request_traces_sent=False,
        dependency_inventory_sent=False,
    )


__all__ = ("SUPPORTED_LATER_ACTION_KINDS", "build_addon_action_plan")
