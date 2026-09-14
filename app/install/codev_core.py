"""Portable Codev Core package identity, independent of editors and authority.

The manifest and executable are installed package payload, never a source-tree
marker or a receipt minted by an editor. Reading identity grants no operations.
System packages and digest-keyed user packages share this exact contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import stat

from app.install.paths import ElysiaPaths, resolve_elysia_paths
from core.codev.contracts import CorePackageManifest

CORE_CONTRACT = CorePackageManifest.model_fields["contract"].default
RUNTIME_CONTRACT = CorePackageManifest.model_fields["runtime_contract"].default
PRODUCT_VERSION = CorePackageManifest.model_fields["version"].default
MANIFEST_NAME = "runtime.json"


@dataclass(frozen=True)
class CoreIdentity:
    state: str
    installed: bool = False
    compatible: bool = False
    version: str | None = None
    executable: Path | None = None
    adapter: Path | None = None
    note: str = "Codev Core is not installed."
    installation_id: str | None = None


def package_roots(paths: ElysiaPaths | None = None) -> tuple[Path, Path]:
    resolved = paths or resolve_elysia_paths()
    # The sole deliberate symlink is the installer's atomic current release.
    return (resolved.data_dir.parent / "codev" / "current" / "usr" / "lib" / "codev",
            Path("/usr/lib/codev"))


def _metadata(path: Path, owner: int) -> tuple[int, ...]:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
            or info.st_nlink != 1 or info.st_mode & 0o022):
        raise ValueError("unsafe_package_payload")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@lru_cache(maxsize=8)
def _digest(path: Path, metadata: tuple[int, ...], owner: int) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if _metadata(path, owner) != metadata:
            raise ValueError("package_changed_during_validation")
        return digest.hexdigest()
    except BaseException:
        # fdopen owns fd, including on read errors.
        raise


def inspect_core(paths: ElysiaPaths | None = None) -> CoreIdentity:
    for index, root in enumerate(package_roots(paths)):
        manifest = root / MANIFEST_NAME
        if not manifest.exists() and not manifest.is_symlink():
            continue
        owner = os.getuid() if index == 0 else 0
        try:
            actual = root.resolve(strict=True)
            if index == 0:
                releases = root.parents[3] / "releases"
                # User packages may only select an immutable sibling release.
                actual.relative_to(releases.resolve(strict=True))
            for parent in (actual, *actual.parents):
                info = parent.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022 or info.st_uid not in {0, owner}:
                    # /tmp is valid only as an ancestor of a private XDG test
                    # root; its sticky bit prevents replacing that owned root.
                    if not (info.st_mode & stat.S_ISVTX and info.st_uid == 0):
                        raise ValueError("unsafe_package_parent")
            before = _metadata(manifest, owner)
            if before[2] > 16384:
                raise ValueError("manifest_too_large")
            fd = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if _metadata(manifest, owner) != before or not isinstance(payload, dict) or payload.get("product") != "codev-core":
                raise ValueError("invalid_core_manifest")
            version = payload.get("version")
            if version != PRODUCT_VERSION or payload.get("contract") != CORE_CONTRACT or payload.get("runtime_contract") != RUNTIME_CONTRACT:
                return CoreIdentity("incompatible", installed=True, version=version if isinstance(version, str) else None,
                                    note=f"Install Codev Core {PRODUCT_VERSION} to match this Elysia release. Workspace grants remain separate.")
            if payload.get("architecture") != "amd64" or platform.machine() not in {"x86_64", "AMD64"}:
                return CoreIdentity("incompatible", installed=True, version=version, note="This Codev Core artifact requires an amd64 Linux system.")
            executable = root / "codev-core"
            metadata = _metadata(executable, owner)
            if not os.access(executable, os.X_OK) or _digest(executable, metadata, owner) != payload.get("core_sha256"):
                raise ValueError("core_integrity_failed")
            adapter = root / "elysia-codev-1.1.0.vsix"
            # The adapter is optional and cannot affect Core installation truth.
            try:
                if _digest(adapter, _metadata(adapter, owner), owner) != payload.get("adapter_sha256"):
                    adapter = None
            except (OSError, ValueError):
                adapter = None
            generation = [*before, *metadata]
            if index == 0:
                selected = root.parents[2].lstat()
                generation.extend([selected.st_dev, selected.st_ino, selected.st_ctime_ns])
            installation_id = hashlib.sha256(json.dumps(generation).encode()).hexdigest()
            return CoreIdentity("installed", True, True, version, executable, adapter,
                                "Codev Core is installed. Workspace access and pairing require separate grants.", installation_id)
        except (OSError, ValueError, TypeError):
            return CoreIdentity("degraded", installed=True, note="Codev Core package integrity could not be verified. Repair the installed package.")
    return CoreIdentity("absent")
