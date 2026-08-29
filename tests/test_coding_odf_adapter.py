from __future__ import annotations

from pathlib import Path

from app.api.coding_document_adapter_service import extract_document_preview


def test_odt_preview_extracts_text(tmp_path: Path):
    from odf.opendocument import OpenDocumentText
    from odf.text import P

    path = tmp_path / "sample.odt"
    document = OpenDocumentText()
    document.text.addElement(P(text="ODT adapter smoke text"))
    document.save(str(path))

    preview = extract_document_preview(path)

    assert preview.status == "completed"
    assert "ODT adapter smoke text" in preview.text_preview


def test_ods_preview_extracts_table(tmp_path: Path):
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    path = tmp_path / "sample.ods"
    document = OpenDocumentSpreadsheet()
    sheet = Table(name="Data")
    row = TableRow()
    cell = TableCell()
    cell.addElement(P(text="ODS adapter cell"))
    row.addElement(cell)
    sheet.addElement(row)
    document.spreadsheet.addElement(sheet)
    document.save(str(path))

    preview = extract_document_preview(path)

    assert preview.status == "completed"
    assert preview.tables
    assert "ODS adapter cell" in repr(preview.tables)
