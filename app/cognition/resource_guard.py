"""Request-owned active safety supervision, independent of provider/worker reads.

Admission estimates are not thermal enforcement. A single critical sample trips
this guard. Sampling is separate from the watchdog so a stalled telemetry tool
cannot suspend cancellation. This is polling protection, not a hardware limiter.
"""
from dataclasses import asdict, dataclass
import math
import threading
import time
from typing import Callable


def _finite_reading(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class ResourceSample:
    monotonic_s: float
    cpu_c: float | None
    gpu_c: float | None
    ram_available_mb: int | None
    gpu_used_mb: int | None = None


@dataclass(frozen=True)
class GuardPolicy:
    cpu_cutoff_c: float = 90.0
    gpu_cutoff_c: float = 85.0
    minimum_ram_mb: int = 1024
    stale_after_s: float = 3.0
    sample_interval_s: float = 0.25
    require_gpu: bool = False
    maximum_gpu_used_mb: int | None = None

    def __post_init__(self):
        if not (0 < self.cpu_cutoff_c <= 90 and 0 < self.gpu_cutoff_c <= 85
                and self.minimum_ram_mb >= 0 and 0 < self.stale_after_s <= 3
                and 0 < self.sample_interval_s <= self.stale_after_s):
            raise ValueError("invalid_resource_guard_policy")
        if self.maximum_gpu_used_mb is not None and (not _finite_reading(self.maximum_gpu_used_mb)
                                                    or self.maximum_gpu_used_mb <= 0):
            raise ValueError("invalid_gpu_memory_boundary")


def sample_resources() -> ResourceSample:
    from app.cognition.compute_governor import _system_metrics, _gpu_metrics
    # Timestamp the start, not the end: a slow sample is not fresh telemetry.
    captured = time.monotonic()
    system = _system_metrics()
    gpu = _gpu_metrics()
    return ResourceSample(captured, system.get("cpu_temperature_c"),
                          max((d["temperature_c"] for d in gpu.get("devices", [])), default=None),
                          system.get("ram_available_mb"),
                          max((d["memory_used_mb"] for d in gpu.get("devices", [])), default=None))


class ResourceGuard:
    def __init__(self, on_trip: Callable[[str], None], *, policy: GuardPolicy | None = None,
                 sampler: Callable[[], ResourceSample] | None = None):
        self.policy = policy or GuardPolicy()
        self._sampler = sampler or sample_resources
        self._on_trip = on_trip
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._sample = None
        self._reason = None
        self._threads = []
        self._started = time.monotonic()
        self._peaks = {"cpu_c": None, "gpu_c": None, "gpu_used_mb": None}
        self._samples = 0

    @property
    def reason(self):
        with self._lock:
            return self._reason

    def _trip(self, reason):
        with self._lock:
            if self._reason or self._stop.is_set():
                return
            self._reason = reason
        self._ready.set()
        self._on_trip(reason)

    def _sample_loop(self):
        while not self._stop.is_set():
            try:
                value = self._sampler()
                if not isinstance(value, ResourceSample):
                    raise ValueError("invalid_resource_telemetry")
            except Exception:
                self._trip("resource_telemetry_unavailable")
                return
            if self._stop.is_set():
                return
            with self._lock:
                self._sample = value
                self._samples += 1
                for name in self._peaks:
                    reading = getattr(value, name)
                    if _finite_reading(reading):
                        self._peaks[name] = max(reading, self._peaks[name] or reading)
            # Inspect EACH sample, including one high reading followed by cool.
            self._inspect(value)
            self._ready.set()
            if self.reason or self._stop.wait(self.policy.sample_interval_s):
                return

    def _inspect(self, sample):
        now = time.monotonic()
        if sample is None:
            if now - self._started >= self.policy.stale_after_s:
                self._trip("resource_telemetry_stale")
            return
        if not _finite_reading(sample.monotonic_s) or not 0 <= now - sample.monotonic_s < self.policy.stale_after_s:
            self._trip("resource_telemetry_stale")
        elif not _finite_reading(sample.cpu_c):
            self._trip("cpu_telemetry_unavailable")
        elif sample.cpu_c >= self.policy.cpu_cutoff_c:
            self._trip("cpu_thermal_cutoff")
        elif (self.policy.require_gpu or sample.gpu_c is not None) and not _finite_reading(sample.gpu_c):
            self._trip("gpu_telemetry_unavailable")
        elif sample.gpu_c is not None and sample.gpu_c >= self.policy.gpu_cutoff_c:
            self._trip("gpu_thermal_cutoff")
        elif not _finite_reading(sample.ram_available_mb):
            self._trip("ram_telemetry_unavailable")
        elif sample.ram_available_mb < self.policy.minimum_ram_mb:
            self._trip("ram_safety_reserve")
        elif self.policy.maximum_gpu_used_mb is not None:
            if not _finite_reading(sample.gpu_used_mb):
                self._trip("gpu_memory_telemetry_unavailable")
            elif sample.gpu_used_mb >= self.policy.maximum_gpu_used_mb:
                self._trip("gpu_memory_safety_boundary")

    def _watch(self):
        while not self._stop.wait(min(0.05, self.policy.sample_interval_s)):
            with self._lock:
                sample = self._sample
            self._inspect(sample)
            if self.reason:
                return

    def start(self, *, wait_check: Callable[[], None] | None = None) -> bool:
        for target in (self._watch, self._sample_loop):
            thread = threading.Thread(target=target, name="elysia-resource-guard", daemon=True)
            self._threads.append(thread)
            thread.start()
        until = time.monotonic() + self.policy.stale_after_s + 0.1
        while not self._ready.wait(.02) and time.monotonic() < until:
            if wait_check:
                wait_check()
        if not self._ready.is_set():
            self._trip("resource_telemetry_stale")
        return self.reason is None

    def receipt(self):
        with self._lock:
            return {"reason": self._reason, "samples": self._samples, "peaks": dict(self._peaks),
                    "policy": asdict(self.policy), "enforcement": "owned_work_cancellation_on_polled_limits",
                    "hard_cpu_percentage_enforced": False}

    def close(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=0.1)
