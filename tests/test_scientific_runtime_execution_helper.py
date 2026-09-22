from __future__ import annotations

from app.api.schemas.scientific_workspace import (
    ScientificWorkspaceExecutionResult,
)
from core import runtime


def _plan():
    return {
        "bounded_scientific_execution_candidate": True,
        "scientific_execution_operation": "descriptive_stats",
        "scientific_workspace_relative_path": "measurements.csv",
        "scientific_execution_columns": ["value"],
        "scientific_execution_seed": None,
        "scientific_execution_bootstrap_samples": 10_000,
        "scientific_execution_confidence_level": 0.95,
    }


def _context():
    return {
        "project_id": "project-alpha",
        "request_id": "request-alpha",
        "scientific_workspace_selection": {
            "workspace_root": "/private/approved/science",
            "relative_path": "measurements.csv",
            "columns": ["value"],
            "operation": "descriptive_stats",
        },
    }


def _policy():
    return {
        "allowed": True,
        "boundary_flags": [
            "bounded_local_scientific_execution",
        ],
    }


def test_request_builder_uses_context_root_not_planner_root():
    plan = _plan()
    plan["scientific_workspace_root"] = "/attacker/planner/root"

    request = (
        runtime._build_scientific_execution_request_from_plan(
            plan=plan,
            context=_context(),
        )
    )

    assert request is not None

    assert (
        request.workspace_root
        == "/private/approved/science"
    )

    assert (
        request.relative_path
        == "measurements.csv"
    )

    assert request.project_id == "project-alpha"


def test_request_builder_rejects_selection_plan_path_mismatch():
    plan = _plan()

    context = _context()
    context["scientific_workspace_selection"][
        "relative_path"
    ] = "different.csv"

    request = (
        runtime._build_scientific_execution_request_from_plan(
            plan=plan,
            context=context,
        )
    )

    assert request is None


def test_scientific_lane_requires_policy_boundary():
    assert (
        runtime._should_run_bounded_scientific_execution(
            plan=_plan(),
            policy_review=_policy(),
        )
        is True
    )

    blocked = {
        "allowed": True,
        "boundary_flags": [],
    }

    assert (
        runtime._should_run_bounded_scientific_execution(
            plan=_plan(),
            policy_review=blocked,
        )
        is False
    )


def test_runtime_scientific_helper_returns_safe_payload_and_context(
    monkeypatch,
):
    observed = {}

    def fake_run(request):
        observed["request"] = request

        return ScientificWorkspaceExecutionResult(
            status="completed",
            ok=True,
            project_id="project-alpha",
            workspace_root_hash="abc123",
            relative_path="measurements.csv",
            source_type_id="csv_table",
            source_category="tabular",
            staged_file_id="file_1234567890abcdef",
            scientific_operation="descriptive_stats",
            scientific_job_id="scientificjob_test",
            result={
                "count": 2,
                "mean": 1.5,
            },
            provenance={
                "parameter_sha256": "a" * 64,
                "result_sha256": "b" * 64,
                "deterministic": True,
            },
            source_mutated=False,
            network_used=False,
            shell_used=False,
            raw_absolute_path_exposed=False,
        )

    monkeypatch.setattr(
        runtime,
        "run_scientific_workspace_execution",
        fake_run,
    )

    payload, context_block = (
        runtime._run_bounded_scientific_execution_if_needed(
            plan=_plan(),
            policy_review=_policy(),
            context=_context(),
        )
    )

    assert payload["used"] is True
    assert payload["status"] == "completed"
    assert payload["tool_kind"] == "scientificforge"

    assert payload["result"]["mean"] == 1.5

    assert payload["source_mutated"] is False
    assert payload["network_used"] is False
    assert payload["shell_used"] is False
    assert (
        payload["raw_absolute_path_exposed"]
        is False
    )

    assert (
        observed["request"].workspace_root
        == "/private/approved/science"
    )

    assert (
        "/private/approved/science"
        not in repr(payload)
    )

    assert (
        "/private/approved/science"
        not in context_block
    )

    assert (
        "Governed ScientificForge result:"
        in context_block
    )

    assert (
        "measurements.csv"
        in context_block
    )

    assert (
        "aaaaaaaa"
        in context_block
    )


def test_runtime_scientific_helper_propagates_blocked_truth(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime,
        "run_scientific_workspace_execution",
        lambda request: ScientificWorkspaceExecutionResult(
            status="blocked",
            ok=False,
            project_id="project-alpha",
            workspace_root_hash="abc123",
            relative_path="measurements.csv",
            source_type_id="csv_table",
            source_category="tabular",
            scientific_operation="descriptive_stats",
            errors=[
                "emergency_stop_active"
            ],
        ),
    )

    payload, context_block = (
        runtime._run_bounded_scientific_execution_if_needed(
            plan=_plan(),
            policy_review=_policy(),
            context=_context(),
        )
    )

    assert payload["used"] is True
    assert payload["status"] == "blocked"
    assert (
        "emergency_stop_active"
        in payload["errors"]
    )

    assert (
        "emergency_stop_active"
        in context_block
    )


def test_model_context_includes_scientific_guidance_without_root():
    scientific = (
        "Governed ScientificForge result:\n"
        "- Status: completed\n"
        "- Operation: descriptive_stats\n"
        "- Source: measurements.csv"
    )

    summary = runtime._build_model_context_summary(
        context={},
        math_execution_context_block="",
        data_execution_context_block="",
        scientific_execution_context_block=scientific,
        mode="researcher",
        plan={
            "bounded_scientific_execution_candidate": True,
        },
    )

    assert (
        "Mode-specific governed scientific response guidance:"
        in summary
    )

    assert (
        "Governed ScientificForge result:"
        in summary
    )

    assert (
        "/private/approved/science"
        not in summary
    )


def test_model_routing_receives_scientific_presence_flag():
    flags = (
        runtime._build_model_routing_context_flags(
            plan={},
            policy_review={
                "boundary_flags": [
                    "bounded_local_scientific_execution"
                ]
            },
        )
    )

    assert (
        "bounded_scientific_execution_present"
        in flags
    )
