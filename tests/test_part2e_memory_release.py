from __future__ import annotations

import base64
from hashlib import sha256
from pathlib import Path

import pytest

import app.api.artifact_service as artifact_service
import app.api.account_service as account_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.artifact_service import (
    build_generated_media_artifact_record,
    save_artifact_record,
)
from app.api.schemas.account import AccountCreateRequest
from app.cognition.emergency_control import release_request, request_cancel_event
from app.memory.canonical_models import (
    CandidateDecisionRequest,
    ConsequenceApplyRequest,
    ConsequencePreviewRequest,
    MemoryArchiveExportRequest,
    MemoryArchiveRestoreApplyRequest,
    MemoryArchiveRestorePreviewRequest,
    MemoryCandidateCreateRequest,
    MemoryCreateRequest,
    MemoryForm,
    MemoryFormActionRequest,
    MemoryCorrectionRequest,
    MemoryRelationCreateRequest,
    MemoryPrincipal,
    MemoryPrivacy,
    MemoryQuery,
    MemorySuppressionRequest,
    MemoryTierRequest,
    SharedSpaceCreateRequest,
)
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryAuthorizationError, MemoryFabricService
from app.memory.release_service import MemoryReleaseError, MemoryReleaseService


PASSWORD = "synthetic memory release password"


def store_at(root: Path, username: str = "release-owner") -> AccountStore:
    identity = root / "profile" / "identity"
    store = AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )
    store.create_account(AccountCreateRequest(username=username, password=PASSWORD))
    return store


def services(store: AccountStore):
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    release = MemoryReleaseService(fabric=fabric)
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    return repository, fabric, release, principal


def create_request(form: str, *, privacy: str = "normal", index: int = 0):
    form_data = {
        "episodic": {"actors": ["synthetic-agent"], "outcome": "observed"},
        "semantic": {"confirmation": "explicit"},
        "procedural": {"steps": ["inspect", "verify"], "verified": False},
        "prospective": {"due_at": "2030-01-01T00:00:00Z", "state": "pending"},
        "relational": {"relation": "supports", "target": "synthetic-project"},
        "predictive": {"basis": "synthetic baseline", "prediction": "improves"},
        "corrective": {"change_kind": "direct_correction"},
        "metacognitive": {"metric": "retrieval_precision", "value": 0.8},
        "audit": {"event_code": "synthetic_operation", "content_minimized": True},
    }[form]
    return MemoryCreateRequest(
        title=f"{form} {index}",
        body=f"SYNTHETIC_{form.upper()}_{index}",
        why_stored="Synthetic Part 2E proof.",
        form=form,
        privacy=privacy,
        form_data=form_data,
        observed_at="2026-08-22T00:00:00Z",
    )


def test_all_nine_forms_have_stateful_behavior(tmp_path):
    store = store_at(tmp_path)
    _repository, fabric, release, principal = services(store)
    records = {
        form.value: fabric.create(principal, create_request(form.value))
        for form in MemoryForm
    }
    assert set(records) == {form.value for form in MemoryForm}
    assert records["procedural"].form_data["steps"] == ["inspect", "verify"]

    prospective = release.form_action(
        principal,
        records["prospective"].memory_id,
        MemoryFormActionRequest(action="complete", reason="Synthetic task completed."),
    )["record"]
    assert prospective["form_data"]["state"] == "completed"

    prediction = release.form_action(
        principal,
        records["predictive"].memory_id,
        MemoryFormActionRequest(
            action="record_outcome",
            reason="Synthetic calibration.",
            outcome="Observed improvement",
            outcome_score=0.75,
        ),
    )["record"]
    assert prediction["form_data"]["prediction_frozen"] is True
    assert prediction["form_data"]["outcome_score"] == 0.75

    procedure = release.form_action(
        principal,
        records["procedural"].memory_id,
        MemoryFormActionRequest(action="verify_procedure", reason="Steps reproduced."),
    )
    assert procedure["record"]["form_data"]["verified"] is True
    assert procedure["authority_granted"] is False


@pytest.mark.parametrize("privacy", ["normal", "private", "sealed"])
def test_real_cold_offload_retrieval_and_rehydration(tmp_path, privacy):
    store = store_at(tmp_path)
    repository, fabric, release, principal = services(store)
    if privacy == "sealed":
        fabric.encryption.unlock_sealed(principal=principal, password=PASSWORD, ttl_seconds=60)
    canary = f"COLD_{privacy.upper()}_CANARY"
    record = fabric.create(
        principal,
        MemoryCreateRequest(
            title=f"Cold {privacy}",
            body=canary,
            why_stored="Cold rehydration proof.",
            privacy=privacy,
        ),
    )
    moved = release.move_tier(
        principal,
        record.memory_id,
        MemoryTierRequest(tier="cold", reason="Synthetic cold movement."),
    )
    assert moved["record"]["activation_tier"] == "cold"
    with repository.connect() as conn:
        assert bytes(conn.execute(
            "SELECT content_ciphertext FROM memory_revisions WHERE memory_id=?",
            (record.memory_id,),
        ).fetchone()[0]) == b""
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_cold_revisions WHERE memory_id=?",
            (record.memory_id,),
        ).fetchone()[0] == 1
    if privacy in {"private", "sealed"}:
        assert canary.encode() not in release.objects.pack_database.read_bytes()
        assert canary.encode() not in repository.database_path.read_bytes()
    assert fabric.get(principal, record.memory_id).body == canary
    restored = release.move_tier(
        principal,
        record.memory_id,
        MemoryTierRequest(tier="warm", reason="Synthetic repeated usefulness."),
    )
    assert restored["rehydrated"] is True
    assert restored["record"]["body"] == canary
    assert release.tier_history(principal, record.memory_id)["events"][0]["to_tier"] == "warm"


