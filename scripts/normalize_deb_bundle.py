#!/usr/bin/env python3
"""Repack Tauri's Debian bundle with deterministic ordering and metadata."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(root: Path) -> list[tuple[str, str, int, str]]:
    entries: list[tuple[str, str, int, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            entries.append((relative, "symlink", mode, path.readlink().as_posix()))
        elif path.is_file():
            entries.append((relative, "file", mode, sha256(path)))
        elif path.is_dir():
            entries.append((relative, "directory", mode, ""))
        else:
            raise ValueError(f"unsupported Debian payload entry: {relative}")
    return entries


def deterministic_installed_size_kib(root: Path) -> int:
    """Return a filesystem-independent logical payload size in KiB.

    Tauri's generated Installed-Size can inherit allocation differences from
    the build filesystem.  Debian defines the field in KiB; use the logical
    sizes of installed files and symlink payloads, rounded up once, so the
    same package tree has the same control metadata on every filesystem.
    """

    total = 0
    for path in root.rglob("*"):
        if "DEBIAN" in path.relative_to(root).parts:
            continue
        if path.is_file() or path.is_symlink():
            total += path.lstat().st_size
    return (total + 1023) // 1024


def normalize_control_installed_size(root: Path) -> int:
    control = root / "DEBIAN" / "control"
    lines = control.read_text(encoding="utf-8").splitlines()
    value = deterministic_installed_size_kib(root)
    replacement = f"Installed-Size: {value}"
    indices = [index for index, line in enumerate(lines) if line.startswith("Installed-Size:")]
    if len(indices) > 1:
        raise ValueError("Debian control contains duplicate Installed-Size fields")
    if indices:
        lines[indices[0]] = replacement
    else:
        insertion = next(
            (index + 1 for index, line in enumerate(lines) if line.startswith("Architecture:")),
            len(lines),
        )
        lines.insert(insertion, replacement)
    control.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return value


def normalize(package: Path) -> dict[str, object]:
    package = package.resolve(strict=True)
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is None or not source_date_epoch.isdigit():
        raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer")
    # The final os.replace must remain atomic. Stage beside the package so the
    # temporary file cannot land on a different filesystem and fail with
    # EXDEV when a source/build tree is outside /tmp.
    with tempfile.TemporaryDirectory(
        prefix=".elysia-deb-normalize.",
        dir=package.parent,
    ) as temporary:
        work = Path(temporary)
        tree = work / "tree"
        verify = work / "verify"
        rebuilt = work / package.name
        subprocess.run(["dpkg-deb", "--raw-extract", str(package), str(tree)], check=True)
        md5sums = tree / "DEBIAN" / "md5sums"
        lines = [line for line in md5sums.read_text(encoding="utf-8").splitlines() if line]
        if len(lines) != len(set(lines)):
            raise ValueError("Debian md5sums contains duplicate records")
        md5sums.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
        subprocess.run(
            ["md5sum", "--check", "--quiet", "DEBIAN/md5sums"],
            cwd=tree,
            check=True,
        )
        installed_size_kib = normalize_control_installed_size(tree)
        expected = snapshot(tree)
        environment = dict(os.environ)
        subprocess.run(
            [
                "dpkg-deb",
                "--build",
                "--root-owner-group",
                "--uniform-compression",
                "-Zgzip",
                "-z9",
                str(tree),
                str(rebuilt),
            ],
            check=True,
            env=environment,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["dpkg-deb", "--raw-extract", str(rebuilt), str(verify)], check=True)
        if snapshot(verify) != expected:
            raise ValueError("deterministic Debian repack changed package payload or metadata")
        mode = stat.S_IMODE(package.stat().st_mode)
        os.replace(rebuilt, package)
        package.chmod(mode)
    return {
        "contract_version": "elysia-deb-reproducibility-1.0",
        "payload_entries": len(expected),
        "installed_size_kib": installed_size_kib,
        "source_date_epoch": source_date_epoch,
        "sha256": sha256(package),
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: normalize_deb_bundle.py PACKAGE.deb")
    print(json.dumps(normalize(Path(sys.argv[1])), sort_keys=True))


if __name__ == "__main__":
    main()
