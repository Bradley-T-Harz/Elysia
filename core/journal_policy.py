"""
Elysia journal policy scaffold.

This module builds an effective journal policy from normalized memory
configuration so journaling can be governed by declared policy rather than
runtime-local assumptions.

Current scaffold precedence:
1. scaffold_journaling base config
2. mode_overrides["default"]
3. mode_overrides[current mode]
4. autonomy_overrides[current autonomy level]
5. boundary_overrides for any triggered boundary flags

The result is one effective policy object that downstream code can pass
directly into the journal writer.
"""

from typing import Any, Dict, List, Optional


_VALID_JOURNAL_MODES = {"minimal", "standard", "detailed", "skip"}

_LEGACY_JOURNAL_MODE_ALIASES = {
    "scaffold_minimal": "minimal",
    "scaffold_memory_minimal": "standard",
    "scaffold_local_memory_minimal": "standard",
}


def _coerce_bool(value: Any, default: bool) -> bool:
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


def _coerce_int(value: Any, default: int = 0) -> int:
    """
    Coerce a value into an integer when possible.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _canonical_autonomy_level(value: Any) -> int:
    return max(1, min(5, _coerce_int(value, 1)))


def _as_mapping(value: Any) -> Dict[str, Any]:
    """
    Return a shallow-copied mapping or an empty dict.
    """
    if not isinstance(value, dict):
        return {}

    return dict(value)


def _coerce_string_list(value: Any) -> List[str]:
    """
    Coerce a value into a clean list of strings.
    """
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]

    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]

    text = str(value).strip()
    return [text] if text else []


def _normalize_journal_mode(value: Any) -> str:
    """
    Normalize a journal mode into a supported canonical mode.
    """
    mode = str(value or "minimal").strip().lower()
    mode = _LEGACY_JOURNAL_MODE_ALIASES.get(mode, mode)

    if mode not in _VALID_JOURNAL_MODES:
        return "minimal"

    return mode


def _merge_policy_layer(
    base: Dict[str, Any],
    overrides: Any,
) -> Dict[str, Any]:
    """
    Merge one policy layer onto a base policy if the override is a mapping.
    """
    if not isinstance(overrides, dict):
        return dict(base)

    merged = dict(base)
    merged.update(overrides)
    return merged


def _get_scaffold_journaling_config(configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract scaffold_journaling config from the loaded config tree.
    """
    memory_configs = _as_mapping(configs.get("memory", {}))
    memory_policy = _as_mapping(memory_configs.get("memory_policy", {}))
    return _as_mapping(memory_policy.get("scaffold_journaling", {}))


def _resolve_effective_journal_mode(effective_policy: Dict[str, Any]) -> str:
    """
    Resolve the final journal mode.

    If a layer explicitly set journal_mode, that wins.
    Otherwise, default_journal_mode determines the final mode.
    """
    if "journal_mode" in effective_policy:
        return _normalize_journal_mode(effective_policy.get("journal_mode"))

    return _normalize_journal_mode(
        effective_policy.get("default_journal_mode", "minimal")
    )


def _finalize_journal_policy(
    effective_policy: Dict[str, Any],
    mode: str,
    autonomy_level: int,
    applied_boundary_overrides: List[str],
) -> Dict[str, Any]:
    """
    Normalize the final effective journal policy into a deterministic shape.
    """
    journaling_enabled = _coerce_bool(
        effective_policy.get(
            "journaling_enabled",
            effective_policy.get("journal_write_allowed", True),
        ),
        True,
    )

    journal_write_allowed = _coerce_bool(
        effective_policy.get("journal_write_allowed", journaling_enabled),
        journaling_enabled,
    )

    journal_mode = _resolve_effective_journal_mode(effective_policy)

    finalized = dict(effective_policy)
    finalized["journaling_enabled"] = journaling_enabled
    finalized["journal_write_allowed"] = journal_write_allowed
    finalized["journal_mode"] = journal_mode
    finalized["include_plan_summary"] = _coerce_bool(
        finalized.get("include_plan_summary"),
        False,
    )
    finalized["include_retrieval_summary"] = _coerce_bool(
        finalized.get("include_retrieval_summary"),
        False,
    )
    finalized["include_boundary_flags"] = _coerce_bool(
        finalized.get("include_boundary_flags"),
        False,
    )
    finalized["include_memory_class"] = _coerce_bool(
        finalized.get("include_memory_class"),
        False,
    )
    finalized["include_policy_summary"] = _coerce_bool(
        finalized.get("include_policy_summary"),
        True,
    )
    finalized["redact_sensitive_content"] = _coerce_bool(
        finalized.get("redact_sensitive_content"),
        True,
    )

    if not finalized["journal_write_allowed"] or finalized["journal_mode"] == "skip":
        finalized["journal_write_allowed"] = False
        finalized["journal_mode"] = "skip"

    note_parts = [
        "Effective journal policy built from normalized scaffold_journaling config.",
        f"mode={mode}",
        f"autonomy_level={autonomy_level}",
    ]

    if applied_boundary_overrides:
        note_parts.append(
            "boundary_overrides=" + ", ".join(applied_boundary_overrides)
        )

    finalized["applied_boundary_overrides"] = list(applied_boundary_overrides)
    finalized["note"] = " ".join(note_parts)

    return finalized


