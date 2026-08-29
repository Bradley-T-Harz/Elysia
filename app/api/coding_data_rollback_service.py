"""Rollback contract helpers for data mutations."""

from __future__ import annotations


def rollback_note(backup: dict[str, object] | None = None) -> str:
    if backup and backup.get("backup_path"):
        return f"Restore {backup['backup_path']} over the source if rollback is needed."
    return "Use the derived output or project version control/backups for rollback."


__all__ = ("rollback_note",)
