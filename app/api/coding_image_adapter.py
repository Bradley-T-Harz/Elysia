"""Raster and animated image adapter for governed visual stewardship."""

from __future__ import annotations

import base64
import io
from hashlib import sha256
from pathlib import Path
from typing import Any

import imageio.v3 as iio
import numpy as np
from PIL import Image, ImageOps

from app.api.coding_exif_privacy_service import exif_privacy_report
from app.api.coding_visual_safety_service import THUMBNAIL_SIZE, check_visual_safety
from app.api.coding_visual_type_registry import detect_visual_type


def _hash_bytes(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _data_url_for_thumbnail(image: Image.Image) -> str:
    safe = ImageOps.exif_transpose(image.convert("RGBA"))
    safe.thumbnail(THUMBNAIL_SIZE)
    buffer = io.BytesIO()
    safe.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        frame_count = int(getattr(image, "n_frames", 1) or 1)
        durations = []
        for index in range(min(frame_count, 10)):
            try:
                image.seek(index)
                durations.append(int(image.info.get("duration") or 0))
            except Exception:
                break
        return {
            "format": image.format,
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "channels": len(image.getbands()),
            "dpi": image.info.get("dpi"),
            "icc_profile_present": bool(image.info.get("icc_profile")),
            "icc_profile_size": len(image.info.get("icc_profile") or b""),
            "transparency": "A" in image.getbands() or "transparency" in image.info,
            "frame_count": frame_count,
            "duration_ms_preview": durations,
            "animated": frame_count > 1,
        }


def inspect_image(path: Path) -> dict[str, Any]:
    descriptor = detect_visual_type(path)
    safety = check_visual_safety(path, descriptor)
    if not safety.allowed:
        return {
            "status": "blocked",
            "descriptor": descriptor.to_payload(),
            "blocked_reason": safety.blocked_reason,
            "metadata": {},
            "preview": {},
            "warnings": safety.warnings,
            "risk_flags": safety.risk_flags,
            "content_hash": None,
            "size_bytes": safety.size_bytes,
        }
    try:
        metadata = image_metadata(path)
        with Image.open(path) as image:
            thumbnail = _data_url_for_thumbnail(image)
        privacy = exif_privacy_report(path)
        geospatial_warning = []
        if descriptor.type_id == "tiff_image":
            try:
                tags = iio.immeta(path)
                if any(str(key).lower() in {"modeltiepointtag", "modelpixelscaletag", "geokeydirectorytag"} for key in tags):
                    geospatial_warning.append("This TIFF appears geospatial. Use data/raster stewardship for CRS, bands, and geospatial edits.")
            except Exception:
                pass
        warnings = safety.warnings + privacy.get("warnings", []) + geospatial_warning
        return {
            "status": "completed",
            "descriptor": descriptor.to_payload(),
            "content_hash": _hash_bytes(path),
            "size_bytes": safety.size_bytes,
            "metadata": metadata,
            "preview": {"thumbnail_data_url": thumbnail, "thumbnail_format": "png", "thumbnail_max_size": list(THUMBNAIL_SIZE)},
            "exif_privacy": privacy,
            "warnings": warnings,
            "risk_flags": {**safety.risk_flags, "gps_exif_present": bool(privacy.get("gps_present")), "geospatial_tiff_hint": bool(geospatial_warning)},
        }
    except Exception as exc:
        return {"status": "blocked", "descriptor": descriptor.to_payload(), "blocked_reason": f"image_inspect_failed:{exc.__class__.__name__}", "metadata": {}, "preview": {}, "warnings": safety.warnings, "risk_flags": safety.risk_flags, "content_hash": None, "size_bytes": safety.size_bytes}


def deterministic_visual_analysis(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        safe = ImageOps.exif_transpose(image.convert("RGBA"))
        safe.thumbnail((512, 512))
        arr = np.asarray(safe).astype("float32")
    rgb = arr[..., :3]
    alpha = arr[..., 3] if arr.shape[-1] == 4 else None
    grayscale = rgb.mean(axis=2)
    brightness = float(grayscale.mean())
    contrast = float(grayscale.std())
    dominant = []
    flat = rgb.reshape((-1, 3))
    if len(flat):
        rounded = (flat // 32 * 32).astype("uint8")
        colors, counts = np.unique(rounded, axis=0, return_counts=True)
        order = np.argsort(counts)[-5:][::-1]
        dominant = [f"#{int(colors[i][0]):02x}{int(colors[i][1]):02x}{int(colors[i][2]):02x}" for i in order]
    gy, gx = np.gradient(grayscale)
    edge_density = float((np.sqrt(gx * gx + gy * gy) > 30).mean())
    transparent_ratio = float((alpha < 250).mean()) if alpha is not None else 0.0
    return {
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "dominant_colors": dominant,
        "edge_density": round(edge_density, 4),
        "transparent_pixel_ratio": round(transparent_ratio, 4),
        "document_like_hint": contrast > 35 and edge_density > 0.08,
        "analysis_kind": "deterministic_local",
    }


__all__ = ("deterministic_visual_analysis", "image_metadata", "inspect_image")
