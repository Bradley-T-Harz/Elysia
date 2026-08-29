"""Local-only VS Code coding bridge MVP routes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_chat_service import handle_coding_chat
from app.api.coding_policy_service import build_coding_status
from app.api.coding_repo_service import inspect_repo_preview
from app.api.coding_repo_approval_service import (
    apply_repo_approval,
    plan_repo_approval,
    repo_approval_status,
    revoke_repo,
)
from app.api.coding_session_service import start_coding_session
from app.api.codev_profile_service import build_codev_developer_profile_status
from app.api.schemas.coding import (
    CodingChatRequest,
    CodingSessionStartRequest,
    RepoInspectPreviewRequest,
    CodingRepoApprovalApplyRequest,
    CodingRepoApprovalPlanRequest,
    CodingRepoApprovalStatusRequest,
    CodingRepoRevokeRequest,
)
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "vscode-coding-agent-contract-0.1"

router = APIRouter(prefix="/coding", tags=["coding"])


def _new_request_id(prefix: str = "coding") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _envelope(*, result_type: str, data: Any) -> dict[str, Any]:
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[
            "VS Code coding bridge is local-only and governed by approval mode; mutation/check routes require explicit operator approval."
        ],
        errors=[],
        trace_summary=TraceSummary(
            route_used=f"coding.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    )
    return envelope.to_payload()


@router.get("/status")
async def get_coding_status() -> dict[str, Any]:
    status = build_coding_status()
    return _envelope(result_type="coding_status", data={"coding_bridge": status.to_payload()})


@router.get("/developer-profile")
async def get_developer_profile() -> dict[str, Any]:
    return _envelope(
        result_type="codev_developer_profile",
        data={"developer_profile": build_codev_developer_profile_status()},
    )


@router.post("/session/start")
async def post_coding_session_start(
    payload: CodingSessionStartRequest = Body(...),
) -> dict[str, Any]:
    session = start_coding_session(payload)
    return _envelope(result_type="coding_session", data={"session": session.to_payload()})


@router.post("/chat")
async def post_coding_chat(payload: CodingChatRequest = Body(...)) -> dict[str, Any]:
    result = handle_coding_chat(payload)
    return _envelope(result_type="coding_chat", data={"coding_chat": result.to_payload()})


@router.post("/repo/inspect-preview")
async def post_repo_inspect_preview(
    payload: RepoInspectPreviewRequest = Body(...),
) -> dict[str, Any]:
    result = inspect_repo_preview(payload)
    return _envelope(result_type="repo_inspect_preview", data={"repo_preview": result.to_payload()})


@router.post("/repo/approval-status")
async def post_repo_approval_status(payload: CodingRepoApprovalStatusRequest = Body(...)) -> dict[str, Any]:
    result = repo_approval_status(payload)
    return _envelope(result_type="repo_approval_status", data={"repo_approval": result.to_payload()})


@router.post("/repo/approval-plan")
async def post_repo_approval_plan(payload: CodingRepoApprovalPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_repo_approval(payload)
    return _envelope(result_type="repo_approval_plan", data={"repo_approval_plan": result.to_payload()})


@router.post("/repo/approval-apply")
async def post_repo_approval_apply(payload: CodingRepoApprovalApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_repo_approval(payload)
    return _envelope(result_type="repo_approval_apply", data={"repo_approval_result": result.to_payload()})


@router.post("/repo/revoke")
async def post_repo_revoke(payload: CodingRepoRevokeRequest = Body(...)) -> dict[str, Any]:
    result = revoke_repo(payload)
    return _envelope(result_type="repo_revoke", data={"repo_approval_result": result.to_payload()})


__all__ = ("router",)
