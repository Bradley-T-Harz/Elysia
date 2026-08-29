from __future__ import annotations

from app.api.coding_document_type_registry import detect_document_type
from app.api.coding_file_type_registry import detect_file_type


def test_document_type_detection_matrix():
    expected = {
        "paper.pdf": "pdf_document",
        "brief.docx": "docx_document",
        "table.xlsx": "xlsx_workbook",
        "deck.pptx": "pptx_presentation",
        "notes.odt": "odt_document",
        "sheet.ods": "ods_spreadsheet",
        "slides.odp": "odp_presentation",
    }

    for filename, type_id in expected.items():
        assert detect_document_type(filename).type_id == type_id
        assert detect_file_type(filename).category == "document"
        assert detect_file_type(filename).patchable is False


def test_macro_and_legacy_documents_are_blocked():
    for filename in ["bad.docm", "bad.xlsm", "bad.pptm", "old.doc", "old.xls", "old.ppt"]:
        descriptor = detect_document_type(filename)
        assert descriptor.readable is False
        assert descriptor.extractable is False
        assert descriptor.editable is False