def test_suppression_graph_privacy_and_scoped_object_dedup(tmp_path):
    store = store_at(tmp_path)
    repository, fabric, release, principal = services(store)
    normal = fabric.create(principal, create_request("relational"))
    private = fabric.create(principal, create_request("relational", privacy="private", index=1))
    suppressed = release.suppress(
        principal,
        normal.memory_id,
        MemorySuppressionRequest(suppressed=True, reason="Do not auto-recall."),
    )
    assert suppressed["explicit_lookup_remains_available"] is True
    assert suppressed["automatic_context_admission"] is False
    assert fabric.get(principal, normal.memory_id).body is not None

    fabric.add_relation(
        principal,
        normal.memory_id,
        MemoryRelationCreateRequest(
            target_type="memory",
            target_id=private.memory_id,
            relation_type="private_context",
        ),
    )

    graph = release.rebuild_graph(principal)
    assert graph["private_nodes_persisted"] == 0
    assert release.graph(principal, private.memory_id)["projection_excluded_for_privacy"] is True
    with repository.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_graph_nodes WHERE authority_id=?",
            (private.memory_id,),
        ).fetchone()[0] == 0
    visible_edges = release.graph(principal, normal.memory_id)["edges"]
    assert {edge["relation_type"] for edge in visible_edges} >= {"owned_by", "sourced_from"}
    assert not any(
        edge["node_type"] == "memory" and edge["authority_id"] == private.memory_id
        for edge in visible_edges
    )

    first = release.objects.put(
        principal=principal,
        raw=b"identical synthetic bytes",
        privacy=MemoryPrivacy.NORMAL,
        space_id=None,
        ref_type="memory",
        ref_id=normal.memory_id,
        purpose="attachment",
    )
    second = release.objects.put(
        principal=principal,
        raw=b"identical synthetic bytes",
        privacy=MemoryPrivacy.NORMAL,
        space_id=None,
        ref_type="memory",
        ref_id=normal.memory_id,
        purpose="second-reference",
    )
    assert first["object_id"] == second["object_id"]
    assert second["deduplicated_within_security_domain"] is True


def test_portable_encrypted_archive_clean_profile_restore_and_tamper(tmp_path):
    source_store = store_at(tmp_path / "source", "source-owner")
    _source_repository, source_fabric, source_release, source_principal = services(source_store)
    normal = source_fabric.create(source_principal, create_request("episodic"))
    private = source_fabric.create(source_principal, create_request("semantic", privacy="private"))
    attached = source_release.objects.put(
        principal=source_principal,
        raw=b"SYNTHETIC_PORTABLE_BLOB_BYTES" * 64,
        privacy=MemoryPrivacy.NORMAL,
        space_id=None,
        ref_type="memory",
        ref_id=normal.memory_id,
        purpose="portable-attachment",
        media_type="application/octet-stream",
    )
    exported = source_release.export_archive(
        source_principal,
        MemoryArchiveExportRequest(
            recovery_material="portable synthetic recovery material",
            archive_kind="portable_export",
        ),
    )
    assert exported["portable"] is True
    assert exported["credentials_included"] is False

    target_store = store_at(tmp_path / "target", "target-owner")
    _target_repository, target_fabric, target_release, target_principal = services(target_store)
    preview = target_release.preview_restore(
        target_principal,
        MemoryArchiveRestorePreviewRequest(
            archive_base64=exported["archive_base64"],
            recovery_material="portable synthetic recovery material",
        ),
    )
    assert preview["plan"]["additions"] == 2
    applied = target_release.apply_restore(
        target_principal,
        MemoryArchiveRestoreApplyRequest(
            restore_plan_id=preview["restore_plan_id"],
            approval_id=preview["approval_id"],
            approval_token=preview["approval_token"],
            recovery_material="portable synthetic recovery material",
        ),
    )
    assert applied["restored_record_count"] == 2
    assert applied["restored_object_count"] == 1
    assert applied["projection_rebuild_verified"] is True
    assert applied["projection_results"]["fts"]["state"] == "ready"
    assert target_fabric.get(target_principal, normal.memory_id).body == "SYNTHETIC_EPISODIC_0"
    assert target_fabric.get(target_principal, private.memory_id).body == "SYNTHETIC_SEMANTIC_0"
    assert target_release.objects.read(
        principal=target_principal, object_id=attached["object_id"]
    ) == b"SYNTHETIC_PORTABLE_BLOB_BYTES" * 64

    with pytest.raises(MemoryReleaseError):
        target_release.preview_restore(
            target_principal,
            MemoryArchiveRestorePreviewRequest(
                archive_base64=exported["archive_base64"],
                recovery_material="wrong synthetic recovery material",
            ),
        )
    tampered = bytearray(base64.b64decode(exported["archive_base64"]))
    tampered[-1] ^= 1
    with pytest.raises(MemoryReleaseError):
        target_release.preview_restore(
            target_principal,
            MemoryArchiveRestorePreviewRequest(
                archive_base64=base64.b64encode(tampered).decode(),
                recovery_material="portable synthetic recovery material",
            ),
        )


