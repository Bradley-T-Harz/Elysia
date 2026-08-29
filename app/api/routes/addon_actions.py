"""Preview-only add-on action plan routes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api import addon_action_plan_service
from app.api.schemas.addon_actions import AddonActionPlanRequest
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "addon-action-plan-contract-0.1"

router = APIRouter(prefix="/addon-actions", tags=["addon-actions"])


def _new_request_id(prefix: str = "addon_action") -> str:
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
            "Add-on action planning is preview-only. No command, package manager, worker, shell, subprocess, or file mutation is executed."
        ],
        errors=[],
        trace_summary=TraceSummary(
            route_used=f"addon_actions.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    )
    return envelope.to_payload()


@router.post("/plan")
async def plan_addon_action(payload: AddonActionPlanRequest = Body(...)) -> dict[str, Any]:
    plan = addon_action_plan_service.build_addon_action_plan(payload)
    return _envelope(result_type="addon_action_plan", data={"addon_action_plan": plan.to_payload()})


__all__ = ("router",)
