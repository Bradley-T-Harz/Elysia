"""Stable UUIDv7 identifiers for new Elysia first-class objects."""

from __future__ import annotations

import secrets
from threading import Lock
import time
from uuid import UUID


_UUID7_LOCK = Lock()
_LAST_MILLISECOND = -1
_RAND_A = 0


def uuid7() -> UUID:
    """Return an RFC 9562 UUIDv7 using the system clock and CSPRNG bits.

    The 12-bit ``rand_a`` field is advanced monotonically within one
    millisecond. The remaining 62 random bits retain collision resistance.
    """

    global _LAST_MILLISECOND, _RAND_A
    millisecond = time.time_ns() // 1_000_000
    with _UUID7_LOCK:
        if millisecond > _LAST_MILLISECOND:
            _LAST_MILLISECOND = millisecond
            _RAND_A = secrets.randbits(12)
        else:
            millisecond = _LAST_MILLISECOND
            _RAND_A = (_RAND_A + 1) & 0xFFF
            if _RAND_A == 0:
                _LAST_MILLISECOND += 1
                millisecond = _LAST_MILLISECOND
        rand_a = _RAND_A

    value = (
        ((millisecond & ((1 << 48) - 1)) << 80)
        | (0x7 << 76)
        | ((rand_a & 0xFFF) << 64)
        | (0b10 << 62)
        | secrets.randbits(62)
    )
    return UUID(int=value)


def new_id(prefix: str | None = None) -> str:
    value = str(uuid7())
    return f"{prefix}_{value}" if prefix else value


__all__ = ("new_id", "uuid7")
