"""Schemas for Codev file type inspection and registry surfaces."""

from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingFileCapabilityFlags(ElysiaSchemaModel):
    readable: bool = False
    writable: bool = False
    patchable: bool = False
    creatable: bool = False
    deletable: bool = False
    renameable: bool = False


class CodingFileRiskFlags(ElysiaSchemaModel):
    secret_sensitive: bool = False
    generated_sensitive: bool = False
    lockfile: bool = False
    executable_sensitive: bool = False


class CodingFileParseSummary(ElysiaSchemaModel):
    parse_status: str = "not_applicable"
    summary: dict[str, object] = Field(default_factory=dict)


class CodingFileTypeDescriptorResponse(ElysiaSchemaModel):
    type_id: str
    label: str
    category: str
    adapter: str
    language_id: str | None = None
    capabilities: CodingFileCapabilityFlags = Field(default_factory=CodingFileCapabilityFlags)
    risk_flags: CodingFileRiskFlags = Field(default_factory=CodingFileRiskFlags)
    max_preview_bytes: int
    max_patch_bytes: int
    notes: list[str] = Field(default_factory=list)


class CodingFileTypeInspectRequest(ElysiaSchemaModel):
    workspace_root: str
    file_path: str


class CodingFileTypeInspectResponse(ElysiaSchemaModel):
    status: str
    relative_path: str | None = None
    descriptor: CodingFileTypeDescriptorResponse
    blocked_reason: str | None = None


class CodingFileAdapterPreview(ElysiaSchemaModel):
    file_type_id: str
    file_type_label: str
    category: str
    adapter: str
    language_id: str | None = None
    encoding: str | None = None
    line_ending: str | None = None
    content_hash: str | None = None
    byte_hash: str | None = None
    line_count: int = 0
    byte_count: int = 0
    truncated: bool = False
    parse_status: str = "not_applicable"
    parse_summary: dict[str, object] = Field(default_factory=dict)
    capabilities: CodingFileCapabilityFlags = Field(default_factory=CodingFileCapabilityFlags)
    risk_flags: CodingFileRiskFlags = Field(default_factory=CodingFileRiskFlags)
    redactions: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None


__all__ = (
    "CodingFileAdapterPreview",
    "CodingFileCapabilityFlags",
    "CodingFileParseSummary",
    "CodingFileRiskFlags",
    "CodingFileTypeDescriptorResponse",
    "CodingFileTypeInspectRequest",
    "CodingFileTypeInspectResponse",
)