def build_journal_policy(
    configs: Dict[str, Any],
    mode: str,
    autonomy_level: int = 1,
    boundary_flags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build an effective journal policy from normalized scaffold_journaling config.

    Parameters:
    - configs:
        Full loaded config tree from load_all_configs().
    - mode:
        The currently selected runtime mode.
    - autonomy_level:
        The current runtime autonomy level.
    - boundary_flags:
        Any boundary flags raised during policy review.

    Returns:
    One effective journal policy object suitable for passing into the journal
    writer.
    """
    scaffold_journaling = _get_scaffold_journaling_config(configs)

    mode_overrides = _as_mapping(scaffold_journaling.get("mode_overrides", {}))
    autonomy_overrides = _as_mapping(scaffold_journaling.get("autonomy_overrides", {}))
    boundary_overrides = _as_mapping(scaffold_journaling.get("boundary_overrides", {}))

    effective_policy: Dict[str, Any] = {
        "journaling_enabled": _coerce_bool(
            scaffold_journaling.get("journaling_enabled", True),
            True,
        ),
        "default_journal_mode": str(
            scaffold_journaling.get("default_journal_mode", "minimal") or "minimal"
        ),
        "journal_write_allowed": _coerce_bool(
            scaffold_journaling.get("journaling_enabled", True),
            True,
        ),
        "include_plan_summary": _coerce_bool(
            scaffold_journaling.get("include_plan_summary", False),
            False,
        ),
        "include_retrieval_summary": _coerce_bool(
            scaffold_journaling.get("include_retrieval_summary", False),
            False,
        ),
        "include_boundary_flags": _coerce_bool(
            scaffold_journaling.get("include_boundary_flags", False),
            False,
        ),
        "include_memory_class": _coerce_bool(
            scaffold_journaling.get("include_memory_class", False),
            False,
        ),
        "include_policy_summary": _coerce_bool(
            scaffold_journaling.get("include_policy_summary", True),
            True,
        ),
        "redact_sensitive_content": _coerce_bool(
            scaffold_journaling.get("redact_sensitive_content", True),
            True,
        ),
    }

    effective_policy = _merge_policy_layer(
        effective_policy,
        mode_overrides.get("default", {}),
    )
    effective_policy = _merge_policy_layer(
        effective_policy,
        mode_overrides.get(str(mode), {}),
    )
    effective_policy = _merge_policy_layer(
        effective_policy,
        autonomy_overrides.get(str(_canonical_autonomy_level(autonomy_level)), {}),
    )

    applied_boundary_overrides: List[str] = []

    for flag in _coerce_string_list(boundary_flags):
        override = boundary_overrides.get(str(flag), {})

        if isinstance(override, dict) and override:
            effective_policy = _merge_policy_layer(effective_policy, override)
            applied_boundary_overrides.append(str(flag))

    return _finalize_journal_policy(
        effective_policy=effective_policy,
        mode=str(mode),
        autonomy_level=_canonical_autonomy_level(autonomy_level),
        applied_boundary_overrides=applied_boundary_overrides,
    )


if __name__ == "__main__":
    demo_configs = {
        "memory": {
            "memory_policy": {
                "scaffold_journaling": {
                    "journaling_enabled": True,
                    "default_journal_mode": "standard",
                    "include_plan_summary": True,
                    "include_retrieval_summary": True,
                    "include_boundary_flags": True,
                    "include_memory_class": True,
                    "include_policy_summary": True,
                    "redact_sensitive_content": True,
                    "mode_overrides": {
                        "default": {
                            "default_journal_mode": "minimal",
                        },
                        "researcher": {
                            "default_journal_mode": "detailed",
                        },
                    },
                    "autonomy_overrides": {
                        "2": {
                            "default_journal_mode": "minimal",
                            "include_plan_summary": False,
                        }
                    },
                    "boundary_overrides": {
                        "sealed_private_memory": {
                            "default_journal_mode": "minimal",
                            "include_retrieval_summary": False,
                        }
                    },
                }
            }
        }
    }

    demo_policy = build_journal_policy(
        configs=demo_configs,
        mode="researcher",
        autonomy_level=2,
        boundary_flags=["sealed_private_memory"],
    )

    print(demo_policy)
