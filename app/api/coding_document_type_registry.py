"""Canonical document type registry for governed Codev document stewardship."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingDocumentTypeDescriptor:
    type_id: str
    label: str
    extension: str
    family: str
    adapter: str
    readable: bool = True
    extractable: bool = True
    exportable: bool = True
    editable: bool = False
    stable_edit_operations: tuple[str, ...] = ()
    binary_container: bool = True
    macro_risk: bool = False
    legacy_risk: bool = False
    formula_risk: bool = False
    embedded_content_risk: bool = False
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


SUPPORTED_DOCUMENT_TYPES: tuple[CodingDocumentTypeDescriptor, ...] = (
    CodingDocumentTypeDescriptor(
        "pdf_document",
        "PDF document",
        ".pdf",
        "pdf",
        "pdf",
        editable=True,
        stable_edit_operations=(
            "extract_pages",
            "rotate_pages",
            "reorder_pages",
            "merge_pdf",
            "update_metadata",
            "add_text_stamp",
            "add_highlight",
            "redact_rectangles",
            "fill_form_fields",
        ),
        embedded_content_risk=True,
        notes=(
            "PDF support includes extraction, export, page provenance, and approved derived-copy PDF operations. "
            "Arbitrary inline sentence editing remains unstable and is redirected to safer alternatives.",
        ),
    ),
    CodingDocumentTypeDescriptor(
        "docx_document",
        "Word document",
        ".docx",
        "word",
        "docx",
        editable=True,
        stable_edit_operations=("append_paragraph", "replace_paragraph"),
        embedded_content_risk=True,
        notes=("DOCX edits are limited to stable paragraph operations with approval.",),
    ),
    CodingDocumentTypeDescriptor(
        "xlsx_workbook",
        "Excel workbook",
        ".xlsx",
        "spreadsheet",
        "xlsx",
        editable=True,
        stable_edit_operations=("set_cell", "append_row", "create_sheet", "rename_sheet"),
        formula_risk=True,
        embedded_content_risk=True,
        notes=("Formulas are inspected as text and never executed.",),
    ),
    CodingDocumentTypeDescriptor(
        "pptx_presentation",
        "PowerPoint presentation",
        ".pptx",
        "presentation",
        "pptx",
        editable=True,
        stable_edit_operations=("replace_text", "append_slide"),
        embedded_content_risk=True,
        notes=("PPTX edits are limited to text replacement and simple slide append operations.",),
    ),
    CodingDocumentTypeDescriptor(
        "odt_document",
        "OpenDocument text",
        ".odt",
        "word",
        "odf",
        editable=False,
        embedded_content_risk=True,
        notes=("ODT support is extraction/export oriented in this pass.",),
    ),
    CodingDocumentTypeDescriptor(
        "ods_spreadsheet",
        "OpenDocument spreadsheet",
        ".ods",
        "spreadsheet",
        "odf",
        editable=False,
        formula_risk=True,
        embedded_content_risk=True,
        notes=("ODS support is extraction/export oriented; formulas are never executed.",),
    ),
    CodingDocumentTypeDescriptor(
        "odp_presentation",
        "OpenDocument presentation",
        ".odp",
        "presentation",
        "odf",
        editable=False,
        embedded_content_risk=True,
        notes=("ODP support is extraction/export oriented in this pass.",),
    ),
)

MACRO_ENABLED_EXTENSIONS = {
    ".docm",
    ".xlsm",
    ".pptm",
    ".dotm",
    ".xltm",
    ".potm",
}
LEGACY_OFFICE_EXTENSIONS = {".doc", ".xls", ".ppt"}
SUPPORTED_DOCUMENT_EXTENSIONS = {descriptor.extension for descriptor in SUPPORTED_DOCUMENT_TYPES}
DOCUMENT_EXTENSIONS = SUPPORTED_DOCUMENT_EXTENSIONS | MACRO_ENABLED_EXTENSIONS | LEGACY_OFFICE_EXTENSIONS

MACRO_ENABLED_UNSUPPORTED = CodingDocumentTypeDescriptor(
    "macro_enabled_unsupported",
    "Macro-enabled Office document",
    "",
    "blocked",
    "blocked",
    readable=False,
    extractable=False,
    exportable=False,
    editable=False,
    macro_risk=True,
    notes=("Macro-enabled document variants are blocked; macros are never inspected or executed.",),
)
LEGACY_OFFICE_UNSUPPORTED = CodingDocumentTypeDescriptor(
    "legacy_office_unsupported",
    "Legacy Office document",
    "",
    "blocked",
    "blocked",
    readable=False,
    extractable=False,
    exportable=False,
    editable=False,
    legacy_risk=True,
    notes=("Legacy .doc/.xls/.ppt formats are unsupported except for refusal metadata.",),
)
UNKNOWN_DOCUMENT_UNSUPPORTED = CodingDocumentTypeDescriptor(
    "document_unsupported",
    "Unsupported document",
    "",
    "blocked",
    "blocked",
    readable=False,
    extractable=False,
    exportable=False,
    editable=False,
    notes=("This document format is not supported by Elysia document stewardship.",),
)


def detect_document_type(path: Path | str) -> CodingDocumentTypeDescriptor:
    suffix = Path(str(path)).suffix.lower()
    if suffix in MACRO_ENABLED_EXTENSIONS:
        return MACRO_ENABLED_UNSUPPORTED
    if suffix in LEGACY_OFFICE_EXTENSIONS:
        return LEGACY_OFFICE_UNSUPPORTED
    for descriptor in SUPPORTED_DOCUMENT_TYPES:
        if suffix == descriptor.extension:
            return descriptor
    return UNKNOWN_DOCUMENT_UNSUPPORTED


def is_supported_document_path(path: Path | str) -> bool:
    return Path(str(path)).suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS


def document_registry_payload() -> list[dict[str, object]]:
    return [descriptor.to_payload() for descriptor in SUPPORTED_DOCUMENT_TYPES]


__all__ = (
    "DOCUMENT_EXTENSIONS",
    "LEGACY_OFFICE_EXTENSIONS",
    "MACRO_ENABLED_EXTENSIONS",
    "SUPPORTED_DOCUMENT_EXTENSIONS",
    "SUPPORTED_DOCUMENT_TYPES",
    "CodingDocumentTypeDescriptor",
    "detect_document_type",
    "document_registry_payload",
    "is_supported_document_path",
)
