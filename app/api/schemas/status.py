"""
Status-family schema models for the Elysia local API bridge.

This module is the Python-side implementation shape for the Stage 2 contracts
behind:
- GET /status/runtime
- GET /status/health
- GET /status/invoker
- GET /status/capabilities

This file should stay narrow:
- runtime-status response-data models
- health-status response-data models
- invoker-status response-data models
- capability-catalog response-data models
- small status-family enums/literals

It should not contain:
- route logic
- service logic
- runtime logic
- governance logic
- endpoint-specific business rules
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import (
    ApprovalState,
    CapabilityState,
    ElysiaSchemaModel,
    LocalityState,
)


class RuntimeState(str, Enum):
    """
    Canonical runtime-state values for /status/runtime data.

    Meanings:
    - idle: runtime is available but not currently engaged
    - active: runtime is actively processing or very recently engaged
    - blocked: runtime is present, but work is blocked by policy/boundary posture
    - degraded: runtime is present but reduced, impaired, or fallback-shaped
    - unavailable: required runtime path should exist but is currently unreachable
    - starting: runtime is still initializing
    - unknown: runtime truth has not yet been confirmed
    """

    IDLE = "idle"
    ACTIVE = "active"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    STARTING = "starting"
    UNKNOWN = "unknown"


class InvocationStatus(str, Enum):
    """
    Compact invocation-status values for runtime-status and invoker-status reporting.
    """

    OK = "ok"
    BLOCKED = "blocked"
    ERROR = "error"
    NOT_INVOKED = "not_invoked"
    UNKNOWN = "unknown"


class InvokerState(str, Enum):
    """
    Canonical invoker-state values for /status/invoker data.

    Meanings:
    - available: the governed invoker path is available for normal local use
    - blocked: the invoker path exists, but current or most recent work is approval-bound or blocked
    - degraded: the invoker path exists, but fallback or recent invocation issues are present
    - unavailable: the invoker path should exist but is currently unreachable/unusable
    - unknown: invoker truth has not yet been confirmed
    """

    AVAILABLE = "available"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class HealthState(str, Enum):
    """
    Canonical health-state values for /status/health data.

    Meanings:
    - healthy: core services/subsystems are functioning for normal Phase 1 use
    - degraded: present but reduced/impaired
    - starting: still initializing
    - unhealthy: reachable enough to inspect, but failing for normal use
    - unavailable: should exist but currently unreachable/unusable
    - unknown: not yet confirmed
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STARTING = "starting"
    UNHEALTHY = "unhealthy"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class StartupState(str, Enum):
    """
    Startup-readiness posture values for /status/health data.
    """

    READY = "ready"
    STARTING = "starting"
    WARMING = "warming"
    NOT_READY = "not_ready"
    UNKNOWN = "unknown"


class CapabilityCatalogState(str, Enum):
    """
    State of the capability catalog snapshot as a whole.

    Meanings:
    - live: actually available now
    - partial: present but incomplete
    - planned: designed/not yet live
    - unknown: not yet confirmed
    - unavailable: should exist but currently unreachable/unusable
    - degraded: present but reduced/impaired
    """

    LIVE = "live"
    PARTIAL = "partial"
    PLANNED = "planned"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class CapabilityGroup(str, Enum):
    """
    Common grouping labels for the qualified stable v1.0 capability catalog.
    """

    CORE_CHAT = "core_chat"
    STATUS_SURFACES = "status_surfaces"
    GOVERNANCE = "governance"
    MEMORY = "memory"
    PROJECTS = "projects"
    APPROVALS = "approvals"
    REQUESTS = "requests"
    QUICK_INVOKE = "quick_invoke"
    FILES = "files"
    EXECUTION = "execution"
    CODER = "coder"
    RESEARCH = "research"
    ARTIFACTS = "artifacts"
    TOOLS = "tools"


class SubsystemHealthEntry(ElysiaSchemaModel):
    """
    Compact per-subsystem health summary for /status/health.
    """

    state: HealthState = Field(
        ...,
        description="Health state of the subsystem entry.",
    )
    healthy: bool = Field(
        ...,
        description="Boolean summary of whether the subsystem is healthy enough for normal use.",
    )
    note: str = Field(
        default="",
        description="Compact UI-safe subsystem note.",
    )


