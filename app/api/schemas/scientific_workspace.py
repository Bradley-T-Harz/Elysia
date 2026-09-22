"""Typed contracts for project-bound scientific workspace authority."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScientificWorkspaceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ScientificWorkspaceStatusRequest(ScientificWorkspaceModel):
    project_id: str = Field(min_length=1, max_length=160)
    workspace_root: str = Field(min_length=1, max_length=4096)


class ScientificWorkspacePlanRequest(ScientificWorkspaceModel):
    project_id: str = Field(min_length=1, max_length=160)
    workspace_root: str = Field(min_length=1, max_length=4096)


class ScientificWorkspaceApplyRequest(ScientificWorkspaceModel):
    project_id: str = Field(min_length=1, max_length=160)
    plan_id: str = Field(min_length=1, max_length=160)
    plan_hash: str = Field(min_length=1, max_length=160)

    operator_approved: bool = False
    confirmation_phrase: str = Field(
        default="",
        max_length=160,
    )


class ScientificWorkspaceRevokeRequest(ScientificWorkspaceModel):
    project_id: str = Field(min_length=1, max_length=160)
    workspace_root: str = Field(min_length=1, max_length=4096)

    operator_approved: bool = False
    confirmation_phrase: str = Field(
        default="",
        max_length=160,
    )


class ScientificWorkspaceManifestRequest(ScientificWorkspaceModel):
    project_id: str = Field(min_length=1, max_length=160)
    workspace_root: str = Field(min_length=1, max_length=4096)

    max_entries: int = Field(
        default=500,
        ge=1,
        le=5000,
    )


class ScientificWorkspaceApprovalPlan(ScientificWorkspaceModel):
    status: str
    plan_id: str | None = None
    plan_hash: str | None = None

    project_id: str
    workspace_label: str
    workspace_root_hash: str

    expires_at_utc: str | None = None
    blocked_reason: str | None = None

    raw_path_exposed: bool = False

    consequences: list[str] = Field(
        default_factory=list,
    )

    warnings: list[str] = Field(
        default_factory=list,
    )


class ScientificWorkspaceApprovalResult(ScientificWorkspaceModel):
    status: str

    project_id: str
    workspace_label: str
    workspace_root_hash: str

    approved: bool = False
    revoked: bool = False

    operation_id: str | None = None
    blocked_reason: str | None = None

    raw_path_exposed: bool = False

    warnings: list[str] = Field(
        default_factory=list,
    )


class ScientificWorkspaceStatus(ScientificWorkspaceModel):
    status: str

    project_id: str
    workspace_label: str
    workspace_root_hash: str

    approved: bool = False
    revoked: bool = False

    approval_source: str | None = None
    blocked_reason: str | None = None

    raw_path_exposed: bool = False

    warnings: list[str] = Field(
        default_factory=list,
    )


class ScientificWorkspaceManifestEntry(ScientificWorkspaceModel):
    relative_path: str

    entry_kind: str = Field(
        description="regular_file or directory_store",
    )

    size_bytes: int = Field(
        default=0,
        ge=0,
    )

    type_id: str
    family: str
    adapter: str

    supported_scientific_data: bool = False

    source_mutated: bool = False
    raw_absolute_path_exposed: bool = False


class ScientificWorkspaceManifest(ScientificWorkspaceModel):
    status: str

    project_id: str
    workspace_label: str
    workspace_root_hash: str

    entries: list[ScientificWorkspaceManifestEntry] = Field(
        default_factory=list,
    )

    discovered_count: int = Field(default=0, ge=0)
    supported_count: int = Field(default=0, ge=0)
    unsupported_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)

    total_size_bytes: int = Field(
        default=0,
        ge=0,
    )

    truncated: bool = False

    raw_paths_exposed: bool = False
    source_mutated: bool = False
    network_used: bool = False

    warnings: list[str] = Field(
        default_factory=list,
    )


__all__ = (
    "ScientificWorkspaceExecutionResult",
    "ScientificWorkspaceExecutionRequest",
    "ScientificWorkspaceApplyRequest",
    "ScientificWorkspaceApprovalPlan",
    "ScientificWorkspaceApprovalResult",
    "ScientificWorkspaceManifest",
    "ScientificWorkspaceManifestEntry",
    "ScientificWorkspaceManifestRequest",
    "ScientificWorkspacePlanRequest",
    "ScientificWorkspaceRevokeRequest",
    "ScientificWorkspaceStatus",
    "ScientificWorkspaceStatusRequest",
)

class ScientificWorkspaceExecutionRequest(ScientificWorkspaceModel):
    """One fixed ScientificForge operation over one approved workspace source."""

    project_id: str = Field(
        min_length=1,
        max_length=160,
    )

    workspace_root: str = Field(
        min_length=1,
        max_length=4096,
    )

    relative_path: str = Field(
        min_length=1,
        max_length=4096,
    )

    operation: str = Field(
        min_length=1,
        max_length=80,
    )

    request_id: str | None = Field(
        default=None,
        max_length=160,
    )

    columns: list[str] = Field(
        default_factory=list,
        max_length=16,
    )

    seed: int | None = Field(
        default=None,
        ge=0,
        le=4_294_967_295,
    )

    bootstrap_samples: int = Field(
        default=10_000,
        ge=100,
        le=100_000,
    )

    confidence_level: float = Field(
        default=0.95,
        gt=0.0,
        lt=1.0,
    )


class ScientificWorkspaceExecutionResult(ScientificWorkspaceModel):
    status: str
    ok: bool = False

    project_id: str
    workspace_root_hash: str

    relative_path: str
    source_type_id: str
    source_category: str

    staged_file_id: str | None = None

    scientific_operation: str
    scientific_job_id: str | None = None

    result: dict = Field(
        default_factory=dict,
    )

    provenance: dict = Field(
        default_factory=dict,
    )

    source_mutated: bool = False
    network_used: bool = False
    shell_used: bool = False

    raw_absolute_path_exposed: bool = False

    warnings: list[str] = Field(
        default_factory=list,
    )

    errors: list[str] = Field(
        default_factory=list,
    )
