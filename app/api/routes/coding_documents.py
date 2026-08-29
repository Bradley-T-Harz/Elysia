"""Routes for governed Codev document stewardship."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_document_adapter_service import extract_document_preview, inspect_document
from app.api.coding_document_edit_service import apply_document_edit, plan_document_edit
from app.api.coding_document_export_service import apply_document_export, plan_document_export
from app.api.coding_document_type_registry import detect_document_type, document_registry_payload
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.schemas.coding_documents import (
    CodingDocumentDescriptorResponse,
    CodingDocumentEditApplyRequest,
    CodingDocumentEditPlanRequest,
    CodingDocumentExportApplyRequest,
    CodingDocumentExportPlanRequest,
    CodingDocumentPathRequest,
    CodingDocumentPreviewResponse,
)
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "coding-documents-0.1"

router = APIRouter(prefix="/coding", tags=["coding"])


def _new_request_id(prefix: str = "coding_documents") -> str:
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
        warnings=["Document stewardship is bounded, local, macro-safe, and preview/audit oriented."],
        errors=[],
        trace_summary=TraceSummary(route_used=f"coding.document.{result_type}", log_written=False, journal_written=False),
        data=data,
    )
    return envelope.to_payload()


def _descriptor_response(descriptor) -> CodingDocumentDescriptorResponse:
    return CodingDocumentDescriptorResponse(
        type_id=descriptor.type_id,
        label=descriptor.label,
        extension=descriptor.extension,
        family=descriptor.family,
        adapter=descriptor.adapter,
        readable=descriptor.readable,
        extractable=descriptor.extractable,
        exportable=descriptor.exportable,
        editable=descriptor.editable,
        stable_edit_operations=list(descriptor.stable_edit_operations),
        risk_flags={
            "macro_risk": descriptor.macro_risk,
            "legacy_risk": descriptor.legacy_risk,
            "formula_risk": descriptor.formula_risk,
            "embedded_content_risk": descriptor.embedded_content_risk,
        },
        notes=list(descriptor.notes),
    )


def _preview_response(payload: CodingDocumentPathRequest, *, inspect_only: bool = False) -> CodingDocumentPreviewResponse:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path)
    descriptor = detect_document_type(guarded.target_path if guarded.target_path else Path(payload.file_path))
    if not guarded.allowed:
        return CodingDocumentPreviewResponse(
            status="blocked",
            file_label=guarded.target_path.name if guarded.target_path else Path(payload.file_path).name,
            relative_path=guarded.relative_path,
            path_hash=hash_path(payload.file_path),
            blocked_reason=guarded.reason,
            descriptor=_descriptor_response(descriptor),
            warnings=list(descriptor.notes),
        )
    if not payload.approval_granted:
        return CodingDocumentPreviewResponse(
            status="approval_required",
            file_label=guarded.target_path.name,
            relative_path=guarded.relative_path,
            path_hash=hash_path(guarded.target_path),
            blocked_reason="explicit_approval_required",
            descriptor=_descriptor_response(descriptor),
            warnings=["Document inspection/extraction requires explicit operator approval."],
        )
    preview = inspect_document(guarded.target_path) if inspect_only else extract_document_preview(
        guarded.target_path,
        max_chars=payload.max_chars or 12000,
        max_tables=payload.max_tables or 8,
        max_rows=payload.max_rows or 20,
    )
    return CodingDocumentPreviewResponse(
        status=preview.status,
        file_label=guarded.target_path.name,
        relative_path=guarded.relative_path,
        path_hash=hash_path(guarded.target_path),
        blocked_reason=preview.blocked_reason,
        descriptor=_descriptor_response(preview.descriptor),
        safety=preview.safety.to_payload(),
        metadata=preview.metadata,
        text_preview=preview.text_preview,
        tables=preview.tables,
        outline=preview.outline,
        provenance=preview.provenance,
        warnings=preview.warnings,
        redactions=preview.redactions,
        secret_scan_findings=preview.secret_scan_findings,
    )


@router.get("/document-types")
async def get_document_types() -> dict[str, Any]:
    return _envelope("document_types", {"document_types": document_registry_payload()})


@router.post("/document/inspect")
async def post_document_inspect(payload: CodingDocumentPathRequest = Body(...)) -> dict[str, Any]:
    result = _preview_response(payload, inspect_only=True)
    return _envelope("document_inspect", {"document": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED)


@router.post("/document/extract-preview")
async def post_document_extract_preview(payload: CodingDocumentPathRequest = Body(...)) -> dict[str, Any]:
    result = _preview_response(payload, inspect_only=False)
    return _envelope("document_extract_preview", {"document": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.approval_granted else ApprovalState.NEEDED)


@router.post("/document/export-plan")
async def post_document_export_plan(payload: CodingDocumentExportPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_document_export(payload)
    return _envelope("document_export_plan", {"document_export_plan": result.to_payload()}, approval_state=ApprovalState.NEEDED)


@router.post("/document/export-approved")
async def post_document_export_approved(payload: CodingDocumentExportApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_document_export(payload)
    return _envelope("document_export_approved", {"document_export_result": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.operator_approved else ApprovalState.NEEDED)


@router.post("/document/edit-plan")
async def post_document_edit_plan(payload: CodingDocumentEditPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_document_edit(payload)
    return _envelope("document_edit_plan", {"document_edit_plan": result.to_payload()}, approval_state=ApprovalState.NEEDED)


@router.post("/document/apply-approved")
async def post_document_apply_approved(payload: CodingDocumentEditApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_document_edit(payload)
    return _envelope("document_apply_approved", {"document_edit_result": result.to_payload()}, approval_state=ApprovalState.APPROVED if payload.operator_approved else ApprovalState.NEEDED)


__all__ = ("router",)
