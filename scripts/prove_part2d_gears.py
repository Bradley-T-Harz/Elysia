#!/usr/bin/env python3
"""Exercise all six Part 2D gears through the real local API/runtime/model path.

Only sanitized timings, routing facts, hashes, and bounded counts are emitted.
The synthetic account, conversations, receipts, and model outcome database live
under a temporary XDG root that is deleted when the proof exits.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import tempfile
from time import perf_counter
from urllib import request as urllib_request
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


GEARS = (
    "reflex",
    "quick",
    "standard",
    "deep",
    "deliberative",
    "research_engineering",
)

MESSAGES = {
    "reflex": "hello",
    "quick": "Give one short sentence about rain.",
    "standard": "Explain in exactly one short sentence why leaves are green.",
    "deep": "In exactly one short sentence, connect cause A to consequence B through two intermediate steps.",
    "deliberative": "In exactly one short sentence, contrast two ordinary choices and name one tradeoff.",
    "research_engineering": "In exactly one short sentence, describe a simple cycle with three stages.",
}


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * fraction) + 0.999999) - 1))
    return round(ordered[index], 3)


def _unload(model: str) -> None:
    payload = json.dumps({"model": model, "keep_alive": 0}).encode("utf-8")
    try:
        with urllib_request.urlopen(
            urllib_request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            ),
            timeout=30,
        ) as response:
            response.read()
    except Exception:
        pass


def _gpu_temperature_c() -> float | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        if completed.returncode == 0:
            return float(completed.stdout.splitlines()[0].strip())
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return None


async def _wait_for_thermal_headroom(maximum_c: float = 87.0) -> float | None:
    """Avoid starting above the Governor's 88 C GPU safety boundary.

    A temperature rise during inference may still earn the governed CPU
    fallback; gear and device are deliberately separate axes.
    """
    deadline = perf_counter() + 60.0
    while True:
        temperature = await asyncio.to_thread(_gpu_temperature_c)
        if temperature is None or temperature <= maximum_c:
            return temperature
        if perf_counter() >= deadline:
            raise RuntimeError(
                f"GPU did not cool below the proof preflight ceiling ({maximum_c} C)."
            )
        await asyncio.sleep(2.0)


async def _prove() -> dict[str, object]:
    import httpx

    from app.api.main import create_app
    from app.install.local_auth import LocalApiAuthPolicy
    from app.install.paths import RuntimeMode, resolve_elysia_paths

    paths = resolve_elysia_paths()
    app = create_app(
        auth_policy=LocalApiAuthPolicy(
            required=False,
            credential_path=paths.auth_dir / "synthetic-proof-credential",
            runtime_mode=RuntimeMode.SOURCE,
            source="part2d_disposable_synthetic_proof",
        )
    )
    transport = httpx.ASGITransport(app=app)
    results: dict[str, object] = {}
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
        timeout=300,
    ) as client:
        created = await client.post(
            "/account/create",
            json={
                "username": "part2d-gear-proof",
                "password": "synthetic Part2D gear proof password only",
            },
        )
        created.raise_for_status()
        if created.json().get("status") != "ok":
            raise RuntimeError("Synthetic account creation did not succeed.")

        current_settings = (await client.get("/memory/settings")).json()["data"]["settings"]
        current_settings.update(
            {
                "autonomy_level": 5,
                "internet_master_enabled": False,
                "preferred_reasoning_gear": "automatic",
                "compute_preference": "automatic",
                # The six-gear benchmark measures Governor policy, not maximum
                # model size. Resource preference earns the configured 8B local
                # fallback and keeps repeated proof calls thermally bounded.
                "model_performance_preference": "resource",
                "background_cognition_enabled": False,
                "cpu_percent_ceiling": 95,
                "ram_mb_ceiling": 32768,
                "vram_mb_ceiling": 16000,
                "max_background_jobs": 1,
            }
        )
        updated = await client.put("/memory/settings", json=current_settings)
        updated.raise_for_status()
        persisted_settings = updated.json()["data"]["settings"]
        if persisted_settings.get("vram_mb_ceiling") != 16000:
            raise RuntimeError("Synthetic resource settings did not persist.")

        # Prove four governed general-role gear policies against shared model
        # residency, then release that residency before the Quick model.
        execution_order = (
            "standard", "deep", "deliberative", "research_engineering",
            "quick", "reflex",
        )
        for gear in execution_order:
            samples: list[float] = []
            receipts: list[dict[str, object]] = []
            for sample_index in range(3):
                preflight_temperature = (
                    None
                    if gear == "reflex"
                    else await _wait_for_thermal_headroom()
                )
                request_id = f"part2d-{gear}-{sample_index}"
                started = perf_counter()
                response = await client.post(
                    "/chat/send",
                    json={
                        "message": MESSAGES[gear],
                        "request_id": request_id,
                        "requested_gear": gear,
                        "ui_surface": "part2d_disposable_proof",
                    },
                )
                elapsed_ms = (perf_counter() - started) * 1000
                response.raise_for_status()
                envelope = response.json()
                if envelope.get("status") != "ok":
                    safe_data = dict(envelope.get("data") or {})
                    raise RuntimeError(
                        f"Gear {gear} failed with status {envelope.get('status')}: "
                        f"errors={envelope.get('errors')} "
                        f"warnings={envelope.get('warnings')} "
                        f"invocation={safe_data.get('invocation_status')} "
                        f"source={safe_data.get('response_source')} "
                        f"model={safe_data.get('selected_model_runtime_tag')} "
                        f"compute={dict(safe_data.get('compute') or {}).get('reasons')}"
                    )
                data = dict(envelope.get("data") or {})
                governor = dict(data.get("governor") or {})
                compute = dict(data.get("compute") or {})
                text = str(data.get("response_text") or "")
                if governor.get("selected_gear") != gear:
                    raise RuntimeError(
                        f"Requested {gear}, runtime selected {governor.get('selected_gear')}"
                    )
                selected_device = str(compute.get("selected_device") or "")
                if gear != "reflex" and selected_device not in {"cuda:0", "cpu"}:
                    raise RuntimeError(
                        f"Gear {gear} did not complete on a governed local device: "
                        f"device={selected_device}"
                    )
                if (
                    selected_device == "cuda:0"
                    and int(compute.get("observed_vram_mb") or 0) <= 0
                ):
                    raise RuntimeError(
                        f"Gear {gear} claimed CUDA without measured model residency."
                    )
                print(
                    f"proved gear={gear} sample={sample_index + 1} "
                    f"device={compute.get('selected_device')} "
                    f"model={data.get('selected_model_runtime_tag')} "
                    f"elapsed_ms={elapsed_ms:.3f}",
                    file=sys.stderr,
                    flush=True,
                )
                samples.append(round(elapsed_ms, 3))
                receipts.append(
                    {
                        "request_id": request_id,
                        "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "response_chars": len(text),
                        "response_source": data.get("response_source"),
                        "model": data.get("selected_model_runtime_tag"),
                        "device": compute.get("selected_device"),
                        "compute_decision": compute.get("decision"),
                        "estimate_source": dict(compute.get("workload") or {}).get("estimate_source"),
                        "estimated_vram_mb": dict(compute.get("workload") or {}).get("estimated_vram_mb"),
                        "incremental_vram_mb": dict(compute.get("workload") or {}).get("incremental_vram_mb"),
                        "observed_vram_mb": compute.get("observed_vram_mb"),
                        "preflight_gpu_temperature_c": preflight_temperature,
                        "verification_depth": governor.get("verification_depth"),
                        "context_token_budget": governor.get("context_token_budget"),
                        "output_token_budget": governor.get("output_token_budget"),
                        "tool_budget": governor.get("tool_budget"),
                        "research_budget": governor.get("research_budget"),
                        "authority_increased": governor.get("authority_increased"),
                        "private_content_included": False,
                    }
                )
            results[gear] = {
                "sample_count": len(samples),
                "verified_answer_p50_ms": round(median(samples), 3),
                "verified_answer_p95_ms": _percentile(samples, 0.95),
                "samples_ms": samples,
                "receipts": receipts,
            }

        cognition = (await client.get("/cognition/status")).json()["data"]
        account_state = (await client.get("/account/state")).json()["data"]

    _unload("mistral-small3.1:24b")
    _unload("granite3.3:8b")
    observed_devices = sorted({
        str(receipt.get("device") or "")
        for result in results.values()
        for receipt in result["receipts"]
    })
    return {
        "contract": "part2d-six-gear-live-proof-v1",
        "gears": {gear: results[gear] for gear in GEARS},
        "all_six_selected_exactly": set(results) == set(GEARS),
        "all_answers_live_or_deterministic": all(
            receipt["response_source"] in {"live_invoker", "deterministic_reflex"}
            for result in results.values()
            for receipt in result["receipts"]
        ),
        "observed_devices": observed_devices,
        "cuda_execution_observed": "cuda:0" in observed_devices,
        "cpu_execution_observed": "cpu" in observed_devices,
        "active_gpu_leases_after": len(cognition.get("active_gpu_leases") or []),
        "active_compute_jobs_after": int((cognition.get("compute") or {}).get("active_job_count") or 0),
        "synthetic_profile_count_before_disposal": account_state.get("account_count"),
        "disposable_xdg": True,
        "operator_data_touched": False,
        "internet_enabled": False,
        "response_bodies_recorded": False,
        "part2e_started": False,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="elysia-part2d-gears-") as temporary:
        root = Path(temporary)
        os.environ.update(
            {
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"),
                "XDG_CACHE_HOME": str(root / "cache"),
                "XDG_STATE_HOME": str(root / "state"),
                "XDG_RUNTIME_DIR": str(root / "runtime"),
                "ELYSIA_QA_RUN_ID": f"pass10d-i-{root.name}",
                "ELYSIA_RUNTIME_MODE": "source",
                "ELYSIA_API_AUTH_MODE": "development-disabled",
            }
        )
        for name in ("config", "data", "cache", "state", "runtime"):
            (root / name).mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            proof = asyncio.run(_prove())
        finally:
            _unload("mistral-small3.1:24b")
            _unload("granite3.3:8b")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
