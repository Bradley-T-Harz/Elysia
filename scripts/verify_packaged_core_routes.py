#!/usr/bin/env python3
"""Fail a release build when required packaged API routes cannot import."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


REQUIRED_PATHS = {
    "/account/create",
    "/account/state",
    "/memory/items",
    "/memory/health",
    "/memory/projection/rebuild",
    "/memory/migration/status",
    "/memory/backup/status",
    "/research/search",
    "/research/fetch",
    "/research/records",
    "/research/context-receipts",
    "/research/egress/approvals/pending",
    "/chat/send",
    "/cognition/status",
    "/cognition/requests/{request_id}/cancel",
    "/emergency/status",
    "/emergency/stop",
    "/emergency/reset",
    "/admin/summary",
    "/admin/changes/preview",
    "/admin/changes/apply",
    "/admin/changes/restore",
    "/conversations",
    "/projects",
    "/coding/status",
    "/coding/file/read-preview",
    "/coding/file-types",
    "/coding/patch/propose",
    "/coding/file/operation-plan",
    "/coding/visual-types",
}


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_packaged_core_routes.py PACKAGED_BINARY")
    binary = Path(sys.argv[1]).resolve()
    if not binary.is_file():
        raise SystemExit(f"Packaged binary does not exist: {binary}")

    port = _free_port()
    with tempfile.TemporaryDirectory(prefix="elysia-packaged-route-smoke.") as root:
        proof_root = Path(root)
        runtime = proof_root / "runtime"
        runtime.mkdir(mode=0o700)
        env = {
            **os.environ,
            "HOME": str(proof_root / "home"),
            "XDG_CONFIG_HOME": str(proof_root / "config"),
            "XDG_DATA_HOME": str(proof_root / "data"),
            "XDG_CACHE_HOME": str(proof_root / "cache"),
            "XDG_STATE_HOME": str(proof_root / "state"),
            "XDG_RUNTIME_DIR": str(runtime),
        }
        process = subprocess.Popen(
            [
                str(binary),
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--mode",
                "packaged",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 45
            document: dict[str, object] | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=1) as response:
                        document = json.load(response)
                    break
                except (OSError, URLError, TimeoutError):
                    time.sleep(0.25)
            if document is None:
                output = process.stdout.read() if process.poll() is not None and process.stdout else ""
                raise SystemExit(
                    "Packaged Core did not expose OpenAPI during the route smoke test.\n"
                    + output[-4000:]
                )
            paths = set(document.get("paths", {}))
            missing = sorted(REQUIRED_PATHS - paths)
            if missing:
                raise SystemExit(
                    "Packaged Core omitted required release routes: " + ", ".join(missing)
                )
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)

    print("Packaged Core required-route smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
