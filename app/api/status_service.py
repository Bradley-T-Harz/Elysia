"""
Status-side service organ for the Elysia local API bridge.

This module sits between the thin status routes and the deeper runtime/health
truth surfaces. Its job is to assemble compact governed status snapshots and
wrap them in the standard response envelope.

This file should stay narrow:
- runtime status assembly
- health status assembly
- small local inspection helpers

It must not:
- become a second runtime
- become a capability catalog
- become governance logic
- call Ollama for generation
- dump raw logs or raw journals
- invent system truth beyond narrow translation/inspection
"""

from __future__ import annotations
from datetime import datetime, timezone

import importlib
import logging
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.status import (
    CapabilityCatalogState,
    HealthState,
    HealthStatusData,
    HealthSubsystems,
    InvocationStatus,
    RuntimeState,
    RuntimeStatusData,
    StartupState,
    SubsystemHealthEntry,
)
from app.install.paths import resolve_elysia_paths

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_USER_PATHS = resolve_elysia_paths()
LOG_DIR = _USER_PATHS.log_dir
JOURNAL_DIR = _USER_PATHS.journal_dir
MEMORY_DIR = _USER_PATHS.data_dir / "memory"

OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
DEFAULT_SEARXNG_HEALTH_URL = "http://127.0.0.1:8888/"


