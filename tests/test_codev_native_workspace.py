from pathlib import Path
from uuid import uuid4

import pytest

from core.codev import workspaces
from core.codev.approvals import PLANS
from core.codev.contracts import Actor
from core.codev.grants import GrantDenied


def fixture(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    (root / "main.py").write_text("answer = 1\n")
    actor = Actor(local_profile_id="local-fixture", client_id="native_" + uuid4().hex, client_kind="native", surface="local")
    selected = workspaces.select_workspace(actor, str(root))
    return root, actor, selected.workspace_id


def share(actor, workspace_id, files=None):
    return workspaces.grant_workspace(actor, workspace_id, scopes=["metadata", "read", "propose", "apply"],
        files=files or ["main.py"], command_ids=[], expected_epoch=0, explicitly_approved=True)


def propose_and_approve(actor, workspace_id, edits):
    snapshot = workspaces.snapshot(actor, workspace_id)
    plan = workspaces.plan_patch(actor, workspace_id, edits=edits, revision=snapshot.current_revision, summary="Reviewed change")
    approval, token = PLANS.approve(actor, plan.plan_id, plan.plan_hash, explicitly_approved=True)
    return dict(plan_id=plan.plan_id, approval_id=approval.approval_id, approval_token=token)


def test_selection_alone_grants_no_metadata_or_files(tmp_path):
    root, actor, workspace_id = fixture(tmp_path)
    with pytest.raises(GrantDenied):
        workspaces.tree(actor, workspace_id)
    with pytest.raises(GrantDenied):
        workspaces.snapshot(actor, workspace_id)
    assert (root / "main.py").read_text() == "answer = 1\n"


def test_session_grant_does_not_create_legacy_ambient_authority(tmp_path, monkeypatch):
    from app.api.coding_path_guard_service import guard_workspace_path
    root, actor, workspace_id = fixture(tmp_path)
    monkeypatch.delenv("ELYSIA_CODING_APPROVED_ROOTS")
    share(actor, workspace_id)
    assert workspaces.snapshot(actor, workspace_id).files[0].text == "answer = 1\n"
    assert not guard_workspace_path(workspace_root=str(root), target_path="main.py").allowed


@pytest.mark.parametrize("new_text", ["answer = 2\n", "answer = 2", "answer = 2\r\n"])
def test_exact_apply_preserves_reviewed_bytes_and_backup(tmp_path, new_text):
    root, actor, workspace_id = fixture(tmp_path)
    share(actor, workspace_id)
    approved = propose_and_approve(actor, workspace_id, {"main.py": new_text})
    receipt = workspaces.apply_plan(actor, workspace_id, **approved)
    assert receipt.status == "completed", receipt.warnings
    assert receipt.files_changed == ["main.py"]
    assert receipt.verification == "passed"
    assert receipt.tests_run == [] and not receipt.network_used
    assert (root / "main.py").read_bytes() == new_text.encode()
    assert (root / receipt.artifacts[0].relative_path).read_bytes() == b"answer = 1\n"
    with pytest.raises(GrantDenied):
        workspaces.apply_plan(actor, workspace_id, **approved)


def test_stale_source_and_other_workspace_cannot_use_approval(tmp_path):
    root, actor, workspace_id = fixture(tmp_path)
    share(actor, workspace_id)
    approved = propose_and_approve(actor, workspace_id, {"main.py": "answer = 2\n"})
    other = workspaces.select_workspace(actor, str(root))
    share(actor, other.workspace_id)
    with pytest.raises(GrantDenied, match="workspace_mismatch"):
        workspaces.apply_plan(actor, other.workspace_id, **approved)
    (root / "main.py").write_text("answer = 3\n")
    with pytest.raises(GrantDenied, match="revision_conflict"):
        workspaces.apply_plan(actor, workspace_id, **approved)
    assert (root / "main.py").read_text() == "answer = 3\n"


def test_revocation_survives_folder_deletion_and_blocks_old_plan(tmp_path):
    root, actor, workspace_id = fixture(tmp_path)
    share(actor, workspace_id)
    approved = propose_and_approve(actor, workspace_id, {"main.py": "answer = 2\n"})
    root.rename(tmp_path / "moved")
    assert workspaces.revoke_workspace(actor, workspace_id)["revoked"]
    with pytest.raises(GrantDenied):
        workspaces.apply_plan(actor, workspace_id, **approved)


def test_tree_hides_secret_paths_and_links(tmp_path):
    root, actor, workspace_id = fixture(tmp_path)
    (root / ".env").write_text("PRIVATE_CANARY")
    (root / "alias.py").symlink_to(root / "main.py")
    share(actor, workspace_id)
    assert [item["path"] for item in workspaces.tree(actor, workspace_id)["files"]] == ["main.py"]


def test_partial_failure_reports_exact_changed_files(tmp_path, monkeypatch):
    from core.codev import service
    root, actor, workspace_id = fixture(tmp_path)
    (root / "second.py").write_text("answer = 1\n")
    share(actor, workspace_id, ["main.py", "second.py"])
    approved = propose_and_approve(actor, workspace_id, {"main.py": "answer = 2\n", "second.py": "answer = 2\n"})
    original = service.apply_patch_with_approval
    def fail_second(payload):
        if payload.target_file == "second.py":
            raise OSError("fixture second-write failure")
        return original(payload)
    monkeypatch.setattr(service, "apply_patch_with_approval", fail_second)
    receipt = workspaces.apply_plan(actor, workspace_id, **approved)
    assert receipt.status == "partial"
    assert receipt.files_changed == ["main.py"]
    assert len(receipt.artifacts) == 1
    assert (root / "second.py").read_text() == "answer = 1\n"
