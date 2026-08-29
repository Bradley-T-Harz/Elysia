from __future__ import annotations

from pathlib import Path

import pytest


yaml = pytest.importorskip("yaml")


CONFIG_PATH = Path("config/benchmarks/part3_benchmark_prompts.yaml")

REQUIRED_BENCHMARK_IDS = {
    "file_qa_001",
    "math_tutor_001",
    "data_plot_001",
    "repo_inspect_001",
    "patch_proposal_001",
    "research_evidence_001",
    "writing_grounded_calc_001",
    "project_continuity_001",
    "blocked_unsafe_001",
    "fallback_locality_approval_001",
}

REQUIRED_BENCHMARK_FIELDS = {
    "id",
    "title",
    "mode",
    "prompt",
    "expected_capabilities",
    "expected_tools_used",
    "expected_tools_not_used",
    "expected_locality",
    "expected_approval_state",
    "expected_boundary_state",
    "expected_evidence_packet_count",
    "expected_artifact_count",
    "expected_request_ledger_fields",
    "must_not_claim",
    "pass_criteria",
    "failure_signs",
}


def _load_config() -> dict:
    assert CONFIG_PATH.exists()
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


def _benchmark_by_id(data: dict) -> dict[str, dict]:
    benchmarks = data.get("benchmarks")
    assert isinstance(benchmarks, list)
    return {
        benchmark["id"]: benchmark
        for benchmark in benchmarks
        if isinstance(benchmark, dict) and isinstance(benchmark.get("id"), str)
    }


def test_part3_benchmark_config_shape_and_required_ids():
    data = _load_config()

    assert data["version"] == 1
    assert data["benchmark_suite"] == "part3_capability_organs"
    assert data["status"] == "manual_first"

    benchmarks = data.get("benchmarks")
    assert isinstance(benchmarks, list)
    assert benchmarks

    by_id = _benchmark_by_id(data)
    assert REQUIRED_BENCHMARK_IDS.issubset(set(by_id))


def test_every_part3_benchmark_has_required_fields_and_nonempty_lists():
    data = _load_config()
    by_id = _benchmark_by_id(data)

    for benchmark_id in REQUIRED_BENCHMARK_IDS:
        benchmark = by_id[benchmark_id]
        assert REQUIRED_BENCHMARK_FIELDS.issubset(set(benchmark))
        assert isinstance(benchmark["pass_criteria"], list)
        assert benchmark["pass_criteria"]
        assert isinstance(benchmark["failure_signs"], list)
        assert benchmark["failure_signs"]
        assert isinstance(benchmark["must_not_claim"], list)
        assert benchmark["must_not_claim"]


def test_blocked_unsafe_benchmark_blocks_private_web_worker_and_mutation_paths():
    benchmark = _benchmark_by_id(_load_config())["blocked_unsafe_001"]

    expected_not_used = set(benchmark["expected_tools_not_used"])
    assert {
        "bounded_public_web_research",
        "searxng_research_worker",
        "aider_worker",
        "patch_application",
        "shell_execution",
        "git_mutation",
        "vault_access",
    }.issubset(expected_not_used)
    assert (
        benchmark["expected_approval_state"] == "blocked"
        or benchmark["expected_boundary_state"] == "blocked"
    )


def test_file_qa_prohibits_web_research_and_memory_promotion():
    benchmark = _benchmark_by_id(_load_config())["file_qa_001"]

    combined = " ".join(
        list(benchmark["expected_tools_not_used"])
        + list(benchmark["must_not_claim"])
    )
    assert "web research" in combined or "bounded_public_web_research" in combined
    assert "memory" in combined


def test_research_evidence_requires_evidence_truth_and_private_context_safety():
    benchmark = _benchmark_by_id(_load_config())["research_evidence_001"]

    assert "evidence_packets" in benchmark["expected_capabilities"]
    fields_and_claims = " ".join(
        list(benchmark["expected_request_ledger_fields"])
        + list(benchmark["must_not_claim"])
    )
    assert "evidence_packet_count" in fields_and_claims
    assert "private_context_sent" in fields_and_claims or "private context" in fields_and_claims


def test_patch_proposal_prohibits_application_and_mutation_claims():
    benchmark = _benchmark_by_id(_load_config())["patch_proposal_001"]

    assert "patch_application" in benchmark["expected_tools_not_used"]
    combined = " ".join(benchmark["must_not_claim"])
    assert "patch was applied" in combined
    assert "files changed" in combined


def test_writing_grounded_calc_mentions_expected_after_value():
    benchmark = _benchmark_by_id(_load_config())["writing_grounded_calc_001"]

    combined = " ".join([benchmark["prompt"], *benchmark["pass_criteria"]])
    assert "3 060" in combined


def test_data_plot_mentions_artifact_expectations():
    benchmark = _benchmark_by_id(_load_config())["data_plot_001"]

    assert "artifact_outputs" in benchmark["expected_capabilities"]
    assert benchmark["expected_artifact_count"]
