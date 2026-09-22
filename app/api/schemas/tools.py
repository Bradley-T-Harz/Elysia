"""
Compact tool-ledger schema models for request trace surfaces.

This module is schema-only. It describes UI-safe tool availability/use truth
without executing tools, authorizing tools, routing tools, or consulting runtime
or policy services.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import ApprovalState, ElysiaSchemaModel, LocalityState


class ToolLedgerState(str, Enum):
    """
    Compact state vocabulary for one tool-ledger entry.

    Availability, invocation and successful completion are distinct. Retain
    the actual bounded operation outcome; ``used`` alone does not mean success.
    """

    AVAILABLE = "available"
    USED = "used"
    PLANNED = "planned"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NOT_NEEDED = "not_needed"
    CLARIFICATION_REQUIRED = "clarification_required"
    REFERENCE_REQUIRED = "reference_required"
    UNSUPPORTED = "unsupported"
    CONTRACT_ONLY = "contract_only"
    DRY_RUN_READY = "dry_run_ready"


class ToolBoundaryKind(str, Enum):
    """
    Compact boundary vocabulary for a tool's possible or actual work surface.
    """

    LOCAL = "local"
    LOCAL_PRIVATE = "local_private"
    LOCAL_SELECTED_FILE = "local_selected_file"
    LOCAL_SELECTED_REPO = "local_selected_repo"
    EXTERNAL_PUBLIC_WEB = "external_public_web"
    HOST_OR_SANDBOX = "host_or_sandbox"
    FILE_MUTATION = "file_mutation"
    APPROVED_SCIENTIFIC_WORKSPACE = "approved_scientific_workspace"
    TYPED_SCIENTIFIC_WORKFLOW = "typed_scientific_workflow"
    PRIVATE_SNAPSHOT_OR_STATIC_WORKER = "private_snapshot_or_static_worker"
    UNKNOWN = "unknown"


class ToolLedgerEntry(ElysiaSchemaModel):
    """
    UI-safe ledger truth for one tool or worker organ.

    Dangerous-use fields default to false and should only be set true by
    governed trace producers that actually observed the action.
    """

    tool_key: str = Field(..., min_length=1)
    tool_label: str | None = None
    tool_kind: str | None = None
    state: ToolLedgerState = ToolLedgerState.UNKNOWN
    available: bool = False
    used: bool = False
    approval_required: bool = False
    approval_state: ApprovalState = ApprovalState.UNKNOWN
    locality: LocalityState = LocalityState.UNKNOWN
    boundary_kind: ToolBoundaryKind = ToolBoundaryKind.UNKNOWN
    boundary_state: str | None = None
    worker_name: str | None = None
    operation: str | None = None
    summary: str | None = None
    input_count: int = Field(default=0, ge=0)
    output_count: int = Field(default=0, ge=0)
    mutated_files: bool = False
    network_access_used: bool = False
    private_context_sent: bool = False
    shell_used: bool = False
    git_mutation_used: bool = False
    cloud_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    session_id: str | None = None
    operation_id: str | None = None
    approval_id: str | None = None
    workspace_root_hash: str | None = None
    relative_paths: list[str] = Field(default_factory=list)
    source_hash: str | None = None
    parameter_hash: str | None = None
    source_type_id: str | None = None
    plan_hash: str | None = None
    result_hash: str | None = None
    mutation_class: str | None = None
    backup_summary: str | None = None
    audit_persisted: bool = False
    archive_type: str | None = None
    archive_hash: str | None = None
    manifest_hash: str | None = None
    member_count: int = Field(default=0, ge=0)
    risk_total: int = Field(default=0, ge=0)
    selected_member_count: int = Field(default=0, ge=0)
    sandbox_hash: str | None = None
    extracted_file_count: int = Field(default=0, ge=0)
    extracted_bytes: int = Field(default=0, ge=0)
    blocked_member_count: int = Field(default=0, ge=0)
    skipped_member_count: int = Field(default=0, ge=0)
    policy_version: str | None = None
    sandbox_files_written: bool = False
    project_files_mutated: bool = False
    artifact_id: str | None = None
    model_id: str | None = None
    synthetic_media: bool = False
    raw_content_logged: bool = False
    runtime_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    peak_gpu_memory_mib: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cancel_requested: bool = False


class ToolLedgerSummary(ElysiaSchemaModel):
    """
    Compact aggregate for request-level tool availability and use.
    """

    tools_available: list[ToolLedgerEntry] = Field(default_factory=list)
    tools_used: list[ToolLedgerEntry] = Field(default_factory=list)
    tool_count: int = Field(default=0, ge=0)
    used_tool_count: int = Field(default=0, ge=0)
    approval_required_count: int = Field(default=0, ge=0)
    blocked_tool_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


__all__ = (
    "ToolBoundaryKind",
    "ToolLedgerEntry",
    "ToolLedgerState",
    "ToolLedgerSummary",
)
