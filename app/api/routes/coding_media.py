"""Routes for governed, metadata-only local media stewardship."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_media_adapter_service import media_dependency_health
from app.api.coding_media_service import inspect_governed_media, thumbnail_governed_media
from app.api.coding_media_type_registry import media_registry_payload
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.media import CodingMediaInspectResult, CodingMediaPathRequest


API_VERSION = "1.0.0"
CONTRACT_VERSION = "coding-media-0.1"

router = APIRouter(prefix="/coding", tags=["coding"])


def _new_request_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _envelope(result_type: str, result: CodingMediaInspectResult) -> dict[str, Any]:
    if result.status == "approval_required":
        approval_state = ApprovalState.NEEDED
    elif result.status == "completed":
        approval_state = ApprovalState.APPROVED
    else:
        approval_state = ApprovalState.DENIED
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=result.request_id or "req_coding_media_unavailable",
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=[
            "Media stewardship is local, read-only, bounded, path-guarded, and explicit-approval only.",
            "Governed STT and non-cloning TTS use separate exact-approved local worker routes; media mutation and transcoding remain unavailable.",
        ],
        errors=[],
        trace_summary=TraceSummary(
            route_used=f"coding.media.{result_type}",
            log_written=result.audit_written,
            journal_written=False,
        ),
        data={"media": result.to_payload(exclude_none=False)},
    )
    return envelope.to_payload()


@router.get("/media-types")
async def get_media_types() -> dict[str, Any]:
    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id("req_coding_media_types"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="media_types",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=["Registry truth does not itself grant STT/TTS authority; saved outputs require exact one-time approval. Media mutation and transcoding remain unavailable."],
        errors=[],
        trace_summary=TraceSummary(route_used="coding.media.media_types", log_written=False, journal_written=False),
        data={"media_types": media_registry_payload(), "dependency_health": media_dependency_health()},
    )
    return envelope.to_payload()


@router.post("/media/inspect")
async def post_media_inspect(payload: CodingMediaPathRequest = Body(...)) -> dict[str, Any]:
    return _envelope("media_inspect", inspect_governed_media(payload))


@router.post("/media/thumbnail")
async def post_media_thumbnail(payload: CodingMediaPathRequest = Body(...)) -> dict[str, Any]:
    return _envelope("media_thumbnail", thumbnail_governed_media(payload))


__all__ = ("router",)
