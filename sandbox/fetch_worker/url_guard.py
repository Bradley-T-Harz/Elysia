"""URL guard for bounded public page fetch requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from ipaddress import ip_address
from socket import getaddrinfo
from typing import Any
from urllib.parse import urlparse, urlunparse

from .config import FetchWorkerConfig


@dataclass
class FetchUrlGuardResult:
    allowed: bool
    sanitized_url: str = ""
    url_hash: str = ""
    approval_required: bool = False
    refusal_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resolved_public_ips: list[str] = field(default_factory=list)


def _is_private_ip(value: str) -> bool:
    try:
        address = ip_address(value)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def _resolved_ips(host: str) -> list[str]:
    try:
        infos = getaddrinfo(host, None)
    except OSError:
        return []
    return sorted({str(info[4][0]) for info in infos if info[4]})


def sanitize_fetch_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            parsed.path or "/",
            "",
            parsed.query,
            "",
        )
    )


def guard_fetch_url(
    url: str,
    *,
    config: FetchWorkerConfig,
    approval_token: str | None = None,
    approved_by_user: bool = False,
) -> FetchUrlGuardResult:
    # Compatibility arguments are deliberately ignored. Ordinary harmless
    # public GETs do not require per-request approval; sensitive or
    # authenticated egress is exactly authorized by the ResearchPort before
    # constructing a worker request.
    del approval_token, approved_by_user
    sanitized = sanitize_fetch_url(url)
    parsed = urlparse(sanitized)
    reasons: list[str] = []
    warnings: list[str] = []

    if parsed.scheme not in set(config.allowed_schemes):
        reasons.append("URL scheme is not allowed.")
    if parsed.scheme in set(config.blocked_schemes):
        reasons.append("URL scheme is blocked.")
    if parsed.username or parsed.password:
        reasons.append("Credentials in URLs are blocked.")

    host = (parsed.hostname or "").lower()
    resolved_ips: list[str] = []
    if not host:
        reasons.append("URL host is required.")
    if host in {item.lower() for item in config.blocked_hosts}:
        reasons.append("Loopback or blocked host is not fetchable.")
    if host and _is_private_ip(host):
        reasons.append("Private, local, or reserved IP targets are blocked.")
    if host and not _is_private_ip(host):
        resolved_ips = _resolved_ips(host)
        if not resolved_ips:
            reasons.append("Public host DNS resolution failed.")
        if any(_is_private_ip(candidate) for candidate in resolved_ips):
            reasons.append("Host resolves to a private/local IP target.")

    if reasons:
        return FetchUrlGuardResult(
            allowed=False,
            sanitized_url=sanitized,
            url_hash=sha256(sanitized.encode("utf-8")).hexdigest(),
            refusal_reasons=reasons,
            warnings=warnings,
            resolved_public_ips=[],
        )

    return FetchUrlGuardResult(
        allowed=True,
        sanitized_url=sanitized,
        url_hash=sha256(sanitized.encode("utf-8")).hexdigest(),
        warnings=warnings,
        resolved_public_ips=resolved_ips,
    )


__all__ = ("FetchUrlGuardResult", "guard_fetch_url", "sanitize_fetch_url")
