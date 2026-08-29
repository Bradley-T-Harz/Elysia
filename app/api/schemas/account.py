"""Account and profile schemas for the local identity gate."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class AccountStatus(str, Enum):
    NEEDS_CREATION = "needs_creation"
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"


class LocalAccountRole(str, Enum):
    """Installation-governance role; never a content-ownership grant."""

    INSTALLATION_OWNER = "installation_owner"
    ADMIN = "admin"
    USER = "user"


class AccountStateData(ElysiaSchemaModel):
    has_user: bool = False
    is_authenticated: bool = False
    requires_user_creation: bool = True
    requires_login: bool = False
    active_username: str | None = None
    active_user_id: str | None = None
    active_role: LocalAccountRole | None = None
    active_profile_managed: bool = False
    supervision_notice: str | None = None
    account_count: int = Field(default=0, ge=0)
    multiple_accounts_available: bool = False
    account_status: AccountStatus = AccountStatus.NEEDS_CREATION


class AccountColorOption(ElysiaSchemaModel):
    id: str
    label: str
    hex: str


class ProfilePhotoAsset(ElysiaSchemaModel):
    asset_id: str
    mime_type: str
    extension: str
    byte_size: int = Field(default=0, ge=0)
    sha256: str
    preview_available: bool = True


class AccountCreateRequest(ElysiaSchemaModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=12, max_length=1024)
    interests: str = ""
    bio: str = ""
    birthdate: str | None = None
    emails: list[str] | str = Field(default_factory=list)
    phone_number: str | None = None
    social_media: list[str] | str = Field(default_factory=list)
    github: str | None = None
    city_state: str | None = None
    profile_color_id: str = "meteor_rose"
    profile_photo_asset_id: str | None = None
    requested_role: LocalAccountRole = LocalAccountRole.USER
    managed_profile: bool = False


class AccountLoginRequest(ElysiaSchemaModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=1024)


class AccountProfilePrivate(ElysiaSchemaModel):
    username: str
    interests: str = ""
    bio: str = ""
    birthdate: str | None = None
    emails: list[str] = Field(default_factory=list)
    phone_number: str | None = None
    social_media: list[str] = Field(default_factory=list)
    github: str | None = None
    city_state: str | None = None
    profile_color_id: str = "meteor_rose"
    profile_photo_asset_id: str | None = None
    profile_photo_available: bool = False
    profile_photo: ProfilePhotoAsset | None = None


class AccountProfileUpdateRequest(ElysiaSchemaModel):
    username: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=12, max_length=1024)
    current_password: str | None = Field(default=None, min_length=1, max_length=1024)
    interests: str | None = None
    bio: str | None = None
    birthdate: str | None = None
    emails: list[str] | str | None = None
    phone_number: str | None = None
    social_media: list[str] | str | None = None
    github: str | None = None
    city_state: str | None = None
    profile_color_id: str | None = None
    profile_photo_asset_id: str | None = None


class AccountDeleteRequest(ElysiaSchemaModel):
    """Fresh-authenticated request to remove one local Identity authority."""

    current_password: str = Field(..., min_length=1, max_length=1024)
    confirmation_username: str = Field(..., min_length=1, max_length=120)


class AccountProfileArchiveExportRequest(ElysiaSchemaModel):
    current_password: str = Field(..., min_length=1, max_length=1024)
    recovery_material: str = Field(..., min_length=12, max_length=1024)


class AccountProfileArchiveRestoreRequest(ElysiaSchemaModel):
    current_password: str = Field(..., min_length=1, max_length=1024)
    recovery_material: str = Field(..., min_length=12, max_length=1024)
    archive_base64: str = Field(..., min_length=1, max_length=24_000_000)
    operator_confirmed: bool


class AccountDeletionInventory(ElysiaSchemaModel):
    memory_records: int = Field(default=0, ge=0)
    shared_spaces: int = Field(default=0, ge=0)
    project_records: int = Field(default=0, ge=0)
    conversation_records: int = Field(default=0, ge=0)
    profile_photo_assets: int = Field(default=0, ge=0)
    blocking_owned_records: int = Field(default=0, ge=0)


class AccountDeleteResult(ElysiaSchemaModel):
    deleted: bool = True
    state: AccountStateData
    deletion_inventory: AccountDeletionInventory
    sessions_removed: int = Field(default=0, ge=0)
    profile_assets_removed: int = Field(default=0, ge=0)


class ElysiaVisibleProfile(ElysiaSchemaModel):
    name_or_username: str
    interests: str = ""
    bio: str = ""
    profile_photo_asset_id: str | None = None
    profile_photo_available: bool = False


class AccountCreateResult(ElysiaSchemaModel):
    state: AccountStateData
    profile: AccountProfilePrivate


class AccountLoginResult(ElysiaSchemaModel):
    state: AccountStateData


class AccountLogoutResult(ElysiaSchemaModel):
    state: AccountStateData
    session_revoked: bool = True


class AccountProfileUpdateResult(ElysiaSchemaModel):
    profile: AccountProfilePrivate
    password_changed: bool = False


class ProfilePhotoSelectRequest(ElysiaSchemaModel):
    source_path: str = Field(..., min_length=1)


class ProfilePhotoDeleteResult(ElysiaSchemaModel):
    deleted: bool
    profile_photo_asset_id: str | None = None


class AccountPrivacyPolicyView(ElysiaSchemaModel):
    elysia_visible_fields: list[str] = Field(default_factory=list)
    sealed_fields: list[str] = Field(default_factory=list)
    runtime_private_access: bool = False
    tools_private_access: bool = False
    workers_private_access: bool = False
    memory_import_private_profile: bool = False
    prudence_note: str


__all__ = (
    "AccountColorOption",
    "AccountCreateRequest",
    "AccountCreateResult",
    "AccountDeleteRequest",
    "AccountDeleteResult",
    "AccountDeletionInventory",
    "AccountLoginRequest",
    "AccountLoginResult",
    "AccountLogoutResult",
    "AccountPrivacyPolicyView",
    "AccountProfileArchiveExportRequest",
    "AccountProfileArchiveRestoreRequest",
    "AccountProfilePrivate",
    "AccountProfileUpdateRequest",
    "AccountProfileUpdateResult",
    "AccountStateData",
    "AccountStatus",
    "ElysiaVisibleProfile",
    "ProfilePhotoAsset",
    "ProfilePhotoDeleteResult",
    "ProfilePhotoSelectRequest",
    "LocalAccountRole",
)
