from __future__ import annotations

from app.api.coding_git_service import preview_git_state
from app.api.schemas.coding_git import CodingGitPreviewRequest


def test_git_preview_degrades_to_head_truth_when_status_cannot_run(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    result = preview_git_state(CodingGitPreviewRequest(workspace_root=str(tmp_path)))

    assert result.status == "degraded"
    assert result.repo_detected is True
    assert result.branch == "main"
    assert result.mutation_allowed is False
    assert result.shell_git_used is False


def test_git_preview_handles_non_repo(tmp_path):
    result = preview_git_state(CodingGitPreviewRequest(workspace_root=str(tmp_path)))

    assert result.status == "not_a_git_repo"
    assert result.repo_detected is False
