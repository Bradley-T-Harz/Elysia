"""
Elysia context gatherer scaffold.

This module builds a small, structured context object from the user
message, session state, config state, and recent local session memory.
It does not perform semantic retrieval yet. It only assembles bounded,
deterministic scaffold context from an explicit runtime retrieval policy.
"""

from typing import Any, Dict, List

from .memory_manager import get_recent_session_memory


def normalize_message(message: str, limit: int = 120) -> str:
    """
    Normalize whitespace and shorten long messages for context summaries.
    """
    cleaned = " ".join(message.split())

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 3] + "..."


def gather_context(
    message: str,
    session_state: Any,
    configs: Dict[str, Any],
    retrieval_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a small structured context object for the scaffold runtime.

    Current scaffold behavior:
    - records a short request summary
    - records active memory layers from session state
    - records loaded config groups
    - applies the retrieval policy chosen by runtime
    - retrieves a bounded list of recent local session journal entries
    """
    request_summary = normalize_message(message)

    active_memory_layers = list(getattr(session_state, "memory_layers", []))
    available_config_groups = sorted(list(configs.keys()))

    retrieval_enabled = bool(retrieval_policy.get("retrieval_enabled", True))
    exclude_paths = list(retrieval_policy.get("exclude_paths", []))
    retrieval_mode = str(retrieval_policy.get("retrieval_mode", "unknown"))
    retrieval_note = str(retrieval_policy.get("note", ""))
    retrieval_limit = int(retrieval_policy.get("limit", 3) or 0)

    if retrieval_enabled:
        memory_items: List[Dict[str, Any]] = get_recent_session_memory(
            limit=retrieval_limit,
            exclude_paths=exclude_paths,
        )
    else:
        memory_items = []

    retrieved_memory_count = len(memory_items)

    context_items: List[Dict[str, Any]] = [
        {
            "source": "session_state",
            "kind": "memory_layers",
            "value": active_memory_layers,
        },
        {
            "source": "config",
            "kind": "config_groups",
            "value": available_config_groups,
        },
        {
            "source": "memory_manager",
            "kind": "recent_session_memory",
            "value": memory_items,
        },
    ]

    if exclude_paths:
        context_items.append(
            {
                "source": "memory_manager",
                "kind": "excluded_memory_paths",
                "value": exclude_paths,
            }
        )

    return {
        "request_summary": request_summary,
        "active_memory_layers": active_memory_layers,
        "available_config_groups": available_config_groups,
        "retrieved_memory_count": retrieved_memory_count,
        "memory_items": memory_items,
        "context_items": context_items,
        "retrieval_mode": retrieval_mode,
        "note": retrieval_note,
    }


if __name__ == "__main__":
    demo_session_state = type(
        "DemoSessionState",
        (),
        {
            "memory_layers": ["working", "conversation", "project", "preferences"],
        },
    )()

    demo_configs = {
        "memory": {},
        "models": {},
        "policies": {},
        "system": {},
    }

    demo_retrieval_policy = {
        "retrieval_enabled": True,
        "exclude_paths": ["/tmp/2026-03-16_runtime-session.md"],
        "retrieval_mode": "local_session_journal_scaffold_excluding_current_day",
        "note": (
            "Recent session memory retrieved from local scaffold journal entries "
            "while excluding the current day session journal path."
        ),
        "limit": 3,
    }

    print(
        gather_context(
            "Can you explain derivatives step by step?",
            demo_session_state,
            demo_configs,
            demo_retrieval_policy,
        )
    )
