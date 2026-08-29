"""Load the bounded ArchiveForge extraction policy."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from app.api.project_paths import config_path


DEFAULT_LIMITS: dict[str, int] = {
    "max_archive_input_bytes": 512 * 1024 * 1024,
    "max_projected_uncompressed_bytes": 1024 * 1024 * 1024,
    "max_single_file_bytes": 256 * 1024 * 1024,
    "max_members": 10_000,
    "max_directories": 2_000,
    "max_nested_archive_depth": 1,
    "max_output_path_chars": 240,
    "max_extraction_runtime_seconds": 60,
    "max_extraction_bytes_written": 1024 * 1024 * 1024,
    "max_worker_stdout_bytes": 2 * 1024 * 1024,
    "max_worker_stderr_bytes": 64 * 1024,
    "max_metadata_member_bytes": 1024 * 1024,
    "max_manifest_members_in_response": 500,
    "compression_ratio_warn": 100,
    "compression_ratio_block": 1000,
}


def load_archive_limits(path: Path | None = None) -> dict[str, Any]:
    policy_path = path or config_path("policies", "archive_extraction_limits.yaml")
    loaded: dict[str, Any] = {}
    try:
        import yaml

        candidate = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        if isinstance(candidate, dict):
            loaded = candidate
    except Exception:
        loaded = {}
    limits = deepcopy(DEFAULT_LIMITS)
    configured_limits = loaded.get("limits") if isinstance(loaded.get("limits"), dict) else {}
    for key, default in DEFAULT_LIMITS.items():
        try:
            value = int(configured_limits.get(key, default))
        except (TypeError, ValueError):
            value = default
        limits[key] = max(1, value)
    return {
        "version": str(loaded.get("version") or "archive-extraction-limits-0.1"),
        "limits": limits,
        "permissions": dict(loaded.get("permissions") or {}),
        "member_policy": dict(loaded.get("member_policy") or {}),
    }


def public_archive_limits() -> dict[str, Any]:
    policy = load_archive_limits()
    return {
        "version": policy["version"],
        "limits": dict(policy["limits"]),
        "permissions": dict(policy["permissions"]),
        "member_policy": dict(policy["member_policy"]),
    }


__all__ = ("DEFAULT_LIMITS", "load_archive_limits", "public_archive_limits")
