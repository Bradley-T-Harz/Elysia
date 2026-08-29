"""Typed contracts for exact Governance plan, apply, and restore requests."""

from __future__ import annotations

from enum import Enum
import math
import re

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator

from app.api.schemas.common import ElysiaSchemaModel
from app.governance.governance_control_registry import (
    GovernanceMutationClassification,
    GovernanceMutationRisk,
)


GovernanceScalar = StrictBool | StrictInt | StrictFloat | StrictStr | None
_CONTROL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,159}$")
_RECORD_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _validate_pattern(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"{label} has an invalid format.")
    return value


class GovernanceMutationAction(str, Enum):
    PLAN = "plan"
    APPLY = "apply"
    RESTORE = "restore"


class GovernanceMutationOutcome(str, Enum):
    PLANNED = "planned"
    APPLIED = "applied"
    RESTORED = "restored"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    STALE = "stale"
    TAMPERED = "tampered"


class GovernanceMutationReceipt(ElysiaSchemaModel):
    request_id: str
    operation_id: str
    action: GovernanceMutationAction
    outcome: GovernanceMutationOutcome
    control_id: str
    classification: GovernanceMutationClassification
    risk: GovernanceMutationRisk
    recorded_at_utc: str
    config_hash_before: str | None = None
    config_hash_after: str | None = None
    plan_hash: str | None = None
    approval_id: str | None = None
    reason_code: str | None = None
    sanitized: bool = True
    raw_values_logged: bool = False
    raw_paths_logged: bool = False


class GovernanceChangePlanRequest(ElysiaSchemaModel):
    control_id: str = Field(..., min_length=1, max_length=160)
    proposed_value: GovernanceScalar = None
    expected_config_hash: str = Field(..., min_length=64, max_length=64)
    reason: str | None = Field(default=None, max_length=500)
    ui_surface: str = Field(default="governance_room", min_length=1, max_length=80)

    @field_validator("control_id")
    @classmethod
    def validate_control_id(cls, value: str) -> str:
        return _validate_pattern(value, _CONTROL_ID_PATTERN, "control_id")

    @field_validator("expected_config_hash")
    @classmethod
    def validate_config_hash(cls, value: str) -> str:
        return _validate_pattern(value, _SHA256_PATTERN, "expected_config_hash")

    @field_validator("proposed_value")
    @classmethod
    def validate_proposed_value(cls, value: GovernanceScalar) -> GovernanceScalar:
        if isinstance(value, str) and len(value) > 240:
            raise ValueError("proposed_value string is too long.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("proposed_value number must be finite.")
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 1_000_000_000:
            raise ValueError("proposed_value integer is outside the bounded contract range.")
        return value


class GovernanceChangePlan(ElysiaSchemaModel):
    plan_id: str
    control_id: str
    classification: GovernanceMutationClassification
    risk: GovernanceMutationRisk
    mutation_allowed: bool
    approval_required: bool
    current_value: GovernanceScalar = None
    proposed_value: GovernanceScalar = None
    config_hash: str
    plan_hash: str
    expires_at_utc: str
    approval_request_id: str | None = None
    consequences: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    receipt: GovernanceMutationReceipt


class GovernanceChangeApplyRequest(ElysiaSchemaModel):
    plan_id: str = Field(..., min_length=1, max_length=100)
    plan_hash: str = Field(..., min_length=64, max_length=64)
    expected_config_hash: str = Field(..., min_length=64, max_length=64)
    approval_id: str | None = Field(default=None, max_length=100)
    approval_token: str | None = Field(default=None, max_length=200)
    confirmed: bool = False

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        return _validate_pattern(value, _RECORD_ID_PATTERN, "plan_id")

    @field_validator("plan_hash", "expected_config_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        return _validate_pattern(value, _SHA256_PATTERN, "hash")


class GovernanceChangeApplyResult(ElysiaSchemaModel):
    applied: bool
    control_id: str
    config_hash_before: str
    config_hash_after: str
    restore_id: str | None = None
    restore_plan_hash: str | None = None
    restore_approval_request_id: str | None = None
    receipt: GovernanceMutationReceipt


class GovernanceRestoreRequest(ElysiaSchemaModel):
    restore_id: str = Field(..., min_length=1, max_length=100)
    restore_plan_hash: str = Field(..., min_length=64, max_length=64)
    expected_config_hash: str = Field(..., min_length=64, max_length=64)
    approval_id: str | None = Field(default=None, max_length=100)
    approval_token: str | None = Field(default=None, max_length=200)
    confirmed: bool = False

    @field_validator("restore_id")
    @classmethod
    def validate_restore_id(cls, value: str) -> str:
        return _validate_pattern(value, _RECORD_ID_PATTERN, "restore_id")

    @field_validator("restore_plan_hash", "expected_config_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        return _validate_pattern(value, _SHA256_PATTERN, "hash")


class GovernanceRestoreResult(ElysiaSchemaModel):
    restored: bool
    control_id: str
    config_hash_before: str
    config_hash_after: str
    receipt: GovernanceMutationReceipt


__all__ = (
    "GovernanceChangeApplyRequest",
    "GovernanceChangeApplyResult",
    "GovernanceChangePlan",
    "GovernanceChangePlanRequest",
    "GovernanceMutationAction",
    "GovernanceMutationOutcome",
    "GovernanceMutationReceipt",
    "GovernanceRestoreRequest",
    "GovernanceRestoreResult",
    "GovernanceScalar",
)
