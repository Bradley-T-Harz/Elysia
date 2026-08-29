"""Routes for non-mutating coding patch proposals."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_patch_service import apply_patch_with_approval, propose_patch
from app.api.schemas.coding_patch import CodingPatchApplyRequest, CodingPatchProposeRequest
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "vscode-coding-agent-contract-0.1"

router = APIRouter(prefix="/coding/patch", tags=["coding"])


def _new_request_id(prefix: str = "coding_patch") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


@router.post("/propose")
async def post_patch_propose(
    payload: CodingPatchProposeRequest = Body(...),
) -> dict[str, Any]:
    result = propose_patch(payload)
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="patch_proposal",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=["Patch proposal is preview-only and never applies files."],
        errors=[],
        trace_summary=TraceSummary(
            route_used="coding.patch.propose",
            log_written=False,
            journal_written=False,
        ),
        data={"patch_proposal": result.to_payload()},
    )
    return envelope.to_payload()


@router.post("/apply-approved")
async def post_patch_apply_approved(
    payload: CodingPatchApplyRequest = Body(...),
) -> dict[str, Any]:
    result = apply_patch_with_approval(payload)
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="patch_apply_approved",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.APPROVED if result.mutation_performed else ApprovalState.NEEDED,
        warnings=["Patch apply is workspace-scoped, text-only, hash-checked, and approval-gated."],
        errors=[],
        trace_summary=TraceSummary(
            route_used="coding.patch.apply_approved",
            log_written=result.audit_written,
            journal_written=False,
        ),
        data={"patch_apply": result.to_payload()},
    )
    return envelope.to_payload()


__all__ = ("router",)
