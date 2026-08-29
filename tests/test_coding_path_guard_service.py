from __future__ import annotations

from app.api.coding_path_guard_service import guard_workspace_path


def test_path_guard_allows_workspace_file(tmp_path):
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("print('ok')\n", encoding="utf-8")

    guarded = guard_workspace_path(workspace_root=str(tmp_path), target_path=str(source))

    assert guarded.allowed is True
    assert guarded.relative_path == "src/app.py"


def test_path_guard_blocks_outside_workspace(tmp_path):
    outside = tmp_path.parent / "outside.py"

    guarded = guard_workspace_path(workspace_root=str(tmp_path), target_path=str(outside), require_existing=False)

    assert guarded.allowed is False
    assert guarded.reason == "outside_workspace"


def test_path_guard_blocks_private_and_generated_paths(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=secret\n", encoding="utf-8")
    vault_file = tmp_path / "vault" / "note.md"
    vault_file.parent.mkdir()
    vault_file.write_text("private\n", encoding="utf-8")

    assert guard_workspace_path(workspace_root=str(tmp_path), target_path=str(env_file)).allowed is False
    assert guard_workspace_path(workspace_root=str(tmp_path), target_path=str(vault_file)).allowed is False


def test_path_guard_rejects_unapproved_and_broad_workspace_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_CODING_APPROVED_ROOTS", str(tmp_path / "approved"))
    (tmp_path / "approved").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    assert guard_workspace_path(workspace_root=str(outside), target_path="sample.py", require_existing=False).reason == "workspace_root_not_approved"
    assert guard_workspace_path(workspace_root=str(tmp_path), target_path="sample.py", require_existing=False).reason == "workspace_root_not_approved"


def test_path_guard_checks_blocked_workspace_root_itself(tmp_path, monkeypatch):
    approved = tmp_path / "approved"
    blocked = approved / "sealed_private"
    blocked.mkdir(parents=True)
    monkeypatch.setenv("ELYSIA_CODING_APPROVED_ROOTS", str(approved))

    guarded = guard_workspace_path(workspace_root=str(blocked), target_path="note.md", require_existing=False)

    assert guarded.allowed is False
    assert guarded.reason == "workspace_root_blocked"


def test_path_guard_rejects_in_workspace_symlinks(tmp_path):
    real = tmp_path / "real.py"
    real.write_text("print('ok')\n", encoding="utf-8")
    linked = tmp_path / "linked.py"
    linked.symlink_to(real)

    guarded = guard_workspace_path(workspace_root=str(tmp_path), target_path=str(linked))

    assert guarded.allowed is False
    assert guarded.reason == "symlink_not_allowed"
