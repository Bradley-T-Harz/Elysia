"""Lab-only Wan text-to-video worker. Heavy imports stay outside Elysia core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


BLOCKED_PROMPT_MARKERS = {
    "deepfake", "face swap", "faceswap", "nude", "sexual", "porn", "graphic violence",
    "political persuasion", "campaign propaganda", "celebrity", "public figure",
    "copyrighted character", "voice-driven avatar", "impersonate", "real person",
}
MAX_OUTPUT_BYTES = 64 * 1024 * 1024


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
        return "videoforge_cuda_oom"
    if "cuda" in text:
        return "videoforge_cuda_unavailable"
    if isinstance(exc, FileNotFoundError):
        return "videoforge_local_model_missing"
    if isinstance(exc, ValueError):
        return str(exc)[:120] if str(exc).startswith("videoforge_") else "videoforge_request_refused"
    return "videoforge_worker_exception"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request_path = Path(args.request)
    result_path = Path(args.result)
    started = time.monotonic()
    pipe = None
    try:
        job = json.loads(request_path.read_text(encoding="utf-8"))
        output = Path(str(job.get("output_path") or ""))
        root = Path(str(job.get("job_root") or ""))
        prompt = str(job.get("prompt") or "")
        negative_prompt = str(job.get("negative_prompt") or "")
        width = int(job.get("width") or 416)
        height = int(job.get("height") or 256)
        frames = int(job.get("frames") or 9)
        fps = int(job.get("fps") or 8)
        steps = int(job.get("steps") or 4)
        seed = int(job.get("seed") or 5)
        model_path = Path(str(job.get("model_path") or ""))
        if (
            job.get("model_id") != "wan21-t2v-1.3b"
            or not model_path.is_absolute()
            or not (model_path / "model_index.json").is_file()
        ):
            raise ValueError("videoforge_model_not_allowed")
        if not _inside(output, root) or output.suffix.lower() != ".mp4":
            raise ValueError("videoforge_output_boundary_failed")
        if not prompt or len(prompt) > 1200 or (width, height, frames, fps, steps) != (416, 256, 9, 8, 4):
            raise ValueError("videoforge_resource_profile_not_allowed")
        lowered = f"{prompt} {negative_prompt}".casefold()
        if job.get("contains_real_person_request") is True or any(marker in lowered for marker in BLOCKED_PROMPT_MARKERS):
            raise ValueError("videoforge_prompt_policy_blocked")

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        import torch
        from diffusers import AutoencoderKLWan, WanPipeline
        from diffusers.utils import export_to_video

        if not torch.cuda.is_available():
            raise RuntimeError("videoforge cuda unavailable")
        torch.cuda.reset_peak_memory_stats()
        vae = AutoencoderKLWan.from_pretrained(
            model_path,
            subfolder="vae",
            torch_dtype=torch.float32,
            local_files_only=True,
        )
        vae.enable_tiling()
        pipe = WanPipeline.from_pretrained(
            model_path,
            vae=vae,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )
        pipe.enable_model_cpu_offload()
        generator = torch.Generator(device="cpu").manual_seed(seed)
        generated_frames = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            height=height,
            width=width,
            num_frames=frames,
            num_inference_steps=steps,
            guidance_scale=5.0,
            generator=generator,
            max_sequence_length=128,
        ).frames[0]
        export_to_video(generated_frames, str(output), fps=fps)
        if not output.is_file() or output.stat().st_size > MAX_OUTPUT_BYTES:
            output.unlink(missing_ok=True)
            raise ValueError("videoforge_output_missing_or_too_large")
        result = {
            "status": "completed",
            "worker_key": "videoforge_worker",
            "model_id": "wan21-t2v-1.3b",
            "output_path": str(output),
            "output_sha256": _sha(output),
            "output_bytes": output.stat().st_size,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": fps,
            "steps": steps,
            "duration_seconds": round(frames / float(fps), 3),
            "runtime_seconds": round(time.monotonic() - started, 3),
            "peak_gpu_memory_mib": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1),
            "synthetic_media": True,
            "network_used": False,
            "cloud_used": False,
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "blocked_reason": _failure_reason(exc),
            "error_type": type(exc).__name__,
        }
    finally:
        if pipe is not None:
            del pipe
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    result_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
