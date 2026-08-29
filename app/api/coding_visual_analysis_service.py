"""Deterministic local visual analysis."""

from __future__ import annotations

from pathlib import Path

from app.api.coding_image_adapter import deterministic_visual_analysis
from app.api.coding_svg_adapter import inspect_svg
from app.api.coding_visual_model_service import semantic_vision_health
from app.api.coding_visual_type_registry import detect_visual_type


def analyze_visual(path: Path, *, include_semantic_provider: bool = False) -> dict[str, object]:
    descriptor = detect_visual_type(path)
    if descriptor.adapter == "svg":
        svg = inspect_svg(path)
        return {
            "status": svg["status"],
            "analysis": {
                "analysis_kind": "deterministic_local_svg",
                "text_node_count": len(svg.get("metadata", {}).get("text_nodes", [])),
                "unsafe_svg_content": svg.get("risk_flags", {}).get("unsafe_svg_content", False),
                "external_references_count": svg.get("metadata", {}).get("external_references_count", 0),
            },
            "semantic_provider": semantic_vision_health() if include_semantic_provider else None,
            "warnings": svg.get("warnings", []),
        }
    analysis = deterministic_visual_analysis(path)
    return {
        "status": "completed",
        "analysis": analysis,
        "semantic_provider": semantic_vision_health() if include_semantic_provider else None,
        "warnings": ["Deterministic analysis is local and does not upload pixels. Semantic vision provider is local-only and disabled unless configured."],
    }


__all__ = ("analyze_visual",)
