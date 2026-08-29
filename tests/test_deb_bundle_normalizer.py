from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "normalize_deb_bundle.py"
SPEC = importlib.util.spec_from_file_location("normalize_deb_bundle", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_package(
    root: Path,
    *,
    reverse_md5_order: bool,
    installed_size: int | None = None,
) -> Path:
    tree = root / "tree"
    (tree / "DEBIAN").mkdir(parents=True)
    (tree / "usr" / "share" / "elysia").mkdir(parents=True)
    (tree / "usr" / "share" / "elysia" / "a.txt").write_text("a\n", encoding="utf-8")
    (tree / "usr" / "share" / "elysia" / "b.txt").write_text("b\n", encoding="utf-8")
    installed_size_line = "" if installed_size is None else f"Installed-Size: {installed_size}\n"
    (tree / "DEBIAN" / "control").write_text(
        "Package: elysia-test\nVersion: 1.0.0\nArchitecture: all\n"
        + installed_size_line
        + "Maintainer: EcoSyneva Commons LLC\nDescription: reproducibility fixture\n",
        encoding="utf-8",
    )
    records = []
    for name in ("a.txt", "b.txt"):
        path = tree / "usr" / "share" / "elysia" / name
        records.append(f"{MODULE.hashlib.md5(path.read_bytes()).hexdigest()}  usr/share/elysia/{name}")
    if reverse_md5_order:
        records.reverse()
    (tree / "DEBIAN" / "md5sums").write_text("\n".join(records) + "\n", encoding="utf-8")
    package = root / "elysia-test.deb"
    environment = dict(os.environ, SOURCE_DATE_EPOCH="0")
    subprocess.run(
        ["dpkg-deb", "--build", "--root-owner-group", str(tree), str(package)],
        check=True,
        env=environment,
        stdout=subprocess.DEVNULL,
    )
    return package


def test_normalizer_canonicalizes_debian_record_order(tmp_path: Path, monkeypatch) -> None:
    first = make_package(tmp_path / "first", reverse_md5_order=False)
    second = make_package(tmp_path / "second", reverse_md5_order=True)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")

    first_result = MODULE.normalize(first)
    second_result = MODULE.normalize(second)

    assert first_result["sha256"] == second_result["sha256"]
    assert first.read_bytes() == second.read_bytes()


def test_normalizer_stages_atomic_replacement_beside_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = make_package(tmp_path / "external-volume", reverse_md5_order=False)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    observed: dict[str, Path] = {}
    original = MODULE.tempfile.TemporaryDirectory

    def adjacent_temporary_directory(*args, **kwargs):
        observed["dir"] = Path(kwargs["dir"])
        return original(*args, **kwargs)

    monkeypatch.setattr(MODULE.tempfile, "TemporaryDirectory", adjacent_temporary_directory)

    MODULE.normalize(package)

    assert observed["dir"] == package.parent


def test_normalizer_replaces_filesystem_dependent_installed_size(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first = make_package(
        tmp_path / "first-size",
        reverse_md5_order=False,
        installed_size=123,
    )
    second = make_package(
        tmp_path / "second-size",
        reverse_md5_order=False,
        installed_size=987654,
    )
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")

    first_result = MODULE.normalize(first)
    second_result = MODULE.normalize(second)

    assert first_result["installed_size_kib"] == second_result["installed_size_kib"]
    assert first_result["sha256"] == second_result["sha256"]
    assert first.read_bytes() == second.read_bytes()
