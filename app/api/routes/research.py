"""
Bounded public research route.

The route stays thin: it validates the body shape, delegates to
research_service, and never calls SearXNG directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.api import research_service


router = APIRouter(
    prefix="/research",
    tags=["research"],
)


def _require_mapping_payload(payload: Any, path: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=400,
            detail=f"Request body for {path} must be a JSON object.",
        )
    return dict(payload)


def _service_call(operation):
    try:
        return operation()
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Repository authorization/state conflicts are safe operator-facing
        # facts; raw internals and stack traces remain out of the API body.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/search")
async def search_bounded_public_research(payload: Any = Body(...)) -> dict[str, Any]:
    """Run bounded public research through the SearXNG worker service path."""
    return research_service.run_bounded_public_research(
        _require_mapping_payload(payload, "/research/search")
    )


@router.post("/fetch")
async def fetch_bounded_public_page(payload: Any = Body(...)) -> dict[str, Any]:
    """Run one explicit bounded public page fetch through the fetch worker."""
    return research_service.run_bounded_public_fetch(
        _require_mapping_payload(payload, "/research/fetch")
    )


@router.get("/records")
async def get_durable_research(
    project_id: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return _service_call(
        lambda: research_service.list_durable_research(
            project_id=project_id,
            conversation_id=conversation_id,
        )
    )


@router.get("/context-receipts")
async def get_context_receipts(
    project_id: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return _service_call(
        lambda: research_service.list_context_receipts(
            project_id=project_id,
            conversation_id=conversation_id,
            limit=limit,
        )
    )


@router.get("/egress/approvals/pending")
async def get_pending_egress_approvals() -> dict[str, Any]:
    return _service_call(research_service.list_pending_egress_approvals)


@router.post("/egress/approvals/resolve")
async def resolve_egress_approval(payload: Any = Body(...)) -> dict[str, Any]:
    body = _require_mapping_payload(payload, "/research/egress/approvals/resolve")
    return _service_call(
        lambda: research_service.resolve_egress_approval(body)
    )


@router.post("/evidence/{evidence_id}/review")
async def review_evidence(evidence_id: str, payload: Any = Body(...)) -> dict[str, Any]:
    body = _require_mapping_payload(payload, f"/research/evidence/{evidence_id}/review")
    return _service_call(
        lambda: research_service.review_evidence(evidence_id, body)
    )


@router.post("/evidence/{evidence_id}/correct")
async def correct_evidence(evidence_id: str, payload: Any = Body(...)) -> dict[str, Any]:
    body = _require_mapping_payload(payload, f"/research/evidence/{evidence_id}/correct")
    return _service_call(
        lambda: research_service.correct_evidence(evidence_id, body)
    )


@router.post("/evidence/{evidence_id}/promote")
async def promote_evidence(evidence_id: str) -> dict[str, Any]:
    return _service_call(lambda: research_service.promote_evidence(evidence_id))


__all__ = ("router",)
