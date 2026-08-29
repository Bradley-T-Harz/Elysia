"""Schemas for local, metadata-only audio/video stewardship."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CodingMediaPathRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    file_path: str
    approval_granted: bool = False
    approval_reason: str | None = None


class CodingMediaInspectResult(ElysiaSchemaModel):
    status: str
    file_label: str
    relative_path: str | None = None
    path_hash: str
    content_hash: str | None = None
    blocked_reason: str | None = None
    descriptor: dict[str, Any] = Field(default_factory=dict)
    size_bytes: int = 0
    media_family: str = "unknown"
    container: str | None = None
    duration_seconds: float | None = None
    bitrate_bps: int | None = None
    stream_count: int = 0
    audio: dict[str, Any] = Field(default_factory=dict)
    video: dict[str, Any] = Field(default_factory=dict)
    privacy_flags: dict[str, bool] = Field(default_factory=dict)
    safety_flags: dict[str, bool] = Field(default_factory=dict)
    dependencies: dict[str, Any] = Field(default_factory=dict)
    thumbnail_status: str = "not_requested"
    thumbnail_data_url: str | None = None
    thumbnail_path: str | None = None
    operation_id: str | None = None
    request_id: str | None = None
    audit_written: bool = False
    warnings: list[str] = Field(default_factory=list)


__all__ = ("CodingMediaInspectResult", "CodingMediaPathRequest")
