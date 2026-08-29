from pathlib import Path

import pytest

from app.install.python_lock_service import (
    PythonLockError,
    compare_environment_to_lock,
    compare_environment_to_locks_exact,
    merge_hash_locks,
    parse_hash_lock,
)
from scripts.verify_publication_history import built_in_private_markers


def test_every_public_python_lock_is_exact_hashed_and_private_path_free() -> None:
    for lock in Path("config/install/locks").glob("*.lock.txt"):
        pins = parse_hash_lock(lock)
        assert pins
        text = lock.read_text(encoding="utf-8")
        assert "/home/" not in text
        assert all(
            marker.decode("utf-8") not in text
            for marker in built_in_private_markers()
        )


def test_creator_cpu_and_cuda_locks_are_explicitly_separated() -> None:
    cpu = parse_hash_lock(Path("config/install/locks/creator-cpu-py312.lock.txt"))
    cuda = parse_hash_lock(Path("config/install/locks/creator-cuda-py312.lock.txt"))

    assert cpu["torch"] == "2.13.0+cpu"
    assert not any(name.startswith(("cuda", "nvidia")) for name in cpu)
    assert cuda["torch"] == "2.13.0"
    assert any(name.startswith(("cuda", "nvidia")) for name in cuda)


def test_environment_comparison_reports_missing_and_mismatch_without_mutation() -> None:
    lock = Path("config/install/locks/neurofabric-cpu-py312.lock.txt")
    pins = parse_hash_lock(lock)
    exact = dict(pins)
    assert compare_environment_to_lock(lock, installed=exact)["matches"] is True
    first = next(iter(pins))
    broken = dict(exact)
    broken[first] = "0"
    result = compare_environment_to_lock(lock, installed=broken)
    assert result["matches"] is False
    assert result["mismatched"][0]["name"] == first


def test_lock_parser_rejects_orphan_hash_blocks(tmp_path: Path) -> None:
    broken = tmp_path / "broken.lock.txt"
    broken.write_text(
        f"--hash=sha256:{'a' * 64}\n"
        "second-package==1.0 \\\n"
        f"    --hash=sha256:{'b' * 64}\n",
        encoding="utf-8",
    )
    with pytest.raises(PythonLockError, match="orphan artifact hash"):
        parse_hash_lock(broken)


def test_exact_composed_build_environment_rejects_optional_or_test_extras() -> None:
    paths = [
        Path("config/install/locks/core-py312.lock.txt"),
        Path("config/install/locks/build-py312.lock.txt"),
    ]
    pins = merge_hash_locks(paths)
    exact_with_bootstrap = {**pins, "pip": "synthetic-bootstrap"}
    result = compare_environment_to_locks_exact(
        paths,
        installed=exact_with_bootstrap,
        allowed_additional={"pip"},
    )
    assert result["matches"] is True
    assert result["additional_packages_ignored"] is False

    contaminated = {**exact_with_bootstrap, "pytest": "9.1.1", "pandas": "3.0.5"}
    result = compare_environment_to_locks_exact(
        paths,
        installed=contaminated,
        allowed_additional={"pip"},
    )
    assert result["matches"] is False
    assert result["unexpected"] == ["pandas", "pytest"]


def test_exact_lock_composition_rejects_conflicting_versions(tmp_path: Path) -> None:
    first = tmp_path / "first.lock.txt"
    second = tmp_path / "second.lock.txt"
    first.write_text(
        f"example==1.0 \\\n    --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )
    second.write_text(
        f"example==2.0 \\\n    --hash=sha256:{'b' * 64}\n",
        encoding="utf-8",
    )
    with pytest.raises(PythonLockError, match="conflict"):
        merge_hash_locks([first, second])
