"""
Elysia policy gate scaffold.

This module reviews a structured plan and records which policy-relevant
boundaries were touched.

Current distinction:
- low-risk governed local response generation may proceed
- broader tool use, outward action, and side-effecting execution remain
  disabled / approval-bound during scaffold phase
- local session memory is visible as a boundary flag, but does not by itself
  make an ordinary local response approval-bound
"""

from typing import Any, Dict, List


_SENSITIVE_MEMORY_CLASSES = {
    "sealed_private_memory",
    "audit_memory",
}


def _is_local_session_memory_source(memory_context_source: str) -> bool:
    """
    Return True when the memory source is a known local session journal scaffold.
    """
    return memory_context_source.startswith("local_session_journal_scaffold")


def _normalize_memory_class_name(value: Any) -> str:
    """
    Normalize one memory-class value into a clean string.
    """
    return str(value or "").strip()


def _append_once(values: List[str], value: str) -> None:
    """
    Append a string once while preserving ordering.
    """
    if value not in values:
        values.append(value)


def evaluate_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Review a scaffold plan and record boundary flags.

    Current scaffold behavior:
    - ordinary low-risk local response generation can be allowed
    - side-effecting execution remains unavailable during scaffold phase
    - approval is required only when an approval-bound boundary is touched
    - local session journal memory is flagged but not treated as approval-bound
      by itself
    - sealed/private/audit memory, tools, external network, file writes,
      high-risk plans, and execution requests remain approval-bound
    """
    requires_tools = bool(plan.get("requires_tools", False))
    touches_external_network = bool(plan.get("touches_external_network", False))
    writes_files = bool(plan.get("writes_files", False))
    reads_private_memory = bool(plan.get("reads_private_memory", False))
    execution_allowed = bool(plan.get("execution_allowed", False))
    bounded_math_execution_candidate = bool(
        plan.get("bounded_math_execution_candidate", False)
    )
    bounded_data_execution_candidate = bool(
        plan.get("bounded_data_execution_candidate", False)
    )
    repo_context_candidate = bool(
        plan.get("repo_context_candidate", False)
    )
    code_patch_plan_candidate = bool(
        plan.get("code_patch_plan_candidate", False)
    )
    hard_blocked_request = bool(plan.get("hard_blocked_request", False))
    governed_public_research = bool(plan.get("governed_public_research_candidate", False))

    risk_level = str(plan.get("risk_level", "unknown"))
    memory_context_source = str(plan.get("memory_context_source", "") or "")
    memory_class = _normalize_memory_class_name(plan.get("memory_class", ""))
    forced_memory_class = _normalize_memory_class_name(
        plan.get("forced_memory_class", "")
    )
    memory_class_boundary_sensitive = bool(
        plan.get("memory_class_boundary_sensitive", False)
    )
    memory_class_requires_boundary_check = bool(
        plan.get("memory_class_requires_boundary_check", False)
    )
    checked_step_count = len(plan.get("steps", []))

    local_session_memory = _is_local_session_memory_source(memory_context_source)

    approval_reasons: List[str] = [
        (
            "governed local response generation may proceed when no approval-bound "
            "boundary is touched; broader tool use, outward action, and "
            "side-effecting execution remain disabled during scaffold phase"
        )
    ]
    boundary_flags: List[str] = []
    approval_bound_boundary_touched = False

    if requires_tools and not governed_public_research:
        _append_once(boundary_flags, "tool_usage")
        approval_reasons.append("plan requests tool usage")
        approval_bound_boundary_touched = True

    if hard_blocked_request:
        _append_once(boundary_flags, "hard_blocked_request")
        approval_reasons.append(
            "request combines private/vault context with an outward or mutation-bound action"
        )
        approval_bound_boundary_touched = True

    if touches_external_network:
        if governed_public_research and not hard_blocked_request:
            _append_once(boundary_flags, "governed_public_research")
            approval_reasons.append(
                "public research may proceed only through the Internet master, egress classifier, scrubber, and bounded ResearchPort"
            )
        else:
            _append_once(boundary_flags, "external_network")
            approval_reasons.append("plan touches external network")
            approval_bound_boundary_touched = True

    if writes_files:
        _append_once(boundary_flags, "file_writes")
        approval_reasons.append("plan writes files")
        approval_bound_boundary_touched = True

    if reads_private_memory:
        if local_session_memory:
            _append_once(boundary_flags, "local_session_memory")
            approval_reasons.append("plan reads local session journal memory")
        elif memory_class == "sealed_private_memory":
            _append_once(boundary_flags, "sealed_private_memory")
            approval_reasons.append("plan uses sealed private memory class")
            approval_bound_boundary_touched = True
        elif memory_class == "audit_memory":
            _append_once(boundary_flags, "audit_memory")
            approval_reasons.append("plan uses audit memory class")
            approval_bound_boundary_touched = True
        else:
            _append_once(boundary_flags, "private_memory")
            approval_reasons.append("plan reads private memory")
            approval_bound_boundary_touched = True

    if forced_memory_class and not local_session_memory:
        approval_reasons.append(
            f"plan memory class was forced to {forced_memory_class}"
        )

        if forced_memory_class == "sealed_private_memory":
            _append_once(boundary_flags, "sealed_private_memory")
            approval_reasons.append(
                "forced memory class sealed_private_memory is approval-bound"
            )
            approval_bound_boundary_touched = True

        if forced_memory_class == "audit_memory":
            _append_once(boundary_flags, "audit_memory")
            approval_reasons.append(
                "forced memory class audit_memory is approval-bound"
            )
            approval_bound_boundary_touched = True

    if memory_class_boundary_sensitive and memory_class in _SENSITIVE_MEMORY_CLASSES:
        _append_once(boundary_flags, memory_class)
        approval_reasons.append(
            f"plan memory class {memory_class} is boundary-sensitive"
        )
        approval_bound_boundary_touched = True

    if memory_class_requires_boundary_check:
        approval_reasons.append("selected memory class requires boundary check")

    if bounded_math_execution_candidate:
        _append_once(boundary_flags, "bounded_local_math_execution")
        approval_reasons.append(
            "bounded local math execution is allowed as non-side-effecting local computation"
        )

    if bounded_data_execution_candidate:
        _append_once(boundary_flags, "bounded_local_data_execution")
        approval_reasons.append(
            "bounded local data execution is allowed as read-only local CSV/XLSX inspection of an attached file"
        )

    if repo_context_candidate:
        _append_once(boundary_flags, "bounded_repo_context")
        approval_reasons.append(
            "read-only approved repo context gathering is allowed as local non-side-effecting inspection"
        )

    if code_patch_plan_candidate:
        _append_once(boundary_flags, "code_patch_plan")
        approval_reasons.append(
            "proposal-only patch planning is allowed; patch application remains approval-bound and not live"
        )

    if risk_level == "high":
        _append_once(boundary_flags, "high_risk")
        approval_reasons.append("plan is marked high risk")
        approval_bound_boundary_touched = True

    if execution_allowed:
        _append_once(boundary_flags, "execution_requested")
        approval_reasons.append(
            "plan requested execution even though scaffold blocks it"
        )
        approval_bound_boundary_touched = True

    if not boundary_flags and not execution_allowed and risk_level == "low":
        boundary_flags.append("low_risk_nonexecuting_path")

    approval_required = approval_bound_boundary_touched
    allowed = not approval_required

    return {
        "allowed": allowed,
        "approval_required": approval_required,
        "approval_reasons": approval_reasons,
        "boundary_flags": boundary_flags,
        "review_note": (
            "Policy gate distinguishes governed local response generation from "
            "side-effecting execution. Local responses may proceed when no "
            "approval-bound boundary is touched; tools, outward actions, file "
            "writes, sensitive memory, high-risk plans, and execution requests "
            "remain approval-bound during scaffold phase. Bounded local math "
            "execution, bounded local CSV/XLSX data inspection, read-only approved "
            "repo context, and proposal-only patch planning are treated as "
            "non-side-effecting local computation when narrowly planned."
        ),
        "checked_step_count": checked_step_count,
    }


if __name__ == "__main__":
    demo_plan = {
        "steps": [
            "interpret the request",
            "gather allowed context",
            "respond carefully",
            "check the result",
        ],
        "requires_tools": False,
        "touches_external_network": False,
        "writes_files": False,
        "reads_private_memory": True,
        "memory_context_source": "local_session_journal_scaffold_excluding_current_day",
        "memory_class": "working_memory",
        "forced_memory_class": "working_memory",
        "memory_class_boundary_sensitive": False,
        "memory_class_requires_boundary_check": True,
        "risk_level": "low",
        "execution_allowed": False,
    }

    print(evaluate_plan(demo_plan))