def test_temporal_truth_candidate_relationship_and_shared_space_restore(tmp_path):
    source_store = store_at(tmp_path / "source-complete", "source-complete-owner")
    source_repository, source_fabric, source_release, source_principal = services(source_store)
    space = source_fabric.create_space(
        source_principal,
        SharedSpaceCreateRequest(label="Synthetic shared continuity", description="Portable proof."),
    )
    shared_request = create_request("semantic").model_dump()
    shared_request.update({"scope": "shared_space", "space_id": space["space_id"]})
    original = source_fabric.create(
        source_principal,
        MemoryCreateRequest.model_validate(shared_request),
    )
    candidate = source_fabric.create_candidate(
        source_principal,
        MemoryCandidateCreateRequest(
            title="Candidate continuity",
            body="SYNTHETIC_CANDIDATE_WORDING",
            why_stored="Synthetic candidate evidence.",
            candidate_kind="consolidation_proposal",
            proposed_wording="Approved wording has not been chosen.",
            evidence_summary="Two synthetic observations.",
        ),
    )
    source_fabric.add_relation(
        source_principal,
        original.memory_id,
        MemoryRelationCreateRequest(
            target_type="memory",
            target_id=candidate.memory_id,
            relation_type="supports",
        ),
    )
    contradictory = source_fabric.correct(
        source_principal,
        original.memory_id,
        MemoryCorrectionRequest(
            body="SYNTHETIC_CONTRADICTORY_CLAIM",
            reason="A conflicting synthetic observation remains unresolved.",
            change_kind="direct_contradiction",
            confidence=0.6,
        ),
    )
    explanation = source_fabric.belief_explanation(source_principal, original.memory_id)
    assert explanation["contradictions"][0]["status"] == "unresolved"
    assert explanation["hidden_reasoning_included"] is False

    exported = source_release.export_archive(
        source_principal,
        MemoryArchiveExportRequest(
            recovery_material="complete portable recovery material",
            archive_kind="portable_export",
        ),
    )
    target_store = store_at(tmp_path / "target-complete", "target-complete-owner")
    target_repository, target_fabric, target_release, target_principal = services(target_store)
    preview = target_release.preview_restore(
        target_principal,
        MemoryArchiveRestorePreviewRequest(
            archive_base64=exported["archive_base64"],
            recovery_material="complete portable recovery material",
        ),
    )
    assert preview["plan"]["shared_spaces_to_create"] == 1
    target_release.apply_restore(
        target_principal,
        MemoryArchiveRestoreApplyRequest(
            restore_plan_id=preview["restore_plan_id"],
            approval_id=preview["approval_id"],
            approval_token=preview["approval_token"],
            recovery_material="complete portable recovery material",
        ),
    )
    restored = target_fabric.get(target_principal, original.memory_id)
    assert restored.space_id == space["space_id"]
    assert restored.owner_user_id == target_principal.user_id
    assert target_fabric.get(target_principal, candidate.memory_id).candidate_proposed_wording
    assert target_fabric.belief_explanation(target_principal, contradictory.memory_id)["contradictions"]
    with target_repository.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM shared_spaces").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM shared_space_members WHERE role='owner'").fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_archive_schema_missing_component_future_and_supported_v1(tmp_path):
    source_store = store_at(tmp_path / "source-schema", "source-schema-owner")
    _repository, fabric, release, principal = services(source_store)
    fabric.create(principal, create_request("semantic"))
    payload = release._logical_export(principal, "full_account")
    recovery = "synthetic archive schema recovery"

    missing = dict(payload)
    missing["records"] = [dict(payload["records"][0])]
    missing["records"][0]["revisions"] = []
    missing_raw = release._encrypt_archive(missing, recovery)
    with pytest.raises(MemoryReleaseError, match="missing a required current revision"):
        release.preview_restore(
            principal,
            MemoryArchiveRestorePreviewRequest(
                archive_base64=base64.b64encode(missing_raw).decode(),
                recovery_material=recovery,
            ),
        )

    missing_manifest = dict(payload)
    missing_manifest.pop("projection_manifest")
    missing_manifest_raw = release._encrypt_archive(missing_manifest, recovery)
    with pytest.raises(MemoryReleaseError, match="missing a required component"):
        release.preview_restore(
            principal,
            MemoryArchiveRestorePreviewRequest(
                archive_base64=base64.b64encode(missing_manifest_raw).decode(),
                recovery_material=recovery,
            ),
        )

    missing_objects = dict(payload)
    missing_objects.pop("objects")
    missing_objects_raw = release._encrypt_archive(missing_objects, recovery)
    with pytest.raises(MemoryReleaseError, match="missing a required component"):
        release.preview_restore(
            principal,
            MemoryArchiveRestorePreviewRequest(
                archive_base64=base64.b64encode(missing_objects_raw).decode(),
                recovery_material=recovery,
            ),
        )

    envelope = release._encrypt_archive(payload, recovery)
    future_manifest = bytearray(envelope)
    # The clear authenticated header is parsed before decryption; changing only
    # its version must fail as unsupported rather than mutate live state.
    text = future_manifest.decode("utf-8")
    text = text.replace('"format_version":2', '"format_version":999', 1)
    with pytest.raises(MemoryReleaseError, match="unsupported future schema"):
        release.preview_restore(
            principal,
            MemoryArchiveRestorePreviewRequest(
                archive_base64=base64.b64encode(text.encode()).decode(),
                recovery_material=recovery,
            ),
        )

    older = dict(payload)
    older["format_version"] = 1
    older["records"] = [dict(payload["records"][0])]
    older["records"][0].pop("candidate", None)
    older["records"][0].pop("truth_events", None)
    older.pop("contradictions", None)
    older.pop("settings_manifest", None)
    older_raw = release._encrypt_archive(older, recovery)
    clean_store = store_at(tmp_path / "target-schema", "target-schema-owner")
    _clean_repository, _clean_fabric, clean_release, clean_principal = services(clean_store)
    preview = clean_release.preview_restore(
        clean_principal,
        MemoryArchiveRestorePreviewRequest(
            archive_base64=base64.b64encode(older_raw).decode(),
            recovery_material=recovery,
        ),
    )
    assert preview["plan"]["format_version"] == 1


def test_exhaustive_delete_rewrites_managed_backups_and_preserves_other_records(tmp_path):
    store = store_at(tmp_path)
    repository, fabric, release, principal = services(store)
    record = fabric.create(principal, create_request("relational"))
    retained = fabric.create(principal, create_request("semantic", index=91))
    release.rebuild_graph(principal)
    release.move_tier(
        principal,
        record.memory_id,
        MemoryTierRequest(tier="cold", reason="Prepare exhaustive purge."),
    )
    managed_material = __import__("hashlib").sha256(
        fabric.encryption.account_key(principal)
    ).hexdigest()
    release.export_archive(
        principal,
        MemoryArchiveExportRequest(
            # Public callers cannot choose or cause Elysia to retain a
            # managed-backup recovery secret.
            recovery_material="ignored synthetic caller material",
            archive_kind="managed_backup",
        ),
    )
    preview = fabric.preview_consequence(
        principal,
        record.memory_id,
        ConsequencePreviewRequest(action="hard_delete", reason="Synthetic exhaustive purge."),
    )
    assert preview["consequence"]["deletion_plan"]["managed_backups"] >= 1
    result = fabric.apply_consequence(
        principal,
        record.memory_id,
        ConsequenceApplyRequest(
            approval_id=preview["approval_id"], approval_token=preview["approval_token"]
        ),
    )
    assert result["absence_verification"]["absent"] is True
    assert result["offline_user_exports_erased"] is False
    with repository.connect() as conn:
        archive = conn.execute(
            "SELECT path_token,checksum,record_count FROM memory_archive_registry"
        ).fetchone()
    assert archive is not None
    assert int(archive["record_count"]) == 1
    raw = (repository.paths.memory_backup_dir / str(archive["path_token"])).read_bytes()
    assert __import__("hashlib").sha256(raw).hexdigest() == str(archive["checksum"])
    payload = release._decrypt_archive(raw, managed_material)
    archived_ids = {
        str(item["record"]["memory_id"]) for item in payload["records"]
    }
    assert record.memory_id not in archived_ids
    assert retained.memory_id in archived_ids


