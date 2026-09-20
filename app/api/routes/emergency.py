"""System-wide emergency posture routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from app.api import account_service
from app.api.routes.account import _envelope, _error_envelope
from app.api.schemas.emergency import EmergencyResetRequest, EmergencyStopRequest
from app.cognition.emergency_control import (
    activate_emergency_stop,
    emergency_status,
    reset_emergency_stop,
)


router = APIRouter(prefix="/emergency", tags=["emergency"])


@router.get("/status")
async def get_emergency_status() -> dict[str, Any]:
    return _envelope(result_type="emergency_status", data=emergency_status())


@router.post("/stop")
async def stop_everything(
    payload: EmergencyStopRequest = Body(default=EmergencyStopRequest()),
) -> dict[str, Any]:
    try:
        data = activate_emergency_stop(reason=payload.reason)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="emergency_stop")
    return _envelope(result_type="emergency_stop", data=data)


@router.post("/reset")
async def reset_after_stop(
    payload: EmergencyResetRequest = Body(default=EmergencyResetRequest()),
) -> dict[str, Any]:
    if not payload.acknowledge_safe_restart:
        return _envelope(
            result_type="emergency_reset",
            data={"reset": False, "acknowledgement_required": True},
        )
    try:
        data = reset_emergency_stop()
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="emergency_reset")
    return _envelope(result_type="emergency_reset", data=data)


__all__ = ("router",)
