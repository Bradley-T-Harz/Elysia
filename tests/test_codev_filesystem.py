from hashlib import sha256
import os

import pytest

from core.codev.filesystem import atomic_write, read_bytes, move_exact, WorkspaceConflict
from app.api.coding_backup_service import create_coding_backup


def test_parent_and_backup_symlinks_cannot_redirect_writes(tmp_path):
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "nested").symlink_to(outside, target_is_directory=True)
    (root / ".elysia_backups").symlink_to(outside, target_is_directory=True)
    (root / "source.txt").write_text("original")
    with pytest.raises(OSError):
        atomic_write(root, "nested/new.txt", b"denied", expected_hash=None)
    with pytest.raises(OSError):
        create_coding_backup(workspace_root=root, source_path=root / "source.txt",
                             source_relative_path="source.txt", operation_kind="edit", session_id=None)
    assert list(outside.iterdir()) == []


def test_atomic_write_detects_change_while_preparing_replacement(tmp_path, monkeypatch):
    target = tmp_path / "code.py"
    target.write_bytes(b"before")
    original_fsync = os.fsync
    def competing_edit(fd):
        target.write_bytes(b"external edit")
        original_fsync(fd)
    monkeypatch.setattr(os, "fsync", competing_edit)
    with pytest.raises(WorkspaceConflict):
        atomic_write(tmp_path, "code.py", b"after", expected_hash=sha256(b"before").hexdigest())
    assert target.read_bytes() == b"external edit"
    assert not list(tmp_path.glob(".codev-*.tmp"))


def test_create_and_move_never_overwrite_existing_destination(tmp_path):
    (tmp_path / "source.txt").write_bytes(b"source")
    (tmp_path / "dest.txt").write_bytes(b"destination")
    with pytest.raises(FileExistsError):
        atomic_write(tmp_path, "dest.txt", b"replace", expected_hash=None)
    with pytest.raises(OSError):
        move_exact(tmp_path, "source.txt", "dest.txt", expected_hash=sha256(b"source").hexdigest())
    assert (tmp_path / "dest.txt").read_bytes() == b"destination"
    assert (tmp_path / "source.txt").read_bytes() == b"source"


def test_hardlink_and_fifo_reads_are_refused(tmp_path):
    (tmp_path / "a").write_bytes(b"private")
    os.link(tmp_path / "a", tmp_path / "b")
    os.mkfifo(tmp_path / "fifo")
    for name in ("a", "b", "fifo"):
        with pytest.raises(WorkspaceConflict):
            read_bytes(tmp_path, name)


def test_atomic_replace_preserves_executable_permission_and_backup_bytes(tmp_path):
    target = tmp_path / "script.py"
    target.write_bytes(b"before\r\n")
    target.chmod(0o750)
    digest = sha256(target.read_bytes()).hexdigest()
    receipt = create_coding_backup(workspace_root=tmp_path, source_path=target,
        source_relative_path="script.py", operation_kind="edit", session_id=None, expected_hash=digest)
    atomic_write(tmp_path, "script.py", b"after\r\n", expected_hash=digest)
    assert target.stat().st_mode & 0o777 == 0o750
    assert (tmp_path / receipt.backup_relative_path).read_bytes() == b"before\r\n"


def test_backup_preserves_existing_large_document_support(tmp_path):
    from app.api.coding_backup_service import hash_file_bytes
    source = tmp_path / "document.docx"
    with source.open("wb") as stream:
        for _ in range(17):
            stream.write(b'x' * 1024 * 1024)
    digest = hash_file_bytes(source)
    receipt = create_coding_backup(workspace_root=tmp_path, source_path=source,
        source_relative_path=source.name, operation_kind="document_edit", session_id=None, expected_hash=digest)
    assert hash_file_bytes(tmp_path / receipt.backup_relative_path) == digest
