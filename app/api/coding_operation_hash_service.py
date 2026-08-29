"""Canonical hashes for exact governed operation plans."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any


def operation_plan_hash(
    *,
    action: str,
    source_relative_path: str | None,
    target_relative_path: str | None,
    source_hash: str | None,
    details: dict[str, Any] | None = None,
) -> str:
    canonical = json.dumps(
        {
            "action": action,
            "source_relative_path": source_relative_path,
            "target_relative_path": target_relative_path,
            "source_hash": source_hash,
            "details": details or {},
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()[:32]


__all__ = ("operation_plan_hash",)
