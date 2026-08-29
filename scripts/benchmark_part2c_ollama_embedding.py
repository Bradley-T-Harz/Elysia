#!/usr/bin/env python3
"""Synthetic cold/warm/batch benchmark for the promoted Ollama embedding model."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import math
import statistics
import subprocess
from time import perf_counter
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MODEL = "qwen3-embedding:0.6b"
DIMENSION = 1024


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * p)))], 3)


def distribution(values: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "mean": round(statistics.mean(values), 3),
    }


def request_json(url: str, payload: dict | None = None, *, timeout: float = 180.0) -> dict:
    request = Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        method="GET" if payload is None else "POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read(64 * 1024 * 1024))
    if not isinstance(result, dict):
        raise RuntimeError("Ollama returned an invalid JSON contract.")
    return result


def gpu_memory_mib() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=used_memory", "--format=csv,noheader,nounits"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
        return sum(values)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--device", choices=("cpu", "gpu"), required=True)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--unload-first", action="store_true")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Only an explicit loopback Ollama endpoint is accepted.")
    if args.unload_first:
        subprocess.run(["ollama", "stop", MODEL], check=False, timeout=30)

    options = {"num_gpu": 0} if args.device == "cpu" else {}
    base_payload = {
        "model": MODEL,
        "truncate": True,
        "keep_alive": "10m",
        "options": options,
    }
    query = "restore rainfall retention through connected wetland habitat"
    started = perf_counter()
    first = request_json(args.base_url + "/api/embed", {**base_payload, "input": query})
    cold_ms = (perf_counter() - started) * 1000
    embeddings = first.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != 1 or len(embeddings[0]) != DIMENSION:
        raise RuntimeError("The cold embedding response had the wrong shape.")
    if not all(math.isfinite(float(value)) for value in embeddings[0]):
        raise RuntimeError("The cold embedding response contained a nonfinite value.")

    warm: list[float] = []
    for index in range(max(1, args.samples)):
        tick = perf_counter()
        request_json(
            args.base_url + "/api/embed",
            {**base_payload, "input": f"{query} synthetic-query-{index % 7}"},
        )
        warm.append((perf_counter() - tick) * 1000)

    batches: dict[str, dict[str, float]] = {}
    for size in (1, 8, 32):
        texts = [f"Synthetic ecological evidence item {index}: {query}" for index in range(size)]
        values = []
        for _iteration in range(5):
            tick = perf_counter()
            result = request_json(args.base_url + "/api/embed", {**base_payload, "input": texts})
            elapsed = perf_counter() - tick
            returned = result.get("embeddings")
            if not isinstance(returned, list) or len(returned) != size:
                raise RuntimeError("The batch embedding response had the wrong shape.")
            values.append(elapsed)
        batches[str(size)] = {
            "mean_batch_ms": round(statistics.mean(values) * 1000, 3),
            "mean_items_per_second": round(size / statistics.mean(values), 3),
        }

    processes = request_json(args.base_url + "/api/ps").get("models", [])
    model_process = next(
        (item for item in processes if str(item.get("name") or "") == MODEL),
        {},
    )
    output = {
        "benchmark": "part2c-ollama-qwen-device-warm-batch-v1",
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model": MODEL,
        "model_digest": "sha256-06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
        "dimension": DIMENSION,
        "device_requested": args.device,
        "cold_first_request_ms": round(cold_ms, 3),
        "warm_request_latency_ms": distribution(warm),
        "warm_samples": len(warm),
        "batch_throughput": batches,
        "ollama_size_bytes": int(model_process.get("size") or 0),
        "ollama_size_vram_bytes": int(model_process.get("size_vram") or 0),
        "nvidia_compute_process_memory_mib": gpu_memory_mib(),
        "cloud_used": False,
        "synthetic_only": True,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
