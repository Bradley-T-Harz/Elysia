"""Static BlendForge header inspection without launching Blender."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from app.api.coding_engineering_static import EngineeringInspectionError, classify_reference, risk


_PATH_FRAGMENT_RE = re.compile(rb"(?:(?:\.\.?/)|(?:[A-Za-z]:[\\/])|/)[^\x00\r\n]{1,220}?\.blend", re.IGNORECASE)


def inspect_blend(path: Path, *, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    scan_limit = min(limits["max_input_bytes"], 16 * 1024 * 1024)
    with path.open("rb") as stream:
        header = stream.read(12)
        scan = header + stream.read(max(0, scan_limit - len(header)))
    if len(header) < 12 or not header.startswith(b"BLENDER"):
        raise EngineeringInspectionError("blend_header_not_detected")
    pointer_code = chr(header[7])
    endian_code = chr(header[8])
    version_raw = header[9:12].decode("ascii", errors="replace")
    version = f"{version_raw[0]}.{version_raw[1:]}" if len(version_raw) == 3 and version_raw.isdigit() else "unknown"
    references = []
    for match in _PATH_FRAGMENT_RE.finditer(scan):
        raw = match.group(0).decode("utf-8", errors="replace")
        references.append(classify_reference(raw, source_path=path, workspace_root=workspace_root, reference_kind="blend_linked_library_candidate"))
        if len(references) >= limits["max_external_references"]:
            break
    flags = [
        risk("blend_active_content_possible", "high", "Blend files may contain scripts, drivers, handlers, add-ons, and linked data; none were executed or loaded."),
        risk("blend_metadata_only", "warning", "Only the static Blender header and bounded linked-library string candidates were inspected."),
    ]
    if references:
        flags.append(risk("linked_library_candidates", "warning", "Possible linked .blend paths were detected but never followed.", len(references)))
    return {
        "blender_file_version": version,
        "pointer_size_bits": 32 if pointer_code == "_" else 64 if pointer_code == "-" else None,
        "endianness": "little" if endian_code == "v" else "big" if endian_code == "V" else "unknown",
        "static_scan_bytes": len(scan),
        "linked_library_candidate_count": len(references),
        "embedded_script_state": "possible_not_loaded_or_executed",
        "driver_state": "possible_not_evaluated",
        "addon_state": "not_loaded",
        "preview_state": "future_locked_sandbox_and_exact_approval_required",
        "risk_flags": flags,
        "external_references": references,
        "magic_summary": f"Blender file {version}",
    }


__all__ = ("inspect_blend",)
