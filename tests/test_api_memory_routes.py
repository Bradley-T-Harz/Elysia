from __future__ import annotations

import asyncio

import app.api.account_service as account_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.routes import memory as memory_routes
from app.api.schemas.account import AccountCreateRequest
from app.memory.canonical_models import (
    CandidateDecisionRequest,
    ConsequenceApplyRequest,
    ConsequencePreviewRequest,
    MemoryArchiveExportRequest,
    MemoryArchiveRestorePreviewRequest,
    MemoryCandidateCreateRequest,
    MemoryCorrectionRequest,
    MemoryCreateRequest,
    MemoryFormActionRequest,
    MemoryJobRequest,
    MemoryPinRequest,
    MemoryReasonRequest,
    MemorySuppressionRequest,
    MemorySettings,
    MemoryTierRequest,
    SealedUnlockRequest,
)


PASSWORD = "correct horse battery staple"


def run(coro):
    return asyncio.run(coro)


def get_items(*, search: str | None = None):
    return run(
        memory_routes.get_memory_items(
            search=search,
            scope=None,
            form=None,
            privacy=None,
            status=None,
            space_id=None,
            conversation_id=None,
            project_id=None,
            include_archived=False,
            limit=50,
            offset=0,
        )
    )


def _store_with_account(monkeypatch, tmp_path) -> AccountStore:
    identity = tmp_path / "profile" / "identity"
    store = AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    store.create_account(AccountCreateRequest(username="memory operator", password=PASSWORD))
    return store


def _memory_request(**overrides) -> MemoryCreateRequest:
    payload = {
        "title": "Canonical memory",
        "body": "Durable synthetic memory body.",
        "why_stored": "Explicit test declaration.",
        "scope": "user",
        "form": "semantic",
        "privacy": "normal",
        "source": {
            "source_type": "manual_entry",
            "source_authority": "user",
            "provenance_status": "declared",
        },
    }
    payload.update(overrides)
    return MemoryCreateRequest.model_validate(payload)


def test_memory_summary_and_empty_items_are_canonical(monkeypatch, tmp_path):
    _store_with_account(monkeypatch, tmp_path)

    summary = run(memory_routes.get_memory_summary())
    assert summary["status"] == "ok"
    assert summary["data"]["summary"]["total_items"] == 0
    assert summary["data"]["store_posture"]["source"] == "xdg_sqlite"
    assert summary["data"]["store_posture"]["canonical_writer"] is True
    assert summary["data"]["store_posture"]["legacy_writer_active"] is False
    assert summary["data"]["store_posture"]["write_actions_live"] is True

    items = get_items()
    assert items["status"] == "ok"
    assert items["data"]["items"] == []
    assert items["data"]["total"] == 0


def test_create_correct_archive_restore_pin_and_receipts(monkeypatch, tmp_path):
    _store_with_account(monkeypatch, tmp_path)

    created = run(memory_routes.create_memory(_memory_request()))
    record = created["data"]["record"]
    memory_id = record["memory_id"]
    assert record["body"] == "Durable synthetic memory body."
    assert record["actions"]["can_edit"] is True

    corrected = run(
        memory_routes.correct_memory(
            memory_id,
            MemoryCorrectionRequest(
                body="Corrected durable body.", reason="Operator correction."
            ),
        )
    )
    assert corrected["data"]["record"]["revision_number"] == 2
    assert corrected["data"]["record"]["body"] == "Corrected durable body."

    archived = run(
        memory_routes.archive_memory(
            memory_id, MemoryReasonRequest(reason="Dormant for now.")
        )
    )
    assert archived["data"]["record"]["status"] == "archived"
    restored = run(
        memory_routes.restore_memory(
            memory_id, MemoryReasonRequest(reason="Relevant again.")
        )
    )
    assert restored["data"]["record"]["status"] == "active"
    pinned = run(memory_routes.pin_memory(memory_id, MemoryPinRequest(pinned=True)))
    assert pinned["data"]["record"]["pinned"] is True

    revisions = run(memory_routes.get_revisions(memory_id))
    assert len(revisions["data"]["revisions"]) == 2
    receipts = run(memory_routes.get_receipts(limit=100))["data"]["receipts"]
    assert {row["action"] for row in receipts} >= {
        "created",
        "corrected_superseded_revision",
        "archive",
        "restore",
        "pinned",
    }
    assert "Corrected durable body." not in repr(receipts)


