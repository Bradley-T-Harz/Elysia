"""Shared governed command and cognition actions for Codev clients."""
from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from threading import RLock, Event, Thread
from time import monotonic
from uuid import uuid4

from core.codev.approvals import PLANS
from core.codev.contracts import Actor, ChangePlan, OperationReceipt
from core.codev.grants import GRANTS, GrantDenied, iso_now, utc_now
from core.codev.identity import bind_client
from core.codev.runtime_scope import CHAT_BUDGET_SECONDS, DevelopmentContext, development_context
from core.codev.workspaces import get_workspace, _refresh, _scope, _remember

_CHAT_OWNERS: dict[str, tuple[Actor, str | None]] = {}
_CHAT_LOCK = RLock()


def command_catalog() -> dict:
    from app.api.coding_command_allowlist_service import public_command_catalog
    return public_command_catalog()


def plan_command(actor: Actor, workspace_id: str, command_id: str) -> ChangePlan:
    from app.api.coding_command_allowlist_service import find_allowlist_match_by_id, load_command_allowlist
    value = get_workspace(actor, workspace_id)
    with value.lock, _scope(value):
        grant = GRANTS.require(actor, workspace_id, "command", command_id=command_id)
        policy = load_command_allowlist()
        entry = find_allowlist_match_by_id(command_id, policy)
        if not policy.get("execution_enabled") or not entry or not entry.get("execution_enabled", True):
            raise GrantDenied("command_worker_unavailable")
        _refresh(value)
        return PLANS.register(ChangePlan(plan_id=f"plan_{uuid4().hex}", workspace_id=workspace_id, actor=actor,
            base_revision=value.revision, workspace_hash=value.snapshot_hash, grant_epoch=grant.epoch,
            plan_hash="0" * 64, summary="Run the exact allowlisted repository check.", command_id=command_id,
            command_argv=entry["command"], cwd_label=value.root.name,
            expected_checks=["Exit code and bounded output", f"Timeout: {max(1, min(int(entry.get('timeout_seconds', 120)), 300))} seconds", f"Output limit: {max(256, min(int(entry.get('output_limit_bytes', 20000)), 1_000_000))} bytes"], risks=["Only the fixed command shown here is authorized."],
            expires_at=(utc_now() + timedelta(minutes=5)).isoformat(), recovery_note="No file mutation is authorized by this check."))


def start_command(actor: Actor, workspace_id: str, *, plan_id: str, approval_id: str, approval_token: str) -> dict:
    from app.api import coding_process_service as process
    from app.api.coding_operation_service import approve_operation
    from app.api.schemas.coding_operations import CodingOperationApproveRequest
    from app.api.schemas.coding_commands import CodingCommandRunApprovedRequest
    value = get_workspace(actor, workspace_id)
    with value.lock, _scope(value):
        if any(process.get_command_status(run).status in {"queued", "running"} for run in value.command_runs):
            raise GrantDenied("workspace_command_already_running")
        candidate = PLANS.get(actor, plan_id)
        if candidate.workspace_id != workspace_id or not candidate.command_id:
            raise GrantDenied("command_plan_workspace_mismatch")
        _refresh(value)
        plan = PLANS.consume(actor, approval_id, approval_token, plan_id=plan_id,
                             revision=value.revision, workspace_hash=value.snapshot_hash)
        digest = sha256(("command_check\n" + plan.command_id + "\n" + "\n".join(plan.command_argv)).encode()).hexdigest()[:32]
        child = approve_operation(CodingOperationApproveRequest(operation_kind="command_run", operation_summary=plan.summary,
            workspace_root=str(value.root), exact_files=[], source_hash=None, plan_hash=digest,
            allowed_mutation_class="command_check", operator_approved=True, rollback_note=plan.recovery_note))
        started = process.start_approved_command(CodingCommandRunApprovedRequest(approval_id=child.approval_id,
            approval_token=child.approval_token, approval_mode="test_with_approval", command_id=plan.command_id,
            workspace_root=str(value.root), operator_approved=True))
        value.command_runs.add(started.run_id)
        return started.to_payload()


def command_status(actor: Actor, workspace_id: str, run_id: str) -> dict:
    from app.api import coding_process_service as process
    value = get_workspace(actor, workspace_id, require_directory=False)
    if run_id not in value.command_runs:
        raise GrantDenied("command_not_found_for_workspace")
    with bind_client(actor.client_id):
        state = process.get_command_status(run_id)
        result = process.get_command_result(run_id)
    receipt = None
    if result:
        status = "completed" if result.status == "completed" else "cancelled" if result.status == "cancelled" else "failed" if result.execution_performed else "blocked"
        receipt = _remember(value, OperationReceipt(operation_id=run_id, request_id=run_id, workspace_id=workspace_id,
            status=status, summary="Repository check " + status + ".", commands_run=[result.command] if result.execution_performed else [],
            verification="passed" if result.status == "completed" else "failed" if result.execution_performed else "not_run",
            audit_written=result.audit_written, warnings=result.warnings, created_at=iso_now()))
    return {"state": state.to_payload(), "result": result.to_payload() if result else None,
            "receipt": receipt.model_dump() if receipt else None}


def cancel_command(actor: Actor, workspace_id: str, run_id: str) -> dict:
    from app.api import coding_process_service as process
    from app.api.schemas.coding_commands import CodingCommandCancelRequest
    value = get_workspace(actor, workspace_id, require_directory=False)
    if run_id not in value.command_runs:
        raise GrantDenied("command_not_found_for_workspace")
    with bind_client(actor.client_id):
        return process.cancel_command(CodingCommandCancelRequest(run_id=run_id)).to_payload()


