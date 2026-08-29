"""
Elysia config loader scaffold.

This module loads YAML configuration from the project's config/ tree so
the runtime can begin using real policy and routing files instead of
hardcoded assumptions.

Memory policy config and model config are also normalized here so
downstream runtime code can operate on safer, deterministic scaffold
policy shapes.
"""

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_ROOT = PROJECT_ROOT / "config"


def load_yaml_file(path: Path) -> Dict[str, Any]:
    """
    Load one YAML file and return its top-level dictionary.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Expected a top-level mapping in: {path}")

    return data


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """
    Coerce a value into a boolean with light string handling.
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
        lowered = value.strip().lower()

        if lowered in {"true", "1", "yes", "on"}:
            return True

        if lowered in {"false", "0", "no", "off"}:
            return False

    return bool(value)


def _normalize_string_value(value: Any) -> str:
    """
    Normalize one value into a stripped string.
    """
    return str(value or "").strip()


def _normalize_override_mapping(
    overrides: Any,
    require_numeric_keys: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Normalize an override container into a clean dict-of-dicts.
    """
    if not isinstance(overrides, dict):
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}

    for key, value in overrides.items():
        key_str = str(key)

        if require_numeric_keys and not key_str.isdigit():
            continue

        if not isinstance(value, dict):
            continue

        normalized[key_str] = deepcopy(value)

    return normalized


def _normalize_string_list(values: Any) -> List[str]:
    """
    Normalize a value into a clean list of strings.
    """
    if values is None:
        return []

    if isinstance(values, (list, tuple)):
        normalized = []

        for value in values:
            text = str(value).strip()
            if text:
                normalized.append(text)

        return normalized

    text = str(values).strip()
    return [text] if text else []


def _normalize_memory_class_policy_entry(entry: Any) -> Dict[str, Any]:
    """
    Normalize one memory-class policy entry into a safer deterministic shape.
    """
    if not isinstance(entry, dict):
        return {}

    normalized = deepcopy(entry)

    if "allowed_memory_classes" in normalized:
        normalized["allowed_memory_classes"] = _normalize_string_list(
            normalized.get("allowed_memory_classes"),
        )

    if "disallowed_memory_classes" in normalized:
        normalized["disallowed_memory_classes"] = _normalize_string_list(
            normalized.get("disallowed_memory_classes"),
        )

    if "primary_memory_class" in normalized and normalized["primary_memory_class"] is not None:
        normalized["primary_memory_class"] = _normalize_string_value(
            normalized["primary_memory_class"]
        )

    if "forced_memory_class" in normalized and normalized["forced_memory_class"] is not None:
        normalized["forced_memory_class"] = _normalize_string_value(
            normalized["forced_memory_class"]
        )

    return normalized


def _normalize_memory_class_policy_mapping(
    overrides: Any,
    require_numeric_keys: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Normalize a memory-class policy container into a clean dict-of-dicts.
    """
    if not isinstance(overrides, dict):
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}

    for key, value in overrides.items():
        key_str = str(key)

        if require_numeric_keys and not key_str.isdigit():
            continue

        normalized_entry = _normalize_memory_class_policy_entry(value)

        if not normalized_entry:
            continue

        normalized[key_str] = normalized_entry

    return normalized


def _normalize_scaffold_retrieval_config(scaffold_retrieval: Any) -> Dict[str, Any]:
    """
    Normalize scaffold retrieval config into a safer deterministic shape.
    """
    if not isinstance(scaffold_retrieval, dict):
        return {}

    normalized = deepcopy(scaffold_retrieval)

    normalized["mode_overrides"] = _normalize_override_mapping(
        normalized.get("mode_overrides", {}),
    )
    normalized["autonomy_overrides"] = _normalize_override_mapping(
        normalized.get("autonomy_overrides", {}),
        require_numeric_keys=True,
    )

    return normalized


def _normalize_scaffold_journaling_config(scaffold_journaling: Any) -> Dict[str, Any]:
    """
    Normalize scaffold journaling config into a safer deterministic shape.
    """
    if not isinstance(scaffold_journaling, dict):
        return {}

    normalized = deepcopy(scaffold_journaling)

    normalized["mode_overrides"] = _normalize_override_mapping(
        normalized.get("mode_overrides", {}),
    )
    normalized["autonomy_overrides"] = _normalize_override_mapping(
        normalized.get("autonomy_overrides", {}),
        require_numeric_keys=True,
    )
    normalized["boundary_overrides"] = _normalize_override_mapping(
        normalized.get("boundary_overrides", {}),
    )

    return normalized


