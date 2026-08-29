#!/usr/bin/env python3
"""Real local Ollama streaming/cancellation promotion benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.model_invoker import _call_ollama_chat


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))], 3)


def summarize(rows: list[dict]) -> dict:
    full = [float(row["latency_ms"]) for row in rows]
    first = [
        float(row["provider_metadata"]["first_token_ms"])
        for row in rows
        if row.get("provider_metadata", {}).get("first_token_ms") is not None
    ]
    return {
        "samples": len(rows),
        "successes": sum(bool(row.get("ok")) for row in rows),
        "full_latency_ms_p50": round(median(full), 3),
        "full_latency_ms_p95": percentile(full, 0.95),
        "full_latency_ms_p99": percentile(full, 0.99),
        "first_token_ms_p50": round(median(first), 3) if first else None,
        "first_token_ms_p95": percentile(first, 0.95) if first else None,
        "response_hashes": [
            hashlib.sha256(str(row.get("response_text") or "").encode("utf-8")).hexdigest()
            for row in rows
        ],
        "all_responses_nonempty": all(bool(str(row.get("response_text") or "").strip()) for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    prompt = (
        "Using no tools and no private context, give one concise sentence explaining "
        "why a synthetic wetland monitoring plan should record measurement units."
    )
    system = "You are a local test model. Answer concisely without hidden reasoning."
    # One explicit warmup separates model-load latency from warm transport truth.
    warmup = _call_ollama_chat(
        args.model, system, prompt, stream_transport=True, timeout_s=180
    )
    if not warmup.get("ok"):
        raise SystemExit(f"Ollama warmup failed: {warmup.get('error', 'unknown')}")

    streamed: list[dict] = []
    nonstreamed: list[dict] = []
    for _index in range(max(1, min(10, args.samples))):
        streamed.append(_call_ollama_chat(
            args.model, system, prompt, stream_transport=True, timeout_s=180
        ))
        nonstreamed.append(_call_ollama_chat(
            args.model, system, prompt, stream_transport=False, timeout_s=180
        ))

    checks = 0
    def cancel_after_first_fragment() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    cancelled = _call_ollama_chat(
        args.model,
        system,
        "Write several paragraphs of synthetic text for cancellation testing.",
        stream_transport=True,
        timeout_s=180,
        cancel_check=cancel_after_first_fragment,
    )
    stream_summary = summarize(streamed)
    nonstream_summary = summarize(nonstreamed)
    integrity = (
        stream_summary["successes"] == stream_summary["samples"]
        and nonstream_summary["successes"] == nonstream_summary["samples"]
        and stream_summary["all_responses_nonempty"]
        and nonstream_summary["all_responses_nonempty"]
        and cancelled.get("cancelled") is True
        and "response_text" not in cancelled
    )
    result = {
        "contract": "part2d-real-ollama-streaming-benchmark-v1",
        "model": args.model,
        "fixture": "synthetic_nonprivate",
        "warmup_load_duration_ms": round(
            float(warmup.get("provider_metadata", {}).get("load_duration") or 0) / 1_000_000,
            3,
        ),
        "streaming": stream_summary,
        "non_streaming": nonstream_summary,
        "cancellation": {
            "cancelled": cancelled.get("cancelled") is True,
            "partial_response_exposed": "response_text" in cancelled,
            "latency_ms": cancelled.get("latency_ms"),
        },
        "final_answer_integrity_gate": integrity,
        "decision": "promote_buffered_transport_streaming" if integrity else "do_not_promote",
        "ui_policy": "transport streams locally for cancellation/timing; user-visible answer remains buffered until verification",
        "private_content_included": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
