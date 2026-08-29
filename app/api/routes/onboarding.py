"""Authenticated local routes for voluntary personal onboarding."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.onboarding.schemas import OnboardingDraftRequest, OnboardingFinalizeRequest
from app.onboarding.service import OnboardingError, PersonalOnboardingService


router = APIRouter(prefix="/onboarding", tags=["onboarding"])
API_VERSION = "1.0.0"
CONTRACT_VERSION = "elysia-personal-onboarding-1.0"


def _envelope(*, result_type: str, data: dict[str, Any], status: EnvelopeStatus = EnvelopeStatus.OK, errors: list[str] | None = None) -> dict[str, Any]:
    return build_response_envelope(
        status=status,
        request_id=f"req_onboarding_{uuid4().hex[:16]}",
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE if status == EnvelopeStatus.OK else CapabilityState.DEGRADED,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.APPROVED,
        warnings=[],
        errors=errors or [],
        trace_summary=TraceSummary(route_used=f"onboarding.{result_type}", log_written=False, journal_written=False),
        data=data,
    ).to_payload()


def _run(result_type: str, operation) -> dict[str, Any]:
    try:
        return _envelope(result_type=result_type, data=operation())
    except OnboardingError as exc:
        return _envelope(
            result_type=result_type,
            data={"account_scoped": True, "private_content_returned": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
        )


@router.get("")
async def get_onboarding() -> dict[str, Any]:
    return _run("state", lambda: PersonalOnboardingService().state())


@router.put("/draft")
async def save_onboarding_draft(payload: OnboardingDraftRequest = Body(...)) -> dict[str, Any]:
    return _run("draft_save", lambda: PersonalOnboardingService().save(payload))


@router.post("/finalize")
async def finalize_onboarding(payload: OnboardingFinalizeRequest = Body(...)) -> dict[str, Any]:
    return _run("finalize", lambda: PersonalOnboardingService().finalize(payload))


__all__ = ("router",)
