"""Exact command allowlist for future approved command execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.api.project_paths import policy_path


ALLOWLIST_PATH = policy_path("coding_command_allowlist.yaml")


def load_command_allowlist(path: Path = ALLOWLIST_PATH) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Coding command allowlist must be a mapping.")
    return data


def normalize_command(command: list[str]) -> list[str]:
    return [str(part).strip() for part in command if str(part).strip()]


def command_has_blocked_term(command: list[str], blocked_terms: list[str]) -> str | None:
    joined = " ".join(command).lower()
    for term in blocked_terms:
        if str(term).lower() in joined:
            return str(term)
    return None


def find_allowlist_match(command: list[str], policy: dict[str, Any] | None = None) -> dict[str, Any] | None:
    loaded = policy or load_command_allowlist()
    normalized = normalize_command(command)
    for entry in loaded.get("allowed_commands") or []:
        if normalize_command(list(entry.get("command") or [])) == normalized:
            return dict(entry)
    return None


def find_allowlist_match_by_id(command_id: str, policy: dict[str, Any] | None = None) -> dict[str, Any] | None:
    loaded = policy or load_command_allowlist()
    for entry in loaded.get("allowed_commands") or []:
        if str(entry.get("id")) == command_id:
            return dict(entry)
    return None


def public_command_catalog(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    loaded = policy or load_command_allowlist()
    entries = []
    for entry in loaded.get("allowed_commands") or []:
        entries.append(
            {
                "command_id": str(entry.get("id") or ""),
                "label": str(entry.get("label") or entry.get("id") or "Approved check"),
                "purpose": str(entry.get("purpose") or "Bounded local repository check."),
                "command": normalize_command(list(entry.get("command") or [])),
                "cwd_policy": str(entry.get("cwd_policy") or "approved_repo"),
                "timeout_seconds": int(entry.get("timeout_seconds", 120)),
                "output_limit_bytes": int(entry.get("output_limit_bytes", 20000)),
                "execution_enabled": bool(loaded.get("execution_enabled", False) and entry.get("execution_enabled", True)),
                "approval_required": True,
                "shell": False,
                "stdin": "closed",
                "network_allowed": False,
                "package_install_allowed": False,
                "disabled_reason": str(entry.get("disabled_reason") or "") or None,
            }
        )
    return {
        "contract_version": "coding-command-catalog-1.0",
        "entries": entries,
        "arbitrary_command_input_allowed": False,
        "shell_allowed": False,
        "package_manager_mutation_allowed": False,
        "git_mutation_allowed": False,
        "network_allowed": False,
    }


__all__ = (
    "ALLOWLIST_PATH",
    "command_has_blocked_term",
    "find_allowlist_match",
    "find_allowlist_match_by_id",
    "load_command_allowlist",
    "normalize_command",
    "public_command_catalog",
)
