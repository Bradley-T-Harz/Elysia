"""Browser snapshot adapter for canonical grants, plans, cognition and receipts.

No native paths, disk writes, commands or arbitrary network destinations exist in
this adapter. Authorizing a patch returns an exact one-use plan; the owning
browser still has to check its current revision and apply it in its own buffers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from difflib import unified_diff
from hashlib import sha256
import re
import json
from threading import RLock
from time import monotonic
from uuid import uuid4

from core.codev import actions
from core.codev.approvals import PLANS
from core.codev.contracts import (BrowserWorkspaceShare, ChangePlan, FileChange, OperationReceipt,
    BrowserWorkspaceRequest as WorkspaceRequest, BrowserChatRequest as ChatRequest,
    BrowserCancelRequest as CancelRequest, BrowserPatchRequest as PatchRequest, BrowserApproveRequest as ApproveRequest)
from core.codev.grants import GRANTS, GrantDenied, utc_now, iso_now
from core.codev.revisions import workspace_hash, denied_path, relative_path


@dataclass
class BrowserWorkspace:
    actor: object
    share: BrowserWorkspaceShare
    lock: RLock = field(default_factory=RLock)
    receipts: list = field(default_factory=list)


_WORKSPACES: dict[tuple[str, str], BrowserWorkspace] = {}
_LOCK = RLock()


def _unsafe(text: str) -> bool:
    return bool(re.search(r"\b(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|AWS_ACCESS_KEY_ID|SUPABASE_SERVICE_ROLE|service_role)\b|BEGIN [A-Z ]*PRIVATE KEY|(?:/home/|/Users/|[A-Za-z]:\\Users\\)", text, re.I))


def revoke_actor(actor) -> None:
    with _LOCK:
        removed = [(key, value) for key, value in _WORKSPACES.items() if value.actor == actor]
        for key, value in removed:
            GRANTS.revoke(actor, value.share.workspace_id)
            actions.cancel_workspace_chats(actor, value.share.workspace_id)
            del _WORKSPACES[key]
        PLANS.discard(actor)
        GRANTS.retire_actor(actor)


def _workspace(actor, workspace_id):
    with _LOCK:
        value = _WORKSPACES.get((actor.client_id, workspace_id))
    if not value or value.actor != actor:
        raise GrantDenied("browser_workspace_not_shared")
    return value


def _remember(value, receipt):
    with value.lock:
        value.receipts = [receipt, *value.receipts][:40]
    return receipt


def _status(value):
    grant = GRANTS.get(value.actor, value.share.workspace_id)
    return {"workspace_id": value.share.workspace_id, "label": value.share.label,
        "revision": value.share.current_revision, "content_hash": value.share.content_hash,
        "grant": grant.model_dump() if grant else None,
        "files": [{"path": item.path, "availability": item.availability, "size_bytes": item.size_bytes}
                  for item in value.share.files], "shared_files": grant.files if grant and not grant.revoked else [],
        "native_filesystem_granted": False, "commands_granted": False, "network_granted": False}


def _revision(value, request, scope="read"):
    if (request.revision, request.content_hash) != (value.share.current_revision, value.share.content_hash):
        raise GrantDenied("browser_workspace_revision_conflict")
    return GRANTS.require(value.actor, value.share.workspace_id, scope, epoch=request.grant_epoch)


def dispatch(pair, path: str, payload: dict) -> dict:
    from core.codev import pairing
    # Local revocation and cancellation do not depend on cloud availability.
    if path == "/codev/workspace/reset":
        if payload:
            raise GrantDenied("unexpected_workspace_reset_input")
        with _LOCK:
            owned = [(key, value) for key, value in _WORKSPACES.items() if value.actor == pair.actor]
            for key, value in owned:
                GRANTS.revoke(pair.actor, value.share.workspace_id)
                PLANS.discard(pair.actor, value.share.workspace_id)
                actions.cancel_workspace_chats(pair.actor, value.share.workspace_id)
                del _WORKSPACES[key]
            epochs = GRANTS.epochs(pair.actor)
        return {"workspace_grants": [], "grant_epochs": epochs}
    if path == "/codev/chat/cancel":
        request = CancelRequest.model_validate(payload)
        return actions.cancel_chat(pair.actor, request.request_id)
    if path == "/codev/workspace/revoke":
        request = WorkspaceRequest.model_validate(payload)
        # Idempotent for this actor only; expired/previously revoked shares may
        # already have lost their source while retaining the epoch tombstone.
        with _LOCK:
            grant = GRANTS.get(pair.actor, request.workspace_id)
            if grant and not grant.revoked:
                grant = GRANTS.revoke(pair.actor, request.workspace_id)
            PLANS.discard(pair.actor, request.workspace_id)
            actions.cancel_workspace_chats(pair.actor, request.workspace_id)
            _WORKSPACES.pop((pair.actor.client_id, request.workspace_id), None)
        return {"workspace_id": request.workspace_id, "revoked": True, "grant_epoch": grant.epoch if grant else 0}
    pairing.require_live(pair)
    if path == "/codev/workspace/share":
        request = BrowserWorkspaceShare.model_validate(payload)
        if (request.surface != pair.actor.surface or not request.explicitly_approved
            or "read" not in request.scopes or request.base_revision > request.current_revision
            or any(denied_path(item.path) for item in request.files)
            or workspace_hash(request.files) != request.content_hash):
            raise GrantDenied("browser_share_scope_or_revision_invalid")
        selected = [item for item in request.files if item.text is not None]
        if len(selected) > 40 or sum(len(item.text.encode()) for item in selected) > 1024 * 1024:
            raise GrantDenied("browser_selected_content_limit")
        if any(len(item.text.encode()) > 131072 or "\0" in item.text or _unsafe(item.text) for item in selected):
            raise GrantDenied("browser_selected_content_denied")
        share = request.model_copy(deep=True)
        with _LOCK:
            key = (pair.actor.client_id, request.workspace_id)
            if key not in _WORKSPACES and len(_WORKSPACES) >= 32:
                raise GrantDenied("browser_workspace_capacity_reached")
            old = _WORKSPACES.get(key)
            if old and (old.share.draft_id != share.draft_id or share.current_revision < old.share.current_revision
                or share.current_revision == old.share.current_revision and share.content_hash != old.share.content_hash):
                raise GrantDenied("browser_workspace_identity_or_revision_conflict")
            GRANTS.issue(actor=pair.actor, workspace_id=request.workspace_id, scopes=["metadata", *request.scopes],
                files=[item.path for item in selected], command_ids=[], expected_epoch=request.expected_epoch,
                explicitly_approved=True, ttl_seconds=900)
            if old:
                PLANS.discard(pair.actor, request.workspace_id)
                actions.cancel_workspace_chats(pair.actor, request.workspace_id)
            value = BrowserWorkspace(pair.actor, share, receipts=old.receipts if old else [])
            _WORKSPACES[key] = value
        return _status(value)
    if path in {"/codev/workspace/status", "/codev/receipts"}:
        request = WorkspaceRequest.model_validate(payload)
        value = _workspace(pair.actor, request.workspace_id)
        GRANTS.require(pair.actor, request.workspace_id, "metadata")
        return {"receipts": [item.model_dump() for item in value.receipts]} if path.endswith("receipts") else _status(value)
    if path == "/codev/chat":
        request = ChatRequest.model_validate(payload)
        value = _workspace(pair.actor, request.workspace_id)
        with value.lock:
            grant = _revision(value, request, "propose" if request.response_kind == "edit_proposal" else "read")
            selected = tuple(item.model_copy(deep=True) for item in value.share.files if item.path in grant.files and item.text is not None)
            if request.response_kind == "edit_proposal" and not selected:
                raise GrantDenied("proposal_requires_selected_file_contents")
        checked_at = monotonic()
        def check_pairing(*, periodic=False):
            nonlocal checked_at
            if not periodic or monotonic() - checked_at >= 2:
                pairing.require_live(pair)
                checked_at = monotonic()
        return actions._governed_chat(pair.actor, workspace_id=request.workspace_id, message=request.message,
            request_id=request.request_id, requested_gear=request.requested_gear, selected=selected, grant=grant,
            response_kind=request.response_kind,
            handoff="Explicitly shared browser file inventory (metadata is not file contents):\n" + json.dumps([
                {"path":item.path,"size_bytes":item.size_bytes,"content_available":item.text is not None}
                for item in value.share.files[:60]],ensure_ascii=False).encode("utf-8")[:14000].decode("utf-8",errors="ignore") +
                (f"\n{len(value.share.files)-60} further inventory entries omitted for the context budget." if len(value.share.files)>60 else ""),
            authority_check=check_pairing, remember=lambda receipt: _remember(value, receipt))
    if path == "/codev/patch/plan":
        request = PatchRequest.model_validate(payload)
        value = _workspace(pair.actor, request.workspace_id)
        with value.lock:
            grant = _revision(value, request, "propose")
            changes = []
            for path, text in request.edits.items():
                relative_path(path)
                original = next((item for item in value.share.files if item.path == path), None)
                if (path not in grant.files or not original or original.text is None or len(text.encode()) > 131072
                    or "\0" in text or _unsafe(text)):
                    raise GrantDenied("browser_patch_file_not_granted")
                if text == original.text:
                    continue
                diff = "".join(unified_diff(original.text.splitlines(keepends=True), text.splitlines(keepends=True),
                    fromfile="a/" + path, tofile="b/" + path))
                changes.append(FileChange(path=path, base_hash=original.content_hash, new_text=text,
                    new_hash=sha256(text.encode()).hexdigest(), diff=diff))
            if not changes:
                raise GrantDenied("browser_patch_has_no_changes")
            plan = PLANS.register(ChangePlan(plan_id="plan_" + uuid4().hex, workspace_id=request.workspace_id,
                actor=pair.actor, base_revision=request.revision, workspace_hash=request.content_hash, grant_epoch=grant.epoch,
                plan_hash="0" * 64, summary=request.summary, changes=changes, cwd_label="Browser workspace: " + value.share.label,
                expires_at=(utc_now()+timedelta(minutes=5)).isoformat(), expected_checks=["Exact browser revision and file hashes"],
                risks=["Review every change before applying it to the browser workspace."],
                recovery_note="Keep the previous browser revision in local recovery before applying. Native files and remote drafts are unaffected."))
            return {"plan": plan.model_dump()}
    if path == "/codev/patch/authorize":
        request = ApproveRequest.model_validate(payload)
        value = _workspace(pair.actor, request.workspace_id)
        with value.lock:
            _revision(value, request, "propose")
            plan = PLANS.get(pair.actor, request.plan_id)
            if plan.workspace_id != request.workspace_id:
                raise GrantDenied("browser_plan_workspace_mismatch")
            approval, token = PLANS.approve(pair.actor, request.plan_id, request.plan_hash, explicitly_approved=request.explicitly_approved)
            approved = PLANS.consume(pair.actor, approval.approval_id, token, plan_id=request.plan_id,
                revision=request.revision, workspace_hash=request.content_hash)
            receipt = _remember(value, OperationReceipt(operation_id=approval.approval_id, request_id=approval.approval_id,
                workspace_id=request.workspace_id, status="approved", summary="Exact browser patch authorized. Browser application has not been verified.",
                base_revision=request.revision, verification="required", recovery_note=approved.recovery_note, created_at=iso_now()))
            return {"plan": approved.model_dump(), "approval": approval.model_copy(update={"consumed": True}).model_dump(), "receipt": receipt.model_dump()}
    raise GrantDenied("codev_broker_operation_unavailable")
