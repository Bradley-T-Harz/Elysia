"""Governed Python-only patch worker."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from .contract import (
    PatchFileChange,
    PatchWorkerRequest,
    PatchWorkerResult,
    PatchWorkerStatus,
)
from .patch_apply import apply_exact_replacement
from .path_guard import normalize_patch_path


MAX_DIFF_PREVIEW = 4000


def patch_hash_for_changes(changes: Iterable[PatchFileChange]) -> str:
    """Compute a stable hash over structured patch changes."""
    digest = hashlib.sha256()
    for change in changes:
        digest.update(change.file_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(change.old_text.encode("utf-8"))
        digest.update(b"\0")
        digest.update(change.new_text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def build_diff_preview(changes: Iterable[PatchFileChange], *, limit: int = MAX_DIFF_PREVIEW) -> tuple[str, bool]:
    """Build a bounded human-readable preview for exact replacements."""
    parts: list[str] = []
    for change in changes:
        parts.append(f"--- {change.file_path}\n+++ {change.file_path}\n")
        parts.append("- " + change.old_text[:1000].replace("\n", "\n- ") + "\n")
        parts.append("+ " + change.new_text[:1000].replace("\n", "\n+ ") + "\n")
    preview = "".join(parts)
    if len(preview) > limit:
        return preview[:limit] + "\n...diff preview truncated...", True
    return preview, False


def _blocked(
    request: PatchWorkerRequest,
    errors: list[str],
    *,
    patch_hash: str = "",
    files_refused: list[str] | None = None,
) -> PatchWorkerResult:
    preview, truncated = build_diff_preview(request.changes)
    return PatchWorkerResult(
        status=PatchWorkerStatus.BLOCKED,
        request_id=request.request_id,
        repo_key=request.repo_key,
        patch_id=request.patch_id,
        patch_hash=patch_hash,
        files_refused=list(files_refused or []),
        diff_preview=preview,
        diff_preview_truncated=truncated,
        rollback_note=request.rollback_note,
        approval_reference=request.approval_reference,
        errors=errors,
    )


def run_patch_worker(request: PatchWorkerRequest) -> PatchWorkerResult:
    """Validate and apply one approved structured patch."""
    patch_hash = patch_hash_for_changes(request.changes)
    preview, truncated = build_diff_preview(request.changes)

    if not request.approved_by_user or not request.approval_reference:
        return _blocked(request, ["Exact user approval is required before patch application."], patch_hash=patch_hash)
    if not request.changes:
        return _blocked(request, ["At least one patch change is required."], patch_hash=patch_hash)
    if request.expected_patch_hash and request.expected_patch_hash != patch_hash:
        return _blocked(request, ["Patch hash mismatch; refusing to apply."], patch_hash=patch_hash)

    total_size = sum(len(change.old_text) + len(change.new_text) for change in request.changes)
    if total_size > request.max_patch_bytes:
        return _blocked(request, ["Patch exceeds configured byte limit."], patch_hash=patch_hash)

    approved = {str(path).strip() for path in request.approved_files}
    targets: list[tuple[Path, PatchFileChange]] = []
    refused: list[str] = []
    for change in request.changes:
        if change.file_path not in approved:
            refused.append(change.file_path)
            continue
        target, error = normalize_patch_path(request.repo_root, change.file_path)
        if error or target is None:
            refused.append(change.file_path)
            continue
        targets.append((target, change))

    if refused:
        return _blocked(
            request,
            [f"Patch included unapproved or unsafe files: {', '.join(sorted(set(refused)))}."],
            patch_hash=patch_hash,
            files_refused=sorted(set(refused)),
        )

    applied: list[str] = []
    for target, change in targets:
        ok, error = apply_exact_replacement(target, change)
        if not ok:
            return PatchWorkerResult(
                status=PatchWorkerStatus.FAILED,
                request_id=request.request_id,
                repo_key=request.repo_key,
                patch_id=request.patch_id,
                patch_hash=patch_hash,
                files_changed=applied,
                files_refused=[change.file_path],
                diff_preview=preview,
                diff_preview_truncated=truncated,
                rollback_note=request.rollback_note,
                approval_reference=request.approval_reference,
                mutated_files=bool(applied),
                errors=[error],
            )
        applied.append(change.file_path)

    return PatchWorkerResult(
        status=PatchWorkerStatus.COMPLETED,
        request_id=request.request_id,
        repo_key=request.repo_key,
        patch_id=request.patch_id,
        patch_hash=patch_hash,
        files_changed=applied,
        diff_preview=preview,
        diff_preview_truncated=truncated,
        rollback_note=request.rollback_note
        or f"Restore changed files from version control or backups: {', '.join(applied)}.",
        post_apply_summary=f"Applied approved patch {request.patch_id} to {len(applied)} file(s).",
        mutated_files=bool(applied),
        approval_reference=request.approval_reference,
    )


__all__ = ("build_diff_preview", "patch_hash_for_changes", "run_patch_worker")
