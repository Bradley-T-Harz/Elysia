"""
Approval route module for the Elysia local API bridge.

This module owns:
- POST /approval/resolve

It should stay thin:
- accept approval-resolution input
- perform only minimal request-shape guarding
- call the governance-side service
- return the structured envelope produced downstream

It must not become a second approval engine, second governance layer,
or second request-trace system.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from app.api.schemas.approval import ApprovalResolveRequest

router = APIRouter(
    prefix="/approval",
    tags=["approval"],
)

ALLOWED_DECISIONS = {"approved", "denied", "cancelled"}


def _require_mapping_payload(payload: Any) -> dict[str, Any]:
    """
    Require that the incoming request body is a JSON object / mapping.
    """
    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=400,
            detail="Request body for /approval/resolve must be a JSON object.",
        )

    return dict(payload)


def _require_request_id(payload: dict[str, Any]) -> None:
    """
    Require a non-empty string request_id field.
    """
    request_id = payload.get("request_id", "")

    if not isinstance(request_id, str) or not request_id.strip():
        raise HTTPException(
            status_code=400,
            detail="Field 'request_id' is required and must be a non-empty string.",
        )


def _require_decision(payload: dict[str, Any]) -> None:
    """
    Require an explicit Phase 1 approval decision.
    """
    decision = payload.get("decision", "")

    if not isinstance(decision, str) or not decision.strip():
        raise HTTPException(
            status_code=400,
            detail="Field 'decision' is required and must be a non-empty string.",
        )

    normalized_decision = decision.strip().lower()
    if normalized_decision not in ALLOWED_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Field 'decision' must be one of: approved, denied, cancelled."
            ),
        )


def _load_governance_service() -> Any:
    """
    Import the governance service lazily so this route module can exist before
    every downstream service organ is finished.
    """
    try:
        return importlib.import_module("app.api.governance_service")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Governance service is not available yet: {exc}",
        ) from exc


@router.post("/resolve")
async def resolve_approval(payload: Any = Body(...)) -> dict[str, Any]:
    """
    Submit one approval-resolution request into the governance-side service.

    This route does not decide governance truth itself. It performs only the
    minimum request-shape checks and delegates the real work downstream.
    """
    payload_dict = _require_mapping_payload(payload)
    _require_request_id(payload_dict)
    _require_decision(payload_dict)
    try:
        validated_payload = ApprovalResolveRequest(**payload_dict)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail="Approval resolution payload did not match the exact typed contract.",
        ) from exc

    governance_service = _load_governance_service()

    service_fn = getattr(governance_service, "resolve_approval_request", None)
    if service_fn is None:
        raise HTTPException(
            status_code=503,
            detail="Governance service does not expose resolve_approval_request yet.",
        )

    result = service_fn(validated_payload)
    if inspect.isawaitable(result):
        result = await result

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail="Governance service returned a non-dictionary response.",
        )

    return result
