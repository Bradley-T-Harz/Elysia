"""System-wide emergency posture, cancellation, and restart recovery."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Callable

from app.api import account_service
from app.cognition.compute_governor import ComputeLedger
from app.ids import new_id
from app.install.paths import ElysiaPaths, ensure_elysia_directories, resolve_elysia_paths


EMERGENCY_CONTRACT_VERSION = "system-emergency-stop-v1"
_STOP_EVENT = threading.Event()
_LOCK = threading.RLock()
_REQUEST_EVENTS: dict[str, threading.Event] = {}
_REQUEST_OWNERS: dict[str, str] = {}
_CANCELLERS: dict[str, Callable[[], int | bool | None]] = {}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_default() -> dict[str, Any]:
    return {
        "contract": EMERGENCY_CONTRACT_VERSION,
        "active": False,
        "resume_required": False,
        "trigger_id": None,
        "triggered_at_utc": None,
        "triggered_by_user_id": None,
        "reason": None,
        "reason_code": None,
        "reason_detail_stored": False,
        "internet_effectively_enabled": False,
        "runtime_autonomy_override": 1,
        "sealed_memory_relocked": True,
        "cleanup": {},
        "restart_recovery_performed": False,
        "last_reset_at_utc": None,
        "content_free": True,
    }


def _read(paths: ElysiaPaths) -> dict[str, Any]:
    try:
        value = json.loads(paths.emergency_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _safe_default()
    return value if isinstance(value, dict) else _safe_default()


def _write(paths: ElysiaPaths, payload: dict[str, Any]) -> None:
    ensure_elysia_directories(paths)
    path = paths.emergency_state_path
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".emergency-state-", suffix=".json", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def initialize_emergency_state(paths: ElysiaPaths | None = None) -> dict[str, Any]:
    resolved = paths or resolve_elysia_paths()
    state = _read(resolved)
    if state.get("active"):
        _STOP_EVENT.set()
        if not state.get("restart_recovery_performed"):
            state["restart_recovery_performed"] = True
            state["resume_required"] = True
            cleanup = dict(state.get("cleanup") or {})
            cleanup["interrupted_runtime_recovered"] = True
            cleanup["gpu_leases_recovered"] = ComputeLedger(resolved).cancel_all(
                "restart_emergency_recovery"
            )
            state["cleanup"] = cleanup
            _write(resolved, state)
    else:
        _STOP_EVENT.clear()
    return state


def emergency_stop_event() -> threading.Event:
    return _STOP_EVENT


def emergency_active(paths: ElysiaPaths | None = None) -> bool:
    if _STOP_EVENT.is_set():
        return True
    return bool(initialize_emergency_state(paths).get("active"))


def request_cancel_event(request_id: str) -> threading.Event:
    with _LOCK:
        event = _REQUEST_EVENTS.setdefault(request_id, threading.Event())
        if _STOP_EVENT.is_set():
            event.set()
        return event


def bind_request_owner(request_id: str, owner_user_id: str) -> None:
    """Bind a cancellable request to its authenticated content owner."""
    with _LOCK:
        _REQUEST_OWNERS[request_id] = owner_user_id


def cancel_request(request_id: str, owner_user_id: str) -> bool:
    """Cancel only the caller's own active request without exposing its content."""
    with _LOCK:
        event = _REQUEST_EVENTS.get(request_id)
        owner = _REQUEST_OWNERS.get(request_id)
        if event is None or owner != owner_user_id:
            return False
        event.set()
        return True


def release_request(request_id: str) -> None:
    with _LOCK:
        _REQUEST_EVENTS.pop(request_id, None)
        _REQUEST_OWNERS.pop(request_id, None)


def active_request_count() -> int:
    """Return content-free foreground pressure for governed background yield."""

    with _LOCK:
        return len(_REQUEST_EVENTS)


def register_canceller(name: str, callback: Callable[[], int | bool | None]) -> None:
    with _LOCK:
        _CANCELLERS[name] = callback


def unregister_canceller(name: str) -> None:
    with _LOCK:
        _CANCELLERS.pop(name, None)


