"""Bounded HTTP(S) client for one approved public page fetch."""

from __future__ import annotations

from html import unescape
from http.client import HTTPConnection, HTTPSConnection
from ipaddress import ip_address
import gzip
import re
import socket
import ssl
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urljoin, urlparse
import zlib


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, target_ip: str, server_hostname: str, port: int, timeout: int):
        super().__init__(server_hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self._target_ip = target_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._target_ip, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def _public_ip(value: str) -> bool:
    try:
        address = ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def _pinned_open(
    request: Request,
    *,
    timeout_seconds: int,
    allowed_public_ips: list[str],
):
    parsed = urlparse(request.full_url)
    hostname = parsed.hostname or ""
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise URLError("Only public HTTP(S) URLs are accepted.")
    verified_ips = [candidate for candidate in allowed_public_ips if _public_ip(candidate)]
    if not verified_ips:
        infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        resolved = sorted({str(info[4][0]) for info in infos if info[4]})
        if not resolved or any(not _public_ip(candidate) for candidate in resolved):
            raise URLError("The approved host did not resolve exclusively to public addresses.")
        verified_ips = resolved
    target_ip = verified_ips[0]
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    host_header = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    connection: HTTPConnection
    if parsed.scheme == "https":
        connection = _PinnedHTTPSConnection(target_ip, hostname, port, timeout_seconds)
    else:
        connection = HTTPConnection(target_ip, port=port, timeout=timeout_seconds)
    connection.request(
        "GET",
        path,
        headers={**dict(request.header_items()), "Host": host_header},
    )
    return connection, connection.getresponse()


def _strip_markup(text: str) -> str:
    without_script = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_script)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def _extract_title(text: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    if not match:
        return ""
    return _strip_markup(match.group(1))[:240]


_ALLOWED_MIME_TYPES = {
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/json",
    "application/xml",
    "text/xml",
    "application/rss+xml",
    "application/atom+xml",
}


def _read_bounded(response: Any, limit: int, cancel_check: Callable[[], bool] | None) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        if cancel_check is not None and cancel_check():
            raise InterruptedError("Public page fetch was cancelled.")
        chunk = response.read(min(16384, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    payload = b"".join(chunks)
    return payload[:limit], len(payload) > limit


def _decompress_bounded(raw: bytes, encoding: str, limit: int) -> bytes:
    normalized = str(encoding or "identity").split(",", 1)[0].strip().casefold()
    if normalized in {"", "identity"}:
        if len(raw) > limit:
            raise ValueError("Response exceeded the decompressed byte limit.")
        return raw
    if normalized == "gzip":
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif normalized == "deflate":
        decompressor = zlib.decompressobj()
    else:
        raise ValueError("Unsupported content encoding from public page.")
    output = decompressor.decompress(raw, limit + 1)
    if len(output) > limit or decompressor.unconsumed_tail:
        raise ValueError("Compressed response exceeded the decompressed byte limit.")
    output += decompressor.flush(limit + 1 - len(output))
    if len(output) > limit:
        raise ValueError("Compressed response exceeded the decompressed byte limit.")
    return output


def fetch_public_page(
    *,
    url: str,
    timeout_seconds: int,
    max_response_bytes: int,
    max_snippet_chars: int,
    user_agent: str,
    follow_redirects: bool = False,
    opener: Any | None = None,
    allowed_public_ips: list[str] | None = None,
    max_decompressed_bytes: int | None = None,
    max_redirects: int = 3,
    redirect_validator: Callable[[str], Any] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    Fetch one approved URL and return bounded, sanitized page metadata.
    """
    current_url = url
    current_ips = list(allowed_public_ips or [])
    redirects = 0
    decompressed_limit = max(max_response_bytes, int(max_decompressed_bytes or max_response_bytes * 4))
    try:
        while True:
            if cancel_check is not None and cancel_check():
                raise InterruptedError("Public page fetch was cancelled.")
            request = Request(
                current_url,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "text/html,text/plain,application/xhtml+xml,application/json,application/xml;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                },
                method="GET",
            )
            connection = None
            if opener is not None:
                response = opener.open(request, timeout=timeout_seconds)
            else:
                connection, response = _pinned_open(
                    request,
                    timeout_seconds=timeout_seconds,
                    allowed_public_ips=current_ips,
                )
            try:
                status_code = int(getattr(response, "status", response.getcode()))
                content_type = str(response.headers.get("content-type", "")).lower()
                mime = content_type.split(";", 1)[0].strip()
                if 300 <= status_code < 400:
                    location = str(response.headers.get("location", "")).strip()
                    if not follow_redirects:
                        raise ValueError("Redirect refused by the bounded public fetch worker.")
                    if not location or redirects >= max(0, int(max_redirects)):
                        raise ValueError("Public page redirect limit was exceeded.")
                    target = urljoin(current_url, location)
                    current_scheme = urlparse(current_url).scheme.casefold()
                    target_scheme = urlparse(target).scheme.casefold()
                    if current_scheme == "https" and target_scheme != "https":
                        raise ValueError("HTTPS redirects may not downgrade to a different protocol.")
                    if redirect_validator is None:
                        raise ValueError("Redirect requires URL revalidation.")
                    guarded = redirect_validator(target)
                    if not getattr(guarded, "allowed", False):
                        raise ValueError("Redirect target failed public URL policy.")
                    current_url = str(getattr(guarded, "sanitized_url", target))
                    current_ips = list(getattr(guarded, "resolved_public_ips", []) or [])
                    redirects += 1
                    continue
                if mime not in _ALLOWED_MIME_TYPES:
                    raise ValueError(f"Public page MIME type is not allowed: {mime or 'missing'}")
                raw, truncated = _read_bounded(response, max_response_bytes, cancel_check)
                encoding = str(response.headers.get("content-encoding", ""))
                raw = _decompress_bounded(raw, encoding, decompressed_limit)
                break
            finally:
                response.close()
                if connection is not None:
                    connection.close()
    except HTTPError as exc:
        return {
            "status_code": int(exc.code),
            "content_type": str(exc.headers.get("content-type", "")).lower(),
            "title": "",
            "snippet": "",
            "bytes_read": 0,
            "warnings": [],
            "errors": [f"HTTP error while fetching approved URL: {exc.code}"],
        }
    except (URLError, OSError, ssl.SSLError, ValueError, InterruptedError, gzip.BadGzipFile) as exc:
        return {
            "status_code": None,
            "content_type": "",
            "title": "",
            "snippet": "",
            "bytes_read": 0,
            "warnings": [],
            "errors": [f"URL error while fetching public URL: {getattr(exc, 'reason', str(exc))}"],
        }

    text = raw.decode("utf-8", errors="replace")
    title = _extract_title(text)
    snippet = _strip_markup(text)[:max_snippet_chars]
    warnings = ["Response was truncated at the configured byte limit."] if truncated else []

    return {
        "status_code": status_code,
        "content_type": content_type,
        "title": title,
        "snippet": snippet,
        "bytes_read": len(raw),
        "final_url": current_url,
        "redirect_count": redirects,
        "warnings": warnings,
        "errors": [],
    }


__all__ = ("fetch_public_page",)
