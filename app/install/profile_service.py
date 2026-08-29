"""Deterministic, non-mutating runtime resolution for Elysia install profiles."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import yaml

from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope

from .dependency_service import (
    DependencyCatalogError,
    inspect_dependency_catalog,
    validate_dependency_catalog,
)
from .paths import resolve_elysia_paths
from .schemas import (
    DependencyStatus,
    DependencyStatusEntry,
    InstallProfileStatusData,
    LocalOverrideSummary,
    ProfileReadiness,
    ProfileResolutionState,
    ProfileSummary,
    ProviderProfileSummary,
    WorkerProfileSummary,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILES_PATH = ROOT / "config" / "install" / "profiles.yaml"
DEFAULT_CATALOG_PATH = ROOT / "config" / "install" / "dependency_catalog.yaml"
_USER_PATHS = resolve_elysia_paths()
DEFAULT_PROFILE_OVERRIDE_PATH = _USER_PATHS.config_dir / "install" / "profiles.yaml"
DEFAULT_MODEL_OVERRIDE_PATH = _USER_PATHS.config_dir / "models" / "local_overrides.yaml"

API_VERSION = "1.0.0"
CONTRACT_VERSION = "elysia-install-profile-runtime-1.0"

PROFILE_IDS = (
    "core", "workstation", "creator", "developer", "semantic_local",
    "neurofabric_cpu", "neurofabric_cuda",
)
CAPABILITY_TIER_IDS = {
    "core_v1_default",
    "optional_v1_profile",
    "v1_lab_or_developer_gated",
    "hard_prohibited_by_default",
}
PROFILE_OVERRIDE_KEYS = {
    "version",
    "contract_version",
    "active_profile",
    "additional_profiles",
    "notes",
}
MODEL_OVERRIDE_KEYS = {
    "version",
    "contract_version",
    "local_only",
    "provider_overrides",
    "model_vault",
    "worker_overrides",
    "policy",
    "notes",
}
ROLE_IDS = {
    "primary_general",
    "primary_code",
    "lighter_backup",
    "optional_specialist",
}
WORKER_FIELDS = {
    "speechforge": {
        "python_path",
        "executable",
        "transcription_model",
        "tts_model",
        "tts_voices",
    },
    "imageforge": {"python_path", "model_root"},
    "videoforge": {"python_path", "model_root"},
    "engineeringforge": {"sandbox_mechanism"},
}
DENY_ONLY_POLICY_KEYS = {
    "allow_network_for_model_acquisition",
    "allow_runtime_network",
    "allow_private_memory_mounts",
    "allow_host_docker_socket",
    "allow_physical_hardware",
}


class InstallProfileConfigError(ValueError):
    """Raised when tracked or local profile contracts cannot be trusted."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise InstallProfileConfigError("A configuration contract could not be loaded.") from exc
    if not isinstance(payload, dict):
        raise InstallProfileConfigError("A configuration contract must be a mapping.")
    return payload


def _validate_profiles(profiles_payload: dict[str, Any], catalog: dict[str, Any]) -> None:
    if profiles_payload.get("version") != 1:
        raise InstallProfileConfigError("Unsupported profile contract version.")
    profiles = profiles_payload.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(PROFILE_IDS):
        raise InstallProfileConfigError("The canonical install profiles are required.")

    groups = catalog["dependency_groups"]
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            raise InstallProfileConfigError("Profile entries must be mappings.")
        extends = profile.get("extends")
        dependency_groups = profile.get("dependency_groups")
        if not isinstance(extends, list) or any(item not in profiles for item in extends):
            raise InstallProfileConfigError("A profile inheritance reference is invalid.")
        if not isinstance(dependency_groups, list) or any(
            group_id not in groups for group_id in dependency_groups
        ):
            raise InstallProfileConfigError("A profile dependency-group reference is invalid.")
        if profile_id == "core" and any(
            not catalog["dependencies"][dependency_id]["allowed_in_core"]
            for group_id in dependency_groups
            for dependency_id in groups[group_id]["dependencies"]
        ):
            raise InstallProfileConfigError("Core references a non-Core dependency.")

    for profile_id in profiles:
        _resolve_profile_ids(profile_id, profiles)

    doctrine = profiles_payload.get("doctrine")
    if not isinstance(doctrine, dict):
        raise InstallProfileConfigError("Profile doctrine is required.")
    if doctrine.get("profile_selection_grants_operation_approval") is not False:
        raise InstallProfileConfigError("Profile selection may not grant approval.")
    if doctrine.get("profiles_may_weaken_safety_floor") is not False:
        raise InstallProfileConfigError("Profiles may not weaken the safety floor.")

    capability_tiers = profiles_payload.get("capability_tiers")
    if not isinstance(capability_tiers, dict) or set(capability_tiers) != CAPABILITY_TIER_IDS:
        raise InstallProfileConfigError("The four capability tiers are required.")
    if any(
        not isinstance(items, list)
        or any(
            not isinstance(item, str) or re.fullmatch(r"[a-z0-9_]+", item) is None
            for item in items
        )
        for items in capability_tiers.values()
    ):
        raise InstallProfileConfigError("Capability tiers must contain public identifiers only.")


