"""Authoritative Pass-IV component/profile graph validation and resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPONENT_GRAPH_PATH = ROOT / "config" / "install" / "component_graph.yaml"
CONTRACT_VERSION = "elysia-component-profile-graph-1.0"

PROFILE_IDS = {
    "core",
    "workstation_research",
    "creator_perception",
    "developer_codev",
    "scientific_engineering_mega",
    "complete_v1_mega",
    "custom",
}

LOCAL_RELEASE_CAPABILITY_IDS = {
    "ELY-ID-001",
    *(f"ELY-MEM-{index:03d}" for index in range(1, 15)),
    "ELY-RET-001", "ELY-RET-002",
    "ELY-COG-001", "ELY-COG-002", "ELY-COG-003",
    "ELY-RES-001",
    "ELY-PROJ-001", "ELY-PROJ-002", "ELY-PROJ-003", "ELY-PROJ-004",
    "ELY-CRE-001", "ELY-CRE-002", "ELY-CRE-003", "ELY-CRE-004",
    "ELY-CON-001", "ELY-CODE-001", "ELY-ADM-001", "ELY-UI-001", "ELY-INS-001",
    "CODEV-001", "CODEV-002", "CODEV-003",
    "X-ID-001", "X-MKT-001", "X-ART-001", "X-PKG-001", "X-BLANK-001",
}

COMPONENT_FIELDS = {
    "component_id",
    "exact_version_digest",
    "owning_profile",
    "required_components",
    "optional_components",
    "conflicts",
    "system_dependencies",
    "runtime_environment",
    "models_assets",
    "license_provenance_record",
    "network_behavior",
    "privilege_requirements",
    "health_probe",
    "cancellation_stop_behavior",
    "update_behavior",
    "uninstall_behavior",
    "data_preservation_behavior",
    "doctor_checks",
    "capability_ids",
}


class ComponentGraphError(ValueError):
    """The authoritative component/profile graph is incomplete or inconsistent."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ComponentGraphError("The component graph could not be loaded.") from exc
    if not isinstance(payload, dict):
        raise ComponentGraphError("The component graph must be a mapping.")
    return payload


def _profile_chain(profile_id: str, profiles: dict[str, Any], trail: tuple[str, ...] = ()) -> list[str]:
    if profile_id in trail:
        raise ComponentGraphError("Profile inheritance contains a cycle.")
    profile = profiles.get(profile_id)
    if not isinstance(profile, dict):
        raise ComponentGraphError("A profile reference is missing.")
    resolved: list[str] = []
    for parent in profile.get("extends", []):
        for item in _profile_chain(parent, profiles, (*trail, profile_id)):
            if item not in resolved:
                resolved.append(item)
    if profile_id not in resolved:
        resolved.append(profile_id)
    return resolved


