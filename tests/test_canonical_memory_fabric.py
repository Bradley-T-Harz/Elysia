from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
from uuid import UUID

import pytest

from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import (
    AccountDeleteRequest,
    AccountCreateRequest,
    AccountLoginRequest,
    AccountProfileUpdateRequest,
)
from app.cognition.fts_projection import FtsMemoryProjection
from app.memory.canonical_models import (
    ConsequenceApplyRequest,
    ConsequencePreviewRequest,
    MemoryCorrectionRequest,
    MemoryCreateRequest,
    MemoryPinRequest,
    MemoryPrivacy,
    MemoryPrincipal,
    MemoryQuery,
    SharedSpaceCreateRequest,
    SharedSpaceInvitationResponseRequest,
)
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import (
    MemoryApprovalError,
    MemoryAuthorizationError,
    MemoryFabricError,
    MemoryFabricService,
)
from app.memory.encryption_service import MemoryEncryptionError, SealedMemoryLockedError
from app.memory.object_store import MemoryObjectError
from app.memory.release_service import MemoryReleaseService


def make_store(tmp_path: Path) -> AccountStore:
    identity = tmp_path / "profile" / "identity"
    return AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )


def request(title: str, body: str, *, privacy: str = "normal") -> MemoryCreateRequest:
    return MemoryCreateRequest(
        title=title,
        body=body,
        why_stored="Synthetic isolation proof.",
        privacy=privacy,
    )


def approve(fabric, principal, target_id, preview_request):
    preview = fabric.preview_consequence(principal, target_id, preview_request)
    return fabric.apply_consequence(
        principal,
        target_id,
        ConsequenceApplyRequest(
            approval_id=preview["approval_id"],
            approval_token=preview["approval_token"],
        ),
    )


def test_multi_account_isolation_and_deliberate_shared_space_acl(tmp_path):
    store = make_store(tmp_path)
    store.create_account(AccountCreateRequest(username="alpha", password="alpha account password"))
    alpha = store.authenticated_principal()

    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    alpha_principal = MemoryPrincipal.model_validate(alpha)
    private_record = fabric.create(
        alpha_principal,
        request("Alpha private", "ALPHA_PRIVATE_CANARY", privacy="private"),
    )
    shared_record = fabric.create(
        alpha_principal,
        request("Deliberately shared", "SHARED_CANARY"),
    )
    space = fabric.create_space(
        alpha_principal,
        SharedSpaceCreateRequest(label="Synthetic collaborators", description="ACL proof"),
    )

    store.create_account(AccountCreateRequest(username="beta", password="beta account password"))
    # Creating an additional profile must not silently switch the current
    # Installation Owner session. Select the synthetic second account
    # explicitly before asserting its isolation boundary.
    store.login(AccountLoginRequest(username="beta", password="beta account password"))
    beta = store.authenticated_principal()
    beta_principal = MemoryPrincipal.model_validate(beta)

    beta_items, beta_count = fabric.list(beta_principal, MemoryQuery())
    assert beta_items == []
    assert beta_count == 0
    with pytest.raises(Exception):
        fabric.get(beta_principal, private_record.memory_id)

    approve(
        fabric,
        alpha_principal,
        space["space_id"],
        ConsequencePreviewRequest(
            action="add_space_member",
            target_user_id=beta_principal.user_id,
            target_role="reader",
            reason="Explicitly grant read-only shared access.",
        ),
    )
    approve(
        fabric,
        alpha_principal,
        shared_record.memory_id,
        ConsequencePreviewRequest(
            action="move_to_space",
            target_space_id=space["space_id"],
            reason="Explicitly move this record into the shared ACL.",
        ),
    )

    visible = fabric.get(beta_principal, shared_record.memory_id)
    assert visible.body == "SHARED_CANARY"
    assert visible.space_id == space["space_id"]
    projection = FtsMemoryProjection(
        paths=store.elysia_paths,
        repository=repository,
        fabric=fabric,
    )
    # The ACL filter is part of the FTS query itself.  Supplying the live
    # authorized-space set admits the shared record; omitting it cannot fall
    # back to another account's owner namespace.
    shared_hits = projection.search(
        beta_principal,
        "SHARED_CANARY",
        space_ids=[space["space_id"]],
    )
    assert [row["candidate_id"] for row in shared_hits] == [shared_record.memory_id]
    assert projection.count_search(
        beta_principal,
        "SHARED_CANARY",
        space_ids=[space["space_id"]],
    ) == 1
    assert projection.search(beta_principal, "SHARED_CANARY", space_ids=[]) == []
    with pytest.raises(MemoryAuthorizationError):
        fabric.correct(
            beta_principal,
            shared_record.memory_id,
            MemoryCorrectionRequest(body="Reader must not edit", reason="ACL denial proof"),
        )