def _resolve_profile_ids(
    profile_id: str,
    profiles: dict[str, Any],
    trail: tuple[str, ...] = (),
) -> list[str]:
    if profile_id in trail:
        raise InstallProfileConfigError("Profile inheritance contains a cycle.")
    resolved: list[str] = []
    for parent_id in profiles[profile_id]["extends"]:
        for item in _resolve_profile_ids(parent_id, profiles, (*trail, profile_id)):
            if item not in resolved:
                resolved.append(item)
    if profile_id not in resolved:
        resolved.append(profile_id)
    return resolved


def _validate_profile_override(payload: dict[str, Any]) -> tuple[str, list[str]]:
    if set(payload) - PROFILE_OVERRIDE_KEYS:
        raise InstallProfileConfigError("Local profile override contains unsupported keys.")
    if payload.get("version") != 1:
        raise InstallProfileConfigError("Local profile override version is invalid.")
    active_profile = payload.get("active_profile", "core")
    additional_profiles = payload.get("additional_profiles", [])
    if active_profile not in PROFILE_IDS:
        raise InstallProfileConfigError("Local active profile is invalid.")
    if (
        not isinstance(additional_profiles, list)
        or any(item not in PROFILE_IDS for item in additional_profiles)
        or len(set(additional_profiles)) != len(additional_profiles)
        or active_profile in additional_profiles
    ):
        raise InstallProfileConfigError("Local additional profiles are invalid.")
    return active_profile, list(additional_profiles)


def _bounded_string_or_none(value: Any) -> bool:
    return value is None or (
        isinstance(value, str)
        and 0 < len(value) <= 512
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _validate_model_override(payload: dict[str, Any]) -> None:
    if set(payload) - MODEL_OVERRIDE_KEYS:
        raise InstallProfileConfigError("Local model override contains unsupported keys.")
    if payload.get("version") != 1 or payload.get("local_only") is not True:
        raise InstallProfileConfigError("Local model override must be version 1 and local-only.")

    providers = payload.get("provider_overrides", {})
    if not isinstance(providers, dict) or set(providers) - {"ollama"}:
        raise InstallProfileConfigError("Local provider override is invalid.")
    ollama = providers.get("ollama", {})
    if not isinstance(ollama, dict) or set(ollama) - {"base_url", "role_runtime_tags"}:
        raise InstallProfileConfigError("Local Ollama override is invalid.")
    base_url = ollama.get("base_url")
    if base_url is not None:
        if (
            not isinstance(base_url, str)
            or len(base_url) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in base_url)
        ):
            raise InstallProfileConfigError("Local provider endpoint is invalid.")
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise InstallProfileConfigError("Only credential-free loopback providers are allowed.")
    roles = ollama.get("role_runtime_tags", {})
    if not isinstance(roles, dict) or set(roles) - ROLE_IDS:
        raise InstallProfileConfigError("Local model role mapping is invalid.")
    if any(not _bounded_string_or_none(value) for value in roles.values()):
        raise InstallProfileConfigError("Local model role values are invalid.")

    vault = payload.get("model_vault", {})
    if not isinstance(vault, dict) or set(vault) - {
        "root",
        "permit_authenticated_download_state",
        "provenance_manifest",
    }:
        raise InstallProfileConfigError("Local model-vault override is invalid.")
    if not _bounded_string_or_none(vault.get("root")) or not _bounded_string_or_none(
        vault.get("provenance_manifest")
    ):
        raise InstallProfileConfigError("Local model-vault values are invalid.")
    if vault.get("permit_authenticated_download_state", False) is not False:
        raise InstallProfileConfigError("Authenticated download authority is not allowed here.")

    workers = payload.get("worker_overrides", {})
    if not isinstance(workers, dict) or set(workers) - set(WORKER_FIELDS):
        raise InstallProfileConfigError("Local worker override is invalid.")
    for worker_id, values in workers.items():
        if not isinstance(values, dict) or set(values) - WORKER_FIELDS[worker_id]:
            raise InstallProfileConfigError("Local worker fields are invalid.")
        if any(not _bounded_string_or_none(value) for value in values.values()):
            raise InstallProfileConfigError("Local worker values are invalid.")

    policy = payload.get("policy", {})
    if not isinstance(policy, dict) or set(policy) - DENY_ONLY_POLICY_KEYS:
        raise InstallProfileConfigError("Local policy override is invalid.")
    if any(value is not False for value in policy.values()):
        raise InstallProfileConfigError("Pass 5 local overrides cannot grant authority.")


