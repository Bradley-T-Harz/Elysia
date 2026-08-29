"""Routes for Codev file type registry and inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_file_adapter_service import capability_flags, risk_flags
from app.api.coding_file_type_registry import detect_file_type, registry_payload
from app.api.coding_path_guard_service import guard_workspace_path
from app.api.schemas.coding_file_types import (
    CodingFileCapabilityFlags,
    CodingFileRiskFlags,
    CodingFileTypeDescriptorResponse,
    CodingFileTypeInspectRequest,
    CodingFileTypeInspectResponse,
)
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "coding-file-types-0.1"

router = APIRouter(prefix="/coding", tags=["coding"])


def _new_request_id(prefix: str = "coding_file_types") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _descriptor_response(descriptor) -> CodingFileTypeDescriptorResponse:
    return CodingFileTypeDescriptorResponse(
        type_id=descriptor.type_id,
        label=descriptor.label,
        category=descriptor.category,
        adapter=descriptor.adapter,
        language_id=descriptor.language_id,
        capabilities=CodingFileCapabilityFlags(**capability_flags(descriptor)),
        risk_flags=CodingFileRiskFlags(**risk_flags(descriptor)),
        max_preview_bytes=descriptor.max_preview_bytes,
        max_patch_bytes=descriptor.max_patch_bytes,
        notes=list(descriptor.notes),
    )


def _envelope(result_type: str, data: dict[str, Any]) -> dict[str, Any]:
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=["File type registry is local policy metadata and does not read private file contents."],
        errors=[],
        trace_summary=TraceSummary(route_used=f"coding.{result_type}", log_written=False, journal_written=False),
        data=data,
    )
    return envelope.to_payload()


@router.get("/file-types")
async def get_file_types() -> dict[str, Any]:
    return _envelope("file_types", {"file_types": registry_payload()})


@router.post("/file/inspect-type")
async def post_file_inspect_type(
    payload: CodingFileTypeInspectRequest = Body(...),
) -> dict[str, Any]:
    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.file_path,
        require_existing=False,
        allow_directory=False,
    )
    target = guarded.target_path if guarded.target_path else Path(payload.file_path)
    raw = target.read_bytes()[:4096] if target.exists() and target.is_file() and guarded.allowed else None
    descriptor = detect_file_type(target, raw)
    result = CodingFileTypeInspectResponse(
        status="completed" if guarded.allowed else "blocked",
        relative_path=guarded.relative_path,
        descriptor=_descriptor_response(descriptor),
        blocked_reason=guarded.reason,
    )
    return _envelope("file_inspect_type", {"file_type_inspection": result.to_payload()})


__all__ = ("router",)