def test_shared_space_invitation_roles_change_revocation_and_restart(tmp_path):
    store = make_store(tmp_path)
    owner_password = "space-owner synthetic password"
    store.create_account(
        AccountCreateRequest(username="space-owner", password=owner_password)
    )
    principals: dict[str, MemoryPrincipal] = {
        "space-owner": MemoryPrincipal.model_validate(store.authenticated_principal())
    }
    for username in ("space-editor", "space-contributor", "space-reader", "space-decliner"):
        password = f"{username} synthetic password"
        store.create_account(AccountCreateRequest(username=username, password=password))
        store.logout()
        store.login(AccountLoginRequest(username=username, password=password))
        principals[username] = MemoryPrincipal.model_validate(store.authenticated_principal())
        store.logout()
        store.login(AccountLoginRequest(username="space-owner", password=owner_password))

    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    owner = principals["space-owner"]
    space = fabric.create_space(
        owner,
        SharedSpaceCreateRequest(label="Gate Zero roles", description="Synthetic ACL lifecycle"),
    )

    def consequence(action: str, username: str, role: str | None = None):
        preview = fabric.preview_consequence(
            owner,
            space["space_id"],
            ConsequencePreviewRequest(
                action=action,
                target_user_id=principals[username].user_id,
                target_role=role,
                reason=f"Synthetic {action} proof.",
            ),
        )
        return fabric.apply_consequence(
            owner,
            space["space_id"],
            ConsequenceApplyRequest(
                approval_id=preview["approval_id"],
                approval_token=preview["approval_token"],
            ),
        )

    for username, role in (
        ("space-editor", "editor"),
        ("space-contributor", "contributor"),
        ("space-reader", "reader"),
        ("space-decliner", "reader"),
    ):
        invited = consequence("invite_space_member", username, role)
        invitations = fabric.list_space_invitations(principals[username])
        assert [item["invitation_id"] for item in invitations] == [invited["invitation_id"]]
        response = fabric.respond_space_invitation(
            principals[username],
            str(invited["invitation_id"]),
            SharedSpaceInvitationResponseRequest(
                decision="decline" if username == "space-decliner" else "accept"
            ),
        )
        assert response["state"] == ("declined" if username == "space-decliner" else "accepted")
        assert response["identity_blended"] is False

    owner_record = fabric.create(
        owner,
        MemoryCreateRequest(
            title="Shared role canary",
            body="SHARED_ROLE_LIFECYCLE_CANARY",
            why_stored="Synthetic role proof.",
            scope="shared_space",
            space_id=space["space_id"],
        ),
    )
    editor_record = fabric.create(
        principals["space-editor"],
        MemoryCreateRequest(
            title="Editor contribution",
            body="EDITOR_SHARED_CANARY",
            why_stored="Synthetic editor proof.",
            scope="shared_space",
            space_id=space["space_id"],
        ),
    )
    fabric.correct(
        principals["space-editor"],
        owner_record.memory_id,
        MemoryCorrectionRequest(
            body="SHARED_ROLE_LIFECYCLE_CANARY_EDITED",
            reason="Editor role permits correction.",
        ),
    )
    contributor_record = fabric.create(
        principals["space-contributor"],
        MemoryCreateRequest(
            title="Contributor contribution",
            body="CONTRIBUTOR_SHARED_CANARY",
            why_stored="Synthetic contributor proof.",
            scope="shared_space",
            space_id=space["space_id"],
        ),
    )
    with pytest.raises(MemoryAuthorizationError):
        fabric.correct(
            principals["space-contributor"],
            owner_record.memory_id,
            MemoryCorrectionRequest(body="Forbidden contributor edit", reason="Role denial proof."),
        )
    projection = FtsMemoryProjection(
        paths=store.elysia_paths,
        repository=repository,
        fabric=fabric,
    )
    assert projection.search(
        principals["space-contributor"],
        "CONTRIBUTOR_SHARED_CANARY",
        space_ids=[space["space_id"]],
    )
    release = MemoryReleaseService(repository=repository, fabric=fabric)
    shared_object = release.objects.put(
        principal=principals["space-contributor"],
        raw=b"SYNTHETIC_SHARED_OBJECT_CANARY",
        privacy=MemoryPrivacy.NORMAL,
        space_id=space["space_id"],
        ref_type="memory",
        ref_id=contributor_record.memory_id,
        purpose="synthetic-revocation-proof",
    )
    assert release.objects.read(
        principal=principals["space-contributor"],
        object_id=str(shared_object["object_id"]),
    ) == b"SYNTHETIC_SHARED_OBJECT_CANARY"
    contributor_graph = release.graph(
        principals["space-contributor"], contributor_record.memory_id
    )
    assert contributor_graph["source_owner_preserved"] == principals[
        "space-contributor"
    ].user_id
    consequence("remove_space_member", "space-contributor")
    with pytest.raises(Exception):
        fabric.get(principals["space-contributor"], contributor_record.memory_id)
    contributor_items, _ = fabric.list(principals["space-contributor"], MemoryQuery())
    assert contributor_record.memory_id not in {item.memory_id for item in contributor_items}
    # Source ownership is provenance only after revocation. Even a stale or
    # forged caller-supplied space identifier is intersected with the current
    # canonical membership before plaintext ranking.
    assert projection.search(
        principals["space-contributor"],
        "CONTRIBUTOR_SHARED_CANARY",
        space_ids=[space["space_id"]],
    ) == []
    assert fabric.get(owner, contributor_record.memory_id).body == "CONTRIBUTOR_SHARED_CANARY"
    with pytest.raises(MemoryObjectError):
        release.objects.read(
            principal=principals["space-contributor"],
            object_id=str(shared_object["object_id"]),
        )
    with pytest.raises(MemoryObjectError):
        release.objects.put(
            principal=principals["space-contributor"],
            raw=b"FORGED_SHARED_OBJECT_MUST_NOT_EXIST",
            privacy=MemoryPrivacy.NORMAL,
            space_id=space["space_id"],
            ref_type="memory",
            ref_id=contributor_record.memory_id,
            purpose="synthetic-forged-domain-denial",
        )
    with pytest.raises(MemoryObjectError):
        release.objects.put(
            principal=owner,
            raw=b"PRIVATE_SHARED_OBJECT_MUST_NOT_EXIST",
            privacy=MemoryPrivacy.PRIVATE,
            space_id=space["space_id"],
            ref_type="memory",
            ref_id=contributor_record.memory_id,
            purpose="synthetic-declassification-denial",
        )
    assert release.objects.read(
        principal=owner,
        object_id=str(shared_object["object_id"]),
    ) == b"SYNTHETIC_SHARED_OBJECT_CANARY"
    owner_graph = release.graph(owner, contributor_record.memory_id)
    assert owner_graph["source_owner_preserved"] == principals["space-contributor"].user_id
    with repository.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_graph_nodes WHERE owner_user_id=?",
            (principals["space-contributor"].user_id,),
        ).fetchone()[0] == 0
    assert fabric.get(principals["space-reader"], owner_record.memory_id).body
    with pytest.raises(MemoryAuthorizationError):
        fabric.create(
            principals["space-reader"],
            MemoryCreateRequest(
                title="Forbidden reader write",
                body="READER_WRITE_MUST_NOT_EXIST",
                why_stored="Role denial proof.",
                scope="shared_space",
                space_id=space["space_id"],
            ),
        )

    consequence("change_space_member_role", "space-editor", "reader")
    with pytest.raises(MemoryFabricError, match="already a member"):
        fabric.preview_consequence(
            owner,
            space["space_id"],
            ConsequencePreviewRequest(
                action="add_space_member",
                target_user_id=principals["space-editor"].user_id,
                target_role="editor",
                reason="Synthetic direct-add bypass denial.",
            ),
        )
    with pytest.raises(MemoryAuthorizationError):
        fabric.correct(
            principals["space-editor"],
            editor_record.memory_id,
            MemoryCorrectionRequest(body="Forbidden after downgrade", reason="Role change proof."),
        )
    consequence("remove_space_member", "space-reader")
    with pytest.raises(Exception):
        fabric.get(principals["space-reader"], owner_record.memory_id)

    restarted = MemoryFabricService(repository=MemoryRepository(paths=store.elysia_paths))
    with pytest.raises(Exception):
        restarted.get(principals["space-reader"], owner_record.memory_id)
    assert restarted.get(principals["space-editor"], owner_record.memory_id).body
    with repository.connect() as conn:
        roles = {
            str(row["user_id"]): str(row["role"])
            for row in conn.execute(
                "SELECT user_id,role FROM shared_space_members WHERE space_id=?",
                (space["space_id"],),
            ).fetchall()
        }
        states = {
            str(row["invited_user_id"]): str(row["state"])
            for row in conn.execute(
                "SELECT invited_user_id,state FROM shared_space_invitations WHERE space_id=?",
                (space["space_id"],),
            ).fetchall()
        }
    assert roles[principals["space-editor"].user_id] == "reader"
    assert principals["space-reader"].user_id not in roles
    assert states[principals["space-reader"].user_id] == "revoked"
    assert states[principals["space-decliner"].user_id] == "declined"

    deletable_password = "space-deletable synthetic password"
    store.create_account(
        AccountCreateRequest(username="space-deletable", password=deletable_password)
    )
    store.logout()
    store.login(
        AccountLoginRequest(username="space-deletable", password=deletable_password)
    )
    deletable = MemoryPrincipal.model_validate(store.authenticated_principal())
    store.logout()
    store.login(AccountLoginRequest(username="space-owner", password=owner_password))
    principals["space-deletable"] = deletable
    invited = consequence("invite_space_member", "space-deletable", "reader")
    fabric.respond_space_invitation(
        deletable,
        str(invited["invitation_id"]),
        SharedSpaceInvitationResponseRequest(decision="accept"),
    )
    store.logout()
    store.login(
        AccountLoginRequest(username="space-deletable", password=deletable_password)
    )
    store.delete_current_account(
        AccountDeleteRequest(
            current_password=deletable_password,
            confirmation_username="space-deletable",
        )
    )
    with repository.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM shared_space_members WHERE user_id=?",
            (deletable.user_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM shared_space_invitations WHERE invited_user_id=?",
            (deletable.user_id,),
        ).fetchone()[0] == 0

    stale_password = "space-stale-target synthetic password"
    store.login(AccountLoginRequest(username="space-owner", password=owner_password))
    store.create_account(
        AccountCreateRequest(username="space-stale-target", password=stale_password)
    )
    store.logout()
    store.login(AccountLoginRequest(username="space-stale-target", password=stale_password))
    stale = MemoryPrincipal.model_validate(store.authenticated_principal())
    store.logout()
    store.login(AccountLoginRequest(username="space-owner", password=owner_password))
    stale_preview = fabric.preview_consequence(
        owner,
        space["space_id"],
        ConsequencePreviewRequest(
            action="invite_space_member",
            target_user_id=stale.user_id,
            target_role="reader",
            reason="Synthetic identity-race proof.",
        ),
    )
    store.logout()
    store.login(AccountLoginRequest(username="space-stale-target", password=stale_password))
    store.delete_current_account(
        AccountDeleteRequest(
            current_password=stale_password,
            confirmation_username="space-stale-target",
        )
    )
    store.login(AccountLoginRequest(username="space-owner", password=owner_password))
    with pytest.raises(MemoryFabricError, match="does not exist"):
        fabric.apply_consequence(
            owner,
            space["space_id"],
            ConsequenceApplyRequest(
                approval_id=stale_preview["approval_id"],
                approval_token=stale_preview["approval_token"],
            ),
        )
    with repository.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM shared_space_invitations WHERE invited_user_id=?",
            (stale.user_id,),
        ).fetchone()[0] == 0