def _normalize_scaffold_memory_classes_config(
    scaffold_memory_classes: Any,
) -> Dict[str, Any]:
    """
    Normalize scaffold memory-classes config into a safer deterministic shape.
    """
    if not isinstance(scaffold_memory_classes, dict):
        return {}

    normalized = deepcopy(scaffold_memory_classes)

    normalized["classes"] = _normalize_memory_class_policy_mapping(
        normalized.get("classes", {}),
    )
    normalized["mode_overrides"] = _normalize_memory_class_policy_mapping(
        normalized.get("mode_overrides", {}),
    )
    normalized["autonomy_overrides"] = _normalize_memory_class_policy_mapping(
        normalized.get("autonomy_overrides", {}),
        require_numeric_keys=True,
    )
    normalized["boundary_overrides"] = _normalize_memory_class_policy_mapping(
        normalized.get("boundary_overrides", {}),
    )

    if "default_memory_class" in normalized and normalized["default_memory_class"] is not None:
        normalized["default_memory_class"] = _normalize_string_value(
            normalized["default_memory_class"]
        )

    if "fallback_memory_class" in normalized and normalized["fallback_memory_class"] is not None:
        normalized["fallback_memory_class"] = _normalize_string_value(
            normalized["fallback_memory_class"]
        )

    return normalized


def normalize_memory_policy_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize memory policy config into a safer deterministic shape.

    Current scaffold behavior:
    - leaves unrelated memory policy sections alone
    - ensures scaffold_retrieval is a mapping before using it
    - ensures scaffold_journaling is a mapping before using it
    - ensures scaffold_memory_classes is a mapping before using it
    - normalizes retrieval mode_overrides into a dict of dicts
    - normalizes retrieval autonomy_overrides into a dict of dicts with numeric keys
    - normalizes journaling mode_overrides into a dict of dicts
    - normalizes journaling autonomy_overrides into a dict of dicts with numeric keys
    - normalizes journaling boundary_overrides into a dict of dicts
    - normalizes memory-class classes into a dict of dicts
    - normalizes memory-class mode_overrides into a dict of dicts
    - normalizes memory-class autonomy_overrides into a dict of dicts with numeric keys
    - normalizes memory-class boundary_overrides into a dict of dicts
    """
    normalized = deepcopy(data)

    normalized["scaffold_retrieval"] = _normalize_scaffold_retrieval_config(
        normalized.get("scaffold_retrieval", {}),
    )
    normalized["scaffold_journaling"] = _normalize_scaffold_journaling_config(
        normalized.get("scaffold_journaling", {}),
    )
    normalized["scaffold_memory_classes"] = _normalize_scaffold_memory_classes_config(
        normalized.get("scaffold_memory_classes", {}),
    )

    return normalized


def _normalize_model_role_entry(entry: Any) -> Dict[str, Any]:
    """
    Normalize one model-role entry into a safer deterministic shape.
    """
    if not isinstance(entry, dict):
        return {}

    normalized = deepcopy(entry)

    for field_name in [
        "purpose",
        "status",
        "preferred_model",
        "runtime",
        "privacy_risk",
        "trust_note",
        "activation_rule",
    ]:
        if field_name in normalized and normalized[field_name] is not None:
            normalized[field_name] = _normalize_string_value(normalized[field_name])

    for field_name in [
        "fallback_models",
        "preferred_models",
        "requirements",
        "candidate_notes",
        "allowed_uses",
        "forbidden_uses",
    ]:
        if field_name in normalized:
            normalized[field_name] = _normalize_string_list(
                normalized.get(field_name),
            )

    for field_name in [
        "local_only",
        "signup_required",
        "enabled_by_default",
        "explicit_approval_required",
    ]:
        if field_name in normalized:
            normalized[field_name] = _coerce_bool(
                normalized.get(field_name),
                False,
            )

    return normalized


def _normalize_model_role_mapping(roles: Any) -> Dict[str, Dict[str, Any]]:
    """
    Normalize a model-role container into a clean dict-of-dicts.
    """
    if not isinstance(roles, dict):
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}

    for key, value in roles.items():
        key_str = str(key)
        normalized_entry = _normalize_model_role_entry(value)

        if not normalized_entry:
            continue

        normalized[key_str] = normalized_entry

    return normalized


def normalize_model_roles_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize model_roles config into a safer deterministic shape.
    """
    normalized = deepcopy(data)

    normalized["roles"] = _normalize_model_role_mapping(
        normalized.get("roles", {}),
    )
    normalized["external_helpers"] = _normalize_model_role_mapping(
        normalized.get("external_helpers", {}),
    )

    if "runtime_status" in normalized and normalized["runtime_status"] is not None:
        normalized["runtime_status"] = _normalize_string_value(
            normalized["runtime_status"]
        )

    if "source_canon" in normalized and normalized["source_canon"] is not None:
        normalized["source_canon"] = _normalize_string_value(
            normalized["source_canon"]
        )

    normalized["notes"] = _normalize_string_list(normalized.get("notes"))
    normalized["routing_principles"] = _normalize_string_list(
        normalized.get("routing_principles")
    )

    privacy_defaults = normalized.get("privacy_and_trust_defaults", {})
    if not isinstance(privacy_defaults, dict):
        normalized["privacy_and_trust_defaults"] = {}
    else:
        privacy_defaults = deepcopy(privacy_defaults)

        for field_name in [
            "preferred_runtime",
            "preferred_interface",
        ]:
            if field_name in privacy_defaults and privacy_defaults[field_name] is not None:
                privacy_defaults[field_name] = _normalize_string_value(
                    privacy_defaults[field_name]
                )

        for field_name in [
            "default_outbound_model_use_forbidden",
            "default_external_memory_sync_forbidden",
            "default_sensitive_project_routing_local_only",
            "model_downloads_should_prefer_open_local_sources",
        ]:
            if field_name in privacy_defaults:
                privacy_defaults[field_name] = _coerce_bool(
                    privacy_defaults.get(field_name),
                    False,
                )

        normalized["privacy_and_trust_defaults"] = privacy_defaults

    return normalized


