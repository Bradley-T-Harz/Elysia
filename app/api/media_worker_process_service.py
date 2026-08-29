"""Bounded subprocess boundary for local media workers."""

from __future__ import annotations

import json
import os
import selectors
import signal
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

import yaml

from app.api.project_paths import config_path, elysia_path
from app.api.media_worker_registry_service import resolved_media_runtime_paths
from app.api.user_control_service import current_user_controls
from app.cognition.compute_governor import (
    ComputeDecision,
    ComputeLedger,
    WorkloadDescriptor,
    decide_compute,
    is_accelerator_oom_error,
)
from app.cognition.emergency_control import emergency_active
from app.ids import new_id
from app.ownership import current_user_id


MAX_RESULT_BYTES = 256 * 1024
_WORKER_LOCKS: dict[str, threading.Lock] = {}
_WORKER_LOCKS_GUARD = threading.Lock()


def _worker_lock(worker_key: str) -> threading.Lock:
    with _WORKER_LOCKS_GUARD:
        return _WORKER_LOCKS.setdefault(worker_key, threading.Lock())


def _load_config(worker_key: str) -> dict[str, Any]:
    name = worker_key.removesuffix("_worker")
    path = config_path("workers", f"{name}_worker.yaml")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _bounded_process(
    argv: list[str],
    *,
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
    env: dict[str, str],
    cancel_event: threading.Event | None = None,
    preempt_check: Any | None = None,
) -> tuple[int, bytes, bytes, str | None]:
    process = subprocess.Popen(  # noqa: S603 - fixed executable/script and request/result paths only.
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        close_fds=True,
        env=env,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": stderr_limit}
    deadline = time.monotonic() + timeout_seconds
    failure: str | None = None
    try:
        while selector.get_map():
            if cancel_event is not None and cancel_event.is_set():
                failure = "worker_cancelled"
                break
            if preempt_check is not None and preempt_check():
                failure = "worker_preempted"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "worker_timeout"
                break
            for key, _ in selector.select(timeout=min(remaining, 0.2)):
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                stream = str(key.data)
                buffers[stream].extend(chunk)
                if len(buffers[stream]) > limits[stream]:
                    del buffers[stream][limits[stream]:]
                    failure = f"worker_{stream}_limit"
                    break
            if failure:
                break
    finally:
        selector.close()
        if failure and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
    return process.returncode or 0, bytes(buffers["stdout"]), bytes(buffers["stderr"]), failure


def _offline_environment(
    temporary_root: Path, *, selected_device: str = "automatic"
) -> dict[str, str]:
    # Workers get a deliberately minimal environment. In particular, do not
    # inherit cloud credentials, tokens, proxy settings, or identity-bearing
    # host configuration into an ML subprocess.
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(temporary_root),
        "TMPDIR": str(temporary_root),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    for name in ("CUDA_VISIBLE_DEVICES", "LD_LIBRARY_PATH"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    if selected_device == "cpu":
        environment["CUDA_VISIBLE_DEVICES"] = "-1"
    environment.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
    )
    return environment


def _worker_estimate(worker_key: str, job: dict[str, Any]) -> dict[str, Any]:
    model_id = str(job.get("model_id") or "")
    if worker_key == "videoforge_worker":
        return {
            "task_kind": "local_video_generation",
            "priority": "normal",
            "interactive": False,
            "cpu": 55,
            "ram": 16384,
            "gpu": 95,
            "vram": 11264,
            "duration": 240_000,
            "preemptible": True,
            "cpu_fallback": False,
        }
    if worker_key == "imageforge_worker":
        measured_vram = 6144 if model_id == "commoncanvas-xl-c" else 1024
        return {
            "task_kind": "local_image_generation",
            "priority": "normal",
            "interactive": False,
            "cpu": 45,
            "ram": 12288,
            "gpu": 90,
            "vram": measured_vram,
            "duration": 180_000,
            "preemptible": True,
            "cpu_fallback": False,
        }
    return {
        "task_kind": "local_speech_generation",
        "priority": "interactive",
        "interactive": True,
        "cpu": 40,
        "ram": 4096,
        "gpu": 0,
        "vram": 0,
        "duration": 60_000,
        "preemptible": False,
        "cpu_fallback": True,
    }


def _governed_worker_decision(worker_key: str, job: dict[str, Any]) -> ComputeDecision:
    controls = current_user_controls()
    estimate = _worker_estimate(worker_key, job)
    return decide_compute(
        WorkloadDescriptor(
            workload_id=new_id("mediaworkload"),
            owner_user_id=current_user_id(),
            task_kind=str(estimate["task_kind"]),
            priority=str(estimate["priority"]),
            interactive=bool(estimate["interactive"]),
            privacy="normal",
            estimated_cpu_percent=int(estimate["cpu"]),
            estimated_gpu_percent=int(estimate["gpu"]),
            estimated_ram_mb=int(estimate["ram"]),
            estimated_vram_mb=int(estimate["vram"]),
            incremental_vram_mb=int(estimate["vram"]),
            estimated_duration_ms=int(estimate["duration"]),
            batchable=False,
            cancellable=True,
            preemptible=bool(estimate["preemptible"]),
            cpu_fallback_allowed=bool(estimate["cpu_fallback"]),
            required_model=str(job.get("model_id") or "") or None,
            required_resources=(worker_key,),
            hard_vram_limit_mb=controls.vram_mb_ceiling,
            estimate_source="measured_worker_smoke_profile",
        ),
        preference=controls.compute_preference,
        cpu_percent_ceiling=controls.cpu_percent_ceiling,
        ram_mb_ceiling=controls.ram_mb_ceiling,
        vram_mb_ceiling=controls.vram_mb_ceiling,
        max_background_jobs=controls.max_background_jobs,
        stop_active=emergency_active(),
    )


@contextmanager
def execute_media_worker(
    worker_key: str,
    job: dict[str, Any],
    *,
    cancel_event: threading.Event | None = None,
) -> Iterator[dict[str, Any]]:
    """Execute one fixed local worker and remove only its exact temporary directory."""
    worker_lock = _worker_lock(worker_key)
    if not worker_lock.acquire(blocking=False):
        yield {"status": "unavailable", "blocked_reason": "worker_busy"}
        return
    try:
        config = _load_config(worker_key)
        runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else config
        private_paths = resolved_media_runtime_paths(worker_key, str(job.get("model_id") or "") or None)
        python_path = private_paths.get("python_path") or Path(str(runtime.get("python_path") or ""))
        worker_script = elysia_path(str(runtime.get("worker_script") or config.get("worker_script") or ""))
        if not python_path.is_file() or not worker_script.is_file():
            yield {"status": "unavailable", "blocked_reason": "worker_runtime_missing"}
            return
        try:
            compute = _governed_worker_decision(worker_key, job)
        except Exception:
            yield {
                "status": "unavailable",
                "blocked_reason": "compute_governance_unavailable",
            }
            return
        if compute.decision in {"rejected", "deferred"}:
            yield {
                "status": "unavailable",
                "blocked_reason": "compute_governor_declined_worker",
                "compute_decision": compute.decision,
                "compute_reasons": list(compute.reasons),
            }
            return
        ledger = ComputeLedger()
        temporary_root: Path | None = None
        failure: str | None = None
        result: dict[str, Any] = {}
        try:
            temporary_root = Path(tempfile.mkdtemp(prefix=f"elysia-{worker_key}-"))
            request_path = temporary_root / "request.json"
            result_path = temporary_root / "result.json"
            job_payload = dict(job)
            job_payload.update({key: str(value) for key, value in private_paths.items() if key != "python_path"})
            job_payload["job_root"] = str(temporary_root)
            job_payload["output_path"] = str(temporary_root / str(job.get("output_name") or "worker-output.bin"))
            request_path.write_text(json.dumps(job_payload, sort_keys=True), encoding="utf-8")
            timeout = float(runtime.get("process_timeout_seconds") or 180)
            stdout_limit = int(runtime.get("max_stdout_bytes") or 65_536)
            stderr_limit = int(runtime.get("max_stderr_bytes") or 131_072)
            code, stdout, stderr, failure = _bounded_process(
                [str(python_path), str(worker_script), "--request", str(request_path), "--result", str(result_path)],
                timeout_seconds=timeout,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
                env=_offline_environment(
                    temporary_root,
                    selected_device=compute.selected_device,
                ),
                cancel_event=cancel_event,
                preempt_check=(
                    (lambda: ledger.preemption_requested(str(compute.lease_id)))
                    if compute.lease_id else None
                ),
            )
            if failure == "worker_cancelled":
                yield {
                    "status": "cancelled",
                    "blocked_reason": "operator_cancelled",
                    "exit_code": code,
                    "stdout_bytes": len(stdout),
                    "stderr_bytes": len(stderr),
                }
                return
            if failure == "worker_preempted":
                yield {
                    "status": "cancelled",
                    "blocked_reason": "resource_preempted_for_higher_priority_work",
                    "exit_code": code,
                    "stdout_bytes": len(stdout),
                    "stderr_bytes": len(stderr),
                }
                return
            if failure or not result_path.is_file():
                yield {
                    "status": "failed",
                    "blocked_reason": failure or "worker_process_failed",
                    "exit_code": code,
                    "stdout_bytes": len(stdout),
                    "stderr_bytes": len(stderr),
                    "diagnostic_hash": sha256(stderr).hexdigest() if stderr else None,
                }
                return
            if result_path.stat().st_size > MAX_RESULT_BYTES:
                yield {"status": "failed", "blocked_reason": "worker_result_too_large"}
                return
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                yield {"status": "failed", "blocked_reason": "worker_result_invalid"}
                return
            if not isinstance(result, dict):
                yield {"status": "failed", "blocked_reason": "worker_result_invalid"}
                return
            # A governed worker may use a non-zero exit status for an expected,
            # structured refusal. Preserve that compact reason instead of replacing
            # it with an opaque process failure. Unstructured failures remain
            # unavailable above because they do not produce a result receipt.
            if code != 0:
                result.setdefault("exit_code", code)
                result.setdefault("status", "failed")
                result.setdefault("blocked_reason", "worker_process_failed")
            result["compute_device"] = compute.selected_device
            result["compute_lease_governed"] = bool(compute.lease_id) or compute.selected_device == "cpu"
            yield result
        finally:
            observed_vram = None
            try:
                observed_vram = int(float(result.get("peak_gpu_memory_mib") or 0)) or None
            except (TypeError, ValueError):
                observed_vram = None
            oom_candidate = result.get("blocked_reason") or failure
            if is_accelerator_oom_error(oom_candidate):
                try:
                    ledger.record_oom(
                        workload_id=compute.workload_id,
                        task_kind=str((compute.workload or {}).get("task_kind") or worker_key),
                        selected_device=compute.selected_device,
                        observed_vram_mb=observed_vram,
                        hard_vram_limit_mb=int((compute.workload or {}).get("hard_vram_limit_mb") or 0) or None,
                        recovery_action="lease_released_request_failed",
                    )
                except Exception:
                    pass
            if compute.lease_id:
                ledger.release(
                    compute.lease_id,
                    reason="media_worker_finished",
                    actual_vram_mb=observed_vram,
                )
            if compute.reservation_id:
                ledger.release_job(
                    compute.reservation_id,
                    reason="media_worker_finished",
                )
            if temporary_root is not None:
                shutil.rmtree(temporary_root, ignore_errors=True)
    finally:
        worker_lock.release()


__all__ = ("execute_media_worker",)
