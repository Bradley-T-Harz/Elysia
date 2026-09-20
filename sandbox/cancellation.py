"""Small fail-closed helpers for cooperatively cancellable sandbox work."""

from __future__ import annotations

from collections.abc import Callable


CancelCheck = Callable[[], bool]


def cancellation_requested(
    cancel_check: CancelCheck | None,
) -> bool:
    """
    Return whether work should stop.

    A broken cancellation callback fails closed rather than silently allowing
    bounded worker activity to continue.
    """
    if cancel_check is None:
        return False

    try:
        return bool(cancel_check())
    except Exception:
        return True


__all__ = (
    "CancelCheck",
    "cancellation_requested",
)
