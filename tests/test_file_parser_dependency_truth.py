from pathlib import Path

from app.api.file_text_extractors import extract_file_text
from app.api.schemas.files import FileKind


def test_invalid_pdf_returns_safe_parser_error_not_exception(tmp_path: Path):
    pdf_path = tmp_path / "pretend.pdf"
    pdf_path.write_bytes(b"%PDF-pretend but not a valid real PDF")

    result = extract_file_text(pdf_path, FileKind.PDF)

    assert result.ok is False
    assert result.parser_used in {
        "pdf_pypdf_text_parser",
        "pdf_pdfplumber_text_parser",
        "pdf_local_text_parser_failed",
        "pdf_parser_missing",
    }
    assert result.errors
    rendered_errors = " ".join(result.errors)
    assert (
        "selected file" in rendered_errors
        or "requires one local Python package" in rendered_errors
        or "PDF could not be parsed locally" in rendered_errors
        or "pypdf failed" in rendered_errors
        or "pdfplumber failed" in rendered_errors
    )
    assert str(pdf_path) not in rendered_errors


def test_invalid_docx_returns_safe_parser_error_not_exception(tmp_path: Path):
    docx_path = tmp_path / "pretend.docx"
    docx_path.write_bytes(b"not a real docx archive")

    result = extract_file_text(docx_path, FileKind.DOCX)

    assert result.ok is False
    assert result.parser_used in {
        "docx_python_docx_text_parser",
        "docx_python_docx_parser_missing",
    }
    assert result.errors
    rendered_errors = " ".join(result.errors)
    assert "selected file" in rendered_errors or "requires the local Python package" in rendered_errors
    assert str(docx_path) not in rendered_errors
