"""Part 2E memory metabolism, teaching, graph, backup, and homeostasis.

This module extends the canonical Memory Fabric.  It does not introduce a
second memory writer: every lifecycle decision and reference is committed to
the canonical SQLite authority, while object/archive bytes remain governed by
those canonical pointers.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
from typing import Any
import zlib
import zstandard

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.cognition.compute_governor import (
    ComputeLedger,
    WorkloadDescriptor,
    decide_compute,
    resource_snapshot,
)
from app.cognition.emergency_control import (
    active_request_count,
    emergency_active,
    register_canceller,
)
from app.cognition.governor import resolve_autonomy_policy
from app.ids import new_id
from app.memory.canonical_models import (
    ActivationTier,
    ConsequenceApplyRequest,
    MemoryArchiveExportRequest,
    MemoryArchiveRestoreApplyRequest,
    MemoryArchiveRestorePreviewRequest,
    MemoryCandidateCreateRequest,
    MemoryContent,
    MemoryCorrectionRequest,
    MemoryForm,
    MemoryFormActionRequest,
    MemoryLifecycle,
    MemoryPrincipal,
    MemoryPrivacy,
    MemoryQuery,
    MemoryRelationCreateRequest,
    MemoryReasonRequest,
    MemorySuppressionRequest,
    MemorySourceInput,
    MemoryTierRequest,
)
from app.memory.canonical_repository import (
    MUTATION_RECEIPT_INSERT,
    MemoryRepository,
    mutation_receipt_row,
    utc_now,
)
from app.memory.fabric_service import (
    APPROVAL_TTL_SECONDS,
    MemoryApprovalError,
    MemoryAuthorizationError,
    MemoryFabricError,
    MemoryFabricService,
    _digest,
    _iso_after,
    _parse_iso,
)
from app.memory.object_store import MemoryObjectError, MemoryObjectStore


ARCHIVE_MAGIC = b"ELYMEM1\n"
ARCHIVE_VERSION = 2
ARCHIVE_KDF = {"name": "scrypt", "n": 32768, "r": 8, "p": 1, "length": 32}
RESTORE_TTL_SECONDS = 900


class MemoryReleaseError(MemoryFabricError):
    """Part 2E operation failed without exposing protected content."""


def _archive_key(material: str, salt: bytes) -> bytes:
    if len(material) < 12:
        raise MemoryReleaseError("Archive recovery material is too short.")
    return Scrypt(
        salt=salt,
        length=32,
        n=int(ARCHIVE_KDF["n"]),
        r=int(ARCHIVE_KDF["r"]),
        p=int(ARCHIVE_KDF["p"]),
    ).derive(material.encode("utf-8"))


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise MemoryReleaseError("The archive component encoding is invalid.") from exc


def _safe_archive_token(archive_id: str) -> str:
    return f"{archive_id}.elysia-memory-archive"


def _authorized_fts_usage(
    database: Path, owner_user_id: str, space_ids: list[str]
) -> dict[str, int]:
    if not database.is_file() or database.is_symlink():
        return {"record_count": 0, "text_bytes": 0}
    try:
        with sqlite3.connect(
            f"file:{database.as_posix()}?mode=ro", uri=True, timeout=1.0
        ) as conn:
            clauses = ["(m.owner_user_id=? AND m.space_id IS NULL)"]
            values: list[Any] = [owner_user_id]
            if space_ids:
                placeholders = ",".join("?" for _ in space_ids)
                clauses.append(f"m.space_id IN ({placeholders})")
                values.extend(space_ids)
            row = conn.execute(
                f"""
                SELECT COUNT(*),COALESCE(SUM(
                    length(f.title)+length(f.body)+length(f.why_stored)
                ),0)
                FROM memory_fts f JOIN memory_fts_meta m
                  ON m.candidate_id=f.candidate_id
                WHERE {' OR '.join(clauses)}
                """,
                values,
            ).fetchone()
        return {"record_count": int(row[0]), "text_bytes": int(row[1])}
    except sqlite3.Error:
        return {"record_count": 0, "text_bytes": 0}


class MemoryReleaseService:
    def __init__(
        self,
        *,
        fabric: MemoryFabricService | None = None,
        repository: MemoryRepository | None = None,
    ) -> None:
        self.repository = repository or (fabric.repository if fabric else MemoryRepository())
        self.repository.initialize()
        self.fabric = fabric or MemoryFabricService(repository=self.repository)
        self.objects = MemoryObjectStore(repository=self.repository)
        self.compute = ComputeLedger(self.repository.paths)
        canceller_name = "part2e_memory_jobs:" + sha256(
            str(self.repository.database_path).encode("utf-8")
        ).hexdigest()[:16]
        register_canceller(canceller_name, self._interrupt_for_emergency)

    @staticmethod
    def _managed_governance() -> tuple[bool, dict[str, Any]]:
        """Resolve current supervision truth without requesting user content."""

        try:
            from app.api.account_service import get_authenticated_governance

            governance = get_authenticated_governance()
        except Exception:
            return False, {}
        return bool(governance.get("managed")), dict(
            governance.get("managed_policy") or {}
        )

    def _interrupt_for_emergency(self) -> int:
        if not self.repository.database_path.exists():
            return 0
        with self.repository.transaction() as conn:
            return int(
                conn.execute(
                    """
                    UPDATE memory_jobs SET state='interrupted',cancel_requested=1,
                        updated_at=?,result_code='emergency_stop',
                        checkpoint_json=json_set(checkpoint_json,'$.interrupted',1)
                    WHERE job_kind LIKE 'part2e:%' AND state IN ('pending','running')
                    """,
                    (utc_now(),),
                ).rowcount
            )

    @staticmethod
    def recover_after_restart(repository: MemoryRepository) -> int:
        """Recover interrupted jobs and finish committed deletion scrubs.

        A committed hard-delete journal is content-free and does not require
        an authenticated account merely to checkpoint/VACUUM canonical
        SQLite. Archive and projection absence is reverified later under the
        owning principal before the journal is removed.
        """

        if not repository.database_path.exists():
            return 0
        repository.initialize()
        with repository.transaction() as conn:
            recovered_jobs = int(
                conn.execute(
                    """
                    UPDATE memory_jobs SET state='interrupted',cancel_requested=0,
                        updated_at=?,result_code='restart_recovery',
                        checkpoint_json=json_set(checkpoint_json,'$.restart_recovered',1)
                    WHERE job_kind LIKE 'part2e:%' AND state='running'
                    """,
                    (utc_now(),),
                ).rowcount
            )
            committed = [
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT deletion_id FROM memory_delete_operations
                    WHERE phase='canonical_committed'
                    ORDER BY created_at,deletion_id
                    """
                ).fetchall()
            ]
        recovered_deletions = 0
        for deletion_id in committed:
            repository.secure_purge_deleted_content()
            with repository.transaction() as conn:
                result = conn.execute(
                    """
                    UPDATE memory_delete_operations
                    SET phase='physical_purged',updated_at=?
                    WHERE deletion_id=? AND phase='canonical_committed'
                    """,
                    (utc_now(), deletion_id),
                )
            recovered_deletions += int(result.rowcount)
        return recovered_jobs + recovered_deletions

    def recover_pending_deletions(
        self, principal: MemoryPrincipal
    ) -> dict[str, Any]:
        """Recover content-free hard-delete sagas for one authenticated owner."""

        with self.repository.connect() as conn:
            pending = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM memory_delete_operations
                    WHERE owner_user_id=? ORDER BY created_at,deletion_id
                    """,
                    (principal.user_id,),
                ).fetchall()
            ]
        restored_precommit = 0
        completed = 0
        for operation in pending:
            deletion_id = str(operation["deletion_id"])
            memory_id = str(operation["memory_id"])
            revision_ids = [
                str(value)
                for value in json.loads(str(operation["revision_ids_json"]))
            ]
            with self.repository.connect() as conn:
                canonical_exists = conn.execute(
                    "SELECT 1 FROM memory_records WHERE memory_id=?",
                    (memory_id,),
                ).fetchone() is not None
            phase = str(operation["phase"])
            if phase == "prepared" and canonical_exists:
                # An abrupt pre-commit exit may have cleared rebuildable
                # projections/managed backups or restored a cold payload.
                # Canonical truth survived, so reconstruct every derived
                # surface and remove the abandoned operation.
                row = self._owned_row(principal, memory_id)
                if (
                    str(operation["original_activation_tier"]) == "cold"
                    and not self._cold_entries(memory_id)
                ):
                    self._offload_cold(principal, row)
                    self._purge_ordinary_projections(principal, memory_id)
                else:
                    self._queue_projection_upserts(principal.user_id, memory_id)
                self.rebuild_graph(principal)
                recovery_material = sha256(
                    self.fabric.encryption.account_key(principal)
                ).hexdigest()
                self.export_archive(
                    principal,
                    MemoryArchiveExportRequest(
                        recovery_material=recovery_material,
                        archive_kind="managed_backup",
                        scope="full_account",
                    ),
                )
                self._enforce_backup_retention(principal)
                with self.repository.transaction() as conn:
                    conn.execute(
                        "DELETE FROM memory_delete_operations WHERE deletion_id=?",
                        (deletion_id,),
                    )
                restored_precommit += 1
                continue
            if canonical_exists:
                raise MemoryReleaseError(
                    "A hard-delete recovery journal conflicts with canonical memory state."
                )
            if phase == "canonical_committed":
                self.repository.secure_purge_deleted_content()
                with self.repository.transaction() as conn:
                    conn.execute(
                        """
                        UPDATE memory_delete_operations
                        SET phase='physical_purged',updated_at=?
                        WHERE deletion_id=?
                        """,
                        (utc_now(), deletion_id),
                    )
            absence = self.verify_absence(
                principal, memory_id, revision_ids=revision_ids
            )
            if not absence["absent"]:
                raise MemoryReleaseError(
                    "A resumed hard delete found retained installation-managed state."
                )
            with self.repository.transaction() as conn:
                conn.execute(
                    "DELETE FROM memory_delete_operations WHERE deletion_id=?",
                    (deletion_id,),
                )
            completed += 1
        return {
            "pending_found": len(pending),
            "precommit_state_restored": restored_precommit,
            "committed_deletions_completed": completed,
            "content_included": False,
        }

    def _cold_entries(self, memory_id: str) -> int:
        with self.repository.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM memory_cold_revisions WHERE memory_id=?",
                    (memory_id,),
                ).fetchone()[0]
            )

    def pending_deletion_status(self, principal: MemoryPrincipal) -> dict[str, Any]:
        """Return content-free saga truth without performing recovery work."""

        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT phase,COUNT(*) AS operation_count
                FROM memory_delete_operations
                WHERE owner_user_id=? GROUP BY phase ORDER BY phase
                """,
                (principal.user_id,),
            ).fetchall()
        by_phase = {str(row["phase"]): int(row["operation_count"]) for row in rows}
        return {
            "pending_count": sum(by_phase.values()),
            "by_phase": by_phase,
            "content_included": False,
            "recovery_runs_through_governed_maintenance": True,
        }

    def _job_cancelled(self, principal: MemoryPrincipal, job_id: str) -> bool:
        if emergency_active(self.repository.paths) or active_request_count() > 0:
            return True
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM memory_jobs WHERE job_id=? AND owner_user_id=?",
                (job_id, principal.user_id),
            ).fetchone()
        return bool(row and row[0])

    @staticmethod
    def _device_power_allows_background() -> bool:
        """Pause automatic maintenance on a known discharging battery.

        Systems without a readable Linux power-supply authority are treated as
        ordinary desktops; this never invents AC/battery telemetry.
        """

        power_root = Path("/sys/class/power_supply")
        try:
            supplies = list(power_root.iterdir())
        except OSError:
            return True
        for supply in supplies:
            try:
                if (supply / "type").read_text(encoding="utf-8").strip() != "Battery":
                    continue
                status = (supply / "status").read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if status.casefold() == "discharging":
                return False
        return True

    def _checkpoint_job(
        self, principal: MemoryPrincipal, job_id: str, payload: dict[str, Any]
    ) -> None:
        with self.repository.transaction() as conn:
            conn.execute(
                """
                UPDATE memory_jobs SET checkpoint_json=?,updated_at=?
                WHERE job_id=? AND owner_user_id=? AND state='running'
                """,
                (json.dumps(payload, sort_keys=True), utc_now(), job_id, principal.user_id),
            )

    def _owned_row(self, principal: MemoryPrincipal, memory_id: str, *, action: str = "correct"):
        row = self.fabric.ownership.accessible_record(principal, memory_id, action=action)
        if str(row["owner_user_id"]) != principal.user_id:
            raise MemoryAuthorizationError("Only the memory owner may perform this operation.")
        return row

    def _write_form_data(
        self,
        *,
        principal: MemoryPrincipal,
        row,
        form_data: dict[str, Any],
        reason: str,
        action: str,
    ) -> dict[str, Any]:
        with self.repository.connect() as conn:
            revision = self.fabric._revision_row(conn, row)
        current = self.fabric._read_content(principal, row, revision)
        content = MemoryContent(
            title=current.title,
            body=current.body,
            why_stored=reason,
            form_data=form_data,
        )
        privacy = MemoryPrivacy(str(row["privacy"]))
        old_digest = self.fabric._state_digest(row)
        with self.repository.transaction() as conn:
            revision_id, content_hash = self.fabric._insert_revision(
                conn,
                principal=principal,
                memory_id=str(row["memory_id"]),
                privacy=privacy,
                content=content,
                revision_number=int(row["revision_number"]) + 1,
                actor=principal.user_id,
                reason=reason,
                supersedes_revision_id=str(row["current_revision_id"]),
            )
            conn.execute(
                "UPDATE memory_records SET current_revision_id = ?, updated_at = ? WHERE memory_id = ?",
                (revision_id, utc_now(), row["memory_id"]),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action=action,
                    memory_id=str(row["memory_id"]),
                    request_id=None,
                    old_state_digest=old_digest,
                    new_state_digest=content_hash,
                    scope=str(row["scope"]),
                    form=str(row["form"]),
                    privacy=privacy.value,
                ),
            )
        return self.fabric.get(principal, str(row["memory_id"])).model_dump(mode="json")

    def form_action(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        request: MemoryFormActionRequest,
    ) -> dict[str, Any]:
        row = self._owned_row(principal, memory_id)
        form = MemoryForm(str(row["form"]))
        record = self.fabric.get(principal, memory_id)
        data = dict(record.form_data)
        allowed: dict[MemoryForm, set[str]] = {
            MemoryForm.PROSPECTIVE: {"snooze", "complete", "reopen", "dismiss"},
            MemoryForm.PREDICTIVE: {"record_outcome"},
            MemoryForm.PROCEDURAL: {"verify_procedure", "invalidate_procedure"},
        }
        if request.action not in allowed.get(form, set()):
            raise MemoryReleaseError("That form does not support the requested lifecycle action.")
        if form == MemoryForm.PROSPECTIVE:
            if request.action == "snooze":
                if not request.due_at:
                    raise MemoryReleaseError("Snoozing a prospective memory requires a new due time.")
                data.update(state="pending", due_at=request.due_at, last_action="snoozed")
            elif request.action == "complete":
                data.update(state="completed", completed_at=utc_now())
            elif request.action == "reopen":
                data.update(state="pending", completed_at=None)
            else:
                data.update(state="dismissed", dismissed_at=utc_now())
        elif form == MemoryForm.PREDICTIVE:
            if not request.outcome:
                raise MemoryReleaseError("A prediction outcome is required.")
            data.update(
                outcome=request.outcome,
                outcome_score=request.outcome_score,
                evaluated_at=utc_now(),
                prediction_frozen=True,
            )
        else:
            data.update(
                verified=request.action == "verify_procedure",
                verification_reason=request.reason,
                verified_at=utc_now(),
            )
        return {
            "record": self._write_form_data(
                principal=principal,
                row=row,
                form_data=data,
                reason=request.reason,
                action=f"form_{request.action}",
            ),
            "authority_granted": False,
        }

    def prospective_due(
        self, principal: MemoryPrincipal, *, horizon_hours: int = 168
    ) -> dict[str, Any]:
        """Return authenticated, restart-safe prospective notifications.

        Due state lives in canonical form data, not a transient timer. Sealed
        records never enter the ordinary notification surface; the user can
        inspect them only through the explicitly unlocked Sealed workflow.
        """

        settings = self.fabric.settings(principal)
        if not settings.prospective_notifications_enabled:
            return {
                "enabled": False,
                "due": [],
                "sealed_excluded": True,
                "external_delivery_performed": False,
            }
        now = datetime.now(UTC)
        horizon = now + timedelta(hours=max(0, min(horizon_hours, 24 * 365)))
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.memory_id,r.privacy FROM memory_records r
                WHERE (
                    (r.owner_user_id=? AND r.space_id IS NULL)
                    OR EXISTS (
                        SELECT 1 FROM shared_space_members sm
                        WHERE sm.space_id=r.space_id AND sm.user_id=?
                    )
                  ) AND r.form='prospective'
                  AND status IN ('active','working')
                  AND activation_tier NOT IN ('archived')
                  ORDER BY updated_at,memory_id
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
        due: list[dict[str, Any]] = []
        sealed_count = 0
        for row in rows:
            if str(row["privacy"]) == "sealed":
                sealed_count += 1
                continue
            record = self.fabric.get(principal, str(row["memory_id"]))
            state = str(record.form_data.get("state") or "pending")
            due_at = record.form_data.get("due_at") or record.valid_until
            if state != "pending" or not due_at:
                continue
            try:
                moment = _parse_iso(str(due_at))
            except ValueError:
                continue
            if moment <= horizon:
                due.append(
                    {
                        "memory_id": record.memory_id,
                        "title": record.title,
                        "due_at": str(due_at),
                        "overdue": moment <= now,
                        "privacy": record.privacy.value,
                        "scope": record.scope.value,
                        "project_id": next(
                            (
                                str(item["target_id"])
                                for item in record.relations
                                if item.get("target_type") == "project"
                            ),
                            None,
                        ),
                    }
                )
        return {
            "enabled": True,
            "due": due,
            "due_count": len(due),
            "sealed_records_excluded_count": sealed_count,
            "sealed_excluded": True,
            "external_delivery_performed": False,
            "canonical_restart_safe": True,
        }

    def suppress(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        request: MemorySuppressionRequest,
    ) -> dict[str, Any]:
        row = self._owned_row(principal, memory_id)
        with self.repository.transaction() as conn:
            conn.execute(
                "UPDATE memory_records SET automatic_recall_suppressed = ?, updated_at = ? WHERE memory_id = ?",
                (int(request.suppressed), utc_now(), memory_id),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="automatic_recall_suppressed" if request.suppressed else "automatic_recall_restored",
                    memory_id=memory_id,
                    request_id=None,
                    old_state_digest=self.fabric._state_digest(row),
                    new_state_digest=_digest({"suppressed": request.suppressed}),
                    scope=str(row["scope"]),
                    form=str(row["form"]),
                    privacy=str(row["privacy"]),
                ),
            )
        self._purge_ordinary_projections(principal, memory_id)
        if not request.suppressed:
            self._queue_projection_upserts(principal.user_id, memory_id)
        return {
            "record": self.fabric.get(principal, memory_id).model_dump(mode="json"),
            "explicit_lookup_remains_available": True,
            "automatic_context_admission": not request.suppressed,
        }

    def _queue_projection_upserts(self, owner_user_id: str, memory_id: str) -> None:
        now = utc_now()
        with self.repository.transaction() as conn:
            for kind in ("fts_upsert", "semantic_upsert"):
                conn.execute(
                    """
                    INSERT INTO memory_jobs (
                        job_id, owner_user_id, job_kind, state, progress_current,
                        progress_total, created_at, updated_at, result_code
                    ) VALUES (?, ?, ?, 'pending', 0, 1, ?, ?, NULL)
                    """,
                    (new_id("job"), owner_user_id, f"{kind}:{memory_id}", now, now),
                )

    def _purge_ordinary_projections(self, principal: MemoryPrincipal, memory_id: str) -> None:
        from app.cognition.fts_projection import FtsMemoryProjection
        from app.cognition.semantic_projection import SemanticMemoryProjection, SemanticProjectionError

        FtsMemoryProjection(
            paths=self.repository.paths, repository=self.repository, fabric=self.fabric
        ).privacy_purge_record(principal, memory_id)
        try:
            SemanticMemoryProjection(
                paths=self.repository.paths, repository=self.repository, fabric=self.fabric
            ).purge_record(memory_id)
        except SemanticProjectionError:
            # An absent optional semantic profile has no persistent vector to purge.
            pass

    def move_tier(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        request: MemoryTierRequest,
    ) -> dict[str, Any]:
        row = self._owned_row(principal, memory_id)
        from_tier = ActivationTier(str(row["activation_tier"]))
        to_tier = request.tier
        if to_tier == ActivationTier.COLD:
            managed, policy = self._managed_governance()
            if managed:
                if not bool(policy.get("cold_archive_allowed", True)):
                    raise MemoryAuthorizationError(
                        "Managed-profile policy does not allow cold archival."
                    )
                if not bool(policy.get("managed_backups_allowed", True)):
                    raise MemoryAuthorizationError(
                        "Safe cold archival requires a recovery backup that this managed-profile policy does not allow."
                    )
        if from_tier == to_tier:
            return {"record": self.fabric.get(principal, memory_id).model_dump(mode="json"), "idempotent": True}
        if request.automatic and (bool(row["pinned"]) or bool(row["retention_hold"])):
            raise MemoryReleaseError("Pinned or retained memory cannot be automatically demoted.")
        if to_tier == ActivationTier.ARCHIVED:
            record = self.fabric.set_status(
                principal,
                memory_id,
                MemoryLifecycle.ARCHIVED,
                MemoryReasonRequest(reason=request.reason),
            )
            self._record_tier_event(principal, memory_id, from_tier, to_tier, request)
            self._purge_ordinary_projections(principal, memory_id)
            return {"record": record.model_dump(mode="json"), "cold_payload_offloaded": False}
        if from_tier == ActivationTier.ARCHIVED:
            self.fabric.set_status(
                principal,
                memory_id,
                MemoryLifecycle.ACTIVE,
                MemoryReasonRequest(reason=request.reason),
            )
            row = self._owned_row(principal, memory_id)
        cold_offloaded = False
        cold_restored = False
        try:
            if to_tier == ActivationTier.COLD:
                self._ensure_cold_recovery_backup(principal, str(row["updated_at"]))
                self._offload_cold(principal, row)
                cold_offloaded = True
                self._purge_ordinary_projections(principal, memory_id)
            elif from_tier == ActivationTier.COLD:
                self._restore_cold_payloads(principal, memory_id)
                cold_restored = True
                self._queue_projection_upserts(principal.user_id, memory_id)
            with self.repository.transaction() as conn:
                conn.execute(
                    "UPDATE memory_records SET activation_tier = ?, updated_at = ? WHERE memory_id = ?",
                    (to_tier.value, utc_now(), memory_id),
                )
                self._insert_tier_event(
                    conn, principal, memory_id, from_tier, to_tier, request
                )
        except Exception:
            # Cold bytes are derived placement. If the authoritative tier/event
            # commit does not land, restore the exact previous placement and
            # projection eligibility before returning the error.
            if cold_offloaded:
                self._restore_cold_payloads(principal, memory_id)
                self._queue_projection_upserts(principal.user_id, memory_id)
            elif cold_restored:
                with self.repository.transaction() as conn:
                    conn.execute(
                        """
                        DELETE FROM memory_jobs
                        WHERE owner_user_id=? AND state='pending'
                          AND job_kind IN (?, ?)
                        """,
                        (
                            principal.user_id,
                            f"fts_upsert:{memory_id}",
                            f"semantic_upsert:{memory_id}",
                        ),
                    )
                previous = self._owned_row(principal, memory_id)
                self._offload_cold(principal, previous)
                self._purge_ordinary_projections(principal, memory_id)
            raise
        return {
            "record": self.fabric.get(principal, memory_id).model_dump(mode="json"),
            "cold_payload_offloaded": to_tier == ActivationTier.COLD,
            "rehydrated": from_tier == ActivationTier.COLD,
        }

    def _ensure_cold_recovery_backup(
        self, principal: MemoryPrincipal, record_updated_at: str
    ) -> None:
        with self.repository.connect() as conn:
            existing = conn.execute(
                """
                SELECT 1 FROM memory_archive_registry
                WHERE owner_user_id=? AND archive_kind='managed_backup'
                  AND state='verified' AND verified_at>=?
                LIMIT 1
                """,
                (principal.user_id, record_updated_at),
            ).fetchone()
        if existing is None:
            recovery_material = sha256(
                self.fabric.encryption.account_key(principal)
            ).hexdigest()
            self.export_archive(
                principal,
                MemoryArchiveExportRequest(
                    recovery_material=recovery_material,
                    archive_kind="managed_backup",
                    scope="full_account",
                ),
            )
            self._enforce_backup_retention(principal)

    def _enforce_backup_retention(self, principal: MemoryPrincipal) -> dict[str, int]:
        retention = self.fabric.settings(principal).backup_retention_count
        managed, policy = self._managed_governance()
        if managed:
            retention = min(
                retention, int(policy.get("backup_retention_maximum", retention))
            )
        with self.repository.connect() as conn:
            stale = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT archive_id,path_token FROM memory_archive_registry
                    WHERE owner_user_id=? AND archive_kind='managed_backup'
                    ORDER BY created_at DESC,archive_id DESC LIMIT -1 OFFSET ?
                    """,
                    (principal.user_id, retention),
                ).fetchall()
            ]
        removed = 0
        for archive in stale:
            path = self.repository.paths.memory_backup_dir / str(archive["path_token"])
            if path.is_file() and not path.is_symlink():
                path.unlink()
            with self.repository.transaction() as conn:
                conn.execute(
                    "DELETE FROM memory_archive_registry WHERE archive_id=? AND owner_user_id=?",
                    (archive["archive_id"], principal.user_id),
                )
            removed += 1
        return {"retained": retention, "removed": removed}

    def _record_tier_event(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        from_tier: ActivationTier,
        to_tier: ActivationTier,
        request: MemoryTierRequest,
    ) -> None:
        with self.repository.transaction() as conn:
            self._insert_tier_event(
                conn, principal, memory_id, from_tier, to_tier, request
            )

    @staticmethod
    def _insert_tier_event(
        conn,
        principal: MemoryPrincipal,
        memory_id: str,
        from_tier: ActivationTier,
        to_tier: ActivationTier,
        request: MemoryTierRequest,
    ) -> None:
        explanation = (
            "Tier movement used explicit user policy."
            if not request.automatic
            else "Tier movement used configured recency, retrieval, pin, hold, and storage policy."
        )
        conn.execute(
            """
            INSERT INTO memory_tier_events (
                event_id, memory_id, owner_user_id, from_tier, to_tier,
                reason_code, explanation, automatic, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("tierevent"), memory_id, principal.user_id,
                from_tier.value, to_tier.value,
                "automatic_policy" if request.automatic else "user_requested",
                explanation, int(request.automatic), utc_now(),
            ),
        )
        conn.execute(
            MUTATION_RECEIPT_INSERT,
            mutation_receipt_row(
                actor_user_id=principal.user_id,
                action="memory_tier_moved",
                memory_id=memory_id,
                request_id=None,
                old_state_digest=_digest({"tier": from_tier.value}),
                new_state_digest=_digest({"tier": to_tier.value}),
                scope=None,
                form=None,
                privacy=None,
                reason_code="automatic_policy" if request.automatic else "user_requested",
            ),
        )

    def _offload_cold(self, principal: MemoryPrincipal, row) -> None:
        memory_id = str(row["memory_id"])
        privacy = MemoryPrivacy(str(row["privacy"]))
        with self.repository.connect() as conn:
            revisions = conn.execute(
                "SELECT * FROM memory_revisions WHERE memory_id = ? ORDER BY revision_number",
                (memory_id,),
            ).fetchall()
        staged: list[tuple[str, str, str]] = []
        staged_reference_ids: list[str] = []
        try:
            for revision in revisions:
                ciphertext = bytes(revision["content_ciphertext"])
                if not ciphertext:
                    continue
                result = self.objects.put(
                    principal=principal,
                    raw=ciphertext,
                    privacy=privacy,
                    space_id=row["space_id"],
                    ref_type="cold_revision",
                    ref_id=str(revision["revision_id"]),
                    purpose="canonical_cold_payload",
                    media_type="application/vnd.elysia.memory-revision",
                )
                staged.append(
                    (
                        str(revision["revision_id"]),
                        str(result["object_id"]),
                        sha256(ciphertext).hexdigest(),
                    )
                )
                staged_reference_ids.append(str(result["object_ref_id"]))
            with self.repository.transaction() as conn:
                for revision_id, object_id, digest in staged:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO memory_cold_revisions (
                            revision_id, memory_id, object_id, ciphertext_digest,
                            archive_format, offloaded_at, last_verified_at
                        ) VALUES (?, ?, ?, ?, 'sqlite-pack-zstd-aead-v1', ?, ?)
                        """,
                        (revision_id, memory_id, object_id, digest, utc_now(), utc_now()),
                    )
                    conn.execute(
                        "UPDATE memory_revisions SET content_ciphertext = zeroblob(0) WHERE revision_id = ?",
                        (revision_id,),
                    )
        except Exception:
            self.objects.purge_reference_ids(staged_reference_ids)
            raise

    def _restore_cold_payloads(self, principal: MemoryPrincipal, memory_id: str) -> None:
        with self.repository.connect() as conn:
            rows = conn.execute(
                "SELECT revision_id, object_id, ciphertext_digest FROM memory_cold_revisions WHERE memory_id = ?",
                (memory_id,),
            ).fetchall()
        restored: list[tuple[bytes, str]] = []
        for row in rows:
            raw = self.objects.read(principal=principal, object_id=str(row["object_id"]))
            if sha256(raw).hexdigest() != str(row["ciphertext_digest"]):
                raise MemoryReleaseError("Cold-memory integrity validation failed.")
            restored.append((raw, str(row["revision_id"])))
        with self.repository.transaction() as conn:
            for raw, revision_id in restored:
                conn.execute(
                    "UPDATE memory_revisions SET content_ciphertext = ? WHERE revision_id = ?",
                    (raw, revision_id),
                )
            conn.execute("DELETE FROM memory_cold_revisions WHERE memory_id = ?", (memory_id,))
            conn.execute(
                """
                INSERT INTO memory_access_metrics (
                    memory_id, retrieval_count, last_retrieved_at,
                    last_rehydrated_at, rehydration_count
                ) VALUES (?, 0, NULL, ?, 1)
                ON CONFLICT(memory_id) DO UPDATE SET
                    last_rehydrated_at=excluded.last_rehydrated_at,
                    rehydration_count=memory_access_metrics.rehydration_count + 1
                """,
                (memory_id, utc_now()),
            )
        for row in rows:
            self.objects.purge_references(ref_type="cold_revision", ref_id=str(row["revision_id"]))

    def tier_history(self, principal: MemoryPrincipal, memory_id: str) -> dict[str, Any]:
        self.fabric.ownership.accessible_record(principal, memory_id)
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT from_tier, to_tier, reason_code, explanation, automatic, created_at
                FROM memory_tier_events WHERE memory_id = ? ORDER BY created_at DESC, event_id DESC
                """,
                (memory_id,),
            ).fetchall()
        return {"events": [dict(row) for row in rows], "explainable": True}

    def rebuild_graph(self, principal: MemoryPrincipal) -> dict[str, Any]:
        with self.repository.connect() as conn:
            records = conn.execute(
                """
                SELECT r.* FROM memory_records r
                WHERE (
                    (r.owner_user_id = ? AND r.space_id IS NULL)
                    OR EXISTS (
                        SELECT 1 FROM shared_space_members sm
                        WHERE sm.space_id=r.space_id AND sm.user_id=?
                    )
                  ) AND r.privacy = 'normal' AND r.status != 'deleted'
                ORDER BY memory_id
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
            relations = conn.execute(
                """
                SELECT rel.*, r.space_id AS source_space_id,
                       target.privacy AS target_privacy,
                       target.space_id AS target_space_id
                FROM memory_relations rel
                JOIN memory_records r ON r.memory_id = rel.source_memory_id
                LEFT JOIN memory_records target
                  ON rel.target_type='memory' AND target.memory_id=rel.target_id
                WHERE (
                    (r.owner_user_id = ? AND r.space_id IS NULL)
                    OR EXISTS (
                        SELECT 1 FROM shared_space_members sm
                        WHERE sm.space_id=r.space_id AND sm.user_id=?
                    )
                  ) AND r.privacy = 'normal' AND r.status != 'deleted'
                ORDER BY rel.relation_id
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
            sources = conn.execute(
                """
                SELECT s.*,r.space_id AS source_space_id
                FROM memory_sources s
                JOIN memory_records r ON r.memory_id=s.memory_id
                WHERE (
                    (r.owner_user_id=? AND r.space_id IS NULL)
                    OR EXISTS (
                        SELECT 1 FROM shared_space_members sm
                        WHERE sm.space_id=r.space_id AND sm.user_id=?
                    )
                  ) AND r.privacy='normal'
                  AND r.status!='deleted'
                ORDER BY s.source_row_id
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
        def node_id(kind: str, authority_id: str) -> str:
            token = sha256(f"{principal.user_id}:{kind}:{authority_id}".encode()).hexdigest()[:40]
            return f"graphnode_{token}"
        def edge_id(*parts: Any) -> str:
            token = sha256(":".join(str(value) for value in parts).encode()).hexdigest()[:40]
            return f"graphedge_{token}"
        nodes: dict[tuple[str, str], tuple[Any, ...]] = {}
        edges: list[tuple[Any, ...]] = []
        now = utc_now()
        for record in records:
            key = ("memory", str(record["memory_id"]))
            nodes[key] = (
                node_id(*key), principal.user_id, record["space_id"], "memory",
                record["memory_id"], "normal", record["status"],
                _digest({"memory_id": record["memory_id"], "revision": record["current_revision_id"]}), now,
            )
            source_owner = str(record["owner_user_id"])
            owner_key = ("user", source_owner)
            nodes.setdefault(
                owner_key,
                (
                    node_id(*owner_key), principal.user_id, None, "user",
                    source_owner, "normal", "active",
                    _digest({"owner_user_id": source_owner}), now,
                ),
            )
            edges.append(
                (
                    edge_id("owned_by", record["memory_id"]),
                    principal.user_id, record["space_id"], node_id(*key),
                    node_id(*owner_key), "owned_by", "observed", 1.0,
                    _digest({"memory_id": record["memory_id"], "owner": source_owner}),
                    None, None, "active", now,
                )
            )
            if record["space_id"]:
                space_key = ("shared_space", str(record["space_id"]))
                nodes.setdefault(
                    space_key,
                    (
                        node_id(*space_key), principal.user_id, record["space_id"],
                        "shared_space", record["space_id"], "normal", "active",
                        _digest({"shared_space_id": record["space_id"]}), now,
                    ),
                )
                edges.append(
                    (
                        edge_id("part_of", record["memory_id"], record["space_id"]),
                        principal.user_id, record["space_id"], node_id(*key),
                        node_id(*space_key), "part_of", "observed", 1.0,
                        _digest({"memory_id": record["memory_id"], "space": record["space_id"]}),
                        None, None, "active", now,
                    )
                )
        for source in sources:
            source_key = ("source", str(source["source_id"]))
            memory_key = ("memory", str(source["memory_id"]))
            nodes.setdefault(
                source_key,
                (
                    node_id(*source_key), principal.user_id,
                    source["source_space_id"], "source", source["source_id"],
                    "normal", "active",
                    _digest({"source_row_id": source["source_row_id"]}), now,
                ),
            )
            edges.append(
                (
                    edge_id("sourced_from", source["source_row_id"]),
                    principal.user_id, source["source_space_id"],
                    node_id(*memory_key), node_id(*source_key), "sourced_from",
                    "observed", 1.0,
                    _digest({"source_row_id": source["source_row_id"]}),
                    source["source_time"], None, "active", now,
                )
            )
        for relation in relations:
            if (
                str(relation["target_type"]) == "memory"
                and str(relation["target_privacy"] or "") != "normal"
            ):
                continue
            source_key = ("memory", str(relation["source_memory_id"]))
            target_key = (str(relation["target_type"]), str(relation["target_id"]))
            nodes.setdefault(
                target_key,
                (
                    node_id(*target_key), principal.user_id,
                    relation["target_space_id"] or relation["source_space_id"],
                    target_key[0],
                    target_key[1], "normal", "active",
                    _digest({"authority": target_key}), now,
                ),
            )
            edges.append(
                (
                    f"graphedge_{sha256(str(relation['relation_id']).encode()).hexdigest()[:40]}",
                    principal.user_id, relation["source_space_id"],
                    node_id(*source_key), node_id(*target_key),
                    relation["relation_type"],
                    "inferred" if int(relation["is_inferred"]) else "observed",
                    relation["confidence"],
                    _digest({"relation_id": relation["relation_id"], "source": relation["provenance_source_id"]}),
                    relation["valid_from"], relation["valid_until"], relation["status"], now,
                )
            )
        with self.repository.transaction() as conn:
            conn.execute("DELETE FROM memory_graph_edges WHERE owner_user_id = ?", (principal.user_id,))
            conn.execute("DELETE FROM memory_graph_nodes WHERE owner_user_id = ?", (principal.user_id,))
            conn.executemany(
                """
                INSERT INTO memory_graph_nodes (
                    node_id, owner_user_id, space_id, node_type, authority_id,
                    privacy, status, provenance_digest, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                list(nodes.values()),
            )
            conn.executemany(
                """
                INSERT INTO memory_graph_edges (
                    edge_id, owner_user_id, space_id, source_node_id, target_node_id,
                    relation_type, inference_status, confidence, provenance_digest,
                    valid_from, valid_until, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                edges,
            )
        return {
            "state": "ready",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "private_nodes_persisted": 0,
            "sealed_nodes_persisted": 0,
            "canonical_content_mutated": False,
        }

    def graph(self, principal: MemoryPrincipal, memory_id: str, *, limit: int = 100) -> dict[str, Any]:
        record = self.fabric.ownership.accessible_record(principal, memory_id)
        if str(record["privacy"]) != "normal":
            return {"nodes": [], "edges": [], "projection_excluded_for_privacy": True}
        # Graph rows are an account-scoped projection of the caller's current
        # canonical view. Shared topology is therefore rebuilt for each member
        # and disappears from a revoked member's projection without damaging
        # the remaining members' graph.
        self.rebuild_graph(principal)
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.relation_type,e.inference_status,e.confidence,
                       e.valid_from,e.valid_until,e.status,
                       target.node_type,target.authority_id
                FROM memory_graph_nodes source
                JOIN memory_graph_edges e ON e.source_node_id=source.node_id
                JOIN memory_graph_nodes target ON target.node_id=e.target_node_id
                WHERE source.owner_user_id=? AND source.node_type='memory'
                  AND source.authority_id=? AND e.status='active'
                ORDER BY e.relation_type,target.node_type,target.authority_id LIMIT ?
                """,
                (
                    principal.user_id,
                    memory_id,
                    max(1, min(limit, 500)),
                ),
            ).fetchall()
        edges: list[dict[str, Any]] = []
        for row in rows:
            if str(row["node_type"]) == "memory":
                try:
                    target = self.fabric.ownership.accessible_record(
                        principal, str(row["authority_id"])
                    )
                except MemoryFabricError:
                    continue
                if str(target["privacy"]) != "normal":
                    continue
            edges.append(dict(row))
        return {
            "edges": edges,
            "authorization_before_traversal": True,
            "private_or_sealed_structure_excluded": True,
            "source_owner_preserved": str(record["owner_user_id"]),
            "shared_space_preserved": record["space_id"],
        }

    def _logical_export(
        self,
        principal: MemoryPrincipal,
        scope: str,
        selected_authority_id: str | None = None,
        *,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        record_clause = """
            r.owner_user_id = ?
            AND (
                r.space_id IS NULL
                OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                )
            )
            AND r.status != 'deleted'
        """
        record_values: list[Any] = [principal.user_id, principal.user_id]
        if scope == "selected_space":
            record_clause += " AND r.space_id = ?"
            record_values.append(selected_authority_id)
        elif scope == "selected_project":
            record_clause += " AND EXISTS (SELECT 1 FROM memory_relations rel WHERE rel.source_memory_id=r.memory_id AND rel.target_type='project' AND rel.target_id=?)"
            record_values.append(selected_authority_id)
        with self.repository.connect() as conn:
            records = conn.execute(
                f"SELECT r.* FROM memory_records r WHERE {record_clause} ORDER BY r.memory_id",
                record_values,
            ).fetchall()
            spaces = conn.execute(
                """
                SELECT * FROM shared_spaces
                WHERE owner_user_id = ? AND (? != 'selected_space' OR space_id = ?)
                ORDER BY space_id
                """,
                (principal.user_id, scope, selected_authority_id),
            ).fetchall()
        exported_records: list[dict[str, Any]] = []
        included_ids = {str(record["memory_id"]) for record in records}
        linked_artifact_ids: set[str] = set()
        if scope != "metadata_audit":
            for record_index, record in enumerate(records, start=1):
                if job_id and self._job_cancelled(principal, job_id):
                    raise InterruptedError("Managed backup was cancelled while staging records.")
                with self.repository.connect() as conn:
                    revisions = conn.execute(
                        "SELECT * FROM memory_revisions WHERE memory_id = ? ORDER BY revision_number",
                        (record["memory_id"],),
                    ).fetchall()
                    sources = conn.execute(
                        "SELECT * FROM memory_sources WHERE memory_id = ? ORDER BY source_row_id",
                        (record["memory_id"],),
                    ).fetchall()
                    relations = conn.execute(
                        "SELECT * FROM memory_relations WHERE source_memory_id = ? ORDER BY relation_id",
                        (record["memory_id"],),
                    ).fetchall()
                    candidate = conn.execute(
                        "SELECT * FROM memory_candidates WHERE memory_id = ?",
                        (record["memory_id"],),
                    ).fetchone()
                    truth_events = conn.execute(
                        "SELECT * FROM memory_truth_events WHERE memory_id = ? ORDER BY transaction_at, truth_event_id",
                        (record["memory_id"],),
                    ).fetchall()
                revision_payloads = []
                linked_artifact_ids.update(
                    str(relation["target_id"])
                    for relation in relations
                    if str(relation["target_type"]) == "artifact"
                )
                for revision in revisions:
                    plaintext = self.fabric.encryption.decrypt_content(
                        principal=principal,
                        privacy=MemoryPrivacy(str(record["privacy"])),
                        memory_id=str(record["memory_id"]),
                        revision_id=str(revision["revision_id"]),
                        row=(
                            {**dict(revision), "content_ciphertext": self.objects.read_cold_revision(
                                principal=principal,
                                memory_id=str(record["memory_id"]),
                                revision_id=str(revision["revision_id"]),
                            )}
                            if not bytes(revision["content_ciphertext"])
                            else revision
                        ),
                    )
                    revision_payloads.append(
                        {
                            "revision_id": revision["revision_id"],
                            "revision_number": revision["revision_number"],
                            "plaintext": _b64(plaintext),
                            "created_by_actor": revision["created_by_actor"],
                            "created_at": revision["created_at"],
                            "reason": revision["reason"],
                            "supersedes_revision_id": revision["supersedes_revision_id"],
                        }
                    )
                safe_record = dict(record)
                safe_record.pop("title", None)
                exported_records.append(
                    {
                        "record": safe_record,
                        "revisions": revision_payloads,
                        "sources": [dict(row) for row in sources],
                        "relations": [dict(row) for row in relations],
                        "candidate": dict(candidate) if candidate else None,
                        "truth_events": [
                            dict(row)
                            for row in truth_events
                            if row["related_memory_id"] is None
                            or str(row["related_memory_id"]) in included_ids
                        ],
                    }
                )
                if job_id and record_index % 100 == 0:
                    self._checkpoint_job(
                        principal,
                        job_id,
                        {
                            "phase": "archive_records",
                            "records_processed": record_index,
                            "records_total": len(records),
                        },
                    )
        exported_objects: list[dict[str, Any]] = []
        if scope != "metadata_audit":
            with self.repository.connect() as conn:
                object_rows = conn.execute(
                    """
                    SELECT o.*, ref.object_ref_id, ref.ref_type, ref.ref_id,
                           ref.purpose, ref.created_at AS reference_created_at
                    FROM memory_objects o
                    JOIN memory_object_refs ref ON ref.object_id=o.object_id
                    WHERE o.owner_user_id=?
                    ORDER BY o.object_id, ref.object_ref_id
                    """,
                    (principal.user_id,),
                ).fetchall()
            grouped: dict[str, dict[str, Any]] = {}
            for row in object_rows:
                ref_type = str(row["ref_type"])
                ref_id = str(row["ref_id"])
                if not (
                    (ref_type == "memory" and ref_id in included_ids)
                    or (ref_type == "artifact" and ref_id in linked_artifact_ids)
                ):
                    continue
                object_id = str(row["object_id"])
                entry = grouped.setdefault(
                    object_id,
                    {
                        "object_id": object_id,
                        "privacy": str(row["privacy"]),
                        "space_id": row["space_id"],
                        "media_type": str(row["media_type"]),
                        "original_size": int(row["original_size"]),
                        "content": None,
                        "references": [],
                    },
                )
                entry["references"].append(
                    {
                        "object_ref_id": str(row["object_ref_id"]),
                        "ref_type": ref_type,
                        "ref_id": ref_id,
                        "purpose": str(row["purpose"]),
                        "created_at": str(row["reference_created_at"]),
                    }
                )
            for object_index, (object_id, entry) in enumerate(
                sorted(grouped.items()), start=1
            ):
                if job_id and self._job_cancelled(principal, job_id):
                    raise InterruptedError("Managed backup was cancelled while staging objects.")
                entry["content"] = _b64(
                    self.objects.read(principal=principal, object_id=object_id)
                )
                exported_objects.append(entry)
                if job_id and object_index % 100 == 0:
                    self._checkpoint_job(
                        principal,
                        job_id,
                        {
                            "phase": "archive_objects",
                            "objects_processed": object_index,
                            "objects_total": len(grouped),
                        },
                    )
        with self.repository.connect() as conn:
            receipts = conn.execute(
                """
                SELECT mutation_id, memory_id, action, scope, form, privacy,
                       completion_status, reason_code, created_at
                FROM memory_mutation_receipts WHERE actor_user_id = ? ORDER BY created_at
                """,
                (principal.user_id,),
            ).fetchall()
            if scope not in {"full_account", "metadata_audit"}:
                receipts = [
                    row
                    for row in receipts
                    if row["memory_id"] is not None
                    and str(row["memory_id"]) in included_ids
                ]
            contradictions = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT c.* FROM memory_contradictions c
                    JOIN memory_records l ON l.memory_id=c.left_memory_id
                    JOIN memory_records r ON r.memory_id=c.right_memory_id
                    WHERE l.owner_user_id=? AND r.owner_user_id=?
                    ORDER BY c.created_at, c.contradiction_id
                    """,
                    (principal.user_id, principal.user_id),
                ).fetchall()
                if str(row["left_memory_id"]) in included_ids
                and str(row["right_memory_id"]) in included_ids
            ]
        settings = self.fabric.settings(principal).model_dump(mode="json")
        return {
            "contract": "elysia-memory-archive",
            "format_version": ARCHIVE_VERSION,
            "created_at": utc_now(),
            "scope": scope,
            "origin_owner_id": principal.user_id,
            "records": exported_records,
            "metadata_counts": {
                "records": len(records),
                "spaces": len(spaces),
                "receipts": len(receipts),
                "objects": len(exported_objects),
            },
            "spaces": [dict(row) for row in spaces],
            "objects": exported_objects,
            "contradictions": contradictions,
            "audit_receipts": [dict(row) for row in receipts],
            "settings_manifest": settings,
            "projection_manifest": {
                "fts": "rebuild",
                "semantic": "rebuild_if_profile_installed",
                "graph": "rebuild",
            },
            "restore_contract": {
                "staging_required": True,
                "authenticated_manifest_required": True,
                "stable_identifier_conflict_check": True,
                "owner_mapping": "archive owner -> authenticated local owner",
                "shared_space_membership": "restored owner only",
                "settings_policy": "preview_only_not_automatically_applied",
                "canonical_import": "single_transaction",
                "object_import": "exact_reference_rollback_on_failure",
                "projection_policy": "rebuild_and_verify_after_canonical_import",
                "failure_policy": "restore canonical, object references, and local projections to pre-restore state",
            },
            "credentials_included": False,
            "raw_keys_included": False,
        }

    @staticmethod
    def _encrypt_archive(payload: dict[str, Any], recovery_material: str) -> bytes:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        format_version = int(payload.get("format_version") or ARCHIVE_VERSION)
        compressed = (
            zstandard.ZstdCompressor(level=9).compress(encoded)
            if format_version >= 2
            else zlib.compress(encoded, 9)
        )
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        if format_version < 1 or format_version > ARCHIVE_VERSION:
            raise MemoryReleaseError("The requested archive schema is unsupported.")
        header = {
            "contract": "elysia-memory-archive",
            "format_version": format_version,
            "compression": "zstd-9" if format_version >= 2 else "zlib-9",
            "cipher": "aes-256-gcm",
            "kdf": ARCHIVE_KDF,
            "salt": _b64(salt),
            "nonce": _b64(nonce),
        }
        aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(_archive_key(recovery_material, salt)).encrypt(nonce, compressed, aad)
        envelope = {**header, "ciphertext": _b64(ciphertext), "ciphertext_sha256": sha256(ciphertext).hexdigest()}
        return ARCHIVE_MAGIC + json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _decrypt_archive(raw: bytes, recovery_material: str) -> dict[str, Any]:
        if not raw.startswith(ARCHIVE_MAGIC):
            raise MemoryReleaseError("The file is not an Elysia Memory Archive.")
        try:
            envelope = json.loads(raw[len(ARCHIVE_MAGIC):].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MemoryReleaseError("The archive manifest is invalid.") from exc
        if envelope.get("contract") != "elysia-memory-archive":
            raise MemoryReleaseError("The archive contract is unsupported.")
        version = int(envelope.get("format_version") or 0)
        if version > ARCHIVE_VERSION:
            raise MemoryReleaseError("The archive was created by an unsupported future schema.")
        if version < 1:
            raise MemoryReleaseError("The archive schema is too old to restore safely.")
        try:
            ciphertext = _unb64(str(envelope["ciphertext"]))
            if sha256(ciphertext).hexdigest() != str(envelope["ciphertext_sha256"]):
                raise MemoryReleaseError("The archive ciphertext checksum failed.")
            header = {key: envelope[key] for key in ("contract", "format_version", "compression", "cipher", "kdf", "salt", "nonce")}
            aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
            compressed = AESGCM(
                _archive_key(recovery_material, _unb64(str(envelope["salt"])))
            ).decrypt(_unb64(str(envelope["nonce"])), ciphertext, aad)
            compression = str(envelope.get("compression") or "")
            if compression == "zstd-9":
                decoded = zstandard.ZstdDecompressor().decompress(compressed)
            elif compression == "zlib-9":
                decoded = zlib.decompress(compressed)
            else:
                raise MemoryReleaseError("The archive compression contract is unsupported.")
            payload = json.loads(decoded.decode("utf-8"))
        except MemoryReleaseError:
            raise
        except (
            InvalidTag,
            KeyError,
            ValueError,
            zlib.error,
            zstandard.ZstdError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise MemoryReleaseError("The archive could not be authenticated with the supplied recovery material.") from exc
        if not isinstance(payload, dict) or payload.get("contract") != "elysia-memory-archive":
            raise MemoryReleaseError("The authenticated archive payload is invalid.")
        if int(payload.get("format_version") or 0) != version:
            raise MemoryReleaseError("The archive schema manifest is inconsistent.")
        if version >= 2:
            required_components = {
                "records", "metadata_counts", "spaces", "contradictions",
                "objects", "audit_receipts", "settings_manifest", "projection_manifest",
                "restore_contract",
            }
            if required_components - set(payload):
                raise MemoryReleaseError(
                    "The authenticated archive is missing a required component."
                )
        return payload

    def export_archive(
        self,
        principal: MemoryPrincipal,
        request: MemoryArchiveExportRequest,
        *,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        self.repository.assert_nonessential_writes_ready()
        managed, policy = self._managed_governance()
        if (
            managed
            and request.archive_kind == "managed_backup"
            and not bool(policy.get("managed_backups_allowed", True))
        ):
            raise MemoryAuthorizationError(
                "Managed-profile policy does not allow managed backups."
            )
        # A managed backup must always be locally maintainable: exhaustive
        # hard-delete rewrites it without retaining a user recovery secret.
        # Portable exports continue to use only the user-supplied recovery
        # material and are never treated as installation-managed copies.
        recovery_material = (
            sha256(self.fabric.encryption.account_key(principal)).hexdigest()
            if request.archive_kind == "managed_backup"
            else request.recovery_material
        )
        payload = self._logical_export(
            principal,
            request.scope,
            request.selected_authority_id,
            job_id=job_id,
        )
        if job_id and self._job_cancelled(principal, job_id):
            raise InterruptedError("Managed backup was cancelled before encryption.")
        raw = self._encrypt_archive(payload, recovery_material)
        if job_id and self._job_cancelled(principal, job_id):
            raise InterruptedError("Managed backup was cancelled before commit.")
        archive_id = new_id("memarchive")
        token = _safe_archive_token(archive_id)
        destination = self.repository.paths.memory_backup_dir / token
        descriptor, temporary_name = tempfile.mkstemp(prefix=".archive-", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, destination)
            destination.chmod(0o600)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        checksum = sha256(raw).hexdigest()
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_archive_registry (
                    archive_id, owner_user_id, archive_kind, format_version,
                    scope, path_token, encrypted, size_bytes, checksum, state,
                    created_at, verified_at, record_count
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 'verified', ?, ?, ?)
                """,
                (
                    archive_id, principal.user_id, request.archive_kind,
                    ARCHIVE_VERSION, request.scope, token, len(raw), checksum,
                    utc_now(), utc_now(), len(payload.get("records", [])),
                ),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="portable_archive_created" if request.archive_kind == "portable_export" else "managed_backup_created",
                    memory_id=None,
                    request_id=None,
                    old_state_digest=None,
                    new_state_digest=_digest({"archive_id": archive_id, "checksum": checksum}),
                    scope=request.scope,
                    form="audit",
                    privacy="private",
                    reason_code="encrypted_portable_archive",
                ),
            )
        return {
            "archive_id": archive_id,
            "format_version": ARCHIVE_VERSION,
            "encrypted": True,
            "portable": request.archive_kind == "portable_export",
            "record_count": len(payload.get("records", [])),
            "size_bytes": len(raw),
            "checksum": checksum,
            "archive_base64": _b64(raw) if request.archive_kind == "portable_export" else None,
            "raw_path_exposed": False,
            "credentials_included": False,
            "raw_keys_included": False,
        }

    def _archive_raw(
        self, principal: MemoryPrincipal, request: MemoryArchiveRestorePreviewRequest
    ) -> tuple[bytes, str | None]:
        if request.archive_base64:
            raw = _unb64(request.archive_base64)
            return raw, None
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_archive_registry WHERE archive_id = ? AND owner_user_id = ?",
                (request.archive_id, principal.user_id),
            ).fetchone()
        if row is None:
            raise MemoryReleaseError("The managed archive is unavailable.")
        path = self.repository.paths.memory_backup_dir / str(row["path_token"])
        if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
            raise MemoryReleaseError("The managed archive failed its storage-boundary check.")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != str(row["checksum"]):
            raise MemoryReleaseError("The managed archive checksum failed.")
        return raw, str(row["archive_id"])

    @staticmethod
    def _validated_archive_ids(payload: dict[str, Any]) -> dict[str, set[str]]:
        identifiers: dict[str, set[str]] = {
            "memory": set(), "revision": set(), "source": set(),
            "relation": set(), "candidate": set(), "truth_event": set(),
            "contradiction": set(), "space": set(), "receipt": set(),
            "object": set(), "object_ref": set(),
        }
        linked_artifact_ids: set[str] = set()

        def register(kind: str, raw: Any) -> str:
            value = str(raw or "")
            if not value or value in identifiers[kind]:
                raise MemoryReleaseError(
                    f"The archive contains an invalid or duplicate stable {kind} identifier."
                )
            identifiers[kind].add(value)
            return value

        records = list(payload.get("records") or [])
        for item in records:
            if not isinstance(item, dict) or not isinstance(item.get("record"), dict):
                raise MemoryReleaseError("The archive record manifest is invalid.")
            memory_id = register("memory", item["record"].get("memory_id"))
            revision_ids: set[str] = set()
            for revision in list(item.get("revisions") or []):
                revision_id = register("revision", revision.get("revision_id"))
                revision_ids.add(revision_id)
            current_revision_id = str(item["record"].get("current_revision_id") or "")
            if not revision_ids or current_revision_id not in revision_ids:
                raise MemoryReleaseError("The archive is missing a required current revision.")
            for revision in list(item.get("revisions") or []):
                supersedes = revision.get("supersedes_revision_id")
                if supersedes and str(supersedes) not in revision_ids:
                    raise MemoryReleaseError("An archived revision chain is incomplete.")
            for source in list(item.get("sources") or []):
                if str(source.get("memory_id") or memory_id) != memory_id:
                    raise MemoryReleaseError("An archived provenance row crosses its record boundary.")
                register("source", source.get("source_row_id"))
            for relation in list(item.get("relations") or []):
                if str(relation.get("source_memory_id") or "") != memory_id:
                    raise MemoryReleaseError("An archived relationship crosses its source boundary.")
                register("relation", relation.get("relation_id"))
                if str(relation.get("target_type") or "") == "artifact":
                    linked_artifact_ids.add(str(relation.get("target_id") or ""))
            candidate = item.get("candidate")
            if candidate is not None:
                if not isinstance(candidate, dict) or str(candidate.get("memory_id") or "") != memory_id:
                    raise MemoryReleaseError("An archived candidate crosses its record boundary.")
                register("candidate", candidate.get("candidate_id"))
            for event in list(item.get("truth_events") or []):
                if str(event.get("memory_id") or "") != memory_id:
                    raise MemoryReleaseError("An archived truth event crosses its record boundary.")
                register("truth_event", event.get("truth_event_id"))
        for contradiction in list(payload.get("contradictions") or []):
            register("contradiction", contradiction.get("contradiction_id"))
            if not {
                str(contradiction.get("left_memory_id") or ""),
                str(contradiction.get("right_memory_id") or ""),
            }.issubset(identifiers["memory"]):
                raise MemoryReleaseError("An archived contradiction is missing one of its records.")
        for space in list(payload.get("spaces") or []):
            register("space", space.get("space_id"))
        for receipt in list(payload.get("audit_receipts") or []):
            register("receipt", receipt.get("mutation_id"))
            memory_id = receipt.get("memory_id")
            if memory_id and str(memory_id) not in identifiers["memory"]:
                raise MemoryReleaseError(
                    "An archived mutation receipt references memory outside its archive scope."
                )
        for item in records:
            space_id = item["record"].get("space_id")
            if space_id and str(space_id) not in identifiers["space"]:
                raise MemoryReleaseError("An archived Shared Space record lacks its space manifest.")
        for item in list(payload.get("objects") or []):
            if not isinstance(item, dict):
                raise MemoryReleaseError("An archived object manifest is invalid.")
            register("object", item.get("object_id"))
            raw = _unb64(str(item.get("content") or ""))
            if len(raw) != int(item.get("original_size") or -1):
                raise MemoryReleaseError("An archived object failed its size manifest.")
            privacy = str(item.get("privacy") or "")
            if privacy not in {value.value for value in MemoryPrivacy}:
                raise MemoryReleaseError("An archived object has an invalid privacy class.")
            if privacy != "normal" and item.get("space_id"):
                raise MemoryReleaseError("A protected archived object cannot cross into a Shared Space.")
            references = list(item.get("references") or [])
            if not references:
                raise MemoryReleaseError("An archived object has no retained canonical reference.")
            for reference in references:
                register("object_ref", reference.get("object_ref_id"))
                ref_type = str(reference.get("ref_type") or "")
                ref_id = str(reference.get("ref_id") or "")
                allowed = (
                    ref_type == "memory" and ref_id in identifiers["memory"]
                ) or (
                    ref_type == "artifact" and ref_id in linked_artifact_ids
                )
                if not allowed:
                    raise MemoryReleaseError(
                        "An archived object reference crosses its selected authority scope."
                    )
        return identifiers

    def _restore_conflicts(self, identifiers: dict[str, set[str]]) -> set[str]:
        authorities = {
            "memory": ("memory_records", "memory_id"),
            "revision": ("memory_revisions", "revision_id"),
            "source": ("memory_sources", "source_row_id"),
            "relation": ("memory_relations", "relation_id"),
            "candidate": ("memory_candidates", "candidate_id"),
            "truth_event": ("memory_truth_events", "truth_event_id"),
            "contradiction": ("memory_contradictions", "contradiction_id"),
            "space": ("shared_spaces", "space_id"),
            "receipt": ("memory_mutation_receipts", "mutation_id"),
            "object": ("memory_objects", "object_id"),
            "object_ref": ("memory_object_refs", "object_ref_id"),
        }
        conflicts: set[str] = set()
        with self.repository.connect() as conn:
            for kind, (table, column) in authorities.items():
                incoming = identifiers[kind]
                if not incoming:
                    continue
                live = {
                    str(row[0])
                    for row in conn.execute(f"SELECT {column} FROM {table}").fetchall()
                }
                conflicts.update(f"{kind}:{value}" for value in incoming & live)
        return conflicts

    def preview_restore(
        self, principal: MemoryPrincipal, request: MemoryArchiveRestorePreviewRequest
    ) -> dict[str, Any]:
        raw, existing_archive_id = self._archive_raw(principal, request)
        payload = self._decrypt_archive(raw, request.recovery_material)
        records = list(payload.get("records") or [])
        if len(records) > 1_000_000:
            raise MemoryReleaseError("The archive exceeds the restore record limit.")
        identifiers = self._validated_archive_ids(payload)
        memory_ids = sorted(identifiers["memory"])
        conflicts = self._restore_conflicts(identifiers)
        with self.repository.connect() as conn:
            live_count = int(conn.execute("SELECT COUNT(*) FROM memory_records WHERE owner_user_id = ?", (principal.user_id,)).fetchone()[0])
        archive_id = existing_archive_id or new_id("incomingarchive")
        restore_plan_id = new_id("restoreplan")
        staging_token = f"restore-{restore_plan_id}.archive"
        staging = self.repository.paths.memory_checkpoints_dir / staging_token
        staging.write_bytes(raw)
        staging.chmod(0o600)
        plan = {
            "archive_id": archive_id,
            "archive_checksum": sha256(raw).hexdigest(),
            "format_version": payload.get("format_version"),
            "scope": payload.get("scope"),
            "additions": len(memory_ids) - sum(
                item.startswith("memory:") for item in conflicts
            ),
            "conflicts": sorted(conflicts),
            "stable_identifier_counts": {
                kind: len(values) for kind, values in identifiers.items()
            },
            "owner_mapping": "archive owner -> authenticated local owner",
            "live_record_count_before": live_count,
            "projection_plan": ["fts_rebuild", "semantic_rebuild_if_installed", "graph_rebuild"],
            "objects_to_restore": len(payload.get("objects", [])),
            "shared_spaces_to_create": len(payload.get("spaces", [])),
            "shared_space_membership_policy": "restored owner only; external local identities are not federated",
            "settings_manifest_present": isinstance(payload.get("settings_manifest"), dict),
            "settings_restore_policy": (
                "present_for_operator_review_not_automatically_applied"
                if isinstance(payload.get("settings_manifest"), dict)
                else "no_settings_manifest"
            ),
            "atomic_import": True,
        }
        plan_hash = _digest(plan)
        approval_id = new_id("memapproval")
        token = secrets.token_urlsafe(32)
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=RESTORE_TTL_SECONDS)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_restore_plans (
                    restore_plan_id, owner_user_id, archive_id, plan_hash, state,
                    additions, conflicts, staging_token, created_at, expires_at
                ) VALUES (?, ?, ?, ?, 'previewed', ?, ?, ?, ?, ?)
                """,
                (
                    restore_plan_id, principal.user_id, archive_id, plan_hash,
                    plan["additions"], len(conflicts), staging_token, utc_now(), expires_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO memory_action_approvals (
                    approval_id, actor_user_id, action, target_id, state_digest,
                    consequence_json, token_hash, expires_at, created_at
                ) VALUES (?, ?, 'restore_archive', ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id, principal.user_id, restore_plan_id, plan_hash,
                    json.dumps(plan, sort_keys=True), sha256(token.encode()).hexdigest(),
                    expires_at, utc_now(),
                ),
            )
        return {
            "restore_plan_id": restore_plan_id,
            "plan_hash": plan_hash,
            "plan": plan,
            "approval_id": approval_id,
            "approval_token": token,
            "one_time": True,
            "expires_at": expires_at,
            "plaintext_staged": False,
        }

    def apply_restore(
        self, principal: MemoryPrincipal, request: MemoryArchiveRestoreApplyRequest
    ) -> dict[str, Any]:
        with self.repository.connect() as conn:
            plan_row = conn.execute(
                "SELECT * FROM memory_restore_plans WHERE restore_plan_id = ? AND owner_user_id = ?",
                (request.restore_plan_id, principal.user_id),
            ).fetchone()
            approval = conn.execute(
                "SELECT * FROM memory_action_approvals WHERE approval_id = ?",
                (request.approval_id,),
            ).fetchone()
        if plan_row is None or approval is None or approval["consumed_at"] is not None:
            raise MemoryApprovalError("The exact restore approval is unavailable.")
        if str(approval["target_id"]) != request.restore_plan_id or str(approval["actor_user_id"]) != principal.user_id:
            raise MemoryApprovalError("The restore approval boundary does not match.")
        if datetime.now(UTC) >= _parse_iso(str(approval["expires_at"])):
            raise MemoryApprovalError("The restore approval expired.")
        if not secrets.compare_digest(
            sha256(request.approval_token.encode()).hexdigest(),
            str(approval["token_hash"]),
        ):
            raise MemoryApprovalError("The restore approval token does not match.")
        staging = self.repository.paths.memory_checkpoints_dir / str(plan_row["staging_token"])
        if not staging.is_file() or staging.is_symlink():
            raise MemoryReleaseError("The encrypted restore staging file is unavailable.")
        approved_plan = json.loads(str(approval["consequence_json"]))
        staging_raw = staging.read_bytes()
        if not secrets.compare_digest(
            sha256(staging_raw).hexdigest(),
            str(approved_plan.get("archive_checksum") or ""),
        ):
            raise MemoryApprovalError("The encrypted archive changed after restore preview.")
        payload = self._decrypt_archive(staging_raw, request.recovery_material)
        records = list(payload.get("records") or [])
        identifiers = self._validated_archive_ids(payload)
        conflicts = self._restore_conflicts(identifiers)
        if sorted(conflicts) != sorted(approved_plan.get("conflicts") or []):
            raise MemoryApprovalError("Live Memory changed after the restore preview.")
        if conflicts:
            raise MemoryReleaseError("Resolve stable-ID conflicts before applying this restore.")
        exported_spaces = {
            str(space.get("space_id")): dict(space)
            for space in payload.get("spaces", [])
            if isinstance(space, dict) and space.get("space_id")
        }
        prepared: list[dict[str, Any]] = []
        for item in records:
            source_record = dict(item["record"])
            privacy = MemoryPrivacy(str(source_record["privacy"]))
            encrypted_revisions = []
            for revision in item["revisions"]:
                revision_id = str(revision["revision_id"])
                encrypted = self.fabric.encryption.encrypt_content(
                    principal=principal,
                    privacy=privacy,
                    memory_id=str(source_record["memory_id"]),
                    revision_id=revision_id,
                    plaintext=_unb64(str(revision["plaintext"])),
                )
                encrypted_revisions.append((revision, encrypted))
            prepared.append({"record": source_record, "item": item, "revisions": encrypted_revisions})
        prepared_objects = [
            {
                **dict(item),
                "raw": _unb64(str(item.get("content") or "")),
            }
            for item in list(payload.get("objects") or [])
        ]
        rollback_token = request.restore_plan_id.replace("/", "_")
        canonical_snapshot = (
            self.repository.paths.memory_checkpoints_dir
            / f"restore-rollback-{rollback_token}.sqlite"
        )
        self.repository.backup(canonical_snapshot)
        fts_path = self.repository.paths.memory_fts_database_path
        fts_existed = fts_path.is_file() and not fts_path.is_symlink()
        fts_snapshot = (
            self.repository.paths.memory_checkpoints_dir
            / f"restore-rollback-{rollback_token}-fts.sqlite"
        )
        if fts_existed:
            self._sqlite_copy(fts_path, fts_snapshot)
        with self.repository.transaction() as conn:
            for space_id, source_space in sorted(exported_spaces.items()):
                if conn.execute(
                    "SELECT 1 FROM shared_spaces WHERE space_id = ?", (space_id,)
                ).fetchone() is not None:
                    raise MemoryReleaseError(
                        "A Shared Space stable identifier now conflicts with live state."
                    )
                conn.execute(
                    """
                    INSERT INTO shared_spaces (
                        space_id, owner_user_id, label, description, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        space_id,
                        principal.user_id,
                        source_space.get("label") or "Restored Shared Space",
                        source_space.get("description"),
                        source_space.get("created_at") or utc_now(),
                        utc_now(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO shared_space_members (
                        space_id, user_id, role, added_by_user_id, created_at
                    ) VALUES (?, ?, 'owner', ?, ?)
                    """,
                    (
                        space_id, principal.user_id, principal.user_id, utc_now(),
                    ),
                )
            for prepared_item in prepared:
                source = prepared_item["record"]
                item = prepared_item["item"]
                current_revision_id = str(source["current_revision_id"])
                current_plaintext = next(
                    _unb64(str(rev["plaintext"]))
                    for rev in item["revisions"] if str(rev["revision_id"]) == current_revision_id
                )
                current_content = MemoryContent.model_validate_json(current_plaintext)
                space_id = source.get("space_id")
                if space_id and str(space_id) not in exported_spaces:
                    space_id = None
                conn.execute(
                    """
                    INSERT INTO memory_records (
                        memory_id, owner_user_id, space_id, scope, form, subtype,
                        privacy, status, title, current_revision_id, importance,
                        confidence, user_confirmed, inference_kind, created_at,
                        updated_at, observed_at, valid_from, valid_until,
                        activation_tier, pinned, egress_allowed, legacy_class,
                        schema_version, automatic_recall_suppressed, expires_at,
                        retention_hold
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 3, ?, ?, ?)
                    """,
                    (
                        source["memory_id"], principal.user_id, space_id,
                        "user" if source["scope"] == "shared_space" and space_id is None else source["scope"],
                        source["form"], source.get("subtype"), source["privacy"],
                        source["status"], current_content.title if source["privacy"] == "normal" else None,
                        current_revision_id, source["importance"], source.get("confidence"),
                        source["user_confirmed"], source.get("inference_kind"),
                        source["created_at"], utc_now(), source.get("observed_at"),
                        source.get("valid_from"), source.get("valid_until"),
                        "warm" if source["activation_tier"] == "cold" else source["activation_tier"],
                        source["pinned"], source.get("legacy_class"),
                        source.get("automatic_recall_suppressed", 0), source.get("expires_at"),
                        source.get("retention_hold", 0),
                    ),
                )
                for revision, encrypted in prepared_item["revisions"]:
                    conn.execute(
                        """
                        INSERT INTO memory_revisions (
                            revision_id, memory_id, revision_number, content_ciphertext,
                            content_nonce, wrapped_data_key, key_nonce, key_id,
                            content_format, plaintext_hash, digest_format,
                            created_by_actor, created_at,
                            reason, supersedes_revision_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            revision["revision_id"], source["memory_id"], revision["revision_number"],
                            encrypted.ciphertext, encrypted.nonce, encrypted.wrapped_data_key,
                            encrypted.key_nonce, encrypted.key_id, encrypted.content_format,
                            encrypted.plaintext_hash,
                            self.fabric.encryption.digest_format(privacy),
                            principal.user_id, revision["created_at"],
                            revision.get("reason"), revision.get("supersedes_revision_id"),
                        ),
                    )
                for source_row in item.get("sources", []):
                    values = dict(source_row)
                    values["memory_id"] = source["memory_id"]
                    conn.execute(
                        """
                        INSERT INTO memory_sources (
                            source_row_id, memory_id, source_type, source_id, source_label,
                            source_time, source_authority, retrieval_method, provenance_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        tuple(values.get(key) for key in (
                            "source_row_id", "memory_id", "source_type", "source_id", "source_label",
                            "source_time", "source_authority", "retrieval_method", "provenance_status",
                        )),
                    )
                for relation in item.get("relations", []):
                    conn.execute(
                        """
                        INSERT INTO memory_relations (
                            relation_id, source_memory_id, target_type, target_id,
                            relation_type, confidence, is_inferred, provenance_source_id,
                            valid_from, valid_until, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        tuple(relation.get(key) for key in (
                            "relation_id", "source_memory_id", "target_type", "target_id",
                            "relation_type", "confidence", "is_inferred", "provenance_source_id",
                            "valid_from", "valid_until", "status",
                        )),
                    )
                candidate = item.get("candidate")
                if isinstance(candidate, dict):
                    conn.execute(
                        """
                        INSERT INTO memory_candidates (
                            candidate_id, memory_id, candidate_kind, review_state,
                            created_at, reviewed_at, reviewed_by_user_id,
                            deferred_until, feedback_code, proposed_wording,
                            evidence_summary
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            candidate.get("candidate_id"), source["memory_id"],
                            candidate.get("candidate_kind"), candidate.get("review_state"),
                            candidate.get("created_at"), candidate.get("reviewed_at"),
                            principal.user_id if candidate.get("reviewed_by_user_id") else None,
                            candidate.get("deferred_until"), candidate.get("feedback_code"),
                            candidate.get("proposed_wording"), candidate.get("evidence_summary"),
                        ),
                    )
                for truth_event in item.get("truth_events", []):
                    values = dict(truth_event)
                    values["owner_user_id"] = principal.user_id
                    conn.execute(
                        """
                        INSERT INTO memory_truth_events (
                            truth_event_id, owner_user_id, memory_id, related_memory_id,
                            change_kind, prior_revision_id, resulting_revision_id,
                            rationale, observed_at, valid_from, valid_until,
                            transaction_at, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        tuple(values.get(key) for key in (
                            "truth_event_id", "owner_user_id", "memory_id",
                            "related_memory_id", "change_kind", "prior_revision_id",
                            "resulting_revision_id", "rationale", "observed_at",
                            "valid_from", "valid_until", "transaction_at", "status",
                        )),
                    )
            for contradiction in payload.get("contradictions", []):
                conn.execute(
                    """
                    INSERT INTO memory_contradictions (
                        contradiction_id, left_memory_id, right_memory_id, severity,
                        status, rationale, created_at, resolved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(contradiction.get(key) for key in (
                        "contradiction_id", "left_memory_id", "right_memory_id",
                        "severity", "status", "rationale", "created_at", "resolved_at",
                    )),
                )
            for receipt in payload.get("audit_receipts", []):
                conn.execute(
                    """
                    INSERT INTO memory_mutation_receipts (
                        mutation_id, actor_user_id, request_id, memory_id, action,
                        old_state_digest, new_state_digest, scope, form, privacy,
                        approval_id, projection_invalidation_state, completion_status,
                        reason_code, created_at
                    ) VALUES (?, ?, NULL, ?, ?, NULL, NULL, ?, ?, ?, NULL,
                              'restored_rebuild_required', ?, ?, ?)
                    """,
                    (
                        receipt.get("mutation_id"), principal.user_id,
                        receipt.get("memory_id"), receipt.get("action"),
                        receipt.get("scope"), receipt.get("form"), receipt.get("privacy"),
                        receipt.get("completion_status") or "complete",
                        "restored_content_free_audit_receipt", receipt.get("created_at") or utc_now(),
                    ),
                )
            self.fabric._consume_approval(conn, request.approval_id)
            conn.execute(
                "UPDATE memory_restore_plans SET state = 'applied', applied_at = ? WHERE restore_plan_id = ?",
                (utc_now(), request.restore_plan_id),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="portable_archive_restored",
                    memory_id=None,
                    request_id=None,
                    old_state_digest=None,
                    new_state_digest=str(plan_row["plan_hash"]),
                    scope="full_account",
                    form="audit",
                    privacy="private",
                    approval_id=request.approval_id,
                    reason_code="staged_atomic_restore",
                ),
            )
        projection_results: dict[str, Any] = {}
        imported_object_refs: list[str] = []
        try:
            from app.cognition.fts_projection import FtsMemoryProjection
            from app.cognition.semantic_projection import SemanticMemoryProjection

            for item in prepared_objects:
                references = list(item.get("references") or [])
                for reference in references:
                    result = self.objects.put(
                        principal=principal,
                        raw=bytes(item["raw"]),
                        privacy=MemoryPrivacy(str(item["privacy"])),
                        space_id=item.get("space_id"),
                        ref_type=str(reference["ref_type"]),
                        ref_id=str(reference["ref_id"]),
                        purpose=str(reference["purpose"]),
                        media_type=str(item.get("media_type") or "application/octet-stream"),
                        managed_object_id=str(item["object_id"]),
                        managed_ref_id=str(reference["object_ref_id"]),
                    )
                    if str(result["object_id"]) != str(item["object_id"]):
                        raise MemoryReleaseError(
                            "A restored blob did not preserve its stable managed identifier."
                        )
                    imported_object_refs.append(str(reference["object_ref_id"]))

            projection_results["fts"] = FtsMemoryProjection(
                paths=self.repository.paths,
                repository=self.repository,
                fabric=self.fabric,
            ).repair_and_rebuild(principal)
            projection_results["graph"] = self.rebuild_graph(principal)
            semantic = SemanticMemoryProjection(
                paths=self.repository.paths,
                repository=self.repository,
                fabric=self.fabric,
            )
            projection_results["semantic"] = (
                semantic.rebuild(principal)
                if semantic.configured
                else {"state": "optional_not_configured", "canonical_memory_mutated": False}
            )
        except Exception as exc:
            rollback_errors: list[str] = []
            try:
                self.objects.purge_reference_ids(imported_object_refs)
            except Exception:
                rollback_errors.append("object_rollback")
            try:
                from app.cognition.semantic_projection import SemanticMemoryProjection

                semantic = SemanticMemoryProjection(
                    paths=self.repository.paths,
                    repository=self.repository,
                    fabric=self.fabric,
                )
                for memory_id in identifiers["memory"]:
                    semantic.purge_record(memory_id)
            except Exception:
                # Semantic points are Normal-only and remain authorization-
                # inert without canonical records.  Record the repair need,
                # but always restore canonical and lexical live state first.
                rollback_errors.append("semantic_projection_cleanup")
            try:
                self._restore_sqlite_copy(canonical_snapshot, self.repository.database_path)
            except Exception:
                rollback_errors.append("canonical_rollback")
            try:
                if fts_existed:
                    self._restore_sqlite_copy(fts_snapshot, fts_path)
                else:
                    for candidate in (
                        fts_path,
                        Path(f"{fts_path}-wal"),
                        Path(f"{fts_path}-shm"),
                    ):
                        candidate.unlink(missing_ok=True)
            except Exception:
                rollback_errors.append("fts_rollback")
            if "canonical_rollback" in rollback_errors:
                raise MemoryReleaseError(
                    "Restore failed and the verified canonical rollback requires maintenance."
                ) from exc
            raise MemoryReleaseError(
                "Restore failed after staging and the live canonical/lexical store was rolled back; derived semantic cleanup may require rebuild."
                if rollback_errors
                else "Restore failed after staging and every live store was rolled back to its verified pre-restore state."
            ) from exc
        canonical_snapshot.unlink(missing_ok=True)
        fts_snapshot.unlink(missing_ok=True)
        staging.unlink(missing_ok=True)
        return {
            "restored_record_count": len(prepared),
            "atomic_import": True,
            "projection_rebuild_queued": False,
            "projection_results": projection_results,
            "projection_rebuild_verified": all(
                result.get("state") in {"ready", "optional_not_configured"}
                for result in projection_results.values()
            ),
            "live_state_untouched_on_precommit_failure": True,
            "rollback_snapshot_removed": True,
            "restored_object_count": len(prepared_objects),
        }

    @staticmethod
    def _sqlite_copy(source_path: Path, destination_path: Path) -> None:
        destination_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source = sqlite3.connect(
            f"file:{source_path.as_posix()}?mode=ro", uri=True, timeout=30.0
        )
        destination = sqlite3.connect(destination_path, timeout=30.0)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        destination_path.chmod(0o600)

    @staticmethod
    def _restore_sqlite_copy(snapshot_path: Path, destination_path: Path) -> None:
        source = sqlite3.connect(
            f"file:{snapshot_path.as_posix()}?mode=ro", uri=True, timeout=30.0
        )
        destination = sqlite3.connect(destination_path, timeout=30.0)
        try:
            source.backup(destination)
            destination.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            destination.close()
            source.close()
        destination_path.chmod(0o600)

    def archive_status(self, principal: MemoryPrincipal) -> dict[str, Any]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT archive_id, archive_kind, format_version, scope, encrypted,
                       size_bytes, state, created_at, verified_at, record_count
                FROM memory_archive_registry WHERE owner_user_id = ?
                ORDER BY created_at DESC
                """,
                (principal.user_id,),
            ).fetchall()
        return {"archives": [dict(row) for row in rows], "raw_paths_exposed": False}

    def homeostasis(self, principal: MemoryPrincipal, *, apply_pause: bool = False) -> dict[str, Any]:
        settings = self.fabric.settings(principal)
        managed, managed_policy = self._managed_governance()
        usage = shutil.disk_usage(self.repository.paths.data_dir)
        with self.repository.connect() as conn:
            current_space_ids = [
                str(row["space_id"])
                for row in conn.execute(
                    "SELECT space_id FROM shared_space_members WHERE user_id=? ORDER BY space_id",
                    (principal.user_id,),
                ).fetchall()
            ]
            tiers = {
                str(row["activation_tier"]): int(row["count"])
                for row in conn.execute(
                    """
                    SELECT r.activation_tier, COUNT(*) AS count FROM memory_records r
                    WHERE r.owner_user_id=? AND r.status!='deleted'
                      AND (r.space_id IS NULL OR EXISTS (
                        SELECT 1 FROM shared_space_members sm
                        WHERE sm.space_id=r.space_id AND sm.user_id=?
                      ))
                    GROUP BY r.activation_tier
                    """,
                    (principal.user_id, principal.user_id),
                ).fetchall()
            }
            object_row = conn.execute(
                """
                SELECT COALESCE(SUM(o.original_size),0),
                       COALESCE(SUM(o.stored_size),0),COUNT(*)
                FROM memory_objects o WHERE o.owner_user_id=?
                  AND (o.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=o.space_id AND sm.user_id=?
                  ))
                """,
                (principal.user_id, principal.user_id),
            ).fetchone()
            canonical_row = conn.execute(
                """
                SELECT COALESCE(SUM(length(v.content_ciphertext)),0),
                       COALESCE(SUM(length(v.wrapped_data_key)),0), COUNT(*)
                FROM memory_revisions v JOIN memory_records r ON r.memory_id=v.memory_id
                WHERE r.owner_user_id=?
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                """,
                (principal.user_id, principal.user_id),
            ).fetchone()
            archive_row = conn.execute(
                """
                SELECT COALESCE(SUM(size_bytes),0),COUNT(*),
                       COALESCE(SUM(CASE WHEN state!='verified' THEN 1 ELSE 0 END),0)
                FROM memory_archive_registry WHERE owner_user_id=?
                """,
                (principal.user_id,),
            ).fetchone()
            recent_row = conn.execute(
                """
                SELECT COALESCE(SUM(length(v.content_ciphertext)),0), COUNT(*)
                FROM memory_revisions v JOIN memory_records r ON r.memory_id=v.memory_id
                WHERE r.owner_user_id=? AND v.created_at>=?
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                """,
                (
                    principal.user_id,
                    (datetime.now(UTC) - timedelta(days=30)).isoformat(),
                    principal.user_id,
                ),
            ).fetchone()
            jobs = {
                str(row["state"]): int(row["count"])
                for row in conn.execute(
                    "SELECT state, COUNT(*) AS count FROM memory_jobs WHERE owner_user_id = ? GROUP BY state",
                    (principal.user_id,),
                ).fetchall()
            }
            access_row = conn.execute(
                """
                SELECT COALESCE(SUM(retrieval_count),0),
                       COALESCE(SUM(retrieval_latency_total_ms),0),
                       COALESCE(MAX(last_retrieval_latency_ms),0)
                FROM memory_access_metrics a
                JOIN memory_records r ON r.memory_id=a.memory_id
                WHERE r.owner_user_id=?
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                """,
                (principal.user_id, principal.user_id),
            ).fetchone()
            shared_accounting = [
                {
                    "space_id": str(row["space_id"]),
                    "record_count": int(row["record_count"]),
                    "canonical_payload_bytes": int(row["payload_bytes"]),
                }
                for row in conn.execute(
                    """
                    SELECT r.space_id,COUNT(DISTINCT r.memory_id) AS record_count,
                           COALESCE(SUM(length(v.content_ciphertext)),0) AS payload_bytes
                    FROM memory_records r
                    JOIN memory_revisions v ON v.memory_id=r.memory_id
                    WHERE r.owner_user_id=? AND r.space_id IS NOT NULL
                      AND r.status!='deleted'
                      AND EXISTS (
                        SELECT 1 FROM shared_space_members sm
                        WHERE sm.space_id=r.space_id AND sm.user_id=?
                      )
                    GROUP BY r.space_id ORDER BY r.space_id
                    """,
                    (principal.user_id, principal.user_id),
                ).fetchall()
            ]
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        account_canonical_bytes = int(canonical_row[0]) + int(canonical_row[1])
        account_object_bytes = int(object_row[1])
        account_archive_bytes = int(archive_row[0])
        account_managed_bytes = (
            account_canonical_bytes + account_object_bytes + account_archive_bytes
        )
        budget_bytes = (
            int(settings.storage_budget_value * 1024 * 1024)
            if settings.storage_budget_mode == "absolute_mb"
            else int(usage.total * settings.storage_budget_value / 100.0)
        )
        managed_budget_ceiling_bytes: int | None = None
        if managed:
            managed_budget_ceiling_bytes = int(
                managed_policy.get(
                    "storage_budget_mb_ceiling",
                    max(1, budget_bytes // (1024 * 1024)),
                )
            ) * 1024 * 1024
            budget_bytes = min(budget_bytes, managed_budget_ceiling_bytes)
        recent_daily_growth = int(recent_row[0]) / 30.0
        retrieval_count = int(access_row[0])
        compute_resources = resource_snapshot()
        projected_30_day_bytes = account_managed_bytes + int(recent_daily_growth * 30)
        reserve_bytes = settings.emergency_free_space_reserve_mb * 1024 * 1024
        reserve_pressure = usage.free < reserve_bytes
        budget_pressure = account_managed_bytes > budget_bytes
        projected_pressure = projected_30_day_bytes > budget_bytes
        pressure = reserve_pressure or budget_pressure
        if apply_pause:
            self.repository.set_storage_pressure_pause(reserve_pressure)
        paused = 0
        actions_applied: list[dict[str, Any]] = []
        if apply_pause and pressure:
            with self.repository.transaction() as conn:
                paused = conn.execute(
                    """
                    UPDATE memory_jobs SET state = 'paused_storage_pressure', updated_at = ?,
                        result_code = 'emergency_free_space_reserve'
                    WHERE owner_user_id = ? AND state = 'pending'
                      AND job_kind NOT LIKE 'fts_%' AND job_kind NOT LIKE 'semantic_delete:%'
                    """,
                    (utc_now(), principal.user_id),
                ).rowcount
            actions_applied.append(
                {"action": "pause_nonessential_jobs", "affected": paused}
            )
            orphan_cleanup = self.objects.garbage_collect_orphans()
            actions_applied.append(
                {"action": "deduplicate_and_collect_unreferenced", **orphan_cleanup}
            )
            # A WAL checkpoint releases already-unneeded frames without the
            # temporary disk amplification of VACUUM under severe pressure.
            try:
                with self.repository.connect() as conn:
                    checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                actions_applied.append(
                    {
                        "action": "compact_wal",
                        "completed": bool(checkpoint and int(checkpoint[0]) == 0),
                    }
                )
            except sqlite3.Error:
                actions_applied.append(
                    {"action": "compact_wal", "completed": False}
                )
            if budget_pressure and not reserve_pressure:
                tier_result = self._tier_maintenance(principal)
                actions_applied.append(
                    {
                        "action": "tier_and_cold_archive",
                        "records_moved": tier_result["records_moved"],
                    }
                )
        return {
            "state": "pressure" if pressure else "ready",
            "storage_profile": settings.memory_storage_profile,
            "budget": {
                "mode": settings.storage_budget_mode,
                "value": settings.storage_budget_value,
                "effective_bytes": budget_bytes,
                "current_authorized_bytes": account_managed_bytes,
                "percent_used": round(account_managed_bytes * 100 / max(1, budget_bytes), 2),
                "projected_30_day_bytes": projected_30_day_bytes,
                "projected_pressure": projected_pressure,
                "managed_profile_ceiling_applied": managed,
                "managed_profile_ceiling_bytes": managed_budget_ceiling_bytes,
            },
            "disk": {
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "emergency_reserve_bytes": reserve_bytes,
            },
            "tier_counts": tiers,
            "canonical": {
                "authorized_revision_payload_bytes": account_canonical_bytes,
                "authorized_revision_count": int(canonical_row[2]),
                "database_page_count": page_count,
                "database_freelist_pages": freelist,
                "database_fragmentation_percent": round(
                    freelist * 100 / max(1, page_count), 2
                ),
                "database_allocated_bytes": page_size * page_count,
                "content_included": False,
            },
            "objects": {
                "original_bytes": int(object_row[0]),
                "stored_bytes": int(object_row[1]),
                "object_count": int(object_row[2]),
                "dedup_or_compression_savings_bytes": max(0, int(object_row[0]) - int(object_row[1])),
            },
            "archives": {
                "bytes": account_archive_bytes,
                "count": int(archive_row[1]),
                "degraded_count": int(archive_row[2]),
                "last_verified_at": (
                    max(
                        (
                            str(item["verified_at"])
                            for item in self.archive_status(principal)["archives"]
                            if item.get("verified_at")
                        ),
                        default=None,
                    )
                ),
            },
            "projections": {
                "lexical_authorized": _authorized_fts_usage(
                    self.repository.paths.memory_fts_database_path,
                    principal.user_id,
                    current_space_ids,
                ),
                "semantic_profile_configured": self.repository.paths.memory_semantic_client_config_path.is_file(),
                "cross_account_sizes_exposed": False,
                "derived_and_rebuildable": True,
            },
            "growth": {
                "last_30_day_revision_bytes": int(recent_row[0]),
                "last_30_day_revision_count": int(recent_row[1]),
                "estimated_daily_bytes": round(recent_daily_growth, 2),
            },
            "retrieval": {
                "authorized_retrieval_count": retrieval_count,
                "average_canonical_latency_ms": round(
                    float(access_row[1]) / max(1, retrieval_count), 3
                ),
                "latest_record_max_latency_ms": round(float(access_row[2]), 3),
            },
            "resource_snapshot": {
                "system": compute_resources.get("system", {}),
                "gpu": compute_resources.get("gpu", {}),
                "content_included": False,
            },
            "shared_space_accounting": shared_accounting,
            "cross_account_accounting_exposed": False,
            "failure_history": {
                "failed_jobs": int(jobs.get("failed", 0)),
                "interrupted_jobs": int(jobs.get("interrupted", 0)),
                "paused_storage_pressure_jobs": int(
                    jobs.get("paused_storage_pressure", 0)
                ),
            },
            "jobs": jobs,
            "jobs_paused_now": paused,
            "actions_applied": actions_applied,
            "pressure_reasons": [
                reason
                for reason, active in (
                    ("emergency_free_space_reserve", reserve_pressure),
                    ("authorized_storage_budget", budget_pressure),
                )
                if active
            ],
            "silent_hard_delete_allowed": False,
            "response_order": ["tier", "compact", "compress", "deduplicate", "archive", "ask_before_delete"],
            "raw_paths_exposed": False,
        }

    @staticmethod
    def _assert_job_authorized(
        *,
        job_kind: str,
        settings: Any,
        managed: bool,
        policy: dict[str, Any],
    ) -> None:
        """Enforce mutable user/Admin ceilings both at queue and execution time."""

        if managed:
            if job_kind == "managed_backup" and not bool(policy.get("managed_backups_allowed", True)):
                raise MemoryAuthorizationError("Managed-profile policy does not allow managed backups.")
            if job_kind in {"tier_maintenance", "archive_compression"}:
                if not bool(policy.get("cold_archive_allowed", True)):
                    raise MemoryAuthorizationError("Managed-profile policy does not allow cold archival.")
                if not bool(policy.get("managed_backups_allowed", True)):
                    raise MemoryAuthorizationError(
                        "Safe cold archival requires managed backup authority."
                    )
            if job_kind in {
                "conversation_compaction", "semantic_candidates",
                "duplicate_detection", "relation_candidates",
                "contradiction_scan", "project_summary_refresh",
                "metacognitive_statistics", "consolidation", "replay_validation",
            } and not bool(policy.get("consolidation_allowed", True)):
                raise MemoryAuthorizationError("Managed-profile policy does not allow consolidation jobs.")
        if not settings.consolidation_enabled and job_kind in {
            "conversation_compaction", "semantic_candidates",
            "duplicate_detection", "relation_candidates",
            "contradiction_scan", "project_summary_refresh",
            "metacognitive_statistics", "consolidation", "replay_validation",
        }:
            raise MemoryReleaseError("Memory consolidation is disabled in Settings.")
        if job_kind == "managed_backup" and not settings.backup_enabled:
            raise MemoryReleaseError("Managed backup is disabled in Settings.")

    def submit_job(self, principal: MemoryPrincipal, job_kind: str) -> dict[str, Any]:
        settings = self.fabric.settings(principal)
        managed, policy = self._managed_governance()
        self._assert_job_authorized(
            job_kind=job_kind,
            settings=settings,
            managed=managed,
            policy=policy,
        )
        if emergency_active(self.repository.paths):
            raise MemoryReleaseError("Memory maintenance is paused by emergency stop.")
        with self.repository.connect() as conn:
            active = int(conn.execute(
                "SELECT COUNT(*) FROM memory_jobs WHERE owner_user_id = ? AND state IN ('pending','running') AND job_kind LIKE 'part2e:%'",
                (principal.user_id,),
            ).fetchone()[0])
        if active >= settings.max_background_jobs:
            raise MemoryReleaseError("The configured background-job ceiling is reached.")
        job_id = new_id("memoryjob")
        now = utc_now()
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_jobs (
                    job_id, owner_user_id, job_kind, state, progress_current,
                    progress_total, created_at, updated_at, result_code,
                    priority, checkpoint_json
                ) VALUES (?, ?, ?, 'pending', 0, 1, ?, ?, NULL, 'background', '{}')
                """,
                (job_id, principal.user_id, f"part2e:{job_kind}", now, now),
            )
        return {"job_id": job_id, "job_kind": job_kind, "state": "pending"}

    def run_job(self, principal: MemoryPrincipal, job_id: str) -> dict[str, Any]:
        if emergency_active(self.repository.paths):
            raise MemoryReleaseError("Memory maintenance is paused by emergency stop.")
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_jobs WHERE job_id = ? AND owner_user_id = ?",
                (job_id, principal.user_id),
            ).fetchone()
        if row is None or not str(row["job_kind"]).startswith("part2e:"):
            raise MemoryReleaseError("The memory-maintenance job is unavailable.")
        if str(row["state"]) not in {"pending", "interrupted", "failed"}:
            return {"job_id": job_id, "state": str(row["state"]), "idempotent": True}
        kind = str(row["job_kind"]).split(":", 1)[1]
        settings = self.fabric.settings(principal)
        managed, policy = self._managed_governance()
        self._assert_job_authorized(
            job_kind=kind,
            settings=settings,
            managed=managed,
            policy=policy,
        )
        cpu_ceiling = min(
            settings.cpu_percent_ceiling,
            int(policy.get("cpu_percent_ceiling", settings.cpu_percent_ceiling))
            if managed
            else settings.cpu_percent_ceiling,
        )
        ram_ceiling = min(
            settings.ram_mb_ceiling,
            int(policy.get("ram_mb_ceiling", settings.ram_mb_ceiling))
            if managed
            else settings.ram_mb_ceiling,
        )
        vram_ceiling = min(
            settings.vram_mb_ceiling,
            int(policy.get("vram_mb_ceiling", settings.vram_mb_ceiling))
            if managed
            else settings.vram_mb_ceiling,
        )
        estimated_cpu = (
            min(settings.consolidation_resource_percent, cpu_ceiling)
            if kind in {"consolidation", "replay_validation"}
            else min(25, cpu_ceiling)
        )
        workload = WorkloadDescriptor(
            workload_id=job_id,
            owner_user_id=principal.user_id,
            task_kind=f"memory_{kind}",
            priority="background",
            estimated_cpu_percent=estimated_cpu,
            estimated_ram_mb=min(512, ram_ceiling),
            cancellable=True,
            preemptible=True,
            cpu_fallback_allowed=True,
            required_resources=("canonical_memory", "cpu"),
            estimate_source="part2e_bounded_job_profile",
        )
        decision = decide_compute(
            workload,
            # These deterministic SQLite/object jobs have no CUDA
            # implementation. Claiming a GPU decision would be fake routing.
            preference="cpu",
            cpu_percent_ceiling=cpu_ceiling,
            ram_mb_ceiling=ram_ceiling,
            vram_mb_ceiling=vram_ceiling,
            max_background_jobs=settings.max_background_jobs,
            paths=self.repository.paths,
        )
        if decision.decision in {"deferred", "rejected"}:
            state = "pending" if decision.decision == "deferred" else "failed"
            with self.repository.transaction() as conn:
                conn.execute(
                    "UPDATE memory_jobs SET state=?, updated_at=?, result_code=? WHERE job_id=?",
                    (state, utc_now(), f"compute_{decision.decision}", job_id),
                )
            return {
                "job_id": job_id,
                "state": state,
                "compute_decision": decision.decision,
                "reasons": list(decision.reasons),
            }
        reservation = decision.reservation_id
        if not reservation:
            raise MemoryReleaseError("The Compute Governor did not issue a job reservation.")
        with self.repository.transaction() as conn:
            conn.execute(
                "UPDATE memory_jobs SET state='running', cancel_requested=0, started_at=?, updated_at=?, attempt_count=attempt_count+1 WHERE job_id=?",
                (utc_now(), utc_now(), job_id),
            )
        try:
            self._checkpoint_job(principal, job_id, {"phase": "started", "kind": kind})
            if self._job_cancelled(principal, job_id):
                raise InterruptedError("Memory maintenance was cancelled before execution.")
            if kind == "graph_rebuild":
                result = self.rebuild_graph(principal)
            elif kind in {"object_integrity", "integrity_check"}:
                recovery = self.objects.garbage_collect_orphans()
                result = {
                    **self.objects.verify(principal=principal),
                    "orphan_recovery": recovery,
                    "canonical": self.repository.health(),
                    "graph": self.graph_health(principal),
                    "archives": self.archive_status(principal),
                }
            elif kind == "homeostasis":
                result = self.homeostasis(principal, apply_pause=True)
            elif kind == "tier_maintenance":
                result = self._tier_maintenance(principal, job_id=job_id)
            elif kind == "managed_backup":
                managed_material = sha256(self.fabric.encryption.account_key(principal)).hexdigest()
                result = self.export_archive(
                    principal,
                    MemoryArchiveExportRequest(
                        recovery_material=managed_material,
                        archive_kind="managed_backup",
                    ),
                    job_id=job_id,
                )
                result["retention"] = self._enforce_backup_retention(principal)
            elif kind == "fts_rebuild":
                from app.cognition.fts_projection import FtsMemoryProjection
                result = FtsMemoryProjection(
                    paths=self.repository.paths, repository=self.repository, fabric=self.fabric
                ).repair_and_rebuild(principal)
            elif kind in {"embedding_rebuild", "projection_rebuild"}:
                from app.cognition.fts_projection import FtsMemoryProjection
                from app.cognition.semantic_projection import SemanticMemoryProjection

                fts = FtsMemoryProjection(
                    paths=self.repository.paths,
                    repository=self.repository,
                    fabric=self.fabric,
                ).repair_and_rebuild(principal)
                semantic = SemanticMemoryProjection(
                    paths=self.repository.paths,
                    repository=self.repository,
                    fabric=self.fabric,
                )
                semantic_result = (
                    semantic.rebuild(principal)
                    if semantic.configured
                    else {"state": "optional_not_configured", "canonical_memory_mutated": False}
                )
                result = {
                    "state": "ready",
                    "fts": fts,
                    "semantic": semantic_result,
                    "graph": self.rebuild_graph(principal),
                }
            elif kind in {"consolidation", "duplicate_detection"}:
                result = self._consolidation_candidates(principal, job_id=job_id)
            elif kind == "conversation_compaction":
                result = self._authority_summary_candidates(
                    principal, target_type="conversation", job_id=job_id
                )
            elif kind == "project_summary_refresh":
                result = self._authority_summary_candidates(
                    principal, target_type="project", job_id=job_id
                )
            elif kind == "semantic_candidates":
                result = self._semantic_candidates(principal, job_id=job_id)
            elif kind == "relation_candidates":
                result = self._relation_candidates(principal, job_id=job_id)
            elif kind == "contradiction_scan":
                result = self._contradiction_candidates(principal, job_id=job_id)
            elif kind == "archive_compression":
                result = self._archive_compression_audit(principal)
            elif kind == "metacognitive_statistics":
                result = self._metacognitive_statistics(principal)
            elif kind == "replay_validation":
                result = self._replay_validation(principal)
            else:
                raise MemoryReleaseError("The memory-maintenance job kind is unsupported.")
            if self._job_cancelled(principal, job_id):
                raise InterruptedError("Memory maintenance was cancelled before commit.")
            with self.repository.transaction() as conn:
                conn.execute(
                    "UPDATE memory_jobs SET state='completed', progress_current=1, completed_at=?, updated_at=?, result_code='completed', checkpoint_json=? WHERE job_id=?",
                    (utc_now(), utc_now(), json.dumps({"content_free": True, "result_state": result.get("state", "completed")}), job_id),
                )
            self.compute.release_job(reservation, reason="completed")
            return {"job_id": job_id, "state": "completed", "result": result}
        except InterruptedError:
            with self.repository.transaction() as conn:
                conn.execute(
                    "UPDATE memory_jobs SET state='interrupted', updated_at=?, result_code='cancelled_or_preempted' WHERE job_id=?",
                    (utc_now(), job_id),
                )
            self.compute.release_job(reservation, reason="cancelled_or_preempted")
            return {"job_id": job_id, "state": "interrupted", "resumable": True}
        except Exception as exc:
            with self.repository.transaction() as conn:
                conn.execute(
                    "UPDATE memory_jobs SET state='failed', error_code=?, updated_at=?, result_code='failed' WHERE job_id=?",
                    (type(exc).__name__, utc_now(), job_id),
                )
            self.compute.release_job(reservation, reason="failed")
            raise

    def _candidate_feedback_exists(
        self, principal: MemoryPrincipal, feedback_code: str
    ) -> bool:
        with self.repository.connect() as conn:
            return conn.execute(
                """
                SELECT 1 FROM memory_candidates c
                JOIN memory_records r ON r.memory_id=c.memory_id
                WHERE r.owner_user_id=?
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                  AND c.feedback_code=?
                LIMIT 1
                """,
                (principal.user_id, principal.user_id, feedback_code),
            ).fetchone() is not None

    def _create_derived_candidate(
        self,
        principal: MemoryPrincipal,
        request: MemoryCandidateCreateRequest,
        *,
        feedback_code: str,
        source_memory_ids: list[str] | None = None,
    ) -> bool:
        if self._candidate_feedback_exists(principal, feedback_code):
            return False
        candidate = self.fabric.create_candidate(principal, request)
        for source_id in source_memory_ids or []:
            self.fabric.add_relation(
                principal,
                candidate.memory_id,
                MemoryRelationCreateRequest(
                    target_type="memory",
                    target_id=source_id,
                    relation_type="sourced_from",
                    confidence=1.0,
                    inferred=False,
                    provenance_source_id=request.source.source_id,
                ),
            )
        with self.repository.transaction() as conn:
            conn.execute(
                "UPDATE memory_candidates SET feedback_code=? WHERE memory_id=?",
                (feedback_code, candidate.memory_id),
            )
        return True

    def _authority_summary_candidates(
        self,
        principal: MemoryPrincipal,
        *,
        target_type: str,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        settings = self.fabric.settings(principal)
        if settings.candidate_behavior == "direct_explicit_only":
            return {
                "state": "disabled_by_candidate_behavior",
                "candidate_count": 0,
                "autobiographical_truth_created": False,
            }
        with self.repository.connect() as conn:
            groups = conn.execute(
                """
                SELECT rel.target_id, GROUP_CONCAT(r.memory_id) AS memory_ids,
                       COUNT(*) AS memory_count
                FROM memory_relations rel
                JOIN memory_records r ON r.memory_id=rel.source_memory_id
                WHERE r.owner_user_id=? AND r.status='active'
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                  AND r.privacy!='sealed' AND rel.target_type=?
                  AND rel.status='active'
                GROUP BY rel.target_id HAVING COUNT(*) >= 2
                ORDER BY rel.target_id LIMIT 100
                """,
                (principal.user_id, principal.user_id, target_type),
            ).fetchall()
        created = skipped = 0
        for group in groups:
            if job_id and self._job_cancelled(principal, job_id):
                raise InterruptedError
            source_ids = sorted(set(str(group["memory_ids"]).split(",")))
            records = [self.fabric.get(principal, value) for value in source_ids]
            privacy = (
                MemoryPrivacy.PRIVATE
                if any(item.privacy == MemoryPrivacy.PRIVATE for item in records)
                else MemoryPrivacy.NORMAL
            )
            authority_id = str(group["target_id"])
            feedback_code = _digest(
                {"summary_authority": target_type, "id": authority_id, "sources": source_ids}
            )
            exact_titles = [item.title for item in records[:20]]
            kwargs: dict[str, Any] = {
                "conversation_id" if target_type == "conversation" else "project_id": authority_id
            }
            request = MemoryCandidateCreateRequest(
                title=f"Review {target_type} continuity summary",
                body="\n".join(f"- {title}" for title in exact_titles),
                why_stored=(
                    f"Deterministic compaction of {len(source_ids)} authorized canonical "
                    f"memories linked to one {target_type}; source history is unchanged."
                ),
                scope=target_type,
                privacy=privacy,
                form="metacognitive",
                subtype=f"{target_type}_compaction_candidate",
                importance=0.4,
                confidence=1.0,
                candidate_kind=f"{target_type}_compaction_candidate",
                proposed_wording="\n".join(exact_titles),
                evidence_summary=f"{len(source_ids)} canonical source memories; no transcript/project duplication.",
                form_data={
                    "metric": f"{target_type}_continuity_compaction",
                    "source_memory_ids": source_ids,
                    "source_count": len(source_ids),
                    "model_generated": False,
                },
                source=MemorySourceInput(
                    source_type="deterministic_compaction",
                    source_id=feedback_code,
                    source_authority="canonical_memory_fabric",
                    retrieval_method="stable_authority_link_grouping",
                    provenance_status="derived_review_required",
                ),
                **kwargs,
            )
            if self._create_derived_candidate(
                principal,
                request,
                feedback_code=feedback_code,
                source_memory_ids=source_ids,
            ):
                created += 1
            else:
                skipped += 1
        return {
            "state": "ready",
            "candidate_count": created,
            "existing_candidates_skipped": skipped,
            "source_authority_mutated": False,
            "model_generated": False,
            "owner_review_required": True,
        }

    def _semantic_candidates(
        self, principal: MemoryPrincipal, *, job_id: str | None = None
    ) -> dict[str, Any]:
        settings = self.fabric.settings(principal)
        if settings.candidate_behavior == "direct_explicit_only":
            return {"state": "disabled_by_candidate_behavior", "candidate_count": 0}
        records, _total = self.fabric.list(
            principal,
            MemoryQuery(form=MemoryForm.EPISODIC, status=MemoryLifecycle.ACTIVE, limit=100),
        )
        created = 0
        for source in records:
            if job_id and self._job_cancelled(principal, job_id):
                raise InterruptedError
            if source.privacy == MemoryPrivacy.SEALED:
                continue
            durable_claim = str(source.form_data.get("outcome") or "").strip()
            if not durable_claim:
                continue
            feedback_code = _digest(
                {"semantic_source": source.memory_id, "revision": source.current_revision_id}
            )
            request = MemoryCandidateCreateRequest(
                title=f"Review durable conclusion from {source.title}",
                body=durable_claim,
                why_stored="An explicit episodic outcome may be useful as durable knowledge after owner review.",
                privacy=source.privacy,
                form="semantic",
                subtype="episodic_outcome_candidate",
                confidence=source.confidence,
                candidate_kind="semantic_evidence_candidate",
                proposed_wording=durable_claim,
                evidence_summary="One authorized canonical episode supplies this exact outcome wording.",
                form_data={
                    "confirmation": "candidate_review_required",
                    "source_memory_id": source.memory_id,
                    "model_generated": False,
                },
                source=MemorySourceInput(
                    source_type="canonical_memory",
                    source_id=source.memory_id,
                    source_authority="canonical_memory_fabric",
                    retrieval_method="explicit_episode_outcome",
                    provenance_status="derived_review_required",
                ),
            )
            created += int(
                self._create_derived_candidate(
                    principal,
                    request,
                    feedback_code=feedback_code,
                    source_memory_ids=[source.memory_id],
                )
            )
        return {
            "state": "ready",
            "candidate_count": created,
            "automatic_promotions": 0,
            "autobiographical_truth_created": False,
        }

    def _relation_candidates(
        self, principal: MemoryPrincipal, *, job_id: str | None = None
    ) -> dict[str, Any]:
        settings = self.fabric.settings(principal)
        if settings.candidate_behavior == "direct_explicit_only":
            return {"state": "disabled_by_candidate_behavior", "candidate_count": 0}
        with self.repository.connect() as conn:
            groups = conn.execute(
                """
                SELECT rel.target_type,rel.target_id,
                       GROUP_CONCAT(r.memory_id) AS memory_ids,COUNT(*) AS memory_count
                FROM memory_relations rel
                JOIN memory_records r ON r.memory_id=rel.source_memory_id
                WHERE r.owner_user_id=? AND r.status='active'
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                  AND r.privacy!='sealed'
                  AND rel.target_type IN ('conversation','project')
                  AND rel.status='active'
                GROUP BY rel.target_type,rel.target_id HAVING COUNT(*) >= 2
                ORDER BY rel.target_type,rel.target_id LIMIT 100
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
        created = 0
        for group in groups:
            if job_id and self._job_cancelled(principal, job_id):
                raise InterruptedError
            source_ids = sorted(set(str(group["memory_ids"]).split(",")))
            records = [self.fabric.get(principal, value) for value in source_ids]
            privacy = (
                MemoryPrivacy.PRIVATE
                if any(item.privacy == MemoryPrivacy.PRIVATE for item in records)
                else MemoryPrivacy.NORMAL
            )
            target_type = str(group["target_type"])
            target_id = str(group["target_id"])
            feedback_code = _digest(
                {
                    "relation_authority": target_type,
                    "target_id": target_id,
                    "sources": source_ids,
                }
            )
            request = MemoryCandidateCreateRequest(
                title=f"Review relation among {target_type}-linked memories",
                body=(
                    f"{len(source_ids)} canonical memories share explicit {target_type} "
                    "provenance; review whether a durable relation is useful."
                ),
                why_stored="Stable authority links provide deterministic relation evidence but do not prove a semantic relationship.",
                privacy=privacy,
                form="relational",
                subtype="relation_extraction_candidate",
                candidate_kind="relation_extraction_candidate",
                proposed_wording=f"related_through_{target_type}",
                evidence_summary=f"{len(source_ids)} canonical source memories share one explicit authority.",
                form_data={
                    "relation": f"related_through_{target_type}",
                    "target": target_id,
                    "source_memory_ids": source_ids,
                    "model_generated": False,
                },
                source=MemorySourceInput(
                    source_type="deterministic_relation_scan",
                    source_id=feedback_code,
                    source_authority="canonical_memory_fabric",
                    retrieval_method="shared_stable_authority",
                    provenance_status="derived_review_required",
                ),
            )
            created += int(
                self._create_derived_candidate(
                    principal,
                    request,
                    feedback_code=feedback_code,
                    source_memory_ids=source_ids,
                )
            )
        return {
            "state": "ready",
            "candidate_count": created,
            "graph_mutated": False,
            "owner_review_required": True,
        }

    def _contradiction_candidates(
        self, principal: MemoryPrincipal, *, job_id: str | None = None
    ) -> dict[str, Any]:
        settings = self.fabric.settings(principal)
        if settings.candidate_behavior == "direct_explicit_only":
            return {"state": "disabled_by_candidate_behavior", "candidate_count": 0}
        records, _total = self.fabric.list(
            principal,
            MemoryQuery(form=MemoryForm.SEMANTIC, status=MemoryLifecycle.ACTIVE, limit=200),
        )
        groups: dict[str, list[Any]] = {}
        for record in records:
            if record.privacy == MemoryPrivacy.SEALED:
                continue
            groups.setdefault(" ".join(record.title.casefold().split()), []).append(record)
        created = 0
        for subject, claims in sorted(groups.items()):
            if len(claims) < 2 or len({item.body for item in claims}) < 2:
                continue
            if job_id and self._job_cancelled(principal, job_id):
                raise InterruptedError
            source_ids = sorted(item.memory_id for item in claims)
            feedback_code = _digest(
                {"contradiction_subject": subject, "source_memory_ids": source_ids}
            )
            privacy = (
                MemoryPrivacy.PRIVATE
                if any(item.privacy == MemoryPrivacy.PRIVATE for item in claims)
                else MemoryPrivacy.NORMAL
            )
            request = MemoryCandidateCreateRequest(
                title="Review potentially conflicting active claims",
                body=f"{len(claims)} active semantic claims share one normalized subject and differ in wording.",
                why_stored="A deterministic scan found a possible conflict; it did not decide which claim is true.",
                privacy=privacy,
                form="metacognitive",
                subtype="contradiction_review_candidate",
                candidate_kind="contradiction_review_candidate",
                proposed_wording="Review the linked claims as changed reality, contradiction, refinement, or corroboration.",
                evidence_summary=f"{len(claims)} source-independent canonical claim records require review.",
                form_data={
                    "metric": "possible_semantic_conflict",
                    "source_memory_ids": source_ids,
                    "model_generated": False,
                },
                source=MemorySourceInput(
                    source_type="deterministic_contradiction_scan",
                    source_id=feedback_code,
                    source_authority="canonical_memory_fabric",
                    retrieval_method="normalized_subject_distinct_claim",
                    provenance_status="derived_review_required",
                ),
            )
            created += int(
                self._create_derived_candidate(
                    principal,
                    request,
                    feedback_code=feedback_code,
                    source_memory_ids=source_ids,
                )
            )
        return {
            "state": "ready",
            "candidate_count": created,
            "truth_selected": False,
            "source_records_mutated": False,
        }

    def _archive_compression_audit(
        self, principal: MemoryPrincipal
    ) -> dict[str, Any]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT archive_id,path_token,checksum,format_version,size_bytes
                FROM memory_archive_registry
                WHERE owner_user_id=? AND archive_kind='managed_backup'
                ORDER BY archive_id
                """,
                (principal.user_id,),
            ).fetchall()
        verified = 0
        for row in rows:
            path = self.repository.paths.memory_backup_dir / str(row["path_token"])
            if not path.is_file() or path.is_symlink():
                raise MemoryReleaseError("A managed archive is unavailable for integrity audit.")
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != str(row["checksum"]):
                raise MemoryReleaseError("A managed archive failed compression integrity audit.")
            envelope = json.loads(raw[len(ARCHIVE_MAGIC):].decode("utf-8"))
            if int(envelope.get("format_version") or 0) != ARCHIVE_VERSION or str(
                envelope.get("compression")
            ) != "zstd-9":
                raise MemoryReleaseError(
                    "A legacy managed archive requires explicit versioned restore/migration."
                )
            verified += 1
        return {
            "state": "ready",
            "managed_archives_verified": verified,
            "compression": "zstd-9",
            "portable_user_exports_mutated": False,
        }

    def _metacognitive_statistics(
        self, principal: MemoryPrincipal
    ) -> dict[str, Any]:
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*),COALESCE(SUM(a.retrieval_count),0),
                       COALESCE(SUM(a.rehydration_count),0)
                FROM memory_records r
                LEFT JOIN memory_access_metrics a ON a.memory_id=r.memory_id
                WHERE r.owner_user_id=? AND r.status!='deleted'
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                """,
                (principal.user_id, principal.user_id),
            ).fetchone()
            contradiction_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM memory_contradictions c
                    JOIN memory_records r ON r.memory_id=c.left_memory_id
                    WHERE r.owner_user_id=? AND c.status='unresolved'
                      AND (r.space_id IS NULL OR EXISTS (
                        SELECT 1 FROM shared_space_members sm
                        WHERE sm.space_id=r.space_id AND sm.user_id=?
                      ))
                    """,
                    (principal.user_id, principal.user_id),
                ).fetchone()[0]
            )
        return {
            "state": "ready",
            "authorized_record_count": int(row[0]),
            "retrieval_count": int(row[1]),
            "rehydration_count": int(row[2]),
            "unresolved_contradiction_count": contradiction_count,
            "memory_content_included": False,
            "hidden_reasoning_included": False,
            "authority_granted": False,
        }

    def _consolidation_candidates(
        self, principal: MemoryPrincipal, *, job_id: str | None = None
    ) -> dict[str, Any]:
        settings = self.fabric.settings(principal)
        if settings.candidate_behavior == "direct_explicit_only":
            return {
                "state": "disabled_by_candidate_behavior",
                "candidate_count": 0,
                "autobiographical_truth_created": False,
            }
        with self.repository.connect() as conn:
            duplicate_groups = conn.execute(
                """
                SELECT v.plaintext_hash, r.privacy, COUNT(*) AS duplicate_count,
                       GROUP_CONCAT(r.memory_id) AS memory_ids
                FROM memory_records r
                JOIN memory_revisions v ON v.revision_id=r.current_revision_id
                WHERE r.owner_user_id=? AND r.status='active'
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                  AND r.form!='audit' AND r.privacy!='sealed'
                GROUP BY v.plaintext_hash, r.privacy HAVING COUNT(*) > 1
                ORDER BY MIN(r.memory_id)
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
        created = 0
        skipped = 0
        for group in duplicate_groups:
            if job_id and self._job_cancelled(principal, job_id):
                raise InterruptedError
            source_ids = sorted(str(group["memory_ids"]).split(","))
            evidence_code = _digest({"exact_duplicate_set": source_ids})
            with self.repository.connect() as conn:
                exists = conn.execute(
                    """
                    SELECT 1 FROM memory_candidates c
                    JOIN memory_records r ON r.memory_id=c.memory_id
                    WHERE r.owner_user_id=? AND c.review_state='pending'
                      AND (r.space_id IS NULL OR EXISTS (
                        SELECT 1 FROM shared_space_members sm
                        WHERE sm.space_id=r.space_id AND sm.user_id=?
                      ))
                      AND c.feedback_code=?
                    """,
                    (principal.user_id, principal.user_id, evidence_code),
                ).fetchone()
            if exists:
                skipped += 1
                continue
            keep_id = source_ids[0]
            proposal = self.fabric.create_candidate(
                principal,
                MemoryCandidateCreateRequest(
                    title="Review exact duplicate memory consolidation",
                    body=(
                        f"Keep canonical memory {keep_id} and mark "
                        f"{len(source_ids) - 1} exact duplicate record(s) superseded."
                    ),
                    why_stored="Deterministic exact-content duplicate evidence requires owner review.",
                    scope="user",
                    form="metacognitive",
                    subtype="consolidation_duplicate_set",
                    privacy=str(group["privacy"]),
                    importance=0.2,
                    confidence=1.0,
                    candidate_kind="consolidation_duplicate_set",
                    proposed_wording="Approve a non-destructive supersession of exact duplicates.",
                    evidence_summary=f"{len(source_ids)} owner-scoped records share an authenticated content digest.",
                    form_data={
                        "metric": "authenticated_exact_duplicate_set",
                        "canonical_memory_id": keep_id,
                        "source_memory_ids": source_ids,
                        "operation": "mark_exact_duplicates_superseded",
                        "model_generated": False,
                    },
                    source=MemorySourceInput(
                        source_type="deterministic_consolidation",
                        source_id=evidence_code,
                        source_authority="canonical_memory_fabric",
                        retrieval_method="owner_scoped_authenticated_digest_equality",
                        provenance_status="derived_review_required",
                    ),
                ),
            )
            with self.repository.transaction() as conn:
                conn.execute(
                    "UPDATE memory_candidates SET feedback_code=? WHERE memory_id=?",
                    (evidence_code, proposal.memory_id),
                )
            created += 1
            if job_id:
                self._checkpoint_job(
                    principal, job_id,
                    {"phase": "candidate_review", "groups_processed": created + skipped},
                )
        return {
            "state": "ready",
            "candidate_count": created,
            "existing_candidates_skipped": skipped,
            "model_generated": False,
            "autobiographical_truth_created": False,
            "owner_approval_required": True,
        }

    def _replay_validation(self, principal: MemoryPrincipal) -> dict[str, Any]:
        records, total = self.fabric.list(
            principal,
            MemoryQuery(include_archived=True, limit=200, offset=0),
        )
        statuses: dict[str, int] = {}
        for record in records:
            statuses[record.status.value] = statuses.get(record.status.value, 0) + 1
        return {
            "state": "ready",
            "authorized_records_sampled": len(records),
            "authorized_records_total": total,
            "status_counts": statuses,
            "synthetic_or_authorized_only": True,
            "model_training_performed": False,
            "memory_mutated": False,
            "hidden_reasoning_recorded": False,
        }

    def _project_recent(
        self, principal: MemoryPrincipal, project_id: str | None, cutoff: datetime
    ) -> bool:
        if not project_id:
            return False
        root = self.repository.paths.project_dir
        candidate = root / f"{project_id}.json"
        if candidate.parent != root or not candidate.is_file() or candidate.is_symlink():
            return False
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            metadata = dict(payload.get("metadata") or {})
            if str(metadata.get("owner_user_id") or "") != principal.user_id:
                return False
            if bool(metadata.get("archived")):
                return False
            return _parse_iso(str(metadata.get("updated_at_utc") or "")) >= cutoff
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    def _tier_maintenance(
        self, principal: MemoryPrincipal, *, job_id: str | None = None
    ) -> dict[str, Any]:
        settings = self.fabric.settings(principal)
        now = datetime.now(UTC)
        profile = settings.memory_storage_profile
        hot_days = (
            min(settings.hot_retention_days, 7)
            if profile == "efficient"
            else max(settings.hot_retention_days, 30)
            if profile == "deep_memory"
            else settings.hot_retention_days
        )
        cold_days = (
            min(settings.cold_after_days, 90)
            if profile == "efficient"
            else max(settings.cold_after_days, 365)
            if profile == "deep_memory"
            else settings.cold_after_days
        )
        if settings.retention_policy == "conservative":
            hot_days = max(hot_days, min(settings.hot_retention_days * 2, 3650))
            cold_days = max(cold_days, min(settings.cold_after_days * 2, 36500))
        elif settings.retention_policy == "compact":
            hot_days = max(1, min(hot_days, max(1, settings.hot_retention_days // 2)))
            cold_days = max(
                hot_days + 1,
                min(cold_days, max(7, settings.cold_after_days // 2)),
            )
        hot_cutoff = now - timedelta(days=hot_days)
        cold_cutoff = now - timedelta(days=cold_days)
        project_cutoff = now - timedelta(days=30)
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.*, v.revision_number, v.plaintext_hash,
                       COALESCE(a.retrieval_count,0) AS retrieval_count,
                       a.last_retrieved_at,
                       (SELECT rel.target_id FROM memory_relations rel
                        WHERE rel.source_memory_id=r.memory_id
                          AND rel.target_type='project' AND rel.status='active'
                        ORDER BY rel.relation_id LIMIT 1) AS linked_project_id
                FROM memory_records r JOIN memory_revisions v ON v.revision_id=r.current_revision_id
                LEFT JOIN memory_access_metrics a ON a.memory_id=r.memory_id
                WHERE r.owner_user_id=? AND r.status='active' AND r.pinned=0 AND r.retention_hold=0
                  AND (r.space_id IS NULL OR EXISTS (
                    SELECT 1 FROM shared_space_members sm
                    WHERE sm.space_id=r.space_id AND sm.user_id=?
                  ))
                ORDER BY r.updated_at
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
        moved = 0
        considered = 0
        decision_counts: dict[str, int] = {}
        for row in rows:
            if job_id and self._job_cancelled(principal, job_id):
                raise InterruptedError
            considered += 1
            current = ActivationTier(str(row["activation_tier"]))
            if current in {ActivationTier.WORKING, ActivationTier.ARCHIVED}:
                continue
            updated = _parse_iso(str(row["updated_at"]))
            retrieved = (
                _parse_iso(str(row["last_retrieved_at"]))
                if row["last_retrieved_at"]
                else updated
            )
            last_signal = max(updated, retrieved)
            retrieval_count = int(row["retrieval_count"])
            project_recent = self._project_recent(
                principal, row["linked_project_id"], project_cutoff
            )
            prospective_urgent = False
            if str(row["form"]) == "prospective":
                record = self.fabric.get(principal, str(row["memory_id"]))
                due_at = record.form_data.get("due_at") or record.valid_until
                state = str(record.form_data.get("state") or "pending")
                if due_at and state == "pending":
                    try:
                        prospective_urgent = _parse_iso(str(due_at)) <= now + timedelta(days=30)
                    except ValueError:
                        prospective_urgent = False
            target = None
            reason = "stable_warm_default"
            if (
                float(row["importance"]) >= 0.85
                or prospective_urgent
                or project_recent
                or (retrieval_count >= 5 and retrieved >= hot_cutoff)
                or (str(row["form"]) == "corrective" and updated >= hot_cutoff)
            ):
                target = ActivationTier.HOT
                reason = "active_importance_deadline_project_correction_or_frequency"
            elif last_signal < cold_cutoff and float(row["importance"]) < 0.75:
                target = ActivationTier.COLD
                reason = "aged_low_activity_policy"
            elif last_signal < hot_cutoff or current == ActivationTier.COLD:
                target = ActivationTier.WARM
                reason = "durable_ordinary_or_rehydrated_policy"
            decision_counts[reason] = decision_counts.get(reason, 0) + 1
            if target and target != current:
                self.move_tier(
                    principal,
                    str(row["memory_id"]),
                    MemoryTierRequest(
                        tier=target,
                        reason=f"Deterministic tier policy: {reason}.",
                        automatic=True,
                    ),
                )
                moved += 1
            if job_id:
                self._checkpoint_job(
                    principal, job_id,
                    {"phase": "tier_maintenance", "records_processed": considered},
                )
        return {
            "state": "ready",
            "records_considered": considered,
            "records_moved": moved,
            "effective_policy": {
                "profile": profile, "hot_retention_days": hot_days,
                "cold_after_days": cold_days,
                "retention_policy": settings.retention_policy,
                "byte_storage_profile": settings.storage_resource_profile,
            },
            "decision_counts": decision_counts,
            "silent_hard_delete_allowed": False,
        }

    def schedule_due_jobs(self, principal: MemoryPrincipal) -> dict[str, Any]:
        """Persist due maintenance through the governed Part 2D job ledger."""

        settings = self.fabric.settings(principal)
        if emergency_active(self.repository.paths):
            return {"state": "paused_emergency", "scheduled": []}
        managed, managed_policy = self._managed_governance()
        background_allowed = settings.background_cognition_enabled and (
            not managed
            or bool(managed_policy.get("background_cognition_allowed", False))
        )
        if not background_allowed:
            return {
                "state": "disabled_by_user_or_managed_control",
                "scheduled": [],
                "background_cognition_enabled": settings.background_cognition_enabled,
                "managed_profile_ceiling_applied": managed,
            }
        effective_level = min(
            settings.autonomy_level,
            int(managed_policy.get("autonomy_maximum", 5))
            if managed
            else 5,
        )
        effective_overrides = {
            key: min(int(value), effective_level)
            for key, value in settings.autonomy_domain_overrides.items()
        }
        resolved_domains, capability_policy = resolve_autonomy_policy(
            effective_level, effective_overrides
        )
        if not capability_policy["schedule_visible_background_jobs"]:
            return {
                "state": "blocked_by_autonomy_ceiling",
                "scheduled": [],
                "effective_background_cognition_level": resolved_domains[
                    "background_cognition"
                ],
            }
        if active_request_count() > 0:
            return {
                "state": "preempted_by_foreground",
                "scheduled": [],
                "foreground_request_count": active_request_count(),
            }
        if not self._device_power_allows_background():
            return {
                "state": "paused_on_battery",
                "scheduled": [],
                "power_policy": "automatic_memory_maintenance_requires_external_power",
            }
        try:
            self.fabric.encryption.account_key(principal)
        except Exception:
            return {
                "state": "paused_account_key_unavailable",
                "scheduled": [],
                "protected_content_returned": False,
            }
        schedule: list[tuple[str, str]] = [
            ("homeostasis", "daily"),
            ("tier_maintenance", "daily"),
            ("fts_rebuild", "weekly"),
            ("embedding_rebuild", "weekly"),
            ("graph_rebuild", "weekly"),
            ("object_integrity", "weekly"),
            ("archive_compression", "weekly"),
            ("integrity_check", "weekly"),
        ]
        if settings.consolidation_enabled and settings.consolidation_schedule != "manual":
            cadence = settings.consolidation_schedule
            schedule.extend(
                (kind, cadence)
                for kind in (
                    "conversation_compaction",
                    "semantic_candidates",
                    "duplicate_detection",
                    "relation_candidates",
                    "contradiction_scan",
                    "project_summary_refresh",
                    "metacognitive_statistics",
                    "consolidation",
                )
            )
        if settings.backup_enabled and settings.backup_schedule != "manual":
            schedule.append(("managed_backup", settings.backup_schedule))
        now = datetime.now(UTC)
        scheduled: list[dict[str, Any]] = []
        for kind, cadence in schedule:
            interval = timedelta(days=1 if cadence == "daily" else 7)
            with self.repository.connect() as conn:
                existing = conn.execute(
                    """
                    SELECT state,COALESCE(completed_at,created_at) AS last_time
                    FROM memory_jobs WHERE owner_user_id=? AND job_kind=?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (principal.user_id, f"part2e:{kind}"),
                ).fetchone()
            if existing is not None and str(existing["state"]) in {"pending", "running"}:
                continue
            if existing is not None and now - _parse_iso(str(existing["last_time"])) < interval:
                continue
            try:
                item = self.submit_job(principal, kind)
            except MemoryReleaseError as exc:
                if "ceiling" in str(exc).casefold():
                    break
                raise
            with self.repository.transaction() as conn:
                conn.execute(
                    "UPDATE memory_jobs SET checkpoint_json=? WHERE job_id=?",
                    (
                        json.dumps(
                            {"scheduled": True, "cadence": cadence}, sort_keys=True
                        ),
                        item["job_id"],
                    ),
                )
            scheduled.append(item)
        return {
            "state": "ready",
            "scheduled": scheduled,
            "hidden_scheduler_created": False,
            "governed_compute_ledger_used": True,
            "effective_background_cognition_level": resolved_domains[
                "background_cognition"
            ],
            "foreground_preemption_enforced": True,
            "power_policy_enforced": True,
            "account_key_available": True,
        }

    def run_scheduled_tick(self, principal: MemoryPrincipal) -> dict[str, Any]:
        deletion_recovery = self.recover_pending_deletions(principal)
        scheduled = self.schedule_due_jobs(principal)
        completed: list[dict[str, Any]] = []
        for job in scheduled.get("scheduled", []):
            if emergency_active(self.repository.paths):
                break
            completed.append(self.run_job(principal, str(job["job_id"])))
        return {
            **scheduled,
            "executed": completed,
            "hard_delete_recovery": deletion_recovery,
        }

    def jobs(self, principal: MemoryPrincipal, *, limit: int = 100) -> dict[str, Any]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id, job_kind, state, progress_current, progress_total,
                       priority, cancel_requested, attempt_count, error_code,
                       created_at, updated_at, started_at, completed_at, result_code
                FROM memory_jobs WHERE owner_user_id = ? AND job_kind LIKE 'part2e:%'
                ORDER BY created_at DESC LIMIT ?
                """,
                (principal.user_id, max(1, min(limit, 500))),
            ).fetchall()
        return {"jobs": [dict(row) for row in rows], "content_included": False}

    def cancel_job(self, principal: MemoryPrincipal, job_id: str) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            result = conn.execute(
                """
                UPDATE memory_jobs SET cancel_requested=1, state='cancelled',
                    updated_at=?, result_code='user_cancelled'
                WHERE job_id=? AND owner_user_id=? AND job_kind LIKE 'part2e:%'
                  AND state IN ('pending','running','interrupted')
                """,
                (utc_now(), job_id, principal.user_id),
            )
        return {"job_id": job_id, "cancelled": result.rowcount == 1}

    def delete_plan(self, principal: MemoryPrincipal, memory_id: str) -> dict[str, Any]:
        row = self._owned_row(principal, memory_id, action="delete")
        with self.repository.connect() as conn:
            revision_ids = sorted(
                str(item[0])
                for item in conn.execute(
                    "SELECT revision_id FROM memory_revisions WHERE memory_id=?",
                    (memory_id,),
                ).fetchall()
            )
            source_ids = sorted(
                str(item[0])
                for item in conn.execute(
                    "SELECT source_row_id FROM memory_sources WHERE memory_id=?",
                    (memory_id,),
                ).fetchall()
            )
            relation_ids = sorted(
                str(item[0])
                for item in conn.execute(
                    """
                    SELECT relation_id FROM memory_relations
                    WHERE source_memory_id=? OR (target_type='memory' AND target_id=?)
                    """,
                    (memory_id, memory_id),
                ).fetchall()
            )
            object_reference_ids = sorted(
                str(item[0])
                for item in conn.execute(
                    """
                    SELECT object_ref_id FROM memory_object_refs
                    WHERE ref_id=? OR ref_id IN (
                        SELECT revision_id FROM memory_revisions WHERE memory_id=?
                    )
                    """,
                    (memory_id, memory_id),
                ).fetchall()
            )
            archive_state = [
                {
                    "archive_id": str(item[0]),
                    "checksum": str(item[1]),
                    "size_bytes": int(item[2]),
                    "state": str(item[3]),
                }
                for item in conn.execute(
                    """
                    SELECT archive_id,checksum,size_bytes,state
                    FROM memory_archive_registry WHERE owner_user_id=?
                    ORDER BY archive_id
                    """,
                    (principal.user_id,),
                ).fetchall()
            ]
            counts = {
                "canonical_revisions": len(revision_ids),
                "canonical_sources": len(source_ids),
                "candidate_rows": int(conn.execute("SELECT COUNT(*) FROM memory_candidates WHERE memory_id=?", (memory_id,)).fetchone()[0]),
                "truth_events": int(conn.execute("SELECT COUNT(*) FROM memory_truth_events WHERE memory_id=? OR related_memory_id=?", (memory_id, memory_id)).fetchone()[0]),
                "relations": len(relation_ids),
                "contradictions": int(conn.execute("SELECT COUNT(*) FROM memory_contradictions WHERE left_memory_id=? OR right_memory_id=?", (memory_id, memory_id)).fetchone()[0]),
                "object_references": len(object_reference_ids),
                "cold_revisions": int(conn.execute("SELECT COUNT(*) FROM memory_cold_revisions WHERE memory_id=?", (memory_id,)).fetchone()[0]),
                "graph_nodes": int(conn.execute("SELECT COUNT(*) FROM memory_graph_nodes WHERE owner_user_id=? AND node_type='memory' AND authority_id=?", (principal.user_id, memory_id)).fetchone()[0]),
                "managed_backups": int(conn.execute("SELECT COUNT(*) FROM memory_archive_registry WHERE owner_user_id=? AND archive_kind='managed_backup'", (principal.user_id,)).fetchone()[0]),
                "elysia_held_portable_exports": int(conn.execute("SELECT COUNT(*) FROM memory_archive_registry WHERE owner_user_id=? AND archive_kind='portable_export'", (principal.user_id,)).fetchone()[0]),
            }
        # The approval never exposes record text, source labels, ciphertext
        # digests, or keys. It is nevertheless bound to every exact managed
        # identifier and archive checksum, so same-count state changes revoke
        # the preview instead of silently widening/narrowing its scope.
        state_fingerprint = _digest(
            {
                "memory_id": memory_id,
                "current_revision_id": str(row["current_revision_id"]),
                "status": str(row["status"]),
                "privacy": str(row["privacy"]),
                "activation_tier": str(row["activation_tier"]),
                "revision_ids": revision_ids,
                "source_ids": source_ids,
                "relation_ids": relation_ids,
                "object_reference_ids": object_reference_ids,
                "archives": archive_state,
            }
        )
        return {
            **counts,
            "managed_state_fingerprint": state_fingerprint,
            "fts_entries": "purge_and_verify",
            "qdrant_vectors": "purge_and_verify_if_configured",
            "summaries_and_caches": "invalidate_and_verify",
            "sealed_record_key": "destroyed_with_revision_envelope" if str(row["privacy"]) == "sealed" else "not_applicable",
            "managed_backups": counts["managed_backups"],
            "portable_or_offline_user_exports": "cannot_be_erased_by_elysia",
            "content_free_receipt_only": True,
            "crash_recovery": "content_free_durable_saga",
        }

    def rewrite_archives_for_delete(
        self, principal: MemoryPrincipal, memory_id: str
    ) -> dict[str, Any]:
        recovery_material = sha256(
            self.fabric.encryption.account_key(principal)
        ).hexdigest()
        with self.repository.connect() as conn:
            archives = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT archive_id,archive_kind,path_token,checksum
                    FROM memory_archive_registry WHERE owner_user_id=?
                    ORDER BY archive_id
                    """,
                    (principal.user_id,),
                ).fetchall()
            ]
        rewritten = 0
        removed_occurrences = 0
        for archive in archives:
            path = self.repository.paths.memory_backup_dir / str(archive["path_token"])
            if not path.is_file() or path.is_symlink():
                raise MemoryReleaseError("A managed archive required by the delete plan is unavailable.")
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != str(archive["checksum"]):
                raise MemoryReleaseError("A managed archive required by the delete plan failed integrity.")
            # Managed backups use the local-account recovery material. Portable
            # exports use user-held recovery material that Elysia deliberately
            # does not retain; purge Elysia's writable cache copy instead and
            # state that downloaded/offline copies remain outside our reach.
            if archive["archive_kind"] == "portable_export":
                path.unlink()
                with self.repository.transaction() as conn:
                    conn.execute(
                        "DELETE FROM memory_archive_registry WHERE archive_id=?",
                        (archive["archive_id"],),
                    )
                rewritten += 1
                continue
            payload = self._decrypt_archive(raw, recovery_material)
            before = len(payload.get("records", []))
            payload["records"] = [
                item
                for item in payload.get("records", [])
                if str(item.get("record", {}).get("memory_id")) != memory_id
            ]
            rewritten_objects: list[dict[str, Any]] = []
            for item in payload.get("objects", []):
                retained_references = [
                    reference
                    for reference in item.get("references", [])
                    if not (
                        str(reference.get("ref_type")) == "memory"
                        and str(reference.get("ref_id")) == memory_id
                    )
                ]
                removed_occurrences += len(item.get("references", [])) - len(
                    retained_references
                )
                if retained_references:
                    rewritten_objects.append(
                        {**item, "references": retained_references}
                    )
            payload["objects"] = rewritten_objects
            if isinstance(payload.get("metadata_counts"), dict):
                payload["metadata_counts"]["records"] = len(payload["records"])
                payload["metadata_counts"]["objects"] = len(rewritten_objects)
            removed_occurrences += before - len(payload["records"])
            payload["contradictions"] = [
                item
                for item in payload.get("contradictions", [])
                if memory_id not in {
                    str(item.get("left_memory_id")), str(item.get("right_memory_id"))
                }
            ]
            payload["audit_receipts"] = [
                {**item, "memory_id": None}
                if str(item.get("memory_id")) == memory_id
                else item
                for item in payload.get("audit_receipts", [])
            ]
            payload.setdefault("deletion_manifest", []).append(
                {
                    "content_removed": True,
                    "content_identifier_retained": False,
                    "deleted_at": utc_now(),
                }
            )
            rewritten_raw = self._encrypt_archive(payload, recovery_material)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".archive-rewrite-", dir=path.parent
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(rewritten_raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary.chmod(0o600)
                os.replace(temporary, path)
                path.chmod(0o600)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            with self.repository.transaction() as conn:
                conn.execute(
                    """
                    UPDATE memory_archive_registry
                    SET size_bytes=?,checksum=?,record_count=?,verified_at=?,state='verified'
                    WHERE archive_id=? AND owner_user_id=?
                    """,
                    (
                        len(rewritten_raw), sha256(rewritten_raw).hexdigest(),
                        len(payload["records"]), utc_now(), archive["archive_id"],
                        principal.user_id,
                    ),
                )
            rewritten += 1
        return {
            "elysia_held_archives_rewritten_or_purged": rewritten,
            "record_occurrences_removed": removed_occurrences,
            "offline_user_exports_erased": False,
        }

    def purge_part2e_derivatives(self, principal: MemoryPrincipal, memory_id: str) -> dict[str, Any]:
        with self.repository.connect() as conn:
            revisions = [str(row[0]) for row in conn.execute("SELECT revision_id FROM memory_revisions WHERE memory_id=?", (memory_id,)).fetchall()]
        with self.repository.transaction() as conn:
            conn.execute("DELETE FROM memory_cold_revisions WHERE memory_id = ?", (memory_id,))
        object_results = [self.objects.purge_references(ref_type="memory", ref_id=memory_id)]
        object_results.extend(self.objects.purge_references(ref_type="cold_revision", ref_id=revision) for revision in revisions)
        with self.repository.transaction() as conn:
            conn.execute("DELETE FROM memory_graph_edges WHERE source_node_id IN (SELECT node_id FROM memory_graph_nodes WHERE owner_user_id=? AND node_type='memory' AND authority_id=?) OR target_node_id IN (SELECT node_id FROM memory_graph_nodes WHERE owner_user_id=? AND node_type='memory' AND authority_id=?)", (principal.user_id, memory_id, principal.user_id, memory_id))
            conn.execute("DELETE FROM memory_graph_nodes WHERE owner_user_id=? AND node_type='memory' AND authority_id=?", (principal.user_id, memory_id))
        return {"objects": object_results, "offline_exports_erased": False}

    def verify_absence(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        *,
        revision_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        revision_ids = revision_ids or []
        with self.repository.connect() as conn:
            canonical = int(conn.execute("SELECT COUNT(*) FROM memory_records WHERE memory_id=?", (memory_id,)).fetchone()[0])
            revisions = int(conn.execute("SELECT COUNT(*) FROM memory_revisions WHERE memory_id=?", (memory_id,)).fetchone()[0])
            sources = int(conn.execute("SELECT COUNT(*) FROM memory_sources WHERE memory_id=?", (memory_id,)).fetchone()[0])
            candidates = int(conn.execute("SELECT COUNT(*) FROM memory_candidates WHERE memory_id=?", (memory_id,)).fetchone()[0])
            relations = int(conn.execute("SELECT COUNT(*) FROM memory_relations WHERE source_memory_id=? OR (target_type='memory' AND target_id=?)", (memory_id, memory_id)).fetchone()[0])
            contradictions = int(conn.execute("SELECT COUNT(*) FROM memory_contradictions WHERE left_memory_id=? OR right_memory_id=?", (memory_id, memory_id)).fetchone()[0])
            truth_events = int(conn.execute("SELECT COUNT(*) FROM memory_truth_events WHERE memory_id=? OR related_memory_id=?", (memory_id, memory_id)).fetchone()[0])
            cold = int(conn.execute("SELECT COUNT(*) FROM memory_cold_revisions WHERE memory_id=?", (memory_id,)).fetchone()[0])
            objects = int(conn.execute(
                f"SELECT COUNT(*) FROM memory_object_refs WHERE ref_id=?{(' OR ref_id IN (' + ','.join('?' for _ in revision_ids) + ')') if revision_ids else ''}",
                [memory_id, *revision_ids],
            ).fetchone()[0])
            graph = int(conn.execute("SELECT COUNT(*) FROM memory_graph_nodes WHERE authority_id=?", (memory_id,)).fetchone()[0])
            managed_occurrences = 0
            managed_archives = [dict(row) for row in conn.execute(
                "SELECT path_token,checksum FROM memory_archive_registry WHERE owner_user_id=? AND archive_kind='managed_backup'",
                (principal.user_id,),
            ).fetchall()]
        recovery_material = sha256(self.fabric.encryption.account_key(principal)).hexdigest()
        for archive in managed_archives:
            path = self.repository.paths.memory_backup_dir / str(archive["path_token"])
            if not path.is_file() or path.is_symlink():
                managed_occurrences += 1
                continue
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != str(archive["checksum"]):
                managed_occurrences += 1
                continue
            payload = self._decrypt_archive(raw, recovery_material)
            managed_occurrences += sum(
                str(item.get("record", {}).get("memory_id")) == memory_id
                for item in payload.get("records", [])
            )
            managed_occurrences += sum(
                str(reference.get("ref_type")) == "memory"
                and str(reference.get("ref_id")) == memory_id
                for item in payload.get("objects", [])
                for reference in item.get("references", [])
            )
        fts_occurrences = 0
        fts_path = self.repository.paths.memory_fts_database_path
        if fts_path.is_file() and not fts_path.is_symlink():
            try:
                with sqlite3.connect(
                    f"file:{fts_path.as_posix()}?mode=ro", uri=True, timeout=1.0
                ) as conn:
                    fts_occurrences = int(conn.execute(
                        "SELECT COUNT(*) FROM memory_fts_meta WHERE candidate_id=?",
                        (memory_id,),
                    ).fetchone()[0])
            except sqlite3.Error:
                fts_occurrences = 1
        from app.cognition.semantic_projection import SemanticMemoryProjection

        semantic = SemanticMemoryProjection(
            paths=self.repository.paths,
            repository=self.repository,
            fabric=self.fabric,
        ).verify_record_absent(memory_id)
        values = (
            canonical, revisions, sources, candidates, relations,
            contradictions, truth_events, cold, objects, graph,
            managed_occurrences, fts_occurrences, int(not semantic["absent"]),
        )
        return {
            "absent": all(value == 0 for value in values),
            "canonical_records": canonical,
            "revisions": revisions,
            "sources": sources,
            "candidate_rows": candidates,
            "relations": relations,
            "contradictions": contradictions,
            "truth_events": truth_events,
            "cold_entries": cold,
            "object_references": objects,
            "graph_nodes": graph,
            "managed_archive_occurrences": managed_occurrences,
            "fts_occurrences": fts_occurrences,
            "semantic_projection": semantic,
            "offline_user_exports_checked": False,
        }

    def health(self, principal: MemoryPrincipal) -> dict[str, Any]:
        return {
            "object_store": self.objects.verify(principal=principal),
            "graph": self.graph_health(principal),
            "archives": self.archive_status(principal),
            "homeostasis": self.homeostasis(principal),
            "scheduler": self.jobs(principal, limit=20),
            "canonical_writer_count": 1,
            "hard_delete_recovery": self.pending_deletion_status(principal),
        }

    def graph_health(self, principal: MemoryPrincipal) -> dict[str, Any]:
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), (SELECT COUNT(*) FROM memory_graph_edges WHERE owner_user_id=?) FROM memory_graph_nodes WHERE owner_user_id=?",
                (principal.user_id, principal.user_id),
            ).fetchone()
        return {
            "state": "ready",
            "node_count": int(row[0]),
            "edge_count": int(row[1]),
            "private_or_sealed_persistent_nodes": 0,
            "canonical": False,
        }


def cancel_all_memory_maintenance() -> int:
    repository = MemoryRepository()
    repository.initialize()
    with repository.transaction() as conn:
        result = conn.execute(
            """
            UPDATE memory_jobs SET cancel_requested=1, state='cancelled',
                updated_at=?, result_code='emergency_stop'
            WHERE job_kind LIKE 'part2e:%' AND state IN ('pending','running','interrupted')
            """,
            (utc_now(),),
        )
    return int(result.rowcount)


register_canceller("memory_maintenance_jobs_cancelled", cancel_all_memory_maintenance)


__all__ = (
    "ARCHIVE_VERSION",
    "MemoryReleaseError",
    "MemoryReleaseService",
    "cancel_all_memory_maintenance",
)
