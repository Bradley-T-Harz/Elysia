"""Contract models for the governed Python-only patch worker."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PatchWorkerStatus(str, Enum):
    """Small status vocabulary for approved patch application."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class PatchFileChange:
    """One exact text replacement in one approved repo file."""

    file_path: str
    old_text: str
    new_text: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "old_text_length": len(self.old_text),
            "new_text_length": len(self.new_text),
        }


@dataclass
class PatchWorkerRequest:
    """Patch request accepted by the worker after code-service validation."""

    request_id: str
    repo_key: str
    repo_root: str
    patch_id: str
    expected_patch_hash: str
    changes: list[PatchFileChange]
    approved_files: list[str]
    approval_reference: str
    approved_by_user: bool = False
    rollback_note: str = ""
    max_patch_bytes: int = 80_000


@dataclass
class PatchWorkerResult:
    """Structured result for one patch-worker attempt."""

    status: PatchWorkerStatus
    request_id: str = ""
    repo_key: str = ""
    patch_id: str = ""
    patch_hash: str = ""
    files_changed: list[str] = field(default_factory=list)
    files_refused: list[str] = field(default_factory=list)
    diff_preview: str = ""
    diff_preview_truncated: bool = False
    rollback_note: str = ""
    post_apply_summary: str = ""
    mutated_files: bool = False
    shell_used: bool = False
    git_mutation_used: bool = False
    network_access_used: bool = False
    approval_required: bool = True
    approval_reference: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == PatchWorkerStatus.COMPLETED

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status.value,
            "request_id": self.request_id,
            "repo_key": self.repo_key,
            "patch_id": self.patch_id,
            "patch_hash": self.patch_hash,
            "files_changed": list(self.files_changed),
            "files_refused": list(self.files_refused),
            "diff_preview": self.diff_preview,
            "diff_preview_truncated": self.diff_preview_truncated,
            "rollback_note": self.rollback_note,
            "post_apply_summary": self.post_apply_summary,
            "mutated_files": self.mutated_files,
            "shell_used": self.shell_used,
            "git_mutation_used": self.git_mutation_used,
            "network_access_used": self.network_access_used,
            "approval_required": self.approval_required,
            "approval_reference": self.approval_reference,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


__all__ = (
    "PatchFileChange",
    "PatchWorkerRequest",
    "PatchWorkerResult",
    "PatchWorkerStatus",
)
