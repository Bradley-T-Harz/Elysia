"""Local OCR service for visual stewardship."""

from __future__ import annotations

from pathlib import Path
from shutil import which

import pytesseract
from PIL import Image, ImageOps

from app.api.coding_secret_scan_service import redact_secret_lines, scan_preview_for_secrets
from app.api.coding_visual_safety_service import MAX_OCR_CHARS


def ocr_health() -> dict[str, object]:
    return {"available": bool(which("tesseract")), "engine": "tesseract", "local_only": True}


def run_local_ocr(path: Path, *, max_chars: int = MAX_OCR_CHARS) -> dict[str, object]:
    if not which("tesseract"):
        return {"status": "blocked", "blocked_reason": "tesseract_not_available", "text_preview": "", "redaction_count": 0, "warnings": ["Local Tesseract OCR engine is not available."]}
    with Image.open(path) as image:
        safe = ImageOps.exif_transpose(image.convert("RGB"))
        safe.thumbnail((1800, 1800))
        text = pytesseract.image_to_string(safe)
    bounded = text[:max_chars]
    redacted = redact_secret_lines(bounded)
    redactions = 1 if redacted != bounded or scan_preview_for_secrets(bounded) else 0
    warnings = ["OCR text can contain private data; full OCR text is not stored in audit by default."]
    if len(text) > len(bounded):
        warnings.append("OCR text was truncated to the configured bound.")
    return {"status": "completed", "text_preview": redacted, "characters_returned": len(redacted), "truncated": len(text) > len(bounded), "redaction_count": redactions, "warnings": warnings}


__all__ = ("ocr_health", "run_local_ocr")
