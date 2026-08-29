#!/usr/bin/env python3
"""Build a deterministic reviewed-source archive from tracked files only."""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import io
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "packaging/public_manifest.yaml"


def _manifest() -> dict[str, Any]:
    payload = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("public_manifest_invalid")
    return payload


def _tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    return sorted(
        item.decode("utf-8")
        for item in completed.stdout.split(b"\0")
        if item
    )


def _matches(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)


def _under_reviewed_root(relative: str, roots: set[str]) -> bool:
    """Match both top-level and explicitly nested reviewed-source roots."""

    return any(relative == root or relative.startswith(f"{root}/") for root in roots)


def reviewed_files(payload: dict[str, Any]) -> list[str]:
    source = payload.get("reviewed_source")
    if not isinstance(source, dict):
        raise ValueError("reviewed_source_contract_missing")
    include_roots = {
        str(value).strip("/")
        for value in source.get("include_roots", [])
        if str(value).strip("/")
    }
    required = {str(value) for value in source.get("required_root_files", [])}
    excluded = [str(value) for value in source.get("exclude_globs", [])]
    denied = [str(value) for value in payload.get("tracked_source_deny_globs", [])]
    exceptions = {str(value) for value in payload.get("tracked_template_exceptions", [])}
    selected: list[str] = []
    for relative in _tracked_files():
        included = relative in required or _under_reviewed_root(relative, include_roots)
        if not included or _matches(relative, excluded):
            continue
        if relative not in exceptions and _matches(relative, denied):
            raise ValueError("tracked_source_denylist_violation")
        source_path = ROOT / relative
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError("reviewed_source_requires_regular_files")
        selected.append(relative)
    missing = sorted(required.difference(selected))
    if missing:
        raise ValueError("reviewed_source_required_file_missing")
    return selected


def _tar_info(relative: str, data: bytes, prefix: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(f"{prefix}/{relative}")
    info.size = len(data)
    info.mode = 0o755 if (ROOT / relative).stat().st_mode & 0o111 else 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def build_archive(output: Path) -> dict[str, Any]:
    output = output.expanduser()
    if not output.is_absolute():
        raise ValueError("output_must_be_absolute")
    try:
        output.resolve(strict=False).relative_to(ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise ValueError("output_must_be_outside_source_tree")
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = _manifest()
    files = reviewed_files(payload)
    prefix = f"elysia-{payload.get('target_release', 'source')}-source"
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for relative in files:
                    data = (ROOT / relative).read_bytes()
                    archive.addfile(_tar_info(relative, data, prefix), io.BytesIO(data))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "status": "passed",
        "artifact": output.name,
        "file_count": len(files),
        "sha256": digest,
        "private_paths_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_archive(args.output)
    print(yaml.safe_dump(result, sort_keys=True).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
