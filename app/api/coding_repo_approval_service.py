"""Exact, local approval contracts for Codev repository roots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_policy_service import load_coding_policy
from app.api.coding_repo_registry import (
    list_approved_repo_roots,
    record_repo_approval,
    revoke_repo_approval,
)
from app.api.schemas.coding import (
    CodingRepoApprovalApplyRequest,
    CodingRepoApprovalPlan,
    CodingRepoApprovalPlanRequest,
    CodingRepoApprovalResult,
    CodingRepoApprovalStatus,
    CodingRepoApprovalStatusRequest,
    CodingRepoRevokeRequest,
)


PLAN_TTL_SECONDS = 300


@dataclass
class _PlanRecord:
    plan: CodingRepoApprovalPlan
    root: Path
    expires_at: datetime
    used: bool = False


_PLANS: dict[str, _PlanRecord] = {}
_LOCK = RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _root_hash(root: Path) -> str:
    return sha256(str(root).encode("utf-8")).hexdigest()[:24]


def _candidate(workspace_root: str) -> tuple[Path, str, str | None]:
    root = Path(workspace_root).expanduser().resolve(strict=False)
    label = root.name or "repository"
    broad = {Path(root.anchor), Path.home().resolve(), Path("/home"), Path("/tmp")}
    if not root.exists() or not root.is_dir():
        return root, label, "workspace_root_not_directory"
    if root in broad:
        return root, label, "workspace_root_too_broad"
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current = current / part
        if current.is_symlink():
            return root, label, "workspace_root_symlink"
    policy = load_coding_policy()
    blocked = {str(item).casefold() for item in policy.get("blocked_path_parts") or []}
    if any(part.casefold() in blocked for part in root.parts):
        return root, label, "workspace_root_blocked"
    return root, label, None


def repo_approval_status(payload: CodingRepoApprovalStatusRequest) -> CodingRepoApprovalStatus:
    root, label, error = _candidate(payload.workspace_root)
    root_hash = _root_hash(root)
    approved = any(candidate == root for _, candidate in list_approved_repo_roots())
    return CodingRepoApprovalStatus(
        status="approved" if approved else "blocked" if error else "approval_required",
        workspace_label=label,
        workspace_root_hash=root_hash,
        approved=approved,
        revoked=False,
        approval_source="XDG private repository registry" if approved else None,
        blocked_reason=error,
        raw_path_exposed=False,
        warnings=[
            "Repository approval is exact to this root and grants no shell, Git mutation, package, network, push, or publish authority."
        ],
    )


def plan_repo_approval(payload: CodingRepoApprovalPlanRequest) -> CodingRepoApprovalPlan:
    root, label, error = _candidate(payload.workspace_root)
    root_hash = _root_hash(root)
    if error:
        return CodingRepoApprovalPlan(
            status="blocked",
            workspace_label=label,
            workspace_root_hash=root_hash,
            blocked_reason=error,
            raw_path_exposed=False,
            warnings=["No repository approval plan was issued."],
        )
    plan_id = f"repo_plan_{uuid4().hex[:16]}"
    expires = _now() + timedelta(seconds=PLAN_TTL_SECONDS)
    plan_hash = sha256(f"repo_approval\n{root_hash}\n{label}\n{plan_id}".encode("utf-8")).hexdigest()[:32]
    plan = CodingRepoApprovalPlan(
        status="approval_required",
        plan_id=plan_id,
        plan_hash=plan_hash,
        workspace_label=label,
        workspace_root_hash=root_hash,
        expires_at_utc=_iso(expires),
        consequences=[
            "Allow bounded metadata and explicitly approved file/patch/check requests inside this repository root.",
            "Keep shell, Git mutation, package installation, network, push, publish, and broad filesystem access unavailable.",
        ],
        raw_path_exposed=False,
        warnings=["Review the exact repository label and root hash before approval."],
    )
    with _LOCK:
        _PLANS[plan_id] = _PlanRecord(plan=plan, root=root, expires_at=expires)
    return plan


def apply_repo_approval(payload: CodingRepoApprovalApplyRequest) -> CodingRepoApprovalResult:
    with _LOCK:
        record = _PLANS.get(payload.plan_id)
        if record is None:
            return CodingRepoApprovalResult(status="blocked", blocked_reason="unknown_plan")
        if record.used:
            return CodingRepoApprovalResult(status="blocked", blocked_reason="plan_already_used")
        if _now() >= record.expires_at:
            return CodingRepoApprovalResult(status="blocked", blocked_reason="plan_expired")
        if payload.plan_hash != record.plan.plan_hash:
            return CodingRepoApprovalResult(status="blocked", blocked_reason="plan_hash_mismatch")
        if not payload.operator_approved or payload.confirmation_phrase != "Approve exact repository":
            return CodingRepoApprovalResult(status="approval_required", blocked_reason="explicit_confirmation_required")
        root, label, error = _candidate(str(record.root))
        if error or _root_hash(root) != record.plan.workspace_root_hash:
            return CodingRepoApprovalResult(status="blocked", blocked_reason=error or "workspace_root_changed")
        record_repo_approval(root_hash=record.plan.workspace_root_hash, root=root, label=label)
        record.used = True
    operation_id = f"repo_approval_{uuid4().hex[:16]}"
    audit_written = write_coding_audit_record(
        "repo_approval",
        operation_id,
        {
            "operation_kind": "repo_approval",
            "workspace_root_hash": record.plan.workspace_root_hash,
            "operator_approved": True,
            "mutation_performed": True,
            "shell": False,
            "network": False,
        },
    )
    return CodingRepoApprovalResult(
        status="approved",
        workspace_label=label,
        workspace_root_hash=record.plan.workspace_root_hash,
        approved=True,
        operation_id=operation_id,
        audit_written=audit_written,
        raw_path_exposed=False,
        warnings=["Repository approval grants only separately governed Codev operations."],
    )


def revoke_repo(payload: CodingRepoRevokeRequest) -> CodingRepoApprovalResult:
    root, label, error = _candidate(payload.workspace_root)
    root_hash = _root_hash(root)
    if error:
        return CodingRepoApprovalResult(status="blocked", blocked_reason=error)
    if not payload.operator_approved or payload.confirmation_phrase != "Revoke repository approval":
        return CodingRepoApprovalResult(status="approval_required", blocked_reason="explicit_confirmation_required")
    revoked = revoke_repo_approval(root_hash=root_hash)
    operation_id = f"repo_revoke_{uuid4().hex[:16]}"
    audit_written = write_coding_audit_record(
        "repo_revoke",
        operation_id,
        {
            "operation_kind": "repo_revoke",
            "workspace_root_hash": root_hash,
            "operator_approved": True,
            "mutation_performed": revoked,
            "shell": False,
            "network": False,
        },
    )
    return CodingRepoApprovalResult(
        status="revoked" if revoked else "not_approved",
        workspace_label=label,
        workspace_root_hash=root_hash,
        approved=False,
        revoked=revoked,
        operation_id=operation_id,
        audit_written=audit_written,
        raw_path_exposed=False,
        warnings=["Revocation withdraws Codev repository authority immediately."],
    )


def clear_repo_approval_plans_for_tests() -> None:
    with _LOCK:
        _PLANS.clear()


__all__ = (
    "apply_repo_approval",
    "clear_repo_approval_plans_for_tests",
    "plan_repo_approval",
    "repo_approval_status",
    "revoke_repo",
)
