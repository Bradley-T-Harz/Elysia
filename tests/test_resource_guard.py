"""Safety is proved with controlled telemetry, never deliberate overheating."""
import socket
import threading
import time

import pytest

from app.cognition.resource_guard import GuardPolicy, ResourceGuard, ResourceSample
from core.codev.provider_transport import ProviderControl, ProviderResourceLimited, ProviderCancelled


def sample(cpu=60, gpu=50, age=0, ram=32000):
    return ResourceSample(time.monotonic()-age, cpu, gpu, ram)


@pytest.mark.parametrize("reading,reason", [
    (lambda: sample(cpu=90), "cpu_thermal_cutoff"),
    (lambda: sample(gpu=85), "gpu_thermal_cutoff"),
    (lambda: sample(age=5), "resource_telemetry_stale"),
    (lambda: sample(cpu=None), "cpu_telemetry_unavailable"),
    (lambda: sample(cpu=float('nan')), "cpu_telemetry_unavailable"),
    (lambda: sample(gpu=None), "gpu_telemetry_unavailable"),
    (lambda: sample(ram=512), "ram_safety_reserve"),
])
def test_single_unsafe_sample_refuses_dispatch(reading, reason):
    trips = []
    guard = ResourceGuard(trips.append, policy=GuardPolicy(require_gpu=True), sampler=reading)
    try:
        assert not guard.start()
        assert guard.reason == reason
        assert trips == [reason]
    finally:
        guard.close()


def test_stalled_sampling_cannot_stall_active_watchdog():
    release = threading.Event()
    tripped = threading.Event()
    calls = 0
    def reader():
        nonlocal calls
        calls += 1
        if calls > 1:
            release.wait(2)
        return sample()
    guard = ResourceGuard(lambda reason: tripped.set(), sampler=reader,
                          policy=GuardPolicy(stale_after_s=.15, sample_interval_s=.01))
    try:
        assert guard.start()
        assert tripped.wait(.5)
        assert guard.reason == "resource_telemetry_stale"
    finally:
        release.set()
        guard.close()


def test_one_high_sample_closes_owned_blocked_socket_and_does_not_recover_in_place():
    local, peer = socket.socketpair()
    unrelated, unrelated_peer = socket.socketpair()
    control = ProviderControl(5, lambda: False)
    control.attach(local)
    readings = iter([60, 91, 60])
    guard = ResourceGuard(lambda reason: control.abort("resource_limited"),
                          policy=GuardPolicy(sample_interval_s=.01),
                          sampler=lambda: sample(cpu=next(readings, 60)))
    try:
        assert guard.start()
        local.settimeout(.5)
        assert local.recv(1) == b""
        assert guard.reason == "cpu_thermal_cutoff"
        with pytest.raises(ProviderResourceLimited):
            control.check()
        unrelated_peer.send(b"x")
        assert unrelated.recv(1) == b"x"
        time.sleep(.02)
        assert guard.reason == "cpu_thermal_cutoff"
    finally:
        guard.close(); control.close(); peer.close(); unrelated.close(); unrelated_peer.close()


def test_parent_cancellation_remains_authoritative_over_resource_race():
    event = threading.Event()
    control = ProviderControl(.01, event.is_set)
    try:
        control.abort("resource_limited")
        event.set()
        with pytest.raises(ProviderCancelled):
            control.check()
        assert control.reason == "cancelled"
    finally:
        control.close()


@pytest.mark.parametrize("used,reason", [(None, "gpu_memory_telemetry_unavailable"),
                                          (14000, "gpu_memory_safety_boundary")])
def test_active_vram_boundary(used, reason):
    guard = ResourceGuard(lambda reason: None, policy=GuardPolicy(maximum_gpu_used_mb=14000),
                          sampler=lambda: ResourceSample(time.monotonic(), 60, 50, 32000, used))
    try:
        assert not guard.start()
        assert guard.reason == reason
    finally:
        guard.close()


def test_initial_stalled_telemetry_obeys_shorter_parent_deadline():
    release = threading.Event()
    control = ProviderControl(.05, lambda: False)
    def blocked_sample():
        release.wait(1)
        return sample()
    guard = ResourceGuard(lambda reason: control.abort("resource_limited"),
                          sampler=blocked_sample)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            guard.start(wait_check=control.check)
        assert time.monotonic()-started < .3
    finally:
        release.set(); guard.close(); control.close()


def test_model_resource_cutoff_is_distinct_and_prevents_provider_call(monkeypatch):
    from app.cognition import resource_guard
    from core import model_invoker
    monkeypatch.setattr(resource_guard, "sample_resources", lambda: sample(cpu=95))
    calls = []
    monkeypatch.setattr(model_invoker, "_post_json", lambda *a, **k: calls.append(a))
    outcome = model_invoker._call_ollama_chat("local", "system", "request", stream_transport=False,
                                            limits=model_invoker.ModelInvocationLimits())
    assert calls == []
    assert not outcome["ok"]
    assert outcome["provider_metadata"]["resource_limited"]
    assert outcome["provider_metadata"]["resource_guard"]["reason"] == "cpu_thermal_cutoff"
    assert not outcome.get("cancelled")


