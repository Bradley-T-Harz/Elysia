"""Recoverable, audited backups for governed coding mutations."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record


@dataclass(frozen=True)
class CodingBackupReceipt:
    receipt_id: str
    backup_relative_path: str
    source_relative_path: str
    source_hash: str
    audit_written: bool


def hash_file_bytes(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_coding_backup(
    *,
    workspace_root: Path,
    source_path: Path,
    source_relative_path: str,
    operation_kind: str,
    session_id: str | None,
) -> CodingBackupReceipt:
    receipt_id = f"backup_{uuid4().hex[:16]}"
    safe_name = "".join(char for char in source_path.name if char.isalnum() or char in {".", "_", "-"}) or "file"
    backup_root = workspace_root / ".elysia_backups"
    backup_path = backup_root / f"{receipt_id}_{safe_name}.bak"
    backup_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, backup_path)
    source_hash = hash_file_bytes(source_path)
    audit_written = write_coding_audit_record(
        "backup_created",
        receipt_id,
        {
            "session_id": session_id,
            "operation_kind": operation_kind,
            "source_relative_path": source_relative_path,
            "backup_relative_path": backup_path.relative_to(workspace_root).as_posix(),
            "source_hash": source_hash,
        },
    )
    return CodingBackupReceipt(
        receipt_id=receipt_id,
        backup_relative_path=backup_path.relative_to(workspace_root).as_posix(),
        source_relative_path=source_relative_path,
        source_hash=source_hash,
        audit_written=audit_written,
    )


__all__ = ("CodingBackupReceipt", "create_coding_backup", "hash_file_bytes")
