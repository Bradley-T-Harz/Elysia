"""Shared bounded helpers for EngineeringForge domain inspectors."""

from __future__ import annotations

from hashlib import sha256
import math
import os
from pathlib import Path
from typing import Any, Iterable

from app.api.schemas.engineering import EngineeringExternalReference, EngineeringRiskFlag


class EngineeringInspectionError(ValueError):
    """A stable, policy-safe reason that static inspection could not continue."""


def hash_file(path: Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def read_bounded_bytes(path: Path, limit: int) -> bytes:
    size = path.stat().st_size
    if size > limit:
        raise EngineeringInspectionError("engineering_input_limit_exceeded")
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def read_bounded_text(path: Path, limit: int) -> str:
    raw = read_bounded_bytes(path, limit)
    if b"\x00" in raw:
        raise EngineeringInspectionError("unexpected_binary_content")
    return raw.decode("utf-8", errors="replace")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1].lower()


def parse_defused_xml(path: Path, limit: int):
    raw = read_bounded_bytes(path, limit)
    lowered = raw[: min(len(raw), 1024 * 1024)].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise EngineeringInspectionError("xml_doctype_or_entity_blocked")
    try:
        from defusedxml import ElementTree as SafeElementTree

        return SafeElementTree.fromstring(raw)
    except EngineeringInspectionError:
        raise
    except Exception as exc:
        raise EngineeringInspectionError("malformed_or_unsafe_xml") from exc


def risk(code: str, severity: str, summary: str, count: int = 1) -> EngineeringRiskFlag:
    return EngineeringRiskFlag(code=code, severity=severity, summary=summary, count=max(1, int(count)))  # type: ignore[arg-type]


def risk_counts(flags: Iterable[EngineeringRiskFlag]) -> dict[str, int]:
    return {flag.code: flag.count for flag in flags}


def finite_point(values: Iterable[float]) -> bool:
    return all(math.isfinite(value) for value in values)


def update_bounds(bounds: list[list[float]] | None, point: tuple[float, float, float]) -> list[list[float]]:
    if bounds is None:
        return [[point[0], point[1], point[2]], [point[0], point[1], point[2]]]
    for index, value in enumerate(point):
        bounds[0][index] = min(bounds[0][index], value)
        bounds[1][index] = max(bounds[1][index], value)
    return bounds


def bounds_payload(bounds: list[list[float]] | None) -> dict[str, Any] | None:
    if bounds is None:
        return None
    minimum, maximum = bounds
    return {
        "minimum": [round(value, 9) for value in minimum],
        "maximum": [round(value, 9) for value in maximum],
        "extent": [round(maximum[index] - minimum[index], 9) for index in range(3)],
    }


def _contains_symlink(path: Path, stop: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current == stop or current.parent == current:
            return False
        current = current.parent


def classify_reference(
    reference: str,
    *,
    source_path: Path,
    workspace_root: Path,
    reference_kind: str,
) -> EngineeringExternalReference:
    cleaned = str(reference or "").strip().replace("\\", "/")
    digest = sha256(cleaned.encode("utf-8", errors="replace")).hexdigest()[:24]
    display = cleaned[:240] if cleaned else "(empty reference)"
    lowered = cleaned.lower()
    scheme = "relative"
    state = "not_resolved"
    reason: str | None = None
    if lowered.startswith("package://"):
        scheme, state, reason = "package", "blocked_package_unmapped", "package_root_not_explicitly_mapped"
    elif lowered.startswith(("http://", "https://", "ftp://", "fuel://", "model://")):
        scheme = lowered.split(":", 1)[0]
        state, reason = "blocked_external_scheme", "external_fetch_unavailable_by_design"
    elif lowered.startswith("file://"):
        scheme, state, reason = "file", "blocked_absolute", "absolute_reference_not_followed"
    elif Path(cleaned).is_absolute() or (len(cleaned) >= 3 and cleaned[1:3] == ":/"):
        scheme, state, reason = "absolute", "blocked_absolute", "absolute_reference_not_followed"
    else:
        lexical = Path(os.path.abspath(str(source_path.parent / cleaned)))
        try:
            lexical.relative_to(workspace_root)
        except ValueError:
            state, reason = "blocked_traversal", "reference_escapes_workspace"
        else:
            if ".." in Path(cleaned).parts:
                # A traversal spelling is blocked even when normalization happens to land inside.
                state, reason = "blocked_traversal", "traversal_reference_not_followed"
            elif _contains_symlink(lexical, workspace_root):
                state, reason = "blocked_symlink", "symlink_reference_not_followed"
            elif lexical.is_file():
                state = "inside_workspace"
            else:
                state = "missing"
    return EngineeringExternalReference(
        reference_kind=reference_kind,
        display_reference=display,
        reference_hash=digest,
        scheme=scheme,
        resolution_state=state,  # type: ignore[arg-type]
        blocked_reason=reason,
    )


def sanitized_count_map(values: dict[str, int], *, limit: int = 100) -> dict[str, int]:
    return {str(key)[:80]: int(value) for key, value in sorted(values.items())[:limit]}


__all__ = (
    "EngineeringInspectionError",
    "bounds_payload",
    "classify_reference",
    "finite_point",
    "hash_file",
    "local_name",
    "parse_defused_xml",
    "read_bounded_bytes",
    "read_bounded_text",
    "risk",
    "risk_counts",
    "sanitized_count_map",
    "update_bounds",
)
