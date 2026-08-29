"""Validation helpers for non-mutating patch proposals."""

from __future__ import annotations

from app.api.coding_path_guard_service import guard_workspace_path
from app.api.coding_file_type_registry import detect_file_type


def validate_patch_targets(workspace_root: str, target_files: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    allowed: list[str] = []
    blocked: list[dict[str, str]] = []
    for target in target_files:
        guarded = guard_workspace_path(
            workspace_root=workspace_root,
            target_path=target,
            require_existing=False,
            allow_directory=False,
        )
        if guarded.allowed and guarded.relative_path:
            raw = (
                guarded.target_path.read_bytes()[:4096]
                if guarded.target_path.exists() and guarded.target_path.is_file()
                else None
            )
            descriptor = detect_file_type(guarded.target_path, raw)
            if descriptor.patchable and descriptor.adapter != "blocked":
                allowed.append(guarded.relative_path)
            else:
                blocked.append({"path": target, "reason": "file_type_not_patchable"})
        else:
            blocked.append({"path": target, "reason": guarded.reason or "blocked"})
    return allowed, blocked


__all__ = ("validate_patch_targets",)
