from __future__ import annotations

import asyncio

from app.api.routes.code import apply_patch, run_focused_test


def _assert_validation_envelope(payload: dict, *, result_type: str, path: str) -> None:
    assert payload["status"] == "error"
    assert payload["result_type"] == result_type
    assert payload["approval_state"] == "needed"
    assert payload["trace_summary"]["route_used"] == f"code.{result_type}"
    assert payload["errors"]

    data = payload["data"]
    assert data["validation_error"] is True
    assert data["path"] == path
    assert data["approval_required"] is True
    assert data["patch_applied"] is False
    assert data["command_executed"] is False
    assert data["mutated_files"] is False
    assert data["shell_used"] is False
    assert data["broad_shell_used"] is False
    assert data["git_mutation_used"] is False
    assert data["network_access_used"] is False
    assert data["private_context_sent"] is False


def test_code_patch_route_rejects_non_object_body_with_envelope():
    payload = asyncio.run(apply_patch(["not", "object"]))

    _assert_validation_envelope(
        payload,
        result_type="code_patch_apply_validation_error",
        path="/code/patch/apply",
    )
    assert "JSON object" in " ".join(payload["errors"])


def test_code_command_route_rejects_non_object_body_with_envelope():
    payload = asyncio.run(run_focused_test(["not", "object"]))

    _assert_validation_envelope(
        payload,
        result_type="focused_command_validation_error",
        path="/code/tests/run",
    )
    assert "JSON object" in " ".join(payload["errors"])


def test_code_patch_route_rejects_empty_object_with_validation_envelope():
    payload = asyncio.run(apply_patch({}))

    _assert_validation_envelope(
        payload,
        result_type="code_patch_apply_validation_error",
        path="/code/patch/apply",
    )
    assert payload["result_type"] != "bridge_error"
    assert "Field required" in " ".join(payload["errors"])


def test_code_command_route_rejects_empty_object_with_validation_envelope():
    payload = asyncio.run(run_focused_test({}))

    _assert_validation_envelope(
        payload,
        result_type="focused_command_validation_error",
        path="/code/tests/run",
    )
    assert payload["result_type"] != "bridge_error"
    assert "Field required" in " ".join(payload["errors"])
