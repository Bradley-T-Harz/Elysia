"""Schemas for approved, bounded VS Code file preview requests."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from app.api.schemas.coding import CodingBoundaryFlags
from app.api.schemas.coding_file_types import (
    CodingFileCapabilityFlags,
    CodingFileRiskFlags,
)
from app.api.schemas.common import ElysiaSchemaModel


class CodingFileReadPreviewRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    file_path: str
    approval_granted: bool = False
    approval_reason: str | None = None
    max_bytes: int | None = None
    max_lines: int | None = None


class CodingFileReadPreviewResult(ElysiaSchemaModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    status: str
    file_label: str
    relative_path: str | None = None
    path_hash: str
    content_hash: str | None = None
    byte_hash: str | None = None
    language_hint: str | None = None
    file_type_id: str | None = None
    file_type_label: str | None = None
    category: str | None = None
    adapter: str | None = None
    language_id: str | None = None
    encoding: str | None = None
    line_ending: str | None = None
    line_count: int = 0
    byte_count: int = 0
    parse_status: str | None = None
    parse_summary: dict[str, object] = Field(default_factory=dict)
    risk_flags: CodingFileRiskFlags = Field(default_factory=CodingFileRiskFlags)
    capabilities: CodingFileCapabilityFlags = Field(default_factory=CodingFileCapabilityFlags)
    redactions: list[str] = Field(default_factory=list)
    source_contents_included: bool = False
    content_preview: str | None = None
    bytes_returned: int = 0
    lines_returned: int = 0
    truncated: bool = False
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    secret_scan_findings: list[str] = Field(default_factory=list)
    boundaries: CodingBoundaryFlags = Field(default_factory=CodingBoundaryFlags)


__all__ = (
    "CodingFileReadPreviewRequest",
    "CodingFileReadPreviewResult",
)
