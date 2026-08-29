"""Schemas for Chunk 7 database and binary stewardship."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.api.schemas.common import ElysiaSchemaModel


StewardshipCapabilityState = Literal[
    "available",
    "approval_required",
    "metadata_only",
    "lab_only",
    "blocked",
    "unavailable_by_design",
    "future_sandbox_required",
]


class DataBinaryArtifactReceipt(ElysiaSchemaModel):
    artifact_id: str
    artifact_kind: str
    sha256: str
    size_bytes: int = Field(ge=0)


class DatabaseTypeDescriptor(ElysiaSchemaModel):
    type_id: str
    label: str
    extensions: list[str] = Field(default_factory=list)
    identification_state: StewardshipCapabilityState = "available"
    metadata_state: StewardshipCapabilityState = "available"
    schema_preview_state: StewardshipCapabilityState
    read_only_open_supported: bool
    row_preview_state: StewardshipCapabilityState = "unavailable_by_design"
    arbitrary_sql_state: StewardshipCapabilityState = "unavailable_by_design"
    mutation_state: StewardshipCapabilityState = "unavailable_by_design"
    install_load_state: StewardshipCapabilityState = "unavailable_by_design"
    notes: list[str] = Field(default_factory=list)


class DatabaseInspectRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    workspace_root: str
    database_path: str
    approval_granted: bool = False
    approval_reason: str | None = None


class DatabaseInspectResponse(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    file_label: str
    relative_path: str | None = None
    path_hash: str
    source_sha256: str | None = None
    source_blake3: str | None = None
    size_bytes: int = 0
    extension_type: str = "unknown"
    detected_engine: str = "unknown"
    extension_content_match: bool = False
    magic_summary: str = "unknown"
    descriptor: DatabaseTypeDescriptor
    sidecars: dict[str, Any] = Field(default_factory=dict)
    source_state_digest: str | None = None
    schema_preview_plan_hash: str | None = None
    artifact: DataBinaryArtifactReceipt | None = None
    policy_version: str
    worker_policy_version: str
    audit_written: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class DatabaseSchemaPreviewRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    workspace_root: str
    database_path: str
    approval_id: str | None = None
    approval_token: str | None = None
    operator_approved: bool = False
    expected_source_sha256: str
    expected_plan_hash: str


class DatabaseSchemaPreviewResponse(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    approval_id: str | None = None
    file_label: str
    relative_path: str | None = None
    path_hash: str
    detected_engine: str
    source_sha256: str
    snapshot_sha256: str | None = None
    snapshot_strategy: str | None = None
    table_count: int = 0
    view_count: int = 0
    index_count: int = 0
    trigger_count: int = 0
    schema_object_count: int = 0
    risk_counts: dict[str, int] = Field(default_factory=dict)
    artifact: DataBinaryArtifactReceipt | None = None
    policy_version: str
    mutation_performed: bool = False
    row_data_returned: bool = False
    arbitrary_sql_executed: bool = False
    audit_written: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class BinaryTypeDescriptor(ElysiaSchemaModel):
    type_id: str
    label: str
    extensions: list[str] = Field(default_factory=list)
    inspection_state: StewardshipCapabilityState
    static_metadata_only: bool = True
    strings_state: StewardshipCapabilityState = "available"
    disassembly_state: StewardshipCapabilityState = "future_sandbox_required"
    execution_state: StewardshipCapabilityState = "unavailable_by_design"
    load_state: StewardshipCapabilityState = "unavailable_by_design"
    install_state: StewardshipCapabilityState = "unavailable_by_design"
    mutation_state: StewardshipCapabilityState = "unavailable_by_design"
    patch_state: StewardshipCapabilityState = "unavailable_by_design"
    notes: list[str] = Field(default_factory=list)


class BinaryRiskFlag(ElysiaSchemaModel):
    code: str
    severity: Literal["info", "warning", "high"]
    count: int = Field(default=1, ge=1)
    summary: str


class BinaryInspectRequest(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    session_id: str | None = None
    workspace_root: str
    binary_path: str
    approval_granted: bool = False
    approval_reason: str | None = None


class BinaryInspectResponse(ElysiaSchemaModel):
    status: str
    operation_id: str
    request_id: str | None = None
    file_label: str
    relative_path: str | None = None
    path_hash: str
    source_sha256: str | None = None
    source_blake3: str | None = None
    size_bytes: int = 0
    extension_type: str = "unknown"
    detected_format: str = "unknown"
    extension_content_match: bool = False
    magic_summary: str = "unknown"
    descriptor: BinaryTypeDescriptor
    architecture: str | None = None
    bitness: int | None = None
    endianness: str | None = None
    section_count: int = 0
    import_count: int = 0
    export_count: int = 0
    symbol_count: int = 0
    string_count: int = 0
    entropy: float | None = None
    executable_bit: bool = False
    debug_symbols_present: bool | None = None
    stripped: bool | None = None
    risk_flags: list[BinaryRiskFlag] = Field(default_factory=list)
    risk_counts: dict[str, int] = Field(default_factory=dict)
    artifact: DataBinaryArtifactReceipt | None = None
    policy_version: str
    worker_policy_version: str
    toolchain: list[str] = Field(default_factory=list)
    execution_performed: bool = False
    loading_performed: bool = False
    mutation_performed: bool = False
    audit_written: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


__all__ = (
    "BinaryInspectRequest",
    "BinaryInspectResponse",
    "BinaryRiskFlag",
    "BinaryTypeDescriptor",
    "DataBinaryArtifactReceipt",
    "DatabaseInspectRequest",
    "DatabaseInspectResponse",
    "DatabaseSchemaPreviewRequest",
    "DatabaseSchemaPreviewResponse",
    "DatabaseTypeDescriptor",
    "StewardshipCapabilityState",
)
