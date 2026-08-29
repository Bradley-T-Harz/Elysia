from pathlib import Path

import pytest

from app.install.python_artifact_resolver import (
    PythonArtifactResolutionError,
    parse_locked_requirements,
)


def test_lock_resolution_input_preserves_indexes_versions_and_all_hashes(tmp_path: Path) -> None:
    lock = tmp_path / "profile.lock"
    lock.write_text(
        "--index-url https://pypi.org/simple\n"
        "--extra-index-url https://download.pytorch.org/whl/cpu\n\n"
        "Demo_Pkg==1.2.3 \\\n"
        "    --hash=sha256:" + "a" * 64 + " \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n",
        encoding="utf-8",
    )
    indexes, rows = parse_locked_requirements(lock)
    assert indexes == ["https://pypi.org/simple", "https://download.pytorch.org/whl/cpu"]
    assert [(row.name, row.version) for row in rows] == [("demo-pkg", "1.2.3")]
    assert rows[0].hashes == {"a" * 64, "b" * 64}


def test_lock_resolution_rejects_orphan_and_unhashed_pins(tmp_path: Path) -> None:
    orphan = tmp_path / "orphan.lock"
    orphan.write_text("--hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    with pytest.raises(PythonArtifactResolutionError, match="orphan"):
        parse_locked_requirements(orphan)

    unhashed = tmp_path / "unhashed.lock"
    unhashed.write_text("demo==1.0\n", encoding="utf-8")
    with pytest.raises(PythonArtifactResolutionError, match="no artifact hash"):
        parse_locked_requirements(unhashed)
