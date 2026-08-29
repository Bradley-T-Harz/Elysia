"""Routes for governed visual stewardship."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_image_edit_service import apply_visual_edit, plan_visual_edit
from app.api.coding_ocr_service import ocr_health, run_local_ocr
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_visual_adapter_service import inspect_visual_path, preview_visual_path
from app.api.coding_visual_analysis_service import analyze_visual
from app.api.coding_visual_export_service import apply_visual_export, plan_visual_export
from app.api.coding_visual_model_service import semantic_vision_health
from app.api.coding_visual_type_registry import detect_visual_type, visual_registry_payload
from app.api.schemas.coding_visual import (
    CodingVisualAnalysisRequest,
    CodingVisualApplyRequest,
    CodingVisualEditPlanRequest,
    CodingVisualExportApplyRequest,
    CodingVisualExportPlanRequest,
    CodingVisualOcrRequest,
    CodingVisualPathRequest,
)
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "coding-visual-0.1"

router = APIRouter(prefix="/coding", tags=["coding"])


def _new_request_id(prefix: str = "coding_visual") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _envelope(result_type: str, data: dict[str, Any], *, approval_state: ApprovalState = ApprovalState.NOT_NEEDED) -> dict[str, Any]:
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=["Visual stewardship is local, bounded, privacy-aware, path-guarded, approval-gated, and audit-oriented."],
        errors=[],
        trace_summary=TraceSummary(route_used=f"coding.visual.{result_type}", log_written=False, journal_written=False),
        data=data,
    )
    return envelope.to_payload()


def _visual_response(payload: CodingVisualPathRequest, *, preview: bool) -> dict[str, Any]:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=False)
    descriptor = detect_visual_type(guarded.target_path if guarded.target_path else Path(payload.file_path))
    if not guarded.allowed:
        return {
            "status": "blocked",
            "file_label": guarded.target_path.name if guarded.target_path else Path(payload.file_path).name,
            "relative_path": guarded.relative_path,
            "path_hash": hash_path(payload.file_path),
            "blocked_reason": guarded.reason,
            "descriptor": descriptor.to_payload(),
            "warnings": list(descriptor.notes),
        }
    if not payload.approval_granted:
        return {
            "status": "approval_required",
            "file_label": guarded.target_path.name,
            "relative_path": guarded.relative_path,
            "path_hash": hash_path(guarded.target_path),
            "blocked_reason": "explicit_approval_required",
            "descriptor": descriptor.to_payload(),
            "warnings": ["Visual inspection/preview requires explicit operator approval."],
        }
    result = (preview_visual_path if preview else inspect_visual_path)(guarded.target_path)
    return {
        "file_label": guarded.target_path.name,
        "relative_path": guarded.relative_path,
        "path_hash": hash_path(guarded.target_path),
        **result,
    }


@router.get("/visual-types")
async def get_visual_types() -> dict[str, Any]:
    return _envelope("visual_types", {"visual_types": visual_registry_payload(), "ocr_health": ocr_health(), "semantic_vision_health": semantic_vision_health()})


@router.post("/visual/inspect")
async def post_visual_inspect(payload: CodingVisualPathRequest = Body(...)) -> dict[str, Any]:
    return _envelope("visual_inspect", {"visual": _visual_response(payload, preview=False)}, approval_state=ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED)


@router.post("/visual/preview")
async def post_visual_preview(payload: CodingVisualPathRequest = Body(...)) -> dict[str, Any]:
    return _envelope("visual_preview", {"visual": _visual_response(payload, preview=True)}, approval_state=ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED)


@router.post("/visual/ocr")
async def post_visual_ocr(payload: CodingVisualOcrRequest = Body(...)) -> dict[str, Any]:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=False)
    if not guarded.allowed:
        result = {"status": "blocked", "blocked_reason": guarded.reason, "path_hash": hash_path(payload.file_path)}
    elif not payload.approval_granted:
        result = {"status": "approval_required", "blocked_reason": "explicit_approval_required", "warnings": ["OCR requires explicit operator approval."]}
    else:
        result = run_local_ocr(guarded.target_path, max_chars=payload.max_chars)
    return _envelope("visual_ocr", {"ocr": result}, approval_state=ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED)


@router.post("/visual/analysis")
async def post_visual_analysis(payload: CodingVisualAnalysisRequest = Body(...)) -> dict[str, Any]:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=False)
    if not guarded.allowed:
        result = {"status": "blocked", "blocked_reason": guarded.reason, "path_hash": hash_path(payload.file_path)}
    elif not payload.approval_granted:
        result = {"status": "approval_required", "blocked_reason": "explicit_approval_required", "warnings": ["Visual analysis requires explicit operator approval."]}
    else:
        result = analyze_visual(guarded.target_path, include_semantic_provider=payload.include_semantic_provider)
    return _envelope("visual_analysis", {"analysis": result}, approval_state=ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED)


@router.post("/visual/export-plan")
async def post_visual_export_plan(payload: CodingVisualExportPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_visual_export(payload)
    return _envelope("visual_export_plan", {"visual_export_plan": result.to_payload()}, approval_state=ApprovalState.NEEDED)


@router.post("/visual/export-approved")
async def post_visual_export_approved(payload: CodingVisualExportApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_visual_export(payload)
    return _envelope("visual_export_result", {"visual_export_result": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.operator_approved else ApprovalState.NEEDED)


@router.post("/visual/edit-plan")
async def post_visual_edit_plan(payload: CodingVisualEditPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_visual_edit(payload)
    return _envelope("visual_edit_plan", {"visual_edit_plan": result.to_payload()}, approval_state=ApprovalState.NEEDED)


@router.post("/visual/apply-approved")
async def post_visual_apply_approved(payload: CodingVisualApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_visual_edit(payload)
    return _envelope("visual_apply_result", {"visual_apply_result": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.operator_approved else ApprovalState.NEEDED)


__all__ = ("router",)
