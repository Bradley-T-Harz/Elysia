"""Routes for EngineeringForge static stewardship and local previews."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_engineering_artifact_service import get_engineering_artifact
from app.api.coding_engineering_job_service import cancel_engineering_job, get_engineering_job
from app.api.coding_engineering_policy_service import (
    load_cam_gcode_safety,
    load_engineering_conversion_limits,
    load_engineering_inspection_limits,
    load_engineering_preview_limits,
    load_robot_model_safety,
)
from app.api.coding_engineering_service import apply_engineering_preview, inspect_engineering, plan_engineering_preview
from app.api.coding_engineering_type_registry import engineering_registry_payload
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.engineering import EngineeringInspectRequest, EngineeringPreviewApplyRequest, EngineeringPreviewPlanRequest
from app.api.schemas.envelope import TraceSummary, build_response_envelope


router = APIRouter(prefix="/coding/engineering", tags=["coding", "engineering"])


def _envelope(
    result_type: str,
    data: dict[str, Any],
    approval_state: ApprovalState,
    *,
    request_id: str | None = None,
    log_written: bool = False,
) -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id or f"req_engineering_{uuid4().hex[:16]}",
        api_version="1.0.0",
        contract_version="engineeringforge-0.1",
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=[
            "EngineeringForge is local, path-guarded, read-only for sources, and descriptive rather than certifying.",
            "Physical output, machine send, robot control, script/plugin execution, cloud translation/upload, and source overwrite are unavailable by design.",
        ],
        errors=[],
        trace_summary=TraceSummary(route_used=f"coding.engineering.{result_type}", log_written=log_written, journal_written=False),
        data=data,
    ).to_payload()


@router.get("/types")
async def get_engineering_types() -> dict[str, Any]:
    return _envelope(
        "engineering_types",
        {
            "engineering_types": engineering_registry_payload(),
            "inspection_policy": load_engineering_inspection_limits(),
            "preview_policy": load_engineering_preview_limits(),
            "conversion_policy": load_engineering_conversion_limits(),
            "robot_model_safety": load_robot_model_safety(),
            "cam_gcode_safety": load_cam_gcode_safety(),
        },
        ApprovalState.NOT_NEEDED,
    )


@router.post("/inspect")
def post_engineering_inspect(payload: EngineeringInspectRequest = Body(...)) -> dict[str, Any]:
    result = inspect_engineering(payload)
    state = ApprovalState.APPROVED if result.status == "completed" else ApprovalState.NEEDED if result.status == "approval_required" else ApprovalState.DENIED
    return _envelope("engineering_inspect", {"engineering": result.to_payload()}, state, request_id=result.request_id, log_written=result.audit_written)


@router.post("/preview/plan")
def post_engineering_preview_plan(payload: EngineeringPreviewPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_engineering_preview(payload)
    state = ApprovalState.NEEDED if result.status in {"planned", "approval_required"} else ApprovalState.DENIED
    return _envelope("engineering_preview_plan", {"engineering_preview_plan": result.to_payload()}, state, request_id=result.request_id, log_written=True)


@router.post("/preview/apply")
def post_engineering_preview_apply(payload: EngineeringPreviewApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_engineering_preview(payload)
    state = ApprovalState.APPROVED if result.status == "completed" else ApprovalState.NEEDED if result.status == "approval_required" else ApprovalState.DENIED
    return _envelope("engineering_preview_result", {"engineering_preview_result": result.to_payload()}, state, request_id=result.request_id, log_written=result.audit_written)


@router.get("/jobs/{operation_id}")
async def get_engineering_job_state(operation_id: str) -> dict[str, Any]:
    job = get_engineering_job(operation_id)
    return _envelope("engineering_job", {"engineering_job": job.to_payload() if job else None, "found": job is not None}, ApprovalState.NOT_NEEDED)


@router.post("/jobs/{operation_id}/cancel")
async def post_engineering_job_cancel(operation_id: str) -> dict[str, Any]:
    job = cancel_engineering_job(operation_id)
    return _envelope("engineering_job_cancel", {"engineering_job": job.to_payload() if job else None, "found": job is not None}, ApprovalState.APPROVED if job else ApprovalState.UNKNOWN)


@router.get("/artifacts/{artifact_id}")
async def get_engineering_artifact_detail(artifact_id: str) -> dict[str, Any]:
    artifact = get_engineering_artifact(artifact_id)
    return _envelope("engineering_artifact", {"engineering_artifact": artifact, "found": artifact is not None}, ApprovalState.NOT_NEEDED)


__all__ = ("router",)
