"""Bounded installed-package helpers. None changes workspace/profile authority."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from app.install.codev_core import inspect_core
from app.install.codev_installer import CodevInstallError, inspect_codev_vsix, resolve_codev_editor
from app.install.paths import resolve_elysia_paths


def check_package(root: Path) -> dict:
    from core.codev.contracts import CorePackageManifest
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise CodevInstallError("Select one extracted local package directory.")
    payload = root / "usr/lib/codev"
    manifest = payload / "runtime.json"
    if manifest.is_symlink() or manifest.stat().st_size > 16384:
        raise CodevInstallError("Invalid Codev package manifest.")
    identity = CorePackageManifest.model_validate_json(manifest.read_text())
    for filename, digest in [("codev-core", identity.core_sha256), ("elysia-codev-1.0.0.vsix", identity.adapter_sha256)]:
        target = payload / filename
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022:
            raise CodevInstallError("Invalid Codev package payload permissions.")
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise CodevInstallError("Codev package digest mismatch.")
    inspect_codev_vsix(payload / "elysia-codev-1.0.0.vsix")
    return {"status": "verified", "version": "1.0.0", "package_contract": identity.contract, "workspace_grants": []}


def install_adapter(editor: str | None, profile: str | None) -> dict:
    identity = inspect_core()
    if not identity.compatible or identity.adapter is None:
        raise CodevInstallError("Install or repair Codev Core before installing its optional adapter.")
    inspect_codev_vsix(identity.adapter)
    executable = resolve_codev_editor(editor)
    if profile is not None and (not profile.strip() or len(profile) > 128 or any(ord(char) < 32 for char in profile)):
        raise CodevInstallError("The VS Code profile name is invalid.")
    command = [str(executable), "--install-extension", str(identity.adapter), "--force"]
    if profile:
        command += ["--profile", profile]
    completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180, check=False)
    if completed.returncode != 0:
        raise CodevInstallError("The editor did not accept the bundled adapter. Core remains installed.")
    return {"status": "adapter_installed", "version": "1.0.0", "workspace_grants": [], "profile_authority_changed": False}


def write_user_autostart() -> dict:
    paths = resolve_elysia_paths()
    identity = inspect_core(paths)
    if not identity.compatible:
        raise CodevInstallError("A verified installed Core is required for login startup.")
    home = Path.home()
    launcher = home / ".local/bin/codev"
    if not launcher.is_file() or launcher.is_symlink() or launcher.stat().st_uid != os.getuid():
        raise CodevInstallError("The owned user launcher is unavailable.")
    # Freedesktop Exec quoting, including a second escape layer for backslash
    # in a Desktop Entry string. No shell or PATH lookup is involved.
    command = str(launcher)
    if any(ord(char) < 32 for char in command):
        raise CodevInstallError("Control characters in the user launcher path are unsupported.")
    command = command.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    command = command.replace("\\", "\\\\")
    directory = paths.config_dir.parent / "autostart"
    if directory.is_symlink():
        raise CodevInstallError("The autostart directory is unsafe.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / "codev-core.desktop"
    temporary = directory / f".codev-core-{os.getpid()}.desktop"
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write('[Desktop Entry]\nType=Application\nName=Codev Core\nComment=Start the private installed Core without workspace grants.\n'
                         f'Exec="{command}" runtime ensure\nNoDisplay=true\nTerminal=false\n')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"login_startup": "installed", "workspace_grants": []}
