"""Load bounded EngineeringForge inspection and preview policy."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from app.api.project_paths import config_path


DEFAULT_INSPECTION_LIMITS: dict[str, int] = {
    "max_input_bytes": 512 * 1024 * 1024,
    "max_text_bytes": 64 * 1024 * 1024,
    "max_xml_bytes": 32 * 1024 * 1024,
    "max_archive_members": 2_000,
    "max_archive_projected_bytes": 2 * 1024 * 1024 * 1024,
    "max_archive_compression_ratio": 1_000,
    "max_entities": 2_000_000,
    "max_triangles": 5_000_000,
    "max_vertices": 5_000_000,
    "max_lines": 2_000_000,
    "max_external_references": 2_000,
    "max_names_in_response": 200,
    "max_preview_segments": 20_000,
    "timeout_seconds": 30,
    "max_worker_stdout_bytes": 4 * 1024 * 1024,
    "max_worker_stderr_bytes": 64 * 1024,
}

DEFAULT_PREVIEW_LIMITS: dict[str, int] = {
    "max_input_bytes": 256 * 1024 * 1024,
    "max_segments": 20_000,
    "max_points": 50_000,
    "max_output_bytes": 8 * 1024 * 1024,
    "width_pixels": 960,
    "height_pixels": 720,
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
    return {
        "version": str(loaded.get("version") or fallback_version),
        "limits": limits,
        "posture": dict(loaded.get("posture") or {}),
        "permissions": dict(loaded.get("permissions") or {}),
    }


def load_engineering_inspection_limits(path: Path | None = None) -> dict[str, Any]:
    del path
    return _load("engineering_inspection_limits.yaml", DEFAULT_INSPECTION_LIMITS, "engineering-inspection-limits-0.1")


def load_engineering_preview_limits(path: Path | None = None) -> dict[str, Any]:
    del path
    return _load("engineering_preview_limits.yaml", DEFAULT_PREVIEW_LIMITS, "engineering-preview-limits-0.1")


def _load_policy_document(filename: str, fallback_version: str) -> dict[str, Any]:
    try:
        import yaml

        loaded = yaml.safe_load(config_path("policies", filename).read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return {"version": fallback_version, "state": "policy_defaults_only"}


def load_engineering_conversion_limits() -> dict[str, Any]:
    return _load_policy_document("engineering_conversion_limits.yaml", "engineering-conversion-limits-0.1")


def load_robot_model_safety() -> dict[str, Any]:
    return _load_policy_document("robot_model_safety.yaml", "robot-model-safety-0.1")


def load_cam_gcode_safety() -> dict[str, Any]:
    return _load_policy_document("cam_gcode_safety.yaml", "cam-gcode-safety-0.1")


__all__ = (
    "DEFAULT_INSPECTION_LIMITS",
    "DEFAULT_PREVIEW_LIMITS",
    "load_cam_gcode_safety",
    "load_engineering_conversion_limits",
    "load_engineering_inspection_limits",
    "load_engineering_preview_limits",
    "load_robot_model_safety",
)
