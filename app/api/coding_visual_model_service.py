"""Local semantic vision provider truth surface."""

from __future__ import annotations

import os


def semantic_vision_health() -> dict[str, object]:
    provider = os.environ.get("ELYSIA_LOCAL_VISION_PROVIDER", "").strip()
    return {
        "available": False,
        "provider": provider or "not_configured",
        "local_only": True,
        "cloud_upload_allowed": False,
        "note": "No local semantic vision provider is configured. Deterministic visual analysis remains available.",
    }


__all__ = ("semantic_vision_health",)
