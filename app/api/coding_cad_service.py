"""Bounded CADForge inspectors for neutral CAD, DXF, and Fusion containers."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
import re
from typing import Any
import zipfile

from app.api.coding_engineering_static import (
    EngineeringInspectionError,
    bounds_payload,
    classify_reference,
    finite_point,
    read_bounded_text,
    risk,
    update_bounds,
)
from app.api.schemas.engineering import EngineeringExternalReference


_STEP_ENTITY_RE = re.compile(r"(?im)^\s*#\d+\s*=\s*([A-Z0-9_]+)\s*\(")
_STEP_POINT_RE = re.compile(r"(?i)CARTESIAN_POINT\s*\([^,]*,\s*\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)")


def _step_report(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    text = read_bounded_text(path, limits["max_text_bytes"])
    if "ISO-10303-21" not in text[:4096].upper():
        raise EngineeringInspectionError("step_header_not_detected")
    entity_types = Counter(match.group(1).upper() for match in _STEP_ENTITY_RE.finditer(text))
    entity_count = sum(entity_types.values())
    if entity_count > limits["max_entities"]:
        raise EngineeringInspectionError("cad_entity_limit_exceeded")
    schema_match = re.search(r"(?is)FILE_SCHEMA\s*\(\s*\((.*?)\)\s*\)", text)
    schemas = re.findall(r"'([^']+)'", schema_match.group(1)) if schema_match else []
    products = [value[:240] for value in re.findall(r"(?is)\bPRODUCT\s*\(\s*'([^']*)'", text)[: limits["max_names_in_response"]]]
    bounds: list[list[float]] | None = None
    point_count = 0
    nonfinite = 0
    for match in _STEP_POINT_RE.finditer(text):
        point_count += 1
        try:
            point = tuple(float(value) for value in match.groups())
        except ValueError:
            continue
        if not finite_point(point):
            nonfinite += 1
            continue
        bounds = update_bounds(bounds, point)  # type: ignore[arg-type]
    units: list[str] = []
    upper = text.upper()
    for marker, label in (
        (".MILLI.,.METRE.", "millimetre"),
        (".CENTI.,.METRE.", "centimetre"),
        ("$,.METRE.", "metre"),
        ("CONVERSION_BASED_UNIT('INCH", "inch"),
        ("CONVERSION_BASED_UNIT('DEGREE", "degree"),
    ):
        if marker in upper and label not in units:
            units.append(label)
    assembly_count = entity_types["NEXT_ASSEMBLY_USAGE_OCCURRENCE"] + entity_types["CONTEXT_DEPENDENT_SHAPE_REPRESENTATION"]
    flags = [risk("manufacturing_safety_not_assessed", "info", "Static exchange metadata is not a manufacturing or structural safety assessment.")]
    if not units:
        flags.append(risk("units_not_detected", "warning", "STEP units were not reliably detected by the bounded static parser."))
    if nonfinite:
        flags.append(risk("non_finite_coordinates", "high", "Non-finite STEP Cartesian point coordinates were detected.", nonfinite))
    return {
        "exchange_schema": schemas,
        "entity_count": entity_count,
        "entity_counts_by_type": dict(entity_types.most_common(100)),
        "units_detected": units,
        "product_count": entity_types["PRODUCT"],
        "product_names": products,
        "assembly_relationship_count": assembly_count,
        "shape_representation_count": entity_types["SHAPE_REPRESENTATION"] + entity_types["ADVANCED_BREP_SHAPE_REPRESENTATION"],
        "solid_count": entity_types["MANIFOLD_SOLID_BREP"] + entity_types["BREP_WITH_VOIDS"],
        "closed_shell_count": entity_types["CLOSED_SHELL"],
        "open_shell_count": entity_types["OPEN_SHELL"],
        "face_count": entity_types["ADVANCED_FACE"] + entity_types["FACE_SURFACE"],
        "edge_count": entity_types["EDGE_CURVE"],
        "cartesian_point_count": point_count,
        "coordinate_point_bounds": bounds_payload(bounds),
        "bounding_box_state": "coordinate_points_only_not_ocp_shape_bounds",
        "conversion_readiness": "plan_only_neutral_derivative_exact_approval_required_for_future_apply",
        "risk_flags": flags,
        "external_references": [],
        "magic_summary": "ISO 10303-21 STEP exchange",
    }


def _iges_report(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    text = read_bounded_text(path, limits["max_text_bytes"])
    lines = text.splitlines()
    section_counts = Counter(line[72:73].upper() for line in lines if len(line) >= 73)
    if not section_counts["S"] or not section_counts["T"]:
        raise EngineeringInspectionError("iges_sections_not_detected")
    directory_lines = [line for line in lines if len(line) >= 73 and line[72:73].upper() == "D"]
    entity_types = Counter()
    for line in directory_lines[::2]:
        try:
            entity_types[int(line[:8].strip())] += 1
        except ValueError:
            continue
    entity_count = sum(entity_types.values())
    if entity_count > limits["max_entities"]:
        raise EngineeringInspectionError("cad_entity_limit_exceeded")
    global_text = "".join(line[:72] for line in lines if len(line) >= 73 and line[72:73].upper() == "G").upper()
    unit = None
    for token, label in (("2HMM", "millimetre"), ("2HCM", "centimetre"), ("1HM", "metre"), ("2HIN", "inch"), ("2HFT", "foot")):
        if token in global_text:
            unit = label
            break
    curve_types = {100, 102, 104, 106, 110, 112, 114, 116, 118, 120, 126}
    surface_types = {108, 114, 118, 120, 122, 128, 140, 143, 144}
    solid_types = {150, 152, 154, 156, 158, 160, 162, 164, 168, 186}
    flags = [risk("watertightness_not_assessed", "warning", "IGES topology and watertightness are not established by static directory inspection.")]
    if not unit:
        flags.append(risk("units_not_detected", "warning", "IGES units were not reliably detected."))
    return {
        "entity_count": entity_count,
        "entity_counts_by_type": {str(key): value for key, value in entity_types.most_common(100)},
        "curve_entity_count": sum(value for key, value in entity_types.items() if key in curve_types),
        "surface_entity_count": sum(value for key, value in entity_types.items() if key in surface_types),
        "solid_entity_count": sum(value for key, value in entity_types.items() if key in solid_types),
        "units_detected": unit,
        "section_line_counts": {key: section_counts[key] for key in ("S", "G", "D", "P", "T")},
        "bounding_box_state": "unavailable_in_bounded_static_pass",
        "import_warnings": ["IGES units, trimming, topology, and solids require validation in a dedicated CAD worker before derivative export."],
        "risk_flags": flags,
        "external_references": [],
        "magic_summary": "IGES fixed-record exchange",
    }


_DXF_UNITS = {
    0: "unitless",
    1: "inches",
    2: "feet",
    4: "millimetres",
    5: "centimetres",
    6: "metres",
    9: "mils",
    10: "yards",
    14: "decimetres",
}


def _dxf_pairs(text: str, max_lines: int) -> list[tuple[int, str]]:
    lines = text.splitlines()
    if len(lines) > max_lines:
        raise EngineeringInspectionError("engineering_line_limit_exceeded")
    if len(lines) % 2:
        lines = lines[:-1]
    pairs = []
    for index in range(0, len(lines), 2):
        try:
            code = int(lines[index].strip())
        except ValueError:
            continue
        pairs.append((code, lines[index + 1].strip()))
    return pairs


def _dxf_report(path: Path, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    text = read_bounded_text(path, limits["max_text_bytes"])
    pairs = _dxf_pairs(text, limits["max_lines"])
    if not any(code == 0 and value.upper() == "SECTION" for code, value in pairs):
        raise EngineeringInspectionError("dxf_section_not_detected")
    version = None
    units_code = None
    layers: set[str] = set()
    entity_counts: Counter[str] = Counter()
    block_count = 0
    text_count = 0
    closed_profiles = 0
    open_profiles = 0
    any_3d = False
    bounds: list[list[float]] | None = None
    preview_segments: list[list[list[float]]] = []
    xref_values: list[str] = []
    section = ""
    current: str | None = None
    record: list[tuple[int, str]] = []

    def finish_record(record_type: str | None, values: list[tuple[int, str]]) -> None:
        nonlocal bounds, block_count, text_count, closed_profiles, open_profiles, any_3d
        if not record_type:
            return
        upper_type = record_type.upper()
        if section == "ENTITIES":
            entity_counts[upper_type] += 1
            if upper_type in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
                text_count += 1
            if upper_type in {"3DFACE", "MESH", "POLYFACE"}:
                any_3d = True
            flags = [int(value) for code, value in values if code == 70 and value.lstrip("-").isdigit()]
            if upper_type in {"LWPOLYLINE", "POLYLINE"}:
                if any(flag & 1 for flag in flags):
                    closed_profiles += 1
                else:
                    open_profiles += 1
            points: dict[int, list[float]] = {}
            for code, value in values:
                if 10 <= code <= 38:
                    try:
                        coordinate = float(value)
                    except ValueError:
                        continue
                    axis = code // 10 - 1
                    if axis not in {0, 1, 2}:
                        continue
                    point_key = code % 10
                    points.setdefault(point_key, [0.0, 0.0, 0.0])[axis] = coordinate
                    if axis == 2 and abs(coordinate) > 1e-12:
                        any_3d = True
            for point in points.values():
                if finite_point(point):
                    bounds = update_bounds(bounds, tuple(point))  # type: ignore[arg-type]
            if upper_type == "LINE" and 0 in points and 1 in points and len(preview_segments) < limits["max_preview_segments"]:
                preview_segments.append([[points[0][0], points[0][1]], [points[1][0], points[1][1]]])
        elif section == "BLOCKS" and upper_type == "BLOCK":
            block_count += 1
            block_flags = next((int(value) for code, value in values if code == 70 and value.lstrip("-").isdigit()), 0)
            if block_flags & 4 or block_flags & 8:
                path_value = next((value for code, value in values if code == 1), "")
                name_value = next((value for code, value in values if code == 2), "")
                xref_values.append(path_value or name_value)
        elif section == "TABLES" and upper_type == "LAYER":
            layer = next((value for code, value in values if code == 2), "")
            if layer:
                layers.add(layer[:240])

    index = 0
    while index < len(pairs):
        code, value = pairs[index]
        upper = value.upper()
        if code == 9 and upper == "$ACADVER" and index + 1 < len(pairs):
            version = pairs[index + 1][1]
        if code == 9 and upper == "$INSUNITS" and index + 1 < len(pairs):
            try:
                units_code = int(pairs[index + 1][1])
            except ValueError:
                pass
        if code == 2 and index > 0 and pairs[index - 1] == (0, "SECTION"):
            finish_record(current, record)
            current, record = None, []
            section = upper
        elif code == 0:
            finish_record(current, record)
            current, record = upper, []
        else:
            record.append((code, value))
        index += 1
    finish_record(current, record)
    entity_total = sum(entity_counts.values())
    if entity_total > limits["max_entities"]:
        raise EngineeringInspectionError("cad_entity_limit_exceeded")
    references = [classify_reference(value, source_path=path, workspace_root=workspace_root, reference_kind="dxf_xref") for value in xref_values if value]
    flags = [risk("cut_readiness_not_assessed", "info", "DXF inspection does not establish toolpath or cut readiness.")]
    blocked = sum(1 for ref in references if ref.resolution_state.startswith("blocked_"))
    if blocked:
        flags.append(risk("blocked_xrefs", "high", "DXF external references were reported but not followed.", blocked))
    if open_profiles:
        flags.append(risk("open_profiles_present", "warning", "Open polyline profiles were detected; this is not a cut-readiness verdict.", open_profiles))
    return {
        "dxf_version": version,
        "units_code": units_code,
        "units": _DXF_UNITS.get(units_code, "unknown") if units_code is not None else "not_specified",
        "layer_count": len(layers),
        "layer_names": sorted(layers)[: limits["max_names_in_response"]],
        "entity_count": entity_total,
        "entity_counts_by_type": dict(entity_counts.most_common(100)),
        "block_count": block_count,
        "text_annotation_count": text_count,
        "closed_profile_count": closed_profiles,
        "open_profile_count": open_profiles,
        "dimensionality": "3d_or_mixed" if any_3d else "2d_observed",
        "bounding_box": bounds_payload(bounds),
        "xref_count": len(references),
        "_preview_segments": preview_segments,
        "risk_flags": flags,
        "external_references": references,
        "magic_summary": f"DXF {version or 'unknown version'} text exchange",
    }


def _fusion_report(path: Path, type_id: str, limits: dict[str, int]) -> dict[str, Any]:
    if path.stat().st_size > limits["max_input_bytes"]:
        raise EngineeringInspectionError("engineering_input_limit_exceeded")
    with path.open("rb") as stream:
        raw = stream.read(4096)
    is_zip = raw.startswith(b"PK\x03\x04")
    members: list[dict[str, Any]] = []
    total_uncompressed = 0
    encrypted = 0
    suspicious_ratio_count = 0
    references: list[EngineeringExternalReference] = []
    if is_zip:
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > limits["max_archive_members"]:
                    raise EngineeringInspectionError("fusion_archive_member_limit_exceeded")
                for info in infos:
                    normalized = info.filename.replace("\\", "/")
                    traversal = normalized.startswith("/") or ".." in Path(normalized).parts
                    ratio = info.file_size / max(1, info.compress_size)
                    members.append({
                        "name": normalized[:240],
                        "name_hash": sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:24],
                        "compressed_size": info.compress_size,
                        "uncompressed_size": info.file_size,
                        "encrypted": bool(info.flag_bits & 1),
                        "traversal_spelling": traversal,
                    })
                    references.append(
                        EngineeringExternalReference(
                            reference_kind="f3z_contained_reference",
                            display_reference=normalized[:240],
                            reference_hash=sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:24],
                            scheme="container",
                            resolution_state="blocked_traversal" if traversal else "not_resolved",
                            blocked_reason="unsafe_container_member_not_extracted" if traversal else "contained_reference_not_loaded",
                        )
                    )
                    total_uncompressed += info.file_size
                    encrypted += int(bool(info.flag_bits & 1))
                    suspicious_ratio_count += int(ratio > limits["max_archive_compression_ratio"])
        except zipfile.BadZipFile as exc:
            raise EngineeringInspectionError("malformed_fusion_archive") from exc
    flags = [risk("fusion_local_support_limited", "warning", "Fusion data is limited to local container/header metadata; export to STEP/STL/DXF is recommended.")]
    if encrypted:
        flags.append(risk("encrypted_container_members", "warning", "Encrypted Fusion container members were detected and not read.", encrypted))
    if any(member["traversal_spelling"] for member in members):
        flags.append(risk("unsafe_container_names", "high", "Traversal-like member names were detected and never extracted."))
    if total_uncompressed > limits["max_archive_projected_bytes"]:
        flags.append(risk("projected_archive_size_exceeded", "high", "Projected F3Z member bytes exceed the inspection policy; no member was decompressed."))
    if suspicious_ratio_count:
        flags.append(risk("suspicious_archive_compression_ratio", "high", "Suspicious F3Z compression ratios were detected; no member was decompressed.", suspicious_ratio_count))
    return {
        "container_recognized": is_zip,
        "container_kind": "zip_compatible" if is_zip else "opaque_fusion_binary",
        "member_count": len(members),
        "members": members[: limits["max_names_in_response"]],
        "projected_uncompressed_bytes": total_uncompressed,
        "cloud_translation": "unavailable_by_design",
        "autodesk_upload": "unavailable_by_design",
        "local_workflow_recommendation": "Export to STEP, STL, or DXF in the authoring tool, then inspect the neutral derivative locally.",
        "risk_flags": flags,
        "external_references": references[: limits["max_external_references"]],
        "magic_summary": f"Fusion {type_id.upper()} {'ZIP-compatible container' if is_zip else 'opaque data'}",
    }


def inspect_cad(path: Path, *, type_id: str, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    if type_id == "step":
        return _step_report(path, limits)
    if type_id == "iges":
        return _iges_report(path, limits)
    if type_id == "dxf":
        return _dxf_report(path, workspace_root, limits)
    if type_id in {"f3d", "f3z"}:
        return _fusion_report(path, type_id, limits)
    raise EngineeringInspectionError("unsupported_cad_format")


__all__ = ("inspect_cad",)
