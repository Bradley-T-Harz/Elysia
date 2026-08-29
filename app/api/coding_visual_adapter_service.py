"""Adapter router for visual inspection and preview."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.api.coding_image_adapter import inspect_image
from app.api.coding_svg_adapter import inspect_svg
from app.api.coding_visual_type_registry import detect_visual_type


def inspect_visual_path(path: Path) -> dict[str, Any]:
    descriptor = detect_visual_type(path)
    if descriptor.adapter == "image":
        return inspect_image(path)
    if descriptor.adapter == "svg":
        return inspect_svg(path)
    return {"status": "blocked", "descriptor": descriptor.to_payload(), "blocked_reason": "unsupported_visual_type", "metadata": {}, "preview": {}, "warnings": list(descriptor.notes), "risk_flags": {}, "content_hash": None, "size_bytes": 0}


preview_visual_path = inspect_visual_path


__all__ = ("inspect_visual_path", "preview_visual_path")