def _cancel_known_subsystems(paths: ElysiaPaths) -> dict[str, Any]:
    cleanup: dict[str, Any] = {}
    with _LOCK:
        request_events = list(_REQUEST_EVENTS.values())
        callbacks = dict(_CANCELLERS)
    for event in request_events:
        event.set()
    cleanup["active_requests_signalled"] = len(request_events)
    for name, callback in callbacks.items():
        try:
            cleanup[name] = callback()
        except Exception as exc:
            cleanup[name] = f"degraded:{type(exc).__name__}"
    known = (
        ("imageforge", "app.api.imageforge_service", "cancel_all_image_jobs"),
        ("videoforge", "app.api.videoforge_service", "cancel_all_video_jobs"),
        ("archiveforge", "app.api.coding_archive_job_service", "cancel_all_archive_jobs"),
        ("engineeringforge", "app.api.coding_engineering_job_service", "cancel_all_engineering_jobs"),
        ("coding_tasks", "app.api.coding_task_service", "stop_all_coding_tasks"),
        ("sustained_goals", "app.api.project_capability_service", "emergency_stop_all_goals"),
        (
            "soundcloud_pending_authorizations_closed",
            "app.api.soundcloud_connector_service",
            "close_pending_authorizations_for_emergency",
        ),
    )
    import importlib

    for name, module_name, function_name in known:
        try:
            callback = getattr(importlib.import_module(module_name), function_name)
            cleanup[name] = callback()
        except Exception as exc:
            cleanup[name] = f"degraded:{type(exc).__name__}"
    try:
        from app.memory.encryption_service import MemoryEncryptionService

        cleanup["sealed_unlocks_relocked"] = MemoryEncryptionService.relock_all()
    except Exception as exc:
        cleanup["sealed_unlocks_relocked"] = f"degraded:{type(exc).__name__}"
    cleanup["gpu_leases_cancelled"] = ComputeLedger(paths).cancel_all("emergency_stop")
    cleanup["external_connector_network_closed"] = True
    cleanup["canonical_user_data_deleted"] = False
    return cleanup


def activate_emergency_stop(
    *,
    reason: str,
    paths: ElysiaPaths | None = None,
) -> dict[str, Any]:
    resolved = paths or account_service.get_active_elysia_paths()
    try:
        actor = account_service.get_authenticated_governance()
    except account_service.AccountServiceError:
        raise account_service.AccountAuthError(
            "A valid local account session is required to trigger emergency stop."
        )
    with _LOCK:
        current = _read(resolved)
        if current.get("active"):
            _STOP_EVENT.set()
            current["idempotent_repeat"] = True
            return current
        _STOP_EVENT.set()
        cleanup = _cancel_known_subsystems(resolved)
        normalized_reason = " ".join(str(reason or "").split()).casefold()
        reason_code = (
            "desktop_keyboard_shortcut"
            if "keyboard" in normalized_reason
            else "desktop_emergency_control"
            if "desktop" in normalized_reason
            else "cli_emergency_control"
            if "cli" in normalized_reason
            else "operator_requested"
        )
        state = _safe_default()
        state.update(
            active=True,
            resume_required=True,
            trigger_id=new_id("emergencystop"),
            triggered_at_utc=_utc_now(),
            triggered_by_user_id=actor["user_id"],
            reason="Operator emergency stop",
            reason_code=reason_code,
            reason_detail_stored=False,
            cleanup=cleanup,
        )
        _write(resolved, state)
        try:
            store = account_service.AccountStore()
            with store._connect() as conn:
                store._record_event(
                    conn,
                    "system_emergency_stop",
                    actor_user_id=str(actor["user_id"]),
                    safe_details={
                        "trigger_id": state["trigger_id"],
                        "active_requests_signalled": cleanup.get("active_requests_signalled", 0),
                        "content_accessed": False,
                    },
                )
        except Exception:
            state["admin_event_persistence"] = "degraded"
        return state


def reset_emergency_stop(paths: ElysiaPaths | None = None) -> dict[str, Any]:
    resolved = paths or account_service.get_active_elysia_paths()
    actor = account_service.get_authenticated_governance()
    if actor["role"] not in {"installation_owner", "admin"}:
        raise account_service.AccountAuthError(
            "Installation Owner or Admin authority is required to resume after emergency stop."
        )
    with _LOCK:
        prior = _read(resolved)
        state = _safe_default()
        state["last_reset_at_utc"] = _utc_now()
        state["prior_trigger_id"] = prior.get("trigger_id")
        state["reset_by_user_id"] = actor["user_id"]
        _write(resolved, state)
        _STOP_EVENT.clear()
    return state


def emergency_status(paths: ElysiaPaths | None = None) -> dict[str, Any]:
    return initialize_emergency_state(paths)


__all__ = (
    "EMERGENCY_CONTRACT_VERSION",
    "activate_emergency_stop",
    "emergency_active",
    "emergency_status",
    "emergency_stop_event",
    "initialize_emergency_state",
    "register_canceller",
    "bind_request_owner",
    "cancel_request",
    "release_request",
    "request_cancel_event",
    "reset_emergency_stop",
    "unregister_canceller",
)
