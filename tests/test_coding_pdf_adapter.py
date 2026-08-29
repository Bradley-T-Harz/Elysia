from __future__ import annotations

from pathlib import Path

from app.api.coding_document_adapter_service import extract_document_preview


def test_pdf_preview_extracts_page_text(tmp_path: Path):
    import fitz

    path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "PDF adapter smoke text")
    document.save(path)
    document.close()

    preview = extract_document_preview(path)

    assert preview.status == "completed"
    assert "PDF adapter smoke text" in preview.text_preview
    assert preview.metadata["page_count"] == 1


def test_pdf_preview_inspects_form_fields(tmp_path: Path):
    import fitz

    path = tmp_path / "form.pdf"
    document = fitz.open()
    page = document.new_page()
    text_widget = fitz.Widget()
    text_widget.field_name = "full_name"
    text_widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    text_widget.rect = fitz.Rect(72, 72, 260, 94)
    text_widget.field_value = ""
    page.add_widget(text_widget)
    checkbox = fitz.Widget()
    checkbox.field_name = "agree"
    checkbox.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    checkbox.rect = fitz.Rect(72, 112, 90, 130)
    checkbox.field_value = False
    page.add_widget(checkbox)
    choice = fitz.Widget()
    choice.field_name = "color"
    choice.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
    choice.rect = fitz.Rect(72, 150, 220, 174)
    choice.choice_values = ["red", "green"]
    choice.field_value = "red"
    page.add_widget(choice)
    document.save(path)
    document.close()

    preview = extract_document_preview(path)
    form_fields = [item for item in preview.outline if item.get("kind") == "form_field"]

    assert preview.metadata["form_field_count"] == 3
    assert {field["name"] for field in form_fields} == {"full_name", "agree", "color"}
    assert any(field["field_type"] == "text" for field in form_fields)
    assert any(field["field_type"] == "checkbox" for field in form_fields)
    assert any(field["field_type"] == "combobox" and field["options"] == ["red", "green"] for field in form_fields)
