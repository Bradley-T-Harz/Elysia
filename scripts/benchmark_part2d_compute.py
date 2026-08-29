#!/usr/bin/env python3
"""Real synthetic GPU-lease and primary/embedding coexistence benchmark."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:11434"
PRIMARY = "mistral-small3.1:24b"
EMBEDDING = "qwen3-embedding:0.6b"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def post(path: str, payload: dict, *, timeout: float = 300.0) -> dict:
    request = Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read(64 * 1024 * 1024))
    if not isinstance(result, dict):
        raise RuntimeError("The local Ollama response was not an object.")
    return result


def stop(model: str) -> float:
    started = perf_counter()
    subprocess.run(["ollama", "stop", model], check=False, capture_output=True, timeout=60)
    return round((perf_counter() - started) * 1000, 3)


def process_map() -> dict[str, dict]:
    with urlopen(BASE + "/api/ps", timeout=10) as response:
        payload = json.loads(response.read(2 * 1024 * 1024))
    return {
        str(item.get("name") or ""): item
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }


def embed(device: str, samples: int = 5) -> dict:
    options = {} if device == "gpu" else {"num_gpu": 0}
    latencies: list[float] = []
    for index in range(samples):
        started = perf_counter()
        result = post("/api/embed", {
            "model": EMBEDDING,
            "input": f"synthetic governed compute fixture {index}",
            "truncate": True,
            "keep_alive": "10m",
            "options": options,
        })
        if len(result.get("embeddings") or []) != 1:
            raise RuntimeError("The embedding response shape was invalid.")
        latencies.append((perf_counter() - started) * 1000)
    ordered = sorted(latencies)
    return {
        "samples": samples,
        "p50_ms": round(median(ordered), 3),
        "p95_ms": round(ordered[-1], 3),
        "p99_ms": round(ordered[-1], 3),
        "cold_first_ms": round(latencies[0], 3),
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="elysia-part2d-compute-") as root:
        base = Path(root)
        for variable, leaf in (
            ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
            ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
            ("XDG_RUNTIME_DIR", "runtime"),
        ):
            path = base / leaf
            path.mkdir(mode=0o700)
            os.environ[variable] = str(path)
        os.environ["ELYSIA_QA_RUN_ID"] = f"pass10d-i-{base.name}"

        from app.cognition.compute_governor import (
            ComputeLedger,
            WorkloadDescriptor,
            decide_compute,
        )
        from app.install.paths import resolve_elysia_paths

        paths = resolve_elysia_paths()
        stop(EMBEDDING)
        stop(PRIMARY)
        workload = WorkloadDescriptor(
            workload_id="synthetic-idle-embedding",
            owner_user_id="synthetic",
            task_kind="semantic_query_embedding",
            priority="interactive",
            interactive=True,
            estimated_cpu_percent=35,
            estimated_ram_mb=1536,
            estimated_vram_mb=1800,
            estimated_duration_ms=3000,
        )
        idle = decide_compute(workload, preference="automatic", paths=paths)
        idle_benchmark = embed("gpu" if idle.selected_device == "cuda:0" else "cpu")
        idle_processes = process_map()
        ledger = ComputeLedger(paths)
        if idle.lease_id:
            ledger.release(idle.lease_id, reason="idle_embedding_benchmark_complete")
        if idle.reservation_id:
            ledger.release_job(idle.reservation_id, reason="idle_embedding_benchmark_complete")
        embedding_stop_ms = stop(EMBEDDING)

        primary_started = perf_counter()
        primary = post("/api/generate", {
            "model": PRIMARY,
            "prompt": "Reply with one synthetic word.",
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_predict": 1},
        })
        primary_load_ms = (perf_counter() - primary_started) * 1000
        before_contention = process_map()
        contended = decide_compute(
            WorkloadDescriptor(
                **{
                    **workload.__dict__,
                    "workload_id": "synthetic-contended-embedding",
                    "priority": "background",
                    "interactive": False,
                    "preemptible": True,
                }
            ),
            preference="automatic",
            paths=paths,
        )
        contended_benchmark = embed(
            "gpu" if contended.selected_device == "cuda:0" else "cpu"
        )
        after_contention = process_map()
        if contended.lease_id:
            ledger.release(contended.lease_id, reason="contended_embedding_benchmark_complete")
        if contended.reservation_id:
            ledger.release_job(
                contended.reservation_id, reason="contended_embedding_benchmark_complete"
            )
        qwen_stop_ms = stop(EMBEDDING)
        primary_stop_ms = stop(PRIMARY)

        output = {
            "contract": "part2d-real-compute-governor-coexistence-v1",
            "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "fixture": "synthetic_nonprivate_disposable_xdg",
            "idle_embedding": {
                "decision": idle.to_payload(),
                "benchmark": idle_benchmark,
                "resident_size_vram_bytes": int(
                    idle_processes.get(EMBEDDING, {}).get("size_vram") or 0
                ),
            },
            "primary_contention": {
                "primary_http_ok": bool(primary.get("done", True)),
                "primary_load_ms": round(primary_load_ms, 3),
                "primary_size_vram_bytes_before": int(
                    before_contention.get(PRIMARY, {}).get("size_vram") or 0
                ),
                "embedding_decision": contended.to_payload(),
                "embedding_benchmark": contended_benchmark,
                "primary_remained_resident": PRIMARY in after_contention,
                "primary_size_vram_bytes_after": int(
                    after_contention.get(PRIMARY, {}).get("size_vram") or 0
                ),
            },
            "unload_ms": {
                "idle_embedding": embedding_stop_ms,
                "contended_embedding": qwen_stop_ms,
                "primary": primary_stop_ms,
            },
            "no_orphan_gpu_leases": not ledger.active_leases(),
            "no_orphan_compute_jobs": not ledger.active_jobs(),
            "operator_data_used": False,
        }
        print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
