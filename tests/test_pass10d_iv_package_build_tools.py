from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
import yaml

from scripts import package_build_tools as tools


def _policy(tmp_path: Path, *, runtime: bytes = b"runtime") -> tuple[Path, dict]:
    cache_bytes = b"cache"
    appimagetool_bytes = b"appimagetool"
    payload = {
        "version": 1,
        "contract_version": "elysia-package-build-tools-1.0",
        "rules": {
            "unverified_cached_tool_allowed": False,
            "mutable_remote_without_expected_hash_allowed": False,
            "private_source_egress": False,
        },
        "tauri_cache_files": {
            "tool": {"sha256": sha256(cache_bytes).hexdigest()},
        },
        "appimagetool": {
            "extracted_relative_path": "bin/appimagetool",
            "sha256": sha256(appimagetool_bytes).hexdigest(),
            "version": "exact-test",
        },
        "type2_runtime": {
            "source": "https://example.invalid/exact-runtime",
            "source_channel_mutable": True,
            "size_bytes": len(runtime),
            "sha256": sha256(runtime).hexdigest(),
        },
    }
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path, payload


def test_package_build_inputs_fail_closed_on_any_hash_change(tmp_path: Path, monkeypatch) -> None:
    policy_path, _ = _policy(tmp_path)
    monkeypatch.setattr(tools, "POLICY_PATH", policy_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "tool").write_bytes(b"cache")
    assert tools.verify_tauri_cache(cache)["all_hashes_match"] is True
    (cache / "tool").write_bytes(b"changed")
    with pytest.raises(tools.PackageBuildToolError, match="SHA-256"):
        tools.verify_tauri_cache(cache)


def test_appimagetool_and_existing_runtime_require_exact_identity(tmp_path: Path, monkeypatch) -> None:
    policy_path, _ = _policy(tmp_path)
    monkeypatch.setattr(tools, "POLICY_PATH", policy_path)
    plugin = tmp_path / "plugin"
    (plugin / "bin").mkdir(parents=True)
    (plugin / "bin" / "appimagetool").write_bytes(b"appimagetool")
    assert tools.verify_appimagetool(plugin)["sha256_verified"] is True
    runtime = tmp_path / "runtime"
    runtime.write_bytes(b"runtime")
    assert tools.prepare_runtime(runtime)["exact_hash_mismatch_fails_closed"] is True
    runtime.write_bytes(b"tampered")
    with pytest.raises(tools.PackageBuildToolError):
        tools.prepare_runtime(runtime)


def test_runtime_acquisition_is_atomic_and_hash_verified(tmp_path: Path, monkeypatch) -> None:
    policy_path, _ = _policy(tmp_path)
    monkeypatch.setattr(tools, "POLICY_PATH", policy_path)
    monkeypatch.setattr(tools, "urlopen", lambda *_args, **_kwargs: BytesIO(b"runtime"))
    output = tmp_path / "nested" / "runtime"
    result = tools.prepare_runtime(output)
    assert output.read_bytes() == b"runtime"
    assert output.stat().st_mode & 0o077 == 0
    assert result["source_channel_mutable"] is True
    assert result["exact_hash_mismatch_fails_closed"] is True


@pytest.mark.parametrize("active_cache", ["absent", "mismatched", "matching"])
def test_linux_wrapper_verifies_actual_xdg_cache_before_build(tmp_path, active_cache):
    """A valid HOME cache must not authorize Tauri's different XDG cache."""
    import os
    import shutil
    import subprocess
    import sys

    source = Path(__file__).resolve().parents[1]
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(source / "scripts/tauri_build_linux.sh", scripts)
    shutil.copy2(source / "scripts/package_build_tools.py", scripts)
    policy, _ = _policy(tmp_path)
    policy_target = root / "config/install/package_build_tools.yaml"
    policy_target.parent.mkdir(parents=True)
    shutil.copy2(policy, policy_target)
    core_marker = root / "core-started"
    core = scripts / "build_packaged_core_runtime.sh"
    core.write_text('#!/bin/sh\ntouch "$(dirname "$0")/../core-started"\n')
    core.chmod(0o700)
    shim = scripts / "packaging_bin/appstreamcli"
    shim.parent.mkdir()
    shim.write_text("#!/bin/sh\nexit 0\n")
    shim.chmod(0o700)
    home = tmp_path / "home"
    home_cache = home / ".cache/tauri"
    home_cache.mkdir(parents=True)
    (home_cache / "tool").write_bytes(b"cache")
    (home_cache / "runtime-x86_64").write_bytes(b"runtime")
    cache = tmp_path / "isolated-cache/tauri"
    if active_cache != "absent":
        cache.mkdir(parents=True)
        (cache / "tool").write_bytes(b"cache" if active_cache == "matching" else b"changed")
        (cache / "runtime-x86_64").write_bytes(b"runtime")
    commands = tmp_path / "bin"
    commands.mkdir()
    (commands / "python3").symlink_to(sys.executable)
    npm = commands / "npm"
    npm.write_text("#!/bin/sh\nexit 31\n")  # Stop at the real bundler boundary.
    npm.chmod(0o700)
    env = {**os.environ, "HOME": str(home), "XDG_CACHE_HOME": str(cache.parent),
           "PATH": str(commands) + os.pathsep + os.environ["PATH"], "ELYSIA_TAURI_BUNDLES": "appimage"}
    env.pop("RUSTFLAGS", None)
    env.pop("CARGO_ENCODED_RUSTFLAGS", None)
    result = subprocess.run(["bash", str(scripts / "tauri_build_linux.sh")], env=env,
                            capture_output=True, text=True, timeout=15)
    if active_cache == "matching":
        assert result.returncode == 31, result.stderr
        assert core_marker.exists()
    else:
        assert result.returncode != 0
        assert not core_marker.exists(), "Wrong cache was trusted before starting the build"