def test_private_to_shared_requires_preview_and_explicitly_declassifies(tmp_path):
    store = make_store(tmp_path)
    store.create_account(AccountCreateRequest(username="owner", password="owner account password"))
    principal_data = store.authenticated_principal()
    fabric = MemoryFabricService(repository=MemoryRepository(paths=store.elysia_paths))
    principal = MemoryPrincipal.model_validate(principal_data)
    record = fabric.create(
        principal,
        request("Private source", "DECLASSIFICATION_CANARY", privacy="private"),
    )
    space = fabric.create_space(
        principal, SharedSpaceCreateRequest(label="Publishable", description="Synthetic")
    )
    result = approve(
        fabric,
        principal,
        record.memory_id,
        ConsequencePreviewRequest(
            action="move_to_space",
            target_space_id=space["space_id"],
            reason="Operator accepts explicit declassification.",
        ),
    )
    assert result["record"]["privacy"] == MemoryPrivacy.NORMAL.value
    assert result["record"]["body"] == "DECLASSIFICATION_CANARY"
    assert result["record"]["egress_allowed"] is False


def test_private_keys_follow_login_logout_and_password_rewrap(tmp_path):
    store = make_store(tmp_path)
    old_password = "original account password"
    new_password = "replacement account password"
    store.create_account(AccountCreateRequest(username="key-owner", password=old_password))
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    first_principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    record = fabric.create(
        first_principal,
        request("Encrypted continuity", "PRIVATE_RELOGIN_CANARY", privacy="private"),
    )

    with pytest.raises(MemoryEncryptionError):
        fabric.encryption.unlock_sealed(
            principal=first_principal,
            password="wrong password",
            ttl_seconds=60,
        )
    with pytest.raises(SealedMemoryLockedError):
        fabric.encryption.sealed_key(first_principal)

    store.logout()
    with pytest.raises(MemoryEncryptionError):
        fabric.get(first_principal, record.memory_id)

    store.login(AccountLoginRequest(username="key-owner", password=old_password))
    second_principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    assert fabric.get(second_principal, record.memory_id).body == "PRIVATE_RELOGIN_CANARY"

    _, changed = store.update_profile(
        AccountProfileUpdateRequest(
            current_password=old_password,
            password=new_password,
        )
    )
    assert changed is True
    store.logout()
    with pytest.raises(Exception):
        store.login(AccountLoginRequest(username="key-owner", password=old_password))
    store.login(AccountLoginRequest(username="key-owner", password=new_password))
    third_principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    assert fabric.get(third_principal, record.memory_id).body == "PRIVATE_RELOGIN_CANARY"


