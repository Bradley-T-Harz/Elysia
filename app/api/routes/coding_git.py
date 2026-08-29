"""Routes for read-only git preview."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_git_service import preview_git_state
from app.api.schemas.coding_git import CodingGitPreviewRequest
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "vscode-coding-agent-contract-0.1"

router = APIRouter(prefix="/coding/git", tags=["coding"])


def _new_request_id(prefix: str = "coding_git") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


@router.post("/preview")
async def post_git_preview(payload: CodingGitPreviewRequest = Body(...)) -> dict[str, Any]:
    result = preview_git_state(payload)
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="git_preview",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=["Git truth uses fixed read-only argv with shell=False and grants no Git mutation authority."],
        errors=[],
        trace_summary=TraceSummary(
            route_used="coding.git.preview",
            log_written=False,
            journal_written=False,
        ),
        data={"git_preview": result.to_payload()},
    )
    return envelope.to_payload()


__all__ = ("router",)
