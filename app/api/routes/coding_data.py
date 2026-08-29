"""Routes for governed science/data stewardship."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_data_adapter_service import inspect_data_path, preview_data_path
from app.api.coding_data_edit_service import apply_data_edit, plan_data_edit
from app.api.coding_data_export_service import apply_data_export, plan_data_export
from app.api.coding_data_type_registry import data_registry_payload, detect_data_type
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.schemas.coding_data import (
    CodingDataApplyRequest,
    CodingDataEditPlanRequest,
    CodingDataExportApplyRequest,
    CodingDataExportPlanRequest,
    CodingDataPathRequest,
)
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "coding-data-0.1"

router = APIRouter(prefix="/coding", tags=["coding"])


def _new_request_id(prefix: str = "coding_data") -> str:
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
        warnings=["Science/data stewardship is local, bounded, path-guarded, approval-gated, and audit-oriented."],
        errors=[],
        trace_summary=TraceSummary(route_used=f"coding.data.{result_type}", log_written=False, journal_written=False),
        data=data,
    )
    return envelope.to_payload()


def _data_response(payload: CodingDataPathRequest, *, preview: bool) -> dict[str, Any]:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=True)
    descriptor = detect_data_type(guarded.target_path if guarded.target_path else Path(payload.file_path))
    if not guarded.allowed:
        data = {
            "status": "blocked",
            "file_label": guarded.target_path.name if guarded.target_path else Path(payload.file_path).name,
            "relative_path": guarded.relative_path,
            "path_hash": hash_path(payload.file_path),
            "blocked_reason": guarded.reason,
            "descriptor": descriptor.to_payload(),
            "warnings": list(descriptor.notes),
        }
        return data
    if descriptor.database or descriptor.adapter == "databaseforge":
        return {
            "status": "blocked",
            "file_label": guarded.target_path.name,
            "relative_path": guarded.relative_path,
            "path_hash": hash_path(guarded.target_path),
            "blocked_reason": "database_requires_databaseforge_schema_only_route",
            "descriptor": descriptor.to_payload(),
            "warnings": ["Database rows, export, and mutation are unavailable. Use DatabaseForge metadata or exact-approved snapshot-first schema preview."],
        }
    if not payload.approval_granted:
        return {
            "status": "approval_required",
            "file_label": guarded.target_path.name,
            "relative_path": guarded.relative_path,
            "path_hash": hash_path(guarded.target_path),
            "blocked_reason": "explicit_approval_required",
            "descriptor": descriptor.to_payload(),
            "warnings": ["Data inspection/preview requires explicit operator approval."],
        }
    result = (preview_data_path if preview else inspect_data_path)(
        guarded.target_path,
        max_rows=payload.max_rows or descriptor.max_preview_rows,
        max_features=payload.max_features or descriptor.max_preview_features,
        max_values=payload.max_values or descriptor.max_sample_values,
    )
    return result.to_payload(file_label=guarded.target_path.name, relative_path=guarded.relative_path, path_hash=hash_path(guarded.target_path))


@router.get("/data-types")
async def get_data_types() -> dict[str, Any]:
    return _envelope("data_types", {"data_types": data_registry_payload()})


@router.post("/data/inspect")
async def post_data_inspect(payload: CodingDataPathRequest = Body(...)) -> dict[str, Any]:
    return _envelope("data_inspect", {"data": _data_response(payload, preview=False)}, approval_state=ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED)


@router.post("/data/preview")
async def post_data_preview(payload: CodingDataPathRequest = Body(...)) -> dict[str, Any]:
    return _envelope("data_preview", {"data": _data_response(payload, preview=True)}, approval_state=ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED)


@router.post("/data/export-plan")
async def post_data_export_plan(payload: CodingDataExportPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_data_export(payload)
    return _envelope("data_export_plan", {"data_export_plan": result.to_payload()}, approval_state=ApprovalState.NEEDED)


@router.post("/data/apply-approved")
async def post_data_apply_approved(payload: CodingDataApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_data_edit(payload)
    return _envelope("data_apply_result", {"data_apply_result": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.operator_approved else ApprovalState.NEEDED)


@router.post("/data/export-approved")
async def post_data_export_approved(payload: CodingDataExportApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_data_export(payload)
    return _envelope("data_export_result", {"data_export_result": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.operator_approved else ApprovalState.NEEDED)


@router.post("/data/edit-plan")
async def post_data_edit_plan(payload: CodingDataEditPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_data_edit(payload)
    return _envelope("data_edit_plan", {"data_edit_plan": result.to_payload()}, approval_state=ApprovalState.NEEDED)


@router.post("/data/mutation-plan")
async def post_data_mutation_plan(payload: CodingDataEditPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_data_edit(payload)
    return _envelope("data_mutation_plan", {"data_mutation_plan": result.to_payload()}, approval_state=ApprovalState.NEEDED)


@router.post("/data/apply-mutation-approved")
async def post_data_apply_mutation_approved(payload: CodingDataApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_data_edit(payload)
    return _envelope("data_mutation_result", {"data_mutation_result": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.operator_approved else ApprovalState.NEEDED)


__all__ = ("router",)
