"""Hardened local subprocess boundary for ScientificForge.

This module owns process isolation and immutable source handoff only.
Compute admission and user-facing ScientificForge policy live elsewhere.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from app.api.scientificforge_source_service import (
    VerifiedScientificSource,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

WORKER_MODULE = (
    "sandbox.scientificforge_worker.worker_cli"
)

MAX_RESULT_BYTES = 512 * 1024
MAX_STDOUT_BYTES = 32 * 1024
MAX_STDERR_BYTES = 64 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0


class ScientificProcessError(RuntimeError):
    """ScientificForge process boundary failed safely."""


def _hash_stream(
    descriptor: int,
    output_descriptor: int,
    *,
    cancel_event: threading.Event | None = None,
) -> tuple[str, int]:
    digest = sha256()
    total = 0

    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise ScientificProcessError(
                "scientific_snapshot_cancelled"
            )

        chunk = os.read(
            descriptor,
            1024 * 1024,
        )

        if not chunk:
            break

        digest.update(chunk)
        total += len(chunk)

        view = memoryview(chunk)

        while view:
            written = os.write(
                output_descriptor,
                view,
            )

            if written <= 0:
                raise ScientificProcessError(
                    "source_snapshot_write_failed"
                )

            view = view[written:]

    return digest.hexdigest(), total


def copy_verified_source_snapshot(
    source: VerifiedScientificSource,
    job_root: Path,
    *,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Copy one verified ingest source into the private job sandbox.

    The source is opened with O_NOFOLLOW and is revalidated from the file
    descriptor. The bytes copied into the job sandbox must reproduce the
    verified ingest digest exactly.
    """

    root = Path(job_root)

    if root.is_symlink():
        raise ScientificProcessError(
            "scientific_job_root_symlink_not_allowed"
        )

    root.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    try:
        root.chmod(0o700)
    except OSError:
        pass

    suffix = source.source_path.suffix.lower()

    if suffix not in {".csv", ".xlsx"}:
        raise ScientificProcessError(
            "scientific_snapshot_type_not_allowed"
        )

    target = root / f"source{suffix}"

    if target.exists() or target.is_symlink():
        raise ScientificProcessError(
            "scientific_snapshot_target_exists"
        )

    read_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
    )

    if hasattr(os, "O_NOFOLLOW"):
        read_flags |= os.O_NOFOLLOW

    write_flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
    )

    if hasattr(os, "O_NOFOLLOW"):
        write_flags |= os.O_NOFOLLOW

    source_fd = -1
    target_fd = -1

    try:
        source_fd = os.open(
            source.source_path,
            read_flags,
        )

        before = os.fstat(
            source_fd
        )

        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
        ):
            raise ScientificProcessError(
                "scientific_source_identity_unsafe"
            )

        if int(before.st_size) != int(
            source.size_bytes
        ):
            raise ScientificProcessError(
                "scientific_source_size_changed"
            )

        target_fd = os.open(
            target,
            write_flags,
            0o600,
        )

        digest, copied = _hash_stream(
            source_fd,
            target_fd,
            cancel_event=cancel_event,
        )

        os.fsync(
            target_fd
        )

        after = os.fstat(
            source_fd
        )

        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise ScientificProcessError(
                "scientific_source_changed_during_snapshot"
            )

        if copied != int(
            source.size_bytes
        ):
            raise ScientificProcessError(
                "scientific_snapshot_size_mismatch"
            )

        if digest != source.sha256:
            raise ScientificProcessError(
                "scientific_snapshot_digest_mismatch"
            )

    except ScientificProcessError:
        target.unlink(missing_ok=True)
        raise

    except OSError as exc:
        target.unlink(missing_ok=True)
        raise ScientificProcessError(
            "scientific_snapshot_io_failed"
        ) from exc

    finally:
        if source_fd >= 0:
            os.close(
                source_fd
            )

        if target_fd >= 0:
            os.close(
                target_fd
            )

    info = target.stat()

    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or int(info.st_size) != int(source.size_bytes)
    ):
        target.unlink(
            missing_ok=True
        )

        raise ScientificProcessError(
            "scientific_snapshot_identity_failed"
        )

    return target


