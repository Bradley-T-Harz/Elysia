from __future__ import annotations

from pathlib import Path

import pytest


yaml = pytest.importorskip("yaml")


CONFIG_PATH = Path("config/benchmarks/elysia_1_0_competition_suite.yaml")

REQUIRED_BENCHMARK_IDS = {
    "file_qa_local_context",
    "math_tutoring_stepwise",
    "table_data_plot_artifact",
    "code_inspection_repo_context",
    "patch_proposal_no_mutation",
    "bounded_web_research_evidence",
    "writing_with_calculation",
    "project_continuity_summary",
    "unsafe_refusal_no_tools",
    "mode_switching_posture",
    "evidence_contradiction_scan",
    "fallback_locality_truth",
    "ui_truth_request_trace",
}

REQUIRED_BENCHMARK_FIELDS = {
    "id",
    "title",
    "mode",
    "prompt",
    "setup_required",
    "expected_organs",
    "expected_trace_truth",
    "pass_criteria",
    "failure_signs",
    "must_not_claim",
    "manual_ui_checks",
    "comparison_notes",
}


def _load_config() -> dict:
    assert CONFIG_PATH.exists()
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


def _benchmarks(data: dict) -> list[dict]:
    benchmarks = data.get("benchmarks")
    assert isinstance(benchmarks, list)
    assert benchmarks
    assert all(isinstance(item, dict) for item in benchmarks)
    return benchmarks


def _by_id(data: dict) -> dict[str, dict]:
    return {item["id"]: item for item in _benchmarks(data)}


def test_competition_suite_yaml_exists_and_parses():
    data = _load_config()

    assert data["version"] == 1
    assert data["benchmark_suite"] == "elysia_1_0_competition"
    assert data["status"] == "manual_first"
    assert data["global_rules"]["private_context_to_external_models_allowed"] is False


def test_required_benchmark_ids_exist_and_are_unique():
    benchmarks = _benchmarks(_load_config())
    ids = [item.get("id") for item in benchmarks]

    assert len(ids) == len(set(ids))
    assert set(ids) == REQUIRED_BENCHMARK_IDS


def test_each_benchmark_has_required_fields_and_non_empty_criteria():
    for benchmark in _benchmarks(_load_config()):
        assert REQUIRED_BENCHMARK_FIELDS.issubset(set(benchmark))
        assert isinstance(benchmark["expected_organs"], list)
        assert benchmark["expected_organs"]
        assert isinstance(benchmark["pass_criteria"], list)
        assert benchmark["pass_criteria"]
        assert isinstance(benchmark["failure_signs"], list)
        assert benchmark["failure_signs"]
        assert isinstance(benchmark["manual_ui_checks"], list)
        assert benchmark["manual_ui_checks"]
        assert isinstance(benchmark["must_not_claim"], list)
        assert benchmark["must_not_claim"]


def test_unsafe_refusal_benchmark_requires_no_tools_or_mutation():
    benchmark = _by_id(_load_config())["unsafe_refusal_no_tools"]
    combined = " ".join(
        benchmark["expected_trace_truth"]
        + benchmark["pass_criteria"]
        + benchmark["failure_signs"]
        + benchmark["must_not_claim"]
    )

    assert "mutated_files false" in combined
    assert "network_access_used false" in combined
    assert "shell_used false" in combined
    assert "git_mutation_used false" in combined
    assert "Aider was invoked" in combined
    assert "vault was accessed" in combined


def test_research_benchmark_requires_evidence_and_private_context_boundaries():
    benchmark = _by_id(_load_config())["bounded_web_research_evidence"]
    combined = " ".join(
        benchmark["expected_organs"]
        + benchmark["expected_trace_truth"]
        + benchmark["pass_criteria"]
        + benchmark["failure_signs"]
        + benchmark["must_not_claim"]
    )

    assert "evidence_packets" in benchmark["expected_organs"]
    assert "private_context_sent false" in combined
    assert "fake search results" in combined
    assert "SearXNG is unavailable" in combined or "SearXNG is disabled" in combined


def test_patch_benchmark_requires_no_mutation_without_approval():
    benchmark = _by_id(_load_config())["patch_proposal_no_mutation"]
    combined = " ".join(
        benchmark["expected_trace_truth"]
        + benchmark["pass_criteria"]
        + benchmark["failure_signs"]
        + benchmark["must_not_claim"]
    )

    assert "approval_required true" in combined
    assert "mutated_files false" in combined
    assert "patch was applied" in combined
    assert "git mutation occurred" in combined


def test_fallback_benchmark_requires_no_silent_cloud_fallback():
    benchmark = _by_id(_load_config())["fallback_locality_truth"]
    combined = " ".join(
        benchmark["expected_organs"]
        + benchmark["expected_trace_truth"]
        + benchmark["failure_signs"]
        + benchmark["must_not_claim"]
    )

    assert "used_fallback visible" in combined
    assert "locality_state local" in combined
    assert "network_access_used false" in combined
    assert "silent cloud fallback occurred" in combined


def test_external_comparison_notes_preserve_privacy():
    for benchmark in _benchmarks(_load_config()):
        notes = " ".join(benchmark["comparison_notes"])
        if benchmark["id"] in {
            "file_qa_local_context",
            "code_inspection_repo_context",
            "project_continuity_summary",
            "bounded_web_research_evidence",
        }:
            assert "private" in notes.lower() or "sanitized" in notes.lower()
