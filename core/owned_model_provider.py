"""Request-owned Ollama address spaces for measured, server-configured profiles.

Model selection and compute admission stay outside this module. It cannot
choose a fallback, download a model, or stop the shared Ollama service. A
profile earns no authority unless the runtime binds it to a fresh admission.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from urllib.request import build_opener, ProxyHandler

from app.cognition.resource_guard import GuardPolicy, ResourceGuard
from app.install.paths import resolve_elysia_paths


@dataclass(frozen=True)
class OwnedModelProfile:
    profile_id: str
    runtime_tag: str
    manifest_sha256: str
    gpu_name: str
    gpu_layers: int
    context_tokens: int
    cpu_threads: int
    batch_tokens: int
    cpu_affinity: tuple[int, ...]
    run_fraction: float
    ram_mb: int
    vram_mb: int
    maximum_gpu_used_mb: int
    wall_seconds: float
    provider_version: str = "0.18.0"

    def __post_init__(self):
        if not (re.fullmatch(r"[a-z0-9_:-]{1,80}", self.profile_id)
                and re.fullmatch(r"[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+", self.runtime_tag)
                and re.fullmatch(r"[a-f0-9]{64}", self.manifest_sha256)
                and 1 <= self.gpu_layers <= 256 and 2048 <= self.context_tokens <= 32768
                and 1 <= self.cpu_threads <= 8 and 16 <= self.batch_tokens <= 256
                and 1 <= len(self.cpu_affinity) <= 8
                and all(type(i) is int and 0 <= i <= 4095 for i in self.cpu_affinity)
                and .1 <= self.run_fraction <= 1 and 1 <= self.wall_seconds <= 300
                and 512 <= self.ram_mb <= 131072 and 512 <= self.vram_mb <= 131072
                and self.vram_mb < self.maximum_gpu_used_mb <= 131072):
            raise ValueError("invalid_owned_model_profile")

    def estimate(self, original):
        return {**original, "estimated_ram_mb": self.ram_mb,
                "estimated_vram_mb": self.vram_mb, "incremental_vram_mb": self.vram_mb,
                "measurement_source": "qualified_owned_profile:" + self.profile_id}


def qualified_profile(configs, tag, inventory, resource_state):
    """Exact model/hardware match only; unknown machines retain existing paths."""
    entries = configs.get("models", {}).get("execution_profiles", {}).get("profiles", [])
    model = next((m for m in inventory.get("models", []) if m.get("runtime_tag") == tag), {})
    devices = resource_state.get("gpu", {}).get("devices", [])
    for entry in entries:
        if entry.get("runtime_tag") != tag:
            continue
        profile = OwnedModelProfile(**{**entry, "cpu_affinity": tuple(entry["cpu_affinity"])})
        if (str(model.get("digest", "")).removeprefix("sha256:") == profile.manifest_sha256
                and devices and devices[0].get("name") == profile.gpu_name
                and hasattr(os, "sched_getaffinity")
                and set(profile.cpu_affinity) <= os.sched_getaffinity(0)):
            return profile
    return None


class OwnedProviderError(RuntimeError):
    pass


class OwnedModelProvider:
    """Own only a private provider process group; kill it at every terminal path."""
    def __init__(self, profile, *, timeout_s, cancel_check=None):
        self.profile = profile
        self.deadline = time.monotonic() + min(timeout_s, profile.wall_seconds)
        self.cancel_check = cancel_check
        self.process = None
        self.reason = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._temp = None
        self._log = None
        self.url = None
        self.guard = ResourceGuard(self.abort, policy=GuardPolicy(
            require_gpu=True, maximum_gpu_used_mb=profile.maximum_gpu_used_mb))
        self.receipt = {"profile_id": profile.profile_id, "provider_owned": True,
                        "manifest_sha256": profile.manifest_sha256,
                        "hard_cpu_percentage_enforced": False,
                        "process_group_run_fraction": profile.run_fraction,
                        "cpu_affinity": list(profile.cpu_affinity),
                        "provider_compute_stop_verified": False}

    def abort(self, reason):
        with self._lock:
            if self.reason is None:
                self.reason = reason
            if self.process is not None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def check(self):
        if self.cancel_check and self.cancel_check():
            self.abort("operator_cancelled")
        elif time.monotonic() >= self.deadline:
            self.abort("owned_provider_wall_deadline")
        if self.reason:
            raise OwnedProviderError(self.reason)

    def _watch(self):
        paused = False
        while not self._stop.wait(.01):
            try:
                self.check()
                if self._log and os.fstat(self._log.fileno()).st_size > 4 * 1024 * 1024:
                    self.abort("owned_provider_log_limit")
                with self._lock:
                    if self.process is not None:
                        want = time.monotonic() % .2 >= .2 * self.profile.run_fraction
                        if want != paused:
                            try:
                                os.killpg(self.process.pid, signal.SIGSTOP if want else signal.SIGCONT)
                            except ProcessLookupError:
                                pass
                            paused = want
            except OwnedProviderError:
                return

    def _stage_model(self, root):
        name, tag = self.profile.runtime_tag.split(":", 1)
        rel = Path("manifests/registry.ollama.ai/library") / name / tag
        # Discovery is local server policy, never a request/model-supplied path.
        candidates = [Path.home() / ".ollama/models", Path("/usr/share/ollama/.ollama/models")]
        if os.environ.get("OLLAMA_MODELS"):
            candidates.insert(0, Path(os.environ["OLLAMA_MODELS"]))
        source = None
        for candidate in candidates:
            path = candidate / rel
            if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() == self.profile.manifest_sha256:
                    source = candidate.resolve()
                    break
        if source is None:
            raise OwnedProviderError("qualified_model_manifest_not_found")
        manifest = json.loads(raw)
        layers = [manifest["config"], *manifest["layers"]]
        if not 1 <= len(layers) <= 64:
            raise OwnedProviderError("invalid_model_manifest")
        models = root / "models"
        (models / rel).parent.mkdir(parents=True)
        (models / rel).write_bytes(raw)
        (models / "blobs").mkdir()
        for layer in layers:
            digest = layer["digest"]
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise OwnedProviderError("invalid_model_blob_digest")
            path = source / "blobs" / digest.replace(":", "-")
            if (path.is_symlink() or not path.is_file() or path.stat().st_size != layer["size"]):
                raise OwnedProviderError("model_blob_unavailable")
            target = models / "blobs" / path.name
            if not target.exists():
                target.symlink_to(path)
        return models

    def _owns_listener(self, port):
        """An ephemeral loopback port is not authority without PID ownership."""
        if self.process is None:
            return False
        try:
            sockets = {os.readlink(fd) for fd in Path(f"/proc/{self.process.pid}/fd").iterdir()}
            for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
                fields = line.split()
                if (fields[1] == f"0100007F:{port:04X}" and fields[3] == "0A"
                        and f"socket:[{fields[9]}]" in sockets):
                    return True
        except OSError:
            return False
        return False

    def __enter__(self):
        try:
            self.check()
            if not self.guard.start(wait_check=self.check):
                self.check()
                raise OwnedProviderError("owned_provider_resource_refused")
            binary = shutil.which("ollama")
            if binary is None or not hasattr(os, "sched_getaffinity"):
                raise OwnedProviderError("owned_provider_runtime_unavailable")
            base = resolve_elysia_paths().runtime_dir
            base.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._temp = tempfile.TemporaryDirectory(prefix="owned-model-", dir=base)
            root = Path(self._temp.name)
            models = self._stage_model(root)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            self.url = f"http://127.0.0.1:{port}"
            environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(root), "TMPDIR": str(root), "LANG": "C.UTF-8",
                "OLLAMA_HOST": f"127.0.0.1:{port}", "OLLAMA_MODELS": str(models),
                "OLLAMA_NOPRUNE": "true", "OLLAMA_NO_CLOUD": "true",
                "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1",
                "OLLAMA_KEEP_ALIVE": "0", "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1", "GOMAXPROCS": "2"}
            # CUDA's compiled-kernel cache contains no user prompts. Persist it
            # in the private app cache rather than recompiling for every request.
            cache = resolve_elysia_paths().cache_dir / "owned-model-kernels"
            cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            environment["CUDA_CACHE_PATH"] = str(cache)
            self._log = (root / "provider.log").open("w")
            affinity = ",".join(map(str, self.profile.cpu_affinity))
            with self._lock:
                self.check()
                self.process = subprocess.Popen(["taskset", "-c", affinity, binary, "serve"],
                    env=environment, stdin=subprocess.DEVNULL, stdout=self._log,
                    stderr=subprocess.STDOUT, start_new_session=True)
            self.receipt["provider_pid"] = self.process.pid
            self._thread = threading.Thread(target=self._watch, daemon=True, name="elysia-owned-model")
            self._thread.start()
            opener = build_opener(ProxyHandler({}))
            ready_until = min(self.deadline, time.monotonic() + 10)
            while time.monotonic() < ready_until:
                self.check()
                if self.process.poll() is not None:
                    raise OwnedProviderError("owned_provider_exited")
                if not self._owns_listener(port):
                    self._stop.wait(.05)
                    continue
                try:
                    with opener.open(self.url + "/api/version", timeout=.2) as response:
                        self.receipt["provider_version"] = json.loads(response.read(4096))["version"]
                    if self.receipt["provider_version"] != self.profile.provider_version:
                        raise OwnedProviderError("owned_provider_version_not_qualified")
                    return self
                except OSError:
                    self._stop.wait(.05)
            raise OwnedProviderError("owned_provider_startup_deadline")
        except BaseException:
            self.close()
            raise

    def close(self):
        self._stop.set()
        self.abort("owned_scope_finished")
        if self._thread:
            self._thread.join(timeout=1)
        if self.process is not None:
            self.process.wait(timeout=3)
            # No active member of this uniquely owned process group may remain.
            cleanup_deadline = time.monotonic() + 3
            while True:
                remaining = []
                for stat in Path("/proc").glob("[0-9]*/stat"):
                    try:
                        values = stat.read_text().rsplit(") ", 1)[1].split()
                        if int(values[2]) == self.process.pid and values[0] not in {"Z", "X"}:
                            remaining.append(int(stat.parent.name))
                    except (OSError, ValueError, IndexError):
                        pass
                if not remaining or time.monotonic() >= cleanup_deadline:
                    break
                time.sleep(.02)
            self.receipt.update(provider_exit_code=self.process.returncode,
                provider_compute_stop_verified=not remaining, remaining_active_pids=remaining)
            with self._lock:
                self.process = None
        self.guard.close()
        self.receipt.update(termination_reason=self.reason, resource_guard=self.guard.receipt())
        if self._log:
            self._log.flush()
            # Preserve bounded diagnostic bytes locally, outside model/UI data.
            # The receipt exposes only their hash, never a filesystem path.
            try:
                data = Path(self._log.name).read_bytes()[:4 * 1024 * 1024]
                digest = hashlib.sha256(data).hexdigest()
                from app.api.account_service import get_active_elysia_paths
                logs = get_active_elysia_paths().log_dir / "owned-model-providers"
                logs.mkdir(mode=0o700, parents=True, exist_ok=True)
                target = logs / (digest + ".log")
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                self.receipt["provider_log_sha256"] = digest
            except (OSError, RuntimeError):
                self.receipt["provider_log_preservation"] = "unavailable"
            self._log.close()
            self._log = None
        if self._temp:
            self._temp.cleanup()
            self._temp = None

    def __exit__(self, *_):
        self.close()
