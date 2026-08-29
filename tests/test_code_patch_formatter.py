from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.code_patch_formatter import (
    APPROVAL_REASON,
    CODE_PATCH_FORMATTER_OPERATION,
    CODE_PATCH_FORMATTER_TOOL_KIND,
    CodePatchPlanStatus,
    format_code_patch_plan,
)


def valid_plan_kwargs() -> dict:
    return {
        "summary": "Add safe repo context gathering.",
        "files_to_touch": [
            "core/repo_context_gatherer.py",
            "tests/test_repo_context_gatherer.py",
        ],
        "patch_plan": [
            "Create a bounded repo context result dataclass.",
            "Load approved repo config.",
            "Collect safe tree and framework hints.",
            "Add tests for approved roots and secret skipping.",
        ],
        "tests_to_run": [
            "./scripts/test_backend.sh tests/test_repo_context_gatherer.py -q",
            "./scripts/test_backend.sh -q",
        ],
        "risk_notes": [
            "Keep repo inspection read-only.",
            "Do not add shell execution in this sprint.",
        ],
        "rollback_notes": [
            "Use git restore on the proposed files before commit if needed.",
        ],
    }


def test_valid_plan_formats_successfully_with_boundary_truth():
    result = format_code_patch_plan(**valid_plan_kwargs())

    assert result.ok is True
    assert result.status == CodePatchPlanStatus.COMPLETED
    assert result.tool_kind == CODE_PATCH_FORMATTER_TOOL_KIND
    assert result.operation == CODE_PATCH_FORMATTER_OPERATION
    assert result.summary == "Add safe repo context gathering."
    assert result.files_to_touch == [
        "core/repo_context_gatherer.py",
        "tests/test_repo_context_gatherer.py",
    ]
    assert result.patch_plan[0] == "Create a bounded repo context result dataclass."
    assert result.tests_to_run == [
        "./scripts/test_backend.sh tests/test_repo_context_gatherer.py -q",
        "./scripts/test_backend.sh -q",
    ]
    assert result.risk_notes == [
        "Keep repo inspection read-only.",
        "Do not add shell execution in this sprint.",
    ]
    assert result.rollback_notes == [
        "Use git restore on the proposed files before commit if needed.",
    ]

    assert result.approval_needed is True
    assert result.approval_reason == APPROVAL_REASON
    assert result.can_apply_patch is False
    assert result.patch_application_live is False
    assert result.shell_execution_used is False
    assert result.network_access_used is False
    assert result.mutated_files is False
    assert result.external_workers_used is False
    assert "Patch plan only. No files were mutated." in result.boundary_notes
    assert "No shell commands were run." in result.boundary_notes
    assert result.errors == []


def test_empty_summary_blocks():
    kwargs = valid_plan_kwargs()
    kwargs["summary"] = ""

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert "summary is required" in result.errors[0]


def test_no_files_blocks():
    kwargs = valid_plan_kwargs()
    kwargs["files_to_touch"] = []

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert "file path is required" in result.errors[0]


def test_no_patch_steps_blocks():
    kwargs = valid_plan_kwargs()
    kwargs["patch_plan"] = []

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert "patch step is required" in result.errors[0]


def test_unsafe_absolute_path_blocks():
    kwargs = valid_plan_kwargs()
    kwargs["files_to_touch"] = ["/etc/passwd"]

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert "must be relative" in result.errors[0]


def test_parent_traversal_blocks():
    kwargs = valid_plan_kwargs()
    kwargs["files_to_touch"] = ["../outside.py"]

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert "must not traverse" in result.errors[0]


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "vault/private.md",
        ".env",
        "secrets/token.txt",
        ".git/config",
        "id_rsa",
    ],
)
def test_secret_or_sealed_paths_block(unsafe_path):
    kwargs = valid_plan_kwargs()
    kwargs["files_to_touch"] = [unsafe_path]

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert any(
        phrase in result.errors[0]
        for phrase in [
            "sealed/generated",
            "secret-bearing",
        ]
    )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "node_modules/pkg/index.js",
        ".venv/bin/python",
        "__pycache__/x.pyc",
        "dist/index.js",
    ],
)
def test_generated_or_heavy_paths_block(unsafe_path):
    kwargs = valid_plan_kwargs()
    kwargs["files_to_touch"] = [unsafe_path]

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert "sealed/generated" in result.errors[0]


