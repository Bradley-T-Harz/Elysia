"""ODF adapter for bounded extraction from ODT/ODS/ODP containers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.api.coding_document_type_registry import CodingDocumentTypeDescriptor


def extract_odf_preview(
    path: Path,
    *,
    descriptor: CodingDocumentTypeDescriptor,
    max_chars: int,
    max_tables: int,
    max_rows: int,
) -> dict[str, Any]:
    from odf import table, text
    from odf.opendocument import load
    from odf.teletype import extractText

    document = load(str(path))
    metadata = {
        "family": descriptor.family,
        "document_type_id": descriptor.type_id,
    }
    outline: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    text_parts: list[str] = []

    paragraphs = document.getElementsByType(text.P)
    headings = document.getElementsByType(text.H)
    for index, heading in enumerate(headings[:100], start=1):
        heading_text = extractText(heading)
        if heading_text:
            outline.append({"kind": "heading", "heading": index, "text": heading_text[:300]})
    for index, paragraph in enumerate(paragraphs, start=1):
        paragraph_text = extractText(paragraph)
        if paragraph_text and len("\n".join(text_parts)) < max_chars:
            text_parts.append(f"[paragraph {index}] {paragraph_text}")
            provenance.append({"kind": "paragraph", "paragraph": index, "chars": len(paragraph_text)})

    tables: list[dict[str, Any]] = []
    for table_index, item in enumerate(document.getElementsByType(table.Table)[:max_tables], start=1):
        rows: list[list[str]] = []
        for row in item.getElementsByType(table.TableRow)[:max_rows]:
            rendered_row: list[str] = []
            for cell in row.getElementsByType(table.TableCell)[:12]:
                rendered_row.append(extractText(cell)[:500])
            rows.append(rendered_row)
        tables.append({"kind": "table", "table": table_index, "rows": rows, "row_count_previewed": len(rows)})
        provenance.append({"kind": "table", "table": table_index, "rows_previewed": len(rows)})

    metadata["paragraph_count"] = len(paragraphs)
    metadata["table_count"] = len(document.getElementsByType(table.Table))
    return {
        "status": "completed",
        "metadata": metadata,
        "text_preview": "\n".join(text_parts)[:max_chars],
        "tables": tables,
        "outline": outline,
        "provenance": provenance,
        "warnings": ["ODF support is extraction/export oriented; stable in-place edits are refused in this pass."],
    }


__all__ = ("extract_odf_preview",)
