from __future__ import annotations

from copy import deepcopy

import pytest

from core import model_invoker as invoker
from core import runtime


@pytest.fixture
def base_configs():
    return {
        "memory": {
            "memory_policy": {
                "scaffold_memory_classes": {
                    "require_declared_memory_class": True,
                    "planner_must_record_memory_class": True,
                    "journal_selected_memory_class": True,
                    "retrieval_must_respect_allowed_classes": True,
                    "default_memory_class": "conversation_memory",
                    "fallback_memory_class": "working_memory",
                    "classes": {
                        "working_memory": {},
                        "conversation_memory": {},
                        "preference_memory": {},
                        "project_memory": {},
                    },
                    "mode_overrides": {
                        "default": {
                            "primary_memory_class": "conversation_memory",
                            "default_memory_class": "conversation_memory",
                            "fallback_memory_class": "working_memory",
                            "allowed_memory_classes": [
                                "working_memory",
                                "conversation_memory",
                                "preference_memory",
                            ],
                            "disallowed_memory_classes": [],
                        },
                        "tutor": {
                            "primary_memory_class": "working_memory",
                            "default_memory_class": "conversation_memory",
                            "fallback_memory_class": "working_memory",
                            "allowed_memory_classes": [
                                "working_memory",
                                "conversation_memory",
                                "preference_memory",
                                "project_memory",
                            ],
                            "disallowed_memory_classes": [],
                        },
                    },
                    "autonomy_overrides": {},
                    "boundary_overrides": {
                        "local_session_memory": {
                            "forced_memory_class": "working_memory",
                            "require_boundary_check": True,
                        }
                    },
                }
            }
        },
        "models": {
            "model_roles": {
                "roles": {
                    "primary_general": {
                        "preferred_model": "qwen3:8b",
                        "preferred_model_runtime_tag": "qwen3:8b",
                        "fallback_models": ["llama3.1:8b"],
                        "fallback_model_runtime_tags": ["llama3.1:8b"],
                        "runtime": "ollama",
                        "local_only": True,
                        "enabled_by_default": True,
                        "status": "candidate_declared",
                        "privacy_risk": "low",
                        "trust_note": "Trust-first local general brain.",
                    },
                    "lighter_backup": {
                        "preferred_model": "llama3.1:8b",
                        "preferred_model_runtime_tag": "llama3.1:8b",
                        "runtime": "ollama",
                        "local_only": True,
                        "enabled_by_default": True,
                        "status": "candidate_declared",
                        "privacy_risk": "low",
                        "trust_note": "Lightweight backup.",
                    },
                },
                "external_helpers": {},
            },
            "routing": {
                "routing_mode": "explicit_local_first_role_governed",
                "defaults": {
                    "primary_role": "primary_general",
                    "fallback_role": "lighter_backup",
                    "allow_silent_cloud_fallback": False,
                    "sensitive_work_must_remain_local": True,
                },
                "mode_routes": {
                    "tutor": {
                        "preferred_role": "primary_general",
                        "fallback_role": "lighter_backup",
                        "local_only": True,
                    }
                },
                "task_routes": {
                    "tutoring": {
                        "preferred_role": "primary_general",
                        "fallback_role": "lighter_backup",
                        "local_only": True,
                    }
                },
            },
        },
        "policies": {},
        "system": {},
    }


