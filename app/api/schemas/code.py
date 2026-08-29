"""Governed Coder 1.0 API schemas."""

from __future__ import annotations

from pydantic import Field
try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover
    ConfigDict = None  # type: ignore[assignment]

from .common import ApprovalState, ElysiaSchemaModel, LocalityState


class PatchChange(ElysiaSchemaModel):
    if ConfigDict is not None:
        model_config = ConfigDict(
            extra="forbid",
            populate_by_name=True,
            validate_assignment=True,
            use_enum_values=True,
            str_strip_whitespace=False,
        )
    else:  # pragma: no cover
        class Config:
            extra = "forbid"
            anystr_strip_whitespace = False

    file_path: str = Field(..., min_length=1)
    old_text: str = Field(..., min_length=1)
    new_text: str = Field(..., min_length=1)


class PatchApplyRequest(ElysiaSchemaModel):
    request_id: str | None = None
    repo_key: str = "elysia"
    patch_id: str = Field(..., min_length=1)
    expected_patch_hash: str = Field(..., min_length=1)
    changes: list[PatchChange] = Field(..., min_length=1)
    approved_files: list[str] = Field(..., min_length=1)
    approval_reference: str = Field(..., min_length=1)
    approved_by_user: bool = False
    rollback_note: str | None = None


class PatchApplyResponseData(ElysiaSchemaModel):
    request_id: str
    repo_key: str
    patch_id: str
    patch_hash: str
    status: str
    files_changed: list[str] = Field(default_factory=list)
    files_refused: list[str] = Field(default_factory=list)
    diff_preview: str = ""
    diff_preview_truncated: bool = False
    rollback_note: str = ""
    post_apply_summary: str = ""
    approval_state: ApprovalState = ApprovalState.NEEDED
    mutated_files: bool = False
    shell_used: bool = False
    git_mutation_used: bool = False
    network_access_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class FocusedCommandRunRequest(ElysiaSchemaModel):
    request_id: str | None = None
    repo_key: str = "elysia"
    command_key: str = Field(..., min_length=1)
    argv: list[str] = Field(..., min_length=1)
    approval_reference: str = Field(..., min_length=1)
    approved_by_user: bool = False
    timeout_seconds: int = Field(default=120, ge=1, le=600)


class FocusedCommandRunResponseData(ElysiaSchemaModel):
    request_id: str
    repo_key: str
    command_key: str
    argv: list[str] = Field(default_factory=list)
    cwd_label: str = ""
    status: str
    allowlist_matched: bool = False
    approved_by_user: bool = False
    approval_state: ApprovalState = ApprovalState.NEEDED
    exit_code: int | None = None
    duration_ms: int = 0
    stdout_preview: str = ""
    stderr_preview: str = ""
    output_truncated: bool = False
    timeout_seconds: int = 0
    locality: LocalityState = LocalityState.LOCAL
    shell_used: bool = False
    broad_shell_used: bool = False
    network_access_used: bool = False
    mutated_files: bool = False
    git_mutation_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


__all__ = (
    "FocusedCommandRunRequest",
    "FocusedCommandRunResponseData",
    "PatchApplyRequest",
    "PatchApplyResponseData",
    "PatchChange",
)
