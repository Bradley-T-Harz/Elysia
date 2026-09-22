"""Scientific compilation keeps routing, placement, and execution distinct."""
import json
import time

import pytest

from core import model_invoker, runtime
from app.cognition.compute_governor import WorkloadDescriptor, decide_compute


@pytest.mark.parametrize("gpu_available,expected", [(True, "cuda:0"), (False, "none")])
def test_hot_cpu_never_earns_cpu_fallback(isolated_account_store, gpu_available, expected):
    state = {"system": {"cpu_percent": 5, "ram_available_mb": 32000, "cpu_temperature_c": 95},
             "gpu": {"available": gpu_available, "devices": [{"memory_free_mb": 10000,
                       "temperature_c": 55, "utilization_percent": 20}] if gpu_available else []}}
    result = decide_compute(WorkloadDescriptor(
        workload_id="thermal-synthetic", owner_user_id=None, task_kind="scientific_formulation",
        estimated_vram_mb=5000, estimated_ram_mb=5000), resource_state=state)
    assert result.selected_device == expected
    assert "cpu_thermal_safety_boundary" in result.reasons


def test_model_limits_reach_provider_without_changing_model_authority(monkeypatch, safe_resource_samples):
    captured = {}
    monkeypatch.setattr(model_invoker, "_post_json", lambda url, payload, timeout_s:
                        (captured.update(payload) or {"message": {"content": "bounded"}}))
    result = model_invoker._call_ollama_chat("configured:local", "system", "science",
        stream_transport=False, num_gpu=-1, max_output_tokens=1000,
        limits=model_invoker.ModelInvocationLimits(admitted_runtime_tag="configured:local"))
    assert result["ok"]
    assert captured["options"] == {"num_gpu": -1, "num_predict": 1000,
                                  "num_ctx": 8192, "num_thread": 2, "num_batch": 64}
    assert result["execution_controls"]["cpu_threads"] == 2
    assert "tools" not in captured


@pytest.mark.parametrize("outcome,expected", [
    ({"status": "error", "provider_metadata": {"timeout": True}}, "scientific_formulation_timed_out"),
    ({"status": "error", "block_reasons": ["operator_cancelled"]}, "scientific_request_cancelled"),
    ({"status": "error", "provider_metadata": {"resource_limited": True}}, "scientific_formulation_resource_limited"),
])
def test_formulation_has_minimal_context_and_distinct_terminal_truth(monkeypatch, outcome, expected):
    captured = {}
    monkeypatch.setattr(runtime, "invoke_model", lambda **kw: (captured.update(kw) or outcome))
    result = runtime._run_model_proposed_scientific_workflow(
        message="augmented PRIVATE_CANARY", canonical_user_message="Calculate 2 plus 3",
        model_routing={"selected_runtime_tag": "configured:local"}, configs={}, mode="researcher",
        task_type="research", model_context_summary="unrelated private journal",
        context={}, cancel_check=lambda: False, selected_device="cuda:0", output_token_budget=4000,
        deadline_monotonic=time.monotonic()+60)
    assert result["reason"] == expected
    assert captured["message"] == "Calculate 2 plus 3"
    assert captured["context_summary"] == ""
    assert captured["max_output_tokens"] == 2048
    assert captured["limits"].admitted_runtime_tag == "configured:local"
    assert captured["limits"].require_gpu is True
    assert not result["used"]


@pytest.mark.parametrize("device,should_dispatch", [("cuda:0", False), ("cpu", True)])
def test_admitted_device_controls_required_telemetry_with_automatic_offload(monkeypatch, device, should_dispatch):
    from app.cognition import resource_guard
    monkeypatch.setattr(resource_guard, "sample_resources", lambda:
        resource_guard.ResourceSample(time.monotonic(), 60, None, 32000))
    dispatched = []
    def provider(*args, **kwargs):
        dispatched.append(True)
        return {"message": {"content": "{}"}}
    monkeypatch.setattr(model_invoker, "_post_json", provider)
    def invoke(**kwargs):
        outcome = model_invoker._call_ollama_chat("configured:local", "system", kwargs["message"],
            stream_transport=False, num_gpu=kwargs["num_gpu"], limits=kwargs["limits"])
        return {"status": "ok" if outcome["ok"] else "error",
                "response_text": outcome.get("response_text", ""),
                "provider_metadata": outcome.get("provider_metadata", {})}
    monkeypatch.setattr(runtime, "invoke_model", invoke)
    result = runtime._run_model_proposed_scientific_workflow(
        message="Evaluate 2 + 3", canonical_user_message="Evaluate 2 + 3",
        model_routing={"selected_runtime_tag": "configured:local"}, configs={}, mode="researcher",
        task_type="research", model_context_summary="", context={}, cancel_check=lambda: False,
        selected_device=device, output_token_budget=1000, deadline_monotonic=time.monotonic()+10)
    assert bool(dispatched) is should_dispatch
    if not should_dispatch:
        assert result["reason"] == "scientific_formulation_resource_limited"
        assert result["formulation_receipt"]["provider_metadata"]["resource_guard"]["reason"] == "gpu_telemetry_unavailable"
