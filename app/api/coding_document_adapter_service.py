"""Adapter router for governed document inspection and extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.api.coding_document_safety_service import CodingDocumentSafetyResult, check_document_safety
from app.api.coding_document_type_registry import CodingDocumentTypeDescriptor, detect_document_type
from app.api.coding_docx_adapter import extract_docx_preview
from app.api.coding_odf_adapter import extract_odf_preview
from app.api.coding_pdf_adapter import extract_pdf_preview
from app.api.coding_pptx_adapter import extract_pptx_preview
from app.api.coding_secret_scan_service import redact_secret_lines, scan_preview_for_secrets
from app.api.coding_xlsx_adapter import extract_xlsx_preview


@dataclass(frozen=True)
class CodingDocumentPreview:
    descriptor: CodingDocumentTypeDescriptor
    safety: CodingDocumentSafetyResult
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)
    text_preview: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    outline: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)
    secret_scan_findings: list[str] = field(default_factory=list)
    blocked_reason: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "document_type_id": self.descriptor.type_id,
            "document_label": self.descriptor.label,
            "document_family": self.descriptor.family,
            "adapter": self.descriptor.adapter,
            "status": self.status,
            "metadata": self.metadata,
            "safety": self.safety.to_payload(),
            "outline_count": len(self.outline),
            "table_count": len(self.tables),
            "provenance_count": len(self.provenance),
            "warnings": self.warnings,
            "redactions": self.redactions,
        }


def _redact_preview(text: str) -> tuple[str, list[str], list[str]]:
    findings = scan_preview_for_secrets(text)
    if not findings:
        return text, [], []
    return redact_secret_lines(text), findings, ["Potential secret-like values were redacted from the extracted preview."]


def extract_document_preview(
    path: Path,
    *,
    max_chars: int = 12000,
    max_tables: int = 8,
    max_rows: int = 20,
) -> CodingDocumentPreview:
    descriptor = detect_document_type(path)
    safety = check_document_safety(path, descriptor)
    if not safety.allowed:
        return CodingDocumentPreview(
            descriptor=descriptor,
            safety=safety,
            status="blocked",
            warnings=list(descriptor.notes) + list(safety.warnings),
            blocked_reason=safety.blocked_reason,
        )

    try:
        if descriptor.adapter == "pdf":
            payload = extract_pdf_preview(path, max_chars=max_chars, max_tables=max_tables, max_rows=max_rows)
        elif descriptor.adapter == "docx":
            payload = extract_docx_preview(path, max_chars=max_chars, max_tables=max_tables, max_rows=max_rows)
        elif descriptor.adapter == "xlsx":
            payload = extract_xlsx_preview(path, max_chars=max_chars, max_tables=max_tables, max_rows=max_rows)
        elif descriptor.adapter == "pptx":
            payload = extract_pptx_preview(path, max_chars=max_chars, max_tables=max_tables, max_rows=max_rows)
        elif descriptor.adapter == "odf":
            payload = extract_odf_preview(path, descriptor=descriptor, max_chars=max_chars, max_tables=max_tables, max_rows=max_rows)
        else:
            return CodingDocumentPreview(
                descriptor=descriptor,
                safety=safety,
                status="blocked",
                warnings=list(descriptor.notes),
                blocked_reason="unsupported_document_adapter",
            )
    except Exception as exc:
        return CodingDocumentPreview(
            descriptor=descriptor,
            safety=safety,
            status="blocked",
            warnings=list(descriptor.notes),
            blocked_reason=f"document_parse_failed:{exc.__class__.__name__}",
        )

    text_preview = str(payload.get("text_preview") or "")
    redacted_text, findings, redactions = _redact_preview(text_preview)
    warnings = list(descriptor.notes) + list(payload.get("warnings") or [])
    if descriptor.formula_risk:
        warnings.append("Spreadsheet formulas are treated as inert text and are never executed.")
    if descriptor.embedded_content_risk:
        warnings.append("Embedded content, links, media, scripts, and macros are not executed.")

    return CodingDocumentPreview(
        descriptor=descriptor,
        safety=safety,
        status=str(payload.get("status") or "completed"),
        metadata=dict(payload.get("metadata") or {}),
        text_preview=redacted_text[:max_chars],
        tables=list(payload.get("tables") or [])[:max_tables],
        outline=list(payload.get("outline") or []),
        provenance=list(payload.get("provenance") or []),
        warnings=warnings,
        redactions=redactions,
        secret_scan_findings=findings,
    )


def inspect_document(path: Path) -> CodingDocumentPreview:
    return extract_document_preview(path, max_chars=2000, max_tables=3, max_rows=8)


__all__ = ("CodingDocumentPreview", "extract_document_preview", "inspect_document")
