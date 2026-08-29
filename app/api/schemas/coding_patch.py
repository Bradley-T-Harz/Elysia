"""Schemas for non-mutating coding patch proposals."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from app.api.schemas.coding import CodingBoundaryFlags
from app.api.schemas.common import ElysiaSchemaModel


class CodingPatchProposeRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    approval_mode: str = "plan_only"
    workspace_root: str
    target_files: list[str] = Field(default_factory=list)
    change_summary: str
    proposed_diff: str | None = None


class CodingPatchProposeResult(ElysiaSchemaModel):
    # Unified diffs are byte-sensitive review artifacts. In particular, a
    # final context line may require its trailing newline to match the exact
    # approved source and patch hash, so response validation must not trim it.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    status: str
    patch_id: str
    patch_hash: str
    expected_content_hash: str | None = None
    change_summary: str
    target_files: list[str] = Field(default_factory=list)
    allowed_target_files: list[str] = Field(default_factory=list)
    blocked_target_files: list[dict[str, str]] = Field(default_factory=list)
    diff_preview: str | None = None
    truncated: bool = False
    apply_allowed: bool = False
    approval_required_for_apply: bool = True
    rollback_note: str
    warnings: list[str] = Field(default_factory=list)
    boundaries: CodingBoundaryFlags = Field(default_factory=CodingBoundaryFlags)


class CodingPatchApplyRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    approval_mode: str = "plan_only"
    workspace_root: str
    target_file: str
    proposed_diff: str
    expected_content_hash: str
    patch_hash: str
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    approval_phrase: str | None = None


class CodingPatchApplyResult(ElysiaSchemaModel):
    status: str
    target_relative_path: str | None = None
    patch_hash: str
    expected_content_hash: str
    previous_content_hash: str | None = None
    new_content_hash: str | None = None
    backup_relative_path: str | None = None
    rollback_receipt_id: str | None = None
    approval_id: str | None = None
    mutation_performed: bool = False
    audit_written: bool = False
    blocked_reason: str | None = None
    rollback_note: str
    warnings: list[str] = Field(default_factory=list)


__all__ = (
    "CodingPatchApplyRequest",
    "CodingPatchApplyResult",
    "CodingPatchProposeRequest",
    "CodingPatchProposeResult",
)