def test_hard_delete_resumes_physical_scrub_after_abrupt_postcommit_failure(
    tmp_path, monkeypatch
):
    store = store_at(tmp_path / "delete-saga")
    repository, fabric, release, principal = services(store)
    record = fabric.create(principal, create_request("audit"))
    release.export_archive(
        principal,
        MemoryArchiveExportRequest(
            recovery_material="ignored synthetic caller material",
            archive_kind="managed_backup",
        ),
    )
    preview = fabric.preview_consequence(
        principal,
        record.memory_id,
        ConsequencePreviewRequest(
            action="hard_delete", reason="Prove durable physical purge recovery."
        ),
    )
    original_secure_purge = repository.secure_purge_deleted_content

    def interrupted_scrub():
        raise RuntimeError("synthetic abrupt exit after canonical commit")

    monkeypatch.setattr(repository, "secure_purge_deleted_content", interrupted_scrub)
    with pytest.raises(RuntimeError, match="synthetic abrupt exit"):
        fabric.apply_consequence(
            principal,
            record.memory_id,
            ConsequenceApplyRequest(
                approval_id=preview["approval_id"],
                approval_token=preview["approval_token"],
            ),
        )
    with repository.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_records WHERE memory_id=?",
            (record.memory_id,),
        ).fetchone()[0] == 0
        operation = conn.execute(
            "SELECT phase,revision_ids_json FROM memory_delete_operations"
        ).fetchone()
    assert operation is not None
    assert str(operation["phase"]) == "canonical_committed"
    assert record.memory_id not in str(operation["revision_ids_json"])

    monkeypatch.setattr(
        repository, "secure_purge_deleted_content", original_secure_purge
    )
    assert MemoryReleaseService.recover_after_restart(repository) == 1
    recovery = release.recover_pending_deletions(principal)
    assert recovery["committed_deletions_completed"] == 1
    assert release.verify_absence(principal, record.memory_id)["absent"] is True
    with repository.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_delete_operations"
        ).fetchone()[0] == 0


def test_governed_jobs_and_homeostasis_never_delete(tmp_path):
    store = store_at(tmp_path)
    repository, fabric, release, principal = services(store)
    fabric.create(principal, create_request("semantic"))
    job = release.submit_job(principal, "graph_rebuild")
    completed = release.run_job(principal, job["job_id"])
    assert completed["state"] == "completed"
    assert release.jobs(principal)["jobs"][0]["state"] == "completed"
    homeostasis = release.homeostasis(principal)
    assert homeostasis["silent_hard_delete_allowed"] is False
    assert homeostasis["response_order"][-1] == "ask_before_delete"
    with repository.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0] == 1


