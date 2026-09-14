#!/usr/bin/env python3
"""Release gate for the compiled native service, without a source environment.

This supplements route/unit checks. Full installer, GUI, reboot, and editor
qualification must additionally run from artifacts on supported guest systems.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ctypes
import http.client
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile


def pidfd_open(pid: int) -> int:
    # Some Python distributions omit os.pidfd_open despite a supporting host.
    library = ctypes.CDLL(None, use_errno=True)
    call = library.pidfd_open
    call.argtypes = [ctypes.c_int, ctypes.c_uint]
    call.restype = ctypes.c_int
    fd = call(pid, 0)
    if fd < 0: raise OSError(ctypes.get_errno(), "pidfd_open failed")
    return fd


def pidfd_signal(fd: int, signum: int) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    call = library.pidfd_send_signal
    call.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    call.restype = ctypes.c_int
    if call(fd, signum, None, 0) < 0: raise OSError(ctypes.get_errno(), "pidfd_send_signal failed")


def request(directory: Path, method: str, path: str, body: bytes = b"") -> tuple[int, dict, int]:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(5)
            stream.connect(f"/proc/self/fd/{fd}/core.sock")
            pid, uid, _ = struct.unpack("3i", stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            assert uid == os.getuid()
            stream.sendall(f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
            response = http.client.HTTPResponse(stream)
            response.begin()
            return response.status, json.loads(response.read(65536)), pid
    finally:
        os.close(fd)


def qualify(binary: Path, *, runtime_fallback: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="elysia-packaged-native-") as temporary:
        root = Path(temporary)
        home = root / "ordinary user with spaces"
        home.mkdir(mode=0o700)
        environment = {"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                       "PYINSTALLER_RESET_ENVIRONMENT": "1"}
        for axis in ("CONFIG", "DATA", "CACHE", "STATE"):
            environment[f"XDG_{axis}_HOME"] = str(home / axis.lower())
        if not runtime_fallback:
            environment["XDG_RUNTIME_DIR"] = str(home / "runtime")
        directory = (home / "state/elysia/runtime" if runtime_fallback else home / "runtime/elysia")
        pidfd = None
        try:
            def ensure(_: int) -> dict:
                completed = subprocess.run([str(binary), "runtime", "ensure"], env=environment,
                                           cwd="/", capture_output=True, text=True, timeout=75, check=True)
                return json.loads(completed.stdout)
            with ThreadPoolExecutor(max_workers=3) as pool:
                starts = list(pool.map(ensure, range(3)))
            assert all(item["state"] == "ready" and item["transport"] == "unix" for item in starts)
            assert len({item["instance_id"] for item in starts}) == 1
            status, identity, peer = request(directory, "GET", "/runtime/identity")
            assert status == 200 and identity["pid"] == peer == starts[0]["pid"]
            pidfd = pidfd_open(peer)
            assert identity["contract"] == "elysia-local-runtime-1" and identity["product_version"] == "1.0.0"
            assert identity["executable_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
            assert stat.S_IMODE(directory.stat().st_mode) == 0o700
            assert stat.S_IMODE((directory / "core.sock").stat().st_mode) == 0o600
            status, install, _ = request(directory, "GET", "/codev/installation")
            install = install["data"]["codev_installation"]
            assert status == 200 and install["installed"] is False and install["state"] == "absent"
            status, _, _ = request(directory, "POST", "/codev/session", b"{}")
            assert status == 401, "Private transport must retain API authentication"
            return {"passed": True, "runtime_fallback": runtime_fallback, "concurrent_clients": 3,
                    "instances": 1, "socket_mode": "0600", "source_environment": False,
                    "codev_absent": True, "unauthenticated_session_status": status}
        finally:
            # Only the kernel peer just verified inside this private fixture.
            if pidfd is None and directory.exists():
                try:
                    status, identity, peer = request(directory, "GET", "/runtime/identity")
                    if status == 200 and identity.get("pid") == peer: pidfd = pidfd_open(peer)
                except (OSError, ValueError):
                    pass
            if pidfd is not None:
                try:
                    pidfd_signal(pidfd, signal.SIGTERM)
                    import select
                    if not select.select([pidfd], [], [], 5)[0]:
                        pidfd_signal(pidfd, signal.SIGKILL)
                        assert select.select([pidfd], [], [], 5)[0], "Packaged fixture did not stop"
                except ProcessLookupError:
                    pass
                finally:
                    os.close(pidfd)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_packaged_native_runtime.py COMPILED_CORE")
    binary = Path(sys.argv[1]).resolve(strict=True)
    print(json.dumps({"packaged_native_gate": [qualify(binary, runtime_fallback=value) for value in (False, True)]}, sort_keys=True))
