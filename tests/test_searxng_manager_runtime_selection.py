from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "manage_searxng.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _fake_environment(
    tmp_path: Path,
    *,
    podman_container: bool,
    docker_container: bool,
) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    podman_exists = "exit 0" if podman_container else "exit 1"
    docker_exists = "exit 0" if docker_container else "exit 1"

    _write_executable(
        bin_dir / "podman",
        f"""#!/usr/bin/env bash
set -eu
if [[ "${{1:-}}" == "container" && "${{2:-}}" == "exists" ]]; then
  {podman_exists}
fi
if [[ "${{1:-}}" == "inspect" ]]; then
  echo "status=created image=fake-podman port=127.0.0.1:8888"
  exit 0
fi
exit 0
""",
    )

    _write_executable(
        bin_dir / "docker",
        f"""#!/usr/bin/env bash
set -eu
if [[ "${{1:-}}" == "info" ]]; then
  exit 0
fi
if [[ "${{1:-}}" == "container" && "${{2:-}}" == "inspect" ]]; then
  {docker_exists}
fi
if [[ "${{1:-}}" == "inspect" ]]; then
  echo "status=running image=fake-docker port=127.0.0.1:8888"
  exit 0
fi
exit 0
""",
    )

    # Force the loopback readiness probe to report unavailable so status
    # exercises runtime/container selection instead of a real host service.
    _write_executable(
        bin_dir / "python3",
        """#!/usr/bin/env bash
exit 1
""",
    )

    home = tmp_path / "home"
    home.mkdir()

    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }


def test_manager_prefers_runtime_that_actually_contains_named_container(
    tmp_path: Path,
) -> None:
    environment = _fake_environment(
        tmp_path,
        podman_container=False,
        docker_container=True,
    )

    result = subprocess.run(
        ["bash", str(SCRIPT), "status"],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "status=running" in result.stdout
    assert "fake-docker" in result.stdout
    assert "fake-podman" not in result.stdout


def test_manager_fails_closed_when_same_container_name_exists_in_both_runtimes(
    tmp_path: Path,
) -> None:
    environment = _fake_environment(
        tmp_path,
        podman_container=True,
        docker_container=True,
    )

    result = subprocess.run(
        ["bash", str(SCRIPT), "status"],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "runtime ambiguity" in result.stderr.lower()
    assert "both Podman and Docker" in result.stderr
    assert "Refusing to choose one implicitly" in result.stderr


def test_mutating_action_also_fails_before_ambiguous_runtime_is_touched(
    tmp_path: Path,
) -> None:
    environment = _fake_environment(
        tmp_path,
        podman_container=True,
        docker_container=True,
    )

    result = subprocess.run(
        ["bash", str(SCRIPT), "stop"],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "runtime ambiguity" in result.stderr.lower()
