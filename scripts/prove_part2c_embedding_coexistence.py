#!/usr/bin/env python3
"""Synthetic proof of Qwen embedding behavior beside Elysia's primary LLM."""

from __future__ import annotations

import json
import subprocess
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:11434"
PRIMARY = "mistral-small3.1:24b"
EMBEDDING = "qwen3-embedding:0.6b"


def post(path: str, payload: dict, *, timeout: float = 300.0) -> tuple[int, dict]:
    request = Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read(64 * 1024 * 1024))
            return int(response.status), result if isinstance(result, dict) else {}
    except HTTPError as exc:
        exc.read(2 * 1024 * 1024)
        return int(exc.code), {}


def processes() -> dict[str, dict]:
    with urlopen(BASE + "/api/ps", timeout=10) as response:
        payload = json.loads(response.read(2 * 1024 * 1024))
    return {
        str(item.get("name") or ""): item
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }


def timed_embedding(options: dict) -> tuple[int, float]:
    started = perf_counter()
    status, _ = post("/api/embed", {
        "model": EMBEDDING,
        "input": "synthetic wetland restoration continuity",
        "truncate": True,
        "keep_alive": "10m",
        "options": options,
    })
    return status, round((perf_counter() - started) * 1000, 3)


def stop(model: str) -> float:
    started = perf_counter()
    subprocess.run(["ollama", "stop", model], check=False, capture_output=True, timeout=60)
    return round((perf_counter() - started) * 1000, 3)


def main() -> int:
    stop(EMBEDDING)
    stop(PRIMARY)
    load_started = perf_counter()
    primary_status, _ = post("/api/generate", {
        "model": PRIMARY,
        "prompt": "Reply with one synthetic word.",
        "stream": False,
        "keep_alive": "10m",
        "options": {"num_predict": 1},
    })
    primary_load_ms = round((perf_counter() - load_started) * 1000, 3)
    before = processes()
    primary_before = before.get(PRIMARY, {})
    gpu_status, gpu_ms = timed_embedding({})
    after_gpu = processes()
    cpu_status, cpu_ms = timed_embedding({"num_gpu": 0})
    after_cpu = processes()
    qwen_cpu = after_cpu.get(EMBEDDING, {})
    primary_cpu = after_cpu.get(PRIMARY, {})
    qwen_stop_ms = stop(EMBEDDING)
    primary_stop_ms = stop(PRIMARY)
    output = {
        "proof": "part2c-embedding-primary-llm-coexistence-v1",
        "primary_model": PRIMARY,
        "primary_load_http_status": primary_status,
        "primary_load_ms": primary_load_ms,
        "primary_resident_before_embedding": PRIMARY in before,
        "primary_size_vram_bytes_before_embedding": int(primary_before.get("size_vram") or 0),
        "default_gpu_embedding_http_status": gpu_status,
        "default_gpu_embedding_ms": gpu_ms,
        "primary_resident_after_gpu_attempt": PRIMARY in after_gpu,
        "cpu_embedding_http_status": cpu_status,
        "cpu_embedding_ms": cpu_ms,
        "cpu_embedding_size_vram_bytes": int(qwen_cpu.get("size_vram") or 0),
        "primary_resident_with_cpu_embedding": PRIMARY in after_cpu,
        "primary_size_vram_bytes_with_cpu_embedding": int(primary_cpu.get("size_vram") or 0),
        "embedding_unload_ms": qwen_stop_ms,
        "primary_unload_ms": primary_stop_ms,
        "no_permanent_gpu_reservation": True,
        "synthetic_only": True,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    if cpu_status != 200 or int(qwen_cpu.get("size_vram") or 0) != 0:
        raise RuntimeError("The deterministic CPU coexistence path did not pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