def _minimal_environment(
    job_root: Path,
    *,
    memory_limit_mb: int | None = None,
    cpu_seconds: int | None = None,
) -> dict[str, str]:
    """Return a deliberately narrow local worker environment."""

    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(job_root),
        "TMPDIR": str(job_root),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONPATH": str(PROJECT_ROOT),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "CUDA_VISIBLE_DEVICES": "-1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    if memory_limit_mb is not None:
        environment["ELYSIA_SCIENTIFIC_ADDRESS_SPACE_MB"] = str(memory_limit_mb)
    if cpu_seconds is not None:
        environment["ELYSIA_SCIENTIFIC_CPU_SECONDS"] = str(cpu_seconds)
    return environment


def _kill_process_group(
    process: subprocess.Popen,
) -> None:
    # Descendants can still hold pipes/resources after the group leader exits.
    try:
        os.killpg(
            process.pid,
            signal.SIGKILL,
        )
    except ProcessLookupError:
        pass

    try:
        process.wait(
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(
            timeout=2,
        )


def _bounded_process(
    argv: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    cancel_event: threading.Event | None,
    timeout_seconds: float,
) -> tuple[int, bytes, bytes, str | None]:
    """Run one fixed argv with active cancellation and bounded output."""

    process = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        close_fds=True,
        env=environment,
        start_new_session=True,
    )

    assert process.stdout is not None
    assert process.stderr is not None

    selector = selectors.DefaultSelector()

    selector.register(
        process.stdout,
        selectors.EVENT_READ,
        "stdout",
    )

    selector.register(
        process.stderr,
        selectors.EVENT_READ,
        "stderr",
    )

    buffers = {
        "stdout": bytearray(),
        "stderr": bytearray(),
    }

    limits = {
        "stdout": MAX_STDOUT_BYTES,
        "stderr": MAX_STDERR_BYTES,
    }

    deadline = (
        time.monotonic()
        + max(
            0.1,
            float(timeout_seconds),
        )
    )

    failure: str | None = None

    try:
        while (
            selector.get_map()
            or process.poll() is None
        ):
            if (
                cancel_event is not None
                and cancel_event.is_set()
            ):
                failure = "worker_cancelled"
                break

            if time.monotonic() >= deadline:
                failure = "worker_timeout"
                break

            for key, _ in selector.select(
                timeout=0.05
            ):
                chunk = os.read(
                    key.fd,
                    65_536,
                )

                if not chunk:
                    selector.unregister(
                        key.fileobj
                    )
                    continue

                stream = str(
                    key.data
                )

                remaining = (
                    limits[stream]
                    - len(buffers[stream])
                )

                if remaining <= 0:
                    failure = (
                        f"worker_{stream}_limit"
                    )
                    break

                buffers[stream].extend(
                    chunk[:remaining]
                )

                if len(chunk) > remaining:
                    failure = (
                        f"worker_{stream}_limit"
                    )
                    break

            if failure:
                break

    finally:
        selector.close()

        if failure:
            _kill_process_group(
                process
            )
        else:
            try:
                process.wait(
                    timeout=2
                )
            except subprocess.TimeoutExpired:
                failure = "worker_exit_timeout"
                _kill_process_group(
                    process
                )

        process.stdout.close()
        process.stderr.close()

    return (
        int(
            process.returncode
            if process.returncode is not None
            else -1
        ),
        bytes(
            buffers["stdout"]
        ),
        bytes(
            buffers["stderr"]
        ),
        failure,
    )


