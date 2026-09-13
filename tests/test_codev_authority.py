from hashlib import sha256
import os

from app.api.coding_operation_service import approve_operation, consume_operation_approval
from app.api.coding_path_guard_service import guard_workspace_path
from app.api.coding_repo_registry import record_repo_approval, revoke_repo_approval
from app.api.schemas.coding_operations import CodingOperationApproveRequest
from core.codev.identity import bind_client


def test_revocation_overrides_runtime_root_and_descendants(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    root = tmp_path / "repo"
    root.mkdir()
    nested = root / "nested"
    nested.mkdir()
    key = sha256(str(root).encode()).hexdigest()[:24]
    assert revoke_repo_approval(root_hash=key, root=root)
    for candidate in (root, nested):
        result = guard_workspace_path(workspace_root=str(candidate), target_path=".", allow_directory=True)
        assert result.reason == "workspace_root_revoked"
    record_repo_approval(root_hash=key, root=root, label="repo")
    assert guard_workspace_path(workspace_root=str(root), target_path=".", allow_directory=True).allowed


def test_workspace_root_symlink_and_hardlink_are_denied(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    assert not guard_workspace_path(workspace_root=str(alias), target_path=".", allow_directory=True).allowed
    source = root / "source.txt"
    source.write_text("content")
    os.link(source, root / "alias.txt")
    assert guard_workspace_path(workspace_root=str(root), target_path="alias.txt").reason == "hardlink_not_allowed"


def test_exact_approval_is_bound_to_internal_client(tmp_path):
    (tmp_path / "a.txt").write_text("old")
    with bind_client("workroom-session-A"):
        approval = approve_operation(CodingOperationApproveRequest(
            operation_kind="patch_apply", operation_summary="exact patch", workspace_root=str(tmp_path),
            exact_files=["a.txt"], source_hash="source", plan_hash="plan",
            allowed_mutation_class="text_patch", operator_approved=True,
            rollback_note="Use governed backup receipt.",
        ))
    args = dict(approval_id=approval.approval_id, approval_token=approval.approval_token,
                operation_kind="patch_apply", workspace_root=str(tmp_path), exact_files=["a.txt"],
                source_hash="source", plan_hash="plan", allowed_mutation_class="text_patch")
    with bind_client("workroom-session-B"):
        assert consume_operation_approval(**args).reason == "approval_actor_mismatch"
    with bind_client("workroom-session-A"):
        assert consume_operation_approval(**args).allowed
        assert not consume_operation_approval(**args).allowed


def test_managed_policy_covers_both_coding_route_families():
    from app.api.main import _managed_policy_requirements
    assert _managed_policy_requirements("/code/tests/run", "POST") == ("coding_execution",)
    assert _managed_policy_requirements("/codev/patch/apply", "POST") == ("coding_execution",)


def test_legacy_command_boolean_never_launches_worker(monkeypatch):
    from app.api.code_service import run_approved_focused_command
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("process launched")))
    result = run_approved_focused_command({
        "command_key": "frontend_build", "argv": ["npm", "--prefix", "apps/elysia-desktop", "run", "build"],
        "approval_reference": "claimed-approval", "approved_by_user": True,
    })
    assert result.status == "blocked"
    assert not result.mutated_files and not result.network_access_used
