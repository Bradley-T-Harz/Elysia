"""One private installed Core service shared by Desktop and native adapters.

No TCP discovery, editor profile, workspace grant, shell or cloud fallback is
involved. A kernel-owned Unix socket and a held flock define the live instance.
The content-free descriptor is diagnostic, never authority to choose a URL.
"""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

from app.install.codev_core import RUNTIME_CONTRACT, inspect_core
from app.install.paths import ensure_elysia_directories, resolve_elysia_paths

SOCKET_NAME = "core.sock"
START_TIMEOUT_SECONDS = 60


def _executable_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _graceful_upgrade(current: dict, deadline: float) -> bool:
    """Drain the verified older service. Never force-kill work for an upgrade."""
    with _socket_connection() as stream:
        pid, uid, _ = struct.unpack("3i", stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if pid != current["pid"] or uid != os.getuid() or pid == os.getpid():
            raise ValueError("runtime_changed_during_upgrade")
        library = ctypes.CDLL(None, use_errno=True)
        library.pidfd_open.argtypes = [ctypes.c_int, ctypes.c_uint]
        library.pidfd_open.restype = ctypes.c_int
        library.pidfd_send_signal.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
        library.pidfd_send_signal.restype = ctypes.c_int
        pidfd = library.pidfd_open(pid, 0)
        if pidfd < 0: raise OSError(ctypes.get_errno(), "runtime_upgrade_pidfd_failed")
        try:
            # A pidfd pins the kernel process even if its numeric PID is reused.
            start = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            if current.get("process_start_ticks") != start or current.get("boot_id") != boot:
                raise ValueError("runtime_identity_changed_during_upgrade")
            if library.pidfd_send_signal(pidfd, signal.SIGTERM, None, 0) < 0:
                raise OSError(ctypes.get_errno(), "runtime_upgrade_signal_failed")
            return bool(select.select([pidfd], [], [], max(0, deadline - time.monotonic()))[0])
        finally:
            os.close(pidfd)


def private_runtime_directory(*, create: bool = False) -> Path:
    path = resolve_elysia_paths().runtime_dir
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("unsafe_runtime_directory")
    return path


def _socket_connection(timeout: float = 2) -> socket.socket:
    directory = private_runtime_directory()
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        info = os.stat(SOCKET_NAME, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("unsafe_runtime_socket")
        stream.settimeout(timeout)
        # A directory descriptor also supports long XDG/home paths on Linux.
        stream.connect(f"/proc/self/fd/{directory_fd}/{SOCKET_NAME}")
        _pid, uid, _gid = struct.unpack("3i", stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid():
            raise ValueError("runtime_peer_owner_mismatch")
        return stream
    except BaseException:
        stream.close()
        raise
    finally:
        os.close(directory_fd)


def runtime_status() -> dict:
    try:
        with _socket_connection() as stream:
            pid, uid, _gid = struct.unpack("3i", stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            stream.sendall(b"GET /runtime/identity HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            response = http.client.HTTPResponse(stream)
            response.begin()
            raw = response.read(16385)
            if response.status != 200 or len(raw) > 16384:
                raise ValueError("runtime_identity_unavailable")
            value = json.loads(raw)
            if value.get("contract") != RUNTIME_CONTRACT or value.get("pid") != pid or value.get("uid") != uid:
                raise ValueError("runtime_contract_or_peer_mismatch")
            return {**value, "state": "ready", "transport": "unix", "credential_exposed": False}
    except (OSError, ValueError, http.client.HTTPException):
        return {"contract": RUNTIME_CONTRACT, "state": "disconnected", "transport": "unix", "credential_exposed": False}


def ensure_runtime() -> dict:
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        core = inspect_core()
        # The neutral installed Core owns the service whenever available. An
        # Elysia launcher is a client, including after reverse install order.
        if core.compatible and core.executable and core.executable.resolve() != Path(sys.executable).resolve():
            environment = dict(os.environ)
            for name in ("PYTHONPATH", "LD_LIBRARY_PATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
                environment.pop(name, None)
            environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            completed = subprocess.run([str(core.executable), "runtime", "ensure"], env=environment,
                cwd="/", stdin=subprocess.DEVNULL, capture_output=True, timeout=75, check=False)
            if len(completed.stdout) > 16384: raise ValueError("runtime_discovery_output_exceeded")
            return json.loads(completed.stdout)
    desired_digest = _executable_digest(Path("/proc/self/exe")) if frozen else None
    current = runtime_status()
    if current["state"] == "ready" and current.get("executable_sha256") == desired_digest:
        return current
    directory = private_runtime_directory(create=True)
    # Serialize starters independently of the lifetime lock, so concurrent
    # Desktop/Codev launches do not unpack multiple Python payloads.
    fd = os.open(directory / "start.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            raise ValueError("unsafe_start_lock")
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    return runtime_status()
                time.sleep(0.1)
        current = runtime_status()
        if current["state"] == "ready" and current.get("executable_sha256") == desired_digest:
            return current
        if current["state"] == "ready" and not _graceful_upgrade(current, deadline):
            return {**current, "state": "update_pending"}
        if time.monotonic() >= deadline:
            return runtime_status()
        # A draining or still-starting server may no longer answer HTTP while
        # retaining its lifetime lock. Wait instead of repeatedly unpacking it.
        lifetime = os.open(directory / "core.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(lifetime)
            if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ValueError("unsafe_runtime_lock")
            while True:
                try:
                    fcntl.flock(lifetime, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(lifetime, fcntl.LOCK_UN)
                    break
                except BlockingIOError:
                    current = runtime_status()
                    if current["state"] == "ready" and current.get("executable_sha256") == desired_digest:
                        return current
                    if time.monotonic() >= deadline: return {**current, "state": "update_pending"}
                    time.sleep(0.15)
        finally:
            os.close(lifetime)
        command = ([sys.executable, "runtime", "serve"] if frozen
                   else [sys.executable, "-m", "app.install.runtime_service", "serve"])
        environment = dict(os.environ)
        if frozen:
            for name in ("PYTHONPATH", "LD_LIBRARY_PATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
                environment.pop(name, None)
            environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        environment["ELYSIA_RUNTIME_MODE"] = "packaged"
        environment["ELYSIA_API_AUTH_MODE"] = "required"
        log_path = directory / "core-startup.log"
        log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(log_fd)
            if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ValueError("unsafe_startup_log")
            os.ftruncate(log_fd, 0)
            process = subprocess.Popen(command, env=environment, cwd="/" if frozen else None,
                                       stdin=subprocess.DEVNULL, stdout=log_fd, stderr=log_fd,
                                       close_fds=True, start_new_session=True)
        finally:
            os.close(log_fd)
        while time.monotonic() < deadline:
            current = runtime_status()
            if current["state"] == "ready" or process.poll() is not None:
                return current
            time.sleep(0.15)
        return runtime_status()
    finally:
        os.close(fd)


def serve_runtime() -> int:
    os.environ["ELYSIA_RUNTIME_MODE"] = "packaged"
    os.environ["ELYSIA_API_AUTH_MODE"] = "required"
    directory = private_runtime_directory(create=True)
    lock_fd = os.open(directory / "core.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    info = os.fstat(lock_fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
        os.close(lock_fd)
        raise ValueError("unsafe_runtime_lock")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        return 0
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    socket_identity = None
    try:
        try:
            old = os.stat(SOCKET_NAME, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            old = None
        if old is not None:
            if not stat.S_ISSOCK(old.st_mode) or old.st_uid != os.getuid():
                raise ValueError("refusing_foreign_runtime_socket")
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(1)
                probe.connect(f"/proc/self/fd/{directory_fd}/{SOCKET_NAME}")
            except ConnectionRefusedError:
                pass
            else:
                raise ValueError("refusing_live_unowned_runtime_socket")
            finally:
                probe.close()
            os.unlink(SOCKET_NAME, dir_fd=directory_fd)
        listener.bind(f"/proc/self/fd/{directory_fd}/{SOCKET_NAME}")
        os.chmod(SOCKET_NAME, 0o600, dir_fd=directory_fd)
        socket_identity = os.stat(SOCKET_NAME, dir_fd=directory_fd).st_ino
        listener.listen(128)
        from app.install.local_auth import build_local_api_auth_policy
        paths = resolve_elysia_paths()
        ensure_elysia_directories(paths)
        policy = build_local_api_auth_policy(paths=paths, initialize=True)
        from app.memory.migration_service import prepare_memory_authority_for_startup
        prepare_memory_authority_for_startup(paths)
        import uvicorn
        from app.api.main import create_app
        app = create_app(auth_policy=policy, private_unix_socket=True)
        identity = {"contract": RUNTIME_CONTRACT, "product_version": "1.1.0", "pid": os.getpid(),
                    "uid": os.getuid(), "instance_id": secrets.token_hex(24), "transport": "unix",
                    "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                    "process_start_ticks": Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19],
                    "executable_sha256": _executable_digest(Path("/proc/self/exe")) if getattr(sys, "frozen", False) else None}
        os.environ["ELYSIA_RUNTIME_INSTANCE_ID"] = identity["instance_id"]
        app.state.runtime_identity = identity
        descriptor = directory / "service.json"
        from app.install.codev_installer import _atomic_private_json
        _atomic_private_json(descriptor, {**identity, "socket_name": SOCKET_NAME})
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        server.run(sockets=[listener])
        return 0
    finally:
        listener.close()
        try:
            if socket_identity == os.stat(SOCKET_NAME, dir_fd=directory_fd, follow_symlinks=False).st_ino:
                os.unlink(SOCKET_NAME, dir_fd=directory_fd)
                (directory / "service.json").unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        os.close(directory_fd)
        os.close(lock_fd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("ensure", "status", "serve"))
    args = parser.parse_args(argv)
    if args.operation == "serve":
        return serve_runtime()
    result = ensure_runtime() if args.operation == "ensure" else runtime_status()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