def test_private_is_encrypted_and_sealed_is_explicitly_compartmented(monkeypatch, tmp_path):
    store = _store_with_account(monkeypatch, tmp_path)
    private_secret = "PRIVATE_CANARY_NOT_PLAINTEXT"
    sealed_secret = "SEALED_CANARY_NOT_INDEXED"

    private = run(
        memory_routes.create_memory(
            _memory_request(title="Private title", body=private_secret, privacy="private")
        )
    )
    assert private["data"]["record"]["body"] == private_secret

    unlocked = run(
        memory_routes.unlock_sealed(SealedUnlockRequest(password=PASSWORD, ttl_seconds=60))
    )
    assert unlocked["status"] == "ok"
    sealed = run(
        memory_routes.create_memory(
            _memory_request(title="Sealed title", body=sealed_secret, privacy="sealed")
        )
    )
    sealed_id = sealed["data"]["record"]["memory_id"]
    run(memory_routes.relock_sealed())

    ordinary = get_items(search=sealed_secret)
    assert ordinary["data"]["items"] == []
    summary = run(memory_routes.get_memory_summary())
    assert summary["data"]["summary"]["total_items"] == 1
    assert sealed_secret not in repr(summary)

    locked = run(memory_routes.get_memory(sealed_id))
    assert locked["data"]["record"]["content_state"] == "sealed_locked"
    assert locked["data"]["record"]["body"] is None
    assert sealed_secret not in repr(locked)

    database_bytes = store.elysia_paths.memory_database_path.read_bytes()
    assert private_secret.encode() not in database_bytes
    assert sealed_secret.encode() not in database_bytes


def test_hard_delete_exact_one_time_preview_leaves_content_free_receipt(monkeypatch, tmp_path):
    store = _store_with_account(monkeypatch, tmp_path)
    canary = "PURGE_CANARY_MUST_DISAPPEAR"
    created = run(
        memory_routes.create_memory(_memory_request(body=canary, privacy="private"))
    )
    memory_id = created["data"]["record"]["memory_id"]

    preview = run(
        memory_routes.preview_consequence(
            memory_id,
            ConsequencePreviewRequest(
                action="hard_delete", reason="Exact synthetic purge."
            ),
        )
    )
    approval = preview["data"]["approval"]
    assert approval["one_time"] is True
    assert approval["consequence"]["content_free_receipt_retained"] is True

    request = ConsequenceApplyRequest(
        approval_id=approval["approval_id"],
        approval_token=approval["approval_token"],
    )
    applied = run(memory_routes.apply_consequence(memory_id, request))
    assert applied["data"]["content_retained_in_receipt"] is False
    assert run(memory_routes.apply_consequence(memory_id, request))["status"] == "blocked"
    assert canary.encode() not in store.elysia_paths.memory_database_path.read_bytes()
    receipts = run(memory_routes.get_receipts(limit=100))["data"]["receipts"]
    purge_receipt = next(row for row in receipts if row["action"] == "hard_deleted")
    assert canary not in repr(purge_receipt)
    assert purge_receipt["memory_id"] is None
    assert purge_receipt["old_state_digest"] is None
    assert purge_receipt["new_state_digest"] is None
    assert purge_receipt["scope"] is None
    assert purge_receipt["form"] is None
    assert purge_receipt["privacy"] is None
    fabric, _principal = memory_routes._fabric_and_principal()
    with fabric.repository.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_action_approvals WHERE target_id=?",
            (memory_id,),
        ).fetchone()[0] == 0


