from __future__ import annotations

import json

import pytest

import sandbox.searxng_worker.client as client_module
from sandbox.searxng_worker.client import search_searxng


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {
                "results": [
                    {
                        "title": "Result one",
                        "url": "https://example.test/one",
                        "content": "Snippet one",
                        "engine": "fake",
                    },
                    {
                        "title": "Result two",
                        "url": "https://example.test/two",
                        "content": "Snippet two",
                        "engine": "fake",
                    },
                ]
            }
        ).encode("utf-8")


def test_client_builds_loopback_search_url_and_parses_json(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)

    results = search_searxng(
        base_url="http://127.0.0.1:8888",
        search_endpoint="/search",
        query="wetland restoration",
        max_results=1,
        timeout_seconds=3,
        safe_search="moderate",
        categories=["general"],
        language="en",
    )

    assert captured["url"].startswith("http://127.0.0.1:8888/search?")
    assert "format=json" in captured["url"]
    assert "q=wetland+restoration" in captured["url"]
    assert "safesearch=1" in captured["url"]
    assert captured["timeout"] == 3
    assert results == [
        {
            "title": "Result one",
            "url": "https://example.test/one",
            "snippet": "Snippet one",
            "source_engine": "fake",
            "rank": 1,
        }
    ]


def test_client_rejects_non_loopback_url():
    with pytest.raises(ValueError):
        search_searxng(
            base_url="https://search.example.com",
            search_endpoint="/search",
            query="wetlands",
            max_results=1,
            timeout_seconds=3,
            safe_search="moderate",
            categories=["general"],
            language="en",
        )


def test_client_rejects_non_search_endpoint():
    with pytest.raises(ValueError):
        search_searxng(
            base_url="http://127.0.0.1:8888",
            search_endpoint="/fetch",
            query="wetlands",
            max_results=1,
            timeout_seconds=3,
            safe_search="moderate",
            categories=["general"],
            language="en",
        )


def test_client_rejects_unknown_safe_search_posture():
    with pytest.raises(ValueError, match="safe-search posture"):
        search_searxng(
            base_url="http://127.0.0.1:8888",
            search_endpoint="/search",
            query="wetlands",
            max_results=1,
            timeout_seconds=3,
            safe_search="invented",
            categories=["general"],
            language="en",
        )
