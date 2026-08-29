"""Routes for bounded, checkpoint-only Developer Lab coding tasks."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_task_service import advance_coding_task, approve_coding_task, plan_coding_task, stop_coding_task
from app.api.schemas.coding_tasks import CodingTaskApproveRequest, CodingTaskCheckpointRequest, CodingTaskPlanRequest, CodingTaskStopRequest
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "coding-task-lab-1.0"

router = APIRouter(prefix="/coding/task", tags=["coding"])


def _envelope(result_type: str, data: dict[str, Any], *, approval_state: ApprovalState) -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=f"coding_task_{uuid4().hex[:16]}",
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.PLANNED,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=["Developer Lab tasks are checkpoint-only; no autonomous or background execution is enabled."],
        errors=[],
        trace_summary=TraceSummary(route_used=f"coding.task.{result_type}", log_written=result_type != "plan", journal_written=False),
        data=data,
    ).to_payload()


@router.post("/plan")
async def post_task_plan(payload: CodingTaskPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_coding_task(payload)
    return _envelope("task_plan", {"task_plan": result.to_payload()}, approval_state=ApprovalState.NEEDED)


@router.post("/approve")
async def post_task_approve(payload: CodingTaskApproveRequest = Body(...)) -> dict[str, Any]:
    result = approve_coding_task(payload)
    state = ApprovalState.APPROVED if result.status == "approved_checkpoint_only" else ApprovalState.NEEDED
    return _envelope("task_approval", {"task_approval": result.to_payload()}, approval_state=state)


@router.post("/next")
async def post_task_next(payload: CodingTaskCheckpointRequest = Body(...)) -> dict[str, Any]:
    result = advance_coding_task(payload)
    return _envelope("task_checkpoint", {"task_checkpoint": result.to_payload()}, approval_state=ApprovalState.APPROVED if result.status == "checkpoint_ready" else ApprovalState.NEEDED)


@router.post("/stop")
async def post_task_stop(payload: CodingTaskStopRequest = Body(...)) -> dict[str, Any]:
    result = stop_coding_task(payload)
    return _envelope("task_stop", {"task_checkpoint": result.to_payload()}, approval_state=ApprovalState.APPROVED)


__all__ = ("router",)
