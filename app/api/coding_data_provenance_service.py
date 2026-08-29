"""Small provenance helpers for science/data stewardship."""

from __future__ import annotations


def provenance_ref(kind: str, **values: object) -> dict[str, object]:
    return {"kind": kind, **values}


__all__ = ("provenance_ref",)
