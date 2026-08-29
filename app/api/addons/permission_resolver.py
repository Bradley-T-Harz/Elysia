"""Deny-by-default effective permission resolution for governed add-ons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.api.addons.manifest_validator import load_permission_vocabulary
from app.api.addons.types import AddonPermission


@dataclass(frozen=True)
class PermissionResolution:
    requested: tuple[str, ...]
    approved: tuple[str, ...]
    profile_allowed: tuple[str, ...]
    policy_allowed: tuple[str, ...]
    doctor_proven: tuple[str, ...]
    runtime_available: tuple[str, ...]
    effective: tuple[str, ...]
    denied: tuple[str, ...]
    denied_reasons: dict[str, str]
    revoked: bool
    bridge_ready: bool
    execution_enabled: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "requested_permissions": list(self.requested),
            "approved_permissions": list(self.approved),
            "profile_allowed_permissions": list(self.profile_allowed),
            "policy_allowed_permissions": list(self.policy_allowed),
            "doctor_proven_permissions": list(self.doctor_proven),
            "runtime_available_permissions": list(self.runtime_available),
            "effective_permissions": list(self.effective),
            "denied_permissions": list(self.denied),
            "denied_reasons": dict(self.denied_reasons),
            "revoked": self.revoked,
            "bridge_ready": self.bridge_ready,
            "execution_enabled": self.execution_enabled,
            "permission_widening_allowed": False,
        }


def _permission_keys(requested: Iterable[AddonPermission | dict[str, Any] | str]) -> set[str]:
    keys: set[str] = set()
    for item in requested:
        if isinstance(item, AddonPermission):
            key = item.key
        elif isinstance(item, dict):
            key = str(item.get("key", ""))
        else:
            key = str(item)
        if key.strip():
            keys.add(key.strip())
    return keys


def resolve_effective_permissions(
    requested: Iterable[AddonPermission | dict[str, Any] | str],
    *,
    approved_permissions: Iterable[str] = (),
    active_profiles: Iterable[str] = ("core",),
    policy_allowed_permissions: Iterable[str] = (),
    doctor_proven_permissions: Iterable[str] = (),
    runtime_available_permissions: Iterable[str] = (),
    bridge_ready: bool = False,
    revoked: bool = False,
    vocabulary: dict[str, Any] | None = None,
) -> PermissionResolution:
    """Resolve exact grants; production callers pass no runtime capabilities yet."""
    vocabulary = vocabulary or load_permission_vocabulary()
    definitions = vocabulary.get("permissions", {})
    requested_set = _permission_keys(requested)
    approved_set = {str(item) for item in approved_permissions}
    active_profile_set = {str(item) for item in active_profiles}
    policy_set = {str(item) for item in policy_allowed_permissions}
    doctor_set = {str(item) for item in doctor_proven_permissions}
    runtime_set = {str(item) for item in runtime_available_permissions}

    widening = approved_set - requested_set
    if widening:
        approved_set -= widening

    profile_set: set[str] = set()
    denied_reasons: dict[str, str] = {}
    for key in sorted(requested_set):
        definition = definitions.get(key)
        if not isinstance(definition, dict):
            denied_reasons[key] = "unknown_permission"
            continue
        allowed_profiles = {str(item) for item in definition.get("allowed_profiles", [])}
        if allowed_profiles and not (allowed_profiles & active_profile_set):
            denied_reasons[key] = "profile_not_allowed"
            continue
        profile_set.add(key)

    effective: set[str] = set()
    for key in sorted(requested_set):
        definition = definitions.get(key, {})
        if revoked:
            denied_reasons[key] = "revoked"
        elif str(definition.get("default")) == "blocked":
            denied_reasons[key] = "hard_blocked_by_policy"
        elif key not in approved_set:
            denied_reasons[key] = "not_user_approved"
        elif key not in profile_set:
            denied_reasons.setdefault(key, "profile_not_allowed")
        elif key not in policy_set:
            denied_reasons[key] = "not_policy_allowed"
        elif key not in doctor_set:
            denied_reasons[key] = "doctor_prerequisite_not_proven"
        elif key not in runtime_set:
            denied_reasons[key] = "runtime_capability_unavailable"
        elif not bridge_ready:
            denied_reasons[key] = "governed_bridge_unavailable"
        else:
            effective.add(key)

    for key in sorted(widening):
        denied_reasons[key] = "permission_widening_refused"

    denied = (requested_set | widening) - effective
    return PermissionResolution(
        requested=tuple(sorted(requested_set)),
        approved=tuple(sorted(approved_set)),
        profile_allowed=tuple(sorted(profile_set)),
        policy_allowed=tuple(sorted(policy_set & requested_set)),
        doctor_proven=tuple(sorted(doctor_set & requested_set)),
        runtime_available=tuple(sorted(runtime_set & requested_set)),
        effective=tuple(sorted(effective)),
        denied=tuple(sorted(denied)),
        denied_reasons={key: denied_reasons.get(key, "denied") for key in sorted(denied)},
        revoked=revoked,
        bridge_ready=bridge_ready,
        execution_enabled=bool(effective and bridge_ready and not revoked),
    )


def current_disabled_resolution(
    requested: Iterable[AddonPermission | dict[str, Any] | str],
    *,
    approved_permissions: Iterable[str] = (),
    active_profiles: Iterable[str] = ("core",),
    revoked: bool = False,
) -> PermissionResolution:
    """Resolve current Pass 7 truth: no add-on runtime bridge is enabled."""
    requested_keys = _permission_keys(requested)
    return resolve_effective_permissions(
        requested_keys,
        approved_permissions=approved_permissions,
        active_profiles=active_profiles,
        policy_allowed_permissions=requested_keys,
        doctor_proven_permissions=(),
        runtime_available_permissions=(),
        bridge_ready=False,
        revoked=revoked,
    )


__all__ = ("PermissionResolution", "current_disabled_resolution", "resolve_effective_permissions")
