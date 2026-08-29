"""Routes for approved, bounded selected-file previews."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_file_service import read_selected_file_preview
from app.api.schemas.coding_files import CodingFileReadPreviewRequest
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "vscode-coding-agent-contract-0.1"

router = APIRouter(prefix="/coding/file", tags=["coding"])


def _new_request_id(prefix: str = "coding_file") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _envelope(*, result_type: str, data: Any, approval_state: ApprovalState) -> dict[str, Any]:
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=["Selected-file preview is bounded, local, explicit-approval only, and may redact secrets."],
        errors=[],
        trace_summary=TraceSummary(
            route_used=f"coding.file.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    )
    return envelope.to_payload()


@router.post("/read-preview")
async def post_file_read_preview(
    payload: CodingFileReadPreviewRequest = Body(...),
) -> dict[str, Any]:
    result = read_selected_file_preview(payload)
    approval_state = (
        ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED
    )
    return _envelope(
        result_type="file_read_preview",
        data={"file_preview": result.to_payload()},
        approval_state=approval_state,
    )


__all__ = ("router",)