def _utc_now_iso() -> str:
    """
    Return the current UTC timestamp in compact API-envelope style.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_request_id(prefix: str = "req") -> str:
    """
    Create a compact request identifier for envelope use.
    """
    return f"{prefix}_{uuid4().hex[:16]}"


def _coerce_string(value: Any, default: str = "") -> str:
    """
    Normalize one value into a clean string.
    """
    text = str(value or "").strip()
    return text if text else default


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


def _import_optional(module_path: str) -> tuple[Any | None, str | None]:
    """
    Attempt to import one module without throwing.

    Returns:
    - imported module or None
    - compact error text or None
    """
    try:
        return importlib.import_module(module_path), None
    except Exception as exc:
        return None, str(exc)


def _path_available_for_write(path: Path) -> bool:
    """
    Check whether a path is available enough for write use without forcing
    side-effecting creation.

    Rules:
    - if the path exists, it must be writable
    - if it does not exist, its nearest existing parent must be writable
    """
    if path.exists():
        return path.is_dir() and os.access(path, os.W_OK)

    current = path.parent
    while not current.exists() and current != current.parent:
        current = current.parent

    return current.exists() and current.is_dir() and os.access(current, os.W_OK)


def _ping_ollama() -> bool:
    """
    Check whether the local Ollama service is reachable enough for Phase 1 use.
    """
    try:
        with urlopen(OLLAMA_TAGS_URL, timeout=1.5) as response:
            status_code = getattr(response, "status", 200)
            return 200 <= int(status_code) < 300
    except (URLError, TimeoutError, ValueError):
        return False


def _searxng_health_url() -> str:
    """Return configured loopback SearXNG base URL for reachability only."""
    try:
        from sandbox.searxng_worker.config import load_searxng_worker_config

        config = load_searxng_worker_config()
        base_url = str(config.service.get("base_url") or DEFAULT_SEARXNG_HEALTH_URL)
    except Exception:
        base_url = DEFAULT_SEARXNG_HEALTH_URL

    return base_url.rstrip("/") + "/"


def _ping_searxng_loopback() -> bool:
    """
    Check whether local SearXNG is reachable without sending query terms.

    This is a loopback reachability probe only. It must not call /search.
    """
    health_url = _searxng_health_url()
    if not (
        health_url.startswith("http://127.0.0.1:")
        or health_url.startswith("http://localhost:")
    ):
        return False

    try:
        with urlopen(health_url, timeout=1.5) as response:
            status_code = getattr(response, "status", 200)
            return 200 <= int(status_code) < 500
    except (URLError, TimeoutError, ValueError):
        return False


def _load_runtime_bridge_snapshot() -> dict[str, Any]:
    """
    Try to load a compact last-known runtime snapshot from runtime_bridge.

    This service does not require the bridge snapshot to exist, but it will use
    it when available so runtime status can reflect last-known real body truth.
    """
    runtime_bridge, _ = _import_optional("app.api.runtime_bridge")
    if runtime_bridge is None:
        return {}

    snapshot_candidates = (
        getattr(runtime_bridge, "LAST_RUNTIME_PACKET", None),
        getattr(runtime_bridge, "LAST_CHAT_RUNTIME_PACKET", None),
        getattr(runtime_bridge, "LAST_CHAT_RESULT", None),
        getattr(runtime_bridge, "LAST_RUNTIME_RESULT", None),
    )

    for candidate in snapshot_candidates:
        if isinstance(candidate, dict):
            return dict(candidate)

    return {}


def _get_runtime_import_truth() -> tuple[bool, str]:
    """
    Determine whether the real core runtime organ is importable and shaped
    as expected for the bridge phase.
    """
    runtime_module, runtime_error = _import_optional("core.runtime")
    if runtime_module is None:
        return False, runtime_error or "core.runtime is not importable."

    has_entrypoint = hasattr(runtime_module, "handle_user_message")
    has_session_state = hasattr(runtime_module, "SessionState")

    if has_entrypoint and has_session_state:
        return True, ""

    return False, "core.runtime is missing handle_user_message and/or SessionState."


def _get_config_load_truth() -> tuple[bool, str]:
    """
    Determine whether required config sources are loadable.
    """
    config_loader, config_error = _import_optional("core.config_loader")
    if config_loader is None:
        return False, config_error or "core.config_loader is not importable."

    load_all_configs = getattr(config_loader, "load_all_configs", None)
    if load_all_configs is None:
        return False, "core.config_loader does not expose load_all_configs."

    try:
        configs = load_all_configs()
        if isinstance(configs, dict) and configs:
            return True, ""
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _extract_last_runtime_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Extract compact last-known runtime fields from a previously cached runtime packet.

    The bridge and runtime may evolve. This helper stays narrow and defensive.
    """
    response = snapshot.get("response", {})
    policy_review = snapshot.get("policy_review", {})
    internal_result = snapshot.get("internal_result", {})

    if not isinstance(response, dict):
        response = {}
    if not isinstance(policy_review, dict):
        policy_review = {}
    if not isinstance(internal_result, dict):
        internal_result = {}

    return {
        "active_mode": _coerce_string(
            snapshot.get("session_state", {}).get("active_mode")
            if isinstance(snapshot.get("session_state", {}), dict)
            else "",
            "",
        ),
        "selected_role": _coerce_string(response.get("selected_model_role"), ""),
        "selected_runtime": _coerce_string(response.get("selected_runtime"), ""),
        "selected_model_runtime_tag": _coerce_string(
            response.get("selected_model_runtime_tag"),
            "",
        ),
        "stayed_local": _coerce_bool(
            internal_result.get("stayed_local"),
            _coerce_bool(
                snapshot.get("model_routing", {}).get("stayed_local")
                if isinstance(snapshot.get("model_routing", {}), dict)
                else None,
                True,
            ),
        ),
        "used_fallback": _coerce_bool(response.get("used_fallback"), False),
        "fallback_from": _coerce_string(response.get("fallback_from"), ""),
        "fallback_to": _coerce_string(response.get("fallback_to"), ""),
        "approval_needed": _coerce_bool(
            policy_review.get("approval_required"),
            False,
        )
        if "approval_required" in policy_review
        else None,
        "last_request_id": _coerce_string(snapshot.get("request_id"), ""),
        "last_invocation_status": _coerce_string(response.get("invocation_status"), ""),
        "last_error": _coerce_string(internal_result.get("error"), ""),
    }


def _determine_runtime_state(
    runtime_available: bool,
    last_fields: dict[str, Any],
) -> RuntimeState:
    """
    Determine the compact runtime state without inventing a second runtime.

    Since we are not tracking active in-flight work yet, the honest steady-state
    default is idle when the runtime is available and not obviously blocked or degraded.
    """
    if not runtime_available:
        return RuntimeState.UNAVAILABLE

    invocation_status = _coerce_string(last_fields.get("last_invocation_status"), "")
    approval_needed = last_fields.get("approval_needed")
    used_fallback = _coerce_bool(last_fields.get("used_fallback"), False)
    last_error = _coerce_string(last_fields.get("last_error"), "")

    if invocation_status == InvocationStatus.BLOCKED.value:
        return RuntimeState.BLOCKED

    if used_fallback or invocation_status == InvocationStatus.ERROR.value or last_error:
        return RuntimeState.DEGRADED

    return RuntimeState.IDLE


