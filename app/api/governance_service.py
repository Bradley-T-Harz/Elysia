"""
Governance truth-assembling service for the Elysia local API bridge.

This module gathers honest local governance truth from:
- bridge/front-door posture
- canonical config files
- modest service-defined trust-zone summaries
- staged runtime/service availability checks

It validates that truth through GovernanceStateData and returns the final
structured envelope payload expected by app.api.routes.governance.

This module must not become:
- a route module
- a second runtime
- a raw UI wording layer
- a giant policy-resolution engine
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
import logging
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - defensive import guard
    yaml = None

from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.governance.schemas.governance_state import (
    ApprovalGovernanceSummary,
    GovernanceAuthorityLevel,
    GovernanceControl,
    GovernanceControlSource,
    GovernanceControlState,
    GovernanceSourceKind,
    GovernanceStateData,
    JournalingGovernanceSummary,
    LocalityGovernanceSummary,
    MemoryGovernanceSummary,
    RoleAuthorityEntry,
    RoleAuthoritySummary,
    RoutingPolicySummary,
    TrustZoneAccessState,
    TrustZoneSummary,
)
from app.governance.governance_control_registry import (
    fail_closed_governance_control_registry,
    governance_config_hash,
    load_governance_control_registry,
)

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = REPO_ROOT / "config"

MODEL_ROLES_PATH = CONFIG_ROOT / "models" / "model_roles.yaml"
ROUTING_PATH = CONFIG_ROOT / "models" / "routing.yaml"
MEMORY_POLICY_PATH = CONFIG_ROOT / "memory" / "memory_policy.yaml"
APPROVAL_RULES_PATH = CONFIG_ROOT / "policies" / "approval_rules.yaml"
AUTONOMY_LEVELS_PATH = CONFIG_ROOT / "policies" / "autonomy_levels.yaml"

DEFAULT_MEMORY_CLASSES = [
    "working",
    "conversation",
    "project",
    "research",
    "operational",
    "preferences",
    "sealed_private",
    "audit",
]

HUMANIZED_DISPLAY_VALUES = {
    "primary_general": "Primary general",
    "primary_code": "Primary code",
    "lighter_backup": "Lighter backup",
    "optional_fallback": "Optional fallback",
    "optional_specialist": "Optional specialist",
    "approval_governed": "Approval-governed",
    "approval-governed": "Approval-governed",
    "policy_governed_session_journaling": "Policy-governed session journaling",
    "explicit_local_first_role_governed": "Explicit local-first role governance",
    "local_roles_declared_models_installed_not_yet_wired": "Roles declared, models installed, not yet wired",
    "append_only": "Append-only",
    "explicit_only": "Explicit-only",
    "local_only": "Local-only",
    "candidate_declared": "Candidate declared",
    "open_webui": "Open WebUI",
}


def _sentence_case(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    return stripped[:1].upper() + stripped[1:]


def _humanize_display_value(
    value: str | bool | int | float | None,
) -> str | bool | int | float | None:
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped:
        return None

    mapped = HUMANIZED_DISPLAY_VALUES.get(stripped)
    if mapped:
        return mapped

    if "_" in stripped:
        return _sentence_case(stripped.replace("_", " "))

    return stripped


def _should_surface_canonical_value(
    raw_value: str,
    display_value: str | bool | int | float | None,
) -> bool:
    if not isinstance(display_value, str):
        return False

    return display_value != raw_value and (
        len(raw_value) > 24 or raw_value.count("_") >= 3
    )


def _new_request_id(prefix: str = "req") -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:20]}"


def _model_to_payload(model: Any) -> dict[str, Any]:
    dump_method = getattr(model, "model_dump", None)
    if callable(dump_method):
        return dump_method(mode="json")

    dict_method = getattr(model, "dict", None)
    if callable(dict_method):
        return dict_method()

    if isinstance(model, dict):
        return dict(model)

    raise TypeError("Unable to serialize governance model into dictionary form.")


def _build_trace_summary(route_used: str = "get_governance_state") -> TraceSummary:
    return TraceSummary(
        route_used=route_used,
        log_written=False,
        journal_written=False,
    )


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "on", "enabled"}:
            return True
        if normalized in {"false", "no", "n", "off", "disabled"}:
            return False
    return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            coerced = _coerce_str(item)
            if coerced:
                result.append(coerced)
        return result
    return []


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_yaml(path: Path, warnings: list[str], label: str) -> Any:
    if yaml is None:
        warnings.append(
            f"{label} could not be read because PyYAML is not available in this environment."
        )
        return {}

    if not path.exists():
        warnings.append(f"{label} is not present at {path.as_posix()}.")
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)  # type: ignore[union-attr]
    except Exception as exc:  # pragma: no cover - defensive file read path
        warnings.append(f"{label} could not be parsed: {exc}")
        return {}

    return data if data is not None else {}


def _make_source(
    *,
    kind: GovernanceSourceKind,
    label: str,
    path: str | None = None,
    authority_level: GovernanceAuthorityLevel = GovernanceAuthorityLevel.AUTHORITATIVE,
    note: str | None = None,
) -> GovernanceControlSource:
    return GovernanceControlSource(
        kind=kind,
        label=label,
        path=path,
        authority_level=authority_level,
        note=note,
    )


def _make_control(
    *,
    control_id: str,
    label: str,
    value: str | bool | int | float | None,
    state: GovernanceControlState,
    source: GovernanceControlSource,
    detail: str | None = None,
    category: str | None = None,
    authority_note: str | None = None,
) -> GovernanceControl:
    try:
        mutation_rule = load_governance_control_registry().rule_for(control_id)
    except Exception:
        mutation_rule = fail_closed_governance_control_registry().rule_for(control_id)
    resolved_value = _humanize_display_value(value)
    resolved_authority_note = authority_note

    if (
        resolved_authority_note is None
        and isinstance(value, str)
        and _should_surface_canonical_value(value, resolved_value)
    ):
        resolved_authority_note = f"Canonical value: {value}"

    return GovernanceControl(
        control_id=control_id,
        label=label,
        value=resolved_value,
        detail=detail,
        state=state,
        source=source,
        category=category,
        authority_note=resolved_authority_note,
        mutation_classification=mutation_rule.classification,
        mutation_risk=mutation_rule.risk,
        mutation_allowed=mutation_rule.mutation_allowed,
        approval_required=mutation_rule.mutation_allowed,
        mutation_reason=mutation_rule.reason,
        mutation_later_gate=mutation_rule.later_gate,
    )


def _load_main_module() -> Any | None:
    try:
        return importlib.import_module("app.api.main")
    except Exception as exc:  # pragma: no cover - defensive import path
        LOGGER.warning("Unable to import app.api.main for governance summary: %s", exc)
        return None


def _service_available(module_path: str) -> bool:
    try:
        importlib.import_module(module_path)
        return True
    except Exception:
        return False


def _derive_roles_map(raw: Any) -> dict[str, dict[str, Any]]:
    mapping = _as_mapping(raw)
    if not mapping:
        return {}

    roles_candidate = mapping.get("roles")
    if isinstance(roles_candidate, dict):
        return {
            str(key): value
            for key, value in roles_candidate.items()
            if isinstance(value, dict)
        }

    known_role_keys: dict[str, dict[str, Any]] = {}
    for key, value in mapping.items():
        if not isinstance(value, dict):
            continue

        if any(
            marker in value
            for marker in (
                "preferred_model",
                "preferred_models",
                "fallback_models",
                "runtime",
                "local_only",
                "enabled_by_default",
            )
        ):
            known_role_keys[str(key)] = value

    return known_role_keys


def _humanize_key(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _summarize_priority_list(values: list[str], limit: int | None = None) -> str | None:
    filtered = [value for value in values if value]
    if not filtered:
        return None

    if limit is not None and len(filtered) > limit:
        shown = filtered[:limit]
        return " -> ".join(shown) + " -> …"

    return " -> ".join(filtered)


def _first_sentence(value: str | None) -> str | None:
    if not value:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    for marker in (". ", "! ", "? "):
        if marker in stripped:
            head, _sep, _tail = stripped.partition(marker)
            return head.strip() + marker.strip()

    return stripped


def _truncate_text(value: str | None, limit: int = 180) -> str | None:
    if not value:
        return None

    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped

    return stripped[: limit - 1].rstrip() + "…"


def _role_preferred_models(payload: dict[str, Any]) -> list[str]:
    preferred_models = _coerce_str_list(payload.get("preferred_models"))
    if preferred_models:
        return preferred_models

    preferred_model = _coerce_str(payload.get("preferred_model"))
    return [preferred_model] if preferred_model else []


def _role_preferred_runtime_tags(payload: dict[str, Any]) -> list[str]:
    preferred_tags = _coerce_str_list(payload.get("preferred_model_runtime_tags"))
    if preferred_tags:
        return preferred_tags

    preferred_tag = _coerce_str(payload.get("preferred_model_runtime_tag"))
    return [preferred_tag] if preferred_tag else []


def _coerce_display_value(value: Any) -> str | bool | int | float | None:
    bool_value = _coerce_bool(value)
    if bool_value is not None:
        return bool_value

    if isinstance(value, (int, float)):
        return value

    return _coerce_str(value)


def _build_role_detail(
    payload: dict[str, Any],
    *,
    role_key: str | None = None,
) -> str | None:
    parts: list[str] = []

    trust_note = _truncate_text(_first_sentence(_coerce_str(payload.get("trust_note"))), 160)
    if trust_note:
        parts.append(trust_note)

    status = _coerce_str(payload.get("status"))
    if status:
        parts.append(f"Status: {_humanize_display_value(status)}.")

    privacy_risk = _coerce_str(payload.get("privacy_risk"))
    if privacy_risk:
        parts.append(f"Privacy risk: {privacy_risk}.")

    explicit_approval_required = _coerce_bool(payload.get("explicit_approval_required"))
    if explicit_approval_required is not None:
        parts.append(
            "Explicit approval required."
            if explicit_approval_required
            else "No explicit approval required."
        )

    preferred_models = _role_preferred_models(payload)
    preferred_summary = _summarize_priority_list(preferred_models, limit=2)
    if preferred_summary and len(preferred_models) > 1:
        parts.append(f"Priority: {preferred_summary}.")

    activation_rule = _coerce_str(payload.get("activation_rule"))
    if activation_rule:
        parts.append(f"Activation: {_humanize_display_value(activation_rule)}.")

    candidate_notes = _coerce_str_list(payload.get("candidate_notes"))
    if candidate_notes:
        first_note = _truncate_text(_first_sentence(candidate_notes[0]), 150)
        if first_note:
            parts.append(first_note)

    if role_key == "optional_specialist":
        trimmed_parts = parts[:4]
        return " ".join(trimmed_parts) or None

    return " ".join(parts) or None


def _build_external_helper_detail(
    payload: dict[str, Any],
    *,
    helper_key: str | None = None,
) -> str | None:
    parts: list[str] = []

    trust_note = _truncate_text(_first_sentence(_coerce_str(payload.get("trust_note"))), 150)
    if trust_note:
        parts.append(trust_note)

    status = _coerce_str(payload.get("status"))
    if status:
        parts.append(f"Status: {_humanize_display_value(status)}.")

    privacy_risk = _coerce_str(payload.get("privacy_risk"))
    if privacy_risk:
        parts.append(f"Privacy risk: {privacy_risk}.")

    explicit_approval_required = _coerce_bool(payload.get("explicit_approval_required"))
    if explicit_approval_required is not None:
        parts.append(
            "Explicit approval required."
            if explicit_approval_required
            else "No explicit approval required."
        )

    allowed_uses = _coerce_str_list(payload.get("allowed_uses"))
    if allowed_uses:
        parts.append(f"Allowed: {', '.join(allowed_uses[:2])}.")

    forbidden_uses = _coerce_str_list(payload.get("forbidden_uses"))
    if forbidden_uses:
        parts.append(f"Forbidden: {', '.join(forbidden_uses[:2])}.")

    service_notes = _coerce_str_list(payload.get("service_notes"))
    if service_notes:
        first_note = _truncate_text(_first_sentence(service_notes[0]), 140)
        if first_note:
            parts.append(first_note)

    if helper_key == "optional_cloud_consultant":
        trimmed_parts = parts[:4]
        return " ".join(trimmed_parts) or None

    return " ".join(parts) or None

def _pick_default_role(raw: Any, roles_map: dict[str, dict[str, Any]]) -> str | None:
    mapping = _as_mapping(raw)
    explicit = _coerce_str(mapping.get("default_role"))
    if explicit:
        return explicit

    if "primary_general" in roles_map:
        return "primary_general"

    for role_key, payload in roles_map.items():
        if _coerce_bool(payload.get("enabled_by_default")) is True:
            return role_key

    return next(iter(roles_map.keys()), None)


def _build_locality_summary(warnings: list[str]) -> LocalityGovernanceSummary:
    source = _make_source(
        kind=GovernanceSourceKind.BRIDGE_CONSTANT,
        label="Local bridge posture",
        path="app/api/main.py",
        authority_level=GovernanceAuthorityLevel.AUTHORITATIVE,
        note="Derived from local API bridge constants and locality guard posture.",
    )

    main_module = _load_main_module()
    local_only_by_default = None
    allowed_loopback_hosts: list[str] = []
    registered_route_count: int | None = None

    if main_module is not None:
        local_only_by_default = _coerce_bool(
            getattr(main_module, "LOCAL_ONLY_BY_DEFAULT", None)
        )
        allowed_loopback_hosts = sorted(
            _coerce_str_list(getattr(main_module, "ALLOWED_LOOPBACK_HOSTS", []))
        )
        route_modules = getattr(main_module, "ROUTE_MODULES", ())
        if isinstance(route_modules, tuple):
            registered_route_count = len(route_modules)

    controls = [
        _make_control(
            control_id="bridge_local_only_default",
            label="Local-only bridge posture",
            value="enabled" if local_only_by_default else "disabled",
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Non-local clients are rejected by default at the bridge front door.",
            category="locality",
        ),
        _make_control(
            control_id="bridge_loopback_hosts",
            label="Allowed loopback hosts",
            value=len(allowed_loopback_hosts),
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail=", ".join(allowed_loopback_hosts) if allowed_loopback_hosts else None,
            category="locality",
        ),
    ]

    if registered_route_count is not None:
        controls.append(
            _make_control(
                control_id="bridge_registered_route_modules",
                label="Registered route modules declared",
                value=registered_route_count,
                state=GovernanceControlState.DISPLAY_ONLY,
                source=source,
                detail="Reflects route modules declared at the bridge front door.",
                category="locality",
            )
        )

    return LocalityGovernanceSummary(
        local_only_by_default=local_only_by_default,
        outbound_networking_posture="narrow / approval-gated",
        crossed_boundary_default="blocked",
        state=GovernanceControlState.DISPLAY_ONLY,
        source=source,
        controls=controls,
        detail="The bridge remains local-only by default and treats crossed-boundary access as blocked unless deliberately changed later.",
    )


def _build_trust_zone_summaries() -> list[TrustZoneSummary]:
    source = _make_source(
        kind=GovernanceSourceKind.SERVICE_SUMMARY,
        label="Governance trust-zone map",
        path="app/api/governance_service.py",
        authority_level=GovernanceAuthorityLevel.DERIVED,
        note="Phase 1 trust-zone map expressed conservatively for the Governance room.",
    )

    return [
        TrustZoneSummary(
            zone_id="workspace",
            label="Workspace",
            description="Approved working area for active local project and drafting files.",
            access_state=TrustZoneAccessState.BOUNDED,
            assistant_can_read=True,
            assistant_can_write=True,
            user_can_read=True,
            user_can_write=True,
            sealed=False,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Primary bounded working zone for active local work.",
        ),
        TrustZoneSummary(
            zone_id="commons",
            label="Commons",
            description="Shared local reference area for reusable knowledge and non-sensitive artifacts.",
            access_state=TrustZoneAccessState.OPEN,
            assistant_can_read=True,
            assistant_can_write=False,
            user_can_read=True,
            user_can_write=True,
            sealed=False,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Readable by the core, but not treated as a free-write dump.",
        ),
        TrustZoneSummary(
            zone_id="publish_queue",
            label="Publish queue",
            description="Staging area for outbound or publishable artifacts awaiting explicit approval.",
            access_state=TrustZoneAccessState.PLANNED,
            assistant_can_read=False,
            assistant_can_write=False,
            user_can_read=True,
            user_can_write=True,
            sealed=False,
            state=GovernanceControlState.PLANNED,
            source=source,
            detail="Surfaced now so the room can expose outbound-boundary truth without fake live publishing power.",
        ),
        TrustZoneSummary(
            zone_id="sealed_private",
            label="Sealed private / Vault",
            description="Sensitive private area that remains blocked by default.",
            access_state=TrustZoneAccessState.SEALED,
            assistant_can_read=False,
            assistant_can_write=False,
            user_can_read=True,
            user_can_write=True,
            sealed=True,
            state=GovernanceControlState.INACTIVE,
            source=source,
            detail="Sealed zones should never be treated like ordinary workspace memory.",
        ),
        TrustZoneSummary(
            zone_id="audit",
            label="Audit",
            description="Structured trace and governance accountability surfaces.",
            access_state=TrustZoneAccessState.REVIEW_REQUIRED,
            assistant_can_read=True,
            assistant_can_write=True,
            user_can_read=True,
            user_can_write=False,
            sealed=False,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Audit truth exists for accountability; editing it directly is not exposed as a live room control.",
        ),
    ]


def _build_role_authority_summary(warnings: list[str]) -> RoleAuthoritySummary:
    raw = _as_mapping(_read_yaml(MODEL_ROLES_PATH, warnings, "Model role authority file"))
    roles_map = _derive_roles_map(raw)

    source = _make_source(
        kind=GovernanceSourceKind.CONFIG_FILE,
        label="Model role authority",
        path="config/models/model_roles.yaml",
        authority_level=GovernanceAuthorityLevel.CANONICAL,
        note="Canonical model-role authority for role preferences and defaults.",
    )

    runtime_status = _coerce_str(raw.get("runtime_status"))
    default_role = _pick_default_role(raw, roles_map)

    role_entries: list[RoleAuthorityEntry] = []
    for role_key, payload in roles_map.items():
        preferred_models = _role_preferred_models(payload)
        role_entries.append(
            RoleAuthorityEntry(
                role_key=role_key,
                label=_coerce_str(payload.get("label")) or _humanize_key(role_key),
                preferred_model=preferred_models[0] if preferred_models else None,
                fallback_models=_coerce_str_list(payload.get("fallback_models")),
                runtime=_coerce_str(payload.get("runtime")),
                local_only=_coerce_bool(payload.get("local_only")),
                enabled_by_default=_coerce_bool(payload.get("enabled_by_default")),
                state=GovernanceControlState.DISPLAY_ONLY,
                source=source,
                detail=_build_role_detail(payload, role_key=role_key),
            )
        )

    controls = [
        _make_control(
            control_id="model_role_default_role",
            label="Default role",
            value=default_role,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Surfaced from canonical role authority rather than UI invention.",
            category="role_authority_overview",
        ),
        _make_control(
            control_id="model_role_defined_role_count",
            label="Defined roles",
            value=len(role_entries),
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Count of role entries currently visible to the governance service.",
            category="role_authority_overview",
        ),
    ]

    if runtime_status:
        controls.insert(
            0,
            _make_control(
                control_id="model_role_runtime_status",
                label="Role wiring status",
                value=runtime_status,
                state=GovernanceControlState.DISPLAY_ONLY,
                source=source,
                detail="This distinguishes declared role authority from fully wired runtime execution.",
                category="role_authority_overview",
            ),
        )

    external_helpers = _as_mapping(raw.get("external_helpers"))
    for helper_key, payload in external_helpers.items():
        if not isinstance(payload, dict):
            continue

        enabled_by_default = _coerce_bool(payload.get("enabled_by_default"))
        helper_state = (
            GovernanceControlState.DISPLAY_ONLY
            if enabled_by_default
            else GovernanceControlState.INACTIVE
        )

        controls.append(
            _make_control(
                control_id=f"external_helper_{helper_key}",
                label=f"External helper: {_coerce_str(payload.get('label')) or _humanize_key(helper_key)}",
                value=_coerce_str(payload.get("preferred_service")) or helper_key,
                state=helper_state,
                source=source,
                detail=_build_external_helper_detail(payload, helper_key=helper_key),
                category="external_helpers",
            )
        )

    routing_principles = _as_mapping(raw.get("routing_principles"))
    routing_labels = {
        "local_first": "Local first",
        "explicit_role_selection": "Explicit role selection",
        "no_silent_cloud_fallback": "No silent cloud fallback",
        "specialist_models_require_explicit_enablement": "Specialists require explicit enablement",
        "reasoning_before_action": "Reasoning before action",
        "trust_first_core_over_experimental_capability": "Trust-first core over experimental capability",
        "cloud_consultation_requires_explicit_approval": "Cloud consultation requires explicit approval",
        "private_identity_must_remain_local": "Private identity remains local",
    }
    for key, label in routing_labels.items():
        if key not in routing_principles:
            continue

        controls.append(
            _make_control(
                control_id=f"model_role_routing_principle_{key}",
                label=label,
                value=_coerce_bool(routing_principles.get(key)),
                state=GovernanceControlState.DISPLAY_ONLY,
                source=source,
                detail="Surfaced from canonical role authority routing principles.",
                category="routing_principles",
            )
        )

    privacy_defaults = _as_mapping(raw.get("privacy_and_trust_defaults"))
    privacy_labels = {
        "preferred_runtime": "Preferred runtime",
        "preferred_interface": "Preferred interface",
        "default_outbound_model_use_forbidden": "Outbound model use forbidden",
        "default_external_memory_sync_forbidden": "External memory sync forbidden",
        "default_sensitive_project_routing_local_only": "Sensitive project routing local only",
        "model_downloads_should_prefer_open_local_sources": "Prefer open local model sources",
    }
    for key, label in privacy_labels.items():
        if key not in privacy_defaults:
            continue

        controls.append(
            _make_control(
                control_id=f"model_role_privacy_default_{key}",
                label=label,
                value=_coerce_display_value(privacy_defaults.get(key)),
                state=GovernanceControlState.DISPLAY_ONLY,
                source=source,
                detail="Surfaced from canonical privacy and trust defaults.",
                category="privacy_defaults",
            )
        )

    return RoleAuthoritySummary(
        authority_label="Role authority",
        default_role=default_role,
        roles=role_entries,
        controls=controls,
        detail=(
            "Canonical model-role authority remains configuration-governed. "
            "Preferred-model lists are interpreted in declared priority order."
        ),
    )

def _build_routing_summary(warnings: list[str]) -> RoutingPolicySummary:
    raw = _as_mapping(_read_yaml(ROUTING_PATH, warnings, "Routing config file"))

    source = _make_source(
        kind=GovernanceSourceKind.CONFIG_FILE,
        label="Routing policy authority",
        path="config/models/routing.yaml",
        authority_level=GovernanceAuthorityLevel.AUTHORITATIVE,
        note="Routing posture summarized from routing config when available.",
    )

    routing_mode = _coerce_str(raw.get("routing_mode"))
    silent_cloud_fallback_allowed = _coerce_bool(
        raw.get("allow_silent_cloud_fallback")
    )
    sensitive_work_must_remain_local = _coerce_bool(
        raw.get("sensitive_work_must_remain_local")
    )

    local_first = None
    if routing_mode:
        local_first = "local_first" in routing_mode.lower()

    selected_default_role = None
    mode_routes = _as_mapping(raw.get("mode_routes"))
    default_route = _as_mapping(mode_routes.get("default"))
    selected_default_role = _coerce_str(default_route.get("preferred_role"))

    controls = [
        _make_control(
            control_id="routing_mode",
            label="Routing mode",
            value=routing_mode,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Current routing posture should remain downstream of config authority.",
            category="routing_posture",
        ),
        _make_control(
            control_id="routing_silent_cloud_fallback",
            label="Silent cloud fallback",
            value=silent_cloud_fallback_allowed,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Whether cloud fallback may occur silently rather than by explicit enablement.",
            category="routing_posture",
        ),
        _make_control(
            control_id="routing_sensitive_work_local_only",
            label="Sensitive work remains local",
            value=sensitive_work_must_remain_local,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="A key locality rule for the private core.",
            category="routing_posture",
        ),
    ]

    if selected_default_role:
        controls.append(
            _make_control(
                control_id="routing_default_preferred_role",
                label="Default preferred role",
                value=selected_default_role,
                state=GovernanceControlState.DISPLAY_ONLY,
                source=source,
                detail="Preferred default role from routing mode configuration.",
                category="routing_posture",
            )
        )

    return RoutingPolicySummary(
        routing_mode=routing_mode,
        local_first=local_first,
        silent_cloud_fallback_allowed=silent_cloud_fallback_allowed,
        sensitive_work_must_remain_local=sensitive_work_must_remain_local,
        selected_default_role=selected_default_role,
        state=GovernanceControlState.DISPLAY_ONLY,
        source=source,
        controls=controls,
        detail="Routing posture is currently a read-only governance truth surface rather than a live mutable room control.",
    )


def _build_memory_summary(warnings: list[str]) -> MemoryGovernanceSummary:
    raw = _as_mapping(_read_yaml(MEMORY_POLICY_PATH, warnings, "Memory policy file"))

    source = _make_source(
        kind=GovernanceSourceKind.CONFIG_FILE,
        label="Memory policy authority",
        path="config/memory/memory_policy.yaml",
        authority_level=GovernanceAuthorityLevel.AUTHORITATIVE,
        note="Memory policy summary derived from the current memory-policy config.",
    )

    autonomous_updates_enabled = _coerce_bool(
        raw.get("autonomous_updates_enabled")
        or raw.get("autonomous_memory_updates_enabled")
    )
    review_required_for_sensitive_mutations = _coerce_bool(
        raw.get("review_required_for_sensitive_mutations")
        or raw.get("require_review_for_sensitive_mutations")
    )

    known_memory_classes = DEFAULT_MEMORY_CLASSES.copy()

    sealed_memory_posture = (
        _coerce_str(raw.get("sealed_memory_posture"))
        or "sealed/private memory remains more restricted than ordinary memory surfaces"
    )
    retention_posture = (
        _coerce_str(raw.get("retention_posture"))
        or "policy-governed retention"
    )
    promotion_posture = (
        _coerce_str(raw.get("promotion_posture"))
        or "promotion remains governed rather than automatic"
    )

    controls = [
        _make_control(
            control_id="memory_autonomous_updates",
            label="Autonomous memory updates",
            value=autonomous_updates_enabled,
            state=GovernanceControlState.DISPLAY_ONLY
            if autonomous_updates_enabled is not None
            else GovernanceControlState.PLANNED,
            source=source,
            detail="Whether memory mutation initiative is surfaced as enabled in current policy.",
            category="memory",
        ),
        _make_control(
            control_id="memory_sensitive_mutation_review",
            label="Sensitive mutation review",
            value=review_required_for_sensitive_mutations,
            state=GovernanceControlState.DISPLAY_ONLY
            if review_required_for_sensitive_mutations is not None
            else GovernanceControlState.PLANNED,
            source=source,
            detail="Sensitive memory mutations should remain under stricter law than ordinary memory movement.",
            category="memory",
        ),
        _make_control(
            control_id="memory_known_class_count",
            label="Known memory classes",
            value=len(known_memory_classes),
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail=", ".join(known_memory_classes),
            category="memory",
        ),
        _make_control(
            control_id="memory_retention_posture",
            label="Retention posture",
            value=retention_posture,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Retention truth should remain inspectable rather than hidden behind memory automation.",
            category="memory",
        ),
    ]

    return MemoryGovernanceSummary(
        autonomous_updates_enabled=autonomous_updates_enabled,
        review_required_for_sensitive_mutations=review_required_for_sensitive_mutations,
        known_memory_classes=known_memory_classes,
        sealed_memory_posture=sealed_memory_posture,
        retention_posture=retention_posture,
        promotion_posture=promotion_posture,
        state=GovernanceControlState.DISPLAY_ONLY,
        source=source,
        controls=controls,
        detail="Governance should summarize memory law without pretending the room is already a full memory-policy editor.",
    )


def _build_approval_summary(warnings: list[str]) -> ApprovalGovernanceSummary:
    approval_raw = _as_mapping(
        _read_yaml(APPROVAL_RULES_PATH, warnings, "Approval rules file")
    )
    autonomy_raw = _as_mapping(
        _read_yaml(AUTONOMY_LEVELS_PATH, warnings, "Autonomy levels file")
    )

    source = _make_source(
        kind=GovernanceSourceKind.POLICY_FILE,
        label="Approval policy authority",
        path="config/policies/approval_rules.yaml",
        authority_level=GovernanceAuthorityLevel.AUTHORITATIVE,
        note="Approval posture summarized from approval and autonomy policy surfaces.",
    )

    risky_actions_require_approval = _coerce_bool(
        approval_raw.get("risky_actions_require_approval")
    )
    destructive_actions_require_approval = _coerce_bool(
        approval_raw.get("destructive_actions_require_approval")
    )
    outbound_actions_allowed = _coerce_bool(
        approval_raw.get("outbound_actions_allowed")
    )

    approval_mode = (
        _coerce_str(approval_raw.get("approval_mode"))
        or _coerce_str(autonomy_raw.get("default_autonomy_level"))
        or "approval-governed"
    )

    controls = [
        _make_control(
            control_id="approval_risky_actions",
            label="Risky actions require approval",
            value=risky_actions_require_approval,
            state=GovernanceControlState.DISPLAY_ONLY
            if risky_actions_require_approval is not None
            else GovernanceControlState.PLANNED,
            source=source,
            detail="Risky actions should not silently cross permission boundaries.",
            category="approval",
        ),
        _make_control(
            control_id="approval_destructive_actions",
            label="Destructive actions require approval",
            value=destructive_actions_require_approval,
            state=GovernanceControlState.DISPLAY_ONLY
            if destructive_actions_require_approval is not None
            else GovernanceControlState.DISPLAY_ONLY,
            source=source,
            detail="Destructive operations should remain approval-gated even if other powers deepen later.",
            category="approval",
        ),
        _make_control(
            control_id="approval_outbound_actions_allowed",
            label="Outbound actions allowed",
            value=outbound_actions_allowed,
            state=GovernanceControlState.DISPLAY_ONLY
            if outbound_actions_allowed is not None
            else GovernanceControlState.PLANNED,
            source=source,
            detail="Useful for distinguishing inward drafting from outward execution.",
            category="approval",
        ),
    ]

    autonomy_levels_defined = _coerce_str_list(autonomy_raw.get("levels"))
    if autonomy_levels_defined:
        controls.append(
            _make_control(
                control_id="approval_autonomy_levels_defined",
                label="Autonomy levels surfaced",
                value=len(autonomy_levels_defined),
                state=GovernanceControlState.DISPLAY_ONLY,
                source=source,
                detail=", ".join(autonomy_levels_defined),
                category="approval",
            )
        )

    return ApprovalGovernanceSummary(
        approval_mode=approval_mode,
        risky_actions_require_approval=risky_actions_require_approval,
        destructive_actions_require_approval=destructive_actions_require_approval,
        outbound_actions_allowed=outbound_actions_allowed,
        state=GovernanceControlState.DISPLAY_ONLY,
        source=source,
        controls=controls,
        detail="Approval posture is a constitutional truth surface and should never be flattened into decorative toggles.",
    )


def _build_journaling_summary(warnings: list[str]) -> JournalingGovernanceSummary:
    memory_raw = _as_mapping(_read_yaml(MEMORY_POLICY_PATH, warnings, "Memory policy file"))

    journaling_source = _make_source(
        kind=GovernanceSourceKind.SERVICE_SUMMARY,
        label="Journaling and audit summary",
        path="app/api/governance_service.py",
        authority_level=GovernanceAuthorityLevel.DERIVED,
        note="Journaling posture summarized conservatively from memory policy and live service availability.",
    )

    scaffold_journaling = _as_mapping(memory_raw.get("scaffold_journaling"))
    journaling_enabled = (
        _coerce_bool(scaffold_journaling.get("enabled"))
        if scaffold_journaling
        else True
    )
    journal_mode = (
        _coerce_str(scaffold_journaling.get("mode"))
        or "policy_governed_session_journaling"
    )
    request_trace_enabled = _service_available("app.api.request_trace_service")
    audit_append_only = True

    controls = [
        _make_control(
            control_id="journaling_enabled",
            label="Journaling enabled",
            value=journaling_enabled,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=journaling_source,
            detail="Session journaling remains policy-governed rather than decorative.",
            category="journaling",
        ),
        _make_control(
            control_id="journaling_mode",
            label="Journal mode",
            value=journal_mode,
            state=GovernanceControlState.DISPLAY_ONLY,
            source=journaling_source,
            detail="Summarized from current memory policy posture where available.",
            category="journaling",
        ),
        _make_control(
            control_id="journaling_request_trace",
            label="Request trace service available",
            value=request_trace_enabled,
            state=GovernanceControlState.DISPLAY_ONLY
            if request_trace_enabled
            else GovernanceControlState.INACTIVE,
            source=journaling_source,
            detail="Current request trace availability for the trust surfaces.",
            category="journaling",
        ),
        _make_control(
            control_id="journaling_audit_posture",
            label="Audit posture",
            value="append_only",
            state=GovernanceControlState.DISPLAY_ONLY,
            source=journaling_source,
            detail="Audit truth should be more append-oriented than casually editable.",
            category="journaling",
        ),
    ]

    return JournalingGovernanceSummary(
        journaling_enabled=journaling_enabled,
        journal_mode=journal_mode,
        request_trace_enabled=request_trace_enabled,
        audit_append_only=audit_append_only,
        state=GovernanceControlState.DISPLAY_ONLY,
        source=journaling_source,
        controls=controls,
        detail="Journaling and audit posture are surfaced as governance truth, not as hidden backend magic.",
    )


def _unique_sources(sources: list[GovernanceControlSource]) -> list[GovernanceControlSource]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[GovernanceControlSource] = []

    for source in sources:
        key = (
            source.kind.value,
            source.label,
            source.path or "",
            source.authority_level.value,
            source.note or "",
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)

    return unique


def _unique_controls(controls: list[GovernanceControl]) -> list[GovernanceControl]:
    seen: set[str] = set()
    unique: list[GovernanceControl] = []

    for control in controls:
        if control.control_id in seen:
            continue
        seen.add(control.control_id)
        unique.append(control)

    return unique


def _collect_control_states(
    *,
    locality_summary: LocalityGovernanceSummary,
    role_authority: RoleAuthoritySummary,
    routing_summary: RoutingPolicySummary,
    memory_summary: MemoryGovernanceSummary,
    approval_summary: ApprovalGovernanceSummary,
    journaling_summary: JournalingGovernanceSummary,
    trust_zones: list[TrustZoneSummary],
) -> list[GovernanceControl]:
    controls: list[GovernanceControl] = []

    controls.extend(locality_summary.controls)
    controls.extend(role_authority.controls)
    controls.extend(routing_summary.controls)
    controls.extend(memory_summary.controls)
    controls.extend(approval_summary.controls)
    controls.extend(journaling_summary.controls)

    for role in role_authority.roles:
        controls.append(
            _make_control(
                control_id=f"role_{role.role_key}",
                label=f"Role: {role.label}",
                value=role.preferred_model or role.role_key,
                state=role.state,
                source=role.source,
                detail=role.detail,
                category="role_entries",
            )
        )

    for zone in trust_zones:
        controls.append(
            _make_control(
                control_id=f"trust_zone_{zone.zone_id}",
                label=f"Trust zone: {zone.label}",
                value=zone.access_state.value,
                state=zone.state,
                source=zone.source,
                detail=zone.detail or zone.description,
                category="trust_zones",
            )
        )

    return _unique_controls(controls)


def _collect_control_sources(
    *,
    locality_summary: LocalityGovernanceSummary,
    role_authority: RoleAuthoritySummary,
    routing_summary: RoutingPolicySummary,
    memory_summary: MemoryGovernanceSummary,
    approval_summary: ApprovalGovernanceSummary,
    journaling_summary: JournalingGovernanceSummary,
    trust_zones: list[TrustZoneSummary],
    controls: list[GovernanceControl],
) -> list[GovernanceControlSource]:
    sources: list[GovernanceControlSource] = [
        locality_summary.source,
        role_authority.controls[0].source if role_authority.controls else _make_source(
            kind=GovernanceSourceKind.SERVICE_SUMMARY,
            label="Role authority summary",
            path="app/api/governance_service.py",
            authority_level=GovernanceAuthorityLevel.DERIVED,
        ),
        routing_summary.source,
        memory_summary.source,
        approval_summary.source,
        journaling_summary.source,
    ]

    sources.extend(zone.source for zone in trust_zones)
    sources.extend(role.source for role in role_authority.roles)
    sources.extend(control.source for control in controls)

    return _unique_sources(sources)


def get_governance_state() -> dict[str, Any]:
    """
    Build and return the structured governance-state envelope payload.

    The returned dictionary is the final bridge envelope payload expected by the
    thin governance route.
    """
    request_id = _new_request_id()
    warnings: list[str] = []
    errors: list[str] = []

    locality_summary = _build_locality_summary(warnings)
    trust_zones = _build_trust_zone_summaries()
    role_authority = _build_role_authority_summary(warnings)
    routing_summary = _build_routing_summary(warnings)
    memory_summary = _build_memory_summary(warnings)
    approval_summary = _build_approval_summary(warnings)
    journaling_summary = _build_journaling_summary(warnings)

    control_states = _collect_control_states(
        locality_summary=locality_summary,
        role_authority=role_authority,
        routing_summary=routing_summary,
        memory_summary=memory_summary,
        approval_summary=approval_summary,
        journaling_summary=journaling_summary,
        trust_zones=trust_zones,
    )
    control_sources = _collect_control_sources(
        locality_summary=locality_summary,
        role_authority=role_authority,
        routing_summary=routing_summary,
        memory_summary=memory_summary,
        approval_summary=approval_summary,
        journaling_summary=journaling_summary,
        trust_zones=trust_zones,
        controls=control_states,
    )

    try:
        mutation_registry = load_governance_control_registry()
    except Exception as exc:
        mutation_registry = fail_closed_governance_control_registry()
        warnings.append(
            "Governance mutation registry is unavailable; all mutation remains fail-closed "
            f"({type(exc).__name__})."
        )

    control_payloads = [_model_to_payload(control) for control in control_states]
    config_hash = governance_config_hash(control_payloads, registry=mutation_registry)
    mutation_summary: dict[str, int] = {}
    for control in control_states:
        classification = str(control.mutation_classification.value)
        mutation_summary[classification] = mutation_summary.get(classification, 0) + 1

    data_model = GovernanceStateData(
        locality_summary=locality_summary,
        trust_zones=trust_zones,
        role_authority=role_authority,
        routing_summary=routing_summary,
        memory_summary=memory_summary,
        approval_summary=approval_summary,
        journaling_summary=journaling_summary,
        control_states=control_states,
        control_sources=control_sources,
        generated_at_utc=_now_utc(),
        governance_note=(
            "Governance should expose rules of the house honestly. "
            "Pass 3 exposes exact mutability classes; no production control is "
            "live-editable until its authoritative adapter and safety proof exist."
        ),
        governance_config_hash=config_hash,
        mutation_contract_version=mutation_registry.contract_version,
        mutation_summary=mutation_summary,
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="governance_state",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=warnings,
        errors=errors,
        trace_summary=_build_trace_summary(),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


def plan_governance_change(payload: Any) -> dict[str, Any]:
    """Delegate exact planning to the narrow mutation service."""
    from app.api.governance_mutation_service import plan_governance_change as plan_change

    return plan_change(payload)


def apply_governance_change(payload: Any) -> dict[str, Any]:
    """Delegate exact approved apply to the narrow mutation service."""
    from app.api.governance_mutation_service import apply_governance_change as apply_change

    return apply_change(payload)


def restore_governance_change(payload: Any) -> dict[str, Any]:
    """Delegate exact approved restore to the narrow mutation service."""
    from app.api.governance_mutation_service import restore_governance_change as restore_change

    return restore_change(payload)


def resolve_approval_request(payload: Any) -> dict[str, Any]:
    """Resolve an exact pending Governance approval; unknown requests fail closed."""
    from app.api.governance_mutation_service import resolve_governance_approval

    return resolve_governance_approval(payload)
