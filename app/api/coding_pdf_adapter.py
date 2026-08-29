"""PDF adapter for bounded extraction and PDF metadata surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _metadata_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:500]


def discover_pdf_form_fields(path: Path, *, max_fields: int = 100) -> list[dict[str, Any]]:
    from app.api.coding_pdf_worker_client import run_pdf_worker

    payload = run_pdf_worker(
        {"action": "discover_form_fields", "source_path": str(path), "max_fields": max_fields},
        timeout_seconds=20,
    )
    fields = payload.get("fields")
    return [dict(field) for field in fields if isinstance(field, dict)] if isinstance(fields, list) else []


def extract_pdf_preview(path: Path, *, max_chars: int, max_tables: int, max_rows: int) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    outline_items: list[dict[str, Any]] = []
    form_fields: list[dict[str, Any]] = []
    metadata = {
        "page_count": page_count,
        "title": _metadata_value((reader.metadata or {}).get("/Title")) if reader.metadata else None,
        "author": _metadata_value((reader.metadata or {}).get("/Author")) if reader.metadata else None,
        "producer": _metadata_value((reader.metadata or {}).get("/Producer")) if reader.metadata else None,
    }
    try:
        raw_outline = getattr(reader, "outline", []) or []

        def collect_outline(items: list[object], depth: int = 0) -> None:
            for item in items:
                if isinstance(item, list):
                    collect_outline(item, depth + 1)
                    continue
                title = _metadata_value(getattr(item, "title", None) or str(item))
                if not title:
                    continue
                page_number = None
                try:
                    page_number = reader.get_destination_page_number(item) + 1
                except Exception:
                    page_number = None
                outline_items.append(
                    {
                        "kind": "bookmark",
                        "title": title,
                        "page": page_number,
                        "depth": depth,
                    }
                )

        collect_outline(list(raw_outline))
    except Exception:
        outline_items = []
    try:
        form_fields = discover_pdf_form_fields(path, max_fields=100)
    except Exception:
        try:
            fields = reader.get_fields() or {}
            for name, field in list(fields.items())[:50]:
                form_fields.append(
                    {
                        "kind": "form_field",
                        "name": _metadata_value(name),
                        "field_type": _metadata_value(field.get("/FT")),
                        "value_present": field.get("/V") is not None,
                    }
                )
        except Exception:
            form_fields = []
    if form_fields:
        metadata["form_field_count"] = len(form_fields)

    text_parts: list[str] = []
    provenance: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    warnings: list[str] = []

    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            for page_index, page in enumerate(pdf.pages[: min(page_count, 8)], start=1):
                if len("\n".join(text_parts)) < max_chars:
                    page_text = page.extract_text() or ""
                    if page_text:
                        snippet = page_text[: max(0, max_chars - len("\n".join(text_parts)))]
                        text_parts.append(f"[page {page_index}]\n{snippet}")
                        provenance.append({"kind": "page", "page": page_index, "chars": len(snippet)})
                if len(tables) < max_tables:
                    for table_index, table in enumerate(page.extract_tables() or [], start=1):
                        if len(tables) >= max_tables:
                            break
                        rows = [[cell or "" for cell in row] for row in table[:max_rows]]
                        tables.append(
                            {
                                "kind": "table",
                                "page": page_index,
                                "table": table_index,
                                "rows": rows,
                                "row_count_previewed": len(rows),
                            }
                        )
    except Exception as exc:
        warnings.append(f"pdfplumber extraction degraded: {exc.__class__.__name__}")
        for page_index, page in enumerate(reader.pages[: min(page_count, 8)], start=1):
            if len("\n".join(text_parts)) >= max_chars:
                break
            page_text = page.extract_text() or ""
            if page_text:
                snippet = page_text[: max(0, max_chars - len("\n".join(text_parts)))]
                text_parts.append(f"[page {page_index}]\n{snippet}")
                provenance.append({"kind": "page", "page": page_index, "chars": len(snippet)})

    return {
        "status": "completed",
        "metadata": metadata,
        "text_preview": "\n\n".join(text_parts)[:max_chars],
        "tables": tables,
        "outline": outline_items[:100] + form_fields[:50],
        "provenance": provenance,
        "warnings": warnings,
    }


__all__ = ("discover_pdf_form_fields", "extract_pdf_preview")
