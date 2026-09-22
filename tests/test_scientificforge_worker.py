from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from sandbox.scientificforge_worker.worker import (
    ScientificWorkerError,
    run_scientific_job,
)


def _hash(path: Path) -> str:
    return sha256(
        path.read_bytes()
    ).hexdigest()


def test_descriptive_statistics_are_real():
    result = run_scientific_job(
        {
            "operation": "descriptive_stats",
            "values": [1, 2, 3, 4, 5],
        }
    )

    stats = result[
        "result"
    ]["statistics"]

    assert result["status"] == "completed"
    assert stats["count"] == 5
    assert stats["mean"] == pytest.approx(3.0)
    assert stats["median"] == pytest.approx(3.0)
    assert stats["min"] == pytest.approx(1.0)
    assert stats["max"] == pytest.approx(5.0)
    assert stats["stddev_sample"] == pytest.approx(
        2.5 ** 0.5
    )

    assert result["network_access_used"] is False
    assert result["source_mutated"] is False
    assert result["arbitrary_python_used"] is False
    assert result["shell_used"] is False


def test_matrix_multiplication_is_fixed_operation():
    result = run_scientific_job(
        {
            "operation": "matrix_multiply",
            "matrix_a": [
                [1, 2],
                [3, 4],
            ],
            "matrix_b": [
                [5, 6],
                [7, 8],
            ],
        }
    )

    assert result["result"]["matrix"] == [
        [19.0, 22.0],
        [43.0, 50.0],
    ]


def test_matrix_dimension_mismatch_is_blocked():
    with pytest.raises(
        ScientificWorkerError,
        match="matrix_dimension_mismatch",
    ):
        run_scientific_job(
            {
                "operation": "matrix_multiply",
                "matrix_a": [[1, 2]],
                "matrix_b": [[1, 2]],
            }
        )


def test_monte_carlo_is_deterministic_for_same_seed():
    job = {
        "operation": "monte_carlo_normal",
        "seed": 3407,
        "monte_carlo_samples": 5000,
        "distribution_mean": 12.0,
        "distribution_stddev": 2.5,
    }

    first = run_scientific_job(
        job
    )

    second = run_scientific_job(
        job
    )

    assert first["result"] == second["result"]
    assert first["seed_used"] == 3407
    assert second["seed_used"] == 3407


def test_stochastic_operation_refuses_missing_seed():
    with pytest.raises(
        ScientificWorkerError,
        match="explicit_seed_required",
    ):
        run_scientific_job(
            {
                "operation": "monte_carlo_normal",
                "monte_carlo_samples": 1000,
            }
        )


def test_bootstrap_is_deterministic_for_same_seed():
    job = {
        "operation": "bootstrap_mean_ci",
        "values": [1, 2, 3, 4, 5],
        "seed": 12345,
        "bootstrap_samples": 1000,
        "confidence_level": 0.95,
    }

    first = run_scientific_job(
        job
    )

    second = run_scientific_job(
        job
    )

    assert first["result"] == second["result"]


def test_source_column_uses_verified_snapshot(
    tmp_path,
):
    source = tmp_path / "input.csv"

    source.write_text(
        "site,value,other\n"
        "A,1,10\n"
        "B,2,20\n"
        "C,3,30\n",
        encoding="utf-8",
    )

    before = source.read_bytes()

    result = run_scientific_job(
        {
            "operation": "descriptive_stats",
            "source_snapshot": str(source),
            "expected_source_sha256": _hash(source),
            "columns": ["value"],
        }
    )

    assert result["result"]["column"] == "value"
    assert (
        result["result"]["statistics"]["mean"]
        == pytest.approx(2.0)
    )

    assert source.read_bytes() == before


def test_source_digest_mismatch_is_blocked(
    tmp_path,
):
    source = tmp_path / "input.csv"

    source.write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ScientificWorkerError,
        match="source_snapshot_digest_mismatch",
    ):
        run_scientific_job(
            {
                "operation": "descriptive_stats",
                "source_snapshot": str(source),
                "expected_source_sha256": "0" * 64,
                "columns": ["value"],
            }
        )


def test_correlation_uses_complete_numeric_rows(
    tmp_path,
):
    source = tmp_path / "correlation.csv"

    source.write_text(
        "a,b,c\n"
        "1,2,x\n"
        "2,4,y\n"
        "3,6,z\n"
        "4,,w\n",
        encoding="utf-8",
    )

    result = run_scientific_job(
        {
            "operation": "correlation_matrix",
            "source_snapshot": str(source),
            "expected_source_sha256": _hash(source),
            "columns": ["a", "b"],
        }
    )

    payload = result["result"]

    assert payload["complete_row_count"] == 3
    assert payload["columns"] == ["a", "b"]
    assert payload["matrix"][0][0] == pytest.approx(1.0)
    assert payload["matrix"][0][1] == pytest.approx(1.0)
    assert payload["matrix"][1][0] == pytest.approx(1.0)
    assert payload["matrix"][1][1] == pytest.approx(1.0)


def test_arbitrary_operation_name_is_not_an_execution_surface():
    with pytest.raises(
        ScientificWorkerError,
        match="unsupported_scientific_operation",
    ):
        run_scientific_job(
            {
                "operation": "__import__('os').system('id')",
                "values": [1],
            }
        )


def test_bootstrap_total_work_is_bounded():
    with pytest.raises(
        ScientificWorkerError,
        match="bootstrap_work_limit_exceeded",
    ):
        run_scientific_job(
            {
                "operation": "bootstrap_mean_ci",
                "values": list(range(10_000)),
                "seed": 123,
                "bootstrap_samples": 1000,
            }
        )