def validate_component_graph(payload: dict[str, Any]) -> None:
    if payload.get("version") != 1 or payload.get("contract_version") != CONTRACT_VERSION:
        raise ComponentGraphError("The component graph version is unsupported.")
    if payload.get("authority") != "authoritative":
        raise ComponentGraphError("The component graph must be the authoritative installer source.")
    components = payload.get("components")
    profiles = payload.get("profiles")
    if not isinstance(components, dict) or not components:
        raise ComponentGraphError("Components are required.")
    if not isinstance(profiles, dict) or set(profiles) != PROFILE_IDS:
        raise ComponentGraphError("Every supported Pass-IV profile is required.")

    component_ids = set(components)
    capability_owners: dict[str, str] = {}
    for component_id, component in components.items():
        if not isinstance(component, dict) or set(component) != COMPONENT_FIELDS:
            raise ComponentGraphError(f"Component {component_id} does not declare every required field.")
        if component.get("component_id") != component_id:
            raise ComponentGraphError("Component identifiers must match their mapping keys.")
        if component.get("owning_profile") not in PROFILE_IDS - {"custom", "complete_v1_mega"}:
            raise ComponentGraphError("Every component needs a concrete owning profile.")
        for field in ("required_components", "optional_components"):
            values = component.get(field)
            if not isinstance(values, list) or any(item not in component_ids for item in values):
                raise ComponentGraphError(f"Component {component_id} has an invalid component reference.")
            if component_id in values:
                raise ComponentGraphError("A component cannot require itself.")
        for field in ("conflicts", "system_dependencies", "models_assets", "doctor_checks", "capability_ids"):
            if not isinstance(component.get(field), list):
                raise ComponentGraphError(f"Component {component_id} field {field} must be a list.")
        for field in COMPONENT_FIELDS - {
            "component_id", "owning_profile", "required_components", "optional_components",
            "conflicts", "system_dependencies", "models_assets", "doctor_checks", "capability_ids",
        }:
            if not isinstance(component.get(field), str) or not component[field].strip():
                raise ComponentGraphError(f"Component {component_id} field {field} must be truthful text.")
        for capability_id in component["capability_ids"]:
            previous = capability_owners.get(capability_id)
            if previous is not None and previous != component["owning_profile"]:
                raise ComponentGraphError(f"Capability {capability_id} has conflicting profile owners.")
            capability_owners[capability_id] = component["owning_profile"]

    if set(capability_owners) != LOCAL_RELEASE_CAPABILITY_IDS:
        missing = sorted(LOCAL_RELEASE_CAPABILITY_IDS - set(capability_owners))
        extra = sorted(set(capability_owners) - LOCAL_RELEASE_CAPABILITY_IDS)
        raise ComponentGraphError(f"Local capability ownership is incomplete (missing={missing}, extra={extra}).")

    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            raise ComponentGraphError("Profile entries must be mappings.")
        if set(profile) != {"display_name", "extends", "required_components", "optional_components", "hardware_policy", "runtime_projection"}:
            raise ComponentGraphError(f"Profile {profile_id} has an incomplete contract.")
        if not isinstance(profile["extends"], list) or any(parent not in profiles for parent in profile["extends"]):
            raise ComponentGraphError("Profile inheritance is invalid.")
        if any(item not in component_ids for item in [*profile["required_components"], *profile["optional_components"]]):
            raise ComponentGraphError("A profile references an unknown component.")
        projection = profile["runtime_projection"]
        if not isinstance(projection, dict) or set(projection) != {"active_profile", "additional_profiles"}:
            raise ComponentGraphError("A profile runtime projection is invalid.")
        _profile_chain(profile_id, profiles)

    constraints = payload.get("custom_constraints")
    if not isinstance(constraints, dict) or any(
        constraints.get(key) is not True
        for key in (
            "core_components_mandatory", "reject_unknown_components", "reject_conflicts",
            "no_source_forks", "memory_and_governance_mandatory",
        )
    ) or constraints.get("profile_selection_grants_operation_approval") is not False:
        raise ComponentGraphError("Custom selection must preserve Core and the constitutional safety floor.")


def load_component_graph(path: Path = DEFAULT_COMPONENT_GRAPH_PATH) -> dict[str, Any]:
    payload = _load(path)
    validate_component_graph(payload)
    return payload


def resolve_profile_components(
    profile_id: str,
    *,
    custom_components: list[str] | None = None,
    path: Path = DEFAULT_COMPONENT_GRAPH_PATH,
) -> list[str]:
    payload = load_component_graph(path)
    profiles = payload["profiles"]
    components = payload["components"]
    if profile_id not in profiles:
        raise ComponentGraphError("The selected install profile is unknown.")
    resolved: list[str] = []
    for inherited in _profile_chain(profile_id, profiles):
        for component_id in profiles[inherited]["required_components"]:
            if component_id not in resolved:
                resolved.append(component_id)
    if profile_id == "custom":
        allowed = set(profiles["custom"]["optional_components"])
        requested = custom_components or []
        if any(item not in allowed for item in requested):
            raise ComponentGraphError("Custom selection contains an unsupported component.")
        for component_id in requested:
            if component_id not in resolved:
                resolved.append(component_id)

    index = 0
    while index < len(resolved):
        for required in components[resolved[index]]["required_components"]:
            if required not in resolved:
                resolved.append(required)
        index += 1
    return resolved


def public_component_graph_summary(path: Path = DEFAULT_COMPONENT_GRAPH_PATH) -> dict[str, Any]:
    payload = load_component_graph(path)
    return {
        "contract_version": CONTRACT_VERSION,
        "release_target": payload["release_target"],
        "authority": payload["authority"],
        "profiles": [
            {
                "profile_id": profile_id,
                "display_name": profile["display_name"],
                "component_ids": resolve_profile_components(profile_id, path=path),
                "hardware_policy": profile["hardware_policy"],
            }
            for profile_id, profile in payload["profiles"].items()
        ],
        "components": list(payload["components"].values()),
        "capability_count": len(LOCAL_RELEASE_CAPABILITY_IDS),
        "profile_selection_grants_operation_approval": False,
        "source_forks": False,
        "raw_paths_exposed": False,
    }


__all__ = (
    "COMPONENT_FIELDS",
    "CONTRACT_VERSION",
    "ComponentGraphError",
    "DEFAULT_COMPONENT_GRAPH_PATH",
    "LOCAL_RELEASE_CAPABILITY_IDS",
    "load_component_graph",
    "public_component_graph_summary",
    "resolve_profile_components",
    "validate_component_graph",
)
