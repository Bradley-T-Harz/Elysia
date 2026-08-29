from __future__ import annotations

from pathlib import Path
from typing import Any

import core.runtime as runtime
from core.repo_context_gatherer import RepoContextResult, RepoContextStatus


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
        captured["message"] = kwargs.get("message")
        captured["context_summary"] = kwargs.get("context_summary", "")
        captured["task_type"] = kwargs.get("task_type")
        captured["mode"] = kwargs.get("mode")

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
            "prompt_source": "runtime_coder_mode_test",
            "response_text": "Coder response generated from mocked local invoker.",
            "error": "",
            "block_reasons": [],
            "unmet_requirements": [],
            "latency_ms": 0,
            "provider_metadata": {"mocked": True},
            "note": "Fake invoker used by runtime coder mode tests.",
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
        top_level_directories=["app", "apps", "core", "tests", "config"],
        safe_tree_entries=[
            "core/runtime.py",
            "core/planner.py",
            "tests/test_runtime_coder_mode_flow.py",
            "apps/elysia-desktop/src/ConversationsPage.tsx",
        ],
        language_hints=["Python", "TypeScript"],
        framework_hints=[
            "FastAPI local API bridge",
            "React desktop UI",
            "Tauri desktop shell",
            "Pytest backend tests",
            "Core Python organs",
        ],
        test_command_hints=[
            "./scripts/test_backend.sh tests/test_runtime_coder_mode_flow.py -q",
            "./scripts/test_backend.sh -q",
        ],
        boundary_notes=[
            "Read-only local repo context v0.",
            "No shell commands were run.",
            "No network access was used.",
            "No files were mutated.",
        ],
    )


def _install_common_runtime_mocks(monkeypatch, tmp_path: Path, captured: dict[str, Any]) -> None:
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


def test_coder_repo_inspection_gathers_read_only_repo_context(monkeypatch, tmp_path):
    captured_invocation: dict[str, Any] = {}
    _install_common_runtime_mocks(monkeypatch, tmp_path, captured_invocation)

    result = runtime.handle_user_message(
        "Inspect this repo and tell me what kind of project it is.",
        runtime.SessionState(active_mode="coder"),
    )

    repo_context = result["repo_context"]

    assert result["status"] == "ok_local_runtime"
    assert result["plan"]["mode"] == "coder"
    assert result["plan"]["repo_context_candidate"] is True
    assert result["plan"]["code_patch_plan_candidate"] is False
    assert "bounded_repo_context" in result["policy_review"]["boundary_flags"]

    assert repo_context["used"] is True
    assert repo_context["status"] == "completed"
    assert repo_context["tool_kind"] == "repo_context_gatherer"
    assert repo_context["repo_key"] == "elysia"
    assert repo_context["read_only"] is True
    assert repo_context["shell_used"] is False
    assert repo_context["network_access_used"] is False
    assert repo_context["mutated_files"] is False

    assert result["verification"]["verified"] is True
    assert "repo_context_summary_present" in result["verification"]["checks_passed"]
    assert "repo_context_read_only" in result["verification"]["checks_passed"]

    context_summary = captured_invocation["context_summary"]
    assert "Repo Context result:" in context_summary
    assert "Mode-specific Coder response guidance:" in context_summary
    assert "FastAPI local API bridge" in context_summary
    assert "Pytest backend tests" in context_summary
    assert "No shell commands were run." in context_summary

    assert any(
        "Read-only local repo context was gathered from an approved repo" in caveat
        for caveat in result["response"]["caveats"]
    )

    response_text = result["response"]["response_text"]
    assert result["response"]["response_source"] == "structured_coder_repo_context"
    assert "Read-only repo context gathered." in response_text
    assert "Git status detection is not live in repo context v0." in response_text
    assert "No shell was used." in response_text
    assert "No network access was used." in response_text
    assert "No files were changed." in response_text
    assert "Coder response generated from mocked local invoker" not in response_text


