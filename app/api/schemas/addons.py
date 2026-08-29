"""Typed contracts for governed local add-on and review foundations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


AddonTransitionAction = Literal["install_disabled", "enable_limited", "disable", "revoke", "remove"]
AddonLifecycleState = Literal[
    "draft",
    "packaged",
    "submitted",
    "pending_review",
    "approved",
    "rejected",
    "installed_disabled",
    "enabled_limited",
    "disabled",
    "revoked",
    "removed",
]


class AddonPackagePathRequest(ElysiaSchemaModel):
    package_path: str = Field(..., min_length=1, max_length=4096)
    source: str = Field(default="manual_file", max_length=80)
    plan_id: str | None = Field(default=None, max_length=80)
    plan_hash: str | None = Field(default=None, min_length=64, max_length=64)
    approval_id: str | None = Field(default=None, max_length=80)
    approval_token: str | None = Field(default=None, max_length=200)


class AddonStatusChangeRequest(ElysiaSchemaModel):
    addon_id: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    version: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]+$")
    reason: str | None = Field(default=None, max_length=500)
    plan_id: str | None = Field(default=None, max_length=80)
    plan_hash: str | None = Field(default=None, min_length=64, max_length=64)
    approval_id: str | None = Field(default=None, max_length=80)
    approval_token: str | None = Field(default=None, max_length=200)


class AddonTransitionPlanRequest(ElysiaSchemaModel):
    action: AddonTransitionAction
    package_path: str | None = Field(default=None, max_length=4096)
    addon_id: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    version: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]+$")
    expected_state: AddonLifecycleState | None = None
    expected_package_hash: str | None = Field(default=None, min_length=64, max_length=64)
    approved_permissions: list[str] = Field(default_factory=list, max_length=64)
    actor: str = Field(default="local_operator", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._ -]+$")
    reason: str | None = Field(default=None, max_length=500)
    source: str = Field(default="manual_file", max_length=80)


class AddonTransitionApprovalRequest(ElysiaSchemaModel):
    plan_id: str = Field(..., min_length=1, max_length=80)
    plan_hash: str = Field(..., min_length=64, max_length=64)
    operator_confirmed: bool = False
    actor: str = Field(default="local_operator", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._ -]+$")
    confirmation: str = Field(default="", max_length=160)


class AddonTransitionApplyRequest(ElysiaSchemaModel):
    plan_id: str = Field(..., min_length=1, max_length=80)
    plan_hash: str = Field(..., min_length=64, max_length=64)
    approval_id: str = Field(..., min_length=1, max_length=80)
    approval_token: str = Field(..., min_length=1, max_length=200)


class AddonMarketplaceIntentRequest(ElysiaSchemaModel):
    deep_link_url: str | None = Field(default=None, max_length=1024)
    intent_id: str | None = Field(default=None, max_length=128)
    nonce: str | None = Field(default=None, max_length=160)


class AddonAuditRequest(ElysiaSchemaModel):
    limit: int = Field(default=100, ge=1, le=500)


class AddonSourceInventoryItem(ElysiaSchemaModel):
    relative_path: str = Field(..., min_length=1, max_length=512)
    size_bytes: int = Field(default=0, ge=0, le=25 * 1024 * 1024)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    kind: Literal["text", "source", "binary", "archive", "document", "unknown"] = "unknown"


class DeveloperAddonPackagePlanRequest(ElysiaSchemaModel):
    source_kind: Literal["local_project", "local_folder", "local_repository", "source_bundle", "external_tool_output"]
    manifest: dict[str, Any]
    files: list[AddonSourceInventoryItem] = Field(default_factory=list, max_length=500)
    output_name: str | None = Field(default=None, max_length=180)
    actor: str = Field(default="local_developer", max_length=80, pattern=r"^[A-Za-z0-9._ -]+$")


class MarketplaceSubmissionPreviewRequest(ElysiaSchemaModel):
    addon_id: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    version: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]+$")
    package_hash: str = Field(..., min_length=64, max_length=64)
    source_kind: Literal["elysia_addon", "source_bundle", "browser_folder", "browser_repository", "git_url_metadata"]
    publisher_identity: str = Field(..., min_length=1, max_length=120, pattern=r"^[A-Za-z0-9@._ +/()-]+$")
    file_count: int = Field(default=0, ge=0, le=500)
    total_size_bytes: int = Field(default=0, ge=0, le=25 * 1024 * 1024)
    dependency_count: int = Field(default=0, ge=0, le=500)
    requested_permissions: list[str] = Field(default_factory=list, max_length=64)
    static_scan_passed: bool = False
    privacy_notice_acknowledged: bool = False
    actor: str = Field(default="marketplace_submitter", max_length=80, pattern=r"^[A-Za-z0-9._ -]+$")


class MarketplaceReviewPreviewRequest(ElysiaSchemaModel):
    addon_id: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    version: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]+$")
    package_hash: str = Field(..., min_length=64, max_length=64)
    publisher_identity: str = Field(..., min_length=1, max_length=120, pattern=r"^[A-Za-z0-9@._ +/()-]+$")
    requested_permissions: list[str] = Field(default_factory=list, max_length=64)
    dependency_count: int = Field(default=0, ge=0, le=500)
    reviewer: str = Field(..., min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._ -]+$")
    decision: Literal["approved", "rejected"]
    permission_review_complete: bool = False
    compatibility_review_complete: bool = False
    dependency_review_complete: bool = False
    license_provenance_review_complete: bool = False
    static_scan_passed: bool = False
    known_risks: list[str] = Field(default_factory=list, max_length=50)
    sandbox_result: Literal["not_performed", "passed", "blocked", "failed"] = "not_performed"
    test_environment_label: str = Field(default="not_recorded", max_length=120)


__all__ = (
    "AddonAuditRequest",
    "AddonLifecycleState",
    "AddonMarketplaceIntentRequest",
    "AddonPackagePathRequest",
    "AddonSourceInventoryItem",
    "AddonStatusChangeRequest",
    "AddonTransitionAction",
    "AddonTransitionApplyRequest",
    "AddonTransitionApprovalRequest",
    "AddonTransitionPlanRequest",
    "DeveloperAddonPackagePlanRequest",
    "MarketplaceReviewPreviewRequest",
    "MarketplaceSubmissionPreviewRequest",
)
