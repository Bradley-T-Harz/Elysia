from __future__ import annotations

from io import BytesIO
import gzip
from types import SimpleNamespace

from urllib.request import BaseHandler

from sandbox.fetch_worker.client import _NoRedirectHandler, fetch_public_page


class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class FakeResponse:
    status = 200

    def __init__(self, body: bytes):
        self._body = BytesIO(body)
        self.headers = FakeHeaders({"content-type": "text/html; charset=utf-8"})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status

    def read(self, size=-1):
        return self._body.read(size)

    def close(self):
        return None


class FakeOpener:
    def __init__(self):
        self.seen_request = None

    def open(self, request, timeout):
        self.seen_request = request
        assert timeout == 5
        return FakeResponse(
            b"<html><head><title>Example</title></head><body><p>Hello public page.</p></body></html>"
        )


def test_fetch_client_returns_bounded_sanitized_metadata():
    opener = FakeOpener()

    result = fetch_public_page(
        url="https://example.com/",
        timeout_seconds=5,
        max_response_bytes=1000,
        max_snippet_chars=40,
        user_agent="Elysia-Test",
        follow_redirects=False,
        opener=opener,
        allowed_public_ips=["93.184.216.34"],
    )

    assert opener.seen_request.full_url == "https://example.com/"
    assert result["status_code"] == 200
    assert result["content_type"].startswith("text/html")
    assert result["title"] == "Example"
    assert "Hello public page" in result["snippet"]
    assert "<html" not in result["snippet"]
    assert result["errors"] == []


def test_no_redirect_handler_is_a_real_urllib_handler():
    assert isinstance(_NoRedirectHandler(), BaseHandler)


class PolicyResponse(FakeResponse):
    def __init__(self, body: bytes, *, status: int = 200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = FakeHeaders(headers or {"content-type": "text/html"})


class PolicyOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        return self.responses.pop(0)


def _fetch(opener, **overrides):
    options = {
        "url": "https://example.com/source",
        "timeout_seconds": 5,
        "max_response_bytes": 256,
        "max_snippet_chars": 80,
        "user_agent": "Elysia-Test",
        "follow_redirects": False,
        "opener": opener,
        "allowed_public_ips": ["93.184.216.34"],
        "max_decompressed_bytes": 512,
    }
    options.update(overrides)
    return fetch_public_page(**options)


def test_fetch_client_blocks_mime_decompression_bomb_and_cancellation():
    mime = _fetch(
        PolicyOpener(
            [PolicyResponse(b"binary", headers={"content-type": "application/octet-stream"})]
        )
    )
    assert "MIME type is not allowed" in mime["errors"][0]

    compressed = gzip.compress(b"A" * 5000)
    bomb = _fetch(
        PolicyOpener(
            [
                PolicyResponse(
                    compressed,
                    headers={"content-type": "text/plain", "content-encoding": "gzip"},
                )
            ]
        ),
        max_response_bytes=len(compressed) + 10,
        max_decompressed_bytes=200,
    )
    assert "decompressed byte limit" in bomb["errors"][0]

    opener = PolicyOpener([PolicyResponse(b"unused")])
    cancelled = _fetch(opener, cancel_check=lambda: True)
    assert "cancelled" in cancelled["errors"][0]
    assert opener.calls == 0


def test_fetch_client_revalidates_redirect_and_blocks_https_downgrade():
    opener = PolicyOpener(
        [
            PolicyResponse(
                b"",
                status=302,
                headers={"content-type": "text/html", "location": "http://example.org/plain"},
            )
        ]
    )
    result = _fetch(
        opener,
        follow_redirects=True,
        redirect_validator=lambda target: SimpleNamespace(
            allowed=True,
            sanitized_url=target,
            resolved_public_ips=["93.184.216.34"],
        ),
    )
    assert "may not downgrade" in result["errors"][0]