def test_default_chat_does_not_run_coder_organs(monkeypatch, tmp_path):
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

    def fail_if_repo_context_is_called(*args, **kwargs):
        raise AssertionError("Default chat should not gather repo context.")

    monkeypatch.setattr(runtime, "gather_repo_context", fail_if_repo_context_is_called)

    result = runtime.handle_user_message(
        "Hello, how are you?",
        runtime.SessionState(active_mode="default"),
    )

    assert result["status"] == "ok_local_runtime"
    assert result["plan"]["mode"] == "default"
    assert result["plan"]["repo_context_candidate"] is False
    assert result["plan"]["code_patch_plan_candidate"] is False

    assert result["repo_context"]["used"] is False
    assert result["repo_context"]["status"] == "not_needed"
    assert result["code_patch_plan"]["used"] is False
    assert result["code_patch_plan"]["status"] == "not_needed"

    assert result["verification"]["verified"] is True
    assert "repo_context_not_required" in result["verification"]["checks_passed"]
    assert "code_patch_plan_not_required" in result["verification"]["checks_passed"]
    assert "Repo Context result:" not in captured_invocation["context_summary"]
    assert "Code Patch Plan result:" not in captured_invocation["context_summary"]


def test_coder_patch_request_with_safe_files_formats_proposal_only_plan(
    monkeypatch,
    tmp_path,
):
    captured_invocation: dict[str, Any] = {}
    _install_common_runtime_mocks(monkeypatch, tmp_path, captured_invocation)

    result = runtime.handle_user_message(
        "Make a patch plan for core/runtime.py and tests/test_runtime_coder_mode_flow.py.",
        runtime.SessionState(active_mode="coder"),
    )

    boundary_flags = result["policy_review"]["boundary_flags"]
    code_patch_plan = result["code_patch_plan"]

    assert result["status"] == "ok_local_runtime"
    assert result["plan"]["mode"] == "coder"
    assert result["plan"]["repo_context_candidate"] is True
    assert result["plan"]["code_patch_plan_candidate"] is True
    assert result["plan"]["code_patch_files_to_touch"] == [
        "core/runtime.py",
        "tests/test_runtime_coder_mode_flow.py",
    ]
    assert "bounded_repo_context" in boundary_flags
    assert "code_patch_plan" in boundary_flags

    assert code_patch_plan["used"] is True
    assert code_patch_plan["status"] == "completed"
    assert code_patch_plan["tool_kind"] == "code_patch_formatter"
    assert code_patch_plan["files_to_touch"] == [
        "core/runtime.py",
        "tests/test_runtime_coder_mode_flow.py",
    ]
    assert code_patch_plan["approval_needed"] is True
    assert code_patch_plan["can_apply_patch"] is False
    assert code_patch_plan["patch_application_live"] is False
    assert code_patch_plan["shell_execution_used"] is False
    assert code_patch_plan["network_access_used"] is False
    assert code_patch_plan["mutated_files"] is False
    assert code_patch_plan["external_workers_used"] is False
    assert (
        "./scripts/test_backend.sh tests/test_runtime_coder_mode_flow.py -q"
        in code_patch_plan["tests_to_run"]
    )

    assert result["verification"]["verified"] is True
    assert "code_patch_plan_summary_present" in result["verification"]["checks_passed"]
    assert "code_patch_plan_requires_approval" in result["verification"]["checks_passed"]
    assert "code_patch_plan_cannot_apply_patch" in result["verification"]["checks_passed"]

    assert "context_summary" not in captured_invocation
    assert result["aider_worker"]["used"] is True
    assert result["aider_worker"]["status"] == "dry_run_ready"
    assert result["internal_result"]["status"] == "not_invoked"
    assert result["internal_result"]["prompt_source"] == "aider_worker_structured_truth"

    assert any(
        "proposal-only patch plan was formatted" in caveat
        for caveat in result["response"]["caveats"]
    )

    response_text = result["response"]["response_text"]
    assert result["response"]["response_source"] == "structured_coder_patch_plan"
    assert "Proposal-only patch plan created." in response_text
    assert "core/runtime.py" in response_text
    assert "tests/test_runtime_coder_mode_flow.py" in response_text
    assert "Approval is required before any future patch application." in response_text
    assert "No files were changed." in response_text
    assert "No shell, network, Aider, OpenHands, external workers, or tests were used." in response_text
    assert "Coder response generated from mocked local invoker" not in response_text