class HealthSubsystems(ElysiaSchemaModel):
    """
    Named subsystem health entries used by /status/health.
    """

    api: SubsystemHealthEntry
    runtime: SubsystemHealthEntry
    ollama: SubsystemHealthEntry
    config: SubsystemHealthEntry
    logging: SubsystemHealthEntry
    journaling: SubsystemHealthEntry
    memory: SubsystemHealthEntry
    searxng: SubsystemHealthEntry | None = Field(
        default=None,
        description="Loopback-only SearXNG reachability check when configured.",
    )


class RuntimeStatusData(ElysiaSchemaModel):
    """
    Response data model for GET /status/runtime.
    """

    runtime_state: RuntimeState = Field(
        ...,
        description="State of the runtime itself, distinct from the envelope request outcome.",
    )
    runtime_available: bool = Field(
        ...,
        description="Whether the core governed runtime path is currently available.",
    )
    active_mode: str | None = Field(
        default=None,
        description="Current or most recently relevant runtime mode posture.",
    )
    selected_role: str | None = Field(
        default=None,
        description="Current or most recently selected governed role expression.",
    )
    selected_runtime: str | None = Field(
        default=None,
        description="Current or most recently selected runtime.",
    )
    selected_model_runtime_tag: str | None = Field(
        default=None,
        description="Concrete model/runtime tag currently or most recently in use.",
    )
    stayed_local: bool = Field(
        ...,
        description="Whether the current or most recent governed path stayed local.",
    )
    used_fallback: bool = Field(
        default=False,
        description="Whether an allowed fallback path is currently in effect or was most recently used.",
    )
    fallback_from: str | None = Field(
        default=None,
        description="Preferred runtime tag that could not be used when fallback occurred.",
    )
    fallback_to: str | None = Field(
        default=None,
        description="Runtime tag actually used after fallback when fallback occurred.",
    )
    approval_needed: bool | None = Field(
        default=None,
        description="Broad trust-surface indicator for whether current runtime work is approval-bound.",
    )
    last_request_id: str | None = Field(
        default=None,
        description="Most recent request identifier associated with runtime activity when available.",
    )
    last_invocation_status: InvocationStatus | None = Field(
        default=None,
        description="Most recent invocation outcome observed by the runtime.",
    )
    last_error: str | None = Field(
        default=None,
        description="Most recent compact runtime-relevant error message.",
    )
    last_updated_utc: str = Field(
        ...,
        description="UTC timestamp for when this runtime snapshot was produced.",
    )


class InvokerStatusData(ElysiaSchemaModel):
    """
    Response data model for GET /status/invoker.
    """

    invoker_state: InvokerState = Field(
        ...,
        description="State of the governed invoker path itself.",
    )
    invoker_available: bool = Field(
        ...,
        description="Whether the governed invoker path is currently available.",
    )
    selected_role: str | None = Field(
        default=None,
        description="Current or most recently selected governed role expression for the invoker path.",
    )
    selected_runtime: str | None = Field(
        default=None,
        description="Current or most recently selected runtime for the invoker path.",
    )
    selected_model_runtime_tag: str | None = Field(
        default=None,
        description="Concrete model/runtime tag currently or most recently in use by the invoker path.",
    )
    stayed_local: bool = Field(
        ...,
        description="Whether the current or most recent governed invoker path stayed local.",
    )
    used_fallback: bool = Field(
        default=False,
        description="Whether an allowed fallback path is currently in effect or was most recently used by the invoker path.",
    )
    fallback_from: str | None = Field(
        default=None,
        description="Preferred runtime tag that could not be used when invoker fallback occurred.",
    )
    fallback_to: str | None = Field(
        default=None,
        description="Runtime tag actually used after invoker fallback when fallback occurred.",
    )
    approval_needed: bool | None = Field(
        default=None,
        description="Broad trust-surface indicator for whether current invoker work is approval-bound.",
    )
    last_request_id: str | None = Field(
        default=None,
        description="Most recent request identifier associated with invoker activity when available.",
    )
    last_invocation_status: InvocationStatus | None = Field(
        default=None,
        description="Most recent invocation outcome observed by the invoker path.",
    )
    last_error: str | None = Field(
        default=None,
        description="Most recent compact invoker-relevant error message.",
    )
    last_updated_utc: str = Field(
        ...,
        description="UTC timestamp for when this invoker snapshot was produced.",
    )


