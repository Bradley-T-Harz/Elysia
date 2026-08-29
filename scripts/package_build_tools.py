#!/usr/bin/env python3
"""Verify or acquire exact, public package-build inputs without source egress."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "install" / "package_build_tools.yaml"


class PackageBuildToolError(RuntimeError):
    """One exact package-build tool differs from the approved policy."""


def _policy() -> dict:
    try:
        payload = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PackageBuildToolError("The package-build tool policy is unavailable.") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("contract_version") != "elysia-package-build-tools-1.0"
        or payload.get("rules", {}).get("unverified_cached_tool_allowed") is not False
    ):
        raise PackageBuildToolError("The package-build tool policy is invalid.")
    return payload


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def _verify_file(path: Path, expected: str, *, expected_size: int | None = None) -> None:
    if not path.is_file() or path.is_symlink():
        raise PackageBuildToolError("An exact package-build input is missing or unsafe.")
    if expected_size is not None and path.stat().st_size != expected_size:
        raise PackageBuildToolError("An exact package-build input has an unexpected size.")
    if _digest(path) != expected:
        raise PackageBuildToolError("An exact package-build input failed SHA-256 verification.")


def verify_tauri_cache(cache: Path) -> dict[str, object]:
    payload = _policy()
    if not cache.is_absolute() or not cache.is_dir() or cache.is_symlink():
        raise PackageBuildToolError("The Tauri build cache is unavailable or unsafe.")
    records = payload["tauri_cache_files"]
    for filename, record in records.items():
        _verify_file(cache / filename, str(record["sha256"]))
    return {
        "contract_version": payload["contract_version"],
        "verified_cache_input_count": len(records),
        "all_hashes_match": True,
        "raw_paths_exposed": False,
    }


def verify_appimagetool(extracted_plugin: Path) -> dict[str, object]:
    payload = _policy()
    record = payload["appimagetool"]
    tool = extracted_plugin / str(record["extracted_relative_path"])
    _verify_file(tool, str(record["sha256"]))
    return {
        "contract_version": payload["contract_version"],
        "appimagetool_version": record["version"],
        "sha256_verified": True,
        "raw_paths_exposed": False,
    }


def prepare_runtime(output: Path) -> dict[str, object]:
    payload = _policy()
    record = payload["type2_runtime"]
    expected_size = int(record["size_bytes"])
    expected_hash = str(record["sha256"])
    output = output.expanduser().resolve()
    if output.exists():
        _verify_file(output, expected_hash, expected_size=expected_size)
    else:
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        request = Request(str(record["source"]), headers={"User-Agent": "Elysia-Package-Builder/1.0"})
        digest = sha256()
        size = 0
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                with urlopen(request, timeout=60) as response:
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > expected_size:
                            raise PackageBuildToolError("The AppImage runtime exceeded its exact approved size.")
                        digest.update(chunk)
                        handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
                if size != expected_size or digest.hexdigest() != expected_hash:
                    raise PackageBuildToolError("The AppImage runtime differs from the exact approved identity.")
                temporary.chmod(0o700)
                temporary.replace(output)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
    return {
        "contract_version": payload["contract_version"],
        "runtime_sha256": expected_hash,
        "runtime_size_bytes": expected_size,
        "source_channel_mutable": bool(record["source_channel_mutable"]),
        "exact_hash_mismatch_fails_closed": True,
        "raw_paths_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cache = sub.add_parser("verify-tauri-cache")
    cache.add_argument("--cache", type=Path, required=True)
    tool = sub.add_parser("verify-appimagetool")
    tool.add_argument("--extracted-plugin", type=Path, required=True)
    runtime = sub.add_parser("prepare-runtime")
    runtime.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "verify-tauri-cache":
        result = verify_tauri_cache(arguments.cache)
    elif arguments.command == "verify-appimagetool":
        result = verify_appimagetool(arguments.extracted_plugin)
    else:
        result = prepare_runtime(arguments.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
