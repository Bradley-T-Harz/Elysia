from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import project_media_service as service


class _Process:
    pid = 4242


def _prepare(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "current_user_id", lambda: "test_user")
    monkeypatch.setattr(
        service.project_service,
        "get_project_metadata",
        lambda project_id: {"project_id": project_id, "owner_user_id": "test_user"},
    )
    monkeypatch.setattr(
        service,
        "resolve_elysia_paths",
        lambda: SimpleNamespace(data_dir=tmp_path / "data"),
    )
    monkeypatch.setattr(service, "_gimp_binary", lambda: "/usr/bin/gimp")
    monkeypatch.setenv("DISPLAY", ":99")


def test_gimp_launches_fixed_argv_against_private_working_copy(monkeypatch, tmp_path: Path):
    _prepare(monkeypatch, tmp_path)
    source = tmp_path / "operator image.png"
    source.write_bytes(b"safe-test-image")
    captured = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _Process()

    monkeypatch.setattr(service.subprocess, "Popen", fake_popen)
    result = service.open_project_image_in_gimp(
        "project-1",
        service.ProjectImageEditRequest(source_path=str(source), operator_approved=True),
    )

    assert result["status"] == "launched"
    assert result["original_unchanged"] is True
    assert result["working_copy_private"] is True
    assert result["source_sha256"] == result["working_copy_sha256"]
    assert captured["argv"][0] == "/usr/bin/gimp"
    working_copy = Path(captured["argv"][1])
    assert working_copy != source
    assert working_copy.is_file()
    assert working_copy.stat().st_mode & 0o777 == 0o600
    assert captured["kwargs"]["close_fds"] is True
    assert captured["kwargs"]["start_new_session"] is True


def test_gimp_requires_explicit_confirmation_and_regular_image(monkeypatch, tmp_path: Path):
    _prepare(monkeypatch, tmp_path)
    source = tmp_path / "image.png"
    source.write_bytes(b"safe-test-image")

    with pytest.raises(service.ProjectMediaError, match="confirmation"):
        service.open_project_image_in_gimp(
            "project-1",
            service.ProjectImageEditRequest(source_path=str(source), operator_approved=False),
        )

    text_file = tmp_path / "not-an-image.txt"
    text_file.write_text("not an image", encoding="utf-8")
    with pytest.raises(service.ProjectMediaError, match="supported image"):
        service.open_project_image_in_gimp(
            "project-1",
            service.ProjectImageEditRequest(source_path=str(text_file), operator_approved=True),
        )
