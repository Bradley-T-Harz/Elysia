from __future__ import annotations

from sandbox.patch_worker import (
    PatchFileChange,
    PatchWorkerRequest,
    patch_hash_for_changes,
    run_patch_worker,
)
from sandbox.patch_worker.contract import PatchWorkerStatus


def _request(tmp_path, *, approved: bool = True, file_path: str = "sample.txt"):
    changes = [
        PatchFileChange(
            file_path=file_path,
            old_text="before\n",
            new_text="after\n",
        )
    ]
    return PatchWorkerRequest(
        request_id="req_patch_test",
        repo_key="tmp",
        repo_root=str(tmp_path),
        patch_id="patch_test",
        expected_patch_hash=patch_hash_for_changes(changes),
        changes=changes,
        approved_files=[file_path],
        approval_reference="approved-by-test",
        approved_by_user=approved,
        rollback_note="Restore the previous file contents from git or backup.",
    )


def test_patch_worker_requires_exact_approval(tmp_path):
    (tmp_path / "sample.txt").write_text("before\n", encoding="utf-8")

    result = run_patch_worker(_request(tmp_path, approved=False))

    assert result.status == PatchWorkerStatus.BLOCKED
    assert result.mutated_files is False
    assert result.shell_used is False
    assert result.git_mutation_used is False
    assert (tmp_path / "sample.txt").read_text(encoding="utf-8") == "before\n"


def test_patch_worker_applies_exact_python_only_patch(tmp_path):
    (tmp_path / "sample.txt").write_text("before\n", encoding="utf-8")

    result = run_patch_worker(_request(tmp_path))

    assert result.status == PatchWorkerStatus.COMPLETED
    assert result.files_changed == ["sample.txt"]
    assert result.mutated_files is True
    assert result.shell_used is False
    assert result.git_mutation_used is False
    assert result.network_access_used is False
    assert "sample.txt" in result.diff_preview
    assert (tmp_path / "sample.txt").read_text(encoding="utf-8") == "after\n"


def test_patch_worker_blocks_private_or_unsafe_paths(tmp_path):
    (tmp_path / "vault").mkdir()
    (tmp_path / "vault" / "note.txt").write_text("before\n", encoding="utf-8")

    result = run_patch_worker(_request(tmp_path, file_path="vault/note.txt"))

    assert result.status == PatchWorkerStatus.BLOCKED
    assert result.mutated_files is False
    assert result.files_changed == []
    assert result.files_refused == ["vault/note.txt"]
    assert (tmp_path / "vault" / "note.txt").read_text(encoding="utf-8") == "before\n"
