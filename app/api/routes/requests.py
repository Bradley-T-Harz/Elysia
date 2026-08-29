"""
Request-summary route module for the Elysia local API bridge.

This module owns:
- GET /requests/{request_id}/summary

It should stay thin:
- read the path parameter
- accept small optional query metadata
- call the request-trace service
- return the structured envelope produced downstream

It must not become a second request-trace engine, second runtime,
or second logging/journaling layer.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(
    prefix="/requests",
    tags=["requests"],
)


def _require_request_id(request_id: str) -> str:
    """
    Require a non-empty request_id path parameter.
    """
    if not isinstance(request_id, str) or not request_id.strip():
        raise HTTPException(
            status_code=400,
            detail="Path parameter 'request_id' is required and must be a non-empty string.",
        )

    return request_id.strip()


def _load_request_trace_service() -> Any:
    """
    Import the request-trace service lazily so this route module can exist before
    every downstream service organ is finished.
    """
    try:
        return importlib.import_module("app.api.request_trace_service")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Request trace service is not available yet: {exc}",
        ) from exc


@router.get("/{request_id}/summary")
async def get_request_summary(
    request_id: str,
    include_notes: bool | None = Query(
        default=None,
        description="Optional future flag for extra compact notes.",
    ),
    include_resolution: bool | None = Query(
        default=None,
        description="Optional future flag for extra compact resolution detail.",
    ),
) -> dict[str, Any]:
    """
    Return a compact governed summary for one real request_id.

    This route does not build request-summary truth itself. It performs only the
    minimum path/query handling and delegates the real work downstream.
    """
    normalized_request_id = _require_request_id(request_id)

    request_payload: dict[str, Any] = {
        "request_id": normalized_request_id,
    }

    if include_notes is not None:
        request_payload["include_notes"] = include_notes

    if include_resolution is not None:
        request_payload["include_resolution"] = include_resolution

    request_trace_service = _load_request_trace_service()

    service_fn = getattr(request_trace_service, "get_request_summary", None)
    if service_fn is None:
        raise HTTPException(
            status_code=503,
            detail="Request trace service does not expose get_request_summary yet.",
        )

    result = service_fn(request_payload)
    if inspect.isawaitable(result):
        result = await result

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail="Request trace service returned a non-dictionary response.",
        )

    return result