def _determine_runtime_capability_state(runtime_state: RuntimeState) -> CapabilityState:
    """
    Determine capability truth for the /status/runtime surface.
    """
    if runtime_state in {RuntimeState.IDLE, RuntimeState.ACTIVE}:
        return CapabilityState.LIVE

    if runtime_state == RuntimeState.BLOCKED:
        return CapabilityState.LIVE

    if runtime_state == RuntimeState.DEGRADED:
        return CapabilityState.DEGRADED

    if runtime_state == RuntimeState.UNAVAILABLE:
        return CapabilityState.UNAVAILABLE

    return CapabilityState.UNKNOWN


def _build_runtime_status_data() -> tuple[RuntimeStatusData, EnvelopeStatus, CapabilityState, LocalityState, ApprovalState, list[str], list[str], TraceSummary]:
    """
    Build the RuntimeStatusData payload plus envelope metadata.
    """
    runtime_available, runtime_error = _get_runtime_import_truth()
    snapshot = _load_runtime_bridge_snapshot()
    last_fields = _extract_last_runtime_fields(snapshot)

    runtime_state = _determine_runtime_state(runtime_available, last_fields)
    capability_state = _determine_runtime_capability_state(runtime_state)

    locality = (
        LocalityState.LOCAL
        if _coerce_bool(last_fields.get("stayed_local"), True)
        else LocalityState.CROSSED_BOUNDARY
    )

    approval_needed = last_fields.get("approval_needed")
    if approval_needed is True:
        approval_state = ApprovalState.NEEDED
    elif approval_needed is False:
        approval_state = ApprovalState.NOT_NEEDED
    else:
        approval_state = ApprovalState.UNKNOWN

    normalized_invocation_status = _coerce_string(
        last_fields.get("last_invocation_status"),
        InvocationStatus.UNKNOWN.value,
    )
    if normalized_invocation_status not in {status.value for status in InvocationStatus}:
        normalized_invocation_status = InvocationStatus.UNKNOWN.value

    data = RuntimeStatusData(
        runtime_state=runtime_state,
        runtime_available=runtime_available,
        active_mode=_coerce_string(last_fields.get("active_mode"), "") or None,
        selected_role=_coerce_string(last_fields.get("selected_role"), "") or None,
        selected_runtime=_coerce_string(last_fields.get("selected_runtime"), "") or None,
        selected_model_runtime_tag=_coerce_string(
            last_fields.get("selected_model_runtime_tag"),
            "",
        )
        or None,
        stayed_local=_coerce_bool(last_fields.get("stayed_local"), True),
        used_fallback=_coerce_bool(last_fields.get("used_fallback"), False),
        fallback_from=_coerce_string(last_fields.get("fallback_from"), "") or None,
        fallback_to=_coerce_string(last_fields.get("fallback_to"), "") or None,
        approval_needed=approval_needed,
        last_request_id=_coerce_string(last_fields.get("last_request_id"), "") or None,
        last_invocation_status=InvocationStatus(normalized_invocation_status),
        last_error=_coerce_string(last_fields.get("last_error"), "") or None,
        last_updated_utc=(
            _coerce_string(snapshot.get("timestamp_utc"), "")
            or _coerce_string(snapshot.get("updated_at_utc"), "")
            or _coerce_string(snapshot.get("last_updated_utc"), "")
            or _utc_now_iso()
        ),
    )

    warnings: list[str] = []
    errors: list[str] = []

    if runtime_error:
        errors.append(runtime_error)

    if approval_needed is True and runtime_state != RuntimeState.BLOCKED:
        warnings.append(
            "Most recent work is awaiting approval; no side-effecting action has been completed."
        )

    if runtime_state == RuntimeState.BLOCKED:
        warnings.append(
            "Runtime is available, but current or most recent work is blocked by governed boundary rules."
        )

    if runtime_state == RuntimeState.DEGRADED:
        warnings.append(
            "Runtime is available, but fallback or recent invocation issues are present."
        )

    envelope_status = (
        EnvelopeStatus.UNAVAILABLE if runtime_state == RuntimeState.UNAVAILABLE else EnvelopeStatus.OK
    )

    trace_summary = TraceSummary(
        route_used="status.runtime",
        selected_role=data.selected_role,
        selected_runtime=data.selected_runtime,
        selected_model_runtime_tag=data.selected_model_runtime_tag,
        used_fallback=data.used_fallback,
        log_written=None,
        journal_written=None,
    )

    return (
        data,
        envelope_status,
        capability_state,
        locality,
        approval_state,
        warnings,
        errors,
        trace_summary,
    )


