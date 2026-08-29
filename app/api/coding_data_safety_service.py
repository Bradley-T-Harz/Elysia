"""Safety checks for governed science/data stewardship."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.api.coding_data_type_registry import CodingDataTypeDescriptor


MAX_DEFAULT_BYTES = 25 * 1024 * 1024
MAX_PREVIEW_BYTES = 2 * 1024 * 1024
MAX_KMZ_ENTRIES = 1000
MAX_KMZ_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_KMZ_COMPRESSION_RATIO = 100


@dataclass(frozen=True)
class CodingDataSafetyResult:
    allowed: bool
    status: str
    size_bytes: int = 0
    blocked_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    risk_flags: dict[str, Any] = field(default_factory=dict)
    nearest_safe_alternative: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "blocked_reason": self.blocked_reason,
            "warnings": list(self.warnings),
            "risk_flags": dict(self.risk_flags),
            "nearest_safe_alternative": self.nearest_safe_alternative,
        }


def _safe_zip_members(path: Path) -> tuple[bool, list[str], str | None]:
    names: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_KMZ_ENTRIES:
                return False, names, "archive_entry_limit_exceeded"
            total_uncompressed = 0
            total_compressed = 0
            for info in members:
                name = info.filename.replace("\\", "/")
                names.append(name)
                parts = [part for part in name.split("/") if part]
                if name.startswith("/") or ".." in parts:
                    return False, names, "zip_slip_member"
                total_uncompressed += max(0, info.file_size)
                total_compressed += max(0, info.compress_size)
                if total_uncompressed > MAX_KMZ_UNCOMPRESSED_BYTES:
                    return False, names, "archive_uncompressed_size_limit_exceeded"
            if total_uncompressed and total_uncompressed / max(1, total_compressed) > MAX_KMZ_COMPRESSION_RATIO:
                return False, names, "archive_compression_ratio_limit_exceeded"
    except zipfile.BadZipFile:
        return False, names, "bad_zip_container"
    return True, names, None


def check_data_safety(path: Path, descriptor: CodingDataTypeDescriptor) -> CodingDataSafetyResult:
    warnings = list(descriptor.notes)
    risk_flags: dict[str, Any] = {
        "binary_container": descriptor.binary_container,
        "directory_store": descriptor.directory_store,
        "sidecar_required": descriptor.sidecar_required,
        "mutation_requires_transaction": descriptor.mutation_requires_transaction,
        "mutation_requires_backup": descriptor.mutation_requires_backup,
        "derived_copy_preferred": descriptor.derived_copy_preferred,
    }

    if descriptor.adapter == "blocked":
        return CodingDataSafetyResult(False, "blocked", blocked_reason="unsupported_data_type", warnings=warnings, risk_flags=risk_flags)
    if descriptor.directory_store:
        if not path.exists() or not path.is_dir():
            return CodingDataSafetyResult(False, "blocked", blocked_reason="missing_zarr_directory_store", warnings=warnings, risk_flags=risk_flags)
        size_bytes = 0
        for child in path.rglob("*"):
            if child.is_symlink():
                return CodingDataSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason="zarr_symlink_escape_risk", warnings=warnings, risk_flags=risk_flags)
            if child.is_file():
                size_bytes += child.stat().st_size
                if size_bytes > MAX_DEFAULT_BYTES:
                    return CodingDataSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason="data_file_too_large", warnings=warnings, risk_flags={**risk_flags, "large_dataset": True}, nearest_safe_alternative="Use a smaller derived subset or raise the server-owned policy limit explicitly.")
        return CodingDataSafetyResult(True, "allowed_with_bounded_preview", size_bytes=size_bytes, warnings=warnings, risk_flags=risk_flags)

    if not path.exists():
        return CodingDataSafetyResult(False, "blocked", blocked_reason="missing_path", warnings=warnings, risk_flags=risk_flags)
    if not path.is_file():
        return CodingDataSafetyResult(False, "blocked", blocked_reason="directory_not_allowed_for_this_data_type", warnings=warnings, risk_flags=risk_flags)

    size_bytes = path.stat().st_size
    if size_bytes > MAX_DEFAULT_BYTES:
        return CodingDataSafetyResult(
            False,
            "blocked",
            size_bytes=size_bytes,
            blocked_reason="data_file_too_large",
            warnings=warnings,
            risk_flags={**risk_flags, "large_dataset": True},
            nearest_safe_alternative="Use a smaller derived subset or raise the server-owned policy limit explicitly.",
        )
    if descriptor.sidecar_required:
        missing = [
            suffix
            for suffix in (".shp", ".shx", ".dbf")
            if not path.with_suffix(suffix).exists()
        ]
        if missing:
            return CodingDataSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason="missing_required_sidecars", warnings=warnings + [f"Missing shapefile sidecars: {', '.join(missing)}"], risk_flags={**risk_flags, "missing_sidecars": missing})
        if any(path.with_suffix(suffix).is_symlink() for suffix in (".shp", ".shx", ".dbf")):
            return CodingDataSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason="shapefile_sidecar_symlink", warnings=warnings, risk_flags=risk_flags)

    if descriptor.type_id == "kmz_vector_archive":
        ok, names, reason = _safe_zip_members(path)
        risk_flags["kmz_members"] = names[:50]
        if not ok:
            return CodingDataSafetyResult(False, "blocked", size_bytes=size_bytes, blocked_reason=reason, warnings=warnings, risk_flags=risk_flags)

    return CodingDataSafetyResult(True, "allowed_with_bounded_preview", size_bytes=size_bytes, warnings=warnings, risk_flags=risk_flags)


__all__ = (
    "CodingDataSafetyResult",
    "MAX_DEFAULT_BYTES",
    "MAX_KMZ_COMPRESSION_RATIO",
    "MAX_KMZ_ENTRIES",
    "MAX_KMZ_UNCOMPRESSED_BYTES",
    "MAX_PREVIEW_BYTES",
    "check_data_safety",
)
