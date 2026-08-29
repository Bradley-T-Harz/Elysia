"""Bounded metadata-only repo inspection preview for the VS Code bridge."""

from __future__ import annotations

import fnmatch
from hashlib import sha256
from pathlib import Path

from app.api.coding_policy_service import coding_boundary_flags, load_coding_policy, preview_limits
from app.api.schemas.coding import (
    RepoInspectPreviewRequest,
    RepoInspectPreviewResult,
    RepoPreviewEntry,
)


def _root_hash(path: Path) -> str:
    return sha256(str(path).encode("utf-8")).hexdigest()[:24]


def _is_ignored(relative_path: str, name: str, ignored_names: set[str], ignored_globs: list[str]) -> bool:
    normalized = relative_path.replace("\\", "/")
    if name in ignored_names or normalized in ignored_names:
        return True
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(normalized, pattern) for pattern in ignored_globs)


def inspect_repo_preview(payload: RepoInspectPreviewRequest) -> RepoInspectPreviewResult:
    policy = load_coding_policy()
    policy_max_depth, policy_max_entries = preview_limits(policy)
    max_depth = min(int(payload.max_depth or policy_max_depth), policy_max_depth)
    max_entries = min(int(payload.max_entries or policy_max_entries), policy_max_entries)
    ignored_names = set(policy.get("ignored_names") or [])
    ignored_globs = list(policy.get("ignored_globs") or [])

    root = Path(payload.workspace_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return RepoInspectPreviewResult(
            workspace_label=root.name or "workspace",
            workspace_root_hash=_root_hash(root),
            max_depth=max_depth,
            max_entries=max_entries,
            entries_returned=0,
            ignored_entries=[],
            preview_entries=[],
            boundaries=coding_boundary_flags(policy),
        )

    preview_entries: list[RepoPreviewEntry] = []
    ignored_entries: list[str] = []
    queue: list[tuple[Path, int]] = [(root, 0)]

    while queue and len(preview_entries) < max_entries:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        try:
            children = sorted(current.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        except OSError:
            continue
        for child in children:
            if len(preview_entries) >= max_entries:
                break
            try:
                relative = child.relative_to(root).as_posix()
            except ValueError:
                continue
            if _is_ignored(relative, child.name, ignored_names, ignored_globs):
                ignored_entries.append(relative)
                continue
            kind = "directory" if child.is_dir() else "file"
            preview_entries.append(
                RepoPreviewEntry(relative_path=relative, kind=kind, depth=depth + 1)
            )
            if child.is_dir() and depth + 1 < max_depth:
                queue.append((child, depth + 1))

    return RepoInspectPreviewResult(
        workspace_label=root.name or "workspace",
        workspace_root_hash=_root_hash(root),
        max_depth=max_depth,
        max_entries=max_entries,
        entries_returned=len(preview_entries),
        ignored_entries=ignored_entries,
        preview_entries=preview_entries,
        source_contents_included=False,
        files_read=[],
        boundaries=coding_boundary_flags(policy),
    )


__all__ = ("inspect_repo_preview",)
