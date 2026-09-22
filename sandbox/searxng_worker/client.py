from __future__ import annotations

import json
from collections.abc import Callable
from http.client import HTTPConnection, HTTPSConnection, HTTPException
import socket
from threading import Event, Thread
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from sandbox.cancellation import cancellation_requested

from .config import is_loopback_base_url


class SearxngProtocolError(RuntimeError):
    """The local SearXNG endpoint responded without the required JSON contract."""


def _normalize_result(raw: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "title": str(raw.get("title") or "").strip(),
        "url": str(raw.get("url") or raw.get("href") or "").strip(),
        "snippet": str(raw.get("content") or raw.get("snippet") or "").strip(),
        "source_engine": str(
            raw.get("engine") or raw.get("source_engine") or ""
        ).strip(),
        "rank": rank,
    }


def _safe_search_value(value: str) -> str:
    normalized = str(value or "moderate").strip().casefold()
    mapping = {
        "off": "0",
        "none": "0",
        "0": "0",
        "moderate": "1",
        "1": "1",
        "strict": "2",
        "2": "2",
    }
    if normalized not in mapping:
        raise ValueError(
            "SearXNG safe-search posture must be off, moderate, or strict."
        )
    return mapping[normalized]


def _force_close_connection(
    connection: HTTPConnection,
) -> None:
    """
    Close an active loopback transport aggressively enough to wake a
    concurrent blocking request/read when STOP fires.
    """
    sock = getattr(connection, "sock", None)

    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    try:
        connection.close()
    except OSError:
        pass


def _cancellable_loopback_get(
    request: Request,
    *,
    timeout_seconds: int,
    cancel_check: Callable[[], bool],
) -> bytes:
    """
    Perform one loopback GET whose actual socket can be closed by STOP.

    This path is used whenever a governed cancellation signal is available.
    It deliberately avoids leaving an abandoned network thread running after
    the caller has already reported cancellation.
    """
    if cancellation_requested(cancel_check):
        raise InterruptedError(
            "SearXNG search was cancelled before transport."
        )

    parsed = urlparse(request.full_url)
    hostname = str(parsed.hostname or "").strip()

    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
    ):
        raise ValueError(
            "SearXNG cancellable transport requires loopback HTTP(S)."
        )

    timeout = max(1, int(timeout_seconds))
    port = parsed.port or (
        443 if parsed.scheme == "https" else 80
    )

    if parsed.scheme == "https":
        connection: HTTPConnection = HTTPSConnection(
            hostname,
            port=port,
            timeout=timeout,
        )
    else:
        connection = HTTPConnection(
            hostname,
            port=port,
            timeout=timeout,
        )

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    stop_watcher = Event()
    response = None

    def watch_for_cancel() -> None:
        while not stop_watcher.wait(0.05):
            if cancellation_requested(cancel_check):
                _force_close_connection(
                    connection
                )
                return

    watcher = Thread(
        target=watch_for_cancel,
        name="elysia-searxng-cancel-watcher",
        daemon=True,
    )
    watcher.start()

    try:
        connection.request(
            "GET",
            path,
            headers=dict(
                request.header_items()
            ),
        )

        response = connection.getresponse()

        if cancellation_requested(cancel_check):
            raise InterruptedError(
                "SearXNG search was cancelled during transport."
            )

        status = int(
            getattr(response, "status", 0)
            or 0
        )

        if status < 200 or status >= 300:
            raise HTTPError(
                request.full_url,
                status,
                str(
                    getattr(
                        response,
                        "reason",
                        "SearXNG HTTP error",
                    )
                ),
                getattr(
                    response,
                    "headers",
                    None,
                ),
                None,
            )

        payload = response.read()

        if cancellation_requested(cancel_check):
            raise InterruptedError(
                "SearXNG search was cancelled while reading."
            )

        return payload

    except InterruptedError:
        raise

    except (OSError, HTTPException) as exc:
        if cancellation_requested(cancel_check):
            raise InterruptedError(
                "SearXNG search was cancelled during transport."
            ) from exc

        raise

    finally:
        stop_watcher.set()

        if response is not None:
            try:
                response.close()
            except OSError:
                pass

        _force_close_connection(
            connection
        )

        watcher.join(
            timeout=0.25
        )


def _read_urlopen_payload(
    request: Request,
    *,
    timeout_seconds: int,
    cancel_check: Callable[[], bool] | None,
) -> bytes:
    """
    Read one bounded loopback SearXNG response.

    Compatibility callers without a cancellation contract retain the original
    urllib path. Governed runtime work uses the actively-closeable path.
    """
    timeout = max(
        1,
        int(timeout_seconds),
    )

    if cancel_check is None:
        with urlopen(
            request,
            timeout=timeout,
        ) as response:
            return response.read()

    return _cancellable_loopback_get(
        request,
        timeout_seconds=timeout,
        cancel_check=cancel_check,
    )


def search_searxng(
    *,
    base_url: str,
    search_endpoint: str,
    query: str,
    max_results: int,
    timeout_seconds: int,
    safe_search: str,
    categories: list[str],
    language: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    """
    Search a configured loopback SearXNG instance and normalize JSON results.

    This is search-result-only. It never fetches result URLs.
    """
    if not is_loopback_base_url(base_url):
        raise ValueError(
            "SearXNG client only accepts loopback base_url values."
        )

    endpoint = str(search_endpoint or "/search")
    if endpoint != "/search":
        raise ValueError(
            "SearXNG client only accepts the configured /search endpoint."
        )

    params: dict[str, str] = {
        "q": str(query),
        "format": "json",
        "safesearch": _safe_search_value(safe_search),
    }

    if categories:
        params["categories"] = ",".join(
            str(item)
            for item in categories
            if str(item).strip()
        )

    if language:
        params["language"] = str(language)

    url = (
        f"{urljoin(base_url.rstrip('/') + '/', endpoint.lstrip('/'))}"
        f"?{urlencode(params)}"
    )

    request = Request(
        url,
        headers={"Accept": "application/json"},
    )

    raw_payload = _read_urlopen_payload(
        request,
        timeout_seconds=timeout_seconds,
        cancel_check=cancel_check,
    )

    try:
        decoded = raw_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SearxngProtocolError(
            "SearXNG returned a response that was not valid UTF-8: "
            f"{exc}"
        ) from exc

    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise SearxngProtocolError(
            f"SearXNG returned invalid JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise SearxngProtocolError(
            "SearXNG JSON response must be an object."
        )

    if "results" not in payload:
        raise SearxngProtocolError(
            "SearXNG JSON response is missing the results list."
        )

    raw_results = payload["results"]

    if not isinstance(raw_results, list):
        raise SearxngProtocolError(
            "SearXNG JSON response field 'results' must be a list."
        )

    normalized: list[dict[str, Any]] = []

    for index, item in enumerate(
        raw_results[: max(0, int(max_results))],
        start=1,
    ):
        if not isinstance(item, dict):
            continue

        result = _normalize_result(item, index)

        if result["url"]:
            normalized.append(result)

    return normalized


__all__ = (
    "SearxngProtocolError",
    "search_searxng",
)
