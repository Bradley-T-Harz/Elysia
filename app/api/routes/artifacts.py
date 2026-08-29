"""
Artifacts route module for the Elysia local API bridge.

This module exposes safe local artifact summaries and details. It does not
browse arbitrary paths, publish artifacts, mutate source files, or promote
artifacts into memory.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query

from app.ids import new_id

from app.api.artifact_service import get_artifact_detail, list_artifacts
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"
MAX_ROUTE_ARTIFACT_LIMIT = 200

router = APIRouter(
    prefix="/artifacts",
    tags=["artifacts"],
)


def _new_request_id(prefix: str = "req") -> str:
    return new_id(prefix)


def _model_to_payload(model: Any) -> dict[str, Any]:
    dump_method = getattr(model, "model_dump", None)
    if callable(dump_method):
        return dump_method(mode="json")

    dict_method = getattr(model, "dict", None)
    if callable(dict_method):
        return dict_method()

    if isinstance(model, dict):
        return dict(model)

    raise TypeError("Unable to serialize artifact route model.")


def _trace(route_used: str) -> TraceSummary:
    return TraceSummary(
        route_used=route_used,
        log_written=False,
        journal_written=False,
    )


@router.get("")
@router.get("/", include_in_schema=False)
async def get_artifacts(
    project_id: str | None = Query(default=None, max_length=128),
    request_id: str | None = Query(default=None, max_length=160),
    conversation_id: str | None = Query(default=None, max_length=128),
    artifact_type: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=MAX_ROUTE_ARTIFACT_LIMIT),
) -> dict[str, Any]:
    """Return local artifact summaries filtered by compact IDs when provided."""
    request_id_for_envelope = _new_request_id()

    result = list_artifacts(
        project_id=project_id,
        request_id=request_id,
        conversation_id=conversation_id,
        artifact_type=artifact_type,
        limit=limit,
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id_for_envelope,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="artifact_list",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_trace("get_artifacts"),
        data=_model_to_payload(result),
    )
    return envelope.to_payload()


@router.get("/{artifact_id}")
async def get_one_artifact(
    artifact_id: str = Path(..., min_length=1, max_length=180),
) -> dict[str, Any]:
    """Return safe local detail for one known artifact id."""
    request_id = _new_request_id()
    detail = get_artifact_detail(artifact_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact '{artifact_id}' was not found.",
        )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="artifact_detail",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_trace("get_one_artifact"),
        data=_model_to_payload(detail),
    )
    return envelope.to_payload()
