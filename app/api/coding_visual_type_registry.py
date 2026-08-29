"""Canonical registry for governed visual file stewardship."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingVisualTypeDescriptor:
    type_id: str
    label: str
    extensions: tuple[str, ...]
    mime: str
    category: str
    adapter: str
    readable: bool = True
    previewable: bool = True
    ocr_capable: bool = True
    visual_analysis_capable: bool = True
    metadata_editable: bool = True
    pixel_editable: bool = True
    exportable: bool = True
    animated: bool = False
    vector: bool = False
    exif_privacy_risk: bool = False
    svg_security_risk: bool = False
    stable_operations: tuple[str, ...] = ()
    blocked_operations: tuple[str, ...] = ()
    risk: str = "medium"
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["capabilities"] = {
            "readable": self.readable,
            "previewable": self.previewable,
            "ocr_capable": self.ocr_capable,
            "visual_analysis_capable": self.visual_analysis_capable,
            "metadata_editable": self.metadata_editable,
            "pixel_editable": self.pixel_editable,
            "exportable": self.exportable,
            "stable_operations": list(self.stable_operations),
            "blocked_operations": list(self.blocked_operations),
        }
        payload["risk_flags"] = {
            "may_contain_exif": self.exif_privacy_risk,
            "may_contain_gps": self.exif_privacy_risk,
            "may_be_animated": self.animated,
            "svg_security_risk": self.svg_security_risk,
        }
        return payload


RASTER_OPERATIONS = (
    "resize",
    "crop",
    "rotate",
    "flip",
    "transpose",
    "convert_format",
    "strip_exif",
    "strip_gps",
    "normalize_orientation",
    "optimize",
    "extract_frame",
    "make_thumbnail",
    "redact_rectangles",
    "blur_rectangles",
    "draw_rectangle",
    "add_text_overlay",
    "set_dpi",
)

SVG_OPERATIONS = (
    "sanitize_svg",
    "rasterize_svg_png",
    "edit_text",
    "set_dimensions",
    "set_viewbox",
    "change_explicit_fill",
    "remove_unsafe_elements",
    "remove_external_references",
)

SUPPORTED_VISUAL_TYPES: tuple[CodingVisualTypeDescriptor, ...] = (
    CodingVisualTypeDescriptor("png_image", "PNG image", (".png",), "image/png", "raster_image", "image", exif_privacy_risk=True, stable_operations=RASTER_OPERATIONS),
    CodingVisualTypeDescriptor("jpeg_image", "JPEG image", (".jpg", ".jpeg"), "image/jpeg", "raster_image", "image", exif_privacy_risk=True, stable_operations=RASTER_OPERATIONS),
    CodingVisualTypeDescriptor("webp_image", "WebP image", (".webp",), "image/webp", "raster_image", "image", animated=True, exif_privacy_risk=True, stable_operations=RASTER_OPERATIONS),
    CodingVisualTypeDescriptor("gif_image", "GIF image", (".gif",), "image/gif", "animated_image", "image", animated=True, metadata_editable=False, stable_operations=RASTER_OPERATIONS),
    CodingVisualTypeDescriptor("bmp_image", "BMP image", (".bmp",), "image/bmp", "raster_image", "image", metadata_editable=False, stable_operations=RASTER_OPERATIONS),
    CodingVisualTypeDescriptor("tiff_image", "TIFF image", (".tif", ".tiff"), "image/tiff", "raster_image", "image", exif_privacy_risk=True, stable_operations=RASTER_OPERATIONS, notes=("If CRS/geospatial tags are present, use data/raster stewardship for geospatial operations.",)),
    CodingVisualTypeDescriptor("svg_vector_image", "SVG vector image", (".svg",), "image/svg+xml", "vector_image", "svg", ocr_capable=False, metadata_editable=True, pixel_editable=False, vector=True, svg_security_risk=True, stable_operations=SVG_OPERATIONS, blocked_operations=("render_unsanitized_svg",), risk="high", notes=("SVG is parsed with XML safety checks; scripts, event handlers, and external references are removed before rendering.",)),
)

SUPPORTED_VISUAL_EXTENSIONS = tuple(
    sorted({extension for descriptor in SUPPORTED_VISUAL_TYPES for extension in descriptor.extensions})
)

UNKNOWN_VISUAL = CodingVisualTypeDescriptor("visual_unsupported", "Unsupported visual file", (), "application/octet-stream", "unsupported", "blocked", readable=False, previewable=False, ocr_capable=False, visual_analysis_capable=False, metadata_editable=False, pixel_editable=False, exportable=False, risk="blocked")


def detect_visual_type(path: Path | str) -> CodingVisualTypeDescriptor:
    suffix = Path(str(path)).suffix.lower()
    for descriptor in SUPPORTED_VISUAL_TYPES:
        if suffix in descriptor.extensions:
            return descriptor
    return UNKNOWN_VISUAL


def is_supported_visual_path(path: Path | str) -> bool:
    return detect_visual_type(path).adapter != "blocked"


def visual_registry_payload() -> list[dict[str, object]]:
    return [descriptor.to_payload() for descriptor in SUPPORTED_VISUAL_TYPES]


__all__ = (
    "CodingVisualTypeDescriptor",
    "SUPPORTED_VISUAL_EXTENSIONS",
    "SUPPORTED_VISUAL_TYPES",
    "UNKNOWN_VISUAL",
    "detect_visual_type",
    "is_supported_visual_path",
    "visual_registry_payload",
)
