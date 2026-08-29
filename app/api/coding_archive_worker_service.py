"""Core-side client for ArchiveForge's fixed-operation subprocess boundary."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from threading import BoundedSemaphore
from typing import Any

from app.api.project_paths import config_path, elysia_repo_root
from app.api.worker_runtime_path_service import resolve_worker_python


SAFE_WORKER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_WORKER_SLOT = BoundedSemaphore(value=1)


def _worker_config() -> dict[str, Any]:
    try:
        import yaml

        loaded = yaml.safe_load(config_path("workers", "archiveforge_worker.yaml").read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _list_with_archiveforge_worker(
    source: Path,
    *,
    archive_type: str,
    timeout_seconds: int,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
) -> dict[str, Any]:
    config = _worker_config()
    python_path = resolve_worker_python(
        config,
        override_env="ELYSIA_ARCHIVEFORGE_PYTHON",
        allow_current_interpreter=True,
    )
    if python_path is None:
        return {"status": "blocked", "reason": "archive_worker_python_unavailable", "members": [], "tool": "archiveforge_worker"}
    repo_root = elysia_repo_root().resolve(strict=False)
    script = (repo_root / str(config.get("worker_script") or "sandbox/archiveforge_worker/worker_cli.py")).resolve(strict=False)
    try:
        script.relative_to(repo_root)
    except ValueError:
        return {"status": "blocked", "reason": "archive_worker_script_outside_repo", "members": [], "tool": "archiveforge_worker"}
    if not script.is_file() or script.is_symlink():
        return {"status": "blocked", "reason": "archive_worker_script_unavailable", "members": [], "tool": "archiveforge_worker"}
    command = [
        str(python_path),
        str(script),
        "--operation",
        "list",
        "--archive-type",
        archive_type,
        "--source",
        str(source.resolve(strict=True)),
        "--timeout-seconds",
        str(max(1, min(timeout_seconds, 60))),
        "--max-stdout-bytes",
        str(max_stdout_bytes),
        "--max-stderr-bytes",
        str(max_stderr_bytes),
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            cwd=repo_root,
            timeout=max(2, min(timeout_seconds + 2, 62)),
            check=False,
            env={"PATH": SAFE_WORKER_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
    except subprocess.TimeoutExpired:
        return {"status": "blocked", "reason": "archive_worker_timeout", "members": [], "tool": "archiveforge_worker"}
    except OSError:
        return {"status": "blocked", "reason": "archive_worker_launch_failed", "members": [], "tool": "archiveforge_worker"}
    if len(completed.stdout) > max_stdout_bytes or len(completed.stderr) > max_stderr_bytes:
        return {"status": "blocked", "reason": "archive_worker_output_limit_exceeded", "members": [], "tool": "archiveforge_worker"}
    try:
        payload = json.loads(completed.stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        payload = {}
    if completed.returncode != 0 or not isinstance(payload, dict):
        return {
            "status": "blocked",
            "reason": str(payload.get("reason") if isinstance(payload, dict) else "") or f"archive_worker_exit_{completed.returncode}",
            "members": [],
            "tool": "archiveforge_worker",
        }
    return payload


def list_with_archiveforge_worker(
    source: Path,
    *,
    archive_type: str,
    timeout_seconds: int,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
) -> dict[str, Any]:
    if not _WORKER_SLOT.acquire(blocking=False):
        return {"status": "blocked", "reason": "archive_worker_busy", "members": [], "tool": "archiveforge_worker"}
    try:
        return _list_with_archiveforge_worker(
            source,
            archive_type=archive_type,
            timeout_seconds=timeout_seconds,
            max_stdout_bytes=max_stdout_bytes,
            max_stderr_bytes=max_stderr_bytes,
        )
    finally:
        _WORKER_SLOT.release()


__all__ = ("list_with_archiveforge_worker",)
