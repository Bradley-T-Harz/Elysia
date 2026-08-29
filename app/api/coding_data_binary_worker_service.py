"""Core-side clients for fixed DatabaseForge and BinaryForge subprocesses."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
from threading import BoundedSemaphore
from typing import Any, Literal

from app.api.project_paths import config_path, elysia_repo_root
from app.api.worker_runtime_path_service import resolve_worker_python


WorkerFamily = Literal["database", "binary"]
SAFE_WORKER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_SLOTS = {"database": BoundedSemaphore(value=1), "binary": BoundedSemaphore(value=1)}


def _config(family: WorkerFamily) -> dict[str, Any]:
    try:
        import yaml

        loaded = yaml.safe_load(config_path("workers", f"{family}forge_worker.yaml").read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _run_worker(
    family: WorkerFamily,
    *,
    operation: str,
    source: Path,
    limits: dict[str, int],
    snapshot: Path | None = None,
    engine: str | None = None,
) -> dict[str, Any]:
    config = _config(family)
    python_path = resolve_worker_python(
        config,
        override_env=f"ELYSIA_{family.upper()}FORGE_PYTHON",
        allow_current_interpreter=True,
    )
    if python_path is None:
        return {"status": "blocked", "reason": f"{family}_worker_python_unavailable"}
    repo_root = elysia_repo_root().resolve(strict=False)
    default_script = f"sandbox/{family}forge_worker/worker_cli.py"
    script = (repo_root / str(config.get("worker_script") or default_script)).resolve(strict=False)
    try:
        script.relative_to(repo_root)
    except ValueError:
        return {"status": "blocked", "reason": f"{family}_worker_script_outside_repo"}
    if not script.is_file() or script.is_symlink():
        return {"status": "blocked", "reason": f"{family}_worker_script_unavailable"}
    command = [str(python_path), str(script), "--operation", operation, "--source", str(source.resolve(strict=True)), "--limits-json", json.dumps(limits, sort_keys=True, separators=(",", ":"))]
    if snapshot is not None:
        command.extend(["--snapshot", str(snapshot.resolve(strict=False))])
    if engine is not None:
        command.extend(["--engine", engine])
    timeout = max(2, min(int(limits.get("timeout_seconds", 30)), 60))
    stdout_limit = max(1024, int(limits.get("max_worker_stdout_bytes", 4 * 1024 * 1024)))
    stderr_limit = max(1024, int(limits.get("max_worker_stderr_bytes", 64 * 1024)))
    try:
        with tempfile.TemporaryDirectory(prefix=f"elysia-{family}forge-worker-") as temporary:
            Path(temporary).chmod(0o700)
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                cwd=repo_root,
                timeout=timeout + 2,
                check=False,
                close_fds=True,
                env={"PATH": SAFE_WORKER_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "HOME": temporary, "TMPDIR": temporary},
            )
    except subprocess.TimeoutExpired:
        return {"status": "blocked", "reason": f"{family}_worker_timeout"}
    except OSError:
        return {"status": "blocked", "reason": f"{family}_worker_launch_failed"}
    if len(completed.stdout) > stdout_limit or len(completed.stderr) > stderr_limit:
        return {"status": "blocked", "reason": f"{family}_worker_output_limit_exceeded"}
    try:
        payload = json.loads(completed.stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        payload = {}
    if completed.returncode != 0 or not isinstance(payload, dict):
        return {"status": "blocked", "reason": str(payload.get("reason") if isinstance(payload, dict) else "") or f"{family}_worker_exit_{completed.returncode}"}
    return payload


def run_data_binary_worker(
    family: WorkerFamily,
    *,
    operation: str,
    source: Path,
    limits: dict[str, int],
    snapshot: Path | None = None,
    engine: str | None = None,
) -> dict[str, Any]:
    slot = _SLOTS[family]
    if not slot.acquire(blocking=False):
        return {"status": "blocked", "reason": f"{family}_worker_busy"}
    try:
        return _run_worker(family, operation=operation, source=source, limits=limits, snapshot=snapshot, engine=engine)
    finally:
        slot.release()


__all__ = ("run_data_binary_worker",)