def chat(actor: Actor, *, workspace_id: str | None, message: str, request_id: str,
         requested_gear: str = "standard", handoff: str = "") -> dict:
    value, selected, grant = None, (), None
    if workspace_id:
        value = get_workspace(actor, workspace_id)
        with value.lock:
            grant = GRANTS.require(actor, workspace_id, "read")
            _refresh(value)
            selected = tuple(item.model_copy(deep=True) for item in value.files if item.text is not None and item.path in grant.files)
    return _governed_chat(actor, workspace_id=workspace_id, message=message, request_id=request_id,
        requested_gear=requested_gear, handoff=handoff, selected=selected, grant=grant,
        remember=(lambda receipt: _remember(value, receipt)) if value else None)


def _governed_chat(actor: Actor, *, workspace_id: str | None, message: str, request_id: str,
                   requested_gear: str, handoff: str = "", selected=(), grant=None,
                   authority_check=None, remember=None) -> dict:
    """One governed runtime for native and explicitly shared browser snapshots."""
    deadline = monotonic() + CHAT_BUDGET_SECONDS
    from app.api.runtime_bridge import send_chat_request
    from app.cognition.emergency_control import bind_request_owner, request_cancel_event, release_request
    from app.api.account_service import get_authenticated_principal, AccountServiceError
    from core.codev.sessions import ensure_available
    principal = get_authenticated_principal()
    if principal["user_id"] != actor.local_profile_id:
        raise GrantDenied("local_account_changed_during_request")
    if not message.strip() or len(message.encode()) > 16000 or len(handoff.encode()) > 16000:
        raise GrantDenied("bounded_message_required")
    if requested_gear not in {"automatic", "quick", "standard", "deep", "deliberative", "research_engineering"}:
        raise GrantDenied("unsupported_reasoning_gear")
    with _CHAT_LOCK:
        if any(owner[0] == actor for owner in _CHAT_OWNERS.values()) or request_id in _CHAT_OWNERS or len(_CHAT_OWNERS) >= 8:
            raise GrantDenied("codev_cognition_busy")
        if actor.client_kind == "browser" and sum(owner[0].client_kind == "browser" for owner in _CHAT_OWNERS.values()) >= 4:
            raise GrantDenied("codev_browser_cognition_busy")
        _CHAT_OWNERS[request_id] = (actor, workspace_id)
    bind_request_owner(request_id, actor.local_profile_id)
    cancelled = request_cancel_event(request_id)
    finished = Event()

    def still_authorized(*, periodic=False):
        current = get_authenticated_principal()
        if (current["user_id"], current["session_id"]) != (principal["user_id"], principal["session_id"]):
            raise GrantDenied("local_account_changed_during_request")
        ensure_available()
        if authority_check:
            authority_check(periodic=periodic)
        if grant:
            GRANTS.require(actor, workspace_id, "read", epoch=grant.epoch)

    def monitor():
        while not finished.wait(0.5):
            try:
                still_authorized(periodic=True)
            except (AccountServiceError, ValueError, OSError):
                cancelled.set()
                return

    watcher = Thread(target=monitor, name="codev-cognition-authority", daemon=True)
    watcher.start()
    try:
        still_authorized()
        with bind_client(actor.client_id), development_context(DevelopmentContext(
            workspace_id or "no-workspace", selected, handoff, deadline_monotonic=deadline
        )):
            response = send_chat_request({"message": message, "request_id": request_id, "requested_mode": "coder",
                "requested_gear": requested_gear, "ui_surface": "codev_" + actor.surface})
        still_authorized()
        data = response.get("data") or {}
        live = (monotonic() < deadline and not cancelled.is_set()
                and data.get("invocation_status") == "ok" and data.get("response_source") == "live_invoker")
        receipt = OperationReceipt(operation_id=request_id, request_id=request_id, workspace_id=workspace_id,
            status="cancelled" if cancelled.is_set() else "completed" if live else "blocked", summary="Governed local Codev response." if live else "The local model did not complete this request.",
            files_inspected=[item.path for item in selected], warnings=data.get("caveats") or [],
            verification="not_run", created_at=iso_now())
        if remember:
            remember(receipt)
        return {"response_text": data.get("response_text", "") if live else "Local reasoning is unavailable. Your workspace remains available for inspection and exact edits.",
                "model_role": data.get("selected_model_role"), "model_tag": data.get("selected_model_runtime_tag"),
                "invocation_status": data.get("invocation_status", "unavailable"), "receipt": receipt.model_dump(),
                "context_receipt": data.get("context_receipt"), "governor": data.get("governor")}
    finally:
        finished.set()
        watcher.join(timeout=1)
        with _CHAT_LOCK:
            _CHAT_OWNERS.pop(request_id, None)
        release_request(request_id)


def cancel_chat(actor: Actor, request_id: str) -> dict:
    from app.cognition.emergency_control import cancel_request
    with _CHAT_LOCK:
        owner = _CHAT_OWNERS.get(request_id)
        if not owner or owner[0] != actor:
            raise GrantDenied("request_not_found_for_client")
    return {"cancellation_requested": cancel_request(request_id, actor.local_profile_id)}


def cancel_workspace_chats(actor: Actor, workspace_id: str) -> None:
    from app.cognition.emergency_control import cancel_request
    with _CHAT_LOCK:
        for request_id, owner in _CHAT_OWNERS.items():
            if owner == (actor, workspace_id):
                cancel_request(request_id, actor.local_profile_id)
