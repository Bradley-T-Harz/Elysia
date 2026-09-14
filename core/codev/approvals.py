"""Exact, actor-bound multi-client plans and single-use approvals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
import json
import secrets
from threading import RLock
from uuid import uuid4

from core.codev.contracts import Actor, ChangePlan, ExactApproval
from core.codev.grants import GRANTS, GrantAuthority, GrantDenied, utc_now
from core.codev.revisions import denied_path


def plan_digest(plan: ChangePlan) -> str:
    content = plan.model_dump(exclude={"plan_hash"})
    return sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass
class _Record:
    approval: ExactApproval
    token_hash: str


class PlanAuthority:
    def __init__(self, grants: GrantAuthority):
        self.grants = grants
        self._plans: dict[str, ChangePlan] = {}
        self._approvals: dict[str, _Record] = {}
        self._lock = RLock()

    def register(self, plan: ChangePlan) -> ChangePlan:
        if bool(plan.command_id) == bool(plan.changes):
            raise GrantDenied("plan_must_describe_exactly_one_operation_class")
        if any(denied_path(change.path) or sha256(change.new_text.encode()).hexdigest() != change.new_hash for change in plan.changes):
            raise GrantDenied("invalid_change_plan")
        with self._lock:
            self._plans = {key: value for key, value in self._plans.items() if datetime.fromisoformat(value.expires_at) > utc_now()}
            if len(self._plans) >= 128:
                raise GrantDenied("plan_capacity_reached")
            stored = plan.model_copy(deep=True)
            stored.plan_hash = plan_digest(stored)
            self._plans[stored.plan_id] = stored
            return stored.model_copy(deep=True)

    def get(self, actor: Actor, plan_id: str) -> ChangePlan:
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan or plan.actor != actor or datetime.fromisoformat(plan.expires_at) <= utc_now():
                raise GrantDenied("plan_missing_expired_or_wrong_actor")
            return plan.model_copy(deep=True)

    def approve(self, actor: Actor, plan_id: str, plan_hash: str, *, explicitly_approved: bool) -> tuple[ExactApproval, str]:
        if not explicitly_approved:
            raise GrantDenied("explicit_exact_approval_required")
        with self._lock:
            plan = self.get(actor, plan_id)
            if not compare_digest(plan.plan_hash, plan_hash):
                raise GrantDenied("plan_hash_mismatch")
            operation = "command_run" if plan.command_id else "browser_patch" if actor.client_kind == "browser" else "patch_apply"
            scope = "command" if plan.command_id else "propose" if actor.client_kind == "browser" else "apply"
            self.grants.require(actor, plan.workspace_id, scope, epoch=plan.grant_epoch,
                                files=[change.path for change in plan.changes], command_id=plan.command_id)
            self._approvals = {key: value for key, value in self._approvals.items()
                               if not value.approval.consumed and datetime.fromisoformat(value.approval.expires_at) > utc_now()}
            if len(self._approvals) >= 128:
                raise GrantDenied("approval_capacity_reached")
            approval = ExactApproval(approval_id=f"approval_{uuid4().hex}", actor=actor,
                workspace_id=plan.workspace_id, revision=plan.base_revision, workspace_hash=plan.workspace_hash,
                grant_epoch=plan.grant_epoch, operation=operation, files=[change.path for change in plan.changes],
                plan_hash=plan.plan_hash, command_argv=plan.command_argv, cwd_label=plan.cwd_label,
                expires_at=min(datetime.fromisoformat(plan.expires_at), utc_now() + timedelta(minutes=5)).isoformat())
            token = secrets.token_urlsafe(32)
            self._approvals[approval.approval_id] = _Record(approval, sha256(token.encode()).hexdigest())
            return approval.model_copy(deep=True), token

    def consume(self, actor: Actor, approval_id: str, token: str, *, plan_id: str,
                revision: int, workspace_hash: str) -> ChangePlan:
        with self._lock:
            record = self._approvals.get(approval_id)
            if not record or record.approval.actor != actor or not compare_digest(record.token_hash, sha256(token.encode()).hexdigest()):
                raise GrantDenied("approval_not_valid_for_actor")
            approval = record.approval
            if approval.consumed or datetime.fromisoformat(approval.expires_at) <= utc_now():
                raise GrantDenied("approval_expired_or_consumed")
            plan = self.get(actor, plan_id)
            if plan.plan_hash != approval.plan_hash or plan.workspace_id != approval.workspace_id:
                raise GrantDenied("approval_plan_mismatch")
            if approval.revision != revision or approval.workspace_hash != workspace_hash:
                raise GrantDenied("workspace_revision_conflict")
            scope = "command" if approval.operation == "command_run" else "propose" if approval.operation == "browser_patch" else "apply"
            self.grants.require(actor, approval.workspace_id, scope, files=approval.files,
                                epoch=approval.grant_epoch, command_id=plan.command_id)
            approval.consumed = True
            self._plans.pop(plan_id)
            return plan

    def discard(self, actor: Actor, workspace_id: str | None = None) -> None:
        """Drop source-bearing plans and approvals when their scope is revoked."""
        with self._lock:
            self._plans = {key: plan for key, plan in self._plans.items()
                if plan.actor != actor or workspace_id is not None and plan.workspace_id != workspace_id}
            self._approvals = {key: record for key, record in self._approvals.items()
                if record.approval.actor != actor or workspace_id is not None and record.approval.workspace_id != workspace_id}


PLANS = PlanAuthority(GRANTS)
