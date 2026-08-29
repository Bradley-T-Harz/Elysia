#!/usr/bin/env python3
"""Verify publication-bound current source and reachable Git history.

The verifier never prints matching content. Findings contain only a category,
object identifier, and repository-relative path. An operator may provide extra
private markers in an untracked file, one UTF-8 value per line.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
TEXT_SECRET_PATTERNS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(rb"sk-[A-Za-z0-9]{24,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
MACHINE_PATH_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9_-])/home/[A-Za-z0-9._-]+/"),
    re.compile(rb"(?<![A-Za-z0-9_-])/Users/[A-Za-z0-9._-]+/"),
    re.compile(rb"(?<![A-Za-z0-9_-])[A-Za-z]:\\Users\\[^\\]+\\"),
)
SENSITIVE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx", ".log"}
SYNTHETIC_FIXTURE_PREFIXES = ("tests/", "apps/elysia-desktop/tests/")
SYNTHETIC_POLICY_PATHS = {
    "app/api/coding_process_service.py",
    "app/api/addons/static_scanner.py",
    "scripts/verify_publication_history.py",
}


def run(*args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        input=input_bytes,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def built_in_private_markers() -> list[bytes]:
    return [
        # A given name alone is not an identity-safe marker: third-party
        # license payloads legitimately contain unrelated people such as
        # "Bradley Smith". Match the operator's exact name instead so the
        # public-history gate preserves upstream copyright notices verbatim.
        b"Brad" + b"ley" + b" " + b"Har" + b"z",
        b"Brad" + b"ley" + b"-private",
        b"ojiji" + b"-chhaya",
        b"Custos" + b"Naturae",
        b"Brad" + b"ley" + b"_SSD_2TB",
        b"MAIN" + b"_Projects",
    ]


def load_markers(path: Path | None) -> list[bytes]:
    markers = built_in_private_markers()
    if path is not None:
        for line in path.read_bytes().splitlines():
            marker = line.strip()
            if marker and marker not in markers:
                markers.append(marker)
    return markers


def tracked_files() -> list[str]:
    return [
        item.decode("utf-8")
        for item in run("git", "ls-files", "-z").split(b"\0")
        if item
    ]


def fixture_only(paths: set[str]) -> bool:
    return bool(paths) and all(
        path.startswith(SYNTHETIC_FIXTURE_PREFIXES) or path in SYNTHETIC_POLICY_PATHS
        for path in paths
    )


def path_findings(path: str, allowed_paths: set[str] | None = None) -> list[str]:
    normalized = PurePosixPath(path)
    lowered = path.casefold()
    explicitly_allowed = path in (allowed_paths or set())
    findings: list[str] = []
    if normalized.suffix.casefold() in SENSITIVE_SUFFIXES:
        findings.append("sensitive_filename")
    if any(part in {"vault", "node_modules", "__pycache__"} for part in normalized.parts):
        findings.append("denied_path")
    if not explicitly_allowed and (
        any(part == ".env" for part in normalized.parts)
        or "/.env." in f"/{lowered}"
        or lowered.endswith("/.env")
    ):
        findings.append("denied_path")
    return findings


def content_findings(data: bytes, paths: set[str], markers: list[bytes]) -> list[str]:
    findings: list[str] = []
    if any(marker in data for marker in markers):
        findings.append("private_marker")
    if not fixture_only(paths):
        if any(pattern.search(data) for pattern in MACHINE_PATH_PATTERNS):
            findings.append("absolute_machine_path")
        if any(pattern.search(data) for pattern in TEXT_SECRET_PATTERNS):
            findings.append("credential_signature")
    return findings


def private_author_email(email: bytes, markers: list[bytes]) -> bool:
    """Return whether Git metadata uses a private rather than public-safe email."""
    lowered = email.lower()
    if lowered.endswith(b"@users.noreply.github.com"):
        return False
    return lowered.endswith(b".edu") or any(marker.lower() in lowered for marker in markers)


def publication_files() -> list[str]:
    """Resolve the exact reviewed-source artifact boundary from its manifest."""
    builder = ROOT / "scripts" / "build_public_source_archive.py"
    spec = importlib.util.spec_from_file_location("elysia_public_source_builder", builder)
    if spec is None or spec.loader is None:
        raise RuntimeError("publication_source_builder_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.reviewed_files(module._manifest()))


def publication_path_exceptions() -> set[str]:
    """Return only exact manifest-reviewed path exceptions.

    The general environment-file prohibition remains active for every other
    path. This narrow exception lets the stable public Marketplace build
    configuration be tracked without allowing arbitrary `.env*` files.
    """
    builder = ROOT / "scripts" / "build_public_source_archive.py"
    spec = importlib.util.spec_from_file_location("elysia_public_source_builder", builder)
    if spec is None or spec.loader is None:
        raise RuntimeError("publication_source_builder_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module._manifest()
    return {str(value) for value in payload.get("tracked_template_exceptions", [])}


def scan_tree(
    markers: list[bytes],
    *,
    paths: list[str] | None = None,
    scope: str = "tree",
    allowed_paths: set[str] | None = None,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for relative in tracked_files() if paths is None else paths:
        for category in path_findings(relative, allowed_paths):
            findings.append({"scope": scope, "category": category, "path": relative})
        path = ROOT / relative
        if not path.is_file():
            continue
        data = path.read_bytes()
        for category in content_findings(data, {relative}, markers):
            findings.append({"scope": scope, "category": category, "path": relative})
    return findings


def reachable_objects() -> tuple[dict[str, set[str]], list[str]]:
    object_paths: dict[str, set[str]] = defaultdict(set)
    object_ids: list[str] = []
    for line in run("git", "rev-list", "--objects", "--all").decode("utf-8", errors="replace").splitlines():
        object_id, _, path = line.partition(" ")
        object_ids.append(object_id)
        if path:
            object_paths[object_id].add(path)
    return object_paths, object_ids


def blob_types(object_ids: list[str]) -> list[str]:
    payload = "".join(f"{object_id}\n" for object_id in object_ids).encode("ascii")
    output = run("git", "cat-file", "--batch-check=%(objectname) %(objecttype)", input_bytes=payload)
    return [
        object_id
        for line in output.decode("ascii").splitlines()
        for object_id, object_type in [line.split(" ", 1)]
        if object_type == "blob"
    ]


def read_blobs(object_ids: list[str]):
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        for object_id in object_ids:
            process.stdin.write(object_id.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii").strip()
            returned_id, object_type, size_text = header.split(" ")
            if returned_id != object_id or object_type != "blob":
                raise RuntimeError("Unexpected git cat-file batch response.")
            size = int(size_text)
            data = process.stdout.read(size)
            if process.stdout.read(1) != b"\n":
                raise RuntimeError("Malformed git cat-file batch separator.")
            yield object_id, data
    finally:
        process.stdin.close()
        process.stdin = None
        stderr = process.stderr.read() if process.stderr is not None else b""
        returncode = process.wait()
        if returncode:
            raise RuntimeError(stderr.decode("utf-8", errors="replace"))


def scan_history(
    markers: list[bytes],
    *,
    allowed_paths: set[str] | None = None,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    object_paths, object_ids = reachable_objects()
    for object_id, paths in object_paths.items():
        for path in sorted(paths):
            for category in path_findings(path, allowed_paths):
                findings.append(
                    {"scope": "history", "category": category, "object": object_id, "path": path}
                )
    for object_id, data in read_blobs(blob_types(object_ids)):
        paths = object_paths.get(object_id, set())
        for category in content_findings(data, paths, markers):
            findings.append(
                {
                    "scope": "history",
                    "category": category,
                    "object": object_id,
                    "paths": sorted(paths)[:10],
                }
            )

    messages = run("git", "log", "--all", "--format=%H%x00%B%x00").split(b"\0")
    for index in range(0, len(messages) - 1, 2):
        commit = messages[index].decode("ascii", errors="ignore")
        message = messages[index + 1]
        if any(marker in message for marker in markers):
            findings.append({"scope": "history", "category": "private_commit_message", "object": commit})

    identities = run("git", "log", "--all", "--format=%H%x00%ae%x00%ce%x00").split(b"\0")
    for index in range(0, len(identities) - 2, 3):
        commit = identities[index].decode("ascii", errors="ignore")
        for email in identities[index + 1 : index + 3]:
            if private_author_email(email, markers):
                findings.append(
                    {"scope": "history", "category": "private_author_email", "object": commit}
                )
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        choices=("public", "tree", "history", "all"),
        default="all",
    )
    parser.add_argument("--private-markers-file", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    markers = load_markers(args.private_markers_file)
    allowed_paths = publication_path_exceptions()
    findings: list[dict[str, object]] = []
    if args.scope == "public":
        findings.extend(
            scan_tree(
                markers,
                paths=publication_files(),
                scope="public",
                allowed_paths=allowed_paths,
            )
        )
    if args.scope in {"tree", "all"}:
        findings.extend(scan_tree(markers, allowed_paths=allowed_paths))
    if args.scope in {"history", "all"}:
        findings.extend(scan_history(markers, allowed_paths=allowed_paths))
    result = {
        "status": "passed" if not findings else "failed",
        "scope": args.scope,
        "finding_count": len(findings),
        "findings": findings[:200],
        "content_printed": False,
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