def test_model_safety_cutoff_prevents_unadmitted_fallback(monkeypatch, isolated_account_store):
    from core import model_invoker
    from core.config_loader import load_all_configs
    from core.model_routing import build_model_routing_decision
    configs = load_all_configs()
    decision = build_model_routing_decision(configs=configs, mode="default", task_type="conversation", autonomy_level=1)
    monkeypatch.setattr(model_invoker, "_list_ollama_models", lambda **k: None)
    attempts = []
    def provider(**kwargs):
        attempts.append(kwargs["runtime_tag"])
        return {"ok": False, "error": "safety cutoff", "provider_metadata": {"resource_limited": True}}
    monkeypatch.setattr(model_invoker, "_call_ollama_chat", provider)
    result = model_invoker.invoke_model("Hello", decision, configs)
    assert len(attempts) == 1
    assert "local_resource_safety_cutoff" in result["block_reasons"]


def test_worker_thermal_cutoff_kills_real_owned_process(monkeypatch, tmp_path):
    import os
    import sys
    from app.api import scientificforge_process_service as process_service
    from app.cognition import resource_guard
    pidfile = tmp_path / "owned-pid"
    monkeypatch.setattr(resource_guard, "sample_resources", lambda: sample(cpu=91 if pidfile.exists() else 60))
    def run(job, **kwargs):
        _, _, _, failure = process_service._bounded_process(
            [sys.executable, "-c", "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(20)", str(pidfile)],
            cwd=tmp_path, environment=process_service._minimal_environment(tmp_path),
            cancel_event=kwargs["cancel_event"], timeout_seconds=10)
        return {"status": "cancelled", "blocked_reason": failure}
    monkeypatch.setattr(process_service, "_run_scientific_worker_process", run)
    started = time.monotonic()
    result = process_service.run_scientific_worker_process({})
    assert time.monotonic()-started < 2
    assert result["status"] == "failed" and result["blocked_reason"] == "worker_resource_limited"
    assert result["resource_guard"]["reason"] == "cpu_thermal_cutoff"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_worker_hot_preflight_launches_nothing(monkeypatch):
    from app.api import scientificforge_process_service as process_service
    from app.cognition import resource_guard
    monkeypatch.setattr(resource_guard, "sample_resources", lambda: sample(cpu=92))
    calls = []
    monkeypatch.setattr(process_service, "_run_scientific_worker_process", lambda *a, **k: calls.append(a))
    result = process_service.run_scientific_worker_process({})
    assert not calls
    assert result["blocked_reason"] == "worker_resource_limited"


@pytest.mark.parametrize("error", [OSError("transport interrupted"), ValueError("late malformed output")])
def test_parent_cancellation_outranks_concurrent_provider_error(monkeypatch, safe_resource_samples, error):
    from core import model_invoker
    from core.codev.provider_transport import active_provider_control
    event = threading.Event()
    def provider(*args, **kwargs):
        active_provider_control().abort("resource_limited")
        event.set()
        raise error
    monkeypatch.setattr(model_invoker, "_post_json", provider)
    result = model_invoker._call_ollama_chat("local", "system", "request", stream_transport=False,
        limits=model_invoker.ModelInvocationLimits(), cancel_check=event.is_set)
    assert result["cancelled"] is True
    assert result["error"] == "operator_cancelled"
    assert not result["provider_metadata"].get("resource_limited")


@pytest.mark.parametrize("field,value,reason", [
    ("cpu_c", "unknown", "cpu_telemetry_unavailable"),
    ("gpu_c", float("nan"), "gpu_telemetry_unavailable"),
    ("ram_available_mb", float("nan"), "ram_telemetry_unavailable"),
    ("ram_available_mb", "unknown", "ram_telemetry_unavailable"),
    ("gpu_used_mb", float("inf"), "gpu_memory_telemetry_unavailable"),
    ("gpu_used_mb", True, "gpu_memory_telemetry_unavailable"),
])
def test_malformed_resource_readings_fail_closed(field, value, reason):
    from dataclasses import replace
    guard = ResourceGuard(lambda _: None,
        policy=GuardPolicy(maximum_gpu_used_mb=14000, stale_after_s=.2, sample_interval_s=.01),
        sampler=lambda: replace(ResourceSample(time.monotonic(), 60, 50, 32000, 2000), **{field: value}))
    try:
        assert guard.start() is False
        assert guard.reason == reason
    finally:
        guard.close()


def test_rejected_admission_never_races_pending_socket_abort(monkeypatch):
    from app.cognition import resource_guard
    from core import model_invoker
    class RejectedGuard:
        def __init__(self, *args, **kwargs): pass
        def start(self, **kwargs): return False
        def receipt(self): return {"reason": "cpu_thermal_cutoff"}
        def close(self): pass
    monkeypatch.setattr(resource_guard, "ResourceGuard", RejectedGuard)
    calls = []
    def provider(*args, **kwargs):
        calls.append(args)
        return {"message": {"content": "should never execute"}}
    monkeypatch.setattr(model_invoker, "_post_json", provider)
    result = model_invoker._call_ollama_chat("local", "system", "request", stream_transport=False,
        limits=model_invoker.ModelInvocationLimits())
    assert calls == []
    assert result["provider_metadata"]["resource_limited"] is True