@pytest.fixture
def runtime_skills():
    return {
        "conversation.conversation_helper": {},
        "tutoring.tutoring_helper": {},
        "research.research_summary_helper": {},
        "writing.drafting_helper": {},
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


def _install_runtime_environment(monkeypatch, base_configs, runtime_skills):
    captured = {
        "log_payload": None,
        "journal_payload": None,
        "journal_policy_arg": None,
    }

    monkeypatch.setattr(
        runtime,
        "load_all_configs",
        lambda: deepcopy(base_configs),
    )
    monkeypatch.setattr(
        runtime,
        "load_all_skills",
        lambda: deepcopy(runtime_skills),
    )
    # Integration behavior must not depend on the workstation's momentary
    # thermal/load state or the operator's live Ollama residency.
    monkeypatch.setattr(
        runtime.ModelRegistry,
        "snapshot",
        lambda _self: {"provider_healthy": True, "models": []},
    )
    monkeypatch.setattr(
        runtime,
        "resource_snapshot",
        lambda: {
            "captured_at_utc": "2026-08-22T00:00:00Z",
            "system": {
                "cpu_percent": 10,
                "logical_cpus": 8,
                "ram_total_mb": 32768,
                "ram_available_mb": 24576,
                "load_1m": 0.5,
                "telemetry": "synthetic_test_fixture",
            },
            "gpu": {
                "available": False,
                "telemetry": "synthetic_test_fixture",
                "devices": [],
            },
            "ollama_residency": [],
            "private_content_included": False,
        },
    )
    monkeypatch.setattr(runtime.ComputeLedger, "active_jobs", lambda _self: [])
    monkeypatch.setattr(
        runtime.ComputeLedger,
        "reserve_job",
        lambda _self, _workload: "computejob_synthetic_runtime_test",
    )
    monkeypatch.setattr(runtime.ComputeLedger, "record", lambda _self, _decision: None)
    monkeypatch.setattr(
        runtime.ComputeLedger,
        "release_job",
        lambda _self, _reservation_id, *, reason: True,
    )
    monkeypatch.setattr(
        runtime,
        "build_retrieval_policy",
        lambda session_state, mode, configs: {
            "retrieval_mode": "local_session_journal_scaffold_excluding_current_day",
            "allowed_memory_classes": ["working_memory", "conversation_memory"],
            "mode": mode,
        },
    )
    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: {
            "request_summary": message,
            "retrieved_memory_count": 2,
            "retrieval_mode": "local_session_journal_scaffold_excluding_current_day",
        },
    )
    monkeypatch.setattr(
        runtime,
        "select_skill",
        lambda intent, skills: {
            "selected_skill_id": "tutoring.tutoring_helper",
            "selection_basis": "intent_map",
            "found": True,
        },
    )
    monkeypatch.setattr(
        runtime,
        "build_runtime_journal_policy",
        lambda session_state, mode, configs, boundary_flags: {
            "journal_write_allowed": True,
            "journal_mode": "standard",
            "include_plan_summary": True,
            "include_retrieval_summary": True,
            "include_boundary_flags": True,
            "include_memory_class": True,
            "include_policy_summary": True,
            "redact_sensitive_content": True,
            "applied_boundary_overrides": [],
            "note": f"Patched journal policy for mode={mode}",
        },
    )

    def fake_write_runtime_log(payload):
        captured["log_payload"] = deepcopy(payload)
        return "/tmp/fake_runtime.log"

    def fake_write_session_journal_entry(payload, journal_policy):
        captured["journal_payload"] = deepcopy(payload)
        captured["journal_policy_arg"] = deepcopy(journal_policy)
        return {
            "path": "/tmp/fake_runtime-session.md",
            "journal_write_allowed": bool(journal_policy.get("journal_write_allowed", False)),
            "journal_mode": journal_policy.get("journal_mode", "unknown"),
        }

    monkeypatch.setattr(runtime, "write_runtime_log", fake_write_runtime_log)
    monkeypatch.setattr(runtime, "write_session_journal_entry", fake_write_session_journal_entry)

    return captured


