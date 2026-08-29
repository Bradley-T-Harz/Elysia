"""Python-only exact text replacement patch application."""

from __future__ import annotations

from pathlib import Path

from .contract import PatchFileChange


def apply_exact_replacement(target: Path, change: PatchFileChange) -> tuple[bool, str]:
    """Apply one exact replacement, failing closed on ambiguity or mismatch."""
    try:
        current = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False, f"Patch target is not UTF-8 text: {change.file_path}"
    except OSError as exc:
        return False, f"Patch target could not be read: {exc}"

    matches = current.count(change.old_text)
    if matches == 0:
        return False, f"Old text did not match patch target: {change.file_path}"
    if matches > 1:
        return False, f"Old text matched multiple times in patch target: {change.file_path}"

    updated = current.replace(change.old_text, change.new_text, 1)
    try:
        target.write_text(updated, encoding="utf-8")
    except OSError as exc:
        return False, f"Patch target could not be written: {exc}"

    return True, ""


__all__ = ("apply_exact_replacement",)
