"""Native adapter for the canonical multi-client Codev domain."""
from __future__ import annotations

from uuid import uuid4
from fastapi import APIRouter
from core.codev.contracts import CLIENT_CONTRACT
from core.codev.installation import resolve_installation

router = APIRouter(prefix="/codev", tags=["codev"])


def envelope(result_type: str, data: dict) -> dict:
    return {"status": "ok", "request_id": f"codev_{uuid4().hex}", "api_version": "1.0.0",
            "contract_version": CLIENT_CONTRACT, "result_type": result_type,
            "data": data, "warnings": [], "errors": [], "locality": "local"}


@router.get("/installation")
def installation_status() -> dict:
    return envelope("codev_installation", {"codev_installation": resolve_installation().model_dump()})


from fastapi import HTTPException
from app.api.account_service import AccountServiceError
from app.api.schemas.codev_native import (
    NativeRequest, WorkspaceRequest, SelectRequest, GrantRequest, PatchRequest, ApprovalRequest,
    ApplyRequest, CommandPlanRequest, CommandStatusRequest, ChatRequest, ChatCancelRequest,
    PairingClaimRequest, PairingActionRequest, PairingRevokeRequest,
)
from core.codev import actions, workspaces
from core.codev.approvals import PLANS
from core.codev.grants import GrantDenied
from core.codev.sessions import open_native_session, require_native_session
from core.codev import pairing


@router.post("/pairing/claim")
def pairing_claim(payload: PairingClaimRequest):
    return perform("codev_pairing", lambda: pairing.claim(payload.client_id, payload.code))


@router.post("/pairing/action")
def pairing_action(payload: PairingActionRequest):
    return perform("codev_pairing", lambda: pairing.native_action(**payload.model_dump()))


@router.post("/pairing/list")
def pairing_list(payload: NativeRequest):
    return perform("codev_pairing", lambda: {"pairings": pairing.list_native(payload.client_id)})


@router.post("/pairing/revoke")
def pairing_revoke(payload: PairingRevokeRequest):
    return perform("codev_pairing", lambda: pairing.native_action(payload.client_id, payload.pairing_id, "revoke"))


def perform(kind, callback):
    try:
        return envelope(kind, callback())
    except (GrantDenied, AccountServiceError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="The local workspace changed or is unavailable. Refresh its state before continuing.") from exc


@router.post("/session")
def open_session():
    return perform("codev_session", lambda: {"actor": open_native_session().model_dump()})


@router.post("/workspaces/select")
def select(payload: SelectRequest):
    return perform("codev_workspace", lambda: {"workspace": workspaces.select_workspace(
        require_native_session(payload.client_id), payload.root_path).model_dump()})


@router.post("/grants/issue")
def grant(payload: GrantRequest):
    return perform("codev_grant", lambda: workspaces.grant_workspace(require_native_session(payload.client_id),
        payload.workspace_id, **payload.model_dump(exclude={"client_id", "workspace_id"})))


@router.post("/grants/revoke")
def revoke(payload: WorkspaceRequest):
    return perform("codev_revocation", lambda: workspaces.revoke_workspace(
        require_native_session(payload.client_id, revocation_only=True), payload.workspace_id))


@router.post("/workspaces/tree")
def tree(payload: WorkspaceRequest):
    return perform("codev_tree", lambda: workspaces.tree(require_native_session(payload.client_id), payload.workspace_id))


@router.post("/workspaces/snapshot")
def snapshot(payload: WorkspaceRequest):
    return perform("codev_workspace", lambda: {"workspace": workspaces.snapshot(
        require_native_session(payload.client_id), payload.workspace_id).model_dump()})


@router.post("/patches/plan")
def patch(payload: PatchRequest):
    return perform("codev_plan", lambda: {"plan": workspaces.plan_patch(require_native_session(payload.client_id),
        payload.workspace_id, edits=payload.edits, revision=payload.revision, summary=payload.summary).model_dump()})


@router.post("/approvals/issue")
def approve(payload: ApprovalRequest):
    def action():
        approved, token = PLANS.approve(require_native_session(payload.client_id), payload.plan_id, payload.plan_hash,
                                       explicitly_approved=payload.explicitly_approved)
        return {"approval": approved.model_dump(), "approval_token": token}
    return perform("codev_approval", action)


@router.post("/patches/apply")
def apply(payload: ApplyRequest):
    return perform("codev_receipt", lambda: {"receipt": workspaces.apply_plan(require_native_session(payload.client_id),
        payload.workspace_id, plan_id=payload.plan_id, approval_id=payload.approval_id,
        approval_token=payload.approval_token).model_dump()})


@router.post("/commands/catalog")
def catalog(payload: NativeRequest):
    def action():
        require_native_session(payload.client_id)
        return {"catalog": actions.command_catalog()}
    return perform("codev_catalog", action)


@router.post("/commands/plan")
def command_plan(payload: CommandPlanRequest):
    return perform("codev_plan", lambda: {"plan": actions.plan_command(require_native_session(payload.client_id),
        payload.workspace_id, payload.command_id).model_dump()})


@router.post("/commands/start")
def command_start(payload: ApplyRequest):
    return perform("codev_command", lambda: actions.start_command(require_native_session(payload.client_id),
        payload.workspace_id, plan_id=payload.plan_id, approval_id=payload.approval_id, approval_token=payload.approval_token))


@router.post("/commands/status")
def command_status(payload: CommandStatusRequest):
    return perform("codev_command", lambda: actions.command_status(require_native_session(payload.client_id, revocation_only=True),
        payload.workspace_id, payload.run_id))


@router.post("/commands/cancel")
def command_cancel(payload: CommandStatusRequest):
    return perform("codev_cancellation", lambda: actions.cancel_command(require_native_session(payload.client_id, revocation_only=True),
        payload.workspace_id, payload.run_id))


@router.post("/chat")
def chat(payload: ChatRequest):
    return perform("codev_chat", lambda: actions.chat(require_native_session(payload.client_id),
        **payload.model_dump(exclude={"client_id"})))


@router.post("/chat/cancel")
def chat_cancel(payload: ChatCancelRequest):
    return perform("codev_cancellation", lambda: actions.cancel_chat(
        require_native_session(payload.client_id, revocation_only=True), payload.request_id))


@router.post("/receipts")
def receipts(payload: WorkspaceRequest):
    return perform("codev_receipts", lambda: {"receipts": workspaces.receipts(
        require_native_session(payload.client_id, revocation_only=True), payload.workspace_id)})