def test_runtime_successful_invoker_path_preserves_live_output_and_trace_fields(
    monkeypatch,
    base_configs,
    runtime_skills,
    prompt_environment,
):
    del prompt_environment

    captured = _install_runtime_environment(monkeypatch, base_configs, runtime_skills)

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
            "response_text": "Live governed local answer.",
            "latency_ms": 42,
            "provider_metadata": {"model": "qwen3:8b"},
        },
    )

    result = runtime.handle_user_message(
        "Can you explain derivatives step by step?",
        runtime.SessionState(),
    )

    assert result["status"] == "ok_local_runtime"
    assert result["intent"]["primary"] == "tutoring"
    assert result["session_state"]["active_mode"] == "tutor"

    assert result["model_routing"]["task_type"] == "tutoring"
    assert result["model_routing"]["selected_role"] == "primary_general"
    assert result["model_routing"]["selected_runtime"] == "ollama"
    assert result["model_routing"]["stayed_local"] is True

    assert result["memory_class_policy"]["forced_memory_class"] == "working_memory"
    assert result["memory_class_policy"]["applied_boundary_overrides"] == [
        "local_session_memory"
    ]
    assert result["plan"]["memory_class"] == "working_memory"
    assert result["plan"]["memory_class_source"] == "forced_memory_class"

    assert result["internal_result"]["status"] == "ok", (
        result["internal_result"].get("block_reasons"),
        result["internal_result"].get("error"),
        result.get("compute"),
    )
    assert result["internal_result"]["selected_model_runtime_tag"] == "qwen3:8b"
    assert result["internal_result"]["used_fallback"] is False
    assert result["internal_result"]["response_text"] == "Live governed local answer."

    assert result["verification"]["verified"] is True

    assert result["response"]["status"] == "response_composed"
    assert result["response"]["response_source"] == "live_invoker"
    assert result["response"]["invocation_status"] == "ok"
    assert result["response"]["response_text"] == "Live governed local answer."
    assert result["response"]["selected_model_role"] == "primary_general"
    assert result["response"]["selected_runtime"] == "ollama"
    assert result["response"]["selected_model_runtime_tag"] == "qwen3:8b"
    assert (
        "Live local model generation succeeded through the governed invoker. "
        "Tool, network, and mutation authority remains independently governed by "
        "the effective profile, approvals, and capability adapters."
        in result["response"]["caveats"]
    )
    assert (
        "Local session journal memory was considered during context gathering."
        in result["response"]["caveats"]
    )
    assert "Memory handling was constrained by policy boundaries." in result["response"]["caveats"]
    assert (
        "Additional boundary checks were applied to the selected memory path."
        in result["response"]["caveats"]
    )

    assert captured["log_payload"]["selected_model_role"] == "primary_general"
    assert captured["log_payload"]["selected_model_runtime"] == "ollama"
    assert captured["log_payload"]["invoker_status"] == "ok"
    assert captured["log_payload"]["invoker_selected_model_runtime_tag"] == "qwen3:8b"
    assert captured["log_payload"]["invoker_used_fallback"] is False
    assert captured["log_payload"]["invoker_error"] == ""

    assert captured["journal_payload"]["selected_model_role"] == "primary_general"
    assert captured["journal_payload"]["selected_model_runtime"] == "ollama"
    assert captured["journal_payload"]["invoker_status"] == "ok"
    assert captured["journal_payload"]["invoker_selected_model_runtime_tag"] == "qwen3:8b"
    assert captured["journal_payload"]["invoker_used_fallback"] is False
    assert result["log_status"]["path"] == "/tmp/fake_runtime.log"
    assert result["journal_status"]["path"] == "/tmp/fake_runtime-session.md"


