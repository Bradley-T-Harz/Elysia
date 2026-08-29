from __future__ import annotations

from copy import deepcopy

import pytest

from core import model_invoker as invoker
from core.responder import compose_response


@pytest.fixture
def base_configs():
    return {
        "models": {
            "model_roles": {
                "roles": {
                    "primary_general": {
                        "preferred_model": "qwen3:8b",
                        "preferred_model_runtime_tag": "qwen3:8b",
                        "fallback_models": ["llama3.1:8b"],
                        "fallback_model_runtime_tags": ["llama3.1:8b"],
                    },
                    "lighter_backup": {
                        "preferred_model": "phi4-mini",
                        "preferred_model_runtime_tag": "phi4-mini",
                    },
                },
                "external_helpers": {},
            }
        }
    }


@pytest.fixture
def prompt_environment(tmp_path, monkeypatch):
    project_root = tmp_path
    runtime_dir = project_root / "derived" / "runtime"
    runtime_dir.mkdir(parents=True)

    prompt_paths = {
        "primary_general": runtime_dir / "elysia_general_system.txt",
        "lighter_backup": runtime_dir / "elysia_light_system.txt",
    }

    for role_name, path in prompt_paths.items():
        path.write_text(f"System prompt for {role_name}", encoding="utf-8")

    monkeypatch.setattr(invoker, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(invoker, "DERIVED_RUNTIME_ROOT", runtime_dir)
    monkeypatch.setattr(invoker, "ROLE_PROMPT_PATHS", prompt_paths)

    return {
        "project_root": project_root,
        "runtime_dir": runtime_dir,
        "prompt_paths": prompt_paths,
    }


@pytest.fixture
def routing_decision():
    return {
        "allowed": True,
        "stayed_local": True,
        "selected_role": "primary_general",
        "selected_role_container": "roles",
        "selected_target": "qwen3:8b",
        "selected_model": "qwen3:8b",
        "selected_runtime": "ollama",
        "selected_service": "ollama",
        "selected_is_external": False,
        "route_block_reasons": [],
        "unmet_requirements": [],
    }


def _base_plan(**overrides):
    plan = {
        "intent": "conversation",
        "mode": "companion",
        "uses_memory_context": False,
        "memory_context_source": "",
        "memory_class": "working_memory",
        "memory_class_source": "primary_memory_class",
        "forced_memory_class": "",
        "memory_class_boundary_sensitive": False,
        "memory_class_requires_boundary_check": False,
    }
    plan.update(overrides)
    return plan


def _base_policy_review(**overrides):
    policy_review = {
        "allowed": False,
        "boundary_flags": [],
    }
    policy_review.update(overrides)
    return policy_review


def _base_verification(**overrides):
    verification = {
        "verified": True,
    }
    verification.update(overrides)
    return verification


def _base_internal_result(**overrides):
    internal_result = {
        "status": "ok",
        "response_text": "Here is a careful local answer.",
        "note": "Local invocation succeeded.",
        "error": "",
        "selected_role": "primary_general",
        "selected_runtime": "ollama",
        "selected_model_runtime_tag": "qwen3:8b",
        "used_fallback": False,
        "fallback_from": "",
        "fallback_to": "",
    }
    internal_result.update(overrides)
    return internal_result


def test_live_invoker_output_passes_through_and_preserves_render_fields():
    result = compose_response(
        "Hello there",
        _base_plan(),
        _base_policy_review(),
        _base_verification(),
        internal_result=_base_internal_result(
            response_text="This is the live local answer.",
            note="Invocation succeeded cleanly.",
        ),
        model_routing={"selected_role": "primary_general"},
    )

    assert result["status"] == "response_composed"
    assert result["response_source"] == "live_invoker"
    assert result["invocation_status"] == "ok"
    assert result["response_text"] == "This is the live local answer."
    assert result["selected_model_role"] == "primary_general"
    assert result["selected_runtime"] == "ollama"
    assert result["selected_model_runtime_tag"] == "qwen3:8b"
    assert result["used_fallback"] is False
    assert result["fallback_from"] == ""
    assert result["fallback_to"] == ""
    assert result["invocation_note"] == "Invocation succeeded cleanly."
    assert (
        "Live local model generation succeeded through the governed invoker. "
        "Tool, network, and mutation authority remains independently governed by "
        "the effective profile, approvals, and capability adapters."
        in result["caveats"]
    )


def test_ok_invoker_without_usable_text_falls_back_to_scaffold_response():
    result = compose_response(
        "Please help me think this through.",
        _base_plan(memory_class="conversation_memory"),
        _base_policy_review(),
        _base_verification(),
        internal_result=_base_internal_result(
            response_text="   ",
            note="Invocation returned no usable text.",
        ),
        model_routing={"selected_role": "primary_general"},
    )

    assert result["status"] == "response_composed"
    assert result["response_source"] == "scaffold_fallback"
    assert result["invocation_status"] == "ok"
    assert "A bounded scaffold response path was used." in result["response_text"]
    assert (
        "The current scaffold selected memory class 'conversation_memory' from 'primary_memory_class'."
        in result["response_text"]
    )


def test_blocked_invoker_uses_scaffold_fallback_and_surfaces_block_caveat():
    result = compose_response(
        "Handle this carefully.",
        _base_plan(),
        _base_policy_review(allowed=False),
        _base_verification(),
        internal_result=_base_internal_result(
            status="blocked",
            response_text="",
            note="Invocation blocked by routed path.",
        ),
        model_routing={"selected_role": "primary_general"},
    )

    assert result["status"] == "response_composed"
    assert result["response_source"] == "scaffold_fallback"
    assert result["invocation_status"] == "blocked"
    assert "A bounded scaffold response path was used." in result["response_text"]
    assert (
        "Tool or side-effect authority was not granted for this response; no such "
        "operation was implied by model generation."
        in result["caveats"]
    )
    assert (
        "Live local invocation was blocked by the current routed path or boundary rules."
        in result["caveats"]
    )


def test_error_invoker_uses_scaffold_fallback_and_surfaces_error_caveats():
    result = compose_response(
        "Please respond.",
        _base_plan(),
        _base_policy_review(allowed=False),
        _base_verification(),
        internal_result=_base_internal_result(
            status="error",
            response_text="",
            error="Primary model timed out.",
            note="Local invocation failed.",
        ),
        model_routing={"selected_role": "primary_general"},
    )

    assert result["status"] == "response_composed"
    assert result["response_source"] == "scaffold_fallback"
    assert result["invocation_status"] == "error"
    assert "A bounded scaffold response path was used." in result["response_text"]
    assert (
        "Live local invocation failed, so a governed deterministic fallback response was returned."
        in result["caveats"]
    )
    assert "Invocation reported an internal error state." in result["caveats"]


def test_successful_local_fallback_keeps_live_output_and_surfaces_fallback_truth():
    result = compose_response(
        "Give me the answer plainly.",
        _base_plan(),
        _base_policy_review(),
        _base_verification(),
        internal_result=_base_internal_result(
            response_text="Fallback recovered cleanly.",
            used_fallback=True,
            fallback_from="qwen3:8b",
            fallback_to="llama3.1:8b",
            selected_model_runtime_tag="llama3.1:8b",
            note="Fallback invocation succeeded.",
        ),
        model_routing={"selected_role": "primary_general"},
    )

    assert result["status"] == "response_composed"
    assert result["response_source"] == "live_invoker"
    assert result["response_text"] == "Fallback recovered cleanly."
    assert result["used_fallback"] is True
    assert result["fallback_from"] == "qwen3:8b"
    assert result["fallback_to"] == "llama3.1:8b"
    assert result["selected_model_runtime_tag"] == "llama3.1:8b"
    assert (
        "An allowed local fallback model was used instead of the preferred runtime tag."
        in result["caveats"]
    )


def test_live_invoker_latexish_output_is_normalized_by_default():
    result = compose_response(
        "Please explain the equation carefully.",
        _base_plan(),
        _base_policy_review(),
        _base_verification(),
        internal_result=_base_internal_result(
            response_text=r"\(x\)=\frac{a}{b}\cdot y $$",
        ),
        model_routing={"selected_role": "primary_general"},
    )

    assert result["response_source"] == "live_invoker"
    assert r"\(" not in result["response_text"]
    assert r"\)" not in result["response_text"]
    assert r"\frac" not in result["response_text"]
    assert "$$" not in result["response_text"]
    assert "(a) / (b)" in result["response_text"]
    assert "*" in result["response_text"]


def test_explicit_latex_request_preserves_latexish_output():
    latex_text = r"\(x\)=\frac{a}{b}\cdot y $$"

    result = compose_response(
        "Please write it in LaTeX.",
        _base_plan(),
        _base_policy_review(),
        _base_verification(),
        internal_result=_base_internal_result(
            response_text=latex_text,
        ),
        model_routing={"selected_role": "primary_general"},
    )

    assert result["response_source"] == "live_invoker"
    assert result["response_text"] == latex_text


def test_live_invocation_preserves_memory_boundary_and_verification_caveats():
    result = compose_response(
        "Handle this with care.",
        _base_plan(
            uses_memory_context=True,
            memory_context_source="local_session_journal_scaffold",
            memory_class="working_memory",
            memory_class_source="forced_memory_class",
            forced_memory_class="working_memory",
            memory_class_boundary_sensitive=True,
            memory_class_requires_boundary_check=True,
        ),
        _base_policy_review(
            allowed=True,
            boundary_flags=["local_session_memory"],
        ),
        _base_verification(verified=False),
        internal_result=_base_internal_result(
            response_text="Here is the careful live answer.",
        ),
        model_routing={"selected_role": "primary_general"},
    )

    assert result["response_source"] == "live_invoker"
    assert result["response_text"] == "Here is the careful live answer."
    assert (
        "Live local model generation succeeded through the governed invoker. "
        "Tool, network, and mutation authority remains independently governed by "
        "the effective profile, approvals, and capability adapters."
        in result["caveats"]
    )
    assert (
        "Local session journal memory was considered during context gathering."
        in result["caveats"]
    )
    assert "Memory handling was constrained by policy boundaries." in result["caveats"]
    assert (
        "A boundary-sensitive memory class shaped how this response was handled."
        in result["caveats"]
    )
    assert (
        "Additional boundary checks were applied to the selected memory path."
        in result["caveats"]
    )
    assert "Internal verification did not fully pass." in result["caveats"]


def test_invoke_model_result_shape_feeds_responder_live_render(
    base_configs,
    prompt_environment,
    routing_decision,
    monkeypatch,
):
    del prompt_environment

    monkeypatch.setattr(
        invoker,
        "_list_ollama_models",
        lambda **_kwargs: ["qwen3:8b", "llama3.1:8b"],
    )
    monkeypatch.setattr(
        invoker,
        "_call_ollama_chat",
        lambda **_kwargs: {
            "ok": True,
            "response_text": "Hello from the governed local invoker.",
            "latency_ms": 42,
            "provider_metadata": {"model": "qwen3:8b"},
        },
    )

    internal_result = invoker.invoke_model(
        message="In one sentence, who are you?",
        model_routing_decision=deepcopy(routing_decision),
        configs=deepcopy(base_configs),
    )

    result = compose_response(
        "In one sentence, who are you?",
        _base_plan(),
        _base_policy_review(),
        _base_verification(),
        internal_result=internal_result,
        model_routing=deepcopy(routing_decision),
    )

    assert internal_result["status"] == "ok"
    assert result["status"] == "response_composed"
    assert result["response_source"] == "live_invoker"
    assert result["response_text"] == "Hello from the governed local invoker."
    assert result["selected_model_role"] == "primary_general"
    assert result["selected_runtime"] == "ollama"
    assert result["selected_model_runtime_tag"] == "qwen3:8b"


def test_invoke_model_allowed_local_fallback_shape_feeds_responder_truthfully(
    base_configs,
    prompt_environment,
    routing_decision,
    monkeypatch,
):
    del prompt_environment

    monkeypatch.setattr(
        invoker,
        "_list_ollama_models",
        lambda **_kwargs: ["llama3.1:8b"],
    )

    def fake_call(**kwargs):
        assert kwargs["runtime_tag"] == "llama3.1:8b"
        return {
            "ok": True,
            "response_text": "Fallback model answered locally.",
            "latency_ms": 55,
            "provider_metadata": {"model": "llama3.1:8b"},
        }

    monkeypatch.setattr(invoker, "_call_ollama_chat", fake_call)

    internal_result = invoker.invoke_model(
        message="Answer anyway.",
        model_routing_decision=deepcopy(routing_decision),
        configs=deepcopy(base_configs),
    )

    result = compose_response(
        "Answer anyway.",
        _base_plan(),
        _base_policy_review(),
        _base_verification(),
        internal_result=internal_result,
        model_routing=deepcopy(routing_decision),
    )

    assert internal_result["status"] == "ok"
    assert internal_result["used_fallback"] is True
    assert internal_result["fallback_from"] == "qwen3:8b"
    assert internal_result["fallback_to"] == "llama3.1:8b"

    assert result["response_source"] == "live_invoker"
    assert result["response_text"] == "Fallback model answered locally."
    assert result["used_fallback"] is True
    assert result["fallback_from"] == "qwen3:8b"
    assert result["fallback_to"] == "llama3.1:8b"
    assert (
        "An allowed local fallback model was used instead of the preferred runtime tag."
        in result["caveats"]
    )
