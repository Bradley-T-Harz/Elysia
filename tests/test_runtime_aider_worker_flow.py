from __future__ import annotations

from pathlib import Path
from typing import Any

import core.runtime as runtime
from core.repo_context_gatherer import RepoContextResult, RepoContextStatus
from core.verifier import verify_result


def _disable_runtime_side_effects(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        runtime,
        "write_runtime_log",
        lambda payload: tmp_path / "runtime_log.jsonl",
    )
    monkeypatch.setattr(
        runtime,
        "write_session_journal_entry",
        lambda payload, journal_policy: {
            "status": "skipped_for_test",
            "path": "",
            "written": False,
        },
    )


def _fake_invoke_model_factory(captured: dict[str, Any]):
    def fake_invoke_model(**kwargs):
        captured["kwargs"] = kwargs
        captured["context_summary"] = kwargs.get("context_summary", "")
        return {
            "status": "ok",
            "allowed": True,
            "stayed_local": True,
            "selected_role": "primary_code",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "fake-local-code-model",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "prompt_source": "runtime_aider_worker_flow_test",
            "response_text": "Coder response generated from mocked local invoker.",
            "error": "",
            "block_reasons": [],
            "unmet_requirements": [],
            "latency_ms": 0,
            "provider_metadata": {"mocked": True},
            "note": "Fake invoker used by runtime Aider worker tests.",
        }

    return fake_invoke_model


def _context_for_message(message: str) -> dict[str, Any]:
    return {
        "request_summary": message,
        "retrieved_memory_count": 0,
        "retrieval_mode": "none",
    }


def _fake_repo_context_result(tmp_path: Path) -> RepoContextResult:
    return RepoContextResult(
        ok=True,
        status=RepoContextStatus.COMPLETED,
        repo_key="elysia",
        repo_label="Elysia local repository",
        repo_root=str(tmp_path / "Elysia"),
        trust_zone="project_local",
        appears_git_repo=True,
        current_branch="main",
        git_head_read=True,
        changed_files_live=False,
        changed_files_note="Git status detection is not live in repo context v0.",
        important_top_level_files=["README.md"],
        top_level_directories=["app", "core", "tests", "sandbox"],
        safe_tree_entries=[
            "core/runtime.py",
            "sandbox/aider_worker/worker.py",
            "tests/test_runtime_aider_worker_flow.py",
        ],
        language_hints=["Python"],
        framework_hints=["Core Python organs", "Pytest backend tests"],
        test_command_hints=[
            "./scripts/test_backend.sh tests/test_runtime_aider_worker_flow.py -q",
        ],
        boundary_notes=[
            "Read-only local repo context v0.",
            "No shell commands were run.",
            "No network access was used.",
            "No files were mutated.",
        ],
    )


def _install_common_runtime_mocks(
    monkeypatch,
    tmp_path: Path,
    captured: dict[str, Any],
) -> None:
    _disable_runtime_side_effects(monkeypatch, tmp_path)
    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: _context_for_message(
            message
        ),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured),
    )
    monkeypatch.setattr(
        runtime,
        "gather_repo_context",
        lambda repo_key="elysia": _fake_repo_context_result(tmp_path),
    )


def _assert_no_aider_execution(payload: dict[str, Any]) -> None:
    assert payload["worker_used"] is False
    assert payload["aider_invoked"] is False
    assert payload["mutated_files"] is False
    assert payload["shell_used"] is False
    assert payload["network_used"] is False
    assert payload["test_execution_used"] is False
    assert payload["git_mutation_used"] is False
    assert payload["package_install_used"] is False
    assert payload["external_model_used"] is False
    assert payload["commands_run"] == []
    assert payload["tests_run"] == []


def test_coder_aider_request_with_safe_files_surfaces_dry_run_truth(
    monkeypatch,
    tmp_path,
):
    captured_invocation: dict[str, Any] = {}
    _install_common_runtime_mocks(monkeypatch, tmp_path, captured_invocation)

    result = runtime.handle_user_message(
        "Use Aider to prepare a patch plan for core/runtime.py and tests/test_runtime_aider_worker_flow.py.",
        runtime.SessionState(active_mode="coder"),
    )

    aider_worker = result["aider_worker"]

    assert result["status"] == "ok_local_runtime"
    assert aider_worker["used"] is True
    assert aider_worker["status"] == "dry_run_ready"
    assert aider_worker["state"] == "skeleton"
    assert aider_worker["mode"] == "dry_run_validation"
    assert aider_worker["files_considered"] == [
        "core/runtime.py",
        "tests/test_runtime_aider_worker_flow.py",
    ]
    assert aider_worker["approval_required"] is True
    _assert_no_aider_execution(aider_worker)

    assert result["verification"]["verified"] is True
    assert "aider_worker_summary_present" in result["verification"]["checks_passed"]
    assert "aider_worker_aider_invoked_false" in result["verification"]["checks_passed"]

    assert "context_summary" not in captured_invocation
    assert result["internal_result"]["status"] == "not_invoked"
    assert result["internal_result"]["prompt_source"] == "aider_worker_structured_truth"

    response_text = result["response"]["response_text"]
    assert "Aider worker skeleton dry-run validation is ready." in response_text
    assert "Aider subprocess was not invoked." in response_text
    assert "No files were changed." in response_text
    assert "Coder response generated from mocked local invoker" not in response_text


