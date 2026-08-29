"""SVG safety, inspection, sanitization, and rasterization."""

from __future__ import annotations

import base64
import io
from hashlib import sha256
from pathlib import Path
from typing import Any

import cairosvg
from defusedxml import ElementTree as DET

from app.api.coding_visual_safety_service import MAX_SVG_NODES, check_visual_safety
from app.api.coding_visual_type_registry import detect_visual_type


SVG_NS = "http://www.w3.org/2000/svg"
UNSAFE_ELEMENTS = {"script", "foreignObject", "iframe", "object", "embed", "audio", "video"}
REFERENCE_ATTRS = {"href", "{http://www.w3.org/1999/xlink}href", "src"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hash_bytes(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _tree_and_report(path: Path) -> tuple[Any, dict[str, Any]]:
    root = DET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    nodes = list(root.iter())
    scripts = []
    events = []
    external_refs = []
    data_refs = []
    for node in nodes:
        name = _local_name(str(node.tag))
        if name in UNSAFE_ELEMENTS:
            scripts.append(name)
        for attr, value in list(node.attrib.items()):
            attr_name = _local_name(str(attr))
            lowered = str(value).strip().lower()
            if attr_name.startswith("on"):
                events.append(attr_name)
            if attr in REFERENCE_ATTRS or attr_name in {"href", "src"}:
                if lowered.startswith(("http:", "https:", "//", "file:", "ftp:")):
                    external_refs.append(value)
                if lowered.startswith("data:"):
                    data_refs.append(value[:40])
    report = {
        "node_count": len(nodes),
        "unsafe_elements": sorted(set(scripts)),
        "event_handlers": sorted(set(events)),
        "external_references_count": len(external_refs),
        "data_uri_count": len(data_refs),
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "viewBox": root.attrib.get("viewBox"),
        "text_nodes": [text.strip() for text in root.itertext() if text and text.strip()][:50],
    }
    return root, report


def sanitize_svg_text(text: str) -> tuple[str, dict[str, Any]]:
    root = DET.fromstring(text)
    removed = {"elements": 0, "attributes": 0, "event_handlers": 0, "external_references": 0}
    for parent in list(root.iter()):
        for child in list(parent):
            if _local_name(str(child.tag)) in UNSAFE_ELEMENTS:
                parent.remove(child)
                removed["elements"] += 1
    for node in root.iter():
        for attr, value in list(node.attrib.items()):
            attr_name = _local_name(str(attr))
            lowered = str(value).strip().lower()
            if attr_name.startswith("on"):
                del node.attrib[attr]
                removed["attributes"] += 1
                removed["event_handlers"] += 1
            elif attr in REFERENCE_ATTRS or attr_name in {"href", "src"}:
                if lowered.startswith(("http:", "https:", "//", "file:", "ftp:", "data:")):
                    del node.attrib[attr]
                    removed["external_references"] += 1
    sanitized = DET.tostring(root, encoding="unicode")
    return sanitized, removed


def inspect_svg(path: Path) -> dict[str, Any]:
    descriptor = detect_visual_type(path)
    safety = check_visual_safety(path, descriptor)
    if not safety.allowed:
        return {"status": "blocked", "descriptor": descriptor.to_payload(), "blocked_reason": safety.blocked_reason, "metadata": {}, "preview": {}, "warnings": safety.warnings, "risk_flags": safety.risk_flags, "content_hash": None, "size_bytes": safety.size_bytes}
    try:
        _root, report = _tree_and_report(path)
        if report["node_count"] > MAX_SVG_NODES:
            return {"status": "blocked", "descriptor": descriptor.to_payload(), "blocked_reason": "svg_too_many_nodes", "metadata": report, "preview": {}, "warnings": safety.warnings, "risk_flags": safety.risk_flags, "content_hash": _hash_bytes(path), "size_bytes": safety.size_bytes}
        sanitized, removed = sanitize_svg_text(path.read_text(encoding="utf-8", errors="replace"))
        png = cairosvg.svg2png(bytestring=sanitized.encode("utf-8"), output_width=640, output_height=640)
        return {
            "status": "completed",
            "descriptor": descriptor.to_payload(),
            "content_hash": _hash_bytes(path),
            "size_bytes": safety.size_bytes,
            "metadata": report,
            "preview": {"thumbnail_data_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"), "thumbnail_format": "png", "sanitized_for_rendering": True},
            "svg_safety": {**report, "sanitizer_removed": removed},
            "warnings": safety.warnings + (["Unsafe SVG content was detected and removed from the render preview."] if any(removed.values()) else []),
            "risk_flags": {**safety.risk_flags, "unsafe_svg_content": bool(report["unsafe_elements"] or report["event_handlers"] or report["external_references_count"] or report["data_uri_count"])},
            "sanitized_preview": sanitized[:4000],
        }
    except Exception as exc:
        return {"status": "blocked", "descriptor": descriptor.to_payload(), "blocked_reason": f"svg_inspect_failed:{exc.__class__.__name__}", "metadata": {}, "preview": {}, "warnings": safety.warnings, "risk_flags": safety.risk_flags, "content_hash": None, "size_bytes": safety.size_bytes}


def rasterize_sanitized_svg_to_png(source: Path, target: Path) -> dict[str, Any]:
    sanitized, removed = sanitize_svg_text(source.read_text(encoding="utf-8", errors="replace"))
    target.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(bytestring=sanitized.encode("utf-8"), write_to=str(target))
    return {"target_path": target.name, "sanitizer_removed": removed, "format": "png"}


__all__ = ("inspect_svg", "rasterize_sanitized_svg_to_png", "sanitize_svg_text")
