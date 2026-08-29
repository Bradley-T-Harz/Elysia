"""
Elysia journal writer scaffold.

This module writes selective, policy-aware session notes into
memory/journal/sessions so the scaffold can leave continuity records
without blindly journaling every run the same way.

At this stage, journal policy is no longer authored here. This writer
consumes an explicit runtime journal policy and obeys it deterministically.
It can now also narrate model-routing reasoning when runtime provides it.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.install.paths import resolve_elysia_paths


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = resolve_elysia_paths().journal_dir

_VALID_JOURNAL_MODES = {"minimal", "standard", "detailed", "skip"}

_LEGACY_JOURNAL_MODE_ALIASES = {
    "scaffold_minimal": "minimal",
    "scaffold_memory_minimal": "standard",
    "scaffold_local_memory_minimal": "standard",
}


def summarize_message(message: str, limit: int = 120) -> str:
    """
    Normalize whitespace and shorten long messages for journal-friendly summaries.
    """
    cleaned = " ".join(str(message).split())

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 3] + "..."


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
    Normalize a journal mode into a supported writer mode.
    """
    mode = str(value or "minimal").strip().lower()
    mode = _LEGACY_JOURNAL_MODE_ALIASES.get(mode, mode)

    if mode not in _VALID_JOURNAL_MODES:
        return "minimal"

    return mode


