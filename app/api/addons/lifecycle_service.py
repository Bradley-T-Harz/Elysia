"""Exact plan/approve/apply lifecycle for non-executing local add-on state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe
from threading import RLock
from typing import Any
from uuid import uuid4

from app.api.addons.manifest_validator import hash_package_file, inspect_addon_package
from app.api.addons.permission_resolver import current_disabled_resolution
from app.api.addons.registry import (
    append_audit,
    apply_registry_state,
    get_storage_entry,
    registry_revision,
    stage_validated_package,
)
from app.api.schemas.addons import (
    AddonTransitionApplyRequest,
    AddonTransitionApprovalRequest,
    AddonTransitionPlanRequest,
)


PLAN_TTL_SECONDS = 600
APPROVAL_TTL_SECONDS = 300
EXPECTED_CONFIRMATION = "APPROVE EXACT ADD-ON CHANGE"
ACTION_TARGETS = {
    "install_disabled": "installed_disabled",
    "enable_limited": "enabled_limited",
    "disable": "disabled",
    "revoke": "revoked",
    "remove": "removed",
}
VALID_TRANSITIONS = {
    "packaged": {"installed_disabled"},
    "installed_disabled": {"enabled_limited", "disabled", "revoked", "removed"},
    "enabled_limited": {"disabled", "revoked"},
    "disabled": {"enabled_limited", "revoked", "removed"},
    "revoked": {"removed"},
    "removed": set(),
}


@dataclass
class _PlanRecord:
    payload: dict[str, Any]
    package_path: str | None
    source: str
    reason: str | None
    expires_at: datetime
    applied_at: datetime | None = None


@dataclass
class _ApprovalRecord:
    approval_id: str
    plan_id: str
    plan_hash: str
    token: str
    actor: str
    expires_at: datetime
    consumed_at: datetime | None = None


_PLANS: dict[str, _PlanRecord] = {}
_APPROVALS: dict[str, _ApprovalRecord] = {}
_LOCK = RLock()


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _hash_payload(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _audit_refusal(action: str, reason_code: str, payload: dict[str, Any] | None = None) -> None:
    payload = payload or {}
    append_audit(
        action,
        "blocked",
        addon_id=str(payload.get("addon_id")) if payload.get("addon_id") else None,
        version=str(payload.get("version")) if payload.get("version") else None,
        request_id=str(payload.get("request_id")) if payload.get("request_id") else None,
        operation_id=str(payload.get("operation_id")) if payload.get("operation_id") else None,
        details={
            "reason_code": reason_code,
            "planned_action": payload.get("action"),
            "execution_enabled": False,
            "credentials_exposed": False,
            "raw_paths_exposed": False,
        },
    )


def _blocked_plan(action: str, reason_code: str, blocker: str, *, errors: list[str] | None = None) -> dict[str, Any]:
    _audit_refusal("transition_plan", reason_code, {"action": action})
    return {
        "plan_state": "blocked",
        "action": action,
        "reason_code": reason_code,
        "blocker": blocker,
        "errors": errors or [],
        "approval_required": True,
        "execution_enabled": False,
        "bridge_authority_active": False,
        "raw_paths_exposed": False,
    }


def plan_transition(request: AddonTransitionPlanRequest) -> dict[str, Any]:
    action = request.action
    target_state = ACTION_TARGETS[action]
    expires_at = _now() + timedelta(seconds=PLAN_TTL_SECONDS)
    package_path: str | None = None
    inspection = None
    entry: dict[str, Any] | None = None

    if action == "install_disabled":
        if not request.package_path:
            return _blocked_plan(action, "package_path_required", "Select one local .elysia-addon package.")
        inspection = inspect_addon_package(request.package_path)
        if not inspection.installable or inspection.manifest is None or not inspection.package_hash:
            public_inspection = inspection.to_payload()
            return _blocked_plan(
                action,
                "package_validation_failed",
                "Package validation did not pass.",
                errors=[str(item) for item in public_inspection.get("errors", [])],
            )
        package_path = inspection.package_path
        addon_id = inspection.manifest.addon_id
        version = inspection.manifest.version
        package_hash = inspection.package_hash
        current_state = "packaged"
        requested_permissions = [permission.__dict__.copy() for permission in inspection.manifest.permissions]
    else:
        if not request.addon_id or not request.version:
            return _blocked_plan(action, "addon_identity_required", "Add-on ID and version are required.")
        entry = get_storage_entry(request.addon_id, request.version)
        if entry is None:
            return _blocked_plan(action, "addon_not_found", "The exact add-on version is not staged locally.")
        addon_id = request.addon_id
        version = request.version
        package_hash = str(entry.get("package_hash", ""))
        current_state = "enabled_limited" if entry.get("status") == "enabled" else str(entry.get("status"))
        requested_permissions = entry.get("permissions_requested", []) if isinstance(entry.get("permissions_requested"), list) else []

    if request.expected_state and request.expected_state != current_state:
        return _blocked_plan(action, "stale_state", "The add-on state differs from the caller's expected state.")
    if request.expected_package_hash and not compare_digest(request.expected_package_hash, package_hash):
        return _blocked_plan(action, "package_hash_mismatch", "The package hash differs from the caller's expected hash.")
    if target_state not in VALID_TRANSITIONS.get(current_state, set()):
        return _blocked_plan(action, "invalid_transition", f"Transition from {current_state} to {target_state} is not allowed.")

    requested_keys = {str(item.get("key", "")) for item in requested_permissions if isinstance(item, dict)}
    approved = sorted(set(request.approved_permissions))
    widened = sorted(set(approved) - requested_keys)
    if widened:
        return _blocked_plan(action, "permission_widening_refused", "Approved permissions must be a subset of declared permissions.")

    resolution = current_disabled_resolution(
        requested_permissions,
        approved_permissions=approved,
        active_profiles=("core", "workstation", "creator", "developer"),
        revoked=target_state == "revoked",
    )
    plan_id = f"addon_plan_{uuid4().hex[:16]}"
    request_id = f"req_addon_{uuid4().hex[:16]}"
    operation_id = f"op_addon_{uuid4().hex[:16]}"
    hash_material = {
        "action": action,
        "addon_id": addon_id,
        "version": version,
        "package_hash": package_hash,
        "current_state": current_state,
        "proposed_state": target_state,
        "requested_permissions": list(resolution.requested),
        "approved_permissions": list(resolution.approved),
        "effective_permissions": list(resolution.effective),
        "registry_revision": registry_revision(),
        "actor": request.actor,
        "request_id": request_id,
        "operation_id": operation_id,
        "expires_at_utc": _iso(expires_at),
    }
    plan_hash = _hash_payload(hash_material)
    plan = {
        "plan_state": "ready_for_exact_approval",
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        **hash_material,
        "approval_required": True,
        "approval_one_time": True,
        "confirmation_required": EXPECTED_CONFIRMATION,
        "permission_resolution": resolution.to_payload(),
        "execution_enabled": False,
        "bridge_authority_active": False,
        "network_allowed": False,
        "shell_allowed": False,
        "package_manager_allowed": False,
        "private_memory_allowed": False,
        "host_docker_socket_allowed": False,
        "files_retained": True,
        "removal_semantics": "registry_marked_removed_files_retained" if target_state == "removed" else None,
        "revocation_semantics": "trust_withdrawn_no_runtime_was_active" if target_state == "revoked" else None,
        "storage_label": "XDG user add-on data" if target_state == "installed_disabled" else None,
        "raw_paths_exposed": False,
    }
    with _LOCK:
        _PLANS[plan_id] = _PlanRecord(plan, package_path, request.source, request.reason, expires_at)
    append_audit(
        "transition_plan",
        "planned",
        addon_id=addon_id,
        version=version,
        request_id=request_id,
        operation_id=operation_id,
        details={
            "action": action,
            "actor": request.actor,
            "current_state": current_state,
            "proposed_state": target_state,
            "package_hash": package_hash,
            "plan_hash": plan_hash,
            "requested_permission_count": len(resolution.requested),
            "approved_permission_count": len(resolution.approved),
            "effective_permission_count": 0,
            "execution_enabled": False,
        },
    )
    return plan


def approve_transition(request: AddonTransitionApprovalRequest) -> dict[str, Any]:
    with _LOCK:
        record = _PLANS.get(request.plan_id)
        if record is None:
            _audit_refusal("transition_approval", "unknown_plan")
            return {"approved": False, "reason_code": "unknown_plan", "execution_enabled": False}
        if record.applied_at is not None:
            _audit_refusal("transition_approval", "plan_already_applied", record.payload)
            return {"approved": False, "reason_code": "plan_already_applied", "execution_enabled": False}
        if _now() >= record.expires_at:
            _audit_refusal("transition_approval", "plan_expired", record.payload)
            return {"approved": False, "reason_code": "plan_expired", "execution_enabled": False}
        if not compare_digest(request.plan_hash, str(record.payload["plan_hash"])):
            _audit_refusal("transition_approval", "plan_hash_mismatch", record.payload)
            return {"approved": False, "reason_code": "plan_hash_mismatch", "execution_enabled": False}
        if not request.operator_confirmed or request.confirmation != EXPECTED_CONFIRMATION:
            _audit_refusal("transition_approval", "explicit_confirmation_required", record.payload)
            return {"approved": False, "reason_code": "explicit_confirmation_required", "execution_enabled": False}
        if request.actor != record.payload["actor"]:
            _audit_refusal("transition_approval", "actor_mismatch", record.payload)
            return {"approved": False, "reason_code": "actor_mismatch", "execution_enabled": False}
        approval_id = f"addon_approval_{uuid4().hex[:16]}"
        token = token_urlsafe(32)
        expires_at = min(record.expires_at, _now() + timedelta(seconds=APPROVAL_TTL_SECONDS))
        _APPROVALS[approval_id] = _ApprovalRecord(
            approval_id=approval_id,
            plan_id=request.plan_id,
            plan_hash=request.plan_hash,
            token=token,
            actor=request.actor,
            expires_at=expires_at,
        )
    append_audit(
        "transition_approval",
        "approved",
        addon_id=str(record.payload["addon_id"]),
        version=str(record.payload["version"]),
        request_id=str(record.payload["request_id"]),
        operation_id=str(record.payload["operation_id"]),
        details={"actor": request.actor, "plan_hash": request.plan_hash, "execution_enabled": False},
    )
    return {
        "approved": True,
        "approval_id": approval_id,
        "approval_token": token,
        "plan_id": request.plan_id,
        "plan_hash": request.plan_hash,
        "expires_at_utc": _iso(expires_at),
        "one_time": True,
        "execution_enabled": False,
        "warning": "Approval authorizes only the exact non-executing state change in this plan.",
    }


def apply_transition(request: AddonTransitionApplyRequest) -> dict[str, Any]:
    with _LOCK:
        plan_record = _PLANS.get(request.plan_id)
        approval = _APPROVALS.get(request.approval_id)
        if plan_record is None:
            _audit_refusal("transition_apply", "unknown_plan")
            return {"ok": False, "reason_code": "unknown_plan", "execution_enabled": False}
        if approval is None:
            _audit_refusal("transition_apply", "unknown_approval", plan_record.payload)
            return {"ok": False, "reason_code": "unknown_approval", "execution_enabled": False}
        if plan_record.applied_at is not None:
            _audit_refusal("transition_apply", "plan_already_applied", plan_record.payload)
            return {"ok": False, "reason_code": "plan_already_applied", "execution_enabled": False}
        if _now() >= plan_record.expires_at:
            _audit_refusal("transition_apply", "plan_expired", plan_record.payload)
            return {"ok": False, "reason_code": "plan_expired", "execution_enabled": False}
        if approval.consumed_at is not None:
            _audit_refusal("transition_apply", "approval_already_used", plan_record.payload)
            return {"ok": False, "reason_code": "approval_already_used", "execution_enabled": False}
        if _now() >= approval.expires_at:
            _audit_refusal("transition_apply", "approval_expired", plan_record.payload)
            return {"ok": False, "reason_code": "approval_expired", "execution_enabled": False}
        if approval.plan_id != request.plan_id or not compare_digest(approval.plan_hash, request.plan_hash):
            _audit_refusal("transition_apply", "approval_plan_mismatch", plan_record.payload)
            return {"ok": False, "reason_code": "approval_plan_mismatch", "execution_enabled": False}
        if not compare_digest(request.plan_hash, str(plan_record.payload["plan_hash"])):
            _audit_refusal("transition_apply", "plan_hash_mismatch", plan_record.payload)
            return {"ok": False, "reason_code": "plan_hash_mismatch", "execution_enabled": False}
        if not compare_digest(approval.token, request.approval_token):
            _audit_refusal("transition_apply", "approval_token_mismatch", plan_record.payload)
            return {"ok": False, "reason_code": "approval_token_mismatch", "execution_enabled": False}

        payload = plan_record.payload
        if registry_revision() != payload["registry_revision"]:
            approval.consumed_at = _now()
            _audit_refusal("transition_apply", "stale_registry_revision", payload)
            return {"ok": False, "reason_code": "stale_registry_revision", "execution_enabled": False}
        action = str(payload["action"])
        if action == "install_disabled":
            if not plan_record.package_path or hash_package_file(plan_record.package_path) != payload["package_hash"]:
                approval.consumed_at = _now()
                _audit_refusal("transition_apply", "package_hash_changed", payload)
                return {"ok": False, "reason_code": "package_hash_changed", "execution_enabled": False}
            inspection = inspect_addon_package(plan_record.package_path)
            if not inspection.installable or inspection.package_hash != payload["package_hash"]:
                approval.consumed_at = _now()
                _audit_refusal("transition_apply", "package_revalidation_failed", payload)
                return {"ok": False, "reason_code": "package_revalidation_failed", "execution_enabled": False}
        else:
            entry = get_storage_entry(str(payload["addon_id"]), str(payload["version"]))
            current_state = "enabled_limited" if entry and entry.get("status") == "enabled" else str(entry.get("status")) if entry else "missing"
            if not entry or current_state != payload["current_state"] or entry.get("package_hash") != payload["package_hash"]:
                approval.consumed_at = _now()
                _audit_refusal("transition_apply", "stale_or_tampered_state", payload)
                return {"ok": False, "reason_code": "stale_or_tampered_state", "execution_enabled": False}

        approval.consumed_at = _now()
        plan_record.applied_at = approval.consumed_at

    if action == "install_disabled":
        result = stage_validated_package(
            inspection,
            source=plan_record.source,
            approved_permissions=list(payload["approved_permissions"]),
            request_id=str(payload["request_id"]),
            operation_id=str(payload["operation_id"]),
        )
    else:
        result = apply_registry_state(
            str(payload["addon_id"]),
            str(payload["version"]),
            str(payload["proposed_state"]),
            approved_permissions=list(payload["approved_permissions"]),
            expected_state=str(payload["current_state"]),
            expected_package_hash=str(payload["package_hash"]),
            request_id=str(payload["request_id"]),
            operation_id=str(payload["operation_id"]),
            reason=plan_record.reason,
        )
    return {
        **result,
        "plan_id": request.plan_id,
        "plan_hash": request.plan_hash,
        "approval_id": request.approval_id,
        "approval_consumed": True,
        "request_id": payload["request_id"],
        "operation_id": payload["operation_id"],
        "execution_enabled": False,
        "bridge_authority_active": False,
    }


def apply_legacy_exact_request(
    *,
    action: str,
    plan_id: str | None,
    plan_hash: str | None,
    approval_id: str | None,
    approval_token: str | None,
) -> dict[str, Any]:
    if not all((plan_id, plan_hash, approval_id, approval_token)):
        return {
            "ok": False,
            "reason_code": "exact_transition_approval_required",
            "errors": ["Create, review, approve, and apply an exact add-on transition plan first."],
            "execution_enabled": False,
        }
    record = _PLANS.get(str(plan_id))
    if record is None or record.payload.get("action") != action:
        return {"ok": False, "reason_code": "action_plan_mismatch", "errors": ["Approval does not match this action."], "execution_enabled": False}
    return apply_transition(
        AddonTransitionApplyRequest(
            plan_id=str(plan_id),
            plan_hash=str(plan_hash),
            approval_id=str(approval_id),
            approval_token=str(approval_token),
        )
    )


def clear_lifecycle_state_for_tests() -> None:
    with _LOCK:
        _PLANS.clear()
        _APPROVALS.clear()


__all__ = (
    "APPROVAL_TTL_SECONDS",
    "EXPECTED_CONFIRMATION",
    "PLAN_TTL_SECONDS",
    "apply_legacy_exact_request",
    "apply_transition",
    "approve_transition",
    "clear_lifecycle_state_for_tests",
    "plan_transition",
)
