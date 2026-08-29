"""
Elysia runtime logger scaffold.

This module writes small, structured runtime log entries so the scaffold
can leave a reviewable trace without enabling any real execution.

At this stage, runtime logs also record the richer memory-class and
model-routing decision paths so logging does not lag behind planner,
runtime, journaling, and model routing.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from app.install.paths import resolve_elysia_paths


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_LOG_DIR = resolve_elysia_paths().log_dir / "runtime"


def summarize_message(message: str, limit: int = 120) -> str:
    """
    Normalize whitespace and shorten long messages for safe logging.
    """
    cleaned = " ".join(str(message).split())

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 3] + "..."


def write_runtime_log(entry: Dict[str, Any]) -> Path:
    """
    Append one structured runtime entry to today's runtime log file.
    """
    RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    log_path = RUNTIME_LOG_DIR / f"{now.date().isoformat()}_runtime.log"

    config_groups = ", ".join(entry.get("config_groups", []))
    selected_skill_id = entry.get("selected_skill_id") or "none"
    retrieved_memory_count = entry.get("retrieved_memory_count", 0)
    uses_memory_context = entry.get("uses_memory_context", False)
    reads_private_memory = entry.get("reads_private_memory", False)

    memory_class = entry.get("memory_class", "unspecified")
    memory_class_source = entry.get("memory_class_source", "unknown")
    primary_memory_class = entry.get("primary_memory_class", "unspecified")
    forced_memory_class = entry.get("forced_memory_class") or "none"
    memory_class_boundary_sensitive = entry.get(
        "memory_class_boundary_sensitive",
        False,
    )
    memory_class_requires_boundary_check = entry.get(
        "memory_class_requires_boundary_check",
        False,
    )

    selected_model_role = entry.get("selected_model_role", "") or "none"
    selected_model_target = entry.get("selected_model_target", "") or "none"
    selected_model_runtime = entry.get("selected_model_runtime", "") or "unknown"
    model_route_stayed_local = entry.get("model_route_stayed_local", True)
    model_route_allowed = entry.get("model_route_allowed", False)

    journal_mode = entry.get("journal_mode", "unknown")
    journal_write_allowed = entry.get("journal_write_allowed", True)

    lines = [
        f"Timestamp: {now.isoformat(timespec='seconds')}",
        "Category: runtime",
        "Severity: info",
        f"Message: {entry.get('message_summary', '')}",
        f"Intent: {entry.get('intent', 'unknown')}",
        f"Mode: {entry.get('mode', 'unknown')}",
        f"Selected skill: {selected_skill_id}",
        f"Skill count: {entry.get('skill_count', 'unknown')}",
        f"Config groups: {config_groups}",
        f"Retrieved memory count: {retrieved_memory_count}",
        f"Uses memory context: {uses_memory_context}",
        f"Reads private memory: {reads_private_memory}",
        f"Memory class: {memory_class}",
        f"Memory class source: {memory_class_source}",
        f"Primary memory class: {primary_memory_class}",
        f"Forced memory class: {forced_memory_class}",
        f"Memory class boundary-sensitive: {memory_class_boundary_sensitive}",
        (
            "Memory class requires boundary check: "
            f"{memory_class_requires_boundary_check}"
        ),
        f"Selected model role: {selected_model_role}",
        f"Selected model target: {selected_model_target}",
        f"Selected model runtime: {selected_model_runtime}",
        f"Model route stayed local: {model_route_stayed_local}",
        f"Model route allowed: {model_route_allowed}",
        f"Journal mode: {journal_mode}",
        f"Journal write allowed: {journal_write_allowed}",
        f"Execution allowed: {entry.get('execution_allowed', False)}",
        f"Verification passed: {entry.get('verified', False)}",
        "Note: Scaffold runtime handled message without real execution.",
        "---",
    ]

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("\n".join(lines) + "\n")

    return log_path


if __name__ == "__main__":
    demo_path = write_runtime_log(
        {
            "message_summary": summarize_message(
                "Can you explain derivatives step by step?"
            ),
            "intent": "tutoring",
            "mode": "tutor",
            "selected_skill_id": "tutoring.tutoring_helper",
            "skill_count": 4,
            "config_groups": ["memory", "models", "policies", "system"],
            "retrieved_memory_count": 2,
            "uses_memory_context": True,
            "reads_private_memory": True,
            "memory_class": "working_memory",
            "memory_class_source": "forced_memory_class",
            "primary_memory_class": "working_memory",
            "forced_memory_class": "working_memory",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": True,
            "selected_model_role": "primary_general",
            "selected_model_target": "mistral-small-3.1",
            "selected_model_runtime": "ollama",
            "model_route_stayed_local": True,
            "model_route_allowed": True,
            "journal_mode": "standard",
            "journal_write_allowed": True,
            "execution_allowed": False,
            "verified": True,
        }
    )
    print(f"Wrote runtime log: {demo_path}")
