"""Transaction contract helpers for data mutations."""

from __future__ import annotations


def transaction_summary(*, required: bool, mode: str) -> dict[str, str | bool]:
    return {"required": required, "mode": mode, "rollback_on_failure": True}


__all__ = ("transaction_summary",)