def _load_profile_selection(path: Path) -> tuple[str, list[str], str, str | None]:
    if not path.exists():
        return "core", [], "tracked_core_default", None
    try:
        active, additional = _validate_profile_override(_load_yaml_mapping(path))
    except InstallProfileConfigError:
        return "core", [], "invalid_local_override_core_fallback", (
            "Local profile selection was invalid; the tracked Core default was used."
        )
    return active, additional, "gitignored_local_override", None


def _configured_model_labels(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    labels: list[str] = []
    configured_roles: list[str] = []
    ollama = payload.get("provider_overrides", {}).get("ollama", {})
    if ollama.get("base_url"):
        labels.append("Local Ollama endpoint configured")
    for role_id, value in sorted(ollama.get("role_runtime_tags", {}).items()):
        if value:
            configured_roles.append(role_id)
            labels.append(f"Model role {role_id} configured")
    vault = payload.get("model_vault", {})
    if vault.get("root"):
        labels.append("Local model-vault root configured")
    if vault.get("provenance_manifest"):
        labels.append("Local provenance manifest configured")
    for worker_id, values in sorted(payload.get("worker_overrides", {}).items()):
        if any(value for value in values.values()):
            labels.append(f"{worker_id} local metadata configured")
    return labels, configured_roles


def _load_model_override(
    path: Path,
) -> tuple[dict[str, Any], str, list[str], list[str], str | None]:
    if not path.exists():
        return {}, "not_configured", [], [], None
    try:
        payload = _load_yaml_mapping(path)
        _validate_model_override(payload)
    except InstallProfileConfigError:
        return {}, "invalid_fail_closed", [], [], (
            "Local model/provider metadata was invalid and was ignored without granting authority."
        )
    labels, configured_roles = _configured_model_labels(payload)
    return payload, "gitignored_local_override", labels, configured_roles, None


def load_local_model_override_values(path: Path | None = None) -> dict[str, Any]:
    """Return validated local path metadata for internal use only.

    The caller must never serialize this mapping into UI, diagnostics, receipts,
    or logs. Invalid or absent local configuration fails closed to an empty
    mapping and grants no authority.
    """
    payload, _, _, _, _ = _load_model_override(path or DEFAULT_MODEL_OVERRIDE_PATH)
    return payload


def _profile_dependency_ids(
    profile_id: str,
    profiles: dict[str, Any],
    catalog: dict[str, Any],
) -> set[str]:
    ids: set[str] = set()
    for resolved_id in _resolve_profile_ids(profile_id, profiles):
        for group_id in profiles[resolved_id]["dependency_groups"]:
            ids.update(catalog["dependency_groups"][group_id]["dependencies"])
    return ids


def _readiness_for_entries(
    entries: list[DependencyStatusEntry],
    *,
    included: bool,
) -> ProfileReadiness:
    if not included:
        return ProfileReadiness.PROFILE_GATED
    required = [entry for entry in entries if entry.required]
    if any(entry.status == DependencyStatus.MISSING for entry in required):
        return ProfileReadiness.DEGRADED
    if any(
        entry.status
        in {
            DependencyStatus.UNKNOWN,
            DependencyStatus.PROFILE_GATED,
            DependencyStatus.LAB_GATED,
            DependencyStatus.DEGRADED,
        }
        for entry in required
    ):
        return ProfileReadiness.UNKNOWN
    return ProfileReadiness.READY


def _worker_summaries(
    *,
    resolved_profile_ids: set[str],
    model_payload: dict[str, Any],
) -> list[WorkerProfileSummary]:
    configured_workers = {
        worker_id
        for worker_id, values in model_payload.get("worker_overrides", {}).items()
        if any(value for value in values.values())
    }
    rows = [
        ("speechforge", "SpeechForge", "creator", False),
        ("imageforge", "ImageForge", "creator", False),
        ("videoforge", "VideoForge", "creator", True),
        ("engineeringforge", "EngineeringForge heavy workers", "creator", True),
    ]
    summaries: list[WorkerProfileSummary] = []
    for worker_id, label, profile_id, lab_only in rows:
        if lab_only:
            status = DependencyStatus.LAB_GATED
            note = "Local sandbox and doctor proof are required before any worker activation."
        elif profile_id not in resolved_profile_ids:
            status = DependencyStatus.PROFILE_GATED
            note = "The owning optional profile is not selected; the worker remains disabled."
        else:
            status = DependencyStatus.UNKNOWN
            note = "Configuration truth is present, but Pass 6 doctor proof is still required."
        summaries.append(
            WorkerProfileSummary(
                worker_id=worker_id,
                label=label,
                profile_id=profile_id,
                status=status,
                configured=worker_id in configured_workers,
                enabled=False,
                doctor_proof_required=True,
                note=note,
            )
        )
    return summaries


def resolve_install_profile_status(
    *,
    profiles_path: Path = DEFAULT_PROFILES_PATH,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    profile_override_path: Path = DEFAULT_PROFILE_OVERRIDE_PATH,
    model_override_path: Path = DEFAULT_MODEL_OVERRIDE_PATH,
) -> tuple[InstallProfileStatusData, list[str]]:
    """Resolve profile truth without installing, downloading, or activating anything."""
    profiles_payload = _load_yaml_mapping(profiles_path)
    catalog = _load_yaml_mapping(catalog_path)
    try:
        validate_dependency_catalog(catalog)
    except DependencyCatalogError as exc:
        raise InstallProfileConfigError("The dependency catalog is invalid.") from exc
    _validate_profiles(profiles_payload, catalog)

    profiles = profiles_payload["profiles"]
    active_profile, additional_profiles, selection_source, selection_warning = (
        _load_profile_selection(profile_override_path)
    )
    model_payload, model_source, configured_labels, configured_roles, model_warning = (
        _load_model_override(model_override_path)
    )
    selected_profile_ids = [active_profile, *additional_profiles]
    resolved_profile_ids: list[str] = []
    for profile_id in selected_profile_ids:
        for resolved_id in _resolve_profile_ids(profile_id, profiles):
            if resolved_id not in resolved_profile_ids:
                resolved_profile_ids.append(resolved_id)
    resolved_set = set(resolved_profile_ids)

    dependencies = inspect_dependency_catalog(
        catalog,
        selected_profile_ids=resolved_set,
    )
    dependency_by_id = {entry.dependency_id: entry for entry in dependencies}

    profile_summaries: list[ProfileSummary] = []
    for profile_id in PROFILE_IDS:
        dependency_ids = _profile_dependency_ids(profile_id, profiles, catalog)
        profile_entries = [dependency_by_id[item] for item in sorted(dependency_ids)]
        included = profile_id in resolved_set
        required_missing = sum(
            entry.required and entry.status == DependencyStatus.MISSING
            for entry in profile_entries
        )
        required_unknown = sum(
            entry.required
            and entry.status
            in {
                DependencyStatus.UNKNOWN,
                DependencyStatus.PROFILE_GATED,
                DependencyStatus.LAB_GATED,
            }
            for entry in profile_entries
        )
        optional_missing = sum(
            not entry.required and entry.status == DependencyStatus.OPTIONAL_MISSING
            for entry in profile_entries
        )
        profile = profiles[profile_id]
        profile_summaries.append(
            ProfileSummary(
                profile_id=profile_id,
                display_name=profile["display_name"],
                purpose=profile["purpose"],
                selected=profile_id in selected_profile_ids,
                included=included,
                default_enabled=profile["default_enabled"],
                maturity=profile["maturity"],
                risk_level=profile["risk_level"],
                readiness=_readiness_for_entries(profile_entries, included=included),
                dependency_count=len(profile_entries),
                required_missing_count=required_missing,
                required_unknown_count=required_unknown,
                optional_missing_count=optional_missing,
                network_runtime_default=profile["network"]["runtime_default"],
                large_downloads_may_occur=profile["large_downloads_may_occur"],
                private_data_leaves_machine_by_default=profile[
                    "private_data_leaves_machine_by_default"
                ],
                doctor_checks=profile["doctor_checks"],
            )
        )

    status_counts = Counter(
        entry.status.value if isinstance(entry.status, DependencyStatus) else entry.status
        for entry in dependencies
    )
    dependency_summary = {
        status.value: int(status_counts.get(status.value, 0))
        for status in DependencyStatus
    }
    missing_core = sorted(
        entry.dependency_id
        for entry in dependencies
        if entry.profile_id == "core" and entry.status == DependencyStatus.MISSING
    )

    resolved_capability_groups: list[str] = []
    for profile_id in resolved_profile_ids:
        for capability_group in profiles[profile_id]["capability_groups"]:
            if capability_group not in resolved_capability_groups:
                resolved_capability_groups.append(capability_group)

    warnings = [warning for warning in (selection_warning, model_warning) if warning]
    active_summary = next(
        profile for profile in profile_summaries if profile.profile_id == active_profile
    )
    if active_summary.required_missing_count:
        warnings.append(
            f"The active profile has {active_summary.required_missing_count} required dependencies missing."
        )
    if active_summary.required_unknown_count:
        warnings.append(
            f"The active profile has {active_summary.required_unknown_count} required checks reserved for Pass 6 doctor proof."
        )

    override_invalid = selection_warning is not None or model_warning is not None
    if override_invalid:
        override_state = "invalid_fail_closed"
        resolution_state = ProfileResolutionState.INVALID
    elif selection_source == "gitignored_local_override" or model_source == "gitignored_local_override":
        override_state = "loaded"
        resolution_state = ProfileResolutionState.RESOLVED
    else:
        override_state = "not_configured"
        resolution_state = ProfileResolutionState.RESOLVED

    ollama_entry = dependency_by_id["ollama_local_provider"]
    data = InstallProfileStatusData(
        resolution_state=resolution_state,
        active_profile_id=active_profile,
        active_profile_label=profiles[active_profile]["display_name"],
        selected_profile_ids=selected_profile_ids,
        resolved_profile_ids=resolved_profile_ids,
        available_profiles=profile_summaries,
        dependencies=dependencies,
        dependency_summary=dependency_summary,
        missing_core_dependency_ids=missing_core,
        resolved_capability_groups=resolved_capability_groups,
        capability_tiers=profiles_payload["capability_tiers"],
        local_overrides=LocalOverrideSummary(
            state=override_state,
            selection_source=selection_source,
            model_override_source=model_source,
            configured_labels=configured_labels,
            configured_count=len(configured_labels),
            raw_values_exposed=False,
            authority_granted=False,
            warning=model_warning or selection_warning,
        ),
        provider_summary=ProviderProfileSummary(
            command_status=ollama_entry.status,
            configured_role_ids=configured_roles,
            local_override_loaded=model_source == "gitignored_local_override",
            network_check_performed=False,
            model_loaded=False,
            selection_authority_available=False,
            note=(
                "Presence uses executable lookup only. Reachability, model availability, "
                "and role switching are not tested or enabled by this contract."
            ),
        ),
        worker_summaries=_worker_summaries(
            resolved_profile_ids=resolved_set,
            model_payload=model_payload,
        ),
        profile_selection_grants_approval=False,
        install_authority_available=False,
        download_authority_available=False,
        worker_start_authority_available=False,
        doctor_executed=False,
        generated_at_utc=_utc_now_iso(),
    )
    return data, warnings


def get_install_profile_status() -> dict[str, Any]:
    """Return the governed GET /status/profiles response envelope."""
    request_id = f"req_profile_{uuid4().hex[:16]}"
    try:
        data, warnings = resolve_install_profile_status()
        degraded = bool(warnings)
        envelope = build_response_envelope(
            status=EnvelopeStatus.DEGRADED if degraded else EnvelopeStatus.OK,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="install_profile_status",
            capability_state=CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            warnings=warnings,
            errors=[],
            trace_summary=TraceSummary(
                route_used="status.profiles",
                log_written=False,
                journal_written=False,
            ),
            data=data,
        )
        return envelope.to_payload()
    except Exception:
        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="install_profile_status",
            capability_state=CapabilityState.UNAVAILABLE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            warnings=[],
            errors=["Install-profile contracts could not be validated."],
            trace_summary=TraceSummary(
                route_used="status.profiles",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()


__all__ = (
    "CONTRACT_VERSION",
    "DEFAULT_CATALOG_PATH",
    "DEFAULT_MODEL_OVERRIDE_PATH",
    "DEFAULT_PROFILE_OVERRIDE_PATH",
    "DEFAULT_PROFILES_PATH",
    "InstallProfileConfigError",
    "get_install_profile_status",
    "resolve_install_profile_status",
)
