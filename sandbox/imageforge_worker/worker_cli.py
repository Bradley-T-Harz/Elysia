"""Lab-only CommonCanvas worker. Torch/Diffusers never enter Elysia core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


BLOCKED_PROMPT_MARKERS = {
    "deepfake", "face swap", "faceswap", "nude", "sexual", "porn", "graphic violence",
    "political persuasion", "campaign propaganda", "celebrity", "public figure", "copyrighted character",
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _failure_reason(exc: Exception) -> str:
    text = str(exc).casefold()
    if "out of memory" in text:
        return "imageforge_cuda_oom"
    if "cuda" in text:
        return "imageforge_cuda_unavailable"
    if isinstance(exc, ValueError):
        return str(exc)[:120] if str(exc).startswith("image_") else "imageforge_request_refused"
    return "imageforge_worker_exception"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request_path = Path(args.request)
    result_path = Path(args.result)
    started = time.monotonic()
    try:
        job = json.loads(request_path.read_text(encoding="utf-8"))
        output = Path(str(job.get("output_path") or ""))
        root = Path(str(job.get("job_root") or ""))
        prompt = str(job.get("prompt") or "")
        negative_prompt = str(job.get("negative_prompt") or "")
        width = int(job.get("width") or 256)
        height = int(job.get("height") or 256)
        steps = int(job.get("steps") or 8)
        seed = int(job.get("seed") or 5)
        model_id = str(job.get("model_id") or "")
        model_path = Path(str(job.get("model_path") or ""))
        if model_id not in {"commoncanvas-xl-c", "flux1-schnell"}:
            raise ValueError("image_model_not_allowed")
        if not _inside(output, root) or output.suffix.lower() != ".png":
            raise ValueError("image_output_boundary_failed")
        max_steps = 1 if model_id == "flux1-schnell" else 12
        if not model_path.is_absolute() or not model_path.is_dir():
            raise ValueError("image_model_not_available")
        if not prompt or len(prompt) > 1200 or width != 256 or height != 256 or not 1 <= steps <= max_steps:
            raise ValueError("image_settings_not_allowed")
        if model_id == "flux1-schnell" and negative_prompt:
            raise ValueError("image_flux_negative_prompt_not_supported")
        lowered = f"{prompt} {negative_prompt}".casefold()
        if job.get("contains_real_person_request") is True or any(marker in lowered for marker in BLOCKED_PROMPT_MARKERS):
            raise ValueError("image_prompt_policy_blocked")

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from diffusers import FluxPipeline, StableDiffusionXLPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("imageforge_cuda_unavailable")
        torch.cuda.reset_peak_memory_stats()
        if model_id == "flux1-schnell":
            pipe = FluxPipeline.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
                low_cpu_mem_usage=True,
            )
            pipe.enable_sequential_cpu_offload(gpu_id=0)
            pipe.enable_attention_slicing()
            pipe.vae.enable_slicing()
            pipe.vae.enable_tiling()
        else:
            pipe = StableDiffusionXLPipeline.from_pretrained(
                model_path,
                torch_dtype=torch.float16,
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
            )
            pipe.enable_model_cpu_offload()
            pipe.enable_attention_slicing()
        pipe.set_progress_bar_config(disable=True)
        generator = torch.Generator(device="cpu").manual_seed(seed)
        common_args = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "generator": generator,
        }
        if model_id == "flux1-schnell":
            image = pipe(**common_args, guidance_scale=0.0, max_sequence_length=256).images[0]
        else:
            image = pipe(**common_args, negative_prompt=negative_prompt or None, guidance_scale=5.0).images[0]
        image.save(output)
        result = {
            "status": "completed",
            "worker_key": "imageforge_worker",
            "model_id": model_id,
            "output_path": str(output),
            "output_sha256": _sha(output),
            "output_bytes": output.stat().st_size,
            "width": image.width,
            "height": image.height,
            "runtime_seconds": round(time.monotonic() - started, 3),
            "peak_gpu_memory_mib": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1),
            "synthetic_media": True,
            "network_used": False,
            "cloud_used": False,
        }
    except Exception as exc:
        result = {"status": "failed", "blocked_reason": _failure_reason(exc), "error_type": type(exc).__name__}
    result_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
