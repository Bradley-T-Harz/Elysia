"""Authoritative per-account controls consumed by runtime and worker gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.api.account_service import get_active_elysia_paths, get_authenticated_governance
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService


@dataclass(frozen=True)
class UserControlSnapshot:
    memory_recording_enabled: bool
    autonomy_level: int
    internet_master_enabled: bool
    retrieval_breadth: str
    research_initiative: str
    safe_search_level: str
    preferred_reasoning_gear: str
    autonomy_domain_overrides: dict[str, int]
    compute_preference: str
    model_performance_preference: str
    background_cognition_enabled: bool
    cpu_percent_ceiling: int
    ram_mb_ceiling: int
    vram_mb_ceiling: int
    max_background_jobs: int
    managed_profile: bool
    managed_policy_version: int
    addons_allowed: bool
    connectors_allowed: bool
    coding_execution_allowed: bool
    project_agent_limit: int
    external_mutations_allowed: bool
    network_filter_level: str

    def effective_autonomy(self, domain: str | None = None) -> int:
        level = self.autonomy_level
        if domain:
            level = min(level, int(self.autonomy_domain_overrides.get(domain, level)))
        return max(1, min(5, level))


def current_user_controls() -> UserControlSnapshot:
    fabric = MemoryFabricService(repository=MemoryRepository(paths=get_active_elysia_paths()))
    principal = fabric.current_principal()
    settings = fabric.settings(principal)
    governance: dict[str, Any] = get_authenticated_governance()
    managed = bool(governance.get("managed"))
    managed_policy = dict(governance.get("managed_policy") or {})
    autonomy_maximum = int(managed_policy.get("autonomy_maximum", 5)) if managed else 5
    domain_overrides = {
        key: min(int(value), autonomy_maximum)
        for key, value in settings.autonomy_domain_overrides.items()
    }
    filter_rank = {"off": 0, "standard": 0, "moderate": 1, "strict": 2}
    user_filter = str(getattr(settings, "safe_search_level", "strict"))
    managed_filter = str(managed_policy.get("network_filter_level", "strict"))
    effective_filter = max(
        (user_filter, managed_filter if managed else "standard"),
        key=lambda item: filter_rank.get(item, 2),
    )
    return UserControlSnapshot(
        memory_recording_enabled=settings.memory_recording_enabled,
        autonomy_level=min(settings.autonomy_level, autonomy_maximum),
        internet_master_enabled=(
            settings.internet_master_enabled
            and (not managed or bool(managed_policy.get("internet_allowed", False)))
        ),
        retrieval_breadth=str(getattr(settings, "retrieval_breadth", "balanced")),
        research_initiative=str(getattr(settings, "research_initiative", "manual")),
        safe_search_level=effective_filter,
        preferred_reasoning_gear=settings.preferred_reasoning_gear,
        autonomy_domain_overrides=domain_overrides,
        compute_preference=settings.compute_preference,
        model_performance_preference=settings.model_performance_preference,
        background_cognition_enabled=(
            settings.background_cognition_enabled
            and (not managed or bool(managed_policy.get("background_cognition_allowed", False)))
        ),
        cpu_percent_ceiling=min(
            settings.cpu_percent_ceiling,
            int(managed_policy.get("cpu_percent_ceiling", 100)) if managed else 100,
        ),
        ram_mb_ceiling=min(
            settings.ram_mb_ceiling,
            int(managed_policy.get("ram_mb_ceiling", 262_144)) if managed else 262_144,
        ),
        vram_mb_ceiling=min(
            settings.vram_mb_ceiling,
            int(managed_policy.get("vram_mb_ceiling", 131_072)) if managed else 131_072,
        ),
        max_background_jobs=(
            settings.max_background_jobs
            if not managed or bool(managed_policy.get("background_cognition_allowed", False))
            else 0
        ),
        managed_profile=managed,
        managed_policy_version=int(governance.get("policy_version") or 1),
        addons_allowed=not managed or bool(managed_policy.get("addons_allowed", False)),
        connectors_allowed=not managed or bool(managed_policy.get("connectors_allowed", False)),
        coding_execution_allowed=(
            not managed or bool(managed_policy.get("coding_execution_allowed", False))
        ),
        project_agent_limit=(
            int(managed_policy.get("project_agent_limit", 0)) if managed else 32
        ),
        external_mutations_allowed=(
            not managed or bool(managed_policy.get("external_mutations_allowed", False))
        ),
        network_filter_level=effective_filter,
    )


def managed_capability_allowed(capability: str) -> bool:
    """Return an enforceable managed-profile ceiling; unmanaged users retain authority."""
    governance = get_authenticated_governance()
    if not bool(governance.get("managed")):
        return True
    policy = dict(governance.get("managed_policy") or {})
    mapping = {
        "addons": bool(policy.get("addons_allowed", False)),
        "connectors": bool(policy.get("connectors_allowed", False)),
        "coding_execution": bool(policy.get("coding_execution_allowed", False)),
        "external_mutations": bool(policy.get("external_mutations_allowed", False)),
        "background_cognition": bool(policy.get("background_cognition_allowed", False)),
    }
    return mapping.get(capability, True)


def internet_master_enabled() -> bool:
    """Fail closed when no authenticated authoritative setting can be read."""
    try:
        from app.cognition.emergency_control import emergency_active

        if emergency_active():
            return False
        return current_user_controls().internet_master_enabled
    except Exception:
        return False


def autonomy_level(default: int = 3) -> int:
    try:
        return current_user_controls().autonomy_level
    except Exception:
        return default


__all__ = (
    "UserControlSnapshot",
    "autonomy_level",
    "current_user_controls",
    "internet_master_enabled",
    "managed_capability_allowed",
)
