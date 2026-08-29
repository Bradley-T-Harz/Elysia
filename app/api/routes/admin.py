"""Authenticated local installation-governance routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from app.api import account_service, admin_service
from app.api.routes.account import _envelope, _error_envelope
from app.api.schemas.admin import (
    AdminChangeApplyRequest,
    AdminChangePreviewRequest,
    AdminRestoreRequest,
)


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/summary")
async def admin_summary() -> dict[str, Any]:
    try:
        data = admin_service.get_admin_summary()
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="admin_summary")
    return _envelope(result_type="admin_summary", data=data)


@router.post("/changes/preview")
async def preview_change(
    payload: AdminChangePreviewRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = admin_service.preview_admin_change(payload)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="admin_change_preview")
    return _envelope(result_type="admin_change_preview", data=data)


@router.post("/changes/apply")
async def apply_change(
    payload: AdminChangeApplyRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = admin_service.apply_admin_change(payload)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="admin_change_apply")
    return _envelope(result_type="admin_change_apply", data=data)


@router.post("/changes/restore")
async def restore_change(
    payload: AdminRestoreRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = admin_service.restore_admin_change(payload)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="admin_change_restore")
    return _envelope(result_type="admin_change_restore", data=data)


__all__ = ("router",)