def test_generic_patch_request_without_explicit_files_does_not_fake_files(
    monkeypatch,
    tmp_path,
):
    captured_invocation: dict[str, Any] = {}
    _install_common_runtime_mocks(monkeypatch, tmp_path, captured_invocation)

    result = runtime.handle_user_message(
        "What files should we change and how should we patch this?",
        runtime.SessionState(active_mode="coder"),
    )

    code_patch_plan = result["code_patch_plan"]

    assert result["status"] == "ok_local_runtime"
    assert result["plan"]["mode"] == "coder"
    assert result["plan"]["repo_context_candidate"] is True
    assert result["plan"]["code_patch_plan_candidate"] is True
    assert result["plan"]["code_patch_files_to_touch"] == []

    assert result["repo_context"]["used"] is True
    assert code_patch_plan["used"] is False
    assert code_patch_plan["status"] == "not_needed"
    assert code_patch_plan["files_to_touch"] == []
    assert any(
        "no explicit relative file paths" in warning
        for warning in code_patch_plan["warnings"]
    )

    assert result["verification"]["verified"] is True
    assert (
        "code_patch_plan_deferred_without_explicit_files"
        in result["verification"]["checks_passed"]
    )
    assert any(
        "no explicit relative file paths were provided" in caveat
        for caveat in result["response"]["caveats"]
    )
    assert "Code Patch Plan result:" not in captured_invocation["context_summary"]


def test_unsafe_patch_path_is_blocked_safely(monkeypatch, tmp_path):
    captured_invocation: dict[str, Any] = {}
    _install_common_runtime_mocks(monkeypatch, tmp_path, captured_invocation)

    result = runtime.handle_user_message(
        "Make a patch plan for ../outside.py.",
        runtime.SessionState(active_mode="coder"),
    )

    code_patch_plan = result["code_patch_plan"]

    assert result["status"] == "ok_local_runtime"
    assert result["plan"]["repo_context_candidate"] is True
    assert result["plan"]["code_patch_plan_candidate"] is True
    assert result["plan"]["code_patch_files_to_touch"] == ["../outside.py"]

    assert code_patch_plan["used"] is True
    assert code_patch_plan["status"] == "blocked"
    assert any(
        "traverse outside the repo" in error
        for error in code_patch_plan["errors"]
    )
    assert code_patch_plan["mutated_files"] is False
    assert code_patch_plan["shell_execution_used"] is False
    assert code_patch_plan["network_access_used"] is False
    assert code_patch_plan["external_workers_used"] is False
    assert code_patch_plan["can_apply_patch"] is False
    assert code_patch_plan["patch_application_live"] is False

    assert result["verification"]["verified"] is True
    assert "code_patch_plan_blocked_has_errors" in result["verification"]["checks_passed"]
    assert "Code Patch Plan result:" in captured_invocation["context_summary"]
    assert any(
        "Patch planning was blocked by Coder v0 boundaries" in caveat
        for caveat in result["response"]["caveats"]
    )


def test_aider_and_shell_language_does_not_enable_workers_or_commands(
    monkeypatch,
    tmp_path,
):
    captured_invocation: dict[str, Any] = {}
    _install_common_runtime_mocks(monkeypatch, tmp_path, captured_invocation)

    result = runtime.handle_user_message(
        "Use Aider and run tests to fix this in core/runtime.py.",
        runtime.SessionState(active_mode="coder"),
    )

    code_patch_plan = result["code_patch_plan"]

    assert result["status"] == "ok_local_runtime"
    assert result["plan"]["repo_context_candidate"] is True
    assert result["plan"]["code_patch_plan_candidate"] is True

    assert code_patch_plan["used"] is True
    assert code_patch_plan["status"] in {"completed", "blocked"}
    assert code_patch_plan["shell_execution_used"] is False
    assert code_patch_plan["external_workers_used"] is False
    assert code_patch_plan["network_access_used"] is False
    assert code_patch_plan["mutated_files"] is False
    assert code_patch_plan["patch_application_live"] is False
    assert code_patch_plan["can_apply_patch"] is False

    assert result["repo_context"]["shell_used"] is False
    assert result["repo_context"]["network_access_used"] is False
    assert result["repo_context"]["mutated_files"] is False
    assert result["verification"]["verified"] is True

    assert "context_summary" not in captured_invocation
    assert result["aider_worker"]["used"] is True
    assert result["aider_worker"]["aider_invoked"] is False
    assert result["internal_result"]["prompt_source"] == "aider_worker_structured_truth"
