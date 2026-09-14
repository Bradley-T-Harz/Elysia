from datetime import timedelta
from hashlib import sha256

import pytest
from pydantic import ValidationError

from core.codev.approvals import PlanAuthority
from core.codev.contracts import Actor, BrowserPublicKey, ChangePlan, FileChange, WorkspaceFile, BrowserWorkspaceShare
from core.codev.grants import GrantAuthority, GrantDenied, utc_now
from core.codev.revisions import relative_path, workspace_hash
from scripts.generate_codev_contracts import generated_files, generated_rust, ROOT


def actor(client="native-a", account="local-a", kind="native", online=None):
    return Actor(local_profile_id=account, client_id=client, client_kind=kind,
                 surface="local" if kind == "native" else "forge", online_account_id=online,
                 origin="https://elysiaecobotics.com" if kind == "browser" else None)


def setup_plan():
    grants = GrantAuthority()
    owner = actor()
    grant = grants.issue(actor=owner, workspace_id="workspace-a", scopes=["read", "propose", "apply"],
        files=["main.py"], command_ids=[], expected_epoch=0, explicitly_approved=True)
    authority = PlanAuthority(grants)
    plan = authority.register(ChangePlan(plan_id="plan-a", workspace_id="workspace-a", actor=owner,
        base_revision=4, workspace_hash="a" * 64, grant_epoch=grant.epoch, plan_hash="0" * 64,
        summary="Change answer", changes=[FileChange(path="main.py", base_hash="b" * 64,
            new_text="answer = 2\n", new_hash=sha256(b"answer = 2\n").hexdigest(), diff="reviewed diff")],
        cwd_label="selected workspace", expires_at=(utc_now() + timedelta(minutes=5)).isoformat(),
        recovery_note="Exact source backup before replacement."))
    return grants, authority, owner, plan


def test_generated_desktop_contracts_match_canonical_schema():
    schema, ts = generated_files()
    assert (ROOT / "contracts/codev.schema.json").read_text() == schema
    assert (ROOT / "apps/elysia-desktop/src/api/codevContracts.ts").read_text() == ts
    assert (ROOT / "apps/elysia-desktop/src-tauri/src/codev_contracts.rs").read_text() == generated_rust()


def test_workspace_hash_checks_actual_bytes_and_preserves_full_license():
    text = "License heading\n\nFull terms remain part of this revision.\n"
    file = WorkspaceFile(path="LICENSE", content_hash=sha256(text.encode()).hexdigest(), size_bytes=len(text.encode()),
                         availability="text", text=text, provenance="editor")
    digest = workspace_hash([file])
    assert workspace_hash([file.model_copy(update={"text": None, "availability": "metadata_only"})]) == digest
    with pytest.raises(ValueError, match="hash_mismatch"):
        workspace_hash([file.model_copy(update={"text": text.splitlines()[0]})])
    with pytest.raises(ValueError, match="collision"):
        workspace_hash([file, file.model_copy(update={"path": "license"})])


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/../b", "C:/a", "a\\b", "a//b", "NUL.txt", "a. ", "a\x00b"])
def test_noncanonical_paths_are_rejected(path):
    with pytest.raises(ValueError):
        relative_path(path)


def test_browsers_cannot_grant_native_writes_commands_or_secret_files():
    grants = GrantAuthority()
    for scope, files, commands in [("apply", ["main.py"], []), ("command", [], ["git_diff_check"]), ("read", [".env"], [])]:
        with pytest.raises(GrantDenied):
            grants.issue(actor=actor(kind="browser", online="online-a"), workspace_id="workspace-a",
                         scopes=[scope], files=files, command_ids=commands, expected_epoch=0, explicitly_approved=True)


def test_approval_rejects_client_revision_grant_and_replay_changes():
    grants, authority, owner, plan = setup_plan()
    approval, token = authority.approve(owner, plan.plan_id, plan.plan_hash, explicitly_approved=True)
    arguments = dict(plan_id=plan.plan_id, revision=4, workspace_hash="a" * 64)
    with pytest.raises(GrantDenied, match="actor"):
        authority.consume(actor(client="native-b"), approval.approval_id, token, **arguments)
    with pytest.raises(GrantDenied, match="revision_conflict"):
        authority.consume(owner, approval.approval_id, token, **{**arguments, "revision": 5})
    assert authority.consume(owner, approval.approval_id, token, **arguments).plan_hash == plan.plan_hash
    with pytest.raises(GrantDenied):
        authority.consume(owner, approval.approval_id, token, **arguments)


def test_revocation_and_new_epoch_invalidate_old_approvals():
    grants, authority, owner, plan = setup_plan()
    approval, token = authority.approve(owner, plan.plan_id, plan.plan_hash, explicitly_approved=True)
    revoked = grants.revoke(owner, "workspace-a")
    assert revoked.epoch == 2
    grants.issue(actor=owner, workspace_id="workspace-a", scopes=["apply"], files=["main.py"], command_ids=[],
                 expected_epoch=2, explicitly_approved=True)
    with pytest.raises(GrantDenied, match="epoch"):
        authority.consume(owner, approval.approval_id, token, plan_id=plan.plan_id, revision=4, workspace_hash="a" * 64)


def test_account_switch_never_inherits_grants_even_if_client_identifier_is_reused():
    grants = GrantAuthority()
    first = actor(kind="browser", online="online-a")
    second = actor(kind="browser", online="online-b")
    grants.issue(actor=first, workspace_id="workspace-a", scopes=["read"], files=["a.txt"], command_ids=[],
                 expected_epoch=0, explicitly_approved=True)
    assert grants.get(second, "workspace-a") is None
    assert grants.revoke(second, "workspace-a") is None
    with pytest.raises(GrantDenied):
        grants.require(second, "workspace-a", "read", files=["a.txt"])


def test_pairing_key_contract_rejects_private_key_material():
    with pytest.raises(ValidationError):
        BrowserPublicKey(kty="EC", crv="P-256", x="a" * 43, y="b" * 43, d="must-never-cross")


def test_grant_expiry_blocks_previously_approved_operation(monkeypatch):
    import core.codev.grants as grant_module
    grants, authority, owner, plan = setup_plan()
    approval, token = authority.approve(owner, plan.plan_id, plan.plan_hash, explicitly_approved=True)
    later = utc_now() + timedelta(hours=2)
    monkeypatch.setattr(grant_module, "utc_now", lambda: later)
    with pytest.raises(GrantDenied, match="expired"):
        authority.consume(owner, approval.approval_id, token, plan_id=plan.plan_id, revision=4, workspace_hash="a" * 64)


def test_multiple_approval_tickets_cannot_replay_one_plan():
    grants, authority, owner, plan = setup_plan()
    first, token_a = authority.approve(owner, plan.plan_id, plan.plan_hash, explicitly_approved=True)
    second, token_b = authority.approve(owner, plan.plan_id, plan.plan_hash, explicitly_approved=True)
    params = dict(plan_id=plan.plan_id, revision=4, workspace_hash="a" * 64)
    authority.consume(owner, first.approval_id, token_a, **params)
    with pytest.raises(GrantDenied):
        authority.consume(owner, second.approval_id, token_b, **params)
