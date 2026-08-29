"""Safety checks for local visual stewardship."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from app.api.coding_visual_type_registry import CodingVisualTypeDescriptor


MAX_VISUAL_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 60_000_000
MAX_FRAMES = 120
MAX_OCR_CHARS = 4000
THUMBNAIL_SIZE = (640, 640)
MAX_SVG_BYTES = 2 * 1024 * 1024
MAX_SVG_NODES = 5000


@dataclass(frozen=True)
class CodingVisualSafetyResult:
    allowed: bool
    status: str
    size_bytes: int = 0
    blocked_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    risk_flags: dict[str, Any] = field(default_factory=dict)


def check_visual_safety(path: Path, descriptor: CodingVisualTypeDescriptor) -> CodingVisualSafetyResult:
    warnings = list(descriptor.notes)
    risk_flags = {
        "exif_privacy_risk": descriptor.exif_privacy_risk,
        "svg_security_risk": descriptor.svg_security_risk,
        "animated": descriptor.animated,
        "raw_pixel_audit_disabled": True,
        "cloud_vision_disabled": True,
    }
    if descriptor.adapter == "blocked":
        return CodingVisualSafetyResult(False, "blocked", blocked_reason="unsupported_visual_type", warnings=warnings, risk_flags=risk_flags)
    if not path.exists():
        return CodingVisualSafetyResult(False, "blocked", blocked_reason="missing_path", warnings=warnings, risk_flags=risk_flags)
    if not path.is_file():
        return CodingVisualSafetyResult(False, "blocked", blocked_reason="visual_path_must_be_file", warnings=warnings, risk_flags=risk_flags)
    size_bytes = path.stat().st_size
    if size_bytes > MAX_VISUAL_BYTES:
        return CodingVisualSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason="visual_file_too_large", warnings=warnings, risk_flags={**risk_flags, "large_file": True})
    if descriptor.adapter == "svg":
        if size_bytes > MAX_SVG_BYTES:
            return CodingVisualSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason="svg_too_large", warnings=warnings, risk_flags=risk_flags)
        return CodingVisualSafetyResult(True, "allowed_with_svg_sanitization", size_bytes=size_bytes, warnings=warnings + ["SVG is never rendered unsanitized."], risk_flags=risk_flags)
    try:
        with Image.open(path) as image:
            width, height = image.size
            frame_count = int(getattr(image, "n_frames", 1) or 1)
            pixels = width * height * frame_count
    except Exception as exc:
        return CodingVisualSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason=f"image_open_failed:{exc.__class__.__name__}", warnings=warnings, risk_flags=risk_flags)
    if width * height > MAX_PIXELS:
        return CodingVisualSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason="image_pixel_count_too_large", warnings=warnings, risk_flags={**risk_flags, "large_pixels": True})
    if frame_count > MAX_FRAMES:
        return CodingVisualSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason="too_many_frames", warnings=warnings, risk_flags={**risk_flags, "too_many_frames": True})
    if pixels > MAX_PIXELS * 2:
        warnings.append("Animated image total pixel work is high; preview is bounded to sampled frames.")
    return CodingVisualSafetyResult(True, "allowed_with_bounded_preview", size_bytes=size_bytes, warnings=warnings, risk_flags={**risk_flags, "width": width, "height": height, "frame_count": frame_count})


__all__ = (
    "CodingVisualSafetyResult",
    "MAX_FRAMES",
    "MAX_OCR_CHARS",
    "MAX_PIXELS",
    "MAX_SVG_BYTES",
    "MAX_SVG_NODES",
    "MAX_VISUAL_BYTES",
    "THUMBNAIL_SIZE",
    "check_visual_safety",
)