def test_memory_maintenance_emergency_interrupt_and_restart_recovery(tmp_path):
    store = store_at(tmp_path / "emergency-maintenance")
    repository, _fabric, release, principal = services(store)
    job = release.submit_job(principal, "graph_rebuild")
    with repository.transaction() as conn:
        conn.execute(
            "UPDATE memory_jobs SET state='running', cancel_requested=0 WHERE job_id=?",
            (job["job_id"],),
        )

    assert release._interrupt_for_emergency() == 1
    with repository.connect() as conn:
        interrupted = conn.execute(
            "SELECT state,cancel_requested,result_code FROM memory_jobs WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()
    assert tuple(interrupted) == ("interrupted", 1, "emergency_stop")

    # A process crash can leave a job marked running. Startup recovery makes
    # it explicitly resumable without executing or promoting any content.
    with repository.transaction() as conn:
        conn.execute(
            "UPDATE memory_jobs SET state='running', cancel_requested=1 WHERE job_id=?",
            (job["job_id"],),
        )
    assert MemoryReleaseService.recover_after_restart(repository) == 1
    with repository.connect() as conn:
        recovered = conn.execute(
            "SELECT state,cancel_requested,result_code FROM memory_jobs WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()
    assert tuple(recovered) == ("interrupted", 0, "restart_recovery")


def test_complete_public_memory_job_catalog_runs_through_compute_governor(tmp_path):
    store = store_at(tmp_path / "job-catalog")
    _repository, fabric, release, principal = services(store)
    fabric.update_settings(
        principal,
        fabric.settings(principal).model_copy(
            update={"backup_enabled": True, "background_cognition_enabled": True}
        ),
    )
    job_kinds = [
        "conversation_compaction",
        "semantic_candidates",
        "duplicate_detection",
        "relation_candidates",
        "contradiction_scan",
        "project_summary_refresh",
        "tier_maintenance",
        "managed_backup",
        "archive_compression",
        "fts_rebuild",
        "embedding_rebuild",
        "graph_rebuild",
        "object_integrity",
        "projection_rebuild",
        "homeostasis",
        "integrity_check",
        "metacognitive_statistics",
        "consolidation",
        "replay_validation",
    ]
    for job_kind in job_kinds:
        job = release.submit_job(principal, job_kind)
        result = release.run_job(principal, job["job_id"])
        assert result["state"] == "completed", job_kind
    rows = release.jobs(principal, limit=100)["jobs"]
    assert {str(row["job_kind"]).split(":", 1)[1] for row in rows} == set(job_kinds)
    assert all(row["state"] == "completed" for row in rows)


def test_prospective_due_is_restart_safe_and_excludes_sealed(tmp_path):
    store = store_at(tmp_path)
    _repository, fabric, release, principal = services(store)
    due = fabric.create(
        principal,
        MemoryCreateRequest(
            title="Synthetic due reminder",
            body="Synthetic local reminder body",
            why_stored="Prospective lifecycle proof.",
            form="prospective",
            form_data={"due_at": "2026-08-22T00:00:00Z", "state": "pending"},
        ),
    )
    fabric.encryption.unlock_sealed(
        principal=principal, password=PASSWORD, ttl_seconds=60
    )
    fabric.create(
        principal,
        MemoryCreateRequest(
            title="Synthetic sealed reminder",
            body="SEALED_REMINDER_CANARY",
            why_stored="Sealed notification exclusion proof.",
            form="prospective",
            privacy="sealed",
            form_data={"due_at": "2026-08-22T00:00:00Z", "state": "pending"},
        ),
    )
    # A new service instance models process restart: due state is canonical.
    restarted = MemoryReleaseService(fabric=fabric).prospective_due(
        principal, horizon_hours=24
    )
    assert [item["memory_id"] for item in restarted["due"]] == [due.memory_id]
    assert restarted["sealed_records_excluded_count"] == 1
    assert restarted["external_delivery_performed"] is False


def test_object_integrity_job_recovers_only_orphan_pack_rows(tmp_path):
    store = store_at(tmp_path)
    _repository, fabric, release, principal = services(store)
    record = fabric.create(principal, create_request("semantic"))
    referenced = release.objects.put(
        principal=principal,
        raw=b"SYNTHETIC_REFERENCED_OBJECT",
        privacy=MemoryPrivacy.NORMAL,
        space_id=None,
        ref_type="cold_revision",
        ref_id="synthetic-revision",
        purpose="test",
    )
    release.objects._pack_put("pack-synthetic-interrupted-write", b"orphan")
    assert release.objects.verify(principal=principal)["orphan_object_count"] == 1
    job = release.submit_job(principal, "object_integrity")
    result = release.run_job(principal, job["job_id"])["result"]
    assert result["state"] == "ready"
    assert result["orphan_recovery"]["orphan_pack_rows_removed"] == 1
    assert release.objects.read(
        principal=principal, object_id=referenced["object_id"]
    ) == b"SYNTHETIC_REFERENCED_OBJECT"
    assert fabric.get(principal, record.memory_id).body is not None


@pytest.mark.parametrize("profile", ["core_local", "minimal_local"])
def test_object_store_round_trips_every_promoted_zstd_profile(tmp_path, profile):
    store = store_at(tmp_path / profile)
    _repository, fabric, release, principal = services(store)
    fabric.update_settings(
        principal,
        fabric.settings(principal).model_copy(
            update={"storage_resource_profile": profile}
        ),
    )
    raw = (f"SYNTHETIC_{profile}_ZSTD" * 2_000).encode()
    stored = release.objects.put(
        principal=principal,
        raw=raw,
        privacy=MemoryPrivacy.NORMAL,
        space_id=None,
        ref_type="memory",
        ref_id=f"synthetic-{profile}",
        purpose="compression-profile-proof",
    )
    assert stored["compression"] in {"zstd-6", "zstd-12"}
    assert release.objects.read(
        principal=principal, object_id=stored["object_id"]
    ) == raw


def test_generated_artifact_adoption_is_shared_and_rollback_safe(tmp_path, monkeypatch):
    store = store_at(tmp_path / "artifact-owner")
    repository, _fabric, release, principal = services(store)
    monkeypatch.setattr(artifact_service, "current_user_id", lambda: principal.user_id)
    monkeypatch.setattr(account_service, "AccountStore", lambda: store)
    monkeypatch.setattr(
        "app.memory.object_store.MemoryObjectStore", lambda: release.objects
    )

    output = tmp_path / "synthetic-output.bin"
    output.write_bytes(b"synthetic generated artifact bytes")
    media_result = {
        "status": "completed",
        "artifact_kind": "generated_image",
        "output_path": str(output),
        "output_sha256": sha256(output.read_bytes()).hexdigest(),
        "output_bytes": output.stat().st_size,
        "mime_type": "application/octet-stream",
        "model_id": "synthetic-local-model",
        "worker_key": "synthetic-worker",
        "title": "Synthetic generated artifact",
        "summary": "Synthetic generated artifact adoption proof.",
    }
    record = build_generated_media_artifact_record(
        media_result,
        artifact_root=tmp_path / "artifacts",
        artifact_id="artifact_synthetic_adoption",
    )
    saved = save_artifact_record(record)
    assert saved.object_authority == "xdg_content_addressed_objects_v1"
    assert saved.object_id
    assert release.objects.read(
        principal=principal, object_id=str(saved.object_id)
    ) == output.read_bytes()
    assert output.is_file()  # established generated-output surface is preserved

    second_output = tmp_path / "synthetic-failed-output.bin"
    second_output.write_bytes(b"synthetic failed adoption bytes")
    blocked_artifact_root = tmp_path / "artifact-root-is-a-file"
    blocked_artifact_root.write_text("synthetic blocker", encoding="utf-8")
    failed_record = build_generated_media_artifact_record(
        {
            **media_result,
            "output_path": str(second_output),
            "output_sha256": sha256(second_output.read_bytes()).hexdigest(),
            "output_bytes": second_output.stat().st_size,
        },
        artifact_root=blocked_artifact_root,
        artifact_id="artifact_synthetic_rollback",
    )
    with pytest.raises(OSError):
        save_artifact_record(failed_record)
    with repository.connect() as conn:
        dangling = conn.execute(
            "SELECT COUNT(*) FROM memory_object_refs WHERE ref_type='artifact' AND ref_id=?",
            ("artifact_synthetic_rollback",),
        ).fetchone()[0]
    assert int(dangling) == 0


def test_restore_projection_failure_rolls_back_live_canonical_and_objects(
    tmp_path, monkeypatch
):
    source_store = store_at(tmp_path / "rollback-source", "rollback-source")
    _source_repository, source_fabric, source_release, source_principal = services(
        source_store
    )
    imported = source_fabric.create(source_principal, create_request("semantic", index=44))
    source_release.objects.put(
        principal=source_principal,
        raw=b"SYNTHETIC_ROLLBACK_OBJECT" * 100,
        privacy=MemoryPrivacy.NORMAL,
        space_id=None,
        ref_type="memory",
        ref_id=imported.memory_id,
        purpose="rollback-proof",
    )
    exported = source_release.export_archive(
        source_principal,
        MemoryArchiveExportRequest(
            recovery_material="restore rollback recovery material",
            archive_kind="portable_export",
        ),
    )

    target_store = store_at(tmp_path / "rollback-target", "rollback-target")
    target_repository, target_fabric, target_release, target_principal = services(
        target_store
    )
    retained = target_fabric.create(target_principal, create_request("episodic", index=45))
    preview = target_release.preview_restore(
        target_principal,
        MemoryArchiveRestorePreviewRequest(
            archive_base64=exported["archive_base64"],
            recovery_material="restore rollback recovery material",
        ),
    )

    from app.cognition.fts_projection import FtsMemoryProjection

    monkeypatch.setattr(
        FtsMemoryProjection,
        "repair_and_rebuild",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic projection failure")),
    )
    with pytest.raises(MemoryReleaseError, match="rolled back"):
        target_release.apply_restore(
            target_principal,
            MemoryArchiveRestoreApplyRequest(
                restore_plan_id=preview["restore_plan_id"],
                approval_id=preview["approval_id"],
                approval_token=preview["approval_token"],
                recovery_material="restore rollback recovery material",
            ),
        )
    assert target_fabric.get(target_principal, retained.memory_id).body == "SYNTHETIC_EPISODIC_45"
    with pytest.raises(Exception):
        target_fabric.get(target_principal, imported.memory_id)
    with target_repository.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_object_refs WHERE ref_id=?",
            (imported.memory_id,),
        ).fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_portable_sealed_archive_reencrypts_for_clean_installation(tmp_path):
    source_store = store_at(tmp_path / "source-sealed", "source-sealed-owner")
    source_repository, source_fabric, source_release, source_principal = services(source_store)
    source_fabric.encryption.unlock_sealed(
        principal=source_principal, password=PASSWORD, ttl_seconds=60
    )
    record = source_fabric.create(
        source_principal,
        MemoryCreateRequest(
            title="Synthetic sealed portability",
            body="SEALED_PORTABLE_CANARY",
            why_stored="Synthetic sealed restore proof.",
            privacy="sealed",
        ),
    )
    exported = source_release.export_archive(
        source_principal,
        MemoryArchiveExportRequest(
            recovery_material="sealed portable recovery material",
            archive_kind="portable_export",
        ),
    )
    assert b"SEALED_PORTABLE_CANARY" not in base64.b64decode(
        exported["archive_base64"]
    )

    target_store = store_at(tmp_path / "target-sealed", "target-sealed-owner")
    target_repository, target_fabric, target_release, target_principal = services(target_store)
    target_fabric.encryption.unlock_sealed(
        principal=target_principal, password=PASSWORD, ttl_seconds=60
    )
    preview = target_release.preview_restore(
        target_principal,
        MemoryArchiveRestorePreviewRequest(
            archive_base64=exported["archive_base64"],
            recovery_material="sealed portable recovery material",
        ),
    )
    target_release.apply_restore(
        target_principal,
        MemoryArchiveRestoreApplyRequest(
            restore_plan_id=preview["restore_plan_id"],
            approval_id=preview["approval_id"],
            approval_token=preview["approval_token"],
            recovery_material="sealed portable recovery material",
        ),
    )
    assert target_fabric.get(target_principal, record.memory_id).body == "SEALED_PORTABLE_CANARY"
    assert b"SEALED_PORTABLE_CANARY" not in target_repository.database_path.read_bytes()


def test_schema_upgrade_failure_restores_verified_preupgrade_snapshot(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    repository, fabric, _release, principal = services(store)
    record = fabric.create(principal, create_request("semantic", index=73))
    with repository.transaction() as conn:
        conn.execute("DELETE FROM schema_migrations WHERE schema_version=4")
        conn.execute(
            """
            INSERT OR REPLACE INTO schema_migrations (
                schema_version,migration_name,applied_at,source_hash,result,
                rollback_metadata_json
            ) VALUES (2,'synthetic-v2',?,'synthetic','applied','{}')
            """,
            ("2026-08-21T00:00:00Z",),
        )

    def fail_after_mutation(_rollback_metadata):
        with repository.connect() as conn:
            conn.execute(
                "UPDATE memory_records SET title='MUTATED_DURING_FAILED_UPGRADE' WHERE memory_id=?",
                (record.memory_id,),
            )
        raise RuntimeError("synthetic schema failure")

    monkeypatch.setattr(repository, "_initialize_unchecked", fail_after_mutation)
    with pytest.raises(RuntimeError, match="synthetic schema failure"):
        repository.initialize()
    with repository.connect() as conn:
        row = conn.execute(
            "SELECT title FROM memory_records WHERE memory_id=?", (record.memory_id,)
        ).fetchone()
        version = conn.execute("SELECT MAX(schema_version) FROM schema_migrations").fetchone()[0]
    assert row["title"] == "semantic 73"
    assert int(version) == 2
    assert list(repository.paths.memory_backup_dir.glob("pre-schema-v2-to-v4-*.sqlite"))
    assert list(repository.paths.memory_checkpoints_dir.glob("failed-schema-v2-to-v4-*.sqlite"))


def test_consolidation_is_deterministic_candidate_and_replay_never_trains(tmp_path):
    store = store_at(tmp_path)
    repository, fabric, release, principal = services(store)
    first = fabric.create(principal, create_request("semantic", index=8))
    second = fabric.create(principal, create_request("semantic", index=8))
    consolidation_job = release.submit_job(principal, "consolidation")
    consolidated = release.run_job(principal, consolidation_job["job_id"])
    assert consolidated["result"]["candidate_count"] == 1
    candidates, total = fabric.list(
        principal, MemoryQuery(status="candidate", limit=20)
    )
    assert total == 1
    proposal = candidates[0]
    assert proposal.candidate_kind == "consolidation_duplicate_set"
    assert proposal.form_data["model_generated"] is False
    fabric.decide_candidate(
        principal,
        proposal.memory_id,
        CandidateDecisionRequest(
            decision="approve", reason="Synthetic owner approved exact supersession."
        ),
    )
    with repository.connect() as conn:
        states = {
            str(row["memory_id"]): str(row["status"])
            for row in conn.execute(
                "SELECT memory_id, status FROM memory_records WHERE memory_id IN (?,?)",
                (first.memory_id, second.memory_id),
            ).fetchall()
        }
    assert sorted(states.values()) == ["active", "superseded"]

    replay_job = release.submit_job(principal, "replay_validation")
    replay = release.run_job(principal, replay_job["job_id"])["result"]
    assert replay["model_training_performed"] is False
    assert replay["memory_mutated"] is False


def test_recording_control_and_default_privacy_are_enforced_by_canonical_writer(tmp_path):
    store = store_at(tmp_path)
    _repository, fabric, _release, principal = services(store)
    settings = fabric.settings(principal)
    fabric.update_settings(
        principal,
        settings.model_copy(
            update={
                "memory_recording_enabled": False,
                "default_privacy": MemoryPrivacy.PRIVATE,
            }
        ),
    )
    with pytest.raises(MemoryAuthorizationError, match="disabled in Settings"):
        fabric.create(
            principal,
            MemoryCreateRequest(
                title="Blocked capture",
                body="SYNTHETIC_BLOCKED_CAPTURE",
                why_stored="Settings enforcement proof.",
            ),
        )
    fabric.update_settings(
        principal,
        fabric.settings(principal).model_copy(update={"memory_recording_enabled": True}),
    )
    record = fabric.create(
        principal,
        MemoryCreateRequest(
            title="Default-private capture",
            body="SYNTHETIC_DEFAULT_PRIVATE",
            why_stored="Default privacy enforcement proof.",
        ),
    )
    assert record.privacy == MemoryPrivacy.PRIVATE
    assert record.title == "Default-private capture"


def test_legacy_private_and_sealed_raw_hashes_upgrade_only_after_authorization(tmp_path):
    store = store_at(tmp_path)
    repository, fabric, _release, principal = services(store)
    fabric.encryption.unlock_sealed(
        principal=principal, password=PASSWORD, ttl_seconds=60
    )
    private = fabric.create(principal, create_request("semantic", privacy="private", index=81))
    sealed = fabric.create(principal, create_request("semantic", privacy="sealed", index=82))
    legacy_hashes: dict[str, str] = {}
    with repository.connect() as conn:
        for record in (private, sealed):
            row = conn.execute(
                """
                SELECT v.*, r.privacy FROM memory_revisions v
                JOIN memory_records r ON r.current_revision_id=v.revision_id
                WHERE r.memory_id=?
                """,
                (record.memory_id,),
            ).fetchone()
            plaintext = fabric.encryption.decrypt_content(
                principal=principal,
                privacy=MemoryPrivacy(str(row["privacy"])),
                memory_id=record.memory_id,
                revision_id=str(row["revision_id"]),
                row=row,
            )
            legacy_hashes[record.memory_id] = sha256(plaintext).hexdigest()
    with repository.transaction() as conn:
        for memory_id, digest in legacy_hashes.items():
            conn.execute(
                """
                UPDATE memory_revisions SET plaintext_hash=?, digest_format='legacy-sha256-v1'
                WHERE memory_id=?
                """,
                (digest, memory_id),
            )

    result = fabric.encryption.upgrade_authenticated_digests(
        principal, include_sealed=False
    )
    assert result["protected_digests_upgraded"] == 1
    with repository.connect() as conn:
        formats = {
            str(row["memory_id"]): str(row["digest_format"])
            for row in conn.execute(
                "SELECT memory_id,digest_format FROM memory_revisions WHERE memory_id IN (?,?)",
                (private.memory_id, sealed.memory_id),
            ).fetchall()
        }
    assert formats[private.memory_id] == "hmac-sha256-private-v1"
    assert formats[sealed.memory_id] == "legacy-sha256-v1"

    fabric.encryption.relock(principal.user_id)
    fabric.encryption.unlock_sealed(
        principal=principal, password=PASSWORD, ttl_seconds=60
    )
    with repository.connect() as conn:
        sealed_row = conn.execute(
            "SELECT plaintext_hash,digest_format FROM memory_revisions WHERE memory_id=?",
            (sealed.memory_id,),
        ).fetchone()
    assert sealed_row["digest_format"] == "hmac-sha256-sealed-v1"
    assert sealed_row["plaintext_hash"] != legacy_hashes[sealed.memory_id]
    database_bytes = repository.database_path.read_bytes()
    assert all(digest.encode() not in database_bytes for digest in legacy_hashes.values())


def test_candidate_behavior_direct_explicit_only_blocks_inferred_capture(tmp_path):
    store = store_at(tmp_path)
    _repository, fabric, _release, principal = services(store)
    fabric.update_settings(
        principal,
        fabric.settings(principal).model_copy(
            update={"candidate_behavior": "direct_explicit_only"}
        ),
    )
    with pytest.raises(MemoryAuthorizationError, match="inferred candidate capture"):
        fabric.create_candidate(
            principal,
            MemoryCandidateCreateRequest(
                title="Synthetic inferred preference",
                body="SYNTHETIC_INFERRED_PREFERENCE",
                why_stored="Candidate policy proof.",
                candidate_kind="personal_inference",
            ),
        )
    explicit = fabric.create_candidate(
        principal,
        MemoryCandidateCreateRequest(
            title="Synthetic explicit teaching candidate",
            body="SYNTHETIC_EXPLICIT_TEACHING",
            why_stored="The operator explicitly asked for review.",
            candidate_kind="user_submitted_candidate",
            source={"source_authority": "user"},
        ),
    )
    assert explicit.status.value == "candidate"


def test_automatic_scheduler_honors_user_autonomy_and_foreground_preemption(
    tmp_path, monkeypatch
):
    store = store_at(tmp_path)
    _repository, fabric, release, principal = services(store)
    monkeypatch.setattr(release, "_device_power_allows_background", lambda: True)
    assert release.schedule_due_jobs(principal)["state"] == (
        "disabled_by_user_or_managed_control"
    )

    enabled = fabric.settings(principal).model_copy(
        update={
            "background_cognition_enabled": True,
            "autonomy_level": 4,
            "autonomy_domain_overrides": {"background_cognition": 4},
            "max_background_jobs": 2,
        }
    )
    fabric.update_settings(principal, enabled)
    request_cancel_event("synthetic-foreground-request")
    try:
        preempted = release.schedule_due_jobs(principal)
        assert preempted["state"] == "preempted_by_foreground"
        assert preempted["scheduled"] == []
    finally:
        release_request("synthetic-foreground-request")

    scheduled = release.schedule_due_jobs(principal)
    assert scheduled["state"] == "ready"
    assert scheduled["effective_background_cognition_level"] == 4
    assert scheduled["foreground_preemption_enforced"] is True
    assert 1 <= len(scheduled["scheduled"]) <= 2


def test_automatic_scheduler_pauses_on_known_discharging_battery(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    _repository, fabric, release, principal = services(store)
    enabled = fabric.settings(principal).model_copy(
        update={
            "background_cognition_enabled": True,
            "autonomy_level": 4,
            "autonomy_domain_overrides": {"background_cognition": 4},
        }
    )
    fabric.update_settings(principal, enabled)
    monkeypatch.setattr(release, "_device_power_allows_background", lambda: False)
    paused = release.schedule_due_jobs(principal)
    assert paused["state"] == "paused_on_battery"
    assert paused["scheduled"] == []
    assert paused["power_policy"] == "automatic_memory_maintenance_requires_external_power"


def test_managed_profile_memory_ceilings_restrict_authority_not_content(
    tmp_path, monkeypatch
):
    store = store_at(tmp_path / "managed-memory")
    _repository, fabric, release, principal = services(store)
    policy = {
        "consolidation_allowed": False,
        "managed_backups_allowed": False,
        "cold_archive_allowed": False,
        "storage_budget_mb_ceiling": 512,
        "backup_retention_maximum": 1,
        "background_cognition_allowed": False,
        "cpu_percent_ceiling": 10,
        "ram_mb_ceiling": 512,
        "vram_mb_ceiling": 1024,
    }
    monkeypatch.setattr(
        "app.api.account_service.get_authenticated_governance",
        lambda: {"managed": True, "managed_policy": policy},
    )
    settings = fabric.settings(principal)

    with pytest.raises(MemoryAuthorizationError, match="consolidation"):
        fabric.update_settings(
            principal, settings.model_copy(update={"consolidation_enabled": True})
        )
    with pytest.raises(MemoryAuthorizationError, match="managed backups"):
        fabric.update_settings(
            principal,
            settings.model_copy(
                update={"consolidation_enabled": False, "backup_enabled": True}
            ),
        )
    with pytest.raises(MemoryAuthorizationError, match="storage budget"):
        fabric.update_settings(
            principal,
            settings.model_copy(
                update={
                    "consolidation_enabled": False,
                    "storage_budget_mode": "absolute_mb",
                    "storage_budget_value": 1024,
                }
            ),
        )
    with pytest.raises(MemoryAuthorizationError, match="backup retention"):
        fabric.update_settings(
            principal,
            settings.model_copy(
                update={
                    "consolidation_enabled": False,
                    "storage_budget_mode": "absolute_mb",
                    "storage_budget_value": 512,
                    "backup_retention_count": 2,
                }
            ),
        )

    homeostasis = release.homeostasis(principal)
    assert homeostasis["budget"]["managed_profile_ceiling_applied"] is True
    assert homeostasis["budget"]["effective_bytes"] == 512 * 1024 * 1024
    with pytest.raises(MemoryAuthorizationError, match="managed backups"):
        release.export_archive(
            principal,
            MemoryArchiveExportRequest(
                recovery_material="synthetic managed archive recovery",
                archive_kind="managed_backup",
            ),
        )

    record = fabric.create(principal, create_request("semantic"))
    with pytest.raises(MemoryAuthorizationError, match="cold archival"):
        release.move_tier(
            principal,
            record.memory_id,
            MemoryTierRequest(tier="cold", reason="Managed ceiling proof."),
        )
    with pytest.raises(MemoryAuthorizationError, match="consolidation jobs"):
        release.submit_job(principal, "consolidation")

    from app.memory import release_service as release_module

    observed: dict[str, int] = {}
    real_decide_compute = release_module.decide_compute

    def capture_compute(*args, **kwargs):
        observed.update(
            cpu=int(kwargs["cpu_percent_ceiling"]),
            ram=int(kwargs["ram_mb_ceiling"]),
            vram=int(kwargs["vram_mb_ceiling"]),
        )
        # This test owns managed-policy propagation, not live host-pressure
        # sampling.  Keep the resource state deterministic so unrelated CPU
        # load cannot legitimately defer this background job and obscure the
        # exact ceilings supplied by the managed profile.
        return real_decide_compute(
            *args,
            **kwargs,
            resource_state={
                "system": {"cpu_percent": 0, "ram_available_mb": 8192},
                "gpu": {"available": False, "devices": []},
                "ollama_residency": [],
            },
        )

    monkeypatch.setattr(release_module, "decide_compute", capture_compute)
    job = release.submit_job(principal, "graph_rebuild")
    assert release.run_job(principal, job["job_id"])["state"] == "completed"
    assert observed == {"cpu": 10, "ram": 512, "vram": 1024}

    # A queued operation does not retain authority after the Admin ceiling is
    # tightened. Execution re-resolves governance rather than trusting queue-
    # time permission.
    policy["consolidation_allowed"] = True
    queued = release.submit_job(principal, "consolidation")
    policy["consolidation_allowed"] = False
    with pytest.raises(MemoryAuthorizationError, match="consolidation jobs"):
        release.run_job(principal, queued["job_id"])
