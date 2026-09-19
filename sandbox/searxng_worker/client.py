from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

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

    with urlopen(
        request,
        timeout=max(1, int(timeout_seconds)),
    ) as response:
        try:
            decoded = response.read().decode("utf-8")
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