def _run_scientific_worker_process(
    job: dict[str, Any],
    *,
    source: VerifiedScientificSource | None = None,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_limit_mb: int | None = None,
) -> dict[str, Any]:
    """Execute one fixed ScientificForge worker in a private temporary root."""

    temporary = Path(
        tempfile.mkdtemp(
            prefix="elysia-scientificforge-"
        )
    )

    try:
        temporary.chmod(
            0o700
        )

        payload = dict(
            job
        )

        if source is not None:
            snapshot = (
                copy_verified_source_snapshot(
                    source,
                    temporary,
                    cancel_event=cancel_event,
                )
            )

            payload[
                "source_snapshot"
            ] = str(snapshot)

            payload[
                "expected_source_sha256"
            ] = source.sha256

        request_path = (
            temporary / "request.json"
        )

        result_path = (
            temporary / "result.json"
        )

        request_path.write_text(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        request_path.chmod(
            0o600
        )

        # A frozen Elysia CLI is not a general Python interpreter. Both paths
        # select the same fixed worker, never a model-provided module/command.
        argv = [
            sys.executable,
            *(["scientific-worker"] if getattr(sys, "frozen", False)
              else ["-m", WORKER_MODULE]),
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ]

        (
            exit_code,
            stdout,
            stderr,
            failure,
        ) = _bounded_process(
            argv,
            cwd=PROJECT_ROOT,
            environment=_minimal_environment(
                temporary,
                memory_limit_mb=memory_limit_mb,
                cpu_seconds=(max(1, int(timeout_seconds) + 1) if memory_limit_mb is not None else None),
            ),
            cancel_event=cancel_event,
            timeout_seconds=timeout_seconds,
        )

        if failure == "worker_cancelled":
            return {
                "status": "cancelled",
                "blocked_reason": "operator_cancelled",
                "exit_code": exit_code,
                "stdout_bytes": len(stdout),
                "stderr_bytes": len(stderr),
            }

        if failure is not None:
            return {
                "status": "failed",
                "blocked_reason": failure,
                "exit_code": exit_code,
                "stdout_bytes": len(stdout),
                "stderr_bytes": len(stderr),
                "diagnostic_hash": (
                    sha256(stderr).hexdigest()
                    if stderr
                    else None
                ),
            }

        if (
            not result_path.is_file()
            or result_path.is_symlink()
        ):
            return {
                "status": "failed",
                "blocked_reason": "worker_result_missing",
                "exit_code": exit_code,
            }

        if (
            result_path.stat().st_size
            > MAX_RESULT_BYTES
        ):
            return {
                "status": "failed",
                "blocked_reason": "worker_result_too_large",
                "exit_code": exit_code,
            }

        try:
            result = json.loads(
                result_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return {
                "status": "failed",
                "blocked_reason": "worker_result_invalid",
                "exit_code": exit_code,
            }

        if not isinstance(
            result,
            dict,
        ):
            return {
                "status": "failed",
                "blocked_reason": "worker_result_invalid",
                "exit_code": exit_code,
            }

        result.setdefault(
            "exit_code",
            exit_code,
        )

        return result

    finally:
        shutil.rmtree(
            temporary,
            ignore_errors=True,
        )


def run_scientific_worker_process(
    job: dict[str, Any], *, source: VerifiedScientificSource | None = None,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_limit_mb: int | None = None,
) -> dict[str, Any]:
    """Supervise staging and the existing isolated worker with real telemetry.

    The caller's cancellation event retains its identity/authority. A thermal
    trip uses a separate event and is reported as resource failure, not a user
    cancellation. The process loop kills the complete owned group on either.
    """
    from app.cognition.resource_guard import ResourceGuard
    cutoff = threading.Event()
    started = time.monotonic()
    deadline = started + max(0, timeout_seconds)
    class AdmissionInterrupted(Exception):
        pass
    class Cancellation:
        def is_set(self):
            return (cutoff.is_set() or time.monotonic() >= deadline
                    or bool(cancel_event is not None and cancel_event.is_set()))
    def wait_check():
        if Cancellation().is_set():
            raise AdmissionInterrupted()
    guard = ResourceGuard(lambda reason: cutoff.set())
    try:
        if cancel_event is not None and cancel_event.is_set():
            return {"status": "cancelled", "blocked_reason": "operator_cancelled"}
        try:
            admitted = guard.start(wait_check=wait_check)
        except AdmissionInterrupted:
            admitted = False
        if not admitted:
            result = {"status": "failed", "blocked_reason": "worker_resource_limited"}
        else:
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                result = {"status": "failed", "blocked_reason": "worker_timeout"}
            else:
                try:
                    result = _run_scientific_worker_process(job, source=source,
                        cancel_event=Cancellation(), timeout_seconds=remaining, memory_limit_mb=memory_limit_mb)
                except ScientificProcessError:
                    if not Cancellation().is_set():
                        raise
                    result = {"status": "failed", "blocked_reason": "worker_resource_limited"}
        if cancel_event is not None and cancel_event.is_set():
            result = {"status": "cancelled", "blocked_reason": "operator_cancelled"}
        elif guard.reason:
            # Late successful output cannot outrank the safety cutoff.
            result = {"status": "failed", "blocked_reason": "worker_resource_limited"}
        elif time.monotonic() >= deadline:
            result = {"status": "failed", "blocked_reason": "worker_timeout"}
        result["resource_guard"] = guard.receipt()
        return result
    finally:
        guard.close()


__all__ = (
    "DEFAULT_TIMEOUT_SECONDS",
    "ScientificProcessError",
    "copy_verified_source_snapshot",
    "run_scientific_worker_process",
)