def _subsystem_state_from_bool(ok: bool, *, false_state: HealthState) -> HealthState:
    """
    Map a boolean subsystem truth into a compact health-state.
    """
    return HealthState.HEALTHY if ok else false_state


def _build_health_subsystems(
    *,
    api_reachable: bool,
    runtime_reachable: bool,
    ollama_reachable: bool,
    searxng_reachable: bool | None,
    config_loadable: bool,
    logging_writable: bool,
    journaling_writable: bool,
    memory_path_available: bool,
) -> HealthSubsystems:
    """
    Build the named subsystem health block for /status/health.
    """
    return HealthSubsystems(
        api=SubsystemHealthEntry(
            state=_subsystem_state_from_bool(api_reachable, false_state=HealthState.UNAVAILABLE),
            healthy=api_reachable,
            note="" if api_reachable else "Local API layer is not reachable.",
        ),
        runtime=SubsystemHealthEntry(
            state=_subsystem_state_from_bool(runtime_reachable, false_state=HealthState.UNAVAILABLE),
            healthy=runtime_reachable,
            note="" if runtime_reachable else "Core runtime path is not reachable.",
        ),
        ollama=SubsystemHealthEntry(
            state=_subsystem_state_from_bool(ollama_reachable, false_state=HealthState.UNAVAILABLE),
            healthy=ollama_reachable,
            note="" if ollama_reachable else "Local model service is not reachable.",
        ),
        config=SubsystemHealthEntry(
            state=_subsystem_state_from_bool(config_loadable, false_state=HealthState.UNHEALTHY),
            healthy=config_loadable,
            note="" if config_loadable else "Required config sources could not be loaded.",
        ),
        logging=SubsystemHealthEntry(
            state=_subsystem_state_from_bool(logging_writable, false_state=HealthState.UNHEALTHY),
            healthy=logging_writable,
            note="" if logging_writable else "Runtime logging path is not writable enough for normal use.",
        ),
        journaling=SubsystemHealthEntry(
            state=_subsystem_state_from_bool(journaling_writable, false_state=HealthState.UNHEALTHY),
            healthy=journaling_writable,
            note="" if journaling_writable else "Session journaling path is not writable enough for normal use.",
        ),
        memory=SubsystemHealthEntry(
            state=_subsystem_state_from_bool(memory_path_available, false_state=HealthState.UNHEALTHY),
            healthy=memory_path_available,
            note="" if memory_path_available else "Memory path is not available enough for normal use.",
        ),
        searxng=SubsystemHealthEntry(
            state=(
                HealthState.HEALTHY
                if searxng_reachable is True
                else HealthState.UNAVAILABLE
            ),
            healthy=searxng_reachable is True,
            note=(
                "Loopback SearXNG responded without a search query."
                if searxng_reachable is True
                else "Loopback SearXNG was not reachable; no search query was sent."
            ),
        ),
    )