def test_schema_foreign_keys_wal_uuid7_and_concurrent_transactions(tmp_path):
    store = make_store(tmp_path)
    store.create_account(
        AccountCreateRequest(username="concurrency", password="concurrency account password")
    )
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)

    health = repository.health()
    assert health["schema_version"] == 4
    assert health["foreign_keys_enabled"] is True
    assert health["foreign_key_violations"] == 0
    assert health["journal_mode"] == "wal"

    def create_one(index: int):
        return fabric.create(
            principal,
            request(f"Concurrent {index}", f"CONCURRENT_BODY_{index}"),
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        records = list(executor.map(create_one, range(18)))
    assert len({record.memory_id for record in records}) == 18
    parsed = [UUID(record.memory_id.removeprefix("memory_")) for record in records]
    assert all(identifier.version == 7 for identifier in parsed)
    with repository.connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0] == 18


def test_privacy_transition_reencrypts_entire_revision_history_and_refuses_stale_approval(tmp_path):
    store = make_store(tmp_path)
    store.create_account(
        AccountCreateRequest(username="transition", password="transition account password")
    )
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    record = fabric.create(
        principal,
        request("Revision zero", "PLAINTEXT_HISTORY_CANARY_ZERO"),
    )
    fabric.correct(
        principal,
        record.memory_id,
        MemoryCorrectionRequest(
            body="PLAINTEXT_HISTORY_CANARY_ONE",
            reason="Create a second normal revision.",
        ),
    )
    projection = FtsMemoryProjection(
        paths=store.elysia_paths,
        repository=repository,
        fabric=fabric,
    )
    assert projection.search(principal, "PLAINTEXT HISTORY CANARY")
    preview = fabric.preview_consequence(
        principal,
        record.memory_id,
        ConsequencePreviewRequest(
            action="change_privacy",
            target_privacy="private",
            reason="Encrypt all historical revisions.",
        ),
    )
    transition = fabric.apply_consequence(
        principal,
        record.memory_id,
        ConsequenceApplyRequest(
            approval_id=preview["approval_id"],
            approval_token=preview["approval_token"],
        ),
    )
    database_bytes = repository.database_path.read_bytes()
    assert b"PLAINTEXT_HISTORY_CANARY_ZERO" not in database_bytes
    assert b"PLAINTEXT_HISTORY_CANARY_ONE" not in database_bytes
    assert transition["derived_projection_purge"]["plaintext_projection_present"] is False
    projection_bytes = b"".join(
        path.read_bytes()
        for path in (
            store.elysia_paths.memory_fts_database_path,
            Path(str(store.elysia_paths.memory_fts_database_path) + "-wal"),
            Path(str(store.elysia_paths.memory_fts_database_path) + "-shm"),
        )
        if path.exists()
    )
    assert b"PLAINTEXT_HISTORY_CANARY_ZERO" not in projection_bytes
    assert b"PLAINTEXT_HISTORY_CANARY_ONE" not in projection_bytes
    with repository.connect() as conn:
        formats = {
            row[0]
            for row in conn.execute(
                "SELECT content_format FROM memory_revisions WHERE memory_id = ?",
                (record.memory_id,),
            )
        }
    assert formats == {"json/aesgcm-account"}

    stale = fabric.preview_consequence(
        principal,
        record.memory_id,
        ConsequencePreviewRequest(
            action="hard_delete", reason="Stale approval proof."
        ),
    )
    fabric.pin(principal, record.memory_id, MemoryPinRequest(pinned=True))
    with pytest.raises(MemoryApprovalError, match="changed"):
        fabric.apply_consequence(
            principal,
            record.memory_id,
            ConsequenceApplyRequest(
                approval_id=stale["approval_id"],
                approval_token=stale["approval_token"],
            ),
        )
    with pytest.raises(MemoryApprovalError, match="token"):
        fresh = fabric.preview_consequence(
            principal,
            record.memory_id,
            ConsequencePreviewRequest(
                action="hard_delete", reason="Tamper proof."
            ),
        )
        fabric.apply_consequence(
            principal,
            record.memory_id,
            ConsequenceApplyRequest(
                approval_id=fresh["approval_id"], approval_token="tampered-token"
            ),
        )