def normalize_runtime_journal_policy(
    journal_policy: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Normalize a runtime journal policy into a deterministic writer-facing shape.

    This is not the full journal policy builder. It is a defensive final
    normalization step so the writer obeys a stable policy contract.
    """
    raw = journal_policy if isinstance(journal_policy, dict) else {}

    journal_write_allowed = _coerce_bool(
        raw.get("journal_write_allowed", raw.get("journaling_enabled", True)),
        True,
    )
    journal_mode = _normalize_journal_mode(
        raw.get("journal_mode", raw.get("default_journal_mode", "minimal")),
    )

    normalized = {
        "journal_write_allowed": journal_write_allowed,
        "journal_mode": journal_mode,
        "include_plan_summary": _coerce_bool(raw.get("include_plan_summary"), False),
        "include_retrieval_summary": _coerce_bool(
            raw.get("include_retrieval_summary"),
            False,
        ),
        "include_boundary_flags": _coerce_bool(
            raw.get("include_boundary_flags"),
            False,
        ),
        "include_memory_class": _coerce_bool(raw.get("include_memory_class"), False),
        "include_policy_summary": _coerce_bool(
            raw.get("include_policy_summary"),
            True,
        ),
        "redact_sensitive_content": _coerce_bool(
            raw.get("redact_sensitive_content"),
            True,
        ),
        "note": str(raw.get("note", "") or ""),
    }

    if not normalized["journal_write_allowed"] or normalized["journal_mode"] == "skip":
        normalized["journal_write_allowed"] = False
        normalized["journal_mode"] = "skip"

    return normalized


def _should_redact_sensitive_details(
    entry: Dict[str, Any],
    journal_policy: Dict[str, Any],
) -> bool:
    """
    Decide whether sensitive details should be redacted in the written entry.
    """
    if not journal_policy.get("redact_sensitive_content", True):
        return False

    boundary_flags = set(_coerce_string_list(entry.get("boundary_flags", [])))

    sensitive_flags = {
        "sealed_private_memory",
        "sensitive_personal_content",
    }

    return bool(boundary_flags & sensitive_flags)


def _safe_message_summary(
    entry: Dict[str, Any],
    redact_sensitive_details: bool,
) -> str:
    """
    Build a safe message summary for journaling.
    """
    if redact_sensitive_details:
        return "Withheld by journal policy due to sensitive boundary flags."

    explicit_summary = str(entry.get("message_summary", "") or "").strip()

    if explicit_summary:
        return summarize_message(explicit_summary)

    raw_message = str(entry.get("message", "") or "").strip()

    if raw_message:
        return summarize_message(raw_message)

    return "No message summary recorded."


def _maybe_redact(value: Any, redact_sensitive_details: bool) -> str:
    """
    Return a journal-safe value, redacting when required.
    """
    if redact_sensitive_details:
        return "Withheld by journal policy."

    text = str(value or "").strip()
    return text or "none"


def _build_memory_class_reasoning_lines(
    entry: Dict[str, Any],
    redact_sensitive_details: bool,
) -> List[str]:
    """
    Build journal lines explaining the selected memory-class decision path.
    """
    memory_class = _maybe_redact(
        entry.get("memory_class", "unspecified"),
        redact_sensitive_details,
    )
    memory_class_source = _maybe_redact(
        entry.get("memory_class_source", "unknown"),
        redact_sensitive_details,
    )
    primary_memory_class = _maybe_redact(
        entry.get("primary_memory_class", "unspecified"),
        redact_sensitive_details,
    )
    forced_memory_class = _maybe_redact(
        entry.get("forced_memory_class", ""),
        redact_sensitive_details,
    )

    memory_class_boundary_sensitive = _coerce_bool(
        entry.get("memory_class_boundary_sensitive", False),
        False,
    )
    memory_class_requires_boundary_check = _coerce_bool(
        entry.get("memory_class_requires_boundary_check", False),
        False,
    )

    lines: List[str] = [
        "## Memory class reasoning",
        f"- Selected memory class: {memory_class}",
        f"- Memory class source: {memory_class_source}",
        f"- Primary memory class: {primary_memory_class}",
        f"- Forced memory class: {forced_memory_class}",
        f"- Boundary-sensitive memory class: {memory_class_boundary_sensitive}",
        f"- Memory class requires boundary check: {memory_class_requires_boundary_check}",
    ]

    if redact_sensitive_details:
        lines.append(
            "- Memory-class explanation detail was reduced because boundary handling required redaction."
        )
    else:
        if forced_memory_class != "none":
            lines.append(
                "- Boundary handling influenced the selected memory class."
            )
        elif memory_class_source == "primary_memory_class":
            lines.append(
                "- The selected memory class followed the runtime primary memory-class policy."
            )
        elif memory_class_source == "context_memory_class":
            lines.append(
                "- The selected memory class was carried in from context."
            )
        elif memory_class_source == "retrieval_mode_local_session_memory":
            lines.append(
                "- The selected memory class followed local session retrieval context."
            )
        else:
            lines.append(
                "- The selected memory class followed scaffold runtime memory-class reasoning."
            )

    lines.append("")
    return lines


def _build_model_routing_reasoning_lines(
    entry: Dict[str, Any],
    redact_sensitive_details: bool,
) -> List[str]:
    """
    Build journal lines explaining the selected model-routing decision path.
    """
    selected_model_role = _maybe_redact(
        entry.get("selected_model_role", "none"),
        redact_sensitive_details,
    )
    selected_model_target = _maybe_redact(
        entry.get("selected_model_target", "none"),
        redact_sensitive_details,
    )
    selected_model_runtime = _maybe_redact(
        entry.get("selected_model_runtime", "unknown"),
        redact_sensitive_details,
    )
    model_route_stayed_local = _coerce_bool(
        entry.get("model_route_stayed_local", True),
        True,
    )
    model_route_allowed = _coerce_bool(
        entry.get("model_route_allowed", False),
        False,
    )

    lines: List[str] = [
        "## Model routing reasoning",
        f"- Selected model role: {selected_model_role}",
        f"- Selected model target: {selected_model_target}",
        f"- Selected model runtime: {selected_model_runtime}",
        f"- Model route stayed local: {model_route_stayed_local}",
        f"- Model route allowed: {model_route_allowed}",
    ]

    if redact_sensitive_details:
        lines.append(
            "- Model-routing explanation detail was reduced because boundary handling required redaction."
        )
    else:
        if model_route_stayed_local:
            lines.append(
                "- The selected model route remained inside the local-first core."
            )
        else:
            lines.append(
                "- The selected model route allowed an explicitly bounded non-local path."
            )

        if model_route_allowed:
            lines.append(
                "- The selected model route passed current scaffold approval requirements."
            )
        else:
            lines.append(
                "- The selected model route did not meet current scaffold approval requirements."
            )

    lines.append("")
    return lines


def _entry_has_model_routing_data(entry: Dict[str, Any]) -> bool:
    """
    Return True when the entry includes any model-routing fields worth journaling.
    """
    fields = [
        "selected_model_role",
        "selected_model_target",
        "selected_model_runtime",
        "model_route_stayed_local",
        "model_route_allowed",
    ]

    return any(field in entry for field in fields)


def build_journal_lines(
    entry: Dict[str, Any],
    now: datetime,
    journal_policy: Dict[str, Any],
) -> List[str]:
    """
    Build the journal body according to the effective journal policy.
    """
    journal_mode = journal_policy["journal_mode"]
    redact_sensitive_details = _should_redact_sensitive_details(entry, journal_policy)

    config_groups = ", ".join(_coerce_string_list(entry.get("config_groups", []))) or "none"
    boundary_flags = _coerce_string_list(entry.get("boundary_flags", []))
    boundary_flags_text = ", ".join(boundary_flags) or "none"

    retrieved_memory_count = _coerce_int(entry.get("retrieved_memory_count", 0), 0)
    uses_memory_context = _coerce_bool(entry.get("uses_memory_context", False), False)
    reads_private_memory = _coerce_bool(entry.get("reads_private_memory", False), False)
    verified = _coerce_bool(entry.get("verified", False), False)

    memory_context_source = _maybe_redact(
        entry.get("memory_context_source", "unknown"),
        redact_sensitive_details,
    )
    plan_summary = _maybe_redact(
        entry.get("plan_summary", "No plan summary recorded."),
        redact_sensitive_details,
    )

    policy_note = str(journal_policy.get("note", "") or "").strip()
    if not policy_note:
        policy_note = "Writer obeyed the effective runtime journal policy."

    lines: List[str] = [
        "# Runtime Session Note",
        "",
        f"Date: {now.date().isoformat()}",
        "Category: session",
        "",
    ]

    if journal_policy.get("include_policy_summary", True):
        lines.extend(
            [
                "## Journal policy",
                f"- Journal write allowed: {journal_policy['journal_write_allowed']}",
                f"- Journal mode: {journal_mode}",
                f"- Redact sensitive content: {journal_policy['redact_sensitive_content']}",
                f"- Policy note: {policy_note}",
                "",
            ]
        )

    lines.extend(
        [
            "## Context",
            "Scaffold runtime handled a user message without real execution.",
            "",
            "## Key facts",
            f"- Message summary: {_safe_message_summary(entry, redact_sensitive_details)}",
            f"- Intent: {entry.get('intent', 'unknown')}",
            f"- Mode: {entry.get('mode', 'unknown')}",
            f"- Skill count: {_coerce_int(entry.get('skill_count', 0), 0)}",
            f"- Config groups: {config_groups}",
        ]
    )

    if journal_policy.get("include_memory_class", False):
        lines.extend([""])
        lines.extend(
            _build_memory_class_reasoning_lines(
                entry,
                redact_sensitive_details,
            )
        )

        if _entry_has_model_routing_data(entry):
            lines.extend(
                _build_model_routing_reasoning_lines(
                    entry,
                    redact_sensitive_details,
                )
            )

    if journal_policy.get("include_retrieval_summary", False):
        lines.extend(
            [
                "## Retrieval summary",
                f"- Retrieved memory count: {retrieved_memory_count}",
                f"- Uses memory context: {uses_memory_context}",
                f"- Reads private memory: {reads_private_memory}",
                f"- Memory context source: {memory_context_source}",
                "",
            ]
        )
    else:
        lines.append("")

    if journal_policy.get("include_boundary_flags", False):
        lines.extend(
            [
                "## Boundary handling",
                f"- Boundary flags: {boundary_flags_text}",
                "",
            ]
        )

    if journal_policy.get("include_plan_summary", False):
        lines.extend(
            [
                "## Plan summary",
                plan_summary,
                "",
            ]
        )

    if journal_mode == "minimal":
        lines.extend(
            [
                "## Decision or takeaway",
                "Runtime scaffold completed its non-executing path successfully.",
                "",
                "## Uncertainty",
                "This minimal entry preserves continuity while avoiding unnecessary detail.",
                "",
                "## Follow-up",
                "Later phases may refine how this session is categorized and retained.",
            ]
        )
        return lines

    if journal_mode == "standard":
        lines.extend(
            [
                "## Decision or takeaway",
                "Runtime scaffold completed its non-executing path successfully under policy-governed journaling.",
                "",
                "## Verification",
                f"- Verification passed: {verified}",
                "",
                "## Uncertainty",
                "This entry reflects scaffold policy handling with explicit memory-class selection, and model-routing narration remains scaffold-level.",
                "",
                "## Follow-up",
                "Later phases may connect this more explicitly to richer planner rationale, refusals, model-routing intent, and long-term continuity.",
            ]
        )
        return lines

    lines.extend(
        [
            "## Decision or takeaway",
            "Runtime scaffold completed its non-executing path successfully under detailed policy-governed journaling.",
            "",
            "## Verification",
            f"- Verification passed: {verified}",
            "",
            "## Journal reasoning",
            "- This entry was expanded because the effective policy requested detailed journaling.",
            "- Sensitive details may still be redacted when boundary handling requires it.",
            "- Memory-class selection is now recorded more explicitly so the journal better reflects runtime policy reasoning.",
            "- Model-routing selection is now recorded more explicitly when runtime provides it.",
            "",
            "## Uncertainty",
            "This remains scaffold journaling even though planner, runtime, policy, verifier, and model routing now carry richer reasoning.",
            "",
            "## Follow-up",
            "Later phases may attach explicit planner rationale, refusals, model-routing rationale, and deeper memory-class justification to this record.",
        ]
    )
    return lines


def write_session_journal_entry(
    entry: Dict[str, Any],
    journal_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Write or skip a session journal entry according to the supplied journal policy.
    """
    effective_journal_policy = normalize_runtime_journal_policy(journal_policy)

    if not effective_journal_policy["journal_write_allowed"]:
        return {
            "path": "",
            "journal_write_allowed": False,
            "journal_mode": effective_journal_policy["journal_mode"],
            "note": effective_journal_policy["note"] or "Journal writing was skipped by runtime journal policy.",
        }

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    journal_path = SESSIONS_DIR / f"{now.date().isoformat()}_runtime-session.md"

    lines = build_journal_lines(
        entry,
        now,
        effective_journal_policy,
    )

    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write("---\n")
        handle.write("\n".join(lines))
        handle.write("\n---\n")

    return {
        "path": str(journal_path),
        "journal_write_allowed": True,
        "journal_mode": effective_journal_policy["journal_mode"],
        "note": effective_journal_policy["note"] or "Journal entry written according to runtime journal policy.",
    }


if __name__ == "__main__":
    demo_entry = {
        "message_summary": "Can you explain derivatives step by step?",
        "intent": "tutoring",
        "mode": "tutor",
        "skill_count": 4,
        "config_groups": ["memory", "models", "policies", "system"],
        "retrieved_memory_count": 3,
        "uses_memory_context": True,
        "reads_private_memory": True,
        "memory_context_source": "local_session_journal_scaffold",
        "memory_class": "working_memory",
        "primary_memory_class": "working_memory",
        "forced_memory_class": "working_memory",
        "memory_class_source": "forced_memory_class",
        "memory_class_boundary_sensitive": False,
        "memory_class_requires_boundary_check": True,
        "selected_model_role": "primary_general",
        "selected_model_target": "mistral-small-3.1",
        "selected_model_runtime": "ollama",
        "model_route_stayed_local": True,
        "model_route_allowed": True,
        "boundary_flags": ["local_session_memory"],
        "plan_summary": "Explain the concept slowly, then work through an example.",
        "verified": True,
    }

    demo_policy = {
        "journal_write_allowed": True,
        "journal_mode": "standard",
        "include_plan_summary": True,
        "include_retrieval_summary": True,
        "include_boundary_flags": True,
        "include_memory_class": True,
        "include_policy_summary": True,
        "redact_sensitive_content": True,
        "note": "Demo runtime policy requested standard journaling.",
    }

    demo_status = write_session_journal_entry(demo_entry, demo_policy)
    print(demo_status)
