"""
Elysia retrieval policy scaffold.

This module builds explicit retrieval-policy objects for scaffold context
gathering. The runtime remains the owner of the decision to retrieve
memory, but the rule construction lives here so it can evolve cleanly.

Current scaffold behavior:
- reads scaffold retrieval controls from memory policy config when present
- supports per-mode overrides on top of scaffold defaults
- supports per-autonomy overrides on top of mode overrides
- validates override containers before using them
- falls back to safe scaffold defaults when config is missing
- can disable local session memory retrieval entirely
- can exclude the current-day session journal path
- returns a small declared policy object for context gathering
"""

from datetime import datetime
from typing import Any, Dict

from .memory_manager import DEFAULT_SESSION_MEMORY_LIMIT, SESSIONS_DIR


def _as_bool(value: Any, default: bool) -> bool:
    """
    Convert loose config values into a boolean with a safe default.
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False

    return default


def _as_int(value: Any, default: int) -> int:
    """
    Convert loose config values into a positive integer with a safe default.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed < 1:
        return default

    return parsed


def _get_scaffold_retrieval_config(configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pull scaffold retrieval controls from loaded memory policy config.
    """
    memory_group = configs.get("memory", {})
    memory_policy = memory_group.get("memory_policy", {})
    scaffold_retrieval = memory_policy.get("scaffold_retrieval", {})

    if isinstance(scaffold_retrieval, dict):
        return scaffold_retrieval

    return {}


def _get_valid_mode_overrides(scaffold_retrieval: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Return only valid mode overrides.

    Valid scaffold rule:
    - mode_overrides must be a dictionary
    - each override value must also be a dictionary
    """
    raw_mode_overrides = scaffold_retrieval.get("mode_overrides", {})

    if not isinstance(raw_mode_overrides, dict):
        return {}

    valid_mode_overrides: Dict[str, Dict[str, Any]] = {}

    for key, value in raw_mode_overrides.items():
        if isinstance(value, dict):
            valid_mode_overrides[str(key)] = value

    return valid_mode_overrides


def _get_valid_autonomy_overrides(
    scaffold_retrieval: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Return only valid autonomy overrides.

    Valid scaffold rule:
    - autonomy_overrides must be a dictionary
    - keys must be numeric strings
    - each override value must also be a dictionary
    """
    raw_autonomy_overrides = scaffold_retrieval.get("autonomy_overrides", {})

    if not isinstance(raw_autonomy_overrides, dict):
        return {}

    valid_autonomy_overrides: Dict[str, Dict[str, Any]] = {}

    for key, value in raw_autonomy_overrides.items():
        key_text = str(key)

        if not key_text.isdigit():
            continue

        if not isinstance(value, dict):
            continue

        valid_autonomy_overrides[key_text] = value

    return valid_autonomy_overrides


def _get_mode_override(
    scaffold_retrieval: Dict[str, Any],
    mode: str,
) -> Dict[str, Any]:
    """
    Pull a mode-specific scaffold retrieval override when present.
    """
    mode_overrides = _get_valid_mode_overrides(scaffold_retrieval)
    return mode_overrides.get(str(mode), {})


def _get_autonomy_override(
    scaffold_retrieval: Dict[str, Any],
    session_state: Any,
) -> Dict[str, Any]:
    """
    Pull an autonomy-level scaffold retrieval override when present.
    """
    autonomy_overrides = _get_valid_autonomy_overrides(scaffold_retrieval)
    try:
        autonomy_level = max(1, min(5, int(getattr(session_state, "autonomy_level", 1))))
    except (TypeError, ValueError):
        autonomy_level = 1

    return autonomy_overrides.get(str(autonomy_level), {})


def build_retrieval_policy(
    session_state: Any,
    mode: str,
    configs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the runtime retrieval policy for scaffold context gathering.

    Current scaffold behavior:
    - uses config-driven scaffold retrieval controls
    - merges scaffold defaults with mode-specific overrides
    - merges autonomy-specific overrides last
    - ignores malformed override containers and invalid override entries
    - defaults to local session journal retrieval
    - excludes the current-day journal path by default
    - keeps the returned policy small and explicit
    """
    scaffold_retrieval = _get_scaffold_retrieval_config(configs)
    mode_override = _get_mode_override(scaffold_retrieval, mode)
    autonomy_override = _get_autonomy_override(scaffold_retrieval, session_state)

    effective_retrieval = {
        key: value
        for key, value in scaffold_retrieval.items()
        if key not in {"mode_overrides", "autonomy_overrides"}
    }
    effective_retrieval.update(mode_override)
    effective_retrieval.update(autonomy_override)

    local_session_memory_enabled = _as_bool(
        effective_retrieval.get("local_session_memory_enabled"),
        True,
    )
    exclude_current_day_journal = _as_bool(
        effective_retrieval.get("exclude_current_day_journal"),
        True,
    )
    session_memory_limit = _as_int(
        effective_retrieval.get("session_memory_limit"),
        DEFAULT_SESSION_MEMORY_LIMIT,
    )

    if not local_session_memory_enabled:
        return {
            "retrieval_enabled": False,
            "exclude_paths": [],
            "retrieval_mode": "local_session_journal_scaffold_disabled",
            "note": "Local session memory retrieval is disabled by scaffold retrieval policy.",
            "limit": 0,
        }

    exclude_paths = []
    retrieval_mode = "local_session_journal_scaffold"
    note = "Recent session memory retrieved from local scaffold journal entries."

    if exclude_current_day_journal:
        current_session_journal_path = (
            SESSIONS_DIR / f"{datetime.now().date().isoformat()}_runtime-session.md"
        )
        exclude_paths = [str(current_session_journal_path)]
        retrieval_mode = "local_session_journal_scaffold_excluding_current_day"
        note = (
            "Recent session memory retrieved from local scaffold journal entries "
            "while excluding the current day session journal path."
        )

    return {
        "retrieval_enabled": True,
        "exclude_paths": exclude_paths,
        "retrieval_mode": retrieval_mode,
        "note": note,
        "limit": session_memory_limit,
    }


if __name__ == "__main__":
    class DemoSessionState:
        autonomy_level = 1
        active_mode = "default"
        memory_layers = ["working", "conversation", "project", "preferences"]

    demo_configs = {
        "memory": {
            "memory_policy": {
                "scaffold_retrieval": {
                    "local_session_memory_enabled": True,
                    "exclude_current_day_journal": True,
                    "session_memory_limit": 3,
                    "mode_overrides": {
                        "tutor": {
                            "session_memory_limit": 3,
                        },
                        "researcher": {
                            "session_memory_limit": 5,
                        },
                        "default": {
                            "session_memory_limit": 2,
                        },
                        "writer": {
                            "local_session_memory_enabled": False,
                        },
                    },
                    "autonomy_overrides": {
                        "1": {
                            "session_memory_limit": 4,
                        },
                        "2": {
                            "local_session_memory_enabled": False,
                        },
                    },
                }
            }
        }
    }

    print(build_retrieval_policy(DemoSessionState(), "tutor", demo_configs))
