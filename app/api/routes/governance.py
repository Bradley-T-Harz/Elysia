"""
Governance route module for the Elysia local API bridge.

This module owns:
- GET /governance/state
- POST /governance/changes/plan
- POST /governance/changes/apply
- POST /governance/changes/restore

It should stay thin:
- accept typed state/change requests
- call the governance service
- return the structured envelope produced downstream

It must not become a second governance engine, second runtime, or second
policy-resolution layer.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.api.schemas.governance_mutation import (
    GovernanceChangeApplyRequest,
    GovernanceChangePlanRequest,
    GovernanceRestoreRequest,
)

router = APIRouter(
    prefix="/governance",
    tags=["governance"],
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


async def _invoke_service_callable(
    service_module: Any,
    fn_name: str,
    *args: Any,
) -> dict[str, Any]:
    """
    Call a named service function and require a dictionary envelope result.
    """
    service_fn = getattr(service_module, fn_name, None)
    if service_fn is None:
        raise HTTPException(
            status_code=503,
            detail=f"Required service function '{fn_name}' is not available yet.",
        )

    result = service_fn(*args)
    if inspect.isawaitable(result):
        result = await result

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail=f"Service function '{fn_name}' returned a non-dictionary response.",
        )

    return result


@router.get("/state")
async def get_governance_state() -> dict[str, Any]:
    """
    Return a compact governed governance-state envelope.

    This route does not build governance truth itself. It delegates to
    governance_service.
    """
    governance_service = _load_governance_service()
    return await _invoke_service_callable(
        governance_service,
        "get_governance_state",
    )


@router.post("/changes/plan")
async def post_governance_change_plan(
    payload: GovernanceChangePlanRequest = Body(...),
) -> dict[str, Any]:
    """Preview one exact Governance change without mutating authority."""
    return await _invoke_service_callable(
        _load_governance_service(),
        "plan_governance_change",
        payload,
    )


@router.post("/changes/apply")
async def post_governance_change_apply(
    payload: GovernanceChangeApplyRequest = Body(...),
) -> dict[str, Any]:
    """Apply only a current, confirmed, exact, approved Governance plan."""
    return await _invoke_service_callable(
        _load_governance_service(),
        "apply_governance_change",
        payload,
    )


@router.post("/changes/restore")
async def post_governance_change_restore(
    payload: GovernanceRestoreRequest = Body(...),
) -> dict[str, Any]:
    """Restore an applied Governance change from its exact recovery record."""
    return await _invoke_service_callable(
        _load_governance_service(),
        "restore_governance_change",
        payload,
    )
