"""Fixed-argument external archive listing for formats outside the stdlib lane."""

from __future__ import annotations

import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time
from typing import Any


SAFE_TOOL_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


class ExternalListError(RuntimeError):
    """Raised when the bounded external listing lane cannot produce truth."""


def _bounded_process(
    command: list[str],
    *,
    timeout_seconds: int,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
) -> tuple[int, bytes, bytes, bool]:
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        close_fds=True,
        env={"PATH": SAFE_TOOL_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    assert process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": max_stdout_bytes, "stderr": max_stderr_bytes}
    truncated = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                raise ExternalListError("archive_worker_timeout")
            for key, _ in selector.select(timeout=min(remaining, 0.2)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                label = str(key.data)
                room = max(0, limits[label] - len(buffers[label]))
                if len(chunk) > room:
                    buffers[label].extend(chunk[:room])
                    truncated = True
                    process.kill()
                else:
                    buffers[label].extend(chunk)
            if process.poll() is not None and not selector.get_map():
                break
        return process.wait(timeout=1), bytes(buffers["stdout"]), bytes(buffers["stderr"]), truncated
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=1)


def _parse_7z_slt(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            if current:
                blocks.append(current)
                current = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", 1)
            current[key.strip()] = value
    if current:
        blocks.append(current)
    members: list[dict[str, Any]] = []
    for block in blocks:
        name = block.get("Path")
        if not name or "Type" in block or "Physical Size" in block:
            continue
        attributes = block.get("Attributes", "")
        folder = block.get("Folder") == "+" or attributes.startswith("D")
        encrypted = block.get("Encrypted") == "+"
        try:
            size = max(0, int(block.get("Size", "0") or 0))
        except ValueError:
            size = 0
        try:
            packed = max(0, int(block.get("Packed Size", "0") or 0))
        except ValueError:
            packed = 0
        members.append(
            {
                "display_path": name,
                "kind": "directory" if folder else "file",
                "compressed_size": packed,
                "uncompressed_size": size,
                "is_directory": folder,
                "is_regular_file": not folder,
                "is_encrypted": encrypted,
                "attributes": attributes[:80],
            }
        )
    return members


def list_external_archive(
    source: Path,
    *,
    archive_type: str,
    timeout_seconds: int = 20,
    max_stdout_bytes: int = 2 * 1024 * 1024,
    max_stderr_bytes: int = 64 * 1024,
) -> dict[str, Any]:
    if archive_type not in {"7z", "rar"}:
        raise ExternalListError("unsupported_external_archive_type")
    resolved = source.resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        raise ExternalListError("source_must_be_regular_non_symlink_file")
    executable = shutil.which("7zz", path=SAFE_TOOL_PATH) or shutil.which("7z", path=SAFE_TOOL_PATH)
    if not executable:
        raise ExternalListError("7z_listing_tool_unavailable")
    command = [executable, "l", "-slt", "-ba", "-bd", "-y", "--", str(resolved)]
    exit_code, stdout, stderr, truncated = _bounded_process(
        command,
        timeout_seconds=timeout_seconds,
        max_stdout_bytes=max_stdout_bytes,
        max_stderr_bytes=max_stderr_bytes,
    )
    if truncated:
        raise ExternalListError("archive_worker_output_limit_exceeded")
    if exit_code != 0:
        lowered = stderr.decode("utf-8", errors="replace").lower()
        if "password" in lowered or "encrypted" in lowered:
            raise ExternalListError("encrypted_archive_blocked")
        raise ExternalListError(f"archive_listing_failed_exit_{exit_code}")
    return {
        "tool": Path(executable).name,
        "members": _parse_7z_slt(stdout.decode("utf-8", errors="replace")),
        "stdout_truncated": False,
        "stderr_logged": False,
    }


__all__ = ("ExternalListError", "list_external_archive")