def _determine_health_state(
    *,
    api_reachable: bool,
    runtime_reachable: bool,
    ollama_reachable: bool,
    config_loadable: bool,
    logging_writable: bool,
    journaling_writable: bool,
    memory_path_available: bool,
    searxng_reachable: bool | None = None,
) -> tuple[HealthState, StartupState, bool, list[str], list[str], CapabilityState, EnvelopeStatus]:
    """
    Determine overall health-state, startup-state, and envelope/capability truth
    without inventing a second system worldview.
    """
    warnings: list[str] = []
    errors: list[str] = []

    critical_flags = [
        api_reachable,
        runtime_reachable,
        ollama_reachable,
        config_loadable,
        logging_writable,
        journaling_writable,
    ]

    if not api_reachable:
        errors.append("Local API health surface is not reachable enough for normal use.")
        return (
            HealthState.UNAVAILABLE,
            StartupState.UNKNOWN,
            False,
            warnings,
            errors,
            CapabilityState.UNAVAILABLE,
            EnvelopeStatus.UNAVAILABLE,
        )

    if all(critical_flags) and memory_path_available:
        return (
            HealthState.HEALTHY,
            StartupState.READY,
            True,
            warnings,
            errors,
            CapabilityState.LIVE,
            EnvelopeStatus.OK,
        )

    if runtime_reachable and config_loadable and logging_writable and journaling_writable and not ollama_reachable:
        warnings.append("Local model service is not reachable.")
        return (
            HealthState.DEGRADED,
            StartupState.WARMING,
            False,
            warnings,
            errors,
            CapabilityState.DEGRADED,
            EnvelopeStatus.OK,
        )

    if api_reachable and (not runtime_reachable or not config_loadable or not logging_writable or not journaling_writable):
        warnings.append("System is reachable, but not ready for normal Phase 1 use.")
        return (
            HealthState.UNHEALTHY,
            StartupState.NOT_READY,
            False,
            warnings,
            errors,
            CapabilityState.DEGRADED,
            EnvelopeStatus.OK,
        )

    warnings.append("Health truth is not yet fully confirmed.")
    return (
        HealthState.UNKNOWN,
        StartupState.UNKNOWN,
        False,
        warnings,
        errors,
        CapabilityState.UNKNOWN,
        EnvelopeStatus.OK,
    )


def _build_health_status_data() -> tuple[HealthStatusData, EnvelopeStatus, CapabilityState, list[str], list[str], TraceSummary]:
    """
    Build the HealthStatusData payload plus envelope metadata.
    """
    api_reachable = True
    runtime_reachable, runtime_error = _get_runtime_import_truth()
    ollama_reachable = _ping_ollama()
    searxng_reachable = _ping_searxng_loopback()
    config_loadable, config_error = _get_config_load_truth()
    logging_writable = _path_available_for_write(LOG_DIR)
    journaling_writable = _path_available_for_write(JOURNAL_DIR)
    memory_path_available = _path_available_for_write(MEMORY_DIR)

    (
        health_state,
        startup_state,
        healthy,
        warnings,
        errors,
        capability_state,
        envelope_status,
    ) = _determine_health_state(
        api_reachable=api_reachable,
        runtime_reachable=runtime_reachable,
        ollama_reachable=ollama_reachable,
        searxng_reachable=searxng_reachable,
        config_loadable=config_loadable,
        logging_writable=logging_writable,
        journaling_writable=journaling_writable,
        memory_path_available=memory_path_available,
    )

    if runtime_error:
        errors.append(runtime_error)

    if config_error:
        errors.append(config_error)

    if not logging_writable:
        warnings.append("Runtime logging path is not writable enough for normal governed use.")

    if not journaling_writable:
        warnings.append("Session journaling path is not writable enough for normal governed use.")

    if not memory_path_available:
        warnings.append("Memory path is not available enough for normal governed use.")

    if not searxng_reachable:
        warnings.append("Loopback SearXNG is not reachable; no search query was sent.")

    subsystems = _build_health_subsystems(
        api_reachable=api_reachable,
        runtime_reachable=runtime_reachable,
        ollama_reachable=ollama_reachable,
        searxng_reachable=searxng_reachable,
        config_loadable=config_loadable,
        logging_writable=logging_writable,
        journaling_writable=journaling_writable,
        memory_path_available=memory_path_available,
    )

    data = HealthStatusData(
        health_state=health_state,
        healthy=healthy,
        startup_state=startup_state,
        api_reachable=api_reachable,
        runtime_reachable=runtime_reachable,
        ollama_reachable=ollama_reachable,
        searxng_reachable=searxng_reachable,
        config_loadable=config_loadable,
        logging_writable=logging_writable,
        journaling_writable=journaling_writable,
        memory_path_available=memory_path_available,
        last_health_check_utc=_utc_now_iso(),
        health_notes=warnings.copy(),
        subsystems=subsystems,
    )

    trace_summary = TraceSummary(
        route_used="status.health",
        selected_role=None,
        selected_runtime=None,
        selected_model_runtime_tag=None,
        used_fallback=None,
        log_written=logging_writable,
        journal_written=journaling_writable,
    )

    return (
        data,
        envelope_status,
        capability_state,
        warnings,
        errors,
        trace_summary,
    )


