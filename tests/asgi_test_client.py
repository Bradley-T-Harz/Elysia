"""Synchronous facade over httpx's direct in-process ASGI transport."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class ASGITestClient:
    """Provide familiar request helpers without AnyIO's blocking portal."""

    def __init__(self, app: Any, *, base_url: str = "http://testserver") -> None:
        self.app = app
        self.base_url = base_url

    def __enter__(self) -> "ASGITestClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)
