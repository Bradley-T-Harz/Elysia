"""Schemas for read-only git preview and commit planning."""

from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingGitPreviewRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    max_changed_files: int = Field(default=200, ge=1, le=500)


class CodingGitChangedFile(ElysiaSchemaModel):
    relative_path: str
    status: str
    index_status: str
    working_tree_status: str
    staged: bool = False
    unstaged: bool = False


class CodingGitPreview(ElysiaSchemaModel):
    status: str
    repo_detected: bool = False
    approved_repo: bool = False
    branch: str | None = None
    head_ref: str | None = None
    head_commit: str | None = None
    upstream: str | None = None
    remote_present: bool | None = None
    dirty: bool | None = None
    changed_count: int = 0
    staged_count: int = 0
    unstaged_count: int = 0
    untracked_count: int = 0
    changed_files: list[CodingGitChangedFile] = Field(default_factory=list)
    workspace_root_hash: str | None = None
    mutation_allowed: bool = False
    shell_git_used: bool = False
    git_command_used: bool = False
    output_truncated: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


__all__ = ("CodingGitChangedFile", "CodingGitPreview", "CodingGitPreviewRequest")
