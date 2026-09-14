"""Descriptor-relative, bounded filesystem operations for governed Codev writes.

Directory descriptors prevent symlink substitution from redirecting writes. A
root lock serializes Codev writers; source bytes are checked again immediately
before replacement. External editors do not participate in this advisory lock,
so callers must still present and reconcile revision conflicts.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import fcntl
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import stat
from uuid import uuid4


class WorkspaceConflict(ValueError):
    pass


class WorkspaceWriteUncertain(OSError):
    """Replacement happened but its durability could not be confirmed."""


_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
MAX_BYTES = 16 * 1024 * 1024
MAX_COPY_BYTES = 512 * 1024 * 1024


@contextmanager
def _directory(path: Path):
    """Open every absolute path component without following links."""
    absolute = Path(os.path.abspath(path))
    fd = os.open("/", _DIRECTORY)
    try:
        for component in absolute.parts[1:]:
            child = os.open(component, _DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextmanager
def parent_descriptor(root: Path, relative: str, *, create_parents: bool = False, _lock: bool = True):
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith("/") or any(p in {".", "..", ""} for p in relative.split("/")) or "\\" in relative:
        raise WorkspaceConflict("unsafe_relative_path")
    with _directory(root) as root_fd:
        if _lock:
            fcntl.flock(root_fd, fcntl.LOCK_EX)
        parent = os.dup(root_fd)
        try:
            for component in parts[:-1]:
                if create_parents:
                    try:
                        os.mkdir(component, 0o700, dir_fd=parent)
                    except FileExistsError:
                        pass
                child = os.open(component, _DIRECTORY, dir_fd=parent)
                os.close(parent)
                parent = child
            yield parent, parts[-1]
        finally:
            os.close(parent)
            if _lock:
                fcntl.flock(root_fd, fcntl.LOCK_UN)


def _read(parent: int, name: str, limit: int) -> tuple[bytes, os.stat_result]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise WorkspaceConflict("unsafe_file_identity")
        if info.st_size > limit:
            raise WorkspaceConflict("file_too_large")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(fd)
        if len(data) > limit or (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise WorkspaceConflict("file_changed_during_read")
        return data, after
    finally:
        os.close(fd)


def read_bytes(root: Path, relative: str, *, limit: int = MAX_BYTES) -> bytes:
    with parent_descriptor(root, relative) as (parent, name):
        return _read(parent, name, limit)[0]


def _stream_hash(parent: int, name: str, output=None) -> str:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_COPY_BYTES:
            raise WorkspaceConflict("unsafe_or_oversized_file")
        digest = sha256()
        count = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_COPY_BYTES:
                raise WorkspaceConflict("file_too_large")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise WorkspaceConflict("file_changed_during_read")
        return digest.hexdigest()
    finally:
        os.close(fd)


def hash_file(root: Path, relative: str) -> str:
    with parent_descriptor(root, relative) as (parent, name):
        return _stream_hash(parent, name)


def copy_backup(root: Path, source: str, destination: str, *, expected_hash: str | None = None) -> str:
    """Stream existing governed document/data/media sizes without loading them all."""
    with parent_descriptor(root, source) as (src, name):
        with parent_descriptor(root, destination, create_parents=True, _lock=False) as (dst, target):
            temporary = f".codev-{uuid4().hex}.tmp"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dst)
            try:
                with os.fdopen(fd, "wb") as stream:
                    digest = _stream_hash(src, name, stream)
                    if expected_hash is not None and digest != expected_hash:
                        raise WorkspaceConflict("current_content_hash_mismatch")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, target, src_dir_fd=dst, dst_dir_fd=dst, follow_symlinks=False)
                os.unlink(temporary, dir_fd=dst)
                os.fsync(dst)
                return digest
            finally:
                try:
                    os.unlink(temporary, dir_fd=dst)
                except FileNotFoundError:
                    pass


def atomic_write(root: Path, relative: str, data: bytes, *, expected_hash: str | None, create_parents: bool = False) -> None:
    """None means create-only. Existing content needs its exact SHA-256 hash."""
    if len(data) > MAX_BYTES:
        raise WorkspaceConflict("file_too_large")
    with parent_descriptor(root, relative, create_parents=create_parents) as (parent, name):
        mode = 0o600
        before = None
        if expected_hash is not None:
            current, before = _read(parent, name, MAX_BYTES)
            if sha256(current).hexdigest() != expected_hash:
                raise WorkspaceConflict("current_content_hash_mismatch")
            mode = stat.S_IMODE(before.st_mode) & 0o777
        temporary = f".codev-{uuid4().hex}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
            if expected_hash is None:
                # link is atomic and refuses an existing destination, including a link.
                os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            else:
                current, now = _read(parent, name, MAX_BYTES)
                if (before.st_dev, before.st_ino) != (now.st_dev, now.st_ino) or sha256(current).hexdigest() != expected_hash:
                    raise WorkspaceConflict("current_content_hash_mismatch")
                os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            try:
                os.fsync(parent)
            except OSError as exc:
                raise WorkspaceWriteUncertain("replacement_durability_unconfirmed") from exc
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


def delete_exact(root: Path, relative: str, *, expected_hash: str) -> None:
    with parent_descriptor(root, relative) as (parent, name):
        if _stream_hash(parent, name) != expected_hash:
            raise WorkspaceConflict("current_content_hash_mismatch")
        os.unlink(name, dir_fd=parent)
        try:
            os.fsync(parent)
        except OSError as exc:
            raise WorkspaceWriteUncertain("deletion_durability_unconfirmed") from exc


def move_exact(root: Path, source: str, destination: str, *, expected_hash: str) -> None:
    """Linux renameat2 NOREPLACE preserves identity and cannot overwrite a racer."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise WorkspaceConflict("atomic_move_unavailable")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    with parent_descriptor(root, source) as (src, name):
        with parent_descriptor(root, destination, create_parents=True, _lock=False) as (dst, target):
            if _stream_hash(src, name) != expected_hash:
                raise WorkspaceConflict("current_content_hash_mismatch")
            if rename(src, os.fsencode(name), dst, os.fsencode(target), 1) != 0:
                raise OSError(ctypes.get_errno(), "atomic_move_refused")
            try:
                os.fsync(src)
                os.fsync(dst)
            except OSError as exc:
                raise WorkspaceWriteUncertain("move_durability_unconfirmed") from exc