def get_runtime_status() -> dict[str, Any]:
    """
    Return a structured envelope payload for GET /status/runtime.
    """
    request_id = _new_request_id()

    try:
        (
            data,
            envelope_status,
            capability_state,
            locality,
            approval_state,
            warnings,
            errors,
            trace_summary,
        ) = _build_runtime_status_data()

        envelope = build_response_envelope(
            status=envelope_status,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="runtime_status",
            capability_state=capability_state,
            locality=locality,
            approval_state=approval_state,
            warnings=warnings,
            errors=errors,
            trace_summary=trace_summary,
            data=data,
        )
        return envelope.to_payload()

    except Exception as exc:
        LOGGER.exception("Failed to assemble runtime status", exc_info=exc)

        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="runtime_status",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Runtime status inspection failed unexpectedly: {exc}"],
            trace_summary=TraceSummary(
                route_used="status.runtime",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()


def get_health_status() -> dict[str, Any]:
    """
    Return a structured envelope payload for GET /status/health.
    """
    request_id = _new_request_id()

    try:
        (
            data,
            envelope_status,
            capability_state,
            warnings,
            errors,
            trace_summary,
        ) = _build_health_status_data()

        envelope = build_response_envelope(
            status=envelope_status,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="health_status",
            capability_state=capability_state,
            locality=LocalityState.LOCAL if envelope_status != EnvelopeStatus.UNAVAILABLE else LocalityState.UNKNOWN,
            approval_state=ApprovalState.NOT_NEEDED if envelope_status != EnvelopeStatus.UNAVAILABLE else ApprovalState.UNKNOWN,
            warnings=warnings,
            errors=errors,
            trace_summary=trace_summary,
            data=data,
        )
        return envelope.to_payload()

    except Exception as exc:
        LOGGER.exception("Failed to assemble health status", exc_info=exc)

        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="health_status",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Health status inspection failed unexpectedly: {exc}"],
            trace_summary=TraceSummary(
                route_used="status.health",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()


__all__ = (
    "get_health_status",
    "get_runtime_status",
)


def _determine_invoker_state(
    runtime_available: bool,
    last_fields: dict[str, Any],
) -> str:
    """
    Determine the compact invoker state without inventing a second invoker.

    This is a narrow trust surface about the governed invocation path itself,
    not the whole runtime.
    """
    if not runtime_available:
        return "unavailable"

    invocation_status = _coerce_string(last_fields.get("last_invocation_status"), "")
    approval_needed = last_fields.get("approval_needed")
    used_fallback = _coerce_bool(last_fields.get("used_fallback"), False)
    last_error = _coerce_string(last_fields.get("last_error"), "")

    if invocation_status == InvocationStatus.BLOCKED.value:
        return "blocked"

    if approval_needed is True:
        return "approval_needed"

    if used_fallback or invocation_status == InvocationStatus.ERROR.value or last_error:
        return "degraded"

    return "available"


def get_invoker_status() -> dict[str, Any]:
    """
    Return a structured envelope payload for GET /status/invoker.

    This is a narrow truth surface for the governed invoker path, distinct from
    broader runtime and subsystem health surfaces.
    """
    request_id = _new_request_id()

    try:
        runtime_available, runtime_error = _get_runtime_import_truth()
        snapshot = _load_runtime_bridge_snapshot()
        last_fields = _extract_last_runtime_fields(snapshot)

        invoker_state = _determine_invoker_state(runtime_available, last_fields)

        if invoker_state in {"available", "approval_needed", "blocked"}:
            capability_state = CapabilityState.LIVE
        elif invoker_state == "degraded":
            capability_state = CapabilityState.DEGRADED
        elif invoker_state == "unavailable":
            capability_state = CapabilityState.UNAVAILABLE
        else:
            capability_state = CapabilityState.UNKNOWN

        locality = (
            LocalityState.LOCAL
            if _coerce_bool(last_fields.get("stayed_local"), True)
            else LocalityState.CROSSED_BOUNDARY
        )

        approval_needed = last_fields.get("approval_needed")
        if approval_needed is True:
            approval_state = ApprovalState.NEEDED
        elif approval_needed is False:
            approval_state = ApprovalState.NOT_NEEDED
        else:
            approval_state = ApprovalState.UNKNOWN

        normalized_invocation_status = _coerce_string(
            last_fields.get("last_invocation_status"),
            InvocationStatus.UNKNOWN.value,
        )
        if normalized_invocation_status not in {status.value for status in InvocationStatus}:
            normalized_invocation_status = InvocationStatus.UNKNOWN.value

        warnings: list[str] = []
        errors: list[str] = []

        if runtime_error:
            errors.append(runtime_error)

        if invoker_state == "approval_needed":
            warnings.append(
                "Most recent invoker work is awaiting approval; no side-effecting action has been completed."
            )

        if invoker_state == "blocked":
            warnings.append(
                "Invoker path is available, but current or most recent work is blocked by governed boundary rules."
            )

        if invoker_state == "degraded":
            warnings.append(
                "Invoker path is available, but fallback or recent invocation issues are present."
            )

        data = {
            "invoker_state": invoker_state,
            "invoker_available": runtime_available,
            "selected_role": _coerce_string(last_fields.get("selected_role"), "") or None,
            "selected_runtime": _coerce_string(last_fields.get("selected_runtime"), "") or None,
            "selected_model_runtime_tag": _coerce_string(
                last_fields.get("selected_model_runtime_tag"),
                "",
            )
            or None,
            "stayed_local": _coerce_bool(last_fields.get("stayed_local"), True),
            "used_fallback": _coerce_bool(last_fields.get("used_fallback"), False),
            "fallback_from": _coerce_string(last_fields.get("fallback_from"), "") or None,
            "fallback_to": _coerce_string(last_fields.get("fallback_to"), "") or None,
            "approval_needed": approval_needed,
            "last_request_id": _coerce_string(last_fields.get("last_request_id"), "") or None,
            "last_invocation_status": normalized_invocation_status,
            "last_error": _coerce_string(last_fields.get("last_error"), "") or None,
            "last_updated_utc": (
                _coerce_string(snapshot.get("timestamp_utc"), "")
                or _coerce_string(snapshot.get("updated_at_utc"), "")
                or _coerce_string(snapshot.get("last_updated_utc"), "")
                or _utc_now_iso()
            ),
        }

        envelope_status = (
            EnvelopeStatus.UNAVAILABLE
            if invoker_state == "unavailable"
            else EnvelopeStatus.OK
        )

        trace_summary = TraceSummary(
            route_used="status.invoker",
            selected_role=data["selected_role"],
            selected_runtime=data["selected_runtime"],
            selected_model_runtime_tag=data["selected_model_runtime_tag"],
            used_fallback=data["used_fallback"],
            log_written=None,
            journal_written=None,
        )

        envelope = build_response_envelope(
            status=envelope_status,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="invoker_status",
            capability_state=capability_state,
            locality=locality,
            approval_state=approval_state,
            warnings=warnings,
            errors=errors,
            trace_summary=trace_summary,
            data=data,
        )
        return envelope.to_payload()

    except Exception as exc:
        LOGGER.exception("Failed to assemble invoker status", exc_info=exc)

        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="invoker_status",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Invoker status inspection failed unexpectedly: {exc}"],
            trace_summary=TraceSummary(
                route_used="status.invoker",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()
