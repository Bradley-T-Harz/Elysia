"""Schemas for policy-bound archive and package-container stewardship."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.api.schemas.common import ElysiaSchemaModel


ArchiveCapabilityState = Literal[
    "available",
    "list_only",
    "extract_sandbox_only",
    "lab_only",
    "blocked",
    "unsupported",
    "unavailable_by_design",
]


class ArchiveToolStatus(ElysiaSchemaModel):
    tool: str
    available: bool
    path_hash: str | None = None
    purpose: str
    license_status: str = "system_tool"


class ArchiveAutonomyTruth(ElysiaSchemaModel):
    default_level: int = 0
    autonomous_inspection: bool = False
    autonomous_extraction: bool = False
    autonomous_package_install: bool = False
    autonomous_execution: bool = False
    extraction_requires_fresh_human_approval: bool = True
    install_execute_unavailable_by_design: bool = True


class ArchiveTypeDescriptor(ElysiaSchemaModel):
    type_id: str
    label: str
    extensions: list[str] = Field(default_factory=list)
    inspection_state: ArchiveCapabilityState
    extraction_state: ArchiveCapabilityState
    package_container: bool = False
    list_supported: bool = True
    metadata_supported: bool = True
    selected_sandbox_extraction_supported: bool = False
    install_state: ArchiveCapabilityState = "unavailable_by_design"
    execute_state: ArchiveCapabilityState = "unavailable_by_design"
    creation_state: ArchiveCapabilityState = "unavailable_by_design"
    tool_license_status: str = "not_applicable"
    notes: list[str] = Field(default_factory=list)


class ArchiveRiskFlag(ElysiaSchemaModel):
    code: str
    severity: Literal["info", "warning", "high", "blocked"]
    count: int = Field(default=1, ge=1)
    blocks_extraction: bool = False
    summary: str


class ArchiveMemberRecord(ElysiaSchemaModel):
    index: int = Field(ge=0)
    display_path: str
    path_hash: str
    normalized_relative_path: str | None = None
    collision_key_hash: str | None = None
    kind: str = "file"
    compressed_size: int = Field(default=0, ge=0)
    uncompressed_size: int = Field(default=0, ge=0)
    mode: int | None = None
    mtime: str | None = None
    is_directory: bool = False
    is_regular_file: bool = True
    is_symlink: bool = False
    is_hardlink: bool = False
    is_device: bool = False
    is_fifo: bool = False
    is_socket: bool = False
    is_executable: bool = False
    is_encrypted: bool = False
    is_nested_archive_candidate: bool = False
    extractable: bool = False
    blocked_reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)


class ArchivePackageMetadata(ElysiaSchemaModel):
    container_kind: str
    summary: dict[str, Any] = Field(default_factory=dict)
    scripts_present: list[str] = Field(default_factory=list)
    native_binary_count: int = 0
    executable_entrypoint_count: int = 0
    metadata_truncated: bool = False
    install_supported: bool = False
    execute_supported: bool = False
    warnings: list[str] = Field(default_factory=list)


class ArchiveManifestArtifact(ElysiaSchemaModel):
    artifact_id: str
    artifact_kind: str
    sha256: str
    size_bytes: int = Field(ge=0)


class ArchiveInspectRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    workspace_root: str
    archive_path: str
    approval_granted: bool = False
    approval_reason: str | None = None


class ArchiveInspectResponse(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    file_label: str
    relative_path: str | None = None
    path_hash: str
    archive_sha256: str | None = None
    archive_size_bytes: int = 0
    extension_type: str = "unknown"
    detected_type: str = "unknown"
    extension_content_match: bool = False
    descriptor: ArchiveTypeDescriptor
    member_count: int = 0
    directory_count: int = 0
    projected_uncompressed_bytes: int = 0
    largest_member_bytes: int = 0
    nested_archive_count: int = 0
    compression_ratio: float = 0.0
    encrypted: bool = False
    members: list[ArchiveMemberRecord] = Field(default_factory=list)
    member_list_truncated: bool = False
    risk_flags: list[ArchiveRiskFlag] = Field(default_factory=list)
    risk_counts: dict[str, int] = Field(default_factory=dict)
    package_metadata: ArchivePackageMetadata | None = None
    manifest_digest: str | None = None
    artifacts: list[ArchiveManifestArtifact] = Field(default_factory=list)
    policy_version: str
    tool_used: str = "python_stdlib"
    blocked_reason: str | None = None
    audit_written: bool = False
    warnings: list[str] = Field(default_factory=list)


class ArchiveExtractionPlanRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    workspace_root: str
    archive_path: str
    selected_member_indexes: list[int] = Field(default_factory=list, max_length=10_000)
    sandbox_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,63}$")
    approval_granted: bool = False
    approval_reason: str | None = None


class ArchiveExtractionPlan(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    file_label: str
    relative_path: str | None = None
    archive_type: str
    archive_sha256: str
    archive_size_bytes: int
    manifest_digest: str
    selected_member_indexes: list[int] = Field(default_factory=list)
    selected_members_digest: str
    selected_file_count: int = 0
    projected_write_bytes: int = 0
    sandbox_id: str
    sandbox_destination_hash: str
    plan_hash: str
    policy_version: str
    approval_required: bool = True
    exact_approval: dict[str, Any] = Field(default_factory=dict)
    artifact: ArchiveManifestArtifact | None = None
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ArchiveExtractionApplyRequest(ArchiveExtractionPlanRequest):
    operation_id: str = Field(pattern=r"^archive_[a-z_]+_[0-9a-f]{16}$")
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    expected_archive_sha256: str
    expected_manifest_digest: str
    expected_plan_hash: str


class ArchiveExtractionResult(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    approval_id: str | None = None
    archive_type: str
    archive_sha256: str
    manifest_digest: str
    plan_hash: str
    sandbox_id: str
    sandbox_destination_hash: str
    extracted_file_count: int = 0
    extracted_bytes: int = 0
    blocked_member_count: int = 0
    skipped_member_count: int = 0
    artifact: ArchiveManifestArtifact | None = None
    audit_written: bool = False
    mutation_performed: bool = False
    source_mutated: bool = False
    project_root_written: bool = False
    install_performed: bool = False
    execution_performed: bool = False
    cleanup_performed: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ArchiveJobState(ElysiaSchemaModel):
    operation_id: str
    operation_kind: str
    status: str
    archive_sha256: str | None = None
    approval_id: str | None = None
    artifact_id: str | None = None
    cancel_requested: bool = False
    started_at_utc: str
    completed_at_utc: str | None = None
    compact_summary: dict[str, Any] = Field(default_factory=dict)


__all__ = (
    "ArchiveAutonomyTruth",
    "ArchiveCapabilityState",
    "ArchiveExtractionApplyRequest",
    "ArchiveExtractionPlan",
    "ArchiveExtractionPlanRequest",
    "ArchiveExtractionResult",
    "ArchiveInspectRequest",
    "ArchiveInspectResponse",
    "ArchiveJobState",
    "ArchiveManifestArtifact",
    "ArchiveMemberRecord",
    "ArchivePackageMetadata",
    "ArchiveRiskFlag",
    "ArchiveToolStatus",
    "ArchiveTypeDescriptor",
)
