"""Deterministic local-first model routing for Elysia.

This module turns normalized role and routing policy plus measured local model
truth into a decision object.  Invocation stays in ``core.model_invoker`` so
routing cannot silently launch a model or cross an approval/locality boundary.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


def _model_inventory(model_health: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get("runtime_tag") or ""): dict(item)
        for item in _as_mapping(model_health or {}).get("models", [])
        if isinstance(item, dict) and str(item.get("runtime_tag") or "")
    }


def _role_runtime_candidates(role_entry: Dict[str, Any]) -> List[str]:
    preferred = _normalize_string_list(role_entry.get("preferred_model_runtime_tags"))
    if not preferred:
        preferred = _normalize_string_list(role_entry.get("preferred_model_runtime_tag"))
    return preferred + _normalize_string_list(role_entry.get("fallback_model_runtime_tags"))


def _select_measured_runtime_tag(
    role_entry: Dict[str, Any],
    *,
    model_health: Optional[Dict[str, Any]],
    performance_preference: str,
    ram_mb_ceiling: int | None,
) -> Tuple[str, List[str]]:
    """Choose within a configured role using measured local facts.

    Role and locality policy are resolved before this function.  It never
    crosses roles or selects an external model.  Quality/balanced policy keeps
    the configured order; latency/resource policy may earn an installed,
    healthier, smaller fallback within the same role.
    """
    candidates = _role_runtime_candidates(role_entry)
    inventory = _model_inventory(model_health)
    installed = [tag for tag in candidates if inventory.get(tag, {}).get("installed")]
    pool = installed or candidates
    if not pool:
        return "", ["no_declared_runtime_candidate"]

    reasons = ["configured_role_boundary_preserved"]
    ceiling = int(ram_mb_ceiling) if ram_mb_ceiling is not None else None
    within_ram = [
        tag for tag in pool
        if ceiling is None
        or int(inventory.get(tag, {}).get("expected_ram_mb") or 0) <= ceiling
    ]
    if within_ram:
        pool = within_ram
    else:
        reasons.append("no_candidate_within_declared_ram_ceiling")

    if performance_preference in {"latency", "resource"}:
        def efficiency_key(tag: str) -> Tuple[float, int, int]:
            item = inventory.get(tag, {})
            history = _as_mapping(item.get("history"))
            latency = history.get("median_latency_ms")
            # Measured latency wins when present. Artifact size is the truthful
            # cold-start/resource proxy when no benchmark exists.
            return (
                float(latency) if latency is not None else float("inf"),
                int(item.get("size_bytes") or 2**63 - 1),
                candidates.index(tag),
            )

        selected = min(pool, key=efficiency_key)
        reasons.append(f"{performance_preference}_preference_measured_selection")
    else:
        selected = pool[0]
        reasons.append("configured_quality_order_preserved")

    item = inventory.get(selected, {})
    history = _as_mapping(item.get("history"))
    if item.get("loaded"):
        reasons.append("selected_model_resident")
    if int(history.get("failure_count") or 0) > int(history.get("success_count") or 0):
        healthy_alternatives = [
            tag for tag in pool
            if int(_as_mapping(inventory.get(tag, {}).get("history")).get("success_count") or 0)
            >= int(_as_mapping(inventory.get(tag, {}).get("history")).get("failure_count") or 0)
        ]
        if healthy_alternatives:
            selected = healthy_alternatives[0]
            reasons.append("unhealthy_candidate_bypassed_from_outcome_history")
    return selected, reasons


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


def _normalize_string(value: Any, fallback: str = "") -> str:
    """
    Normalize one value into a stripped string.
    """
    text = str(value or "").strip()
    return text if text else fallback


def _normalize_string_list(values: Any) -> List[str]:
    """
    Normalize a value into a clean list of strings.
    """
    if values is None:
        return []

    if isinstance(values, (list, tuple)):
        normalized: List[str] = []

        for value in values:
            text = str(value).strip()
            if text:
                normalized.append(text)

        return normalized

    text = str(values).strip()
    return [text] if text else []


def _as_mapping(value: Any) -> Dict[str, Any]:
    """
    Return a shallow-copied mapping or an empty dict.
    """
    if not isinstance(value, dict):
        return {}

    return dict(value)


def _get_models_config_sections(configs: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extract normalized model_roles and routing sections from loaded config.
    """
    models_group = _as_mapping(configs.get("models", {}))
    model_roles = _as_mapping(models_group.get("model_roles", {}))
    routing = _as_mapping(models_group.get("routing", {}))
    return model_roles, routing


