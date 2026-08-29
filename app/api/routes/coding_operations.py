"""Routes for coding operation approval/result records."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Query

from app.api.coding_audit_service import get_coding_audit_record, list_coding_audit_records
from app.api.coding_operation_service import approve_operation, record_operation_result
from app.api.schemas.coding_operations import CodingOperationApproveRequest, CodingOperationResultRequest
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "vscode-coding-agent-contract-0.1"

router = APIRouter(prefix="/coding/operation", tags=["coding"])


def _new_request_id(prefix: str = "coding_operation") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _envelope(result_type: str, approval_state: ApprovalState, data: dict[str, Any]) -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=["Operation endpoints record approval/result truth; they do not grant broad execution authority."],
        errors=[],
        trace_summary=TraceSummary(
            route_used=f"coding.operation.{result_type}",
            log_written=True,
            journal_written=False,
        ),
        data=data,
    ).to_payload()


@router.post("/approve")
async def post_operation_approve(payload: CodingOperationApproveRequest = Body(...)) -> dict[str, Any]:
    result = approve_operation(payload)
    state = ApprovalState.APPROVED if result.status == "approved" else ApprovalState.NEEDED
    return _envelope("operation_approval", state, {"operation_approval": result.to_payload()})


@router.post("/result")
async def post_operation_result(payload: CodingOperationResultRequest = Body(...)) -> dict[str, Any]:
    result = record_operation_result(payload)
    state = ApprovalState.APPROVED if result.status != "denied" else ApprovalState.DENIED
    return _envelope("operation_result", state, {"operation_result": result.to_payload()})


@router.get("/audit")
async def get_operation_audit_list(
    limit: int = Query(default=50, ge=1, le=200),
    kind: str | None = Query(default=None),
) -> dict[str, Any]:
    records = list_coding_audit_records(limit=limit, kind=kind)
    return _envelope("operation_audit_list", ApprovalState.NOT_NEEDED, {"operation_audits": records, "count": len(records)})


@router.get("/audit/{operation_id}")
async def get_operation_audit_detail(operation_id: str) -> dict[str, Any]:
    record = get_coding_audit_record(operation_id)
    state = ApprovalState.NOT_NEEDED if record else ApprovalState.UNKNOWN
    return _envelope("operation_audit_detail", state, {"operation_audit": record, "found": record is not None})


__all__ = ("router",)
