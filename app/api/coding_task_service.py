"""Checkpoint-only Developer Lab task planning with no autonomous execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe
from threading import RLock
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_autonomy_service import load_autonomy_policy
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.schemas.coding_tasks import (
    CodingTaskApproval,
    CodingTaskApproveRequest,
    CodingTaskCheckpoint,
    CodingTaskCheckpointRequest,
    CodingTaskPlan,
    CodingTaskPlanRequest,
    CodingTaskStopRequest,
)


_ALLOWED_TOOLS = ("repo_metadata", "approved_file_preview", "patch_plan", "command_plan")


@dataclass
class _TaskRecord:
    plan: CodingTaskPlan
    expires_at: datetime
    token: str | None = None
    approved: bool = False
    stopped: bool = False
    current_step: int = 0


_TASKS: dict[str, _TaskRecord] = {}
_LOCK = RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def plan_coding_task(payload: CodingTaskPlanRequest) -> CodingTaskPlan:
    policy = load_autonomy_policy()
    workspace = payload.workspace_label or "the workspace"
    plan_steps = [
        f"Confirm the bounded objective for {workspace}.",
        "Inspect approved repository metadata without reading source contents.",
        "Confirm the explicitly selected file scope and exclusions.",
        "Review only separately approved bounded file previews.",
        "Prepare an exact patch plan without applying it.",
        "Prepare an exact catalog-command plan without running it.",
        "Review proposed evidence, hashes, budgets, and consequences.",
        "Pause for a separate exact operation approval; schedule no continuation.",
    ][: payload.max_steps]
    if not payload.workspace_root:
        return CodingTaskPlan(
            status="plan_only",
            objective=payload.objective,
            max_steps=payload.max_steps,
            max_minutes=payload.max_minutes,
            plan_steps=plan_steps,
            warnings=["No approved repository root was supplied; no Developer Lab task record was created."],
        )
    root = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=".",
        require_existing=True,
        allow_directory=True,
    )
    if not root.allowed:
        return CodingTaskPlan(
            status="blocked",
            objective=payload.objective,
            max_steps=payload.max_steps,
            max_minutes=payload.max_minutes,
            plan_steps=plan_steps,
            blocked_reason=root.reason or "workspace_not_approved",
            warnings=["Developer Lab planning requires an exact approved repository root."],
        )
    allowed_files: list[str] = []
    for file_path in payload.allowed_files:
        guarded = guard_workspace_path(
            workspace_root=payload.workspace_root,
            target_path=file_path,
            require_existing=True,
            allow_directory=False,
        )
        if not guarded.allowed or not guarded.relative_path:
            return CodingTaskPlan(
                status="blocked",
                objective=payload.objective,
                workspace_root_hash=hash_path(root.workspace_root),
                max_steps=payload.max_steps,
                max_minutes=payload.max_minutes,
                plan_steps=plan_steps,
                blocked_reason=guarded.reason or "selected_file_not_allowed",
                warnings=["Every selected task file must pass the repository path guard."],
            )
        allowed_files.append(guarded.relative_path)
    task_id = f"task_{uuid4().hex[:16]}"
    expires = _now() + timedelta(minutes=payload.max_minutes)
    task_hash = sha256(
        ("\n".join([task_id, payload.objective, hash_path(root.workspace_root), *sorted(set(allowed_files)), str(payload.max_steps), str(payload.max_minutes)])).encode("utf-8")
    ).hexdigest()[:32]
    plan = CodingTaskPlan(
        status="approval_required",
        task_id=task_id,
        task_hash=task_hash,
        objective=payload.objective,
        workspace_root_hash=hash_path(root.workspace_root),
        allowed_files=sorted(set(allowed_files)),
        allowed_tool_ids=list(_ALLOWED_TOOLS),
        max_steps=payload.max_steps,
        max_minutes=payload.max_minutes,
        current_step=0,
        expires_at_utc=_iso(expires),
        plan_steps=plan_steps,
        autonomous_loop_allowed=bool(policy.get("autonomous_loop_allowed", False)),
        background_execution_allowed=False,
        mutation_allowed=False,
        command_execution_allowed=False,
        human_approval_required=True,
        stop_available=True,
        warnings=[
            "Approving this plan authorizes only one manually requested checkpoint at a time.",
            "Patch apply and command execution remain separate exact-approved operations.",
        ],
    )
    with _LOCK:
        _TASKS[task_id] = _TaskRecord(plan=plan, expires_at=expires)
    return plan


def approve_coding_task(payload: CodingTaskApproveRequest) -> CodingTaskApproval:
    with _LOCK:
        record = _TASKS.get(payload.task_id)
        if record is None:
            return CodingTaskApproval(status="blocked", task_id=payload.task_id, blocked_reason="unknown_task")
        if record.stopped:
            return CodingTaskApproval(status="blocked", task_id=payload.task_id, blocked_reason="task_stopped")
        if _now() >= record.expires_at:
            return CodingTaskApproval(status="blocked", task_id=payload.task_id, blocked_reason="task_expired")
        if payload.task_hash != record.plan.task_hash:
            return CodingTaskApproval(status="blocked", task_id=payload.task_id, blocked_reason="task_hash_mismatch")
        if not payload.operator_approved or payload.confirmation_phrase != "Approve bounded Developer Lab plan":
            return CodingTaskApproval(status="approval_required", task_id=payload.task_id, task_hash=record.plan.task_hash, blocked_reason="explicit_confirmation_required")
        if record.token is None:
            record.token = token_urlsafe(32)
        record.approved = True
        write_coding_audit_record(
            "task_plan_approval",
            payload.task_id,
            {
                "operation_kind": "task_plan_approval",
                "plan_hash": record.plan.task_hash,
                "workspace_root_hash": record.plan.workspace_root_hash,
                "operator_approved": True,
                "mutation_performed": False,
                "shell": False,
                "network": False,
            },
        )
        return CodingTaskApproval(
            status="approved_checkpoint_only",
            task_id=payload.task_id,
            task_hash=record.plan.task_hash,
            task_token=record.token,
            expires_at_utc=_iso(record.expires_at),
            next_step_requires_operator=True,
            warnings=["The task token remains extension-host local and grants no patch or command authority."],
        )


def advance_coding_task(payload: CodingTaskCheckpointRequest) -> CodingTaskCheckpoint:
    with _LOCK:
        record = _TASKS.get(payload.task_id)
        if record is None:
            return CodingTaskCheckpoint(status="blocked", task_id=payload.task_id, blocked_reason="unknown_task")
        if record.stopped:
            return CodingTaskCheckpoint(status="stopped", task_id=payload.task_id, stopped=True, blocked_reason="task_stopped")
        if _now() >= record.expires_at:
            return CodingTaskCheckpoint(status="blocked", task_id=payload.task_id, blocked_reason="task_expired")
        if not record.approved or not record.token or not payload.task_token or not compare_digest(payload.task_token, record.token):
            return CodingTaskCheckpoint(status="approval_required", task_id=payload.task_id, blocked_reason="task_token_mismatch")
        if not payload.operator_approved:
            return CodingTaskCheckpoint(status="approval_required", task_id=payload.task_id, blocked_reason="operator_checkpoint_approval_required")
        if record.current_step >= record.plan.max_steps:
            return CodingTaskCheckpoint(status="complete", task_id=payload.task_id, current_step=record.current_step, max_steps=record.plan.max_steps)
        record.current_step += 1
        step_label = record.plan.plan_steps[min(record.current_step - 1, len(record.plan.plan_steps) - 1)]
        receipt_id = f"task_step_{uuid4().hex[:16]}"
        write_coding_audit_record(
            "task_checkpoint",
            receipt_id,
            {
                "operation_kind": "task_checkpoint",
                "plan_hash": record.plan.task_hash,
                "workspace_root_hash": record.plan.workspace_root_hash,
                "operator_approved": True,
                "mutation_performed": False,
                "shell": False,
                "network": False,
            },
        )
        return CodingTaskCheckpoint(
            status="checkpoint_ready",
            task_id=payload.task_id,
            current_step=record.current_step,
            max_steps=record.plan.max_steps,
            step_label=step_label,
            receipt_id=receipt_id,
            execution_performed=False,
            mutation_performed=False,
            command_performed=False,
            continuation_scheduled=False,
            warnings=["No tool, command, patch, or background continuation ran; review and invoke a separate governed operation."],
        )


def stop_coding_task(payload: CodingTaskStopRequest) -> CodingTaskCheckpoint:
    with _LOCK:
        record = _TASKS.get(payload.task_id)
        if record is None:
            return CodingTaskCheckpoint(status="stopped", task_id=payload.task_id, stopped=True, warnings=["Unknown task treated as stopped."])
        record.stopped = True
        record.token = None
        receipt_id = f"task_stop_{uuid4().hex[:16]}"
        write_coding_audit_record(
            "task_stop",
            receipt_id,
            {
                "operation_kind": "task_stop",
                "plan_hash": record.plan.task_hash,
                "workspace_root_hash": record.plan.workspace_root_hash,
                "mutation_performed": False,
                "shell": False,
                "network": False,
            },
        )
        return CodingTaskCheckpoint(
            status="stopped",
            task_id=payload.task_id,
            current_step=record.current_step,
            max_steps=record.plan.max_steps,
            receipt_id=receipt_id,
            stopped=True,
            continuation_scheduled=False,
            warnings=["Task token revoked; no background continuation exists."],
        )


def clear_task_state_for_tests() -> None:
    with _LOCK:
        _TASKS.clear()


def stop_all_coding_tasks() -> int:
    with _LOCK:
        count = 0
        for record in _TASKS.values():
            if not record.stopped:
                record.stopped = True
                record.token = None
                count += 1
        return count


__all__ = (
    "advance_coding_task",
    "approve_coding_task",
    "clear_task_state_for_tests",
    "plan_coding_task",
    "stop_coding_task",
    "stop_all_coding_tasks",
)
