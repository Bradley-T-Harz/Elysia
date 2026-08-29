from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.assert_disposable_xdg import assert_disposable_xdg


def _environment(root: Path) -> dict[str, str]:
    run_id = f"pass10d-i-{root.name}-fixture"
    return {
        "ELYSIA_QA_ROOT": str(root),
        "ELYSIA_QA_RUN_ID": run_id,
        "ELYSIA_QA_CANARY": f"synthetic-gate-zero-{run_id}",
        "ELYSIA_RUNTIME_MODE": "test",
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_STATE_HOME": str(root / "state"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    }


def test_disposable_xdg_guard_accepts_only_run_owned_authorities(tmp_path: Path) -> None:
    root = Path("/tmp") / f"elysia-pass10d-i-{tmp_path.name}"
    root.mkdir(mode=0o700)
    try:
        result = assert_disposable_xdg(_environment(root))
    finally:
        root.rmdir()

    assert result == {
        "disposable_xdg": True,
        "run_id": f"pass10d-i-{root.name}-fixture",
        "authority_count": 5,
        "all_authorities_below_run_root": True,
        "operator_defaults_overlap": False,
        "canary_bound_to_run": True,
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("XDG_DATA_HOME", str(Path.home() / ".local" / "share")),
        ("XDG_CONFIG_HOME", str(Path.home() / ".config")),
        ("XDG_STATE_HOME", str(Path.home() / ".local" / "state")),
        ("XDG_CACHE_HOME", str(Path.home() / ".cache")),
        ("XDG_RUNTIME_DIR", "/tmp"),
    ],
)
def test_disposable_xdg_guard_rejects_escape_to_real_or_shared_state(
    tmp_path: Path,
    key: str,
    value: str,
) -> None:
    root = Path("/tmp") / f"elysia-pass10d-i-{tmp_path.name}"
    root.mkdir(mode=0o700)
    try:
        environment = _environment(root)
        environment[key] = value
        with pytest.raises(RuntimeError, match="escaped the disposable QA root"):
            assert_disposable_xdg(environment)
    finally:
        root.rmdir()


def test_backend_preflight_creates_and_destroys_its_universe() -> None:
    repo = Path(__file__).resolve().parents[1]
    before = set(Path("/tmp").glob("elysia-pass10d-i-*"))
    environment = os.environ.copy()
    environment["ELYSIA_TEST_PYTHON"] = sys.executable
    result = subprocess.run(
        ["bash", "scripts/test_backend.sh", "--preflight-only"],
        cwd=repo,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    after = set(Path("/tmp").glob("elysia-pass10d-i-*"))

    assert result.returncode == 0, result.stderr
    assert '"disposable_xdg": true' in result.stdout
    assert "cleanup is armed" in result.stdout
    assert after == before


def test_guard_cli_fails_closed_without_gate_zero_environment() -> None:
    repo = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    for key in (
        "ELYSIA_QA_ROOT",
        "ELYSIA_QA_RUN_ID",
        "ELYSIA_QA_CANARY",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
        "XDG_RUNTIME_DIR",
    ):
        environment.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.assert_disposable_xdg"],
        cwd=repo,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode != 0
    assert "ELYSIA_QA_RUN_ID is missing" in result.stderr
