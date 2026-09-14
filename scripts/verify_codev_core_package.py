#!/usr/bin/env python3
"""Qualify the distributable Core/user installer with isolated installed state.

This executes the compiled payload, never an imported development backend. GUI,
system-package, login/reboot and editor checks remain additional release gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile

from verify_packaged_native_runtime import pidfd_open, pidfd_signal, request


def qualify(artifact: Path, installer: Path, uninstaller: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="codev-artifact-lifecycle-") as temporary:
        root = Path(temporary)
        home = root / "ordinary user with spaces"
        home.mkdir(mode=0o700)
        env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
               "PYINSTALLER_RESET_ENVIRONMENT": "1"}
        for axis in ("DATA", "CONFIG", "STATE", "CACHE"):
            env[f"XDG_{axis}_HOME"] = str(home / axis.lower())
        env["XDG_RUNTIME_DIR"] = str(home / "runtime")
        directory = home / "runtime/elysia"
        current = home / "data/codev/current"
        launcher = home / ".local/bin/codev"
        pidfd = None

        def run(*args):
            result = subprocess.run(list(map(str, args)), cwd="/", env=env,
                                    capture_output=True, text=True, timeout=100)
            if result.returncode:
                raise RuntimeError(f"Artifact lifecycle command failed: {result.stderr[-2000:]}")
            return result.stdout

        def status():
            code, payload, _ = request(directory, "GET", "/codev/installation")
            assert code == 200
            return payload["data"]["codev_installation"]

        try:
            run("bash", installer, "--deb", artifact)
            assert not current.exists(), "Dry run changed installation"
            run("bash", installer, "--apply", "--deb", artifact)
            code, identity, peer = request(directory, "GET", "/runtime/identity")
            assert code == 200 and identity["pid"] == peer
            pidfd = pidfd_open(peer)
            payload = current / "usr/lib/codev"
            manifest = json.loads((payload / "runtime.json").read_text())
            assert identity["executable_sha256"] == manifest["core_sha256"]
            first = status()
            assert first["installed"] and first["runtime_state"] == "ready"
            assert first["session_state"] == "approval_needed" and not first["usable"]
            assert not any(c["available"] for c in first["capabilities"])
            assert request(directory, "POST", "/codev/session", b"{}")[0] == 401
            assert not (home / ".vscode").exists()
            # Equal bytes with unsafe modes are a real installed failure.
            (payload / "runtime.json").chmod(0o666)
            assert status()["state"] == "degraded"
            run("bash", installer, "--apply", "--deb", artifact)
            assert (payload / "runtime.json").stat().st_mode & 0o777 == 0o644
            repaired = status()
            assert repaired["installed"] and repaired["installation_id"] != first["installation_id"]
            private = home / "data/elysia/qualification-preserve"
            private.write_text("preserved local state")
            run("bash", uninstaller, "--apply")
            assert status()["state"] == "absent" and not launcher.exists()
            assert private.read_text() == "preserved local state"
            run("bash", installer, "--apply", "--deb", artifact)
            installed = status()
            assert installed["installed"] and installed["installation_id"] != repaired["installation_id"]
            assert not installed["usable"] and private.read_text() == "preserved local state"
            return {"passed": True, "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    "core_sha256": identity["executable_sha256"], "version": "1.0.0",
                    "source_environment": False, "editor_required": False,
                    "checks": ["dry_run", "install", "private_runtime", "no_account_authority",
                               "no_implicit_workspace", "unsafe_mode_degraded", "permission_repair",
                               "uninstall", "reinstall", "installation_generation", "data_preserved"]}
        finally:
            if pidfd is None and directory.exists():
                try:
                    code, identity, peer = request(directory, "GET", "/runtime/identity")
                    if code == 200 and identity.get("pid") == peer:
                        pidfd = pidfd_open(peer)
                except (OSError, ValueError):
                    pass
            if pidfd is not None:
                try:
                    pidfd_signal(pidfd, signal.SIGTERM)
                    if not select.select([pidfd], [], [], 5)[0]:
                        pidfd_signal(pidfd, signal.SIGKILL)
                        assert select.select([pidfd], [], [], 5)[0]
                except ProcessLookupError:
                    pass
                finally:
                    os.close(pidfd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--uninstaller", type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve(strict=True)
    print(json.dumps(qualify(artifact,
        (args.installer or artifact.parent / "install_codev_core_user.sh").resolve(strict=True),
        (args.uninstaller or artifact.parent / "uninstall_codev_core_user.sh").resolve(strict=True)), sort_keys=True))
