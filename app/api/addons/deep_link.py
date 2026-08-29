"""Untrusted elysia:// deep-link parser for Marketplace install invitations."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class MarketplaceInstallIntent:
    intent_id: str
    nonce: str
    source_url: str

    def to_payload(self) -> dict[str, str]:
        return {"intent_id": self.intent_id, "nonce": self.nonce, "source_url": self.source_url}


def parse_marketplace_install_link(raw_url: str) -> tuple[MarketplaceInstallIntent | None, list[str]]:
    errors: list[str] = []
    parsed = urlparse(raw_url)
    if parsed.scheme != "elysia":
        errors.append("Deep link must use elysia:// scheme.")
    if parsed.netloc != "marketplace" or parsed.path != "/install":
        errors.append("Deep link must target elysia://marketplace/install.")
    params = parse_qs(parsed.query, keep_blank_values=False)
    intent_id = params.get("intent_id", [""])[0].strip()
    nonce = params.get("nonce", [""])[0].strip()
    if not intent_id:
        errors.append("Deep link is missing intent_id.")
    if not nonce:
        errors.append("Deep link is missing nonce.")
    if len(intent_id) > 128 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for ch in intent_id):
        errors.append("Deep link intent_id has invalid characters.")
    if len(nonce) > 160 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-." for ch in nonce):
        errors.append("Deep link nonce has invalid characters.")
    if errors:
        return None, errors
    return MarketplaceInstallIntent(intent_id=intent_id, nonce=nonce, source_url=raw_url), []


__all__ = ("MarketplaceInstallIntent", "parse_marketplace_install_link")

