"""
Shared schema vocabulary for the Elysia local API bridge.

This module exists to keep Stage 3 Python-side schema language aligned with
the Stage 2 YAML contracts. It should centralize cross-schema state words and
provide a strict base model for downstream schema modules.

This file should stay narrow:
- shared cross-schema enums
- shared base schema model
- small serialization helper

It should not contain:
- service logic
- runtime logic
- governance logic
- route logic
- endpoint-specific business rules
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - compatibility fallback
    ConfigDict = None  # type: ignore[assignment]


class ElysiaSchemaModel(BaseModel):
    """
    Strict base model for local API schema modules.

    Goals:
    - reject unexpected fields by default
    - normalize string inputs consistently
    - allow clean dict serialization for route/service responses
    - keep enum output aligned with the Stage 2 contract strings
    """

    if ConfigDict is not None:
        model_config = ConfigDict(
            extra="forbid",
            populate_by_name=True,
            validate_assignment=True,
            use_enum_values=True,
            str_strip_whitespace=True,
        )
    else:  # pragma: no cover - compatibility fallback for older Pydantic
        class Config:
            extra = "forbid"
            allow_population_by_field_name = True
            validate_assignment = True
            use_enum_values = True
            anystr_strip_whitespace = True

    def to_payload(self, *, exclude_none: bool = True) -> dict[str, Any]:
        """
        Return a plain dictionary payload suitable for API responses.

        Uses model_dump() when available (Pydantic v2) and falls back to dict()
        for older compatibility.
        """
        if hasattr(self, "model_dump"):
            return self.model_dump(exclude_none=exclude_none)

        return self.dict(exclude_none=exclude_none)


class EnvelopeStatus(str, Enum):
    """
    Canonical response-envelope request outcome state.

    Meanings:
    - ok: the API request succeeded
    - blocked: the API request was denied by policy/boundary posture
    - error: the API request failed unexpectedly
    - degraded: the API request succeeded, but only partially or with reduced quality
    - unavailable: the required path/service should exist, but is currently unreachable
    """

    OK = "ok"
    BLOCKED = "blocked"
    ERROR = "error"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class CapabilityState(str, Enum):
    """
    Canonical capability-truth state shared across the bridge.

    Locked meanings:
    - live: actually available now
    - inactive: intentionally not active
    - planned: designed / not yet live
    - unknown: not yet confirmed
    - unavailable: should exist but currently unreachable / unusable
    - degraded: present but reduced / impaired
    """

    LIVE = "live"
    INACTIVE = "inactive"
    PLANNED = "planned"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class LocalityState(str, Enum):
    """
    Canonical locality state shared across the bridge.

    Meanings:
    - local: request/capability/path stayed local
    - crossed_boundary: request/capability/path crossed an external boundary
    - unknown: locality truth has not yet been confirmed
    """

    LOCAL = "local"
    CROSSED_BOUNDARY = "crossed_boundary"
    UNKNOWN = "unknown"


class ApprovalState(str, Enum):
    """
    Canonical approval posture state shared across the bridge.

    Meanings:
    - not_needed: no approval is required for the relevant request/path
    - needed: approval is currently required
    - approved: approval has been granted
    - denied: approval has been refused
    - unknown: approval posture has not yet been confirmed
    """

    NOT_NEEDED = "not_needed"
    NEEDED = "needed"
    APPROVED = "approved"
    DENIED = "denied"
    UNKNOWN = "unknown"


__all__ = (
    "ApprovalState",
    "CapabilityState",
    "ElysiaSchemaModel",
    "EnvelopeStatus",
    "LocalityState",
)
