"""Governed API surface for Elysia's canonical XDG-local Memory Fabric."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.ids import new_id
from app.memory.canonical_models import (
    CandidateDecisionRequest,
    ConsequenceApplyRequest,
    ConsequencePreviewRequest,
    MemoryCandidateCreateRequest,
    MemoryArchiveExportRequest,
    MemoryArchiveRestoreApplyRequest,
    MemoryArchiveRestorePreviewRequest,
    MemoryCorrectionRequest,
    MemoryCreateRequest,
    MemoryFormActionRequest,
    MemoryJobRequest,
    MemoryLifecycle,
    MemoryPinRequest,
    MemoryQuery,
    MemoryRelationCreateRequest,
    MemoryReasonRequest,
    MemorySettings,
    MemorySuppressionRequest,
    MemoryTierRequest,
    SealedUnlockRequest,
    SharedSpaceCreateRequest,
    SharedSpaceInvitationResponseRequest,
)
from app.memory.fabric_service import (
    MemoryApprovalError,
    MemoryAuthorizationError,
    MemoryFabricError,
    MemoryFabricService,
)
from app.memory.migration_service import MemoryMigrationError, MemoryMigrationService
from app.memory.canonical_repository import MemoryRepository, MemoryRepositoryError
from app.memory.encryption_service import MemoryEncryptionError
from app.memory.object_store import MemoryObjectError
from app.memory.release_service import MemoryReleaseError, MemoryReleaseService
from app.cognition.fts_projection import FtsMemoryProjection, FtsProjectionError, PROJECTION_VERSION
from app.cognition.hybrid_retrieval import FUSION_VERSION, HybridMemoryRetriever
from app.cognition.evidence_repository import EvidenceRepository
from app.cognition.semantic_projection import SemanticMemoryProjection, semantic_projection_health


API_VERSION = "0.5.0"
CONTRACT_VERSION = "memory-release-closure-1.0"

router = APIRouter(prefix="/memory", tags=["memory"])


def _envelope(
    *,
    result_type: str,
    data: Any,
    status: EnvelopeStatus = EnvelopeStatus.OK,
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return build_response_envelope(
        status=status,
        request_id=new_id("memreq"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=TraceSummary(
            route_used=f"memory.{result_type}",
            log_written=False,
            journal_written=result_type not in {"memory_summary", "memory_items"},
        ),
        data=data,
    ).to_payload()


def _error(exc: Exception, result_type: str) -> dict[str, Any]:
    approval = (
        ApprovalState.NEEDED
        if isinstance(exc, (MemoryApprovalError, MemoryAuthorizationError))
        else ApprovalState.DENIED
    )
    return _envelope(
        result_type=result_type,
        data={"memory_error": True, "content_returned": False},
        status=EnvelopeStatus.BLOCKED,
        approval_state=approval,
        errors=[str(exc)],
    )


def _run(result_type: str, operation, *, approval: ApprovalState = ApprovalState.NOT_NEEDED):
    try:
        return _envelope(result_type=result_type, data=operation(), approval_state=approval)
    except (
        MemoryFabricError,
        MemoryMigrationError,
        MemoryEncryptionError,
        MemoryRepositoryError,
        FtsProjectionError,
        MemoryObjectError,
        MemoryReleaseError,
        ValueError,
    ) as exc:
        return _error(exc, result_type)


def _fabric_and_principal():
    from app.api.account_service import get_active_elysia_paths

    fabric = MemoryFabricService(
        repository=MemoryRepository(paths=get_active_elysia_paths())
    )
    return fabric, fabric.current_principal()


def _record_payload(record) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    source = record.sources[0] if record.sources else {}
    memory_class = record.legacy_class
    if not memory_class:
        if record.form.value == "audit":
            memory_class = "audit"
        elif record.scope.value in {"conversation", "project", "research", "operational"}:
            memory_class = record.scope.value
        else:
            memory_class = "preference"
    payload.update(
        {
            "summary": record.body if record.body is not None else record.content_state,
            "body_excerpt": record.body,
            "memory_class": memory_class,
            "sensitivity": record.privacy.value,
            "mutability": "review_required" if record.status.value == "candidate" else "live_editable",
            "state": record.status.value,
            "status": record.status.value,
            "is_pinned": record.pinned,
            "is_ephemeral": record.status.value == "working",
            "is_promoted": record.status.value not in {"working", "candidate"},
            "source_type": source.get("source_type"),
            "source_label": source.get("source_label"),
            "source_ref": source.get("source_id"),
            "created_at_utc": record.created_at,
            "updated_at_utc": record.updated_at,
            "provenance": {
                "source_kind": source.get("source_type"),
                "source_ref": source.get("source_id"),
                "source_label": source.get("source_label"),
                "captured_at_utc": source.get("source_time"),
            },
            "context_links": {
                f"{relation['target_type']}_id": relation["target_id"]
                for relation in record.relations
                if relation.get("target_type")
                in {"conversation", "message", "project", "request", "evidence", "artifact"}
            },
            "flags": {
                "pinned": record.pinned,
                "user_declared": record.user_confirmed,
                "inferred": bool(record.inference_kind),
                "verified": record.user_confirmed,
                "stale": record.status.value == "superseded",
            },
            "actions": {
                "can_pin": True,
                "can_move": record.privacy.value != "sealed",
                "can_edit": record.content_state == "available",
                "can_forget": True,
                "reason": "Policy-backed canonical mutation is live.",
            },
        }
    )
    return payload


@router.get("/summary")
async def get_memory_summary() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        summary = fabric.summary(principal)
        summary["class_summaries"] = [
            {"memory_class": key, "total_count": count}
            for key, count in sorted(summary["scope_counts"].items())
        ]
        summary["sensitivity_summaries"] = [
            {"sensitivity": key, "count": count}
            for key, count in sorted(summary["privacy_counts"].items())
        ]
        summary["status_summaries"] = [
            {"status": key, "count": count}
            for key, count in sorted(summary["status_counts"].items())
        ]
        summary["mutability_summaries"] = []
        return {
            "summary": summary,
            "store_posture": {
                "source": "xdg_sqlite",
                "canonical_writer": True,
                "legacy_writer_active": False,
                "retrieval_context_is_memory": False,
                "attached_files_are_memory": False,
                "write_actions_live": True,
            },
        }

    return _run("memory_summary", operation)


@router.get("/items")
async def get_memory_items(
    search: str | None = Query(default=None, max_length=240),
    scope: str | None = Query(default=None, max_length=64),
    form: str | None = Query(default=None, max_length=64),
    privacy: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=64),
    activation_tier: str | None = None,
    space_id: str | None = Query(default=None, max_length=160),
    conversation_id: str | None = Query(default=None, max_length=160),
    project_id: str | None = Query(default=None, max_length=160),
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        query = MemoryQuery.model_validate(
            {
                "search": search,
                "scope": scope,
                "form": form,
                "privacy": privacy,
                "status": status,
                "activation_tier": activation_tier,
                "space_id": space_id,
                "conversation_id": conversation_id,
                "project_id": project_id,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            }
        )
        retrieval_explanations: dict[str, dict[str, Any]] = {}
        if search and activation_tier not in {"cold", "archived"} and not include_archived and status in {None, "active", "working"} and privacy != "sealed":
            projection = FtsMemoryProjection(
                paths=fabric.repository.paths,
                repository=fabric.repository,
                fabric=fabric,
            )
            spaces = fabric.list_spaces(principal)
            space_ids = [
                str(item.get("space_id"))
                for item in spaces
                if item.get("space_id") and item.get("role")
            ]
            ranked: list[dict[str, Any]] = []
            total = 0
            requested_candidates = min(100_000, offset + limit)
            semantic_state = "not_requested"
            if privacy in {None, "normal"}:
                lexical_total = projection.count_search(
                    principal,
                    search,
                    scope=scope,
                    form=form,
                    status=status,
                    space_id=space_id,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    space_ids=space_ids,
                )
                hybrid = HybridMemoryRetriever(lexical=projection).search_normal(
                    principal,
                    search,
                    scope=scope,
                    form=form,
                    status=status,
                    space_id=space_id,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    space_ids=space_ids,
                    limit=requested_candidates,
                )
                semantic_state = hybrid.semantic_state
                total += max(lexical_total, len(hybrid.rows))
                ranked.extend(hybrid.rows)
            if privacy in {None, "private"}:
                private_matches = projection.search_private_ephemeral(
                    principal,
                    search,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    scope=scope,
                    form=form,
                    status=status,
                    limit=100_000,
                )
                total += len(private_matches)
                ranked.extend(private_matches[:requested_candidates])
            ranked.sort(
                key=lambda row: (
                    float(row.get("raw_rank") or 0.0),
                    -float(row.get("importance") or 0.0),
                    str(row.get("candidate_id") or ""),
                )
            )
            selected = ranked[offset : offset + limit]
            records = []
            for rank_position, row in enumerate(selected, start=offset + 1):
                try:
                    record = fabric.get(principal, str(row["candidate_id"]))
                except MemoryFabricError:
                    continue
                records.append(record)
                retrieval_explanations[record.memory_id] = {
                    "rank": rank_position,
                    "method": "authenticated_ephemeral_private" if row.get("ephemeral_private") else str(row.get("retrieval_method") or "sqlite_fts5_bm25"),
                    "projection_version": PROJECTION_VERSION if row.get("ephemeral_private") else FUSION_VERSION,
                    "raw_rank": round(float(row.get("raw_rank") or 0.0), 6),
                    "lexical_rank": row.get("lexical_rank"),
                    "semantic_rank": row.get("semantic_rank"),
                    "semantic_score": round(float(row.get("semantic_score") or 0.0), 6),
                    "fusion_score": round(float(row.get("fusion_score") or 0.0), 6),
                    "source_id": record.memory_id,
                    "privacy_filter_applied_before_return": True,
                    "sealed_excluded": True,
                }
        else:
            records, total = fabric.list(principal, query)
        item_payloads = [_record_payload(record) for record in records]
        for item in item_payloads:
            if item["memory_id"] in retrieval_explanations:
                item["retrieval_explanation"] = retrieval_explanations[item["memory_id"]]
        return {
            "items": item_payloads,
            "total": total,
            "limit": limit,
            "offset": offset,
            "query_truth": {
                "sealed_content_excluded_while_locked": True,
                "ordinary_persistent_semantic_index": bool(search) and semantic_state == "ready",
                "semantic_projection_state": semantic_state if search else "not_requested",
                "semantic_projection_version": FUSION_VERSION,
                "lexical_projection_used": bool(search),
                "lexical_projection_version": PROJECTION_VERSION,
                "private_plaintext_persistently_indexed": False,
                "write_actions_live": True,
            },
        }

    return _run("memory_items", operation)


@router.post("/items")
async def create_memory(payload: MemoryCreateRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"record": _record_payload(fabric.create(principal, payload))}

    return _run("memory_create", operation)


@router.post("/candidates")
async def create_candidate(payload: MemoryCandidateCreateRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"record": _record_payload(fabric.create_candidate(principal, payload))}

    return _run("memory_candidate_create", operation, approval=ApprovalState.NEEDED)


@router.get("/items/{memory_id}")
async def get_memory(memory_id: str) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"record": _record_payload(fabric.get(principal, memory_id))}

    return _run("memory_detail", operation)


@router.get("/items/{memory_id}/revisions")
async def get_revisions(memory_id: str) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"revisions": fabric.revisions(principal, memory_id)}

    return _run("memory_revisions", operation)


@router.post("/items/{memory_id}/correct")
async def correct_memory(memory_id: str, payload: MemoryCorrectionRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"record": _record_payload(fabric.correct(principal, memory_id, payload))}

    return _run("memory_correct", operation)


@router.post("/items/{memory_id}/relations")
async def add_memory_relation(
    memory_id: str, payload: MemoryRelationCreateRequest = Body(...)
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"record": _record_payload(fabric.add_relation(principal, memory_id, payload))}

    return _run("memory_relation_create", operation)


@router.get("/items/{memory_id}/belief-explanation")
async def explain_memory_belief(memory_id: str) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return fabric.belief_explanation(principal, memory_id)

    return _run("memory_belief_explanation", operation)


@router.post("/items/{memory_id}/archive")
async def archive_memory(memory_id: str, payload: MemoryReasonRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        record = fabric.set_status(principal, memory_id, MemoryLifecycle.ARCHIVED, payload)
        return {"record": _record_payload(record)}

    return _run("memory_archive", operation)


@router.post("/items/{memory_id}/restore")
async def restore_memory(memory_id: str, payload: MemoryReasonRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        record = fabric.set_status(principal, memory_id, MemoryLifecycle.ACTIVE, payload)
        return {"record": _record_payload(record)}

    return _run("memory_restore", operation)


@router.put("/items/{memory_id}/pin")
async def pin_memory(memory_id: str, payload: MemoryPinRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"record": _record_payload(fabric.pin(principal, memory_id, payload))}

    return _run("memory_pin", operation)


@router.post("/items/{memory_id}/candidate-decision")
async def decide_candidate(memory_id: str, payload: CandidateDecisionRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"record": _record_payload(fabric.decide_candidate(principal, memory_id, payload))}

    return _run("memory_candidate_decision", operation, approval=ApprovalState.APPROVED)


@router.post("/items/{memory_id}/form-action")
async def apply_memory_form_action(
    memory_id: str, payload: MemoryFormActionRequest = Body(...)
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return MemoryReleaseService(fabric=fabric).form_action(principal, memory_id, payload)

    return _run("memory_form_action", operation)


@router.put("/items/{memory_id}/tier")
async def move_memory_tier(
    memory_id: str, payload: MemoryTierRequest = Body(...)
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return MemoryReleaseService(fabric=fabric).move_tier(principal, memory_id, payload)

    return _run("memory_tier_move", operation)


@router.get("/items/{memory_id}/tier-history")
async def get_memory_tier_history(memory_id: str) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return MemoryReleaseService(fabric=fabric).tier_history(principal, memory_id)

    return _run("memory_tier_history", operation)


@router.put("/items/{memory_id}/automatic-recall")
async def set_memory_automatic_recall(
    memory_id: str, payload: MemorySuppressionRequest = Body(...)
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return MemoryReleaseService(fabric=fabric).suppress(principal, memory_id, payload)

    return _run("memory_automatic_recall", operation)


@router.get("/items/{memory_id}/graph")
async def get_memory_graph(
    memory_id: str, limit: int = Query(default=100, ge=1, le=500)
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return MemoryReleaseService(fabric=fabric).graph(principal, memory_id, limit=limit)

    return _run("memory_graph", operation)


@router.post("/targets/{target_id}/consequences/preview")
async def preview_consequence(target_id: str, payload: ConsequencePreviewRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"approval": fabric.preview_consequence(principal, target_id, payload)}

    return _run("memory_consequence_preview", operation, approval=ApprovalState.NEEDED)


@router.post("/targets/{target_id}/consequences/apply")
async def apply_consequence(target_id: str, payload: ConsequenceApplyRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return fabric.apply_consequence(principal, target_id, payload)

    return _run("memory_consequence_apply", operation, approval=ApprovalState.APPROVED)


@router.post("/sealed/unlock")
async def unlock_sealed(payload: SealedUnlockRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {
            "sealed": fabric.encryption.unlock_sealed(
                principal=principal,
                password=payload.password,
                ttl_seconds=payload.ttl_seconds,
            )
        }

    return _run("memory_sealed_unlock", operation, approval=ApprovalState.APPROVED)


@router.post("/sealed/relock")
async def relock_sealed() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        fabric.encryption.relock(principal.user_id)
        return {"sealed": fabric.encryption.sealed_status(principal), "relocked": True}

    return _run("memory_sealed_relock", operation)


@router.get("/spaces")
async def get_spaces() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"spaces": fabric.list_spaces(principal)}

    return _run("memory_spaces", operation)


@router.post("/spaces")
async def create_space(payload: SharedSpaceCreateRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"space": fabric.create_space(principal, payload)}

    return _run("memory_space_create", operation)


@router.get("/spaces/invitations")
async def get_space_invitations() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"invitations": fabric.list_space_invitations(principal)}

    return _run("memory_space_invitations", operation)


@router.post("/spaces/invitations/{invitation_id}/respond")
async def respond_space_invitation(
    invitation_id: str,
    payload: SharedSpaceInvitationResponseRequest = Body(...),
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {
            "invitation": fabric.respond_space_invitation(
                principal, invitation_id, payload
            )
        }

    return _run("memory_space_invitation_response", operation)


@router.get("/receipts")
async def get_receipts(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"receipts": fabric.receipts(principal, limit=limit)}

    return _run("memory_receipts", operation)


@router.get("/approvals/pending")
async def get_pending_approvals() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"approvals": fabric.pending_approvals(principal)}

    return _run("memory_pending_approvals", operation, approval=ApprovalState.NEEDED)


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"settings": fabric.settings(principal).model_dump(mode="json")}

    return _run("memory_settings", operation)


@router.put("/settings")
async def update_settings(payload: MemorySettings = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {
            "settings": fabric.update_settings(principal, payload).model_dump(mode="json")
        }

    return _run("memory_settings_update", operation)


@router.get("/health")
async def get_health() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        health = fabric.health(principal)
        health["lexical_projection"] = FtsMemoryProjection(
            paths=fabric.repository.paths,
            repository=fabric.repository,
            fabric=fabric,
        ).health()
        health["research_evidence"] = EvidenceRepository(
            paths=fabric.repository.paths
        ).health()
        health["semantic_projection"] = semantic_projection_health(
            paths=fabric.repository.paths,
            repository=fabric.repository,
            fabric=fabric,
        )
        health["release_closure"] = MemoryReleaseService(fabric=fabric).health(principal)
        return {"health": health}

    return _run("memory_health", operation)


@router.post("/projection/rebuild")
async def rebuild_lexical_projection() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        result = FtsMemoryProjection(
            paths=fabric.repository.paths,
            repository=fabric.repository,
            fabric=fabric,
        ).repair_and_rebuild(principal)
        semantic_result: dict[str, Any]
        try:
            semantic = SemanticMemoryProjection(
                paths=fabric.repository.paths,
                repository=fabric.repository,
                fabric=fabric,
            )
            if semantic.configured:
                semantic_result = semantic.rebuild(principal)
            else:
                semantic_result = {
                    "state": "optional_not_installed",
                    "canonical_memory_mutated": False,
                }
        except Exception:
            semantic_result = {
                "state": "degraded",
                "reason": "The optional local semantic profile could not rebuild; FTS remains ready.",
                "canonical_memory_mutated": False,
            }
        return {
            "projection": result,
            "semantic_projection": semantic_result,
            "canonical_memory_mutated": False,
        }

    return _run("memory_projection_rebuild", operation)


@router.get("/migration/status")
async def get_migration_status() -> dict[str, Any]:
    def operation():
        fabric, _principal = _fabric_and_principal()
        return {
            "migration": MemoryMigrationService(repository=fabric.repository).status()
        }

    return _run("memory_migration_status", operation)


@router.post("/migration/apply")
async def apply_migration(
    password: str = Body(..., embed=True, min_length=1, max_length=1024),
) -> dict[str, Any]:
    def operation():
        from app.api.account_service import AccountServiceError, reauthenticate_current

        fabric, principal = _fabric_and_principal()
        try:
            verified = reauthenticate_current(password)
        except AccountServiceError as exc:
            raise MemoryAuthorizationError(str(exc)) from exc
        if verified["user_id"] != principal.user_id:
            raise MemoryAuthorizationError("The authenticated migration principal changed.")
        fabric.encryption.provision_account(
            owner_user_id=principal.user_id,
            password=password,
            session_id=principal.session_id,
            session_token=principal.session_token,
        )
        result = MemoryMigrationService(repository=fabric.repository).migrate(
            principal=principal,
            password=password,
        )
        return {"migration": result}

    return _run("memory_migration_apply", operation, approval=ApprovalState.APPROVED)


@router.get("/backup/status")
async def get_backup_status() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        status = fabric.repository.backup_status()
        archives = MemoryReleaseService(fabric=fabric).archive_status(principal)
        return {
            "backup": {
                "automatic_pre_migration_backup": True,
                "backup_retention_contract": (
                    "Encrypted/XDG-local backups are retained until the operator removes them."
                ),
                **status,
                **archives,
                "raw_path_exposed": False,
            }
        }

    return _run("memory_backup_status", operation)


@router.post("/archives/export")
async def export_memory_archive(
    payload: MemoryArchiveExportRequest = Body(...),
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"archive": MemoryReleaseService(fabric=fabric).export_archive(principal, payload)}

    return _run("memory_archive_export", operation, approval=ApprovalState.APPROVED)


@router.get("/archives")
async def list_memory_archives() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return MemoryReleaseService(fabric=fabric).archive_status(principal)

    return _run("memory_archives", operation)


@router.post("/archives/restore/preview")
async def preview_memory_archive_restore(
    payload: MemoryArchiveRestorePreviewRequest = Body(...),
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"restore": MemoryReleaseService(fabric=fabric).preview_restore(principal, payload)}

    return _run("memory_archive_restore_preview", operation, approval=ApprovalState.NEEDED)


@router.post("/archives/restore/apply")
async def apply_memory_archive_restore(
    payload: MemoryArchiveRestoreApplyRequest = Body(...),
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"restore": MemoryReleaseService(fabric=fabric).apply_restore(principal, payload)}

    return _run("memory_archive_restore_apply", operation, approval=ApprovalState.APPROVED)


@router.get("/homeostasis")
async def get_memory_homeostasis() -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"homeostasis": MemoryReleaseService(fabric=fabric).homeostasis(principal)}

    return _run("memory_homeostasis", operation)


@router.get("/prospective/due")
async def get_due_prospective_memory(
    horizon_hours: int = Query(default=168, ge=0, le=8760),
) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {
            "prospective": MemoryReleaseService(fabric=fabric).prospective_due(
                principal, horizon_hours=horizon_hours
            )
        }

    return _run("memory_prospective_due", operation)


@router.get("/jobs")
async def get_memory_jobs(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return MemoryReleaseService(fabric=fabric).jobs(principal, limit=limit)

    return _run("memory_jobs", operation)


@router.post("/jobs")
async def create_memory_job(payload: MemoryJobRequest = Body(...)) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"job": MemoryReleaseService(fabric=fabric).submit_job(principal, payload.job_kind)}

    return _run("memory_job_create", operation)


@router.post("/jobs/{job_id}/run")
async def run_memory_job(job_id: str) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"job": MemoryReleaseService(fabric=fabric).run_job(principal, job_id)}

    return _run("memory_job_run", operation)


@router.post("/jobs/{job_id}/cancel")
async def cancel_memory_job(job_id: str) -> dict[str, Any]:
    def operation():
        fabric, principal = _fabric_and_principal()
        return {"job": MemoryReleaseService(fabric=fabric).cancel_job(principal, job_id)}

    return _run("memory_job_cancel", operation)


__all__ = ("router",)
