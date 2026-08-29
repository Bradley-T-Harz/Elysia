"""Marketplace link schemas for local account linking."""

from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


ALLOWED_MARKETPLACE_SYNC_FIELDS: tuple[str, ...] = ()


class MarketplaceLinkRequest(ElysiaSchemaModel):
    marketplace_user_id: str = Field(..., min_length=1, max_length=240)
    marketplace_email: str | None = Field(default=None, max_length=320)
    marketplace_username: str | None = Field(default=None, max_length=160)
    sync_enabled_fields: list[str] = Field(default_factory=list)


class MarketplaceLinkStatus(ElysiaSchemaModel):
    linked: bool = False
    marketplace_user_id: str | None = None
    marketplace_email: str | None = None
    marketplace_username: str | None = None
    linked_at_utc: str | None = None
    last_sync_at_utc: str | None = None
    sync_enabled_fields: list[str] = Field(default_factory=list)
    allowed_sync_fields: list[str] = Field(default_factory=lambda: list(ALLOWED_MARKETPLACE_SYNC_FIELDS))
    password_stored: bool = False
    token_stored: bool = False
    service_role_key_used: bool = False
    local_private_profile_shared: bool = False
    local_files_shared: bool = False
    memory_shared: bool = False
    request_traces_shared: bool = False
    dependency_inventory_shared: bool = False
    runtime_access_allowed: bool = False
    connector_scope: str = "marketplace_only"
    identity_federated: bool = False
    local_admin_granted_by_marketplace: bool = False
    marketplace_admin_granted_by_local: bool = False


class MarketplaceLinkResult(ElysiaSchemaModel):
    status: MarketplaceLinkStatus


class MarketplaceProfileSyncRecordRequest(ElysiaSchemaModel):
    direction: str = Field(default="local_to_marketplace", max_length=80)
    fields_synced: list[str] = Field(default_factory=list)


class MarketplaceProfileSyncRecord(ElysiaSchemaModel):
    recorded: bool = True
    synced_at_utc: str
    direction: str
    fields_synced: list[str] = Field(default_factory=list)
    raw_values_stored: bool = False
    marketplace_token_received: bool = False
    marketplace_password_received: bool = False
    local_private_fields_synced: bool = False


__all__ = (
    "ALLOWED_MARKETPLACE_SYNC_FIELDS",
    "MarketplaceLinkRequest",
    "MarketplaceLinkResult",
    "MarketplaceLinkStatus",
    "MarketplaceProfileSyncRecord",
    "MarketplaceProfileSyncRecordRequest",
)
