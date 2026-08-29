"""Portable internal resolution for optional worker interpreters.

Resolved paths are execution inputs only. Callers must not serialize them into
API responses, diagnostics, receipts, or logs.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping


_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _absolute_file(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    return (
        candidate
        if candidate.is_absolute() and candidate.is_file() and os.access(candidate, os.X_OK)
        else None
    )


def _environment_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    explicit = str(os.environ.get("ELYSIA_WORKER_ENVS_ROOT") or "").strip()
    if explicit:
        root = Path(explicit).expanduser()
        if root.is_absolute():
            roots.append(root)

    prefix_text = str(os.environ.get("CONDA_PREFIX") or "").strip()
    if prefix_text:
        prefix = Path(prefix_text).expanduser()
        if prefix.is_absolute():
            roots.append(prefix.parent if prefix.parent.name == "envs" else prefix / "envs")

    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def resolve_worker_python(
    config: Mapping[str, Any],
    *,
    override_env: str,
    allow_current_interpreter: bool,
) -> Path | None:
    """Resolve an exact interpreter without embedding workstation defaults."""
    explicit = _absolute_file(os.environ.get(override_env))
    if explicit is not None:
        return explicit
    configured = _absolute_file(config.get("python_path"))
    if configured is not None:
        return configured

    environment = str(config.get("environment") or "").strip()
    if environment and _ENVIRONMENT_NAME.fullmatch(environment):
        for root in _environment_roots():
            candidate = root / environment / "bin" / "python"
            try:
                resolved_root = root.resolve(strict=True)
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(resolved_root / environment)
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                return resolved

    current = _absolute_file(sys.executable) if allow_current_interpreter else None
    return current


__all__ = ("resolve_worker_python",)
