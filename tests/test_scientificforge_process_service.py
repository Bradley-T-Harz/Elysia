from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys
from threading import Event, Thread
import time

import pytest

pytestmark = pytest.mark.usefixtures("safe_resource_samples")

from app.api.scientificforge_process_service import (
    _bounded_process,
    _minimal_environment,
    copy_verified_source_snapshot,
    run_scientific_worker_process,
)
from app.api.scientificforge_source_service import (
    VerifiedScientificSource,
)


def _source(
    path: Path,
) -> VerifiedScientificSource:
    raw = path.read_bytes()

    return VerifiedScientificSource(
        file_id=(
            "file_"
            + sha256(raw).hexdigest()[:16]
        ),
        display_name=path.name,
        file_kind=path.suffix.lstrip("."),
        source_path=path,
        sha256=sha256(raw).hexdigest(),
        size_bytes=len(raw),
    )


def test_private_snapshot_preserves_exact_bytes(
    tmp_path,
):
    source_path = tmp_path / "input.csv"

    source_path.write_text(
        "value\n1\n2\n3\n",
        encoding="utf-8",
    )

    source = _source(
        source_path
    )

    job_root = tmp_path / "job"

    snapshot = (
        copy_verified_source_snapshot(
            source,
            job_root,
        )
    )

    assert snapshot != source_path
    assert snapshot.name == "source.csv"
    assert snapshot.read_bytes() == source_path.read_bytes()
    assert snapshot.stat().st_nlink == 1


def test_snapshot_refuses_changed_source(
    tmp_path,
):
    source_path = tmp_path / "input.csv"

    source_path.write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    source = _source(
        source_path
    )

    source_path.write_text(
        "value\n999\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError,
        match="scientific_source_size_changed|scientific_snapshot_digest_mismatch",
    ):
        copy_verified_source_snapshot(
            source,
            tmp_path / "job",
        )


def test_real_sleeping_process_is_cancelled(
    tmp_path,
):
    cancelled = Event()

    def trigger():
        time.sleep(
            0.2
        )
        cancelled.set()

    thread = Thread(
        target=trigger,
        daemon=True,
    )

    thread.start()

    started = time.monotonic()

    _, _, _, failure = _bounded_process(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(20)",
        ],
        cwd=tmp_path,
        environment=_minimal_environment(
            tmp_path
        ),
        cancel_event=cancelled,
        timeout_seconds=10,
    )

    elapsed = (
        time.monotonic()
        - started
    )

    thread.join(
        timeout=1
    )

    assert failure == "worker_cancelled"
    assert elapsed < 5


def test_fixed_worker_process_runs_matrix_operation():
    result = run_scientific_worker_process(
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

    assert result["status"] == "completed"

    assert result["result"]["matrix"] == [
        [19.0, 22.0],
        [43.0, 50.0],
    ]

    assert result["network_access_used"] is False
    assert result["source_mutated"] is False
    assert result["arbitrary_python_used"] is False
    assert result["shell_used"] is False


def test_fixed_worker_process_receives_snapshot_not_original(
    tmp_path,
):
    source_path = tmp_path / "original.csv"

    source_path.write_text(
        "site,value\n"
        "A,1\n"
        "B,2\n"
        "C,3\n",
        encoding="utf-8",
    )

    before = source_path.read_bytes()

    result = run_scientific_worker_process(
        {
            "operation": "descriptive_stats",
            "columns": ["value"],
        },
        source=_source(
            source_path
        ),
    )

    assert result["status"] == "completed"

    assert (
        result["result"]["statistics"]["mean"]
        == pytest.approx(2.0)
    )

    assert source_path.read_bytes() == before


def test_fixed_worker_process_propagates_structured_refusal():
    result = run_scientific_worker_process(
        {
            "operation": "monte_carlo_normal",
            "monte_carlo_samples": 1000,
        }
    )

    assert result["status"] == "blocked"

    assert (
        result["blocked_reason"]
        == "explicit_seed_required"
    )


def test_snapshot_honors_preexisting_cancellation(
    tmp_path,
):
    source_path = tmp_path / "cancel.csv"

    source_path.write_text(
        "value\n1\n2\n3\n",
        encoding="utf-8",
    )

    cancel = Event()
    cancel.set()

    job_root = tmp_path / "cancel-job"

    with pytest.raises(
        RuntimeError,
        match="scientific_snapshot_cancelled",
    ):
        copy_verified_source_snapshot(
            _source(source_path),
            job_root,
            cancel_event=cancel,
        )

    assert not (
        job_root / "source.csv"
    ).exists()
