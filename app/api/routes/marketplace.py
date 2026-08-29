"""Marketplace link route module."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api import marketplace_link_service
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.marketplace import MarketplaceLinkRequest
from app.api.schemas.marketplace import MarketplaceProfileSyncRecordRequest


API_VERSION = "1.0.0"
CONTRACT_VERSION = "marketplace-link-contract-0.1"

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def _new_request_id(prefix: str = "marketplace") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _envelope(
    *,
    result_type: str,
    data: Any,
    status: EnvelopeStatus = EnvelopeStatus.OK,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED,
) -> dict[str, Any]:
    envelope = build_response_envelope(
        status=status,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=TraceSummary(
            route_used=f"marketplace.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    )
    return envelope.to_payload()


def _error_envelope(exc: Exception, *, result_type: str) -> dict[str, Any]:
    approval_state = ApprovalState.UNKNOWN
    if isinstance(exc, marketplace_link_service.MarketplaceLinkAuthError):
        approval_state = ApprovalState.NEEDED
    return _envelope(
        result_type=result_type,
        data={
            "marketplace_link_error": True,
            "marketplace_password_received": False,
            "marketplace_tokens_received": False,
            "local_private_profile_shared": False,
            "runtime_access_allowed": False,
        },
        status=EnvelopeStatus.BLOCKED,
        errors=[str(exc)],
        approval_state=approval_state,
    )


@router.get("/link/status")
async def get_marketplace_link_status() -> dict[str, Any]:
    try:
        status = marketplace_link_service.get_marketplace_link_status()
    except marketplace_link_service.MarketplaceLinkServiceError as exc:
        return _error_envelope(exc, result_type="marketplace_link_status")
    return _envelope(
        result_type="marketplace_link_status",
        data={"marketplace_link": status.to_payload()},
    )


@router.post("/link")
async def link_marketplace_account(payload: MarketplaceLinkRequest = Body(...)) -> dict[str, Any]:
    try:
        status = marketplace_link_service.link_marketplace_account(payload)
    except marketplace_link_service.MarketplaceLinkServiceError as exc:
        return _error_envelope(exc, result_type="marketplace_link")
    return _envelope(
        result_type="marketplace_link",
        data={"marketplace_link": status.to_payload()},
        warnings=[
            "Marketplace link stores metadata only. Marketplace passwords and Supabase tokens are not stored by the local backend."
        ],
    )


@router.delete("/link")
async def unlink_marketplace_account() -> dict[str, Any]:
    try:
        status = marketplace_link_service.unlink_marketplace_account()
    except marketplace_link_service.MarketplaceLinkServiceError as exc:
        return _error_envelope(exc, result_type="marketplace_unlink")
    return _envelope(
        result_type="marketplace_unlink",
        data={"marketplace_link": status.to_payload(), "unlinked": True},
    )


@router.post("/profile-sync/record")
async def record_marketplace_profile_sync(
    payload: MarketplaceProfileSyncRecordRequest = Body(...),
) -> dict[str, Any]:
    try:
        record = marketplace_link_service.record_marketplace_profile_sync(payload)
        status = marketplace_link_service.get_marketplace_link_status()
    except marketplace_link_service.MarketplaceLinkServiceError as exc:
        return _error_envelope(exc, result_type="marketplace_profile_sync_record")
    return _envelope(
        result_type="marketplace_profile_sync_record",
        data={
            "profile_sync": record.to_payload(),
            "marketplace_link": status.to_payload(),
        },
        warnings=[
            "Marketplace profile sync is retired. The compatibility record stores no Personal Identity values, passwords, Supabase tokens, Story, local photos, memory, files, vaults, logs, or chats."
        ],
    )


__all__ = ("router",)
