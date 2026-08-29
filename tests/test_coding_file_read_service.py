from __future__ import annotations

from hashlib import sha256

from app.api.coding_file_service import read_selected_file_preview
from app.api.schemas.coding_files import CodingFileReadPreviewRequest


def test_file_read_preview_requires_approval(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("print('hello')\n", encoding="utf-8")

    result = read_selected_file_preview(
        CodingFileReadPreviewRequest(workspace_root=str(tmp_path), file_path=str(source))
    )

    assert result.status == "approval_required"
    assert result.source_contents_included is False
    assert result.content_preview is None


def test_file_read_preview_returns_bounded_source_after_approval(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("print('hello')\n", encoding="utf-8")

    result = read_selected_file_preview(
        CodingFileReadPreviewRequest(
            workspace_root=str(tmp_path),
            file_path=str(source),
            approval_granted=True,
        )
    )

    assert result.status == "completed"
    assert result.relative_path == "app.py"
    assert result.file_type_id == "python_code"
    assert result.adapter == "code"
    assert result.capabilities.patchable is True
    assert result.risk_flags.secret_sensitive is False
    assert result.encoding == "utf-8"
    assert result.line_ending == "lf"
    assert result.byte_hash
    assert result.source_contents_included is True
    assert "print('hello')" in (result.content_preview or "")
    assert result.content_preview == "print('hello')\n"
    assert result.content_hash == sha256((result.content_preview or "").encode("utf-8")).hexdigest()
    assert str(tmp_path) not in result.to_payload().__repr__()


def test_file_read_preview_blocks_env_file_even_with_approval(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=secret\n", encoding="utf-8")

    result = read_selected_file_preview(
        CodingFileReadPreviewRequest(
            workspace_root=str(tmp_path),
            file_path=str(env_file),
            approval_granted=True,
        )
    )

    assert result.status == "blocked"
    assert result.file_type_id in {None, "blocked_secret_env"}
    assert result.source_contents_included is False
    assert result.content_preview is None


def test_file_read_preview_allows_env_example_with_redaction(tmp_path):
    env_file = tmp_path / ".env.example"
    env_file.write_text("TOKEN=replace_this_secret\nPUBLIC_URL=http://127.0.0.1\n", encoding="utf-8")

    result = read_selected_file_preview(
        CodingFileReadPreviewRequest(
            workspace_root=str(tmp_path),
            file_path=str(env_file),
            approval_granted=True,
        )
    )

    assert result.status == "completed"
    assert result.file_type_id == "env_example"
    assert result.risk_flags.secret_sensitive is True
    assert result.secret_scan_findings
    assert "replace_this_secret" not in (result.content_preview or "")
