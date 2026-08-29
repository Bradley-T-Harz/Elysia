"""Routes for preview-only file operation plans."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_file_operation_service import execute_file_operation, plan_file_operation
from app.api.schemas.coding_file_operations import CodingFileOperationExecuteRequest, CodingFileOperationPlanRequest
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "vscode-coding-agent-contract-0.1"

router = APIRouter(prefix="/coding/file", tags=["coding"])


def _new_request_id(prefix: str = "coding_file_plan") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


@router.post("/operation-plan")
async def post_file_operation_plan(
    payload: CodingFileOperationPlanRequest = Body(...),
) -> dict[str, Any]:
    result = plan_file_operation(payload)
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="file_operation_plan",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NEEDED,
        warnings=["File operation plans are preview-only and do not mutate files."],
        errors=[],
        trace_summary=TraceSummary(
            route_used="coding.file.operation_plan",
            log_written=False,
            journal_written=False,
        ),
        data={"file_operation_plan": result.to_payload()},
    )
    return envelope.to_payload()


@router.post("/operation-execute-approved")
async def post_file_operation_execute_approved(
    payload: CodingFileOperationExecuteRequest = Body(...),
) -> dict[str, Any]:
    result = execute_file_operation(payload)
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="file_operation_execute_approved",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.APPROVED if result.mutation_performed else ApprovalState.NEEDED,
        warnings=["File operation execution is workspace-scoped, text-only, and approval-gated."],
        errors=[],
        trace_summary=TraceSummary(
            route_used="coding.file.operation_execute_approved",
            log_written=result.audit_written,
            journal_written=False,
        ),
        data={"file_operation_result": result.to_payload()},
    )
    return envelope.to_payload()


__all__ = ("router",)