def test_runtime_blocked_invoker_path_keeps_runtime_structured_and_captures_handoff(
    monkeypatch,
    base_configs,
    runtime_skills,
):
    captured = _install_runtime_environment(monkeypatch, base_configs, runtime_skills)
    invoke_capture = {}

    def fake_invoke_model(
        *,
        message,
        model_routing_decision,
        configs,
        mode,
        task_type,
        context_summary,
        conversation_messages,
    ):
        invoke_capture["message"] = message
        invoke_capture["model_routing_decision"] = deepcopy(model_routing_decision)
        invoke_capture["configs"] = deepcopy(configs)
        invoke_capture["mode"] = mode
        invoke_capture["task_type"] = task_type
        invoke_capture["context_summary"] = context_summary
        invoke_capture["conversation_messages"] = conversation_messages

        return {
            "status": "blocked",
            "allowed": False,
            "stayed_local": True,
            "selected_role": "primary_general",
            "selected_role_container": "roles",
            "selected_target": "qwen3:8b",
            "selected_model": "qwen3:8b",
            "selected_model_runtime_tag": "qwen3:8b",
            "selected_runtime": "ollama",
            "selected_service": "ollama",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "prompt_source": "derived/runtime/elysia_general_system.txt",
            "response_text": "",
            "error": "",
            "block_reasons": ["route_requires_local_only"],
            "unmet_requirements": [],
            "latency_ms": 0,
            "provider_metadata": {},
            "note": "Invocation blocked by routed path.",
        }

    monkeypatch.setattr(runtime, "invoke_model", fake_invoke_model)

    result = runtime.handle_user_message(
        "Can you explain derivatives step by step?",
        runtime.SessionState(),
    )

    assert result["status"] == "ok_local_runtime"
    assert result["internal_result"]["status"] == "blocked"
    assert result["verification"]["verified"] is True

    assert result["response"]["response_source"] == "scaffold_fallback"
    assert result["response"]["invocation_status"] == "blocked"
    assert "A bounded scaffold response path was used." in result["response"]["response_text"]
    assert (
        "Tool or side-effect authority was not granted for this response; no such "
        "operation was implied by model generation."
        in result["response"]["caveats"]
    )
    assert (
        "Live local invocation was blocked by the current routed path or boundary rules."
        in result["response"]["caveats"]
    )

    assert invoke_capture["message"] == "Can you explain derivatives step by step?"
    assert invoke_capture["mode"] == "tutor"
    assert invoke_capture["task_type"] == "tutoring"
    assert invoke_capture["context_summary"] == ""
    assert invoke_capture["conversation_messages"] is None
    assert invoke_capture["model_routing_decision"]["selected_role"] == "primary_general"
    assert invoke_capture["model_routing_decision"]["selected_runtime"] == "ollama"
    assert "private_memory_context_present" in invoke_capture["model_routing_decision"]["context_flags"]
    assert "local_session_memory_context" in invoke_capture["model_routing_decision"]["context_flags"]
    assert "autonomy_level_1_or_higher" in invoke_capture["model_routing_decision"]["context_flags"]

    assert captured["log_payload"]["invoker_status"] == "blocked"
    assert captured["journal_payload"]["invoker_status"] == "blocked"
    assert captured["log_payload"]["invoker_note"] == "Invocation blocked by routed path."
    assert captured["journal_payload"]["invoker_note"] == "Invocation blocked by routed path."


def test_runtime_error_invoker_path_falls_back_and_logs_error_state(
    monkeypatch,
    base_configs,
    runtime_skills,
):
    captured = _install_runtime_environment(monkeypatch, base_configs, runtime_skills)

    monkeypatch.setattr(
        runtime,
        "invoke_model",
        lambda **kwargs: {
            "status": "error",
            "allowed": True,
            "stayed_local": True,
            "selected_role": "primary_general",
            "selected_role_container": "roles",
            "selected_target": "qwen3:8b",
            "selected_model": "qwen3:8b",
            "selected_model_runtime_tag": "qwen3:8b",
            "selected_runtime": "ollama",
            "selected_service": "ollama",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "prompt_source": "derived/runtime/elysia_general_system.txt",
            "response_text": "",
            "error": "Primary model timed out.",
            "block_reasons": ["local_invocation_attempt_failed"],
            "unmet_requirements": [],
            "latency_ms": 88,
            "provider_metadata": {},
            "note": "Local invocation failed.",
        },
    )

    result = runtime.handle_user_message(
        "Can you explain derivatives step by step?",
        runtime.SessionState(),
    )

    assert result["status"] == "ok_local_runtime"
    assert result["internal_result"]["status"] == "error"
    assert result["verification"]["verified"] is True

    assert result["response"]["response_source"] == "scaffold_fallback"
    assert result["response"]["invocation_status"] == "error"
    assert "A bounded scaffold response path was used." in result["response"]["response_text"]
    assert (
        "Live local invocation failed, so a governed deterministic fallback response was returned."
        in result["response"]["caveats"]
    )
    assert "Invocation reported an internal error state." in result["response"]["caveats"]

    assert captured["log_payload"]["invoker_status"] == "error"
    assert captured["log_payload"]["invoker_error"] == "Primary model timed out."
    assert captured["journal_payload"]["invoker_status"] == "error"
    assert captured["journal_payload"]["invoker_error"] == "Primary model timed out."


