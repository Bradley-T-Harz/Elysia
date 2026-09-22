from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.api import file_ingest_service as ingest


def test_cancel_before_ingest_creates_no_ingest_authority(
    tmp_path: Path,
):
    source = tmp_path / "measurements.csv"
    source.write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    ingest_root = tmp_path / "ingest"

    result = ingest.attach_file(
        source,
        project_id="project-alpha",
        ingest_root=ingest_root,
        cancel_check=lambda: True,
    )

    assert result.blocked is True
    assert result.ready is False
    assert "file_ingest_cancelled" in result.errors
    assert not ingest_root.exists()


def test_cancel_during_source_hash_prevents_ingest_commit(
    tmp_path: Path,
):
    source = tmp_path / "measurements.csv"
    source.write_bytes(
        b"value\n"
        + b"1\n" * 100
    )

    ingest_root = tmp_path / "ingest"

    calls = {"count": 0}

    def cancel():
        calls["count"] += 1
        return calls["count"] >= 2

    result = ingest.attach_file(
        source,
        project_id="project-alpha",
        ingest_root=ingest_root,
        cancel_check=cancel,
    )

    assert result.blocked is True
    assert "file_ingest_cancelled" in result.errors
    assert not ingest_root.exists()


def test_cancel_during_atomic_copy_leaves_no_target_or_temp(
    tmp_path: Path,
):
    source = tmp_path / "large.csv"
    source.write_bytes(
        b"value\n"
        + b"1\n" * 1_200_000
    )

    target_root = tmp_path / "raw"
    target_root.mkdir()

    target = target_root / "large.csv"

    expected_sha256 = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()

    calls = {"count": 0}

    def cancel():
        calls["count"] += 1
        return calls["count"] >= 3

    with pytest.raises(
        ingest.FileIngestCancelled
    ):
        ingest._copy_data_file_cancellable(
            source=source,
            target=target,
            expected_sha256=expected_sha256,
            cancel_check=cancel,
        )

    assert not target.exists()
    assert not list(
        target_root.glob(
            ".scientific-ingest-*.tmp"
        )
    )


def test_default_csv_ingest_still_succeeds(
    tmp_path: Path,
):
    source = tmp_path / "measurements.csv"
    source.write_text(
        "site,value\nalpha,1\nbeta,2\n",
        encoding="utf-8",
    )

    ingest_root = tmp_path / "ingest"

    result = ingest.attach_file(
        source,
        project_id="project-alpha",
        ingest_root=ingest_root,
    )

    assert result.accepted is True
    assert result.ready is True
    assert result.blocked is False

    assert result.file is not None
    assert (
        result.file.source_project_id
        == "project-alpha"
    )

    raw = (
        ingest_root
        / "raw"
        / result.file_id
        / source.name
    )

    assert raw.is_file()
    assert raw.read_bytes() == source.read_bytes()
    assert raw.stat().st_nlink == 1
