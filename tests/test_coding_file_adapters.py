from __future__ import annotations

from app.api.coding_file_adapter_service import build_adapter_preview


def test_adapter_preview_returns_code_metadata_and_hashes(tmp_path):
    source = tmp_path / "fibonacci_bug.py"
    source.write_text("def fib(n):\n    return n\n", encoding="utf-8")

    preview = build_adapter_preview(source, max_bytes=4000, max_lines=100)

    assert preview.descriptor.type_id == "python_code"
    assert preview.text_preview is not None
    assert preview.text_preview.raw_byte_hash
    assert preview.text_preview.decoded_text_hash
    assert preview.parse_summary["safe_patch_style"] == "unified_diff_text_patch"


def test_structured_adapter_reports_invalid_json(tmp_path):
    source = tmp_path / "package.json"
    source.write_text('{"scripts": ', encoding="utf-8")

    preview = build_adapter_preview(source, max_bytes=4000, max_lines=100)

    assert preview.descriptor.type_id == "package_json"
    assert preview.parse_status == "invalid"
    assert "parser_error" in preview.parse_summary


def test_delimited_and_markdown_adapters_report_shape(tmp_path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("name,value\nalpha,1\n", encoding="utf-8")
    notes = tmp_path / "README.md"
    notes.write_text("# Title\n\n- [ ] task\n", encoding="utf-8")

    csv_preview = build_adapter_preview(csv_file, max_bytes=4000, max_lines=100)
    md_preview = build_adapter_preview(notes, max_bytes=4000, max_lines=100)

    assert csv_preview.parse_summary["column_names"] == ["name", "value"]
    assert md_preview.parse_summary["document_title"] == "Title"


def test_env_example_is_redacted_but_env_is_blocked(tmp_path):
    env = tmp_path / ".env"
    env.write_text("TOKEN=supersecretvalue\n", encoding="utf-8")
    example = tmp_path / ".env.example"
    example.write_text("TOKEN=replace_me_example\n", encoding="utf-8")

    env_preview = build_adapter_preview(env, max_bytes=4000, max_lines=100)
    example_preview = build_adapter_preview(example, max_bytes=4000, max_lines=100)

    assert env_preview.blocked_reason == "file_type_not_readable"
    assert example_preview.descriptor.type_id == "env_example"
    assert example_preview.secret_scan_findings
    assert "replace_me_example" not in (example_preview.content_preview or "")


def test_huge_text_is_blocked_before_full_read(tmp_path):
    source = tmp_path / "huge.txt"
    source.write_bytes(b"a" * 128)

    preview = build_adapter_preview(source, max_bytes=32, max_lines=10, max_file_bytes=64)

    assert preview.blocked_reason == "text_file_too_large"
    assert preview.parse_summary == {"size_bytes": 128, "max_file_bytes": 64}


def test_late_binary_content_is_blocked(tmp_path):
    source = tmp_path / "late.txt"
    source.write_bytes((b"a" * 5000) + b"\x00tail")

    preview = build_adapter_preview(source, max_bytes=6000, max_lines=10)

    assert preview.blocked_reason == "binary_or_unsupported_file"


def test_unknown_utf8_file_is_preview_only(tmp_path):
    source = tmp_path / "extensionless-custom"
    source.write_text("custom text\n", encoding="utf-8")

    preview = build_adapter_preview(source, max_bytes=4000, max_lines=100)

    assert preview.descriptor.type_id == "unknown_text"
    assert preview.descriptor.readable is True
    assert preview.descriptor.writable is False
    assert preview.descriptor.patchable is False
