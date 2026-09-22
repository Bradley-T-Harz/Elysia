"""Per-attempt authority must survive cancellation, failure and nesting."""
import threading

import pytest

from core import model_invoker as invoker
from core.model_compute_scope import current_admission, model_compute_scope
from tests.test_model_invoker import base_configs, prompt_environment, routing_decision


@pytest.mark.parametrize("late", ["cancel", "deadline"])
def test_admission_cannot_dispatch_after_parent_becomes_terminal(
    monkeypatch, base_configs, prompt_environment, routing_decision, late,
):
    cancelled = threading.Event()
    now = [100.0]
    monkeypatch.setattr(invoker.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(invoker, "_list_ollama_models", lambda **_kw: ["qwen3:8b"])
    calls = []
    monkeypatch.setattr(invoker, "_call_ollama_chat", lambda **kw:
        (calls.append(kw) or {"ok": True, "response_text": "LATE_INVALID_SUCCESS"}))

    def prepare(_tag):
        if late == "cancel":cancelled.set()
        else:now[0] = 111.0
        return 0

    with model_compute_scope(prepare):
        result = invoker.invoke_model("hello", routing_decision, base_configs,
                                      timeout_s=10, cancel_check=cancelled.is_set)
    assert calls == []
    assert result["status"] != "ok"
    assert ("operator_cancelled" if late == "cancel" else "local_invocation_deadline_exceeded") in result["block_reasons"]
    assert current_admission() is None


def test_scope_nesting_and_exception_do_not_leak_admission():
    first = lambda _tag: 0
    second = lambda _tag: None
    with model_compute_scope(first):
        with pytest.raises(RuntimeError, match="synthetic"):
            with model_compute_scope(second):
                assert current_admission() is second
                raise RuntimeError("synthetic")
        assert current_admission() is first
    assert current_admission() is None


@pytest.mark.parametrize("late", ["cancel", "deadline"])
def test_late_provider_success_does_not_revive_terminal_parent(
    monkeypatch, base_configs, prompt_environment, routing_decision, late,
):
    cancelled = threading.Event()
    now = [100.0]
    monkeypatch.setattr(invoker.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(invoker, "_list_ollama_models", lambda **_kw: ["qwen3:8b"])
    def provider(**_kwargs):
        if late == "cancel":cancelled.set()
        else:now[0] = 111.0
        return {"ok": True, "response_text": "LATE_INVALID_SUCCESS"}
    monkeypatch.setattr(invoker, "_call_ollama_chat", provider)
    with model_compute_scope(lambda _tag: 0):
        result = invoker.invoke_model("hello", routing_decision, base_configs,
                                      timeout_s=10, cancel_check=cancelled.is_set)
    assert result["status"] != "ok"
    assert not result["response_text"]
    assert ("operator_cancelled" if late == "cancel" else "local_invocation_deadline_exceeded") in result["block_reasons"]
    assert current_admission() is None
