"""CLI boundary for the fixed ScientificForge worker."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from sandbox.scientificforge_worker.worker import (
    ScientificWorkerError,
    run_scientific_job,
)


MAX_REQUEST_BYTES = 512 * 1024


def _apply_resource_limits() -> bool:
    """Apply parent-declared limits before importing numerical backends."""
    memory = os.environ.get("ELYSIA_SCIENTIFIC_ADDRESS_SPACE_MB")
    cpu = os.environ.get("ELYSIA_SCIENTIFIC_CPU_SECONDS")
    if memory is None and cpu is None:
        return True  # Unchanged v0.1 worker contract.
    try:
        import resource
        if memory is None or cpu is None:
            return False
        memory_bytes = int(memory) * 1024 * 1024
        cpu_seconds = int(cpu)
        if not 256 <= int(memory) <= 16384 or not 1 <= cpu_seconds <= 120:
            return False
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024, 512 * 1024))
        return True
    except (ImportError, OSError, ValueError, AttributeError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--request",
        required=True,
    )
    parser.add_argument(
        "--result",
        required=True,
    )
    args = parser.parse_args(argv)

    request_path = Path(
        args.request
    )
    result_path = Path(
        args.result
    )

    if (
        not request_path.is_file()
        or request_path.is_symlink()
        or request_path.stat().st_size
        > MAX_REQUEST_BYTES
    ):
        return 2

    try:
        if not _apply_resource_limits():
            raise ScientificWorkerError("native_resource_limits_unavailable")
        payload = json.loads(
            request_path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "request_not_object"
            )

        result = run_scientific_job(
            payload
        )
        if os.environ.get("ELYSIA_SCIENTIFIC_ADDRESS_SPACE_MB") is not None:
            result["resource_controls"] = {
                "address_space_limit_mb": int(os.environ["ELYSIA_SCIENTIFIC_ADDRESS_SPACE_MB"]),
                "cpu_time_limit_seconds": int(os.environ["ELYSIA_SCIENTIFIC_CPU_SECONDS"]),
                "file_size_limit_bytes": 512 * 1024,
                "native_threads": int(os.environ.get("OMP_NUM_THREADS", "1")),
                "hard_cpu_percentage_enforced": False,
            }

    except ScientificWorkerError as exc:
        result = {
            "status": "blocked",
            "blocked_reason": str(exc),
            "network_access_used": False,
            "source_mutated": False,
            "arbitrary_python_used": False,
            "shell_used": False,
            "package_install_used": False,
        }

    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        result = {
            "status": "failed",
            "blocked_reason": (
                "scientific_worker_input_failed:"
                + type(exc).__name__
            ),
            "network_access_used": False,
            "source_mutated": False,
            "arbitrary_python_used": False,
            "shell_used": False,
            "package_install_used": False,
        }

    result_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_path.write_text(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        result_path.chmod(
            0o600
        )
    except OSError:
        pass

    return (
        0
        if result.get("status")
        == "completed"
        else 3
    )


if __name__ == "__main__":
    sys.exit(main())