def test_candidate_and_foundational_settings_are_persisted(monkeypatch, tmp_path):
    _store_with_account(monkeypatch, tmp_path)
    candidate_request = MemoryCandidateCreateRequest.model_validate(
        {
            **_memory_request().model_dump(mode="json"),
            "status": "candidate",
            "user_confirmed": False,
            "candidate_kind": "personal_inference",
            "inference_kind": "preference_inference",
        }
    )
    candidate = run(memory_routes.create_candidate(candidate_request))
    memory_id = candidate["data"]["record"]["memory_id"]
    approved = run(
        memory_routes.decide_candidate(
            memory_id,
            CandidateDecisionRequest(
                decision="approve", reason="Synthetic operator approval."
            ),
        )
    )
    assert approved["data"]["record"]["status"] == "active"
    assert approved["data"]["record"]["user_confirmed"] is True

    settings = MemorySettings(
        memory_recording_enabled=False,
        storage_resource_profile="minimal_local",
        default_privacy="private",
        candidate_behavior="review_all",
        autonomy_level=2,
        internet_master_enabled=False,
    )
    updated = run(memory_routes.update_settings(settings))
    assert updated["data"]["settings"] == settings.model_dump(mode="json")
    assert run(memory_routes.get_settings())["data"]["settings"] == settings.model_dump(
        mode="json"
    )


def test_part2e_release_routes_use_real_canonical_services(monkeypatch, tmp_path):
    _store_with_account(monkeypatch, tmp_path)
    created = run(
        memory_routes.create_memory(
            _memory_request(
                title="Prospective release route",
                body="Complete the synthetic release proof.",
                form="prospective",
                form_data={
                    "due_at": "2030-01-01T00:00:00Z",
                    "state": "pending",
                },
            )
        )
    )
    memory_id = created["data"]["record"]["memory_id"]

    completed = run(
        memory_routes.apply_memory_form_action(
            memory_id,
            MemoryFormActionRequest(
                action="complete", reason="Synthetic route completion."
            ),
        )
    )
    assert completed["data"]["record"]["form_data"]["state"] == "completed"

    suppressed = run(
        memory_routes.set_memory_automatic_recall(
            memory_id,
            MemorySuppressionRequest(
                suppressed=True, reason="Synthetic route suppression."
            ),
        )
    )
    assert suppressed["data"]["automatic_context_admission"] is False
    moved = run(
        memory_routes.move_memory_tier(
            memory_id,
            MemoryTierRequest(tier="cold", reason="Synthetic route cold proof."),
        )
    )
    assert moved["data"]["record"]["activation_tier"] == "cold"
    restored = run(
        memory_routes.move_memory_tier(
            memory_id,
            MemoryTierRequest(tier="warm", reason="Synthetic route rehydration."),
        )
    )
    assert restored["data"]["rehydrated"] is True
    assert run(memory_routes.get_memory_tier_history(memory_id))["data"]["events"]
    assert run(memory_routes.get_memory_graph(memory_id, limit=100))["data"][
        "authorization_before_traversal"
    ] is True

    archive = run(
        memory_routes.export_memory_archive(
            MemoryArchiveExportRequest(
                recovery_material="synthetic portable recovery material",
                archive_kind="portable_export",
            )
        )
    )["data"]["archive"]
    preview = run(
        memory_routes.preview_memory_archive_restore(
            MemoryArchiveRestorePreviewRequest(
                archive_base64=archive["archive_base64"],
                recovery_material="synthetic portable recovery material",
            )
        )
    )
    assert preview["data"]["restore"]["plan"]["conflicts"]

    homeostasis = run(memory_routes.get_memory_homeostasis())["data"]["homeostasis"]
    assert homeostasis["silent_hard_delete_allowed"] is False
    assert homeostasis["cross_account_accounting_exposed"] is False
    prospective = run(memory_routes.get_due_prospective_memory(horizon_hours=8760))[
        "data"
    ]["prospective"]
    assert prospective["sealed_excluded"] is True
    assert prospective["external_delivery_performed"] is False

    job = run(
        memory_routes.create_memory_job(MemoryJobRequest(job_kind="integrity_check"))
    )["data"]["job"]
    result = run(memory_routes.run_memory_job(job["job_id"]))["data"]["job"]
    assert result["state"] == "completed"
    assert run(memory_routes.get_memory_jobs(limit=10))["data"]["jobs"]
