from core.planner import (
    _detect_bounded_scientific_execution_candidate,
)
from core.policy_gate import evaluate_plan
from core.verifier import verify_result


def _selection(
    *,
    operation="descriptive_stats",
    columns=None,
    seed=None,
):
    payload = {
        "workspace_root": "/private/approved-science-root",
        "relative_path": "measurements.csv",
        "columns": columns or ["value"],
    }

    if operation is not None:
        payload["operation"] = operation

    if seed is not None:
        payload["seed"] = seed

    return payload


def test_planner_detects_explicit_scientific_workspace_candidate_without_copying_root():
    fields = _detect_bounded_scientific_execution_candidate(
        intent={"primary": "research"},
        mode="researcher",
        context={
            "request_summary": (
                "Run descriptive statistics on the selected scientific dataset."
            ),
            "project_id": "project-alpha",
            "scientific_workspace_selection": _selection(),
        },
    )

    assert fields["bounded_scientific_execution_candidate"] is True
    assert fields["scientific_execution_operation"] == "descriptive_stats"
    assert fields["scientific_workspace_relative_path"] == "measurements.csv"
    assert fields["scientific_execution_columns"] == ["value"]

    assert "workspace_root" not in fields
    assert "/private/approved-science-root" not in repr(fields)


def test_planner_can_infer_correlation_but_requires_valid_columns():
    fields = _detect_bounded_scientific_execution_candidate(
        intent={"primary": "research"},
        mode="researcher",
        context={
            "request_summary": (
                "Compute the correlation matrix for the selected data."
            ),
            "project_id": "project-alpha",
            "scientific_workspace_selection": _selection(
                operation=None,
                columns=["flow", "temperature"],
            ),
        },
    )

    assert fields["bounded_scientific_execution_candidate"] is True
    assert fields["scientific_execution_operation"] == "correlation_matrix"

    invalid = _detect_bounded_scientific_execution_candidate(
        intent={"primary": "research"},
        mode="researcher",
        context={
            "request_summary": (
                "Compute the correlation matrix for the selected data."
            ),
            "project_id": "project-alpha",
            "scientific_workspace_selection": _selection(
                operation=None,
                columns=["flow"],
            ),
        },
    )

    assert invalid["bounded_scientific_execution_candidate"] is False
    assert (
        invalid["scientific_execution_reason"]
        == "scientific_correlation_requires_2_to_16_columns"
    )


def test_planner_requires_project_and_explicit_workspace_selection():
    missing_project = _detect_bounded_scientific_execution_candidate(
        intent={"primary": "research"},
        mode="researcher",
        context={
            "request_summary": (
                "Run descriptive statistics on the selected data."
            ),
            "scientific_workspace_selection": _selection(),
        },
    )

    assert missing_project["bounded_scientific_execution_candidate"] is False

    missing_selection = _detect_bounded_scientific_execution_candidate(
        intent={"primary": "research"},
        mode="researcher",
        context={
            "request_summary": (
                "Run descriptive statistics on the selected data."
            ),
            "project_id": "project-alpha",
        },
    )

    assert missing_selection["bounded_scientific_execution_candidate"] is False


def test_bootstrap_requires_explicit_seed():
    blocked = _detect_bounded_scientific_execution_candidate(
        intent={"primary": "research"},
        mode="researcher",
        context={
            "request_summary": (
                "Bootstrap a confidence interval for the selected data."
            ),
            "project_id": "project-alpha",
            "scientific_workspace_selection": _selection(
                operation="bootstrap_mean_ci",
                columns=["value"],
            ),
        },
    )

    assert blocked["bounded_scientific_execution_candidate"] is False
    assert (
        blocked["scientific_execution_reason"]
        == "scientific_stochastic_operation_requires_seed"
    )

    allowed = _detect_bounded_scientific_execution_candidate(
        intent={"primary": "research"},
        mode="researcher",
        context={
            "request_summary": (
                "Bootstrap a confidence interval for the selected data."
            ),
            "project_id": "project-alpha",
            "scientific_workspace_selection": _selection(
                operation="bootstrap_mean_ci",
                columns=["value"],
                seed=17,
            ),
        },
    )

    assert allowed["bounded_scientific_execution_candidate"] is True
    assert allowed["scientific_execution_seed"] == 17


def test_policy_treats_bounded_scientific_lane_as_governed_local_compute():
    review = evaluate_plan(
        {
            "steps": ["run bounded science"],
            "requires_tools": False,
            "touches_external_network": False,
            "writes_files": False,
            "reads_private_memory": False,
            "execution_allowed": False,
            "bounded_math_execution_candidate": False,
            "bounded_data_execution_candidate": False,
            "bounded_scientific_execution_candidate": True,
            "repo_context_candidate": False,
            "code_patch_plan_candidate": False,
            "hard_blocked_request": False,
            "risk_level": "low",
        }
    )

    assert review["allowed"] is True
    assert review["approval_required"] is False
    assert (
        "bounded_local_scientific_execution"
        in review["boundary_flags"]
    )


def test_verifier_requires_scientific_result_and_provenance_truth():
    plan = {
        "intent": "research",
        "mode": "researcher",
        "retrieved_memory_count": 0,
        "uses_memory_context": False,
        "memory_context_source": "unknown",
        "reads_private_memory": False,
        "memory_class": "",
        "primary_memory_class": "",
        "forced_memory_class": "",
        "memory_class_source": "",
        "memory_class_declared": False,
        "memory_class_boundary_sensitive": False,
        "memory_class_requires_boundary_check": False,
        "bounded_math_execution_candidate": False,
        "bounded_data_execution_candidate": False,
        "bounded_scientific_execution_candidate": True,
        "repo_context_candidate": False,
        "code_patch_plan_candidate": False,
        "research_ticket_candidate": False,
    }

    result = verify_result(
        plan,
        {
            "status": "ok",
            "note": "Scientific execution completed.",
            "scientific_execution": {
                "used": True,
                "status": "completed",
                "result": {
                    "mean": 2.5,
                },
                "provenance": {
                    "parameter_sha256": "a" * 64,
                    "result_sha256": "b" * 64,
                },
                "source_mutated": False,
                "network_used": False,
                "shell_used": False,
                "raw_absolute_path_exposed": False,
            },
        },
    )

    assert "scientific_execution_summary_present" in result["checks_passed"]
    assert "scientific_execution_provenance_present" in result["checks_passed"]
    assert not any(
        "scientific execution" in issue.lower()
        for issue in result["issues"]
    )


def test_verifier_rejects_missing_scientific_execution():
    plan = {
        "intent": "research",
        "mode": "researcher",
        "retrieved_memory_count": 0,
        "uses_memory_context": False,
        "memory_context_source": "unknown",
        "reads_private_memory": False,
        "memory_class": "",
        "primary_memory_class": "",
        "forced_memory_class": "",
        "memory_class_source": "",
        "memory_class_declared": False,
        "memory_class_boundary_sensitive": False,
        "memory_class_requires_boundary_check": False,
        "bounded_math_execution_candidate": False,
        "bounded_data_execution_candidate": False,
        "bounded_scientific_execution_candidate": True,
        "repo_context_candidate": False,
        "code_patch_plan_candidate": False,
        "research_ticket_candidate": False,
    }

    result = verify_result(
        plan,
        {
            "status": "ok",
            "note": "No scientific receipt supplied.",
        },
    )

    assert any(
        "bounded scientific execution" in issue.lower()
        for issue in result["issues"]
    )
