"""Backup and derived-copy helpers for governed data stewardship."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4


def backup_path_for(path: Path) -> Path:
    return path.with_name(f"{path.name}.elysia-backup-{uuid4().hex[:8]}")


def create_backup(path: Path) -> dict[str, str | bool]:
    backup = backup_path_for(path)
    if path.is_dir():
        shutil.copytree(path, backup)
    else:
        shutil.copy2(path, backup)
    return {"created": True, "backup_path": backup.name, "rollback_note": f"Restore {backup.name} over the source if rollback is needed."}


def copy_to_derived(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if target.exists():
            raise FileExistsError(str(target))
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


__all__ = ("backup_path_for", "copy_to_derived", "create_backup")