class HealthStatusData(ElysiaSchemaModel):
    """
    Response data model for GET /status/health.
    """

    health_state: HealthState = Field(
        ...,
        description="Overall health state of the relevant local services/subsystems.",
    )
    healthy: bool = Field(
        ...,
        description="Broad boolean summary for whether the system is healthy enough for normal use.",
    )
    startup_state: StartupState = Field(
        ...,
        description="Startup-readiness posture distinct from general health.",
    )
    api_reachable: bool = Field(
        ...,
        description="Whether the local API layer is reachable enough to serve requests.",
    )
    runtime_reachable: bool = Field(
        ...,
        description="Whether the core governed runtime path is reachable enough for use.",
    )
    ollama_reachable: bool = Field(
        ...,
        description="Whether the configured local model service is reachable enough for Phase 1 use.",
    )
    searxng_reachable: bool | None = Field(
        default=None,
        description="Whether local loopback SearXNG is reachable without issuing a search query.",
    )
    config_loadable: bool = Field(
        ...,
        description="Whether required config sources can be loaded successfully.",
    )
    logging_writable: bool = Field(
        ...,
        description="Whether the runtime logging path is writable enough for governed operation.",
    )
    journaling_writable: bool = Field(
        ...,
        description="Whether the session journaling path is writable enough for governed operation.",
    )
    memory_path_available: bool = Field(
        ...,
        description="Whether required local memory-related storage paths are available enough for use.",
    )
    last_health_check_utc: str = Field(
        ...,
        description="UTC timestamp for when this health snapshot was produced.",
    )
    health_notes: list[str] = Field(
        default_factory=list,
        description="Compact health notes safe for UI inspection.",
    )
    subsystems: HealthSubsystems = Field(
        ...,
        description="Compact per-subsystem health summary.",
    )


class CapabilityEntry(ElysiaSchemaModel):
    """
    Compact capability-truth entry for /status/capabilities.
    """

    capability_key: str = Field(
        ...,
        description="Stable machine-readable capability identifier.",
    )
    display_name: str = Field(
        ...,
        description="Human-facing capability name for UI display.",
    )
    group: CapabilityGroup | str | None = Field(
        default=None,
        description="Grouping label used for UI organization.",
    )
    state: CapabilityState = Field(
        ...,
        description="Truth state of the individual capability entry.",
    )
    summary: str | None = Field(
        default=None,
        description="Compact human-readable description of what the capability currently means.",
    )
    locality: LocalityState = Field(
        ...,
        description="Whether the capability is local, crossed a boundary, or is unknown.",
    )
    approval_state: ApprovalState = Field(
        ...,
        description="Broad approval posture associated with using this capability.",
    )
    read_only: bool = Field(
        ...,
        description="Whether the capability is read-only rather than action-capable.",
    )
    ui_surfaces: list[str] = Field(
        default_factory=list,
        description="UI surfaces where this capability is relevant or surfaced.",
    )
    supporting_endpoint: str | None = Field(
        default=None,
        description="Primary API endpoint associated with this capability when applicable.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Compact capability notes safe for UI display.",
    )


class CapabilityCatalogData(ElysiaSchemaModel):
    """
    Response data model for GET /status/capabilities.
    """

    capability_catalog_state: CapabilityCatalogState = Field(
        ...,
        description="State of the capability catalog snapshot as a whole.",
    )
    capability_count: int = Field(
        ...,
        ge=0,
        description="Number of capability entries present in the returned catalog.",
    )
    last_updated_utc: str = Field(
        ...,
        description="UTC timestamp for when this capability catalog snapshot was produced.",
    )
    capability_groups: list[str] = Field(
        default_factory=list,
        description="Compact grouping labels used to organize the catalog.",
    )
    capabilities: list[CapabilityEntry] = Field(
        default_factory=list,
        description="List of compact capability-truth entries safe for UI inspection.",
    )


__all__ = (
    "CapabilityCatalogData",
    "CapabilityCatalogState",
    "CapabilityEntry",
    "CapabilityGroup",
    "HealthState",
    "HealthStatusData",
    "HealthSubsystems",
    "InvocationStatus",
    "InvokerState",
    "InvokerStatusData",
    "RuntimeState",
    "RuntimeStatusData",
    "StartupState",
    "SubsystemHealthEntry",
)
