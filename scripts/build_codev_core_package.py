#!/usr/bin/env python3
"""Build a neutral Debian Codev Core artifact from reviewed compiled inputs.

No source, model weights, profiles, receipts or credentials enter the package.
The optional VSIX is carried for later explicit installation in any profile.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from app.install.codev_installer import inspect_codev_vsix
from app.install.codev_core import CORE_CONTRACT, RUNTIME_CONTRACT, PRODUCT_VERSION


def build(core: Path, adapter: Path, output: Path) -> dict:
    if not core.is_absolute() or not core.is_file() or core.is_symlink():
        raise ValueError("An absolute compiled Core artifact is required.")
    inspection = inspect_codev_vsix(adapter)
    result = subprocess.run([str(core), "version"], check=True, capture_output=True, text=True, timeout=30)
    if result.stdout.strip() != "Elysia 1.1.0":
        raise ValueError("The compiled Core version is incompatible.")
    if "runtime" not in subprocess.run([str(core), "--help"], check=True, capture_output=True, text=True, timeout=30).stdout:
        raise ValueError("The compiled Core lacks the installed runtime contract.")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("Refusing to overwrite an existing distributable artifact.")
    with tempfile.TemporaryDirectory(prefix="codev-core-package-") as temporary:
        root = Path(temporary)
        payload = root / "usr/lib/codev"
        payload.mkdir(parents=True)
        shutil.copyfile(core, payload / "codev-core")
        (payload / "codev-core").chmod(0o755)
        shutil.copyfile(adapter, payload / "elysia-codev-1.1.0.vsix")
        (payload / "elysia-codev-1.1.0.vsix").chmod(0o644)
        manifest = {"product": "codev-core", "version": PRODUCT_VERSION, "contract": CORE_CONTRACT,
                    "runtime_contract": RUNTIME_CONTRACT, "architecture": "amd64",
                    "core_sha256": hashlib.sha256(core.read_bytes()).hexdigest(),
                    "adapter_sha256": inspection.sha256}
        (payload / "runtime.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        binary = root / "usr/bin/codev"
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nset -eu\nexec env -u PYTHONPATH -u LD_LIBRARY_PATH -u CONDA_PREFIX -u CONDA_DEFAULT_ENV /usr/lib/codev/codev-core "$@"\n')
        binary.chmod(0o755)
        autostart = root / "etc/xdg/autostart/codev-core.desktop"
        autostart.parent.mkdir(parents=True)
        autostart.write_text('[Desktop Entry]\nType=Application\nName=Codev Core\nComment=Start the private installed Codev runtime without workspace grants.\nExec=/usr/bin/codev runtime ensure\nTryExec=/usr/bin/codev\nNoDisplay=true\nTerminal=false\n')
        docs = root / "usr/share/doc/codev-core"
        docs.mkdir(parents=True)
        source = Path(__file__).resolve().parents[1]
        shutil.copyfile(source / "LICENSE", docs / "copyright")
        for name in ("NOTICE", "THIRD_PARTY_NOTICES.md", "requirements/THIRD_PARTY_NOTICES.txt"):
            shutil.copyfile(source / name, docs / Path(name).name)
        (docs / "README").write_text('Codev Core 1.1.0\n\nInstall this Debian package with your software installer. VS Code is optional.\nOpen Elysia to use the Codev workroom. Workspace and website access start ungranted.\nInstall the bundled adapter later with: codev codev-adapter --editor code [--profile PROFILE]\nInspect or start the runtime with: codev runtime status / codev runtime ensure\nRepair/reinstall with your package manager. Uninstall with apt remove codev-core.\nUninstall preserves local account data, conversations, models, and repositories.\nNo models or cloud access are enabled by installation.\n')
        control = root / "DEBIAN"
        control.mkdir()
        (control / "control").write_text('Package: codev-core\nVersion: 1.1.0\nArchitecture: amd64\nMaintainer: EcoSyneva Commons LLC\nSection: devel\nPriority: optional\nDepends: libc6 (>= 2.39), libstdc++6, libgcc-s1, zlib1g\nRecommends: git\nDescription: Governed local Codev runtime shared by Elysia and optional native clients\n Includes the private installed Core service and optional VS Code adapter.\n Installation grants no workspace, command, network, or website authority.\n')
        lines = []
        for path in sorted(root.rglob("*")):
            if path.is_dir(): path.chmod(0o755)
            elif path.is_file() and "DEBIAN" not in path.parts:
                if path not in {binary, payload / "codev-core"}: path.chmod(0o644)
                lines.append(hashlib.md5(path.read_bytes()).hexdigest() + "  " + path.relative_to(root).as_posix())
        (control / "md5sums").write_text("\n".join(lines) + "\n")
        environment = dict(os.environ)
        if not environment.get("SOURCE_DATE_EPOCH", "").isdigit():
            raise ValueError("Set SOURCE_DATE_EPOCH to the reviewed source timestamp.")
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group", "--uniform-compression", "-Zgzip", "-z9", str(root), str(output)], check=True, env=environment)
    # Ship user installation/repair/removal alongside the same artifact; a
    # recipient never needs a checkout to obtain the supported lifecycle.
    for name in ("install_codev_core_user.sh", "uninstall_codev_core_user.sh"):
        target = output.parent / name
        if target.exists() and target.read_bytes() != (source / "scripts" / name).read_bytes():
            raise ValueError("Refusing to overwrite a different distributable installer.")
        shutil.copyfile(source / "scripts" / name, target)
        target.chmod(0o755)
    # The distributable itself must pass the installed lifecycle. Source-only
    # unit success cannot qualify a missing/broken packaged service again.
    subprocess.run([sys.executable, str(source / "scripts/verify_codev_core_package.py"),
                    str(output)], check=True)
    return {"artifact": output.name, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), **manifest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.core, args.adapter, args.output), sort_keys=True))
