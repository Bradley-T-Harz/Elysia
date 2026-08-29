"""Routes for the live bounded command catalog, plans, and exact execution truth."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_command_plan_service import plan_command
from app.api.coding_command_allowlist_service import public_command_catalog
from app.api.coding_process_service import cancel_command, get_command_status, run_approved_command
from app.api.schemas.coding_commands import (
    CodingCommandCancelRequest,
    CodingCommandPlanRequest,
    CodingCommandRunApprovedRequest,
)
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "vscode-coding-agent-contract-0.1"

router = APIRouter(prefix="/coding/command", tags=["coding"])


def _new_request_id(prefix: str = "coding_command") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _envelope(
    result_type: str,
    data: dict[str, Any],
    *,
    approval_state: ApprovalState = ApprovalState.NEEDED,
) -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=["Command execution is exact-allowlist only and requires the matching approval mode plus explicit operator approval."],
        errors=[],
        trace_summary=TraceSummary(
            route_used=f"coding.command.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    ).to_payload()


@router.post("/plan")
async def post_command_plan(payload: CodingCommandPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_command(payload)
    return _envelope("command_plan", {"command_plan": result.to_payload()})


@router.get("/catalog")
async def get_command_catalog() -> dict[str, Any]:
    return _envelope(
        "command_catalog",
        {"command_catalog": public_command_catalog()},
        approval_state=ApprovalState.NOT_NEEDED,
    )


@router.post("/run-approved")
async def post_command_run_approved(
    payload: CodingCommandRunApprovedRequest = Body(...),
) -> dict[str, Any]:
    result = run_approved_command(payload)
    return _envelope(
        "command_run",
        {"command_run": result.to_payload()},
        approval_state=(
            ApprovalState.APPROVED if result.execution_performed else ApprovalState.NEEDED
        ),
    )


@router.get("/status/{run_id}")
async def get_command_run_status(run_id: str) -> dict[str, Any]:
    result = get_command_status(run_id)
    return _envelope(
        "command_status",
        {"command_status": result.to_payload()},
        approval_state=ApprovalState.NOT_NEEDED,
    )


@router.post("/cancel")
async def post_command_cancel(payload: CodingCommandCancelRequest = Body(...)) -> dict[str, Any]:
    result = cancel_command(payload)
    return _envelope(
        "command_cancel",
        {"command_cancel": result.to_payload()},
        approval_state=ApprovalState.NOT_NEEDED,
    )


__all__ = ("router",)
