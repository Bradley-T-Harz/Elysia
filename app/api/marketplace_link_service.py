"""Sealed local Marketplace link metadata service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.api import account_service
from app.api.schemas.marketplace import (
    ALLOWED_MARKETPLACE_SYNC_FIELDS,
    MarketplaceLinkRequest,
    MarketplaceLinkStatus,
    MarketplaceProfileSyncRecord,
    MarketplaceProfileSyncRecordRequest,
)
from app.install.paths import resolve_elysia_paths

IDENTITY_ROOT = resolve_elysia_paths().identity_dir
MARKETPLACE_LINK_PATH = IDENTITY_ROOT / "marketplace_link.json"


class MarketplaceLinkServiceError(RuntimeError):
    """Base exception for Marketplace link failures."""


class MarketplaceLinkAuthError(MarketplaceLinkServiceError):
    """Raised when local account authentication is required."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_private_file(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_sync_fields(fields: list[str] | None) -> list[str]:
    allowed = set(ALLOWED_MARKETPLACE_SYNC_FIELDS)
    normalized: list[str] = []
    for field in fields or []:
        key = str(field).strip()
        if key in allowed and key not in normalized:
            normalized.append(key)
    return normalized


@dataclass(frozen=True)
class MarketplaceLinkPaths:
    identity_root: Path = IDENTITY_ROOT
    link_path: Path = MARKETPLACE_LINK_PATH


class MarketplaceLinkStore:
    def __init__(
        self,
        paths: MarketplaceLinkPaths | None = None,
        account_store: account_service.AccountStore | None = None,
    ) -> None:
        self.paths = paths
        self.account_store = account_store or account_service.AccountStore()

    def _require_local_auth(self) -> str:
        state = self.account_store.state()
        if not state.is_authenticated:
            raise MarketplaceLinkAuthError("A valid local Elysia account session is required.")
        if not state.active_user_id:
            raise MarketplaceLinkAuthError("The authenticated local profile has no stable user ID.")
        return str(state.active_user_id)

    def _paths_for(self, local_user_id: str) -> MarketplaceLinkPaths:
        if self.paths is not None:
            return self.paths
        identity_root = resolve_elysia_paths().identity_dir / "marketplace_connectors"
        return MarketplaceLinkPaths(
            identity_root=identity_root,
            link_path=identity_root / f"{local_user_id}.json",
        )

    def _read_raw(self, paths: MarketplaceLinkPaths) -> dict[str, Any] | None:
        try:
            data = json.loads(paths.link_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def status(self) -> MarketplaceLinkStatus:
        local_user_id = self._require_local_auth()
        data = self._read_raw(self._paths_for(local_user_id))
        if data is None:
            return MarketplaceLinkStatus()
        return MarketplaceLinkStatus(
            linked=True,
            marketplace_user_id=_normalize_optional_text(data.get("marketplace_user_id")),
            marketplace_email=_normalize_optional_text(data.get("marketplace_email")),
            marketplace_username=_normalize_optional_text(data.get("marketplace_username")),
            linked_at_utc=_normalize_optional_text(data.get("linked_at_utc")),
            last_sync_at_utc=_normalize_optional_text(data.get("last_sync_at_utc")),
            sync_enabled_fields=_normalize_sync_fields(data.get("sync_enabled_fields")),
        )

    def link(self, request: MarketplaceLinkRequest) -> MarketplaceLinkStatus:
        local_user_id = self._require_local_auth()
        paths = self._paths_for(local_user_id)
        paths.identity_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        existing = self._read_raw(paths) or {}
        now = _utc_now()
        payload = {
            "marketplace_user_id": request.marketplace_user_id.strip(),
            "marketplace_email": _normalize_optional_text(request.marketplace_email),
            "marketplace_username": _normalize_optional_text(request.marketplace_username),
            "linked_at_utc": existing.get("linked_at_utc") or now,
            "last_sync_at_utc": existing.get("last_sync_at_utc"),
            "sync_enabled_fields": _normalize_sync_fields(request.sync_enabled_fields),
            "local_user_id": local_user_id,
            "connector_scope": "marketplace_only",
            "identity_federated": False,
        }
        paths.link_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _ensure_private_file(paths.link_path)
        return self.status()

    def unlink(self) -> MarketplaceLinkStatus:
        local_user_id = self._require_local_auth()
        paths = self._paths_for(local_user_id)
        try:
            paths.link_path.unlink()
        except FileNotFoundError:
            pass
        return MarketplaceLinkStatus()

    def record_profile_sync(
        self,
        request: MarketplaceProfileSyncRecordRequest,
    ) -> MarketplaceProfileSyncRecord:
        local_user_id = self._require_local_auth()
        paths = self._paths_for(local_user_id)
        data = self._read_raw(paths)
        if data is None:
            raise MarketplaceLinkServiceError("Marketplace sync records require an existing local Marketplace link.")
        now = _utc_now()
        fields_synced = _normalize_sync_fields(request.fields_synced)
        data["last_sync_at_utc"] = now
        data["sync_enabled_fields"] = fields_synced
        paths.identity_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        paths.link_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _ensure_private_file(paths.link_path)
        return MarketplaceProfileSyncRecord(
            synced_at_utc=now,
            direction=_normalize_optional_text(request.direction) or "local_to_marketplace",
            fields_synced=fields_synced,
        )


def _default_store() -> MarketplaceLinkStore:
    return MarketplaceLinkStore()


def get_marketplace_link_status() -> MarketplaceLinkStatus:
    return _default_store().status()


def link_marketplace_account(request: MarketplaceLinkRequest) -> MarketplaceLinkStatus:
    return _default_store().link(request)


def unlink_marketplace_account() -> MarketplaceLinkStatus:
    return _default_store().unlink()


def record_marketplace_profile_sync(
    request: MarketplaceProfileSyncRecordRequest,
) -> MarketplaceProfileSyncRecord:
    return _default_store().record_profile_sync(request)


__all__ = (
    "MarketplaceLinkAuthError",
    "MarketplaceLinkPaths",
    "MarketplaceLinkServiceError",
    "MarketplaceLinkStore",
    "get_marketplace_link_status",
    "link_marketplace_account",
    "record_marketplace_profile_sync",
    "unlink_marketplace_account",
)