def test_runtime_allowed_local_fallback_surfaces_fallback_through_response_log_and_journal(
    monkeypatch,
    base_configs,
    runtime_skills,
    prompt_environment,
):
    del prompt_environment

    captured = _install_runtime_environment(monkeypatch, base_configs, runtime_skills)

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

    result = runtime.handle_user_message(
        "Can you explain derivatives step by step?",
        runtime.SessionState(),
    )

    assert result["status"] == "ok_local_runtime"
    assert result["internal_result"]["status"] == "ok"
    assert result["internal_result"]["used_fallback"] is True
    assert result["internal_result"]["fallback_from"] == "qwen3:8b"
    assert result["internal_result"]["fallback_to"] == "llama3.1:8b"

    assert result["response"]["response_source"] == "live_invoker"
    assert result["response"]["response_text"] == "Fallback model answered locally."
    assert result["response"]["used_fallback"] is True
    assert result["response"]["fallback_from"] == "qwen3:8b"
    assert result["response"]["fallback_to"] == "llama3.1:8b"
    assert (
        "An allowed local fallback model was used instead of the preferred runtime tag."
        in result["response"]["caveats"]
    )

    assert captured["log_payload"]["invoker_used_fallback"] is True
    assert captured["log_payload"]["invoker_fallback_from"] == "qwen3:8b"
    assert captured["log_payload"]["invoker_fallback_to"] == "llama3.1:8b"

    assert captured["journal_payload"]["invoker_used_fallback"] is True
    assert captured["journal_payload"]["invoker_fallback_from"] == "qwen3:8b"
    assert captured["journal_payload"]["invoker_fallback_to"] == "llama3.1:8b"


def test_runtime_verification_still_runs_and_surfaces_verification_caveat_when_invoker_note_is_missing(
    monkeypatch,
    base_configs,
    runtime_skills,
):
    captured = _install_runtime_environment(monkeypatch, base_configs, runtime_skills)

    monkeypatch.setattr(
        runtime,
        "invoke_model",
        lambda **kwargs: {
            "status": "ok",
            "allowed": True,
            "stayed_local": True,
            "selected_role": "primary_general",
            "selected_role_container": "roles",
            "selected_target": "qwen3:8b",
            "selected_model": "qwen3:8b",
            "selected_model_runtime_tag": "qwen3:8b",
            "selected_runtime": "ollama",
            "selected_service": "ollama",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "prompt_source": "derived/runtime/elysia_general_system.txt",
            "response_text": "Live answer still arrived.",
            "error": "",
            "block_reasons": [],
            "unmet_requirements": [],
            "latency_ms": 12,
            "provider_metadata": {},
            "note": "",
        },
    )

    result = runtime.handle_user_message(
        "Can you explain derivatives step by step?",
        runtime.SessionState(),
    )

    assert result["status"] == "ok_local_runtime"
    assert result["internal_result"]["status"] == "ok"
    assert result["verification"]["verified"] is False
    assert "internal result is missing note" in result["verification"]["issues"]

    assert result["response"]["response_source"] == "live_invoker"
    assert result["response"]["response_text"] == "Live answer still arrived."
    assert "Internal verification did not fully pass." in result["response"]["caveats"]

    assert captured["log_payload"]["invoker_note"] == ""
    assert captured["journal_payload"]["invoker_note"] == ""
