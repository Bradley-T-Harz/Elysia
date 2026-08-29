"""Bounded GeometryForge inspectors for STL, OBJ, and COLLADA."""

from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import re
import struct
from typing import Any

from app.api.coding_engineering_static import (
    EngineeringInspectionError,
    bounds_payload,
    classify_reference,
    finite_point,
    local_name,
    parse_defused_xml,
    read_bounded_text,
    risk,
    update_bounds,
)


def _triangle_metrics(vertices: tuple[tuple[float, float, float], ...]) -> tuple[float, tuple[float, float, float]]:
    a, b, c = vertices
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    magnitude = math.sqrt(sum(value * value for value in cross))
    return magnitude / 2.0, cross


def _stl_report(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(84)
    if len(header) < 5:
        raise EngineeringInspectionError("malformed_stl")
    binary_count = struct.unpack("<I", header[80:84])[0] if len(header) >= 84 else 0
    expected_binary_size = 84 + binary_count * 50
    binary = len(header) >= 84 and expected_binary_size == size
    encoding = "binary" if binary else "ascii"
    max_triangles = limits["max_triangles"]
    if binary and binary_count > max_triangles:
        raise EngineeringInspectionError("stl_triangle_limit_exceeded")

    bounds: list[list[float]] | None = None
    surface_area = 0.0
    triangle_count = 0
    nonfinite = 0
    degenerate = 0
    zero_normals = 0
    normal_mismatch = 0
    duplicates = 0
    topology_limit = min(max_triangles, 250_000)
    edges: Counter[tuple[tuple[float, float, float], tuple[float, float, float]]] = Counter()
    seen_triangles: set[tuple[tuple[float, float, float], ...]] = set()
    preview_segments: list[list[list[float]]] = []
    preview_limit = limits["max_preview_segments"]

    def consume(normal: tuple[float, float, float], vertices: tuple[tuple[float, float, float], ...]) -> None:
        nonlocal bounds, surface_area, triangle_count, nonfinite, degenerate, zero_normals, normal_mismatch, duplicates
        triangle_count += 1
        if not finite_point((*normal, *(value for vertex in vertices for value in vertex))):
            nonfinite += 1
            return
        for vertex in vertices:
            bounds = update_bounds(bounds, vertex)
        area, cross = _triangle_metrics(vertices)
        surface_area += area
        if area <= 1e-15:
            degenerate += 1
        normal_length = math.sqrt(sum(value * value for value in normal))
        if normal_length <= 1e-15:
            zero_normals += 1
        elif area > 1e-15 and sum(normal[index] * cross[index] for index in range(3)) < 0:
            normal_mismatch += 1
        if triangle_count <= topology_limit:
            rounded = tuple(tuple(round(value, 9) for value in vertex) for vertex in vertices)
            canonical_triangle = tuple(sorted(rounded))
            if canonical_triangle in seen_triangles:
                duplicates += 1
            else:
                seen_triangles.add(canonical_triangle)
            for start, end in ((rounded[0], rounded[1]), (rounded[1], rounded[2]), (rounded[2], rounded[0])):
                edges[tuple(sorted((start, end)))] += 1
        if len(preview_segments) < preview_limit:
            for start, end in ((vertices[0], vertices[1]), (vertices[1], vertices[2]), (vertices[2], vertices[0])):
                if len(preview_segments) >= preview_limit:
                    break
                preview_segments.append([[start[0], start[1]], [end[0], end[1]]])

    if binary:
        with path.open("rb") as stream:
            stream.seek(84)
            for _ in range(binary_count):
                record = stream.read(50)
                if len(record) != 50:
                    raise EngineeringInspectionError("truncated_binary_stl")
                values = struct.unpack("<12fH", record)
                consume(tuple(values[0:3]), (tuple(values[3:6]), tuple(values[6:9]), tuple(values[9:12])))  # type: ignore[arg-type]
    else:
        text = read_bounded_text(path, limits["max_text_bytes"])
        vertex_values = [
            tuple(float(value) for value in match.groups())
            for match in re.finditer(r"(?im)^\s*vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", text)
        ]
        if len(vertex_values) % 3:
            raise EngineeringInspectionError("malformed_ascii_stl_vertices")
        if len(vertex_values) // 3 > max_triangles:
            raise EngineeringInspectionError("stl_triangle_limit_exceeded")
        normals = [
            tuple(float(value) for value in match.groups())
            for match in re.finditer(r"(?im)^\s*facet\s+normal\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", text)
        ]
        for index in range(0, len(vertex_values), 3):
            normal = normals[index // 3] if index // 3 < len(normals) else (0.0, 0.0, 0.0)
            consume(normal, tuple(vertex_values[index:index + 3]))  # type: ignore[arg-type]
    if not triangle_count:
        raise EngineeringInspectionError("stl_contains_no_triangles")

    boundary_edges = sum(1 for count in edges.values() if count == 1)
    nonmanifold_edges = sum(1 for count in edges.values() if count > 2)
    topology_complete = triangle_count <= topology_limit and nonfinite == 0
    flags = [risk("unit_ambiguity", "warning", "STL does not encode units; dimensions require operator confirmation.")]
    if nonfinite:
        flags.append(risk("non_finite_coordinates", "high", "Non-finite triangle coordinates were detected.", nonfinite))
    if degenerate:
        flags.append(risk("degenerate_triangles", "warning", "Zero-area or near-zero-area triangles were detected.", degenerate))
    if duplicates:
        flags.append(risk("duplicate_triangles", "warning", "Duplicate triangle geometry was detected in the bounded topology pass.", duplicates))
    if boundary_edges:
        flags.append(risk("boundary_edges_or_holes", "warning", "Boundary edges indicate openings or holes in the bounded topology pass.", boundary_edges))
    if nonmanifold_edges:
        flags.append(risk("nonmanifold_edges", "high", "Edges shared by more than two triangles were detected.", nonmanifold_edges))
    if zero_normals or normal_mismatch:
        flags.append(risk("normal_warnings", "warning", "Stored normals were absent, zero, or inconsistent with triangle winding.", zero_normals + normal_mismatch))
    if not topology_complete:
        flags.append(risk("topology_analysis_bounded", "info", "Topology checks were bounded and do not cover every triangle."))
    return {
        "format_variant": encoding,
        "triangle_count": triangle_count,
        "bounding_box": bounds_payload(bounds),
        "surface_area": round(surface_area, 9),
        "topology_analysis_complete": topology_complete,
        "watertight_observation": bool(topology_complete and boundary_edges == 0 and nonmanifold_edges == 0),
        "boundary_edge_count": boundary_edges,
        "nonmanifold_edge_count": nonmanifold_edges,
        "degenerate_triangle_count": degenerate,
        "duplicate_triangle_count": duplicates,
        "non_finite_coordinate_count": nonfinite,
        "normal_warning_count": zero_normals + normal_mismatch,
        "unit_state": "ambiguous_not_encoded",
        "manufacturing_verdict": "not_provided",
        "_preview_segments": preview_segments,
        "risk_flags": flags,
        "external_references": [],
        "magic_summary": f"STL {encoding}",
    }


def _mtl_texture_references(mtl_path: Path, *, source_path: Path, workspace_root: Path, text_limit: int) -> list[Any]:
    try:
        text = read_bounded_text(mtl_path, text_limit)
    except (OSError, EngineeringInspectionError):
        return []
    references = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2 and (parts[0].lower().startswith("map_") or parts[0].lower() in {"bump", "disp", "decal", "refl"}):
            references.append(classify_reference(parts[1], source_path=mtl_path, workspace_root=workspace_root, reference_kind="obj_texture"))
    return references


def _obj_report(path: Path, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    if path.stat().st_size > limits["max_text_bytes"]:
        raise EngineeringInspectionError("engineering_text_limit_exceeded")
    counts = Counter()
    bounds: list[list[float]] | None = None
    objects: set[str] = set()
    groups: set[str] = set()
    materials: set[str] = set()
    mtl_refs: list[str] = []
    malformed_vertices = 0
    nonfinite = 0
    preview_vertices: list[tuple[float, float, float]] = []
    preview_segments: list[list[list[float]]] = []
    max_vertices = limits["max_vertices"]
    max_lines = limits["max_lines"]
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_index, line in enumerate(stream, 1):
            if line_index > max_lines:
                raise EngineeringInspectionError("engineering_line_limit_exceeded")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            keyword = parts[0].lower()
            if keyword == "v":
                counts["vertices"] += 1
                if counts["vertices"] > max_vertices:
                    raise EngineeringInspectionError("obj_vertex_limit_exceeded")
                try:
                    point = tuple(float(value) for value in parts[1:4])
                except (ValueError, TypeError):
                    malformed_vertices += 1
                    continue
                if len(point) != 3 or not finite_point(point):
                    nonfinite += 1
                    continue
                bounds = update_bounds(bounds, point)  # type: ignore[arg-type]
                if len(preview_vertices) < limits["max_preview_segments"] * 4:
                    preview_vertices.append(point)  # type: ignore[arg-type]
            elif keyword == "vt":
                counts["texture_coordinates"] += 1
            elif keyword == "vn":
                counts["normals"] += 1
            elif keyword == "f":
                counts["faces"] += 1
                indices: list[int] = []
                for token in parts[1:]:
                    try:
                        raw_index = int(token.split("/", 1)[0])
                        index = raw_index - 1 if raw_index > 0 else len(preview_vertices) + raw_index
                        if 0 <= index < len(preview_vertices):
                            indices.append(index)
                    except ValueError:
                        continue
                for offset in range(len(indices)):
                    if len(preview_segments) >= limits["max_preview_segments"]:
                        break
                    start = preview_vertices[indices[offset]]
                    end = preview_vertices[indices[(offset + 1) % len(indices)]]
                    preview_segments.append([[start[0], start[1]], [end[0], end[1]]])
            elif keyword == "o" and len(parts) > 1:
                objects.add(" ".join(parts[1:])[:240])
            elif keyword == "g" and len(parts) > 1:
                groups.add(" ".join(parts[1:])[:240])
            elif keyword == "usemtl" and len(parts) > 1:
                materials.add(" ".join(parts[1:])[:240])
            elif keyword == "mtllib" and len(parts) > 1:
                mtl_refs.extend(parts[1:])
    references = [classify_reference(ref, source_path=path, workspace_root=workspace_root, reference_kind="obj_mtl") for ref in mtl_refs]
    for reference, raw in zip(references, mtl_refs):
        if reference.resolution_state == "inside_workspace":
            candidate = (path.parent / raw).resolve(strict=False)
            references.extend(_mtl_texture_references(candidate, source_path=path, workspace_root=workspace_root, text_limit=min(limits["max_text_bytes"], 4 * 1024 * 1024)))
    references = references[: limits["max_external_references"]]
    flags = []
    blocked_refs = sum(1 for ref in references if ref.resolution_state.startswith("blocked_"))
    missing_refs = sum(1 for ref in references if ref.resolution_state == "missing")
    if blocked_refs:
        flags.append(risk("blocked_external_references", "high", "Absolute, traversal, remote, package, or symlink references were not followed.", blocked_refs))
    if missing_refs:
        flags.append(risk("missing_external_references", "warning", "Referenced local material or texture files were not found.", missing_refs))
    if malformed_vertices or nonfinite:
        flags.append(risk("invalid_vertices", "high", "Malformed or non-finite vertex coordinates were detected.", malformed_vertices + nonfinite))
    if not counts["faces"]:
        flags.append(risk("no_faces", "warning", "OBJ contains no face records."))
    return {
        "vertex_count": counts["vertices"],
        "face_count": counts["faces"],
        "normal_count": counts["normals"],
        "texture_coordinate_count": counts["texture_coordinates"],
        "object_count": len(objects),
        "group_count": len(groups),
        "material_count": len(materials),
        "object_names": sorted(objects)[: limits["max_names_in_response"]],
        "group_names": sorted(groups)[: limits["max_names_in_response"]],
        "material_names": sorted(materials)[: limits["max_names_in_response"]],
        "bounding_box": bounds_payload(bounds),
        "_preview_segments": preview_segments,
        "risk_flags": flags,
        "external_references": references,
        "magic_summary": "Wavefront OBJ text",
    }


def _dae_report(path: Path, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    root = parse_defused_xml(path, limits["max_xml_bytes"])
    if local_name(root.tag) != "collada":
        raise EngineeringInspectionError("dae_root_not_collada")
    counts = Counter(local_name(element.tag) for element in root.iter())
    unit_name = None
    unit_meter = None
    references = []
    scene_nodes = 0
    for element in root.iter():
        name = local_name(element.tag)
        if name == "unit":
            unit_name = element.attrib.get("name")
            unit_meter = element.attrib.get("meter")
        elif name == "node":
            scene_nodes += 1
        elif name == "init_from" and element.text and element.text.strip():
            references.append(classify_reference(element.text.strip(), source_path=path, workspace_root=workspace_root, reference_kind="dae_image"))
    references = references[: limits["max_external_references"]]
    flags = []
    blocked = sum(1 for ref in references if ref.resolution_state.startswith("blocked_"))
    missing = sum(1 for ref in references if ref.resolution_state == "missing")
    if blocked:
        flags.append(risk("blocked_external_references", "high", "Remote, absolute, traversal, or symlink COLLADA references were not followed.", blocked))
    if missing:
        flags.append(risk("missing_external_references", "warning", "Referenced local COLLADA assets were not found.", missing))
    return {
        "collada_version": root.attrib.get("version"),
        "asset_unit_name": unit_name,
        "asset_unit_meter": unit_meter,
        "geometry_count": counts["geometry"],
        "material_count": counts["material"],
        "image_count": counts["image"],
        "scene_node_count": scene_nodes,
        "animation_present": counts["animation"] > 0,
        "skinning_present": counts["skin"] > 0 or counts["controller"] > 0,
        "robot_dependency_compatible": True,
        "risk_flags": flags,
        "external_references": references,
        "magic_summary": f"COLLADA XML {root.attrib.get('version') or 'unknown version'}",
    }


def inspect_geometry(path: Path, *, type_id: str, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    if type_id == "stl":
        return _stl_report(path, limits)
    if type_id == "obj":
        return _obj_report(path, workspace_root, limits)
    if type_id == "dae":
        return _dae_report(path, workspace_root, limits)
    raise EngineeringInspectionError("unsupported_geometry_format")


__all__ = ("inspect_geometry",)
