"""Shell lifecycle regressions; compiled product qualification runs separately.

The inert CLI fixture isolates package promotion, repair and uninstall behavior.
It deliberately does not qualify the real manifest resolver or runtime service.
"""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts/install_codev_core_user.sh"
UNINSTALL = ROOT / "scripts/uninstall_codev_core_user.sh"


def package(tmp_path):
    if not shutil.which("dpkg-deb"):
        pytest.skip("Debian package tooling is unavailable")
    root = tmp_path / "fixture"
    (root / "DEBIAN").mkdir(parents=True)
    (root / "DEBIAN/control").write_text(
        "Package: codev-core\nVersion: 1.1.0\nArchitecture: amd64\n"
        "Maintainer: Qualification\nDescription: inert installer fixture\n"
    )
    payload = root / "usr/lib/codev"
    payload.mkdir(parents=True)
    binary = payload / "codev-core"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    manifest = payload / "runtime.json"
    manifest.write_text('{"fixture":"shell lifecycle only"}\n')
    manifest.chmod(0o644)
    artifact = tmp_path / "fixture.deb"
    subprocess.run(["dpkg-deb", "--build", str(root), str(artifact)], check=True, capture_output=True)
    return artifact


def environment(tmp_path):
    home = tmp_path / "ordinary home with spaces"
    home.mkdir()
    return {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
            "XDG_CONFIG_HOME": str(home / "config"), "XDG_STATE_HOME": str(home / "state")}


def invoke(script, env, *args):
    return subprocess.run(["bash", str(script), *args], env=env, text=True, capture_output=True)


def test_repair_restores_permissions_and_preserves_damaged_payload_and_user_data(tmp_path):
    artifact = package(tmp_path)
    env = environment(tmp_path)
    args = ("--apply", "--deb", str(artifact))
    first = invoke(INSTALL, env, *args)
    assert first.returncode == 0, first.stderr
    current = Path(env["XDG_DATA_HOME"]) / "codev/current"
    payload = current.resolve() / "usr/lib/codev"
    (payload / "runtime.json").chmod(0o666)
    (payload / "codev-core").chmod(0o644)
    private = Path(env["XDG_DATA_HOME"]) / "elysia/private-proof"
    private.parent.mkdir()
    private.write_text("preserve")
    repaired = invoke(INSTALL, env, *args)
    assert repaired.returncode == 0, repaired.stderr
    assert (payload / "runtime.json").stat().st_mode & 0o777 == 0o644
    assert (payload / "codev-core").stat().st_mode & 0o777 == 0o755
    recovered = list((current.parent / "recoverable").iterdir())
    assert len(recovered) == 1
    assert (recovered[0] / "usr/lib/codev/runtime.json").stat().st_mode & 0o777 == 0o666
    # Healthy repair does not create another recoverable copy.
    assert invoke(INSTALL, env, *args).returncode == 0
    assert list((current.parent / "recoverable").iterdir()) == recovered
    assert invoke(UNINSTALL, env, "--apply").returncode == 0
    assert not current.exists() and private.read_text() == "preserve"
    assert invoke(INSTALL, env, *args).returncode == 0
    assert current.is_dir() and private.read_text() == "preserve"


@pytest.mark.parametrize("variable", ["HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"])
def test_uninstall_rejects_relative_paths_before_touching_installation(tmp_path, variable):
    env = environment(tmp_path)
    env[variable] = "relative-path"
    result = invoke(UNINSTALL, env, "--apply")
    assert result.returncode == 2
    assert "Absolute HOME/XDG paths are required" in result.stderr
