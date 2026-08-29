"""Deterministic Adaptive Cognition Governor for Elysia's existing runtime.

The Governor selects effort, never authority. Authorization, privacy, ownership,
Internet, approval, managed-profile, and constitutional gates remain upstream
or independently mandatory.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import re
from typing import Any, Mapping


GOVERNOR_VERSION = "adaptive-cognition-governor-v1"

GEARS = (
    "reflex",
    "quick",
    "standard",
    "deep",
    "deliberative",
    "research_engineering",
)
GEAR_INDEX = {gear: index for index, gear in enumerate(GEARS)}
AUTONOMY_LEVELS = {
    1: "directed",
    2: "assisted",
    3: "collaborative",
    4: "proactive",
    5: "stewarded_initiative",
}

_WORD = re.compile(r"[\w'-]+", re.UNICODE)
_HIGH_STAKES = {
    "diagnosis", "medical", "medication", "dosage", "legal", "lawsuit",
    "contract", "investment", "financial", "suicide", "self-harm",
    "emergency", "explosive", "weapon", "security", "credential",
}
_RESEARCH = {"research", "sources", "cite", "latest", "current", "web", "internet"}
_ENGINEERING = {
    "code", "debug", "repository", "build", "deploy", "database", "schema",
    "benchmark", "architecture", "migration", "package", "gpu", "cuda",
}
_DELIBERATE = {
    "audit", "compare", "tradeoff", "prove", "verify", "threat", "policy",
    "governance", "privacy", "ownership", "contradiction", "uncertainty",
}


@dataclass(frozen=True)
class GovernorInput:
    request_id: str
    message: str
    mode: str
    intent: Mapping[str, Any]
    autonomy_level: int
    domain_overrides: Mapping[str, int] = field(default_factory=dict)
    active_domain: str | None = None
    requested_gear: str = "automatic"
    preferred_gear: str = "automatic"
    privacy_state: str = "normal"
    internet_enabled: bool = False
    managed_profile: bool = False
    stop_active: bool = False
    conflict_count: int = 0
    uncertainty_score: float = 0.0
    verification_failed: bool = False
    retrieval_insufficient: bool = False
    tool_required: bool = False
    research_required: bool = False
    time_budget_ms: int | None = None
    context_window: int = 32768
    context_size: int = 0
    complexity_score: float | None = None
    ambiguity_score: float | None = None
    novelty_score: float | None = None
    stakes: str = "ordinary"
    subproblem_count: int = 1
    retrieval_confidence: float | None = None
    evidence_quality: float | None = None
    expected_data_size: int = 0
    model_health: Mapping[str, Any] = field(default_factory=dict)
    resource_state: Mapping[str, Any] = field(default_factory=dict)
    queue_depth: int = 0
    power_thermal_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GovernorDecision:
    version: str
    request_id: str
    selected_gear: str
    initial_gear: str
    gear_override_applied: bool
    effective_autonomy_level: int
    autonomy_label: str
    resolved_domain_levels: Mapping[str, int]
    capability_policy: Mapping[str, bool]
    context_share: float
    recent_turn_limit: int
    verification_depth: str
    research_allowed: bool
    tool_execution_allowed: bool
    model_role_hint: str
    workload_kind: str
    workload_priority: str
    progress_posture: str
    retrieval_breadth: str
    context_token_budget: int
    output_token_budget: int
    research_budget: Mapping[str, int]
    tool_budget: Mapping[str, int]
    device_preference: str
    foreground: bool
    model_constraints: tuple[str, ...]
    early_exit_eligible: bool
    escalation_conditions: tuple[str, ...]
    reasons: tuple[str, ...]
    authority_increased: bool = False
    content_free: bool = True
    input_digest: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _bounded_level(value: Any) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 1


def effective_autonomy(
    level: int,
    domain_overrides: Mapping[str, int],
    active_domain: str | None = None,
) -> int:
    """Return the strictest applicable domain ceiling."""
    result = _bounded_level(level)
    if active_domain and active_domain in domain_overrides:
        result = min(result, _bounded_level(domain_overrides[active_domain]))
    return result


def resolve_autonomy_policy(
    level: int,
    domain_overrides: Mapping[str, int],
) -> tuple[dict[str, int], dict[str, bool]]:
    """Resolve the five-level scalar into inspectable bounded capabilities."""
    global_level = _bounded_level(level)
    domains = {
        name: min(global_level, _bounded_level(domain_overrides.get(name, global_level)))
        for name in (
            "memory_capture",
            "scientific_promotion",
            "web_initiative",
            "project_initiative",
            "background_cognition",
            "coding_execution",
            "external_mutations",
        )
    }
    policy = {
        # Directed retains explicit work, safety, local context, and audit.
        "direct_user_instructions": True,
        "local_context_retrieval": True,
        "objective_audit_recording": True,
        "explicit_memory_operations": True,
        "user_requested_tools": True,
        "safety_checks": True,
        # Assisted capabilities.
        "propose_next_steps": global_level >= 2,
        "create_memory_candidates": domains["memory_capture"] >= 2,
        "identify_contradictions": global_level >= 2,
        "suggest_research": domains["web_initiative"] >= 2,
        "routine_safe_local_maintenance": global_level >= 2,
        "capture_objective_events": domains["memory_capture"] >= 2,
        # Collaborative capabilities.
        "initiate_bounded_web_research": domains["web_initiative"] >= 3,
        "pursue_bounded_local_substeps": domains["project_initiative"] >= 3,
        "promote_reversible_nonpersonal_conclusions": domains["scientific_promotion"] >= 3,
        "run_bounded_background_cognition": domains["background_cognition"] >= 3,
        "maintain_project_continuity": domains["project_initiative"] >= 3,
        "adapt_models_gears_resources": global_level >= 3,
        # Proactive and Stewarded Initiative remain bounded sustained work.
        "broaden_bounded_investigations": domains["web_initiative"] >= 4,
        "maintain_multiple_project_threads": domains["project_initiative"] >= 4,
        "schedule_visible_background_jobs": domains["background_cognition"] >= 4,
        "create_ideas_inbox_entries": domains["project_initiative"] >= 4,
        "prepare_safe_corrective_actions": global_level >= 4,
        "use_larger_reasoning_budgets": global_level >= 4,
        "sustain_multistage_research_engineering": (
            global_level >= 5
            and max(domains["web_initiative"], domains["coding_execution"]) >= 5
        ),
        "resume_approved_project_goals_after_explicit_restart_review": (
            domains["project_initiative"] >= 5
        ),
        "allocate_compute_for_approved_sustained_work": global_level >= 5,
        "make_reversible_nonpersonal_learning_promotions": (
            domains["scientific_promotion"] >= 5
        ),
        # No public level gains these powers.
        "self_increase_authority": False,
        "bypass_approval": False,
        "unlock_sealed_memory": False,
        "bypass_internet_master": False,
        "send_sensitive_data_without_approval": False,
        "mutate_external_systems_without_approval": False,
        "destructive_actions_without_approval": False,
        "silent_publish_or_push": False,
    }
    return domains, policy


def _input_digest(value: GovernorInput) -> str:
    safe = {
        "request_id": value.request_id,
        "message_sha256": hashlib.sha256(value.message.encode("utf-8")).hexdigest(),
        "mode": value.mode,
        "intent": dict(value.intent),
        "autonomy_level": value.autonomy_level,
        "domain_overrides": dict(value.domain_overrides),
        "active_domain": value.active_domain,
        "requested_gear": value.requested_gear,
        "preferred_gear": value.preferred_gear,
        "privacy_state": value.privacy_state,
        "internet_enabled": value.internet_enabled,
        "managed_profile": value.managed_profile,
        "stop_active": value.stop_active,
        "conflict_count": value.conflict_count,
        "uncertainty_score": round(float(value.uncertainty_score), 4),
        "verification_failed": value.verification_failed,
        "retrieval_insufficient": value.retrieval_insufficient,
        "tool_required": value.tool_required,
        "research_required": value.research_required,
        "time_budget_ms": value.time_budget_ms,
        "context_window": value.context_window,
        "context_size": max(0, int(value.context_size)),
        "complexity_score": value.complexity_score,
        "ambiguity_score": value.ambiguity_score,
        "novelty_score": value.novelty_score,
        "stakes": value.stakes,
        "subproblem_count": max(0, int(value.subproblem_count)),
        "retrieval_confidence": value.retrieval_confidence,
        "evidence_quality": value.evidence_quality,
        "expected_data_size": max(0, int(value.expected_data_size)),
        "model_health": dict(value.model_health),
        "resource_state": dict(value.resource_state),
        "queue_depth": max(0, int(value.queue_depth)),
        "power_thermal_state": dict(value.power_thermal_state),
    }
    return hashlib.sha256(json.dumps(safe, sort_keys=True).encode("utf-8")).hexdigest()


def _initial_gear(value: GovernorInput) -> tuple[str, list[str]]:
    text = value.message.casefold()
    words = _WORD.findall(text)
    tokens = set(words)
    reasons: list[str] = ["cheapest_adequate_start"]
    primary = str(value.intent.get("primary") or "").casefold()
    mode = value.mode.casefold()
    if value.stop_active:
        return "reflex", ["emergency_posture"]
    if value.research_required or tokens & _RESEARCH or mode == "researcher" or primary == "research":
        return "research_engineering", reasons + ["research_evidence_demand"]
    if value.tool_required or tokens & _ENGINEERING or mode in {"coder", "coding", "sysadmin", "ops"}:
        return "research_engineering", reasons + ["engineering_or_tool_demand"]
    if tokens & _HIGH_STAKES:
        return "deliberative", reasons + ["high_stakes_floor"]
    if tokens & _DELIBERATE or len(words) > 220:
        return "deliberative", reasons + ["multi_constraint_deliberation"]
    if len(words) > 100 or any(item in text for item in ("analyze", "reason through", "plan")):
        return "deep", reasons + ["complex_request"]
    if len(words) <= 10 and "?" not in text and "\n" not in text:
        return "reflex", reasons + ["bounded_simple_request"]
    if len(words) <= 35:
        return "quick", reasons + ["short_bounded_request"]
    return "standard", reasons + ["ordinary_request"]


def _raise_to(gear: str, floor: str) -> str:
    return GEARS[max(GEAR_INDEX[gear], GEAR_INDEX[floor])]


def decide_cognition(value: GovernorInput) -> GovernorDecision:
    initial, reasons = _initial_gear(value)
    selected = initial
    override = value.requested_gear if value.requested_gear in GEAR_INDEX else "automatic"
    if override == "automatic" and value.preferred_gear in GEAR_INDEX:
        override = value.preferred_gear
    override_applied = override in GEAR_INDEX
    if override_applied:
        selected = override
        reasons.append("explicit_effort_override")

    words = set(_WORD.findall(value.message.casefold()))
    escalation: list[str] = []
    if words & _HIGH_STAKES:
        selected = _raise_to(selected, "deliberative")
        escalation.append("high_stakes_review_floor")
    if value.conflict_count:
        selected = _raise_to(selected, "deep")
        escalation.append("authorized_source_conflict")
    if float(value.uncertainty_score) >= 0.65:
        selected = _raise_to(selected, "deep")
        escalation.append("high_uncertainty")
    if value.verification_failed:
        selected = _raise_to(selected, "deliberative")
        escalation.append("verification_failure")
    if value.retrieval_insufficient:
        selected = _raise_to(selected, "deep")
        escalation.append("retrieval_insufficient")
    if value.research_required or value.tool_required:
        selected = _raise_to(selected, "research_engineering")
        escalation.append("research_or_tool_requirement")
    if value.ambiguity_score is not None and value.ambiguity_score >= 0.7:
        selected = _raise_to(selected, "deep")
        escalation.append("high_request_ambiguity")
    if value.complexity_score is not None and value.complexity_score >= 0.8:
        selected = _raise_to(selected, "deep")
        escalation.append("high_request_complexity")
    if value.subproblem_count >= 5:
        selected = _raise_to(selected, "deep")
        escalation.append("multiple_subproblems")
    if value.novelty_score is not None and value.novelty_score >= 0.75:
        selected = _raise_to(selected, "deep")
        escalation.append("high_task_novelty")
    if str(value.stakes).casefold() in {"high", "critical", "protected"}:
        selected = _raise_to(selected, "deliberative")
        escalation.append("declared_high_stakes_floor")
    context_pressure = max(0, int(value.context_size)) / max(
        1024, int(value.context_window)
    )
    if context_pressure >= 0.80:
        selected = _raise_to(selected, "deep")
        escalation.append("selected_model_context_pressure")
    if value.expected_data_size >= 100_000:
        selected = _raise_to(selected, "deep")
        escalation.append("large_data_workload")
    if value.retrieval_confidence is not None and value.retrieval_confidence < 0.4:
        selected = _raise_to(selected, "deep")
        escalation.append("low_retrieval_confidence")
    if value.evidence_quality is not None and value.evidence_quality < 0.45:
        selected = _raise_to(selected, "deliberative")
        escalation.append("low_evidence_quality")
    if value.stop_active:
        selected = "reflex"
        escalation = ["emergency_stop_blocks_new_work"]

    level = effective_autonomy(
        value.autonomy_level,
        value.domain_overrides,
        value.active_domain,
    )
    resolved_domains, capability_policy = resolve_autonomy_policy(
        level, value.domain_overrides
    )
    verification = {
        "reflex": "deterministic",
        "quick": "basic",
        "standard": "standard",
        "deep": "enhanced",
        "deliberative": "independent_review",
        "research_engineering": "evidence_and_tool_review",
    }[selected]
    context_share = {
        "reflex": 0.05,
        "quick": 0.10,
        "standard": 0.20,
        "deep": 0.30,
        "deliberative": 0.35,
        "research_engineering": 0.45,
    }[selected]
    recent = {
        "reflex": 4,
        "quick": 8,
        "standard": 14,
        "deep": 20,
        "deliberative": 28,
        "research_engineering": 24,
    }[selected]
    model_hint = {
        "reflex": "none_or_light",
        "quick": "light",
        "standard": "general",
        "deep": "general_strong",
        "deliberative": "general_strong",
        "research_engineering": "specialist_or_general_strong",
    }[selected]
    early_exit = (
        selected in {"reflex", "quick", "standard"}
        and not escalation
        and float(value.uncertainty_score) < 0.35
        and not value.verification_failed
    )
    if escalation:
        reasons.extend(escalation)
    retrieval_breadth = {
        "reflex": "none", "quick": "focused", "standard": "balanced",
        "deep": "broad", "deliberative": "broad",
        "research_engineering": "research",
    }[selected]
    research_budget = {
        "reflex": {"queries": 0, "fetches": 0},
        "quick": {"queries": 0, "fetches": 0},
        "standard": {"queries": 1, "fetches": 1},
        "deep": {"queries": 2, "fetches": 3},
        "deliberative": {"queries": 3, "fetches": 4},
        "research_engineering": {"queries": 6, "fetches": 8},
    }[selected]
    tool_budget = {
        "reflex": {"calls": 0, "seconds": 0},
        "quick": {"calls": 1, "seconds": 10},
        "standard": {"calls": 3, "seconds": 30},
        "deep": {"calls": 6, "seconds": 90},
        "deliberative": {"calls": 8, "seconds": 180},
        "research_engineering": {"calls": 12, "seconds": 300},
    }[selected]
    provider_healthy = bool(value.model_health.get("provider_healthy", True))
    gpu_state = dict(value.resource_state.get("gpu") or {})
    gpu_devices = list(gpu_state.get("devices") or [])
    thermal_rows = list(value.power_thermal_state.get("gpu") or gpu_devices)
    thermal_hot = any(
        float(row.get("temperature_c") or 0) >= 88 for row in thermal_rows
    )
    gpu_available = bool(gpu_state.get("available") and gpu_devices and not thermal_hot)
    if value.queue_depth > 0:
        reasons.append("bounded_compute_queue_present")
    if thermal_hot:
        reasons.append("gpu_thermal_ceiling_requires_cpu_fallback")
    elif not gpu_available:
        reasons.append("gpu_unavailable_cpu_fallback")
    if value.time_budget_ms is not None:
        reasons.append("explicit_time_budget_applied")
    if value.privacy_state in {"private", "sealed"}:
        reasons.append("private_local_only_model_boundary")
    model_constraints = ["local_first", "no_silent_cloud", f"role_hint:{model_hint}"]
    if not provider_healthy:
        model_constraints.append("provider_degraded_use_deterministic_or_local_fallback")
    if value.privacy_state in {"private", "sealed"}:
        model_constraints.append(f"{value.privacy_state}_content_local_only")
    if context_pressure >= 0.80:
        model_constraints.append("selected_model_context_window_is_binding")
    if value.queue_depth > 0:
        model_constraints.append("respect_existing_compute_queue_and_leases")
    time_limited_tokens = (
        max(64, min(2048, int(value.time_budget_ms) // 8))
        if value.time_budget_ms is not None else 2048
    )
    context_budget = max(256, int(max(1024, value.context_window) * context_share))
    if value.context_size > 0:
        context_budget = min(
            context_budget,
            max(256, int(value.context_window) - int(value.context_size)),
        )
    gear_output_budget = {
        "reflex": 0,
        "quick": 256,
        "standard": 512,
        "deep": 1024,
        "deliberative": 1536,
        "research_engineering": 2048,
    }[selected]
    return GovernorDecision(
        version=GOVERNOR_VERSION,
        request_id=value.request_id,
        selected_gear=selected,
        initial_gear=initial,
        gear_override_applied=override_applied,
        effective_autonomy_level=level,
        autonomy_label=AUTONOMY_LEVELS[level],
        resolved_domain_levels=resolved_domains,
        capability_policy=capability_policy,
        context_share=context_share,
        recent_turn_limit=recent,
        verification_depth=verification,
        research_allowed=(
            not value.stop_active
            and value.internet_enabled
            and (
                (value.research_required and level >= 1)
                or (not value.research_required and capability_policy["initiate_bounded_web_research"])
            )
        ),
        tool_execution_allowed=(
            not value.stop_active
            and ((value.tool_required and level >= 1) or level >= 2)
        ),
        model_role_hint=model_hint,
        workload_kind=(
            "no_model" if selected == "reflex" else
            "research_or_engineering" if selected == "research_engineering" else
            "language_model"
        ),
        workload_priority="interactive",
        progress_posture=("silent" if selected in {"reflex", "quick"} else "visible"),
        retrieval_breadth=retrieval_breadth,
        context_token_budget=context_budget,
        output_token_budget=min(gear_output_budget, time_limited_tokens),
        research_budget=research_budget,
        tool_budget=tool_budget,
        device_preference=(
            "cpu" if selected == "reflex" or not gpu_available else "automatic"
        ),
        foreground=True,
        model_constraints=tuple(model_constraints),
        early_exit_eligible=early_exit,
        escalation_conditions=tuple(escalation),
        reasons=tuple(dict.fromkeys(reasons)),
        authority_increased=False,
        content_free=True,
        input_digest=_input_digest(value),
    )


def escalate_decision(
    decision: GovernorDecision,
    *,
    conflict_count: int = 0,
    uncertainty_score: float = 0.0,
    verification_failed: bool = False,
    retrieval_insufficient: bool = False,
    model_disagreement: bool = False,
    tool_mismatch: bool = False,
    low_evidence_quality: bool = False,
    ambiguous_intent: bool = False,
) -> GovernorDecision:
    """Deterministically re-evaluate after retrieval/tool/model verification signals."""
    selected = decision.selected_gear
    conditions = list(decision.escalation_conditions)
    reasons = list(decision.reasons)
    if conflict_count:
        selected = _raise_to(selected, "deep")
        conditions.append("authorized_source_conflict")
    if uncertainty_score >= 0.65:
        selected = _raise_to(selected, "deep")
        conditions.append("high_uncertainty")
    if retrieval_insufficient:
        selected = _raise_to(selected, "deep")
        conditions.append("retrieval_insufficient")
    if verification_failed:
        selected = _raise_to(selected, "deliberative")
        conditions.append("verification_failure")
    if model_disagreement:
        selected = _raise_to(selected, "deliberative")
        conditions.append("model_disagreement")
    if tool_mismatch:
        selected = _raise_to(selected, "deep")
        conditions.append("tool_mismatch")
    if low_evidence_quality:
        selected = _raise_to(selected, "deliberative")
        conditions.append("low_evidence_quality")
    if ambiguous_intent:
        selected = _raise_to(selected, "deep")
        conditions.append("ambiguous_user_intent")
    conditions = list(dict.fromkeys(conditions))
    reasons.extend(conditions)
    if selected == decision.selected_gear and not conditions:
        return decision
    context_share = {
        "reflex": 0.05, "quick": 0.10, "standard": 0.20,
        "deep": 0.30, "deliberative": 0.35, "research_engineering": 0.45,
    }[selected]
    return replace(
        decision,
        selected_gear=selected,
        context_share=context_share,
        context_token_budget=max(
            256,
            int(decision.context_token_budget / max(0.01, decision.context_share) * context_share),
        ),
        output_token_budget={
            "reflex": 0,
            "quick": 256,
            "standard": 512,
            "deep": 1024,
            "deliberative": 1536,
            "research_engineering": 2048,
        }[selected],
        recent_turn_limit={
            "reflex": 4, "quick": 8, "standard": 14,
            "deep": 20, "deliberative": 28, "research_engineering": 24,
        }[selected],
        verification_depth={
            "reflex": "deterministic", "quick": "basic", "standard": "standard",
            "deep": "enhanced", "deliberative": "independent_review",
            "research_engineering": "evidence_and_tool_review",
        }[selected],
        retrieval_breadth={
            "reflex": "none", "quick": "focused", "standard": "balanced",
            "deep": "broad", "deliberative": "broad", "research_engineering": "research",
        }[selected],
        research_budget={
            "reflex": {"queries": 0, "fetches": 0}, "quick": {"queries": 0, "fetches": 0},
            "standard": {"queries": 1, "fetches": 1}, "deep": {"queries": 2, "fetches": 3},
            "deliberative": {"queries": 3, "fetches": 4}, "research_engineering": {"queries": 6, "fetches": 8},
        }[selected],
        tool_budget={
            "reflex": {"calls": 0, "seconds": 0}, "quick": {"calls": 1, "seconds": 10},
            "standard": {"calls": 3, "seconds": 30}, "deep": {"calls": 6, "seconds": 90},
            "deliberative": {"calls": 8, "seconds": 180}, "research_engineering": {"calls": 12, "seconds": 300},
        }[selected],
        early_exit_eligible=False,
        escalation_conditions=tuple(conditions),
        reasons=tuple(dict.fromkeys(reasons)),
    )


def reflex_response(message: str) -> str | None:
    """Return exact bounded responses; anything ambiguous proceeds to a model."""
    normalized = " ".join(message.casefold().split()).strip(" .!?")
    if normalized in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}:
        return "Hello. I’m Elysia. How can I help?"
    if normalized in {"thanks", "thank you", "thank you elysia"}:
        return "You’re welcome."
    if normalized in {"who are you", "what are you"}:
        return "I’m Elysia, your local, governed Ecobotics assistant."
    return None


__all__ = (
    "AUTONOMY_LEVELS",
    "GEARS",
    "GOVERNOR_VERSION",
    "GovernorDecision",
    "GovernorInput",
    "decide_cognition",
    "effective_autonomy",
    "escalate_decision",
    "reflex_response",
    "resolve_autonomy_policy",
)
