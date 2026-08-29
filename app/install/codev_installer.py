"""Bounded local installer for the reviewed official Codev VSIX.

This module is part of the packaged Elysia command.  It accepts one local
archive, validates its exact public-package boundary, invokes an allowlisted
VS Code-family executable without a shell, and writes only sanitized XDG
receipt/profile truth.  It never downloads or publishes an extension.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any
from zipfile import BadZipFile, ZipFile

import yaml

from .codev_service import (
    CODEV_CONTRACT_VERSION,
    CODEV_EXTENSION_ID,
    CODEV_VERSION,
    codev_receipt_path,
)
from .paths import ElysiaPaths, ensure_elysia_directories, resolve_elysia_paths


MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ENTRY_COUNT = 500
SUPPORTED_EDITORS = {"code", "code-insiders", "codium", "vscodium"}
SUPPORTED_PROFILES = {"core", "workstation", "creator", "developer"}
_CREDENTIAL_NAMES = {
    ".env",
    "id_rsa",
    "id_dsa",
    "id_ed25519",
    "credentials",
    "token",
    "tokens",
}


class CodevInstallError(ValueError):
    """Raised before installation when a local VSIX violates the contract."""


@dataclass(frozen=True)
class CodevPackageInspection:
    filename: str
    sha256: str
    entry_count: int
    uncompressed_bytes: int
    extension_id: str
    version: str


@dataclass(frozen=True)
class CodevInstallResult:
    package: CodevPackageInspection
    editor: str
    profile_selected: bool
    existing_profile_preserved: bool
    receipt_written: bool

    def public_summary(self) -> dict[str, Any]:
        return {
            "status": "installed",
            "extension_id": self.package.extension_id,
            "version": self.package.version,
            "package_filename": self.package.filename,
            "package_sha256": self.package.sha256,
            "entry_count": self.package.entry_count,
            "editor": self.editor,
            "profile_selected": self.profile_selected,
            "existing_profile_preserved": self.existing_profile_preserved,
            "receipt_storage": "XDG user data",
            "raw_paths_exposed": False,
            "download_performed": False,
            "publication_performed": False,
            "shell_used": False,
        }


def _safe_archive_name(name: str) -> bool:
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return False
    parts = PurePosixPath(name).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _credential_shaped(name: str) -> bool:
    basename = PurePosixPath(name.lower()).name
    return (
        basename in _CREDENTIAL_NAMES
        or basename.startswith(".env.")
        or basename.startswith("credentials.")
        or basename.startswith("token.")
        or basename.startswith("tokens.")
        or basename.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def inspect_codev_vsix(vsix_path: str | Path) -> CodevPackageInspection:
    target = Path(vsix_path).expanduser()
    if not target.is_absolute() or target.is_symlink() or not target.is_file():
        raise CodevInstallError("A non-symlink absolute path to a local VSIX is required.")
    if target.suffix.lower() != ".vsix":
        raise CodevInstallError("The reviewed package must use the .vsix extension.")
    if target.stat().st_size > MAX_ARCHIVE_BYTES:
        raise CodevInstallError("The Codev VSIX exceeds the 50 MiB local package limit.")

    try:
        with ZipFile(target) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRY_COUNT:
                raise CodevInstallError("The Codev VSIX exceeds the 500-entry local package limit.")
            total_bytes = sum(item.file_size for item in entries)
            if total_bytes > MAX_UNCOMPRESSED_BYTES:
                raise CodevInstallError("The Codev VSIX exceeds the 100 MiB uncompressed package limit.")
            manifest_entries = [item for item in entries if item.filename == "extension/package.json"]
            if len(manifest_entries) != 1:
                raise CodevInstallError("The VSIX must contain exactly one extension/package.json manifest.")
            for item in entries:
                if not _safe_archive_name(item.filename):
                    raise CodevInstallError("The VSIX contains an unsafe archive path.")
                if item.flag_bits & 0x1:
                    raise CodevInstallError("Encrypted VSIX entries are not supported.")
                unix_mode = (item.external_attr >> 16) & 0o170000
                if unix_mode and unix_mode not in {stat.S_IFREG, stat.S_IFDIR}:
                    raise CodevInstallError("The VSIX contains a link or special-file entry.")
                if _credential_shaped(item.filename):
                    raise CodevInstallError("The VSIX contains credential-shaped material.")
            manifest = json.loads(archive.read(manifest_entries[0]).decode("utf-8"))
    except (BadZipFile, UnicodeError, json.JSONDecodeError, OSError) as exc:
        raise CodevInstallError("The Codev VSIX could not be validated.") from exc

    if not isinstance(manifest, dict):
        raise CodevInstallError("The VSIX manifest is invalid.")
    if manifest.get("name") != "elysia-codev" or manifest.get("publisher") != "ecosyneva-commons":
        raise CodevInstallError("The VSIX does not identify the official Elysia Codev extension.")
    if manifest.get("version") != CODEV_VERSION:
        raise CodevInstallError("The VSIX version does not match the packaged Developer-profile contract.")
    package_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    return CodevPackageInspection(
        filename=target.name,
        sha256=package_hash,
        entry_count=len(entries),
        uncompressed_bytes=total_bytes,
        extension_id=CODEV_EXTENSION_ID,
        version=CODEV_VERSION,
    )


def resolve_codev_editor(editor: str | None = None) -> Path:
    requested = (editor or "").strip()
    if requested:
        candidate = Path(requested).expanduser()
        resolved = candidate if candidate.is_absolute() else Path(shutil.which(requested) or "")
    else:
        found = next((shutil.which(item) for item in ("code", "code-insiders", "codium", "vscodium") if shutil.which(item)), None)
        resolved = Path(found or "")
    if not str(resolved) or not resolved.is_absolute() or not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise CodevInstallError("No compatible VS Code-family editor command was found.")
    if resolved.name not in SUPPORTED_EDITORS:
        raise CodevInstallError("The editor command is not an allowlisted VS Code-family executable.")
    return resolved


def _atomic_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _plan_developer_profile(paths: ElysiaPaths) -> tuple[str, bool]:
    profile_path = paths.config_dir / "install" / "profiles.yaml"
    existing_profile = profile_path.exists()
    additional_profiles: list[str] = []
    if existing_profile:
        try:
            payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise CodevInstallError(
                "The existing local profile selection could not be validated."
            ) from exc
        if not isinstance(payload, dict) or set(payload) - {
            "version",
            "contract_version",
            "active_profile",
            "additional_profiles",
        }:
            raise CodevInstallError(
                "The existing local profile selection could not be validated."
            )
        active_profile = payload.get("active_profile", "core")
        raw_additional = payload.get("additional_profiles", [])
        if (
            payload.get("version") != 1
            or active_profile not in SUPPORTED_PROFILES
            or not isinstance(raw_additional, list)
            or any(item not in SUPPORTED_PROFILES for item in raw_additional)
        ):
            raise CodevInstallError(
                "The existing local profile selection could not be validated."
            )
        additional_profiles = [
            item
            for item in raw_additional
            if item not in {"core", "developer"}
        ]
        if active_profile not in {"core", "developer"}:
            additional_profiles.insert(0, active_profile)
        additional_profiles = list(dict.fromkeys(additional_profiles))
    content = yaml.safe_dump(
        {
            "version": 1,
            "contract_version": "elysia-local-profile-selection-1.0",
            "active_profile": "developer",
            "additional_profiles": additional_profiles,
        },
        sort_keys=False,
    )
    return content, existing_profile


def _write_developer_profile(paths: ElysiaPaths, content: str) -> None:
    profile_path = paths.config_dir / "install" / "profiles.yaml"
    profile_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile_path.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".profiles.", dir=profile_path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, profile_path)
        profile_path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def install_codev_vsix(
    vsix_path: str | Path,
    *,
    editor: str | None = None,
    select_profile: bool = False,
    paths: ElysiaPaths | None = None,
) -> CodevInstallResult:
    inspection = inspect_codev_vsix(vsix_path)
    editor_path = resolve_codev_editor(editor)
    resolved_paths = paths or resolve_elysia_paths()
    profile_content: str | None = None
    existing_profile_preserved = False
    if select_profile:
        profile_content, existing_profile_preserved = _plan_developer_profile(
            resolved_paths
        )
    completed = subprocess.run(
        [str(editor_path), "--install-extension", str(Path(vsix_path)), "--force"],
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        raise CodevInstallError("VS Code did not accept the reviewed Codev VSIX.")
    ensure_elysia_directories(resolved_paths)
    _atomic_private_json(
        codev_receipt_path(resolved_paths),
        {
            "schema_version": 1,
            "extension_id": CODEV_EXTENSION_ID,
            "version": CODEV_VERSION,
            "contract_version": CODEV_CONTRACT_VERSION,
            "install_state": "installed_by_user",
            "package_sha256": inspection.sha256,
            "raw_paths_exposed": False,
        },
    )
    profile_selected = profile_content is not None
    if profile_content is not None:
        _write_developer_profile(resolved_paths, profile_content)
    return CodevInstallResult(
        package=inspection,
        editor=editor_path.name,
        profile_selected=profile_selected,
        existing_profile_preserved=existing_profile_preserved,
        receipt_written=True,
    )


__all__ = (
    "CodevInstallError",
    "CodevInstallResult",
    "CodevPackageInspection",
    "inspect_codev_vsix",
    "install_codev_vsix",
    "resolve_codev_editor",
)
