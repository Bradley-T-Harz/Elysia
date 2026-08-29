"""Governed local add-on installer routes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Query

from app.api.addons.deep_link import parse_marketplace_install_link
from app.api.addons.manifest_validator import inspect_addon_package, load_permission_vocabulary
from app.api.addons.lifecycle_service import (
    apply_legacy_exact_request,
    apply_transition,
    approve_transition,
    plan_transition,
)
from app.api.addons.marketplace_review_service import (
    load_official_candidates,
    prepare_admin_review_preview,
    prepare_submission_preview,
)
from app.api.addons.preparation_service import prepare_developer_package_plan
from app.api.addons.registry import (
    append_audit,
    list_installed,
    read_audit,
    rollback,
    status_payload,
    validation_only_sandbox,
)
from app.api.schemas.addons import (
    AddonMarketplaceIntentRequest,
    AddonPackagePathRequest,
    AddonStatusChangeRequest,
    AddonTransitionApplyRequest,
    AddonTransitionApprovalRequest,
    AddonTransitionPlanRequest,
    DeveloperAddonPackagePlanRequest,
    MarketplaceReviewPreviewRequest,
    MarketplaceSubmissionPreviewRequest,
)
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "governed-addon-foundation-1.0"

router = APIRouter(prefix="/addons", tags=["addons"])


def _new_request_id(prefix: str = "addon") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _envelope(*, result_type: str, data: Any, warnings: list[str] | None = None, errors: list[str] | None = None, approval_state: ApprovalState = ApprovalState.NOT_NEEDED, status: EnvelopeStatus = EnvelopeStatus.OK) -> dict[str, Any]:
    envelope = build_response_envelope(
        status=status,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=warnings or [
            "Local Elysia is the only installer authority. Website links and Marketplace intents never install, enable, or execute add-ons silently."
        ],
        errors=errors or [],
        trace_summary=TraceSummary(route_used=f"addons.{result_type}", log_written=True, journal_written=False),
        data=data,
    )
    return envelope.to_payload()


@router.get("/status")
async def get_addons_status() -> dict[str, Any]:
    return _envelope(
        result_type="addons_status",
        data={
            "addons_status": status_payload(),
            "official_candidates": load_official_candidates(),
        },
    )


@router.get("/installed")
async def get_installed_addons() -> dict[str, Any]:
    return _envelope(result_type="installed_addons", data={"installed_addons": list_installed()})


@router.post("/inspect-package")
async def inspect_package(payload: AddonPackagePathRequest = Body(...)) -> dict[str, Any]:
    inspection = inspect_addon_package(payload.package_path)
    return _envelope(result_type="addon_package_inspection", data={"inspection": inspection.to_payload()})


@router.post("/install-plan")
async def install_plan(payload: AddonPackagePathRequest = Body(...)) -> dict[str, Any]:
    plan = plan_transition(
        AddonTransitionPlanRequest(
            action="install_disabled",
            package_path=payload.package_path,
            source=payload.source,
        )
    )
    return _envelope(
        result_type="addon_install_plan",
        data={"install_plan": plan},
        approval_state=ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if plan.get("plan_state") == "ready_for_exact_approval" else EnvelopeStatus.BLOCKED,
        errors=plan.get("errors", []),
    )


@router.post("/install-disabled")
async def install_disabled_route(payload: AddonPackagePathRequest = Body(...)) -> dict[str, Any]:
    result = apply_legacy_exact_request(
        action="install_disabled",
        plan_id=payload.plan_id,
        plan_hash=payload.plan_hash,
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
    )
    return _envelope(
        result_type="addon_install_disabled",
        data={"install_result": result},
        approval_state=ApprovalState.APPROVED if result.get("ok") else ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("ok") else EnvelopeStatus.BLOCKED,
        errors=result.get("errors", []),
    )


@router.post("/enable")
async def enable_addon(payload: AddonStatusChangeRequest = Body(...)) -> dict[str, Any]:
    result = apply_legacy_exact_request(
        action="enable_limited",
        plan_id=payload.plan_id,
        plan_hash=payload.plan_hash,
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
    )
    return _envelope(
        result_type="addon_enable_limited",
        data={"operation_result": result},
        approval_state=ApprovalState.APPROVED if result.get("ok") else ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("ok") else EnvelopeStatus.BLOCKED,
        errors=result.get("errors", []),
    )


@router.post("/disable")
async def disable_addon(payload: AddonStatusChangeRequest = Body(...)) -> dict[str, Any]:
    result = apply_legacy_exact_request(
        action="disable",
        plan_id=payload.plan_id,
        plan_hash=payload.plan_hash,
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
    )
    return _envelope(
        result_type="addon_disable",
        data={"operation_result": result},
        approval_state=ApprovalState.APPROVED if result.get("ok") else ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("ok") else EnvelopeStatus.BLOCKED,
        errors=result.get("errors", []),
    )


@router.post("/revoke")
async def revoke_addon(payload: AddonStatusChangeRequest = Body(...)) -> dict[str, Any]:
    result = apply_legacy_exact_request(
        action="revoke",
        plan_id=payload.plan_id,
        plan_hash=payload.plan_hash,
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
    )
    return _envelope(
        result_type="addon_revoke",
        data={"operation_result": result},
        approval_state=ApprovalState.APPROVED if result.get("ok") else ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("ok") else EnvelopeStatus.BLOCKED,
        errors=result.get("errors", []),
    )


@router.post("/remove")
async def remove_addon(payload: AddonStatusChangeRequest = Body(...)) -> dict[str, Any]:
    result = apply_legacy_exact_request(
        action="remove",
        plan_id=payload.plan_id,
        plan_hash=payload.plan_hash,
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
    )
    return _envelope(
        result_type="addon_remove",
        data={"operation_result": result},
        approval_state=ApprovalState.APPROVED if result.get("ok") else ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("ok") else EnvelopeStatus.BLOCKED,
        errors=result.get("errors", []),
    )


@router.post("/transitions/plan")
async def create_transition_plan(payload: AddonTransitionPlanRequest = Body(...)) -> dict[str, Any]:
    plan = plan_transition(payload)
    return _envelope(
        result_type="addon_transition_plan",
        data={"transition_plan": plan},
        approval_state=ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if plan.get("plan_state") == "ready_for_exact_approval" else EnvelopeStatus.BLOCKED,
        errors=plan.get("errors", []),
    )


@router.post("/transitions/approve")
async def approve_exact_transition(payload: AddonTransitionApprovalRequest = Body(...)) -> dict[str, Any]:
    result = approve_transition(payload)
    return _envelope(
        result_type="addon_transition_approval",
        data={"transition_approval": result},
        approval_state=ApprovalState.APPROVED if result.get("approved") else ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("approved") else EnvelopeStatus.BLOCKED,
        errors=[] if result.get("approved") else [str(result.get("reason_code", "approval_refused"))],
    )


@router.post("/transitions/apply")
async def apply_exact_transition(payload: AddonTransitionApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_transition(payload)
    return _envelope(
        result_type="addon_transition_apply",
        data={"transition_result": result},
        approval_state=ApprovalState.APPROVED if result.get("ok") else ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("ok") else EnvelopeStatus.BLOCKED,
        errors=[] if result.get("ok") else [str(result.get("reason_code", "transition_refused"))],
    )


@router.post("/developer/package-plan")
async def developer_package_plan(payload: DeveloperAddonPackagePlanRequest = Body(...)) -> dict[str, Any]:
    result = prepare_developer_package_plan(payload)
    return _envelope(
        result_type="developer_addon_package_plan",
        data={"package_preparation_plan": result},
        status=EnvelopeStatus.OK if result.get("plan_state") == "ready_for_local_package_build" else EnvelopeStatus.BLOCKED,
        errors=result.get("errors", []),
    )


@router.post("/marketplace/submission-preview")
async def marketplace_submission_preview(payload: MarketplaceSubmissionPreviewRequest = Body(...)) -> dict[str, Any]:
    result = prepare_submission_preview(payload)
    return _envelope(
        result_type="marketplace_submission_preview",
        data={"submission_preview": result},
        approval_state=ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("preview_state") == "ready_for_explicit_external_submission" else EnvelopeStatus.BLOCKED,
        errors=[str(item) for item in result.get("blockers", [])],
    )


@router.post("/marketplace/review-preview")
async def marketplace_review_preview(payload: MarketplaceReviewPreviewRequest = Body(...)) -> dict[str, Any]:
    result = prepare_admin_review_preview(payload)
    return _envelope(
        result_type="marketplace_review_preview",
        data={"review_preview": result},
        approval_state=ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("review_state") == "review_contract_valid" else EnvelopeStatus.BLOCKED,
        errors=[str(item) for item in result.get("blockers", [])],
    )


@router.get("/official-candidates")
async def official_candidates() -> dict[str, Any]:
    return _envelope(result_type="official_addon_candidates", data={"official_candidates": load_official_candidates()})


@router.post("/rollback")
async def rollback_addon(payload: AddonStatusChangeRequest = Body(...)) -> dict[str, Any]:
    result = rollback(payload.addon_id, payload.version)
    return _envelope(
        result_type="addon_rollback",
        data={"operation_result": result},
        approval_state=ApprovalState.NEEDED,
        status=EnvelopeStatus.OK if result.get("ok") else EnvelopeStatus.BLOCKED,
        errors=[] if result.get("ok") else [str(result.get("reason") or result.get("error") or "Rollback blocked.")],
    )


@router.post("/test-sandbox")
async def test_sandbox(payload: AddonPackagePathRequest = Body(...)) -> dict[str, Any]:
    return _envelope(result_type="addon_sandbox_test", data={"sandbox_result": validation_only_sandbox(payload.package_path)})


@router.get("/audit")
async def get_addons_audit(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return _envelope(result_type="addon_audit", data={"audit_records": read_audit(limit=limit)})


@router.get("/permissions")
async def get_permission_vocabulary() -> dict[str, Any]:
    return _envelope(result_type="addon_permission_vocabulary", data={"permission_vocabulary": load_permission_vocabulary()})


@router.post("/marketplace-intent/open")
async def open_marketplace_intent(payload: AddonMarketplaceIntentRequest = Body(...)) -> dict[str, Any]:
    if payload.deep_link_url:
        intent, errors = parse_marketplace_install_link(payload.deep_link_url)
    else:
        deep_link = f"elysia://marketplace/install?intent_id={payload.intent_id or ''}&nonce={payload.nonce or ''}"
        intent, errors = parse_marketplace_install_link(deep_link)
    if errors or intent is None:
        append_audit("marketplace_intent_open", "blocked", details={"errors": errors})
        return _envelope(
            result_type="marketplace_install_intent",
            data={"intent": None, "trusted_as_authority": False, "will_install": False},
            errors=errors,
            status=EnvelopeStatus.BLOCKED,
        )
    append_audit("marketplace_intent_open", "ok", details={"intent_id": intent.intent_id, "trusted_as_authority": False})
    return _envelope(
        result_type="marketplace_install_intent",
        data={
            "intent": intent.to_payload(),
            "trusted_as_authority": False,
            "will_install": False,
            "next_step": "Open Add-ons Manager permission review. Local package validation is still required.",
        },
        approval_state=ApprovalState.NEEDED,
    )


__all__ = ("router",)
