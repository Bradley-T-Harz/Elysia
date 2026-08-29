from __future__ import annotations

from app.api.file_path_guard import guard_selected_file_path


def test_safe_selected_file_path_is_allowed(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("safe local notes", encoding="utf-8")

    result = guard_selected_file_path(source)

    assert result.allowed is True
    assert result.risk_category == "none"
    assert result.safe_display_name == "notes.md"


def test_vault_path_is_blocked_without_full_path_exposure():
    result = guard_selected_file_path("/project/vault/private-notes.md")

    assert result.allowed is False
    assert result.risk_category == "sensitive_path"
    assert result.safe_display_name == "private-notes.md"
    assert "/project" not in result.reason


def test_env_and_ssh_key_paths_are_blocked():
    assert guard_selected_file_path("/repo/.env").allowed is False
    assert guard_selected_file_path("/repo/id_rsa").allowed is False
    assert guard_selected_file_path("/repo/.ssh/config").allowed is False


def test_directory_and_symlink_are_blocked(tmp_path):
    directory = tmp_path / "folder"
    directory.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("target", encoding="utf-8")
    symlink = tmp_path / "link.txt"
    symlink.symlink_to(target)

    assert guard_selected_file_path(directory).risk_category == "directory"
    assert guard_selected_file_path(symlink).risk_category == "symlink"


def test_size_limit_blocks_large_selected_file(tmp_path):
    source = tmp_path / "large.txt"
    source.write_text("x" * 20, encoding="utf-8")

    result = guard_selected_file_path(source, max_size_bytes=5)

    assert result.allowed is False
    assert result.risk_category == "size_limit"
