"""Canonical summary-service compatibility import.

The original facade imported this module before it existed. Part 2B keeps the
stable symbol while routing summary truth to the canonical XDG SQLite fabric.
"""

from app.memory.fabric_service import MemorySummaryService

__all__ = ("MemorySummaryService",)
