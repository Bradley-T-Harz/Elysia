"""Content-free Part 2D cognition and compute status contracts."""

from typing import Any

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class CognitionStatusData(ElysiaSchemaModel):
    governor_contract: str
    reasoning_gears: list[str]
    autonomy_levels: dict[int, str]
    effective_controls: dict[str, Any] = Field(default_factory=dict)
    model_registry: dict[str, Any] = Field(default_factory=dict)
    compute: dict[str, Any] = Field(default_factory=dict)
    active_gpu_leases: list[dict[str, Any]] = Field(default_factory=list)
    emergency: dict[str, Any] = Field(default_factory=dict)
    private_content_included: bool = False


__all__ = ("CognitionStatusData",)
