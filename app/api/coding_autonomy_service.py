"""Autonomy policy for coding tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.api.project_paths import policy_path


AUTONOMY_POLICY_PATH = policy_path("coding_autonomy.yaml")


def load_autonomy_policy(path: Path = AUTONOMY_POLICY_PATH) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Coding autonomy policy must be a mapping.")
    return data


def autonomy_is_disabled(policy: dict[str, Any] | None = None) -> bool:
    loaded = policy or load_autonomy_policy()
    return not bool(loaded.get("autonomous_loop_allowed", False))


__all__ = ("AUTONOMY_POLICY_PATH", "autonomy_is_disabled", "load_autonomy_policy")
