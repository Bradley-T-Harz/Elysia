"""Load bounded Chunk 7 database and binary inspection policies."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.api.project_paths import config_path


DEFAULT_DATABASE_LIMITS = {
    "max_input_bytes": 1024 * 1024 * 1024,
    "max_schema_objects": 2000,
    "max_columns_per_object": 512,
    "max_indexes": 4000,
    "max_foreign_keys": 4000,
    "max_schema_sql_chars": 8192,
    "max_worker_stdout_bytes": 4 * 1024 * 1024,
    "max_worker_stderr_bytes": 64 * 1024,
    "timeout_seconds": 30,
}

DEFAULT_BINARY_LIMITS = {
    "max_input_bytes": 1024 * 1024 * 1024,
    "max_sections": 512,
    "max_imports": 4096,
    "max_exports": 4096,
    "max_symbols": 4096,
    "max_strings": 256,
    "max_string_chars": 240,
    "max_string_scan_bytes": 16 * 1024 * 1024,
    "max_worker_stdout_bytes": 4 * 1024 * 1024,
    "max_worker_stderr_bytes": 64 * 1024,
    "timeout_seconds": 30,
}


def _load(filename: str, defaults: dict[str, int], fallback_version: str) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    try:
        import yaml

        candidate = yaml.safe_load(config_path("policies", filename).read_text(encoding="utf-8")) or {}
        if isinstance(candidate, dict):
            loaded = candidate
    except Exception:
        loaded = {}
    limits = deepcopy(defaults)
    configured = loaded.get("limits") if isinstance(loaded.get("limits"), dict) else {}
    for key, default in defaults.items():
        try:
            limits[key] = max(1, int(configured.get(key, default)))
        except (TypeError, ValueError):
            limits[key] = default
    return {"version": str(loaded.get("version") or fallback_version), "limits": limits, "posture": dict(loaded.get("posture") or {}), "permissions": dict(loaded.get("permissions") or {})}


def load_database_limits() -> dict[str, Any]:
    return _load("database_inspection_limits.yaml", DEFAULT_DATABASE_LIMITS, "database-inspection-limits-0.1")


def load_binary_limits() -> dict[str, Any]:
    return _load("binary_inspection_limits.yaml", DEFAULT_BINARY_LIMITS, "binary-inspection-limits-0.1")


__all__ = ("DEFAULT_BINARY_LIMITS", "DEFAULT_DATABASE_LIMITS", "load_binary_limits", "load_database_limits")