def test_sealed_ttl_process_relock_and_encrypted_backup_restore(monkeypatch, tmp_path):
    store = make_store(tmp_path)
    password = "sealed backup account password"
    store.create_account(AccountCreateRequest(username="vault", password=password))
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    monotonic = 10_000.0
    monkeypatch.setattr("app.memory.encryption_service.time.monotonic", lambda: monotonic)
    fabric.encryption.unlock_sealed(
        principal=principal, password=password, ttl_seconds=30
    )
    sealed = fabric.create(
        principal,
        request("Vault backup", "SEALED_BACKUP_CANARY", privacy="sealed"),
    )
    backup = repository.paths.memory_backup_dir / "synthetic-restore.sqlite"
    repository.backup(backup)
    assert b"SEALED_BACKUP_CANARY" not in backup.read_bytes()

    monotonic = 10_031.0
    with pytest.raises(SealedMemoryLockedError):
        fabric.encryption.sealed_key(principal)
    assert fabric.get(principal, sealed.memory_id).content_state == "sealed_locked"
    fabric.encryption.relock(principal.user_id)
    with pytest.raises(SealedMemoryLockedError):
        fabric.encryption.sealed_key(principal)

    restored_path = repository.paths.memory_backup_dir / "restored.sqlite"
    shutil.copy2(backup, restored_path)
    restored = MemoryFabricService(
        repository=MemoryRepository(paths=store.elysia_paths, database_path=restored_path)
    )
    restored.encryption.unlock_sealed(
        principal=principal, password=password, ttl_seconds=30
    )
    assert restored.get(principal, sealed.memory_id).body == "SEALED_BACKUP_CANARY"
