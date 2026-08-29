"""Truthful archive/container capability registry for ArchiveForge."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import shutil
from typing import Any

from app.api.schemas.archive import (
    ArchiveAutonomyTruth,
    ArchiveToolStatus,
    ArchiveTypeDescriptor,
)


ARCHIVE_POLICY_VERSION = "archive-types-0.1"
EXTRACTION_POLICY_VERSION = "archive-extraction-limits-0.1"


@dataclass(frozen=True)
class _DescriptorSpec:
    type_id: str
    label: str
    extensions: tuple[str, ...]
    inspection_state: str
    extraction_state: str
    package_container: bool = False
    selected_extraction: bool = False
    list_supported: bool | None = None
    tool_license_status: str = "not_applicable"
    notes: tuple[str, ...] = ()


_SPECS: tuple[_DescriptorSpec, ...] = (
    _DescriptorSpec(
        "zip",
        "ZIP archive",
        (".zip",),
        "available",
        "extract_sandbox_only",
        selected_extraction=True,
        notes=("Selected regular files may be extracted only into a server-owned sandbox after exact approval.",),
    ),
    _DescriptorSpec(
        "tar",
        "TAR archive",
        (".tar",),
        "available",
        "extract_sandbox_only",
        selected_extraction=True,
        notes=("Links, devices, FIFOs, sockets, ownership, and dangerous permissions are never materialized.",),
    ),
    _DescriptorSpec(
        "tar_gz",
        "Compressed TAR archive",
        (".tar.gz", ".tgz"),
        "available",
        "extract_sandbox_only",
        selected_extraction=True,
        notes=("Selected regular files may be extracted only into a server-owned sandbox after exact approval.",),
    ),
    _DescriptorSpec(
        "7z",
        "7-Zip archive",
        (".7z",),
        "available",
        "list_only",
        notes=("External listing is fixed-argument and noninteractive; extraction is not enabled in this proven slice.",),
    ),
    _DescriptorSpec(
        "rar",
        "RAR archive",
        (".rar",),
        "available",
        "lab_only",
        tool_license_status="mixed_multiverse_nonfree_sensitive",
        notes=(
            "RAR listing uses locally present tooling when available; creation is disabled.",
            "RAR tooling is license-sensitive and needs separate review before bundling or redistribution.",
        ),
    ),
    _DescriptorSpec(
        "whl",
        "Python wheel",
        (".whl",),
        "available",
        "unavailable_by_design",
        package_container=True,
        notes=("Metadata and entry points are inspected as inert data; pip install and import are unavailable by design.",),
    ),
    _DescriptorSpec(
        "jar",
        "Java archive",
        (".jar",),
        "available",
        "unavailable_by_design",
        package_container=True,
        notes=("Manifest, signatures, classes, and native libraries are inspected statically; java -jar is unavailable by design.",),
    ),
    _DescriptorSpec(
        "vsix",
        "VS Code extension package",
        (".vsix",),
        "available",
        "unavailable_by_design",
        package_container=True,
        notes=("Extension metadata is inspected statically; installation and activation are unavailable by design.",),
    ),
    _DescriptorSpec(
        "appimage",
        "AppImage executable container",
        (".appimage",),
        "list_only",
        "unavailable_by_design",
        package_container=True,
        list_supported=False,
        notes=(
            "Identification is static. The AppImage is never run, mounted, or invoked with --appimage-extract.",
            "Payload listing remains unavailable when it cannot be achieved without executing the container.",
        ),
    ),
    _DescriptorSpec(
        "deb",
        "Debian package",
        (".deb",),
        "available",
        "unavailable_by_design",
        package_container=True,
        notes=("Control/data members and maintainer-script presence are inspected statically; dpkg/apt installation is unavailable by design.",),
    ),
)


UNKNOWN_ARCHIVE = ArchiveTypeDescriptor(
    type_id="unknown",
    label="Unsupported or unrecognized container",
    extensions=[],
    inspection_state="unsupported",
    extraction_state="unsupported",
    list_supported=False,
    metadata_supported=False,
    notes=["ArchiveForge only handles explicitly registered local container types."],
)


def _descriptor(spec: _DescriptorSpec) -> ArchiveTypeDescriptor:
    return ArchiveTypeDescriptor(
        type_id=spec.type_id,
        label=spec.label,
        extensions=list(spec.extensions),
        inspection_state=spec.inspection_state,  # type: ignore[arg-type]
        extraction_state=spec.extraction_state,  # type: ignore[arg-type]
        package_container=spec.package_container,
        list_supported=(
            spec.list_supported
            if spec.list_supported is not None
            else spec.inspection_state in {"available", "list_only", "extract_sandbox_only", "lab_only"}
        ),
        metadata_supported=True,
        selected_sandbox_extraction_supported=spec.selected_extraction,
        install_state="unavailable_by_design",
        execute_state="unavailable_by_design",
        creation_state="unavailable_by_design",
        tool_license_status=spec.tool_license_status,
        notes=list(spec.notes),
    )


ARCHIVE_TYPES: tuple[ArchiveTypeDescriptor, ...] = tuple(_descriptor(spec) for spec in _SPECS)
ARCHIVE_EXTENSIONS: tuple[str, ...] = tuple(sorted({extension for spec in _SPECS for extension in spec.extensions}))


def descriptor_for_type(type_id: str) -> ArchiveTypeDescriptor:
    normalized = str(type_id or "").lower().replace(".", "_")
    for descriptor in ARCHIVE_TYPES:
        if descriptor.type_id == normalized:
            return descriptor
    return UNKNOWN_ARCHIVE


def archive_type_from_extension(path: Path | str) -> str:
    lower_name = Path(str(path)).name.lower()
    for spec in _SPECS:
        if any(lower_name.endswith(extension) for extension in spec.extensions):
            return spec.type_id
    return "unknown"


def is_registered_archive_path(path: Path | str) -> bool:
    return archive_type_from_extension(path) != "unknown"


def _tool_status(tool: str, purpose: str, *, license_status: str = "system_tool") -> ArchiveToolStatus:
    resolved = shutil.which(tool)
    return ArchiveToolStatus(
        tool=tool,
        available=bool(resolved),
        path_hash=sha256(str(resolved).encode("utf-8")).hexdigest()[:24] if resolved else None,
        purpose=purpose,
        license_status=license_status,
    )


def archive_tool_status() -> list[ArchiveToolStatus]:
    return [
        _tool_status("file", "static content identification"),
        _tool_status("7zz", "noninteractive 7z/RAR listing"),
        _tool_status("7z", "fallback noninteractive 7z/RAR listing"),
        _tool_status("lsar", "RAR listing fallback", license_status="mixed_multiverse_nonfree_sensitive"),
        _tool_status("unrar", "RAR tool presence truth only", license_status="mixed_multiverse_nonfree_sensitive"),
        _tool_status("unsquashfs", "non-executing SquashFS tooling presence truth"),
        _tool_status("dpkg-deb", "Debian package tool presence truth only"),
        _tool_status("jar", "Java archive tool presence truth only"),
        _tool_status("readelf", "static ELF inspection tooling presence truth"),
    ]


def archive_registry_payload() -> dict[str, Any]:
    return {
        "policy_version": ARCHIVE_POLICY_VERSION,
        "extraction_policy_version": EXTRACTION_POLICY_VERSION,
        "formats": [descriptor.to_payload() for descriptor in ARCHIVE_TYPES],
        "tools": [status.to_payload() for status in archive_tool_status()],
        "autonomy": ArchiveAutonomyTruth().to_payload(),
        "hard_boundaries": {
            "install": "unavailable_by_design",
            "execute": "unavailable_by_design",
            "import": "unavailable_by_design",
            "automatic_open": "unavailable_by_design",
            "project_root_extraction": "blocked",
            "autonomous_extraction": "blocked",
        },
    }


__all__ = (
    "ARCHIVE_EXTENSIONS",
    "ARCHIVE_POLICY_VERSION",
    "ARCHIVE_TYPES",
    "EXTRACTION_POLICY_VERSION",
    "UNKNOWN_ARCHIVE",
    "archive_registry_payload",
    "archive_tool_status",
    "archive_type_from_extension",
    "descriptor_for_type",
    "is_registered_archive_path",
)
