"""Local-only hardware truth for Setup and Doctor; no fingerprinting or egress."""

from __future__ import annotations

import os
import platform
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NEUROFABRIC_LOCK = ROOT / "config" / "install" / "neurofabric_runtime_lock.yaml"


def _driver_branch(value: str) -> int | None:
    try:
        return int(value.strip().split(".", 1)[0])
    except (TypeError, ValueError):
        return None


def detect_local_hardware(
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    lock_path: Path = DEFAULT_NEUROFABRIC_LOCK,
    cpuinfo_path: Path = Path("/proc/cpuinfo"),
) -> dict[str, Any]:
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    minimum_cpu_features = {
        str(item).strip().lower()
        for item in lock["variants"]["cpu"].get("minimum_cpu_features", [])
        if str(item).strip()
    }
    cpu_features: set[str] = set()
    try:
        for line in cpuinfo_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip().lower() in {"flags", "features"}:
                cpu_features = {item.strip().lower() for item in value.split() if item.strip()}
                break
    except OSError:
        pass
    missing_cpu_features = sorted(minimum_cpu_features - cpu_features)
    minimum_branch = int(lock["variants"]["cuda_mega"]["minimum_nvidia_driver_branch"])
    minimum_vram_mb = int(lock["variants"]["cuda_mega"]["minimum_vram_mb"])
    command = shutil.which("nvidia-smi")
    gpu: dict[str, Any] = {
        "detected": False,
        "vendor": None,
        "model": None,
        "driver_version": None,
        "memory_total_mb": None,
        "cuda_variant_supported": False,
        "status": "not_present",
    }
    if command:
        try:
            result = command_runner(
                [
                    command,
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            first = next((line for line in result.stdout.splitlines() if line.strip()), "")
            parts = [part.strip() for part in first.split(",")]
            if result.returncode == 0 and len(parts) >= 3:
                branch = _driver_branch(parts[1])
                memory_total_mb = int(float(parts[2]))
                driver_supported = branch is not None and branch >= minimum_branch
                memory_supported = memory_total_mb >= minimum_vram_mb
                cuda_supported = driver_supported and memory_supported
                gpu.update(
                    {
                        "detected": True,
                        "vendor": "NVIDIA",
                        "model": parts[0][:160],
                        "driver_version": parts[1][:40],
                        "memory_total_mb": memory_total_mb,
                        "cuda_variant_supported": cuda_supported,
                        "status": (
                            "supported" if cuda_supported
                            else "unsupported_driver" if not driver_supported
                            else "insufficient_vram"
                        ),
                    }
                )
        except (OSError, subprocess.SubprocessError, ValueError):
            gpu["status"] = "probe_failed"
    total_memory_bytes: int | None = None
    try:
        total_memory_bytes = int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError, TypeError):
        pass
    os_id = "unknown"
    os_version = "unknown"
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key == "ID":
                os_id = value.strip().strip('"')
            elif key == "VERSION_ID":
                os_version = value.strip().strip('"')
    except OSError:
        pass
    architecture = platform.machine().lower()
    supported_architecture = architecture in {"x86_64", "amd64"}
    cpu_only_supported = supported_architecture and not missing_cpu_features
    return {
        "operating_system": {"id": os_id, "version_id": os_version},
        "supported_ubuntu": os_id == "ubuntu" and os_version.startswith("24.04"),
        "architecture": architecture,
        "supported_architecture": supported_architecture,
        "cpu_logical_count": os.cpu_count() or 1,
        "memory_total_bytes": total_memory_bytes,
        "cpu_only_supported": cpu_only_supported,
        "minimum_cpu_features": sorted(minimum_cpu_features),
        "cpu_feature_requirements": {
            feature: feature in cpu_features for feature in sorted(minimum_cpu_features)
        },
        "missing_cpu_features": missing_cpu_features,
        "gpu": gpu,
        "neurofabric_variant": "cuda_mega" if gpu["cuda_variant_supported"] else "cpu",
        "minimum_nvidia_driver_branch": minimum_branch,
        "minimum_cuda_vram_mb": minimum_vram_mb,
        "external_fingerprinting": False,
        "network_used": False,
        "serial_numbers_returned": False,
    }


__all__ = ("DEFAULT_NEUROFABRIC_LOCK", "detect_local_hardware")
