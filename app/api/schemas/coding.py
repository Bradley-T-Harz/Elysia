"""Schemas for the local VS Code coding bridge MVP."""

from __future__ import annotations

from pydantic import Field
from pydantic import ConfigDict

from app.api.schemas.common import ElysiaSchemaModel


class CodingBoundaryFlags(ElysiaSchemaModel):
    local_only: bool = True
    marketplace_account_required: bool = False
    cloud_upload_allowed: bool = False
    selected_file_read_allowed: bool = False
    patch_proposal_allowed: bool = False
    patch_apply_allowed: bool = False
    command_execution_allowed: bool = False
    test_execution_allowed: bool = False
    git_mutation_allowed: bool = False
    package_manager_allowed: bool = False
    autonomous_loop_allowed: bool = False
    source_contents_included: bool = False


class CodingBridgeStatus(ElysiaSchemaModel):
    available: bool = True
    contract_version: str
    local_api_base: str = "http://127.0.0.1:8000"
    boundaries: CodingBoundaryFlags = Field(default_factory=CodingBoundaryFlags)
    enabled_endpoints: list[str] = Field(default_factory=list)
    disabled_capabilities: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CodingSessionStartRequest(ElysiaSchemaModel):
    workspace_label: str | None = None
    workspace_root: str | None = None
    approval_mode: str = "plan_only"
    source: str = "vscode"


class CodingSession(ElysiaSchemaModel):
    session_id: str
    workspace_label: str
    workspace_root_hash: str | None = None
    approval_mode: str = "plan_only"
    source: str = "vscode"
    status: str = "active"
    created_at_utc: str
    updated_at_utc: str
    boundaries: CodingBoundaryFlags = Field(default_factory=CodingBoundaryFlags)


class CodingChatRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    message: str
    workspace_label: str | None = None
    approval_mode: str = "plan_only"
    approved_file_context: "ApprovedFileContext | None" = None
    selected_context: list["SelectedContextItem"] = Field(default_factory=list, max_length=20)


class ApprovedFileContext(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    file_label: str
    relative_path: str
    language_hint: str | None = None
    path_hash: str
    content_preview: str
    source_contents_included: bool = True
    approval_granted: bool = True


class SelectedContextItem(ElysiaSchemaModel):
    relative_path: str
    context_kind: str = "scm_metadata"
    scm_status: str | None = None
    staged: bool = False
    source_contents_included: bool = False


class CodingChatResult(ElysiaSchemaModel):
    session_id: str | None = None
    assistant_text: str
    approval_mode: str = "plan_only"
    plan: list[str] = Field(default_factory=list)
    refused_capabilities: list[str] = Field(default_factory=list)
    boundaries: CodingBoundaryFlags = Field(default_factory=CodingBoundaryFlags)
    used_approved_file_context: bool = False
    patch_proposal: dict | None = None
    context_receipt: dict[str, object] = Field(default_factory=dict)


class RepoInspectPreviewRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    max_depth: int | None = None
    max_entries: int | None = None


class RepoPreviewEntry(ElysiaSchemaModel):
    relative_path: str
    kind: str
    depth: int


class RepoInspectPreviewResult(ElysiaSchemaModel):
    workspace_label: str
    workspace_root_hash: str
    max_depth: int
    max_entries: int
    entries_returned: int
    ignored_entries: list[str] = Field(default_factory=list)
    preview_entries: list[RepoPreviewEntry] = Field(default_factory=list)
    source_contents_included: bool = False
    files_read: list[str] = Field(default_factory=list)
    boundaries: CodingBoundaryFlags = Field(default_factory=CodingBoundaryFlags)


class CodingRepoApprovalStatusRequest(ElysiaSchemaModel):
    workspace_root: str


class CodingRepoApprovalStatus(ElysiaSchemaModel):
    status: str
    workspace_label: str
    workspace_root_hash: str
    approved: bool = False
    revoked: bool = False
    approval_source: str | None = None
    blocked_reason: str | None = None
    raw_path_exposed: bool = False
    warnings: list[str] = Field(default_factory=list)


class CodingRepoApprovalPlanRequest(ElysiaSchemaModel):
    workspace_root: str


class CodingRepoApprovalPlan(ElysiaSchemaModel):
    status: str
    plan_id: str | None = None
    plan_hash: str | None = None
    workspace_label: str
    workspace_root_hash: str
    expires_at_utc: str | None = None
    consequences: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    raw_path_exposed: bool = False
    warnings: list[str] = Field(default_factory=list)


class CodingRepoApprovalApplyRequest(ElysiaSchemaModel):
    plan_id: str
    plan_hash: str
    operator_approved: bool = False
    confirmation_phrase: str | None = None


class CodingRepoRevokeRequest(ElysiaSchemaModel):
    workspace_root: str
    operator_approved: bool = False
    confirmation_phrase: str | None = None


class CodingRepoApprovalResult(ElysiaSchemaModel):
    status: str
    workspace_label: str | None = None
    workspace_root_hash: str | None = None
    approved: bool = False
    revoked: bool = False
    operation_id: str | None = None
    audit_written: bool = False
    blocked_reason: str | None = None
    raw_path_exposed: bool = False
    warnings: list[str] = Field(default_factory=list)


__all__ = (
    "CodingBoundaryFlags",
    "ApprovedFileContext",
    "SelectedContextItem",
    "CodingBridgeStatus",
    "CodingChatRequest",
    "CodingChatResult",
    "CodingSession",
    "CodingSessionStartRequest",
    "RepoInspectPreviewRequest",
    "RepoInspectPreviewResult",
    "RepoPreviewEntry",
    "CodingRepoApprovalApplyRequest",
    "CodingRepoApprovalPlan",
    "CodingRepoApprovalPlanRequest",
    "CodingRepoApprovalResult",
    "CodingRepoApprovalStatus",
    "CodingRepoApprovalStatusRequest",
    "CodingRepoRevokeRequest",
)
