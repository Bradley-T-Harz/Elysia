"""Account route module for the local identity gate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse

from app.ids import new_id

from app.api import account_service
from app.api.schemas.account import (
    AccountCreateRequest,
    AccountDeleteRequest,
    AccountLoginRequest,
    AccountProfileArchiveExportRequest,
    AccountProfileArchiveRestoreRequest,
    AccountProfileUpdateRequest,
    ProfilePhotoSelectRequest,
)
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"

router = APIRouter(prefix="/account", tags=["account"])


def _new_request_id(prefix: str = "account") -> str:
    return new_id(prefix)


def _envelope(
    *,
    result_type: str,
    data: Any,
    status: EnvelopeStatus = EnvelopeStatus.OK,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    capability_state: CapabilityState = CapabilityState.LIVE,
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED,
) -> dict[str, Any]:
    envelope = build_response_envelope(
        status=status,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=capability_state,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=TraceSummary(
            route_used=f"account.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    )
    return envelope.to_payload()


def _error_envelope(exc: Exception, *, result_type: str) -> dict[str, Any]:
    status = EnvelopeStatus.BLOCKED
    approval_state = ApprovalState.DENIED
    if isinstance(exc, account_service.AccountAuthError):
        approval_state = ApprovalState.NEEDED
    return _envelope(
        result_type=result_type,
        data={
            "account_error": True,
            "private_profile_returned": False,
            "credential_material_returned": False,
        },
        status=status,
        errors=[str(exc)],
        approval_state=approval_state,
    )


@router.get("/state")
async def get_account_state() -> dict[str, Any]:
    return _envelope(
        result_type="account_state",
        data=account_service.get_account_state(),
    )


@router.post("/create")
async def create_account(payload: AccountCreateRequest = Body(...)) -> dict[str, Any]:
    try:
        profile = account_service.create_account(payload)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_create")
    return _envelope(
        result_type="account_create",
        data={
            "state": account_service.get_account_state().to_payload(),
            "profile": profile.to_payload(),
        },
    )


@router.post("/login")
async def login(payload: AccountLoginRequest = Body(...)) -> dict[str, Any]:
    try:
        state = account_service.login(payload)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_login")
    return _envelope(result_type="account_login", data={"state": state.to_payload()})


@router.post("/logout")
async def logout() -> dict[str, Any]:
    state = account_service.logout()
    return _envelope(
        result_type="account_logout",
        data={"state": state.to_payload(), "session_revoked": True},
    )


@router.get("/deletion-inventory")
async def get_deletion_inventory() -> dict[str, Any]:
    try:
        inventory = account_service.get_account_deletion_inventory()
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_deletion_inventory")
    return _envelope(
        result_type="account_deletion_inventory",
        data={"deletion_inventory": inventory.to_payload()},
    )


@router.post("/delete")
async def delete_account(payload: AccountDeleteRequest = Body(...)) -> dict[str, Any]:
    try:
        state, inventory, sessions_removed, profile_assets_removed = (
            account_service.delete_current_account(payload)
        )
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_delete")
    return _envelope(
        result_type="account_delete",
        data={
            "deleted": True,
            "state": state.to_payload(),
            "deletion_inventory": inventory.to_payload(),
            "sessions_removed": sessions_removed,
            "profile_assets_removed": profile_assets_removed,
        },
    )


@router.get("/profile")
async def get_profile() -> dict[str, Any]:
    try:
        profile = account_service.get_private_profile()
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_profile")
    return _envelope(result_type="account_profile", data={"profile": profile.to_payload()})


@router.put("/profile")
async def update_profile(payload: AccountProfileUpdateRequest = Body(...)) -> dict[str, Any]:
    try:
        profile, password_changed = account_service.update_profile(payload)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_profile_update")
    return _envelope(
        result_type="account_profile_update",
        data={
            "profile": profile.to_payload(),
            "password_changed": password_changed,
        },
    )


@router.post("/profile/archive/export")
async def export_profile_archive(
    payload: AccountProfileArchiveExportRequest = Body(...),
) -> dict[str, Any]:
    try:
        archive = account_service.export_profile_archive(payload)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_profile_archive_export")
    return _envelope(
        result_type="account_profile_archive_export",
        data={"archive": archive},
        approval_state=ApprovalState.APPROVED,
    )


@router.post("/profile/archive/restore")
async def restore_profile_archive(
    payload: AccountProfileArchiveRestoreRequest = Body(...),
) -> dict[str, Any]:
    try:
        result = account_service.restore_profile_archive(payload)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_profile_archive_restore")
    return _envelope(
        result_type="account_profile_archive_restore",
        data=result,
        approval_state=ApprovalState.APPROVED,
    )


@router.get("/profile/elysia-visible")
async def get_elysia_visible_profile() -> dict[str, Any]:
    profile = account_service.get_elysia_visible_profile()
    return _envelope(
        result_type="elysia_visible_profile",
        data={"profile": profile.to_payload() if profile else None},
    )


@router.post("/profile-photo/select")
async def select_profile_photo(payload: ProfilePhotoSelectRequest = Body(...)) -> dict[str, Any]:
    try:
        asset = account_service.select_profile_photo(payload.source_path)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_profile_photo_select")
    return _envelope(
        result_type="account_profile_photo_select",
        data={"profile_photo": asset.to_payload()},
    )


@router.delete("/profile-photo")
async def delete_profile_photo() -> dict[str, Any]:
    try:
        deleted = account_service.delete_profile_photo()
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_profile_photo_delete")
    return _envelope(
        result_type="account_profile_photo_delete",
        data={"deleted": deleted, "profile_photo_asset_id": None},
    )


@router.get("/profile-photo/{asset_id}/preview", response_model=None)
async def preview_profile_photo(asset_id: str):
    try:
        path, mime_type = account_service.get_profile_photo_preview(asset_id)
    except account_service.AccountServiceError as exc:
        return _error_envelope(exc, result_type="account_profile_photo_preview")
    return FileResponse(
        path,
        media_type=mime_type,
        filename=f"{asset_id}",
    )


@router.get("/colors")
async def get_account_colors() -> dict[str, Any]:
    colors = [color.to_payload() for color in account_service.load_account_colors()]
    return _envelope(result_type="account_colors", data={"colors": colors})


@router.get("/privacy")
async def get_account_privacy() -> dict[str, Any]:
    policy = account_service.load_privacy_policy_view()
    return _envelope(result_type="account_privacy", data={"privacy": policy.to_payload()})


__all__ = ("router",)
