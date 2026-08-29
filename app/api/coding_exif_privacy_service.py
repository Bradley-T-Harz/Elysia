"""EXIF/privacy reporting for visual stewardship."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import ExifTags, Image


GPS_TAG = "GPSInfo"
PRIVACY_TAGS = {"Make", "Model", "DateTime", "DateTimeOriginal", "Artist", "Copyright", "Software", "OwnerName", "BodySerialNumber", "LensSerialNumber"}


def _tag_name(tag: int) -> str:
    return str(ExifTags.TAGS.get(tag, tag))


def exif_privacy_report(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            raw_exif = image.getexif()
            tags = {_tag_name(tag): value for tag, value in raw_exif.items()}
            gps = raw_exif.get_ifd(ExifTags.IFD.GPSInfo) if raw_exif else {}
    except Exception:
        return {"exif_present": False, "gps_present": False, "privacy_fields": [], "warnings": ["EXIF could not be read safely."]}
    privacy_fields = sorted(name for name in tags if name in PRIVACY_TAGS)
    gps_present = bool(gps or GPS_TAG in tags)
    if gps_present:
        privacy_fields.append("gps_coordinates_present")
    warnings: list[str] = []
    if gps_present:
        warnings.append("GPS EXIF appears present; precise coordinates are not returned in audit-safe summaries.")
    if privacy_fields:
        warnings.append("Camera/device/author/time metadata may identify people, places, or equipment.")
    return {
        "exif_present": bool(raw_exif),
        "gps_present": gps_present,
        "privacy_fields": privacy_fields,
        "orientation": tags.get("Orientation"),
        "icc_profile_present": False,
        "warnings": warnings,
    }


__all__ = ("exif_privacy_report",)
