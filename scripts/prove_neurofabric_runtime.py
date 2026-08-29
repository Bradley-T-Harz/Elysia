#!/usr/bin/env python3
"""Sanitized real-device proof for the optional Neurofabric runtimes."""

from __future__ import annotations

import argparse
import gc
import importlib.metadata
import json


def _prove_bounded_oom(torch, device) -> bool:
    try:
        torch.cuda.set_per_process_memory_fraction(0.05, device=device)
        impossible_under_test_ceiling = torch.empty(
            (1024, 1024, 1024), dtype=torch.float32, device=device
        )
        del impossible_under_test_ceiling
    except torch.OutOfMemoryError:
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", choices=("cuda", "cpu"), required=True)
    args = parser.parse_args()

    import torch

    cuda_available = bool(torch.cuda.is_available())
    if args.expect == "cuda" and not cuda_available:
        raise SystemExit("CUDA profile proof failed: CUDA is unavailable")
    if args.expect == "cpu" and cuda_available:
        raise SystemExit("CPU fallback proof failed: CUDA remained visible")

    torch.manual_seed(20260822)
    left = torch.arange(1, 17, dtype=torch.float32).reshape(4, 4)
    right = torch.eye(4, dtype=torch.float32)
    cpu_result = left @ right
    payload: dict[str, object] = {
        "contract": "elysia-neurofabric-device-proof-v1",
        "torch_version": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "cuda_available": cuda_available,
        "cpu_tensor_verified": bool(torch.equal(cpu_result, left)),
        "ncps_version": importlib.metadata.version("ncps"),
        "private_content_included": False,
    }

    if cuda_available:
        device = torch.device("cuda:0")
        properties = torch.cuda.get_device_properties(device)
        first = torch.randn((256, 256), generator=torch.Generator().manual_seed(44))
        second = torch.randn((256, 256), generator=torch.Generator().manual_seed(45))
        first_gpu = first.to(device)
        second_gpu = second.to(device)
        product_a = (first_gpu @ second_gpu).cpu()
        torch.cuda.synchronize()
        first_gpu = first.to(device)
        second_gpu = second.to(device)
        product_b = (first_gpu @ second_gpu).cpu()
        torch.cuda.synchronize()
        round_trip = left.to(device).cpu()
        payload.update(
            device_count=torch.cuda.device_count(),
            device_name=torch.cuda.get_device_name(device),
            device_total_memory_bytes=int(properties.total_memory),
            gpu_tensor_verified=bool(product_a.shape == (256, 256)),
            cpu_gpu_cpu_round_trip_verified=bool(torch.equal(round_trip, left)),
            deterministic_workload_verified=bool(torch.equal(product_a, product_b)),
        )

        del first_gpu, second_gpu, product_a, product_b, round_trip
        torch.cuda.empty_cache()
        gc.collect()
        try:
            oom_caught = _prove_bounded_oom(torch, device)
        finally:
            torch.cuda.set_per_process_memory_fraction(1.0, device=device)
            torch.cuda.empty_cache()
            gc.collect()
        payload["bounded_oom_caught"] = oom_caught
        payload["allocated_bytes_after_cleanup"] = int(torch.cuda.memory_allocated(device))
    else:
        payload.update(
            device_count=0,
            device_name=None,
            gpu_tensor_verified=False,
            cpu_gpu_cpu_round_trip_verified=False,
            deterministic_workload_verified=True,
            bounded_oom_caught="not_applicable_cpu_fallback",
            allocated_bytes_after_cleanup=0,
        )

    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