def test_approval_cannot_be_disabled_in_v0():
    kwargs = valid_plan_kwargs()
    kwargs["approval_needed"] = False

    result = format_code_patch_plan(**kwargs)

    assert result.ok is True
    assert result.status == CodePatchPlanStatus.COMPLETED
    assert result.approval_needed is True
    assert result.can_apply_patch is False
    assert result.patch_application_live is False
    assert any("Approval was forced" in warning for warning in result.warnings)


def test_repo_context_test_hints_are_used_when_tests_are_missing():
    kwargs = valid_plan_kwargs()
    kwargs["tests_to_run"] = None
    kwargs["repo_context"] = {
        "repo_key": "demo",
        "repo_root": "/tmp/repo",
        "test_command_hints": [
            "./scripts/test_backend.sh -q",
            "npm --prefix apps/elysia-desktop run typecheck",
        ],
    }

    result = format_code_patch_plan(**kwargs)

    assert result.ok is True
    assert result.repo_key == "demo"
    assert result.repo_root == "/tmp/repo"
    assert result.tests_to_run == [
        "./scripts/test_backend.sh -q",
        "npm --prefix apps/elysia-desktop run typecheck",
    ]
    assert any("repo context hints" in warning for warning in result.warnings)
    assert result.shell_execution_used is False


def test_repo_context_object_is_supported():
    kwargs = valid_plan_kwargs()
    kwargs["tests_to_run"] = None
    kwargs["repo_context"] = SimpleNamespace(
        repo_key="elysia",
        repo_root="/tmp/elysia",
        test_command_hints=["./scripts/test_backend.sh tests/test_code_patch_formatter.py -q"],
    )

    result = format_code_patch_plan(**kwargs)

    assert result.ok is True
    assert result.repo_key == "elysia"
    assert result.repo_root == "/tmp/elysia"
    assert result.tests_to_run == [
        "./scripts/test_backend.sh tests/test_code_patch_formatter.py -q"
    ]


def test_false_completed_patch_claim_blocks():
    kwargs = valid_plan_kwargs()
    kwargs["patch_plan"] = [
        "I applied the patch and committed it.",
    ]

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert any("proposed work" in error for error in result.errors)


def test_false_completed_summary_claim_blocks():
    kwargs = valid_plan_kwargs()
    kwargs["summary"] = "I applied the patch and ran the tests."

    result = format_code_patch_plan(**kwargs)

    assert result.ok is False
    assert result.status == CodePatchPlanStatus.BLOCKED
    assert any("summary must not claim" in error for error in result.errors)


def test_default_risk_and_rollback_notes_are_added_when_missing():
    kwargs = valid_plan_kwargs()
    kwargs["risk_notes"] = None
    kwargs["rollback_notes"] = None

    result = format_code_patch_plan(**kwargs)

    assert result.ok is True
    assert result.risk_notes
    assert "Review the proposed files" in result.risk_notes[0]
    assert result.rollback_notes
    assert "git diff" in result.rollback_notes[0]
    assert "git restore core/repo_context_gatherer.py tests/test_repo_context_gatherer.py" in result.rollback_notes[1]


def test_file_paths_are_normalized_and_deduplicated():
    kwargs = valid_plan_kwargs()
    kwargs["files_to_touch"] = [
        "./core/repo_context_gatherer.py",
        "core\\repo_context_gatherer.py",
        "tests/test_repo_context_gatherer.py",
    ]

    result = format_code_patch_plan(**kwargs)

    assert result.ok is True
    assert result.files_to_touch == [
        "core/repo_context_gatherer.py",
        "tests/test_repo_context_gatherer.py",
    ]


def test_payload_is_json_safe():
    payload = format_code_patch_plan(**valid_plan_kwargs()).to_payload()

    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert payload["tool_kind"] == CODE_PATCH_FORMATTER_TOOL_KIND
    assert payload["operation"] == CODE_PATCH_FORMATTER_OPERATION
    assert payload["approval_needed"] is True
    assert payload["can_apply_patch"] is False
    assert payload["patch_application_live"] is False
    assert isinstance(payload["files_to_touch"], list)
    assert isinstance(payload["patch_plan"], list)
    assert isinstance(payload["tests_to_run"], list)
    assert isinstance(payload["boundary_notes"], list)
    assert isinstance(payload["errors"], list)
