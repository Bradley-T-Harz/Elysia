"""Schemas for Chunk 8 EngineeringForge stewardship."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.api.schemas.common import ElysiaSchemaModel


EngineeringCapabilityState = Literal[
    "available",
    "approval_required",
    "metadata_only",
    "plan_only",
    "lab_only",
    "experimental",
    "future_sandbox_required",
    "blocked",
    "unsupported",
    "unavailable_by_design",
]


class EngineeringArtifactReceipt(ElysiaSchemaModel):
    artifact_id: str
    artifact_kind: str
    file_name: str
    media_type: str
    sha256: str
    size_bytes: int = Field(ge=0)
    local_only: bool = True


class EngineeringRiskFlag(ElysiaSchemaModel):
    code: str
    severity: Literal["info", "warning", "high", "blocked"]
    count: int = Field(default=1, ge=1)
    summary: str


class EngineeringExternalReference(ElysiaSchemaModel):
    reference_kind: str
    display_reference: str
    reference_hash: str
    scheme: str = "relative"
    resolution_state: Literal[
        "not_resolved",
        "inside_workspace",
        "missing",
        "blocked_absolute",
        "blocked_traversal",
        "blocked_external_scheme",
        "blocked_package_unmapped",
        "blocked_symlink",
    ]
    blocked_reason: str | None = None


class EngineeringTypeDescriptor(ElysiaSchemaModel):
    type_id: str
    label: str
    family: Literal["geometry", "cad", "robot_model", "cam", "blend", "fusion"]
    forge: str
    extensions: list[str] = Field(default_factory=list)
    identification_state: EngineeringCapabilityState = "available"
    metadata_state: EngineeringCapabilityState = "available"
    static_inspection_state: EngineeringCapabilityState
    report_state: EngineeringCapabilityState
    preview_state: EngineeringCapabilityState
    conversion_state: EngineeringCapabilityState
    repair_state: EngineeringCapabilityState
    simulation_state: EngineeringCapabilityState
    generation_state: EngineeringCapabilityState = "unavailable_by_design"
    physical_output_state: EngineeringCapabilityState = "unavailable_by_design"
    maximum_live_level: int = Field(ge=0, le=9)
    notes: list[str] = Field(default_factory=list)


class EngineeringInspectRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    workspace_root: str
    file_path: str
    approval_granted: bool = False
    approval_reason: str | None = None


class EngineeringInspectResponse(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    file_label: str
    relative_path: str | None = None
    path_hash: str
    source_sha256: str | None = None
    size_bytes: int = Field(default=0, ge=0)
    extension_type: str = "unknown"
    detected_type: str = "unknown"
    extension_content_match: bool = False
    magic_summary: str = "unknown"
    descriptor: EngineeringTypeDescriptor
    report: dict[str, Any] = Field(default_factory=dict)
    capability_truth: dict[str, str] = Field(default_factory=dict)
    risk_flags: list[EngineeringRiskFlag] = Field(default_factory=list)
    risk_counts: dict[str, int] = Field(default_factory=dict)
    external_references: list[EngineeringExternalReference] = Field(default_factory=list)
    external_reference_count: int = 0
    artifacts: list[EngineeringArtifactReceipt] = Field(default_factory=list)
    preview_plan_hash: str | None = None
    preview_kind: str | None = None
    policy_version: str
    worker_policy_version: str
    worker_key: str
    worker_state: str
    audit_written: bool = False
    source_mutated: bool = False
    network_used: bool = False
    scripts_executed: bool = False
    plugins_loaded: bool = False
    physical_output_performed: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class EngineeringPreviewPlanRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    workspace_root: str
    file_path: str
    approval_granted: bool = False
    approval_reason: str | None = None


class EngineeringPreviewPlan(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    file_label: str
    relative_path: str | None = None
    path_hash: str
    source_sha256: str
    size_bytes: int = Field(ge=0)
    detected_type: str
    family: str
    preview_kind: str
    plan_hash: str
    policy_version: str
    approval_required: bool = True
    exact_approval: dict[str, Any] = Field(default_factory=dict)
    artifact: EngineeringArtifactReceipt | None = None
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class EngineeringPreviewApplyRequest(EngineeringPreviewPlanRequest):
    operation_id: str = Field(pattern=r"^engineering_preview_[0-9a-f]{16}$")
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    expected_source_sha256: str
    expected_plan_hash: str


class EngineeringPreviewResult(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    approval_id: str | None = None
    file_label: str
    relative_path: str | None = None
    path_hash: str
    source_sha256: str
    detected_type: str
    family: str
    preview_kind: str
    plan_hash: str
    artifact: EngineeringArtifactReceipt | None = None
    receipt_artifact: EngineeringArtifactReceipt | None = None
    policy_version: str
    audit_written: bool = False
    source_mutated: bool = False
    project_root_written: bool = False
    network_used: bool = False
    scripts_executed: bool = False
    plugins_loaded: bool = False
    physical_output_performed: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class EngineeringJobState(ElysiaSchemaModel):
    operation_id: str
    operation_kind: str
    status: str
    source_sha256: str | None = None
    approval_id: str | None = None
    artifact_id: str | None = None
    cancel_requested: bool = False
    started_at_utc: str
    completed_at_utc: str | None = None
    compact_summary: dict[str, Any] = Field(default_factory=dict)


__all__ = (
    "EngineeringArtifactReceipt",
    "EngineeringCapabilityState",
    "EngineeringExternalReference",
    "EngineeringInspectRequest",
    "EngineeringInspectResponse",
    "EngineeringJobState",
    "EngineeringPreviewApplyRequest",
    "EngineeringPreviewPlan",
    "EngineeringPreviewPlanRequest",
    "EngineeringPreviewResult",
    "EngineeringRiskFlag",
    "EngineeringTypeDescriptor",
)
