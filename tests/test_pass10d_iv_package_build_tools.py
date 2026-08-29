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