def test_default_chat_does_not_create_aider_worker_validation(
    monkeypatch,
    tmp_path,
):
    captured_invocation: dict[str, Any] = {}
    _disable_runtime_side_effects(monkeypatch, tmp_path)
    monkeypatch.setattr(
        runtime,
        "gather_context",
        lambda message, session_state, configs, retrieval_policy: _context_for_message(
            message
        ),
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    def fail_if_aider_worker_is_called(*args, **kwargs):
        raise AssertionError("Default chat should not run Aider worker validation.")

    monkeypatch.setattr(
        runtime,
        "run_aider_worker_dry_run",
        fail_if_aider_worker_is_called,
    )

    result = runtime.handle_user_message(
        "Hello, how are you?",
        runtime.SessionState(active_mode="default"),
    )

    assert result["aider_worker"]["used"] is False
    assert result["aider_worker"]["status"] == "not_needed"
    _assert_no_aider_execution(result["aider_worker"])
    assert "Aider Worker dry-run validation result:" not in captured_invocation["context_summary"]


def test_coder_patch_request_without_explicit_files_does_not_invent_aider_files(
    monkeypatch,
    tmp_path,
):
    captured_invocation: dict[str, Any] = {}
    _install_common_runtime_mocks(monkeypatch, tmp_path, captured_invocation)

    result = runtime.handle_user_message(
        "What files should we change and how should we patch this?",
        runtime.SessionState(active_mode="coder"),
    )

    aider_worker = result["aider_worker"]

    assert result["plan"]["code_patch_plan_candidate"] is True
    assert result["plan"]["code_patch_files_to_touch"] == []
    assert aider_worker["used"] is False
    assert aider_worker["status"] == "not_needed"
    assert aider_worker["files_considered"] == []
    assert aider_worker["files_proposed"] == []
    _assert_no_aider_execution(aider_worker)
    assert "Aider Worker dry-run validation result:" not in captured_invocation["context_summary"]


def test_unsafe_selected_path_surfaces_blocked_aider_worker_truth(
    monkeypatch,
    tmp_path,
):
    captured_invocation: dict[str, Any] = {}
    _install_common_runtime_mocks(monkeypatch, tmp_path, captured_invocation)

    result = runtime.handle_user_message(
        "Use Aider to prepare a patch plan for ../outside.py.",
        runtime.SessionState(active_mode="coder"),
    )

    aider_worker = result["aider_worker"]

    assert result["status"] == "ok_local_runtime"
    assert result["code_patch_plan"]["status"] == "blocked"
    assert aider_worker["used"] is True
    assert aider_worker["status"] == "blocked"
    assert aider_worker["refusal_reasons"]
    _assert_no_aider_execution(aider_worker)

    assert result["verification"]["verified"] is True
    assert "aider_worker_blocked_has_refusal_truth" in result["verification"]["checks_passed"]
    assert "context_summary" not in captured_invocation
    assert result["internal_result"]["status"] == "blocked"
    assert result["internal_result"]["prompt_source"] == "aider_worker_structured_truth"


def test_verifier_rejects_aider_worker_execution_or_mutation_claims():
    bad_payload = {
        "used": True,
        "status": "dry_run_ready",
        "worker_used": True,
        "aider_invoked": True,
        "mutated_files": True,
        "shell_used": True,
        "network_used": True,
        "test_execution_used": True,
        "git_mutation_used": True,
        "package_install_used": True,
        "external_model_used": True,
        "commands_run": ["pytest"],
        "tests_run": ["tests/test_runtime_aider_worker_flow.py"],
        "approval_required": False,
        "refusal_reasons": [],
        "errors": [],
    }

    verification = verify_result(
        {
            "intent": "coding",
            "mode": "coder",
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class_declared": False,
            "repo_context_candidate": False,
            "code_patch_plan_candidate": False,
        },
        {
            "status": "ok",
            "note": "Verifier Aider worker truth test.",
            "aider_worker": bad_payload,
        },
    )

    assert verification["verified"] is False
    assert any("Aider worker skeleton" in issue for issue in verification["issues"])
    assert any("commands were run" in issue for issue in verification["issues"])
    assert any("tests were run" in issue for issue in verification["issues"])