def _derive_context_flags(
    autonomy_level: int,
    context_flags: Optional[List[str]] = None,
) -> List[str]:
    """
    Build the final routing context flags, including derived autonomy flags.
    """
    derived = set(_normalize_string_list(context_flags))

    canonical_level = max(1, min(5, int(autonomy_level)))
    for level in range(1, canonical_level + 1):
        derived.add(f"autonomy_level_{level}_or_higher")

    return sorted(derived)


def _get_role_entry(
    model_roles_config: Dict[str, Any],
    role_name: str,
) -> Tuple[str, Dict[str, Any]]:
    """
    Resolve one role name from roles or external_helpers.

    Returns:
    - container name: "roles", "external_helpers", or "none"
    - resolved entry mapping
    """
    role_name = _normalize_string(role_name)
    if not role_name:
        return "none", {}

    roles = _as_mapping(model_roles_config.get("roles", {}))
    external_helpers = _as_mapping(model_roles_config.get("external_helpers", {}))

    if role_name in roles:
        return "roles", deepcopy(_as_mapping(roles[role_name]))

    if role_name in external_helpers:
        return "external_helpers", deepcopy(_as_mapping(external_helpers[role_name]))

    return "none", {}


def _select_role_target(role_entry: Dict[str, Any]) -> str:
    """
    Select the most relevant declared target for a role or helper.
    """
    preferred_model = _normalize_string(role_entry.get("preferred_model"))
    if preferred_model:
        return preferred_model

    preferred_service = _normalize_string(role_entry.get("preferred_service"))
    if preferred_service:
        return preferred_service

    preferred_models = _normalize_string_list(role_entry.get("preferred_models"))
    if preferred_models:
        return preferred_models[0]

    fallback_models = _normalize_string_list(role_entry.get("fallback_models"))
    if fallback_models:
        return fallback_models[0]

    return ""


def _merge_route_layer(
    base: Dict[str, Any],
    route_layer: Dict[str, Any],
    layer_label: str,
) -> Dict[str, Any]:
    """
    Merge one routing layer on top of the current routing decision base.
    """
    merged = deepcopy(base)

    if not route_layer:
        return merged

    preferred_role = _normalize_string(route_layer.get("preferred_role"))
    fallback_role = _normalize_string(route_layer.get("fallback_role"))

    if preferred_role:
        merged["preferred_role"] = preferred_role

    if fallback_role:
        merged["fallback_role"] = fallback_role

    if "local_only" in route_layer:
        merged["local_only"] = _coerce_bool(route_layer.get("local_only"), False)

    requirements = _normalize_string_list(route_layer.get("requires"))
    if requirements:
        merged["requires"] = requirements

    applied_layers = list(merged.get("applied_layers", []))
    applied_layers.append(layer_label)
    merged["applied_layers"] = applied_layers

    return merged


def _requirements_met(
    required_flags: List[str],
    available_flags: List[str],
) -> Tuple[bool, List[str]]:
    """
    Check whether all route requirements are satisfied.
    """
    available = set(_normalize_string_list(available_flags))
    required = _normalize_string_list(required_flags)

    unmet = [flag for flag in required if flag not in available]
    return len(unmet) == 0, unmet


