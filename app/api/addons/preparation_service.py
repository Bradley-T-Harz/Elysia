"""Non-executing Developer Forge add-on package preparation plans."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from app.api.addons.manifest_validator import validate_manifest_payload
from app.api.addons.path_safety import MAX_FILE_COUNT, MAX_PACKAGE_BYTES, validate_package_entry
from app.api.addons.types import sanitize_public_text
from app.api.schemas.addons import DeveloperAddonPackagePlanRequest


_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_RISKY_KINDS = {"archive", "binary"}


def prepare_developer_package_plan(request: DeveloperAddonPackagePlanRequest) -> dict[str, Any]:
    """Validate caller-supplied static inventory; never reads or writes source files."""
    manifest, manifest_errors, manifest_warnings, risk_flags = validate_manifest_payload(request.manifest)
    errors = list(manifest_errors)
    warnings = list(manifest_warnings)
    seen: set[str] = set()
    total_size = 0
    risky_count = 0
    for item in request.files:
        normalized = item.relative_path.replace("\\", "/")
        path_errors = validate_package_entry(normalized)
        if path_errors:
            errors.extend(f"Source inventory path rejected: {PurePosixPath(normalized).name or 'unnamed'}" for _ in path_errors[:1])
        if normalized in seen:
            errors.append(f"Duplicate source inventory entry: {PurePosixPath(normalized).name}")
        seen.add(normalized)
        total_size += item.size_bytes
        if item.sha256 and not _SHA256_RE.fullmatch(item.sha256):
            errors.append(f"Source inventory checksum is not SHA-256: {PurePosixPath(normalized).name}")
        if item.kind in _RISKY_KINDS:
            risky_count += 1
    if len(request.files) > MAX_FILE_COUNT:
        errors.append(f"Source inventory exceeds maximum file count of {MAX_FILE_COUNT}.")
    if total_size > MAX_PACKAGE_BYTES:
        errors.append(f"Source inventory exceeds package preparation limit of {MAX_PACKAGE_BYTES} bytes.")
    if not request.files:
        warnings.append("No source inventory was supplied; package preparation cannot advance beyond manifest review.")

    addon_id = manifest.addon_id if manifest else str(request.manifest.get("addon_id", "unresolved"))
    version = manifest.version if manifest else str(request.manifest.get("version", "unresolved"))
    output_name = request.output_name or f"{addon_id}-{version}.elysia-addon"
    output_name = PurePosixPath(output_name).name
    if not output_name.endswith(".elysia-addon"):
        errors.append("Developer Forge output name must end with .elysia-addon.")

    ready = not errors and manifest is not None and bool(request.files)
    return {
        "plan_state": "ready_for_local_package_build" if ready else "blocked_by_static_contract",
        "addon_id": sanitize_public_text(addon_id),
        "version": sanitize_public_text(version),
        "output_label": sanitize_public_text(output_name),
        "source_kind": request.source_kind,
        "file_count": len(request.files),
        "total_size_bytes": total_size,
        "risky_output_count": risky_count,
        "manifest_valid": manifest is not None and not manifest_errors,
        "errors": [sanitize_public_text(item) for item in dict.fromkeys(errors)],
        "warnings": [sanitize_public_text(item) for item in dict.fromkeys(warnings)],
        "risk_flags": [sanitize_public_text(item) for item in risk_flags],
        "package_written": False,
        "local_only": True,
        "will_upload": False,
        "will_submit": False,
        "will_publish": False,
        "will_add_remote": False,
        "will_push": False,
        "will_execute": False,
        "credential_access_allowed": False,
        "telemetry_allowed": False,
        "next_step": (
            "A later exact-approved local packager may build the immutable archive from this reviewed inventory."
            if ready
            else "Resolve all static contract errors before local package creation."
        ),
        "raw_paths_exposed": False,
    }


__all__ = ("prepare_developer_package_plan",)
