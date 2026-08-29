#!/usr/bin/env python3
"""Generate native-library notices from an assembled Elysia AppImage AppDir.

The AppImage bundler copies GTK/WebKit and their native dependencies. This
local-only guard maps every top-level bundled shared object back to the native
Debian package that supplied it and includes that package's installed copyright
record. It fails closed when a library or copyright record cannot be resolved.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path


def command(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def elf_build_id(path: Path) -> str:
    result = subprocess.run(
        ["readelf", "-n", str(path)],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    match = re.search(r"Build ID:\s*([0-9a-f]+)", result.stdout, re.IGNORECASE)
    return match.group(1).lower() if match else ""


def copyright_text(path: Path) -> str:
    resolved = path.resolve(strict=True)
    if resolved.suffix == ".gz":
        with gzip.open(resolved, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    return resolved.read_text(encoding="utf-8", errors="replace")


def owners_for_libraries(libraries: list[Path], architecture: str, multiarch: str) -> dict[str, str]:
    names = [library.name for library in libraries]
    bundled_by_name = {library.name: library for library in libraries}
    matches = command(
        "dpkg-query",
        "-S",
        f"/usr/lib/{multiarch}/lib*.so*",
        f"/usr/lib/{multiarch}/*/lib*.so*",
        f"/usr/lib/{multiarch}/*/*/lib*.so*",
        f"/lib/{multiarch}/lib*.so*",
    ).splitlines()
    native: dict[str, list[tuple[str, str]]] = defaultdict(list)
    fallback: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for line in matches:
        if ": " not in line:
            continue
        package_spec, installed_path = line.split(": ", 1)
        package = package_spec.rsplit(":", 1)[0]
        name = Path(installed_path).name
        if name not in names:
            continue
        fallback[name].append((package, installed_path))
        if package_spec.endswith(f":{architecture}") and f"/{multiarch}/{name}" in installed_path:
            native[name].append((package, installed_path))
    owners: dict[str, str] = {}
    for name in names:
        records = native[name] or fallback[name]
        exact = []
        bundled_hash = sha256(bundled_by_name[name])
        bundled_build_id = elf_build_id(bundled_by_name[name])
        for package, installed_path in records:
            candidate = Path(installed_path)
            if candidate.exists() and (
                sha256(candidate) == bundled_hash
                or bool(bundled_build_id and elf_build_id(candidate) == bundled_build_id)
            ):
                exact.append(package)
        candidates = sorted(set(exact or [package for package, _ in records]))
        if len(candidates) != 1:
            raise RuntimeError(f"{name}: expected one native owner, got {candidates}")
        owners[name] = candidates[0]
    return owners


def package_fact(package: str, architecture: str) -> tuple[str, str, str]:
    raw = command(
        "dpkg-query",
        "-W",
        "-f=${Version}\\t${source:Package}\\t${source:Version}",
        f"{package}:{architecture}",
    ).strip()
    rows = {
        tuple(line.split("\t"))
        for line in raw.splitlines()
        if line.strip()
    }
    if len(rows) != 1:
        raise RuntimeError(f"{package}:{architecture}: expected one package fact, got {sorted(rows)}")
    row = rows.pop()
    if len(row) != 3:
        raise RuntimeError(f"{package}:{architecture}: malformed package fact")
    version, source, source_version = row
    return version, source or package, source_version or version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--appdir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-json", type=Path)
    args = parser.parse_args()

    library_dir = args.appdir.resolve() / "usr/lib"
    libraries = sorted(path for path in library_dir.glob("lib*.so*") if path.is_file())
    if not libraries:
        raise SystemExit(f"no bundled shared libraries found in {library_dir}")

    architecture = command("dpkg", "--print-architecture").strip()
    multiarch = command("dpkg-architecture", "-qDEB_HOST_MULTIARCH").strip()
    by_package: dict[str, list[Path]] = defaultdict(list)
    try:
        owners = owners_for_libraries(libraries, architecture, multiarch)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"unresolved AppImage library owner: {error}") from error
    for library in libraries:
        by_package[owners[library.name]].append(library)

    sections = [
        "Elysia AppImage native-library notices",
        "=======================================",
        "",
        "Generated locally from the exact assembled AppDir. Each bundled shared",
        "object is mapped to its installed Debian package and the package's full",
        "copyright/license record is reproduced below.",
        "",
    ]
    evidence: list[dict[str, object]] = []
    for package in sorted(by_package):
        version, source, source_version = package_fact(package, architecture)
        copyright_path = Path("/usr/share/doc") / package / "copyright"
        try:
            legal_text = copyright_text(copyright_path).rstrip()
        except OSError as error:
            raise SystemExit(f"{package}: missing readable copyright record: {error}") from error
        names = sorted(path.name for path in by_package[package])
        sections.extend(
            [
                "-" * 78,
                f"Binary package: {package}",
                f"Binary version: {version}",
                f"Source package: {source}",
                f"Source version: {source_version}",
                f"Bundled files: {', '.join(names)}",
                f"Installed copyright record: {copyright_path}",
                "",
                legal_text,
                "",
            ]
        )
        evidence.append(
            {
                "binary_package": package,
                "binary_version": version,
                "source_package": source,
                "source_version": source_version,
                "bundled_files": names,
                "copyright_path": str(copyright_path),
                "copyright_sha256": hashlib.sha256((legal_text + "\n").encode()).hexdigest(),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    if args.evidence_json:
        args.evidence_json.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_json.write_text(
            json.dumps(
                {
                    "architecture": architecture,
                    "appdir": str(args.appdir.resolve()),
                    "library_count": len(libraries),
                    "package_count": len(by_package),
                    "notice_sha256": sha256(args.output),
                    "packages": evidence,
                    "unresolved": [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"mapped {len(libraries)} AppImage libraries to {len(by_package)} native packages; unresolved=0")


if __name__ == "__main__":
    main()
