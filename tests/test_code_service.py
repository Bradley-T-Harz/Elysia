from __future__ import annotations

from pathlib import Path

import app.api.code_service as code_service
from sandbox.patch_worker import PatchFileChange, patch_hash_for_changes


def _approved_repo_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "approved_repos.yaml"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    config_path.write_text(
        "version: 1\n"
        "repos:\n"
        "  tmp:\n"
        f"    root: {repo_root}\n"
        "    allowed: true\n",
        encoding="utf-8",
    )
    return config_path


def test_code_service_applies_approved_patch_and_writes_truth(tmp_path, monkeypatch):
    config_path = _approved_repo_config(tmp_path)
    repo_root = tmp_path / "repo"
    (repo_root / "sample.txt").write_text("before\n", encoding="utf-8")
    monkeypatch.setattr(code_service, "APPROVED_REPOS_CONFIG_PATH", config_path)
    changes = [
        PatchFileChange(
            file_path="sample.txt",
            old_text="before\n",
            new_text="after\n",
        )
    ]

    result = code_service.apply_approved_patch(
        {
            "request_id": "req_code_patch_test",
            "repo_key": "tmp",
            "patch_id": "patch_test",
            "expected_patch_hash": patch_hash_for_changes(changes),
            "changes": [
                {
                    "file_path": "sample.txt",
                    "old_text": "before\n",
                    "new_text": "after\n",
                }
            ],
            "approved_files": ["sample.txt"],
            "approval_reference": "approval",
            "approved_by_user": True,
            "rollback_note": "Restore old text from backup.",
        }
    )

    assert result.status == "completed"
    assert result.mutated_files is True
    assert result.shell_used is False
    assert result.git_mutation_used is False
    assert (repo_root / "sample.txt").read_text(encoding="utf-8") == "after\n"


def test_code_service_blocks_unapproved_patch(tmp_path, monkeypatch):
    config_path = _approved_repo_config(tmp_path)
    monkeypatch.setattr(code_service, "APPROVED_REPOS_CONFIG_PATH", config_path)
    changes = [
        PatchFileChange(
            file_path="sample.txt",
            old_text="before\n",
            new_text="after\n",
        )
    ]

    result = code_service.apply_approved_patch(
        {
            "request_id": "req_code_patch_blocked",
            "repo_key": "tmp",
            "patch_id": "patch_test",
            "expected_patch_hash": patch_hash_for_changes(changes),
            "changes": [
                {
                    "file_path": "sample.txt",
                    "old_text": "before\n",
                    "new_text": "after\n",
                }
            ],
            "approved_files": ["sample.txt"],
            "approval_reference": "approval",
            "approved_by_user": False,
        }
    )

    assert result.status == "blocked"
    assert result.mutated_files is False