def _build_base_route_decision(routing_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the base routing decision from routing defaults.
    """
    defaults = _as_mapping(routing_config.get("defaults", {}))

    return {
        "preferred_role": _normalize_string(defaults.get("primary_role")),
        "fallback_role": _normalize_string(defaults.get("fallback_role")),
        "local_only": _coerce_bool(
            defaults.get("sensitive_work_must_remain_local", False),
            False,
        ),
        "requires": [],
        "applied_layers": ["defaults"],
    }


def _resolve_preferred_and_fallback_roles(
    model_roles_config: Dict[str, Any],
    route_decision: Dict[str, Any],
    allow_silent_cloud_fallback: bool,
    context_flags: List[str],
) -> Dict[str, Any]:
    """
    Resolve the preferred role and, if necessary, fall back deterministically.
    """
    preferred_role = _normalize_string(route_decision.get("preferred_role"))
    fallback_role = _normalize_string(route_decision.get("fallback_role"))
    route_local_only = _coerce_bool(route_decision.get("local_only", False), False)
    required_flags = _normalize_string_list(route_decision.get("requires", []))

    requirements_met, unmet_requirements = _requirements_met(required_flags, context_flags)

    decision_path: List[str] = []
    selected_role = preferred_role
    selected_role_reason = "preferred_role"

    if preferred_role:
        decision_path.append(f"preferred_role={preferred_role}")

    if required_flags:
        decision_path.append("required_flags=" + ", ".join(required_flags))

    if not requirements_met and fallback_role:
        selected_role = fallback_role
        selected_role_reason = "fallback_due_to_unmet_route_requirements"
        decision_path.append(
            "fallback_due_to_unmet_route_requirements=" + ", ".join(unmet_requirements)
        )

    selected_container, selected_entry = _get_role_entry(model_roles_config, selected_role)
    fallback_container, fallback_entry = _get_role_entry(model_roles_config, fallback_role)

    selected_entry_local_only = _coerce_bool(selected_entry.get("local_only", False), False)
    selected_explicit_approval_required = _coerce_bool(
        selected_entry.get("explicit_approval_required", False),
        False,
    )
    selected_enabled_by_default = _coerce_bool(
        selected_entry.get("enabled_by_default", False),
        False,
    )

    selected_is_external = selected_container == "external_helpers"
    selected_is_specialist = selected_role == "optional_specialist"

    explicit_enablement = "explicit_enablement" in context_flags
    explicit_approval = "explicit_approval" in context_flags
    explicit_user_request = "explicit_user_request" in context_flags

    route_blocked = False
    route_block_reasons: List[str] = []

    if route_local_only and selected_is_external:
        route_blocked = True
        route_block_reasons.append("route_requires_local_only")

    if selected_entry_local_only is False and route_local_only:
        route_blocked = True
        route_block_reasons.append("selected_role_is_not_local_enough")

    if selected_is_specialist and not explicit_enablement:
        route_blocked = True
        route_block_reasons.append("specialist_requires_explicit_enablement")

    if selected_is_external:
        if not explicit_approval:
            route_blocked = True
            route_block_reasons.append("external_helper_requires_explicit_approval")

        if not explicit_user_request:
            route_blocked = True
            route_block_reasons.append("external_helper_requires_explicit_user_request")

        if not allow_silent_cloud_fallback:
            decision_path.append("silent_cloud_fallback_forbidden=true")

    if selected_explicit_approval_required and not (explicit_enablement or explicit_approval):
        route_blocked = True
        route_block_reasons.append("selected_role_requires_explicit_approval")

    if not selected_enabled_by_default and not (explicit_enablement or explicit_approval):
        if selected_role in {"optional_fallback", "optional_specialist"} or selected_is_external:
            route_blocked = True
            route_block_reasons.append("selected_role_not_enabled_by_default")

    if route_blocked and fallback_role and fallback_role != selected_role:
        selected_role = fallback_role
        selected_role_reason = "fallback_due_to_role_constraints"
        decision_path.append(
            "fallback_due_to_role_constraints=" + ", ".join(route_block_reasons)
        )
        selected_container, selected_entry = _get_role_entry(model_roles_config, selected_role)
        selected_is_external = selected_container == "external_helpers"
        selected_is_specialist = selected_role == "optional_specialist"
        selected_entry_local_only = _coerce_bool(selected_entry.get("local_only", False), False)
        route_blocked = False
        route_block_reasons = []

    selected_target = _select_role_target(selected_entry)
    fallback_target = _select_role_target(fallback_entry)

    stayed_local = not selected_is_external
    external_routing_forbidden = not allow_silent_cloud_fallback

    allowed = bool(selected_role)
    if selected_is_external and not explicit_approval:
        allowed = False

    if route_local_only and selected_is_external:
        allowed = False

    return {
        "selected_role": selected_role,
        "selected_role_reason": selected_role_reason,
        "selected_role_container": selected_container,
        "selected_target": selected_target,
        "selected_model": selected_target if selected_container == "roles" else "",
        "selected_service": selected_target if selected_container == "external_helpers" else "",
        "selected_runtime": _normalize_string(selected_entry.get("runtime")),
        "selected_role_status": _normalize_string(selected_entry.get("status")),
        "selected_role_local_only": selected_entry_local_only,
        "selected_role_enabled_by_default": _coerce_bool(
            selected_entry.get("enabled_by_default", False),
            False,
        ),
        "selected_role_explicit_approval_required": _coerce_bool(
            selected_entry.get("explicit_approval_required", False),
            False,
        ),
        "selected_role_privacy_risk": _normalize_string(
            selected_entry.get("privacy_risk"),
            "unknown",
        ),
        "selected_role_trust_note": _normalize_string(selected_entry.get("trust_note")),
        "fallback_role": fallback_role,
        "fallback_role_container": fallback_container,
        "fallback_target": fallback_target,
        "requirements_met": requirements_met,
        "unmet_requirements": unmet_requirements,
        "route_local_only": route_local_only,
        "stayed_local": stayed_local,
        "selected_is_specialist": selected_is_specialist,
        "selected_is_external": selected_is_external,
        "external_routing_forbidden": external_routing_forbidden,
        "decision_path": decision_path,
        "allowed": allowed,
        "route_block_reasons": route_block_reasons,
    }


def build_model_routing_decision(
    configs: Dict[str, Any],
    mode: str,
    task_type: str,
    autonomy_level: int = 1,
    context_flags: Optional[List[str]] = None,
    reasoning_gear: str = "standard",
    performance_preference: str = "balanced",
    model_health: Optional[Dict[str, Any]] = None,
    ram_mb_ceiling: int | None = None,
) -> Dict[str, Any]:
    """
    Build one deterministic model-routing decision from normalized config.

    Parameters:
    - configs:
        Full loaded config tree from load_all_configs().
    - mode:
        Runtime mode such as default, tutor, researcher, writer.
    - task_type:
        Routing task label such as tutoring, coding, drafting, research_summary.
    - autonomy_level:
        Current runtime autonomy level.
    - context_flags:
        Explicit routing permission/context flags, for example:
        - explicit_enablement
        - explicit_approval
        - explicit_user_request
        - approved_tool_path
        - explicit_public_source_scope
        - outbound_use_is_logged
        - no_private_memory_authority

    Returns:
    One deterministic routing decision object. This does not launch models yet.
    """
    model_roles_config, routing_config = _get_models_config_sections(configs)

    mode = _normalize_string(mode, "default")
    task_type = _normalize_string(task_type, "conversation")
    routing_mode = _normalize_string(
        routing_config.get("routing_mode"),
        "explicit_local_first_role_governed",
    )

    defaults = _as_mapping(routing_config.get("defaults", {}))
    allow_silent_cloud_fallback = _coerce_bool(
        defaults.get("allow_silent_cloud_fallback", False),
        False,
    )

    available_flags = _derive_context_flags(
        autonomy_level=max(1, min(5, int(autonomy_level))),
        context_flags=context_flags,
    )

    route_decision = _build_base_route_decision(routing_config)

    route_resolution_order = _normalize_string_list(
        routing_config.get("route_resolution_order")
    )
    if not route_resolution_order:
        route_resolution_order = ["mode_route", "task_route", "local_fallback"]

    mode_routes = _as_mapping(routing_config.get("mode_routes", {}))
    task_routes = _as_mapping(routing_config.get("task_routes", {}))

    for layer_name in route_resolution_order:
        if layer_name == "mode_route":
            route_decision = _merge_route_layer(
                route_decision,
                _as_mapping(mode_routes.get(mode, {})),
                f"mode:{mode}",
            )
        elif layer_name == "task_route":
            route_decision = _merge_route_layer(
                route_decision,
                _as_mapping(task_routes.get(task_type, {})),
                f"task:{task_type}",
            )
        elif layer_name == "local_fallback":
            # local_fallback is enforced during final role resolution.
            continue

    normalized_gear = _normalize_string(reasoning_gear, "standard")
    normalized_preference = _normalize_string(performance_preference, "balanced")
    if (
        normalized_gear == "quick"
        and task_type in {"conversation", "explanation", "drafting"}
        and normalized_preference != "quality"
    ):
        route_decision = _merge_route_layer(
            route_decision,
            {
                "preferred_role": "lighter_backup",
                "fallback_role": "primary_general",
                "local_only": True,
            },
            "gear:quick",
        )

    resolved = _resolve_preferred_and_fallback_roles(
        model_roles_config=model_roles_config,
        route_decision=route_decision,
        allow_silent_cloud_fallback=allow_silent_cloud_fallback,
        context_flags=available_flags,
    )
    _, resolved_role_entry = _get_role_entry(
        model_roles_config, str(resolved["selected_role"] or "")
    )
    selected_runtime_tag, measured_selection_reasons = _select_measured_runtime_tag(
        resolved_role_entry,
        model_health=model_health,
        performance_preference=normalized_preference,
        ram_mb_ceiling=ram_mb_ceiling,
    )

    note_parts = [
        "Model routing decision built from normalized model_roles and routing config.",
        f"mode={mode}",
        f"task_type={task_type}",
        f"selected_role={resolved['selected_role'] or 'none'}",
        f"selected_target={resolved['selected_target'] or 'none'}",
        f"stayed_local={resolved['stayed_local']}",
    ]

    if resolved["unmet_requirements"]:
        note_parts.append(
            "unmet_requirements=" + ", ".join(resolved["unmet_requirements"])
        )

    if resolved["route_block_reasons"]:
        note_parts.append(
            "route_block_reasons=" + ", ".join(resolved["route_block_reasons"])
        )

    return {
        "routing_mode": routing_mode,
        "mode": mode,
        "task_type": task_type,
        "autonomy_level": max(1, min(5, int(autonomy_level))),
        "reasoning_gear": normalized_gear,
        "performance_preference": normalized_preference,
        "measured_model_health": deepcopy(model_health or {}),
        "context_flags": available_flags,
        "applied_layers": route_decision.get("applied_layers", []),
        "preferred_role": route_decision.get("preferred_role", ""),
        "selected_role": resolved["selected_role"],
        "selected_role_reason": resolved["selected_role_reason"],
        "selected_role_container": resolved["selected_role_container"],
        "selected_target": resolved["selected_target"],
        "selected_runtime_tag": selected_runtime_tag,
        "measured_selection_reasons": measured_selection_reasons,
        "selected_model": resolved["selected_model"],
        "selected_service": resolved["selected_service"],
        "selected_runtime": resolved["selected_runtime"],
        "selected_role_status": resolved["selected_role_status"],
        "selected_role_local_only": resolved["selected_role_local_only"],
        "selected_role_enabled_by_default": resolved["selected_role_enabled_by_default"],
        "selected_role_explicit_approval_required": resolved[
            "selected_role_explicit_approval_required"
        ],
        "selected_role_privacy_risk": resolved["selected_role_privacy_risk"],
        "selected_role_trust_note": resolved["selected_role_trust_note"],
        "fallback_role": resolved["fallback_role"],
        "fallback_role_container": resolved["fallback_role_container"],
        "fallback_target": resolved["fallback_target"],
        "route_local_only": resolved["route_local_only"],
        "requirements_met": resolved["requirements_met"],
        "unmet_requirements": resolved["unmet_requirements"],
        "stayed_local": resolved["stayed_local"],
        "selected_is_specialist": resolved["selected_is_specialist"],
        "selected_is_external": resolved["selected_is_external"],
        "external_routing_forbidden": resolved["external_routing_forbidden"],
        "decision_path": resolved["decision_path"],
        "allowed": resolved["allowed"],
        "route_block_reasons": resolved["route_block_reasons"],
        "note": " ".join(note_parts),
    }


if __name__ == "__main__":
    demo_configs = {
        "models": {
            "model_roles": {
                "roles": {
                    "primary_general": {
                        "preferred_model": "mistral-small-3.1",
                        "runtime": "ollama",
                        "local_only": True,
                        "enabled_by_default": True,
                        "privacy_risk": "low",
                        "trust_note": "Trust-first local general brain.",
                    },
                    "primary_code": {
                        "preferred_model": "starcoder2-15b-instruct",
                        "runtime": "ollama",
                        "local_only": True,
                        "enabled_by_default": True,
                        "privacy_risk": "low",
                        "trust_note": "Trust-first coding role.",
                    },
                    "lighter_backup": {
                        "preferred_model": "granite-3.3-8b-instruct",
                        "runtime": "ollama",
                        "local_only": True,
                        "enabled_by_default": True,
                        "privacy_risk": "low",
                        "trust_note": "Lightweight backup.",
                    },
                    "optional_specialist": {
                        "preferred_models": [
                            "qwen3-coder-next",
                            "deepseek-coder-v2-16b",
                        ],
                        "runtime": "ollama",
                        "local_only": True,
                        "enabled_by_default": False,
                        "explicit_approval_required": True,
                        "privacy_risk": "moderate",
                        "trust_note": "Optional lab-only specialists.",
                    },
                },
                "external_helpers": {
                    "optional_cloud_consultant": {
                        "preferred_service": "chatgpt",
                        "local_only": False,
                        "enabled_by_default": False,
                        "explicit_approval_required": True,
                        "privacy_risk": "high",
                        "trust_note": "Consultant only, never default.",
                    }
                },
            },
            "routing": {
                "routing_mode": "explicit_local_first_role_governed",
                "defaults": {
                    "primary_role": "primary_general",
                    "fallback_role": "lighter_backup",
                    "allow_silent_cloud_fallback": False,
                    "sensitive_work_must_remain_local": True,
                },
                "mode_routes": {
                    "tutor": {
                        "preferred_role": "primary_general",
                        "fallback_role": "lighter_backup",
                        "local_only": True,
                    },
                },
                "task_routes": {
                    "coding": {
                        "preferred_role": "primary_code",
                        "fallback_role": "primary_general",
                        "local_only": True,
                    },
                    "specialist_task": {
                        "preferred_role": "optional_specialist",
                        "fallback_role": "primary_general",
                        "local_only": True,
                        "requires": [
                            "explicit_enablement",
                        ],
                    },
                },
            },
        }
    }

    print(
        build_model_routing_decision(
            configs=demo_configs,
            mode="tutor",
            task_type="coding",
            autonomy_level=1,
            context_flags=[],
        )
    )