def _normalize_model_route_entry(entry: Any) -> Dict[str, Any]:
    """
    Normalize one routing entry into a safer deterministic shape.
    """
    if not isinstance(entry, dict):
        return {}

    normalized = deepcopy(entry)

    for field_name in [
        "preferred_role",
        "fallback_role",
    ]:
        if field_name in normalized and normalized[field_name] is not None:
            normalized[field_name] = _normalize_string_value(normalized[field_name])

    if "requires" in normalized:
        normalized["requires"] = _normalize_string_list(
            normalized.get("requires"),
        )

    if "local_only" in normalized:
        normalized["local_only"] = _coerce_bool(
            normalized.get("local_only"),
            False,
        )

    return normalized


def _normalize_model_route_mapping(routes: Any) -> Dict[str, Dict[str, Any]]:
    """
    Normalize a route container into a clean dict-of-dicts.
    """
    if not isinstance(routes, dict):
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}

    for key, value in routes.items():
        key_str = str(key)
        normalized_entry = _normalize_model_route_entry(value)

        if not normalized_entry:
            continue

        normalized[key_str] = normalized_entry

    return normalized


def normalize_model_routing_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize routing config into a safer deterministic shape.
    """
    normalized = deepcopy(data)

    if "routing_mode" in normalized and normalized["routing_mode"] is not None:
        normalized["routing_mode"] = _normalize_string_value(
            normalized["routing_mode"]
        )

    defaults = normalized.get("defaults", {})
    if not isinstance(defaults, dict):
        normalized["defaults"] = {}
    else:
        defaults = deepcopy(defaults)

        for field_name in [
            "primary_role",
            "fallback_role",
        ]:
            if field_name in defaults and defaults[field_name] is not None:
                defaults[field_name] = _normalize_string_value(defaults[field_name])

        for field_name in [
            "allow_silent_cloud_fallback",
            "require_explicit_enablement_for_specialists",
            "require_explicit_approval_for_external_helpers",
            "sensitive_work_must_remain_local",
        ]:
            if field_name in defaults:
                defaults[field_name] = _coerce_bool(
                    defaults.get(field_name),
                    False,
                )

        normalized["defaults"] = defaults

    normalized["mode_routes"] = _normalize_model_route_mapping(
        normalized.get("mode_routes", {}),
    )
    normalized["task_routes"] = _normalize_model_route_mapping(
        normalized.get("task_routes", {}),
    )

    normalized["route_resolution_order"] = _normalize_string_list(
        normalized.get("route_resolution_order"),
    )
    normalized["selection_principles"] = _normalize_string_list(
        normalized.get("selection_principles"),
    )
    normalized["notes"] = _normalize_string_list(normalized.get("notes"))
    normalized["source_canons"] = _normalize_string_list(
        normalized.get("source_canons"),
    )

    guards = normalized.get("privacy_and_trust_guards", {})
    if not isinstance(guards, dict):
        normalized["privacy_and_trust_guards"] = {}
    else:
        guards = deepcopy(guards)

        for field_name in [
            "private_identity_must_remain_local",
            "long_term_memory_authority_must_remain_local",
            "sensitive_project_context_must_remain_local",
            "external_consultation_is_consultant_only",
            "specialist_roles_must_never_silently_replace_core_roles",
        ]:
            if field_name in guards:
                guards[field_name] = _coerce_bool(
                    guards.get(field_name),
                    False,
                )

        normalized["privacy_and_trust_guards"] = guards

    return normalized


def load_config_group(group_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Load every YAML file inside config/<group_name>/.
    Returns a mapping like:
    {
        "routing": {...},
        "model_roles": {...},
    }
    """
    group_path = CONFIG_ROOT / group_name

    if not group_path.exists():
        raise FileNotFoundError(f"Config group not found: {group_path}")

    loaded: Dict[str, Dict[str, Any]] = {}

    for path in sorted(group_path.glob("*.yaml")):
        data = load_yaml_file(path)

        if group_name == "memory" and path.stem == "memory_policy":
            data = normalize_memory_policy_config(data)
        elif group_name == "models" and path.stem == "model_roles":
            data = normalize_model_roles_config(data)
        elif group_name == "models" and path.stem == "routing":
            data = normalize_model_routing_config(data)

        loaded[path.stem] = data

    return loaded


def load_all_configs() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Load all main config groups.
    """
    return {
        "models": load_config_group("models"),
        "memory": load_config_group("memory"),
        "policies": load_config_group("policies"),
        "system": load_config_group("system"),
    }


if __name__ == "__main__":
    configs = load_all_configs()
    print("Loaded config groups:", ", ".join(configs.keys()))
    for group_name, group_data in configs.items():
        print(f"{group_name}: {', '.join(sorted(group_data.keys()))}")
