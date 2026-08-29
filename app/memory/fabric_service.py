"""Transactional policy/service layer for Elysia's canonical Memory Fabric."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
import json
from pathlib import Path
import secrets
import shutil
from time import perf_counter
from typing import Any, Iterable

import yaml

from app.ids import new_id
from app.memory.canonical_models import (
    ActivationTier,
    CandidateDecision,
    CandidateDecisionRequest,
    ConsequenceApplyRequest,
    ConsequencePreviewRequest,
    MemoryCandidateCreateRequest,
    MemoryContent,
    MemoryCorrectionRequest,
    MemoryCreateRequest,
    MemoryLifecycle,
    MemoryPinRequest,
    MemoryPrincipal,
    MemoryPrivacy,
    MemoryQuery,
    MemoryRelationCreateRequest,
    MemoryReasonRequest,
    MemoryRecordView,
    MemoryScope,
    MemorySettings,
    MemorySourceInput,
    MemoryTruthChange,
    SharedSpaceCreateRequest,
    SharedSpaceInvitationResponseRequest,
    SharedSpaceRole,
)
from app.memory.canonical_repository import (
    MUTATION_RECEIPT_INSERT,
    MemoryRepository,
    mutation_receipt_row,
    utc_now,
)
from app.memory.encryption_service import (
    MemoryEncryptionError,
    MemoryEncryptionService,
    SealedMemoryLockedError,
)


POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "memory" / "canonical_memory_policy.yaml"
APPROVAL_TTL_SECONDS = 300


class MemoryFabricError(RuntimeError):
    """Base error with a safe user-facing message."""


class MemoryAuthorizationError(MemoryFabricError):
    """The authenticated principal cannot perform the requested operation."""


class MemoryNotFoundError(MemoryFabricError):
    """The requested memory is unavailable to the current principal."""


class MemoryApprovalError(MemoryFabricError):
    """An exact consequence approval was missing, stale, or invalid."""


def _iso_after(seconds: int) -> str:
    return (
        datetime.now(UTC) + timedelta(seconds=seconds)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _digest(payload: Any) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _content_bytes(content: MemoryContent) -> bytes:
    return json.dumps(
        content.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class MemoryPolicyService:
    def __init__(self, path: Path = POLICY_PATH) -> None:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("authority") != "canonical_memory_fabric":
            raise MemoryFabricError("The canonical memory policy is unavailable.")
        self.data = data

    def legacy_mapping(self, legacy_class: str) -> dict[str, str]:
        mapping = self.data.get("legacy_class_mapping", {}).get(legacy_class)
        if not isinstance(mapping, dict):
            raise MemoryFabricError(f"Legacy memory class is unsupported: {legacy_class}.")
        return {str(key): str(value) for key, value in mapping.items()}

    def role_allows(self, role: str, action: str) -> bool:
        actions = self.data.get("authorization", {}).get("shared_roles", {}).get(role, [])
        return action in actions

    def requires_approval(self, action: str) -> bool:
        return action in set(self.data.get("approval_required", []))


class MemoryOwnershipService:
    def __init__(self, repository: MemoryRepository, policy: MemoryPolicyService) -> None:
        self.repository = repository
        self.policy = policy

    def assert_space_access(
        self,
        *,
        principal: MemoryPrincipal,
        space_id: str,
        action: str,
        conn=None,
    ) -> str:
        owned = conn is None
        connection = conn or self.repository.connect()
        try:
            row = connection.execute(
                """
                SELECT role FROM shared_space_members
                WHERE space_id = ? AND user_id = ?
                """,
                (space_id, principal.user_id),
            ).fetchone()
        finally:
            if owned:
                connection.close()
        if row is None or not self.policy.role_allows(str(row["role"]), action):
            raise MemoryAuthorizationError("The shared-space role does not allow this operation.")
        return str(row["role"])

    def accessible_record(self, principal: MemoryPrincipal, memory_id: str, *, action: str = "read"):
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT r.*, v.revision_number, v.plaintext_hash
                FROM memory_records r
                JOIN memory_revisions v ON v.revision_id = r.current_revision_id
                WHERE r.memory_id = ?
                  AND r.status != 'deleted'
                  AND (
                    (r.owner_user_id = ? AND r.space_id IS NULL)
                    OR EXISTS (
                        SELECT 1 FROM shared_space_members m
                        WHERE m.space_id = r.space_id AND m.user_id = ?
                    )
                  )
                """,
                (memory_id, principal.user_id, principal.user_id),
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError("The memory record is unavailable.")
            if row["space_id"]:
                # Once a record enters a Shared Space, the current space role
                # governs every participant, including the member who created
                # that record.  Ownership remains provenance, not a stale ACL
                # bypass after downgrade or revocation.
                self.assert_space_access(
                    principal=principal,
                    space_id=str(row["space_id"]),
                    action=action,
                    conn=conn,
                )
            elif str(row["owner_user_id"]) != principal.user_id:
                raise MemoryAuthorizationError("The memory record belongs to another account.")
            return row


class MemoryFabricService:
    def __init__(
        self,
        repository: MemoryRepository | None = None,
        encryption: MemoryEncryptionService | None = None,
        policy: MemoryPolicyService | None = None,
    ) -> None:
        self.repository = repository or MemoryRepository()
        self.repository.initialize()
        self.encryption = encryption or MemoryEncryptionService(self.repository)
        self.policy = policy or MemoryPolicyService()
        self.ownership = MemoryOwnershipService(self.repository, self.policy)

    @staticmethod
    def current_principal() -> MemoryPrincipal:
        from app.api.account_service import get_authenticated_principal

        try:
            return MemoryPrincipal(**get_authenticated_principal())
        except Exception as exc:
            raise MemoryAuthorizationError(
                "A valid authenticated local account is required for memory access."
            ) from exc

    def _validate_authority_links(
        self, principal: MemoryPrincipal, request: MemoryCreateRequest
    ) -> None:
        from app.memory.source_adapters import (
            MemorySourceReferenceError,
            validate_source_reference,
        )

        try:
            for target_type, target_id, context_id in (
                ("conversation", request.conversation_id, None),
                ("message", request.message_id, request.conversation_id),
                ("project", request.project_id, None),
                ("request", request.request_id, None),
                ("evidence", request.evidence_id, None),
                ("artifact", request.artifact_id, None),
            ):
                if target_id:
                    validate_source_reference(
                        target_type, target_id, context_id=context_id
                    )
        except MemorySourceReferenceError as exc:
            raise MemoryFabricError(str(exc)) from exc
        if request.space_id:
            self.ownership.assert_space_access(
                principal=principal,
                space_id=request.space_id,
                action="create",
            )

    def _insert_revision(
        self,
        conn,
        *,
        principal: MemoryPrincipal,
        memory_id: str,
        privacy: MemoryPrivacy,
        content: MemoryContent,
        revision_number: int,
        actor: str,
        reason: str,
        supersedes_revision_id: str | None,
        revision_id: str | None = None,
    ) -> tuple[str, str]:
        resolved_revision_id = revision_id or new_id("memrev")
        encrypted = self.encryption.encrypt_content(
            principal=principal,
            privacy=privacy,
            memory_id=memory_id,
            revision_id=resolved_revision_id,
            plaintext=_content_bytes(content),
        )
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
                resolved_revision_id,
                memory_id,
                revision_number,
                encrypted.ciphertext,
                encrypted.nonce,
                encrypted.wrapped_data_key,
                encrypted.key_nonce,
                encrypted.key_id,
                encrypted.content_format,
                encrypted.plaintext_hash,
                self.encryption.digest_format(privacy),
                actor,
                utc_now(),
                reason,
                supersedes_revision_id,
            ),
        )
        return resolved_revision_id, encrypted.plaintext_hash

    def create(
        self,
        principal: MemoryPrincipal,
        request: MemoryCreateRequest,
        *,
        actor: str = "user",
        legacy_memory_id: str | None = None,
        legacy_class: str | None = None,
    ) -> MemoryRecordView:
        self.repository.assert_content_writes_ready()
        self.repository.assert_nonessential_writes_ready()
        settings = self.settings(principal)
        if not settings.memory_recording_enabled and actor != "migration_service":
            raise MemoryAuthorizationError(
                "Memory recording is disabled in Settings. Existing memory remains available."
            )
        if "privacy" not in request.model_fields_set:
            request = request.model_copy(update={"privacy": settings.default_privacy})
        self._validate_authority_links(principal, request)
        memory_id = legacy_memory_id or new_id("memory")
        revision_id = new_id("memrev")
        now = utc_now()
        display_title = request.title if request.privacy == MemoryPrivacy.NORMAL else None
        # Egress is a separate governed decision. Creation never grants it
        # implicitly from scope or privacy alone.
        egress_allowed = False
        content = MemoryContent(
            title=request.title,
            body=request.body,
            why_stored=request.why_stored,
            form_data=request.form_data,
        )
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_records (
                    memory_id, owner_user_id, space_id, scope, form, subtype,
                    privacy, status, title, current_revision_id, importance,
                    confidence, user_confirmed, inference_kind, created_at,
                    updated_at, observed_at, valid_from, valid_until,
                    activation_tier, pinned, egress_allowed, legacy_class,
                    schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 3)
                """,
                (
                    memory_id,
                    principal.user_id,
                    request.space_id,
                    request.scope.value,
                    request.form.value,
                    request.subtype,
                    request.privacy.value,
                    request.status.value,
                    display_title,
                    revision_id,
                    request.importance,
                    request.confidence,
                    int(request.user_confirmed),
                    request.inference_kind,
                    now,
                    now,
                    request.observed_at,
                    request.valid_from,
                    request.valid_until,
                    request.activation_tier.value,
                    int(egress_allowed),
                    legacy_class,
                ),
            )
            _, plaintext_hash = self._insert_revision(
                conn,
                principal=principal,
                memory_id=memory_id,
                privacy=request.privacy,
                content=content,
                revision_number=1,
                actor=actor,
                reason=request.why_stored,
                supersedes_revision_id=None,
                revision_id=revision_id,
            )
            source_id = request.source.source_id or new_id("source")
            source_label = (
                request.source.source_label if request.privacy == MemoryPrivacy.NORMAL else None
            )
            conn.execute(
                """
                INSERT INTO memory_sources (
                    source_row_id, memory_id, source_type, source_id, source_label,
                    source_time, source_authority, retrieval_method, provenance_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("memsource"),
                    memory_id,
                    request.source.source_type,
                    source_id,
                    source_label,
                    request.source.source_time,
                    request.source.source_authority,
                    request.source.retrieval_method,
                    request.source.provenance_status,
                ),
            )
            for target_type, target_id in (
                ("conversation", request.conversation_id),
                ("message", request.message_id),
                ("project", request.project_id),
                ("request", request.request_id),
                ("evidence", request.evidence_id),
                ("artifact", request.artifact_id),
            ):
                if target_id:
                    conn.execute(
                        """
                        INSERT INTO memory_relations (
                            relation_id, source_memory_id, target_type, target_id,
                            relation_type, confidence, is_inferred,
                            provenance_source_id, valid_from, valid_until, status
                        ) VALUES (?, ?, ?, ?, 'derived_from', ?, 0, NULL, ?, ?, 'active')
                        """,
                        (
                            new_id("memrel"),
                            memory_id,
                            target_type,
                            target_id,
                            request.confidence,
                            request.valid_from,
                            request.valid_until,
                        ),
                    )
            if request.status == MemoryLifecycle.CANDIDATE:
                candidate_kind = getattr(request, "candidate_kind", None) or "review_required"
                conn.execute(
                    """
                    INSERT INTO memory_candidates (
                        candidate_id, memory_id, candidate_kind, review_state,
                        proposed_wording, evidence_summary, created_at
                    ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
                    """,
                    (
                        new_id("memcandidate"), memory_id, candidate_kind,
                        getattr(request, "proposed_wording", None),
                        getattr(request, "evidence_summary", None), now,
                    ),
                )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="candidate_created" if request.status == MemoryLifecycle.CANDIDATE else "created",
                    memory_id=memory_id,
                    request_id=request.request_id,
                    old_state_digest=None,
                    new_state_digest=plaintext_hash,
                    scope=request.scope.value,
                    form=request.form.value,
                    privacy=request.privacy.value,
                ),
            )
        self._trace_mutation(request.request_id, memory_id, "created")
        return self.get(principal, memory_id)

    def create_candidate(
        self, principal: MemoryPrincipal, request: MemoryCandidateCreateRequest
    ) -> MemoryRecordView:
        settings = self.settings(principal)
        if (
            settings.candidate_behavior == "direct_explicit_only"
            and (
                request.candidate_kind != "user_submitted_candidate"
                or request.source.source_authority != "user"
            )
        ):
            raise MemoryAuthorizationError(
                "Settings allow only direct, explicit memory teaching; inferred candidate capture is disabled."
            )
        return self.create(principal, request, actor="assistant_candidate")

    def _revision_row(self, conn, record_row):
        return conn.execute(
            "SELECT * FROM memory_revisions WHERE revision_id = ?",
            (record_row["current_revision_id"],),
        ).fetchone()

    def _read_content(self, principal: MemoryPrincipal, record_row, revision_row) -> MemoryContent:
        if not bytes(revision_row["content_ciphertext"]):
            from app.memory.object_store import MemoryObjectStore

            revision_row = dict(revision_row)
            revision_row["content_ciphertext"] = MemoryObjectStore(
                repository=self.repository
            ).read_cold_revision(
                principal=principal,
                memory_id=str(record_row["memory_id"]),
                revision_id=str(revision_row["revision_id"]),
            )
        plaintext = self.encryption.decrypt_content(
            principal=principal,
            privacy=MemoryPrivacy(str(record_row["privacy"])),
            memory_id=str(record_row["memory_id"]),
            revision_id=str(revision_row["revision_id"]),
            row=revision_row,
        )
        try:
            return MemoryContent.model_validate_json(plaintext)
        except Exception as exc:
            raise MemoryFabricError("The canonical memory content is invalid.") from exc

    def _view(self, principal: MemoryPrincipal, record_row, *, include_body: bool) -> MemoryRecordView:
        with self.repository.connect() as conn:
            revision = self._revision_row(conn, record_row)
            sources = conn.execute(
                """
                SELECT source_type, source_id, source_label, source_time,
                       source_authority, retrieval_method, provenance_status
                FROM memory_sources WHERE memory_id = ? ORDER BY source_row_id
                """,
                (record_row["memory_id"],),
            ).fetchall()
            relations = conn.execute(
                """
                SELECT relation_id, target_type, target_id, relation_type,
                       confidence, is_inferred, provenance_source_id,
                       valid_from, valid_until, status
                FROM memory_relations WHERE source_memory_id = ?
                ORDER BY relation_id
                """,
                (record_row["memory_id"],),
            ).fetchall()
            candidate = conn.execute(
                """
                SELECT candidate_kind, proposed_wording, evidence_summary, deferred_until
                FROM memory_candidates WHERE memory_id = ?
                """,
                (record_row["memory_id"],),
            ).fetchone()
        privacy = MemoryPrivacy(str(record_row["privacy"]))
        content_state = "available"
        content: MemoryContent | None = None
        if privacy == MemoryPrivacy.SEALED:
            try:
                content = self._read_content(principal, record_row, revision)
            except SealedMemoryLockedError:
                content_state = "sealed_locked"
        else:
            content = self._read_content(principal, record_row, revision)
        if content is None:
            title = "Sealed memory"
            body = None
            why_stored = None
        else:
            title = content.title
            body = content.body if include_body else None
            why_stored = content.why_stored if include_body else None
        return MemoryRecordView(
            memory_id=str(record_row["memory_id"]),
            owner_user_id=str(record_row["owner_user_id"]),
            space_id=record_row["space_id"],
            scope=str(record_row["scope"]),
            form=str(record_row["form"]),
            subtype=record_row["subtype"],
            privacy=privacy,
            status=str(record_row["status"]),
            title=title,
            body=body,
            why_stored=why_stored,
            content_state=content_state,
            current_revision_id=str(record_row["current_revision_id"]),
            revision_number=int(record_row["revision_number"]),
            importance=float(record_row["importance"]),
            confidence=(float(record_row["confidence"]) if record_row["confidence"] is not None else None),
            user_confirmed=bool(record_row["user_confirmed"]),
            inference_kind=record_row["inference_kind"],
            created_at=str(record_row["created_at"]),
            updated_at=str(record_row["updated_at"]),
            observed_at=record_row["observed_at"],
            valid_from=record_row["valid_from"],
            valid_until=record_row["valid_until"],
            activation_tier=str(record_row["activation_tier"]),
            pinned=bool(record_row["pinned"]),
            egress_allowed=bool(record_row["egress_allowed"]),
            legacy_class=record_row["legacy_class"],
            form_data=(content.form_data if content is not None else {}),
            automatic_recall_suppressed=bool(record_row["automatic_recall_suppressed"]),
            expires_at=record_row["expires_at"],
            retention_hold=bool(record_row["retention_hold"]),
            sources=[dict(row) for row in sources],
            relations=[dict(row) for row in relations],
            candidate_kind=(str(candidate["candidate_kind"]) if candidate else None),
            candidate_proposed_wording=(candidate["proposed_wording"] if candidate else None),
            candidate_evidence_summary=(candidate["evidence_summary"] if candidate else None),
            candidate_deferred_until=(candidate["deferred_until"] if candidate else None),
        )

    def get(self, principal: MemoryPrincipal, memory_id: str) -> MemoryRecordView:
        started = perf_counter()
        row = self.ownership.accessible_record(principal, memory_id)
        view = self._view(principal, row, include_body=True)
        latency_ms = round((perf_counter() - started) * 1000, 3)
        now = utc_now()
        cold = str(row["activation_tier"]) == "cold"
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_access_metrics (
                    memory_id,retrieval_count,last_retrieved_at,
                    last_rehydrated_at,rehydration_count,
                    last_retrieval_latency_ms,retrieval_latency_total_ms
                ) VALUES (?,1,?,?,?,?,?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    retrieval_count=memory_access_metrics.retrieval_count+1,
                    last_retrieved_at=excluded.last_retrieved_at,
                    last_retrieval_latency_ms=excluded.last_retrieval_latency_ms,
                    retrieval_latency_total_ms=memory_access_metrics.retrieval_latency_total_ms
                                               + excluded.last_retrieval_latency_ms,
                    last_rehydrated_at=CASE WHEN ? THEN excluded.last_rehydrated_at
                                            ELSE memory_access_metrics.last_rehydrated_at END,
                    rehydration_count=memory_access_metrics.rehydration_count+?
                """,
                (
                    memory_id, now, now if cold else None, int(cold), latency_ms, latency_ms,
                    int(cold), int(cold),
                ),
            )
        return view

    def list(self, principal: MemoryPrincipal, query: MemoryQuery | None = None) -> tuple[list[MemoryRecordView], int]:
        filters = query or MemoryQuery()
        clauses = ["r.status != 'deleted'"]
        values: list[Any] = [principal.user_id, principal.user_id]
        if not filters.include_archived and filters.status is None:
            clauses.append("r.status != 'archived'")
        if filters.privacy is None:
            # Sealed records live in an explicit vault compartment and do not
            # participate in ordinary listing/search.
            clauses.append("r.privacy != 'sealed'")
        if filters.activation_tier is not None:
            clauses.append("r.activation_tier = ?")
            values.append(filters.activation_tier.value)
        for column, value in (
            ("scope", filters.scope),
            ("form", filters.form),
            ("privacy", filters.privacy),
            ("status", filters.status),
        ):
            if value is not None:
                clauses.append(f"r.{column} = ?")
                values.append(value.value)
        for column, value in (
            ("space_id", filters.space_id),
            ("conversation_id", filters.conversation_id),
            ("project_id", filters.project_id),
        ):
            if value is not None:
                if column == "space_id":
                    clauses.append("r.space_id = ?")
                else:
                    target_type = column.removesuffix("_id")
                    clauses.append(
                        "EXISTS (SELECT 1 FROM memory_relations rel WHERE rel.source_memory_id = r.memory_id AND rel.target_type = ? AND rel.target_id = ?)"
                    )
                    values.append(target_type)
                values.append(value)
        where = " AND ".join(clauses)
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.*, v.revision_number, v.plaintext_hash
                FROM memory_records r
                JOIN memory_revisions v ON v.revision_id = r.current_revision_id
                WHERE (
                    (r.owner_user_id = ? AND r.space_id IS NULL) OR EXISTS (
                        SELECT 1 FROM shared_space_members m
                        WHERE m.space_id = r.space_id AND m.user_id = ?
                    )
                ) AND {where}
                ORDER BY r.pinned DESC, r.updated_at DESC, r.memory_id DESC
                """,
                values,
            ).fetchall()
        views = [self._view(principal, row, include_body=True) for row in rows]
        if filters.search:
            needle = filters.search.casefold()
            views = [
                view
                for view in views
                if needle
                in "\n".join(
                    (view.title, view.body or "", view.why_stored or "")
                ).casefold()
            ]
        total = len(views)
        return views[filters.offset : filters.offset + filters.limit], total

    def _state_digest(self, row) -> str:
        return _digest(
            {
                "memory_id": row["memory_id"],
                "owner_user_id": row["owner_user_id"],
                "space_id": row["space_id"],
                "scope": row["scope"],
                "form": row["form"],
                "privacy": row["privacy"],
                "status": row["status"],
                "current_revision_id": row["current_revision_id"],
                "plaintext_hash": row["plaintext_hash"],
                "pinned": row["pinned"],
            }
        )

    def correct(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        request: MemoryCorrectionRequest,
        *,
        request_id: str | None = None,
        preserve_form: bool = False,
    ) -> MemoryRecordView:
        self.repository.assert_content_writes_ready()
        self.repository.assert_nonessential_writes_ready()
        row = self.ownership.accessible_record(principal, memory_id, action="correct")
        if str(row["form"]) == "audit" and str(row["status"]) != "candidate":
            raise MemoryAuthorizationError(
                "Audit memory is append-only; record a new content-free event instead."
            )
        old_digest = self._state_digest(row)
        with self.repository.connect() as read_conn:
            current_revision = self._revision_row(read_conn, row)
        current_content = self._read_content(principal, row, current_revision)
        if request.change_kind == MemoryTruthChange.DIRECT_CONTRADICTION:
            links = {
                str(relation.get("target_type")): str(relation.get("target_id"))
                for relation in self._view(principal, row, include_body=False).relations
                if relation.get("target_type") and relation.get("target_id")
            }
            contradictory = self.create(
                principal,
                MemoryCreateRequest(
                    title=request.title or f"Contradiction of {current_content.title}",
                    body=request.body,
                    why_stored=request.reason,
                    scope=MemoryScope(str(row["scope"])),
                    form="corrective",
                    subtype="direct_contradiction",
                    privacy=MemoryPrivacy(str(row["privacy"])),
                    status="active",
                    activation_tier=str(row["activation_tier"]),
                    importance=float(row["importance"]),
                    confidence=request.confidence,
                    user_confirmed=True,
                    inference_kind="user_declared_contradiction",
                    observed_at=request.observed_at,
                    valid_from=request.valid_from,
                    valid_until=request.valid_until,
                    conversation_id=links.get("conversation"),
                    project_id=links.get("project"),
                    request_id=request_id,
                    space_id=row["space_id"],
                    form_data={"change_kind": "direct_contradiction"},
                    source=MemorySourceInput(
                        source_type="memory_contradiction",
                        source_id=memory_id,
                        source_label="Earlier canonical memory" if str(row["privacy"]) == "normal" else None,
                        source_time=utc_now(),
                        source_authority="user",
                        retrieval_method="explicit_correction",
                        provenance_status="declared",
                    ),
                ),
                actor=principal.user_id,
            )
            now = utc_now()
            with self.repository.transaction() as conn:
                contradiction_id = new_id("memcontradiction")
                conn.execute(
                    """
                    INSERT INTO memory_contradictions (
                        contradiction_id, left_memory_id, right_memory_id, severity,
                        status, rationale, created_at
                    ) VALUES (?, ?, ?, 'material', 'unresolved', ?, ?)
                    """,
                    (contradiction_id, memory_id, contradictory.memory_id, request.reason, now),
                )
                conn.execute(
                    """
                    INSERT INTO memory_relations (
                        relation_id, source_memory_id, target_type, target_id,
                        relation_type, confidence, is_inferred, provenance_source_id,
                        valid_from, valid_until, status
                    ) VALUES (?, ?, 'memory', ?, 'contradicts', ?, 0, NULL, ?, ?, 'active')
                    """,
                    (
                        new_id("memrel"), contradictory.memory_id, memory_id,
                        request.confidence, request.valid_from, request.valid_until,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO memory_truth_events (
                        truth_event_id, owner_user_id, memory_id, related_memory_id,
                        change_kind, prior_revision_id, resulting_revision_id,
                        rationale, observed_at, valid_from, valid_until,
                        transaction_at, status
                    ) VALUES (?, ?, ?, ?, 'direct_contradiction', ?, ?, ?, ?, ?, ?, ?, 'unresolved')
                    """,
                    (
                        new_id("truthevent"), principal.user_id, contradictory.memory_id,
                        memory_id, row["current_revision_id"], contradictory.current_revision_id,
                        request.reason, request.observed_at, request.valid_from,
                        request.valid_until, now,
                    ),
                )
            return contradictory
        content = MemoryContent(
            title=request.title or current_content.title,
            body=request.body,
            why_stored=request.reason,
            form_data=current_content.form_data,
        )
        privacy = MemoryPrivacy(str(row["privacy"]))
        with self.repository.transaction() as conn:
            revision_id, new_hash = self._insert_revision(
                conn,
                principal=principal,
                memory_id=memory_id,
                privacy=privacy,
                content=content,
                revision_number=int(row["revision_number"]) + 1,
                actor=principal.user_id,
                reason=request.reason,
                supersedes_revision_id=str(row["current_revision_id"]),
            )
            resulting_status = (
                MemoryLifecycle.SUPERSEDED.value
                if request.change_kind == MemoryTruthChange.RETRACTION
                else MemoryLifecycle.ACTIVE.value
            )
            conn.execute(
                """
                UPDATE memory_records SET current_revision_id = ?, title = ?,
                    form = CASE WHEN ? THEN form ELSE 'corrective' END,
                    updated_at = ?, observed_at = COALESCE(?, observed_at),
                    valid_from = COALESCE(?, valid_from), valid_until = ?, user_confirmed = 1,
                    confidence = COALESCE(?, confidence), status = ?
                WHERE memory_id = ?
                """,
                (
                    revision_id,
                    content.title if privacy == MemoryPrivacy.NORMAL else None,
                    int(preserve_form),
                    utc_now(),
                    request.observed_at,
                    request.valid_from,
                    request.valid_until,
                    request.confidence,
                    resulting_status,
                    memory_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO memory_truth_events (
                    truth_event_id, owner_user_id, memory_id, related_memory_id,
                    change_kind, prior_revision_id, resulting_revision_id,
                    rationale, observed_at, valid_from, valid_until,
                    transaction_at, status
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 'resolved')
                """,
                (
                    new_id("truthevent"), principal.user_id, memory_id,
                    request.change_kind.value, row["current_revision_id"], revision_id,
                    request.reason, request.observed_at, request.valid_from,
                    request.valid_until, utc_now(),
                ),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="corrected_superseded_revision",
                    memory_id=memory_id,
                    request_id=request_id,
                    old_state_digest=old_digest,
                    new_state_digest=new_hash,
                    scope=str(row["scope"]),
                    form="corrective",
                    privacy=privacy.value,
                ),
            )
        self._trace_mutation(request_id, memory_id, "corrected")
        return self.get(principal, memory_id)

    def add_relation(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        request: MemoryRelationCreateRequest,
    ) -> MemoryRecordView:
        row = self.ownership.accessible_record(principal, memory_id, action="correct")
        if request.target_type == "memory":
            self.ownership.accessible_record(principal, request.target_id)
        if request.provenance_source_id:
            with self.repository.connect() as conn:
                source = conn.execute(
                    "SELECT memory_id FROM memory_sources WHERE source_row_id = ?",
                    (request.provenance_source_id,),
                ).fetchone()
            if source is None or str(source["memory_id"]) != memory_id:
                raise MemoryAuthorizationError("Relationship provenance is outside this memory authority.")
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_relations (
                    relation_id, source_memory_id, target_type, target_id,
                    relation_type, confidence, is_inferred, provenance_source_id,
                    valid_from, valid_until, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    new_id("memrel"), memory_id, request.target_type,
                    request.target_id, request.relation_type, request.confidence,
                    int(request.inferred), request.provenance_source_id,
                    request.valid_from, request.valid_until,
                ),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="relation_added",
                    memory_id=memory_id,
                    request_id=None,
                    old_state_digest=self._state_digest(row),
                    new_state_digest=_digest(request.model_dump(mode="json")),
                    scope=str(row["scope"]),
                    form="relational",
                    privacy=str(row["privacy"]),
                ),
            )
        return self.get(principal, memory_id)

    def belief_explanation(self, principal: MemoryPrincipal, memory_id: str) -> dict[str, Any]:
        record = self.get(principal, memory_id)
        if record.privacy == MemoryPrivacy.SEALED and record.content_state != "available":
            return {
                "memory_id": memory_id,
                "content_state": "sealed_locked",
                "timeline": [],
                "contradictions": [],
                "provenance": [],
            }
        with self.repository.connect() as conn:
            timeline = conn.execute(
                """
                SELECT change_kind, related_memory_id, prior_revision_id,
                       resulting_revision_id, rationale, observed_at, valid_from,
                       valid_until, transaction_at, status
                FROM memory_truth_events
                WHERE owner_user_id = ? AND (memory_id = ? OR related_memory_id = ?)
                ORDER BY transaction_at, truth_event_id
                """,
                (principal.user_id, memory_id, memory_id),
            ).fetchall()
            contradictions = conn.execute(
                """
                SELECT contradiction_id, left_memory_id, right_memory_id, severity,
                       status, rationale, created_at, resolved_at
                FROM memory_contradictions
                WHERE left_memory_id = ? OR right_memory_id = ?
                ORDER BY created_at, contradiction_id
                """,
                (memory_id, memory_id),
            ).fetchall()
        return {
            "memory_id": memory_id,
            "current_status": record.status.value,
            "current_confidence": record.confidence,
            "observed_at": record.observed_at,
            "valid_from": record.valid_from,
            "valid_until": record.valid_until,
            "provenance": record.sources,
            "timeline": [dict(item) for item in timeline],
            "contradictions": [dict(item) for item in contradictions],
            "selection_rule": "active, non-expired, user-confirmed claims remain eligible; unresolved contradictions surface uncertainty",
            "hidden_reasoning_included": False,
        }

    def set_status(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        status: MemoryLifecycle,
        request: MemoryReasonRequest,
        *,
        request_id: str | None = None,
    ) -> MemoryRecordView:
        self.repository.assert_content_writes_ready()
        action = "archive" if status == MemoryLifecycle.ARCHIVED else "restore"
        row = self.ownership.accessible_record(principal, memory_id, action=action)
        old_digest = self._state_digest(row)
        activation = ActivationTier.ARCHIVED.value if status == MemoryLifecycle.ARCHIVED else ActivationTier.WARM.value
        with self.repository.transaction() as conn:
            conn.execute(
                "UPDATE memory_records SET status = ?, activation_tier = ?, updated_at = ? WHERE memory_id = ?",
                (status.value, activation, utc_now(), memory_id),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action=action,
                    memory_id=memory_id,
                    request_id=request_id,
                    old_state_digest=old_digest,
                    new_state_digest=_digest({"status": status.value, "reason": request.reason}),
                    scope=str(row["scope"]),
                    form=str(row["form"]),
                    privacy=str(row["privacy"]),
                ),
            )
        self._trace_mutation(request_id, memory_id, action)
        return self.get(principal, memory_id)

    def pin(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        request: MemoryPinRequest,
        *,
        request_id: str | None = None,
    ) -> MemoryRecordView:
        self.repository.assert_content_writes_ready()
        row = self.ownership.accessible_record(principal, memory_id, action="pin")
        old_digest = self._state_digest(row)
        with self.repository.transaction() as conn:
            conn.execute(
                "UPDATE memory_records SET pinned = ?, updated_at = ? WHERE memory_id = ?",
                (int(request.pinned), utc_now(), memory_id),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="pinned" if request.pinned else "unpinned",
                    memory_id=memory_id,
                    request_id=request_id,
                    old_state_digest=old_digest,
                    new_state_digest=_digest({"pinned": request.pinned}),
                    scope=str(row["scope"]),
                    form=str(row["form"]),
                    privacy=str(row["privacy"]),
                ),
            )
        return self.get(principal, memory_id)

    def decide_candidate(
        self,
        principal: MemoryPrincipal,
        memory_id: str,
        request: CandidateDecisionRequest,
        *,
        request_id: str | None = None,
    ) -> MemoryRecordView:
        self.repository.assert_content_writes_ready()
        row = self.ownership.accessible_record(principal, memory_id, action="correct")
        with self.repository.connect() as conn:
            candidate = conn.execute(
                "SELECT * FROM memory_candidates WHERE memory_id = ? AND review_state = 'pending'",
                (memory_id,),
            ).fetchone()
        if candidate is None:
            raise MemoryFabricError("The memory candidate is not pending review.")
        if request.decision in {CandidateDecision.APPROVE, CandidateDecision.SEAL} and (request.edited_body or request.edited_title):
            current = self.get(principal, memory_id)
            self.correct(
                principal,
                memory_id,
                MemoryCorrectionRequest(
                    title=request.edited_title or current.title,
                    body=request.edited_body or current.body or "",
                    reason=request.reason,
                ),
                request_id=request_id,
                preserve_form=True,
            )
            row = self.ownership.accessible_record(principal, memory_id, action="correct")
        if request.decision == CandidateDecision.DEFER:
            with self.repository.transaction() as conn:
                conn.execute(
                    "UPDATE memory_candidates SET deferred_until = ? WHERE memory_id = ?",
                    (request.defer_until, memory_id),
                )
                conn.execute(
                    MUTATION_RECEIPT_INSERT,
                    mutation_receipt_row(
                        actor_user_id=principal.user_id,
                        action="candidate_deferred",
                        memory_id=memory_id,
                        request_id=request_id,
                        old_state_digest=self._state_digest(row),
                        new_state_digest=_digest({"deferred": True, "until": request.defer_until}),
                        scope=str(row["scope"]),
                        form=str(row["form"]),
                        privacy=str(row["privacy"]),
                    ),
                )
            return self.get(principal, memory_id)
        if request.decision == CandidateDecision.SEAL:
            if str(row["owner_user_id"]) != principal.user_id:
                raise MemoryAuthorizationError("Only the owner may seal a candidate.")
            current = self.get(principal, memory_id)
            if current.privacy != MemoryPrivacy.SEALED:
                preview = self.preview_consequence(
                    principal,
                    memory_id,
                    ConsequencePreviewRequest(
                        action="change_privacy",
                        target_privacy=MemoryPrivacy.SEALED,
                        reason=request.reason,
                    ),
                )
                self.apply_consequence(
                    principal,
                    memory_id,
                    ConsequenceApplyRequest(
                        approval_id=preview["approval_id"],
                        approval_token=preview["approval_token"],
                    ),
                )
                row = self.ownership.accessible_record(principal, memory_id, action="correct")
        approved = request.decision in {CandidateDecision.APPROVE, CandidateDecision.SEAL}
        new_status = "active" if approved else "blocked"
        review_state = "approved" if approved else "rejected"
        consolidation_plan: dict[str, Any] | None = None
        if approved and str(candidate["candidate_kind"]) == "consolidation_duplicate_set":
            proposal = self.get(principal, memory_id)
            source_ids = sorted(
                str(value) for value in proposal.form_data.get("source_memory_ids", [])
            )
            keep_id = str(proposal.form_data.get("canonical_memory_id") or "")
            if len(source_ids) < 2 or keep_id not in source_ids:
                raise MemoryFabricError("The consolidation candidate no longer has a valid exact plan.")
            consolidation_plan = {"source_ids": source_ids, "keep_id": keep_id}
        with self.repository.transaction() as conn:
            if consolidation_plan is not None:
                placeholders = ",".join("?" for _ in consolidation_plan["source_ids"])
                source_rows = conn.execute(
                    f"""
                    SELECT r.memory_id, r.status, v.plaintext_hash
                    FROM memory_records r
                    JOIN memory_revisions v ON v.revision_id=r.current_revision_id
                    WHERE r.owner_user_id=? AND r.memory_id IN ({placeholders})
                    ORDER BY r.memory_id
                    """,
                    (principal.user_id, *consolidation_plan["source_ids"]),
                ).fetchall()
                if (
                    len(source_rows) != len(consolidation_plan["source_ids"])
                    or any(str(item["status"]) != "active" for item in source_rows)
                    or len({str(item["plaintext_hash"]) for item in source_rows}) != 1
                ):
                    raise MemoryFabricError(
                        "The exact-duplicate evidence changed; rebuild the consolidation candidate."
                    )
                for source_id in consolidation_plan["source_ids"]:
                    if source_id != consolidation_plan["keep_id"]:
                        conn.execute(
                            "UPDATE memory_records SET status='superseded', updated_at=? WHERE memory_id=?",
                            (utc_now(), source_id),
                        )
            conn.execute(
                """
                UPDATE memory_candidates SET review_state = ?, reviewed_at = ?, reviewed_by_user_id = ?
                WHERE memory_id = ?
                """,
                (review_state, utc_now(), principal.user_id, memory_id),
            )
            conn.execute(
                """
                UPDATE memory_records SET status = ?, user_confirmed = ?,
                    automatic_recall_suppressed = CASE WHEN ? THEN 1 ELSE automatic_recall_suppressed END,
                    updated_at = ? WHERE memory_id = ?
                """,
                (new_status, int(approved), int(consolidation_plan is not None), utc_now(), memory_id),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action=f"candidate_{request.decision.value}d",
                    memory_id=memory_id,
                    request_id=request_id,
                    old_state_digest=self._state_digest(row),
                    new_state_digest=_digest({"candidate_state": request.decision.value}),
                    scope=str(row["scope"]),
                    form=str(row["form"]),
                    privacy=str(row["privacy"]),
                ),
            )
        return self.get(principal, memory_id)

    def revisions(self, principal: MemoryPrincipal, memory_id: str) -> list[dict[str, Any]]:
        self.ownership.accessible_record(principal, memory_id)
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT revision_id, revision_number, plaintext_hash, created_by_actor,
                       created_at, reason, supersedes_revision_id, content_format
                FROM memory_revisions WHERE memory_id = ? ORDER BY revision_number DESC
                """,
                (memory_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_space(
        self, principal: MemoryPrincipal, request: SharedSpaceCreateRequest
    ) -> dict[str, Any]:
        self.repository.assert_content_writes_ready()
        space_id = new_id("space")
        now = utc_now()
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO shared_spaces (space_id, owner_user_id, label, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (space_id, principal.user_id, request.label, request.description, now, now),
            )
            conn.execute(
                """
                INSERT INTO shared_space_members (space_id, user_id, role, added_by_user_id, created_at)
                VALUES (?, ?, 'owner', ?, ?)
                """,
                (space_id, principal.user_id, principal.user_id, now),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="shared_space_created",
                    memory_id=None,
                    request_id=None,
                    old_state_digest=None,
                    new_state_digest=_digest({"space_id": space_id, "owner": principal.user_id}),
                    scope="shared_space",
                    form=None,
                    privacy="normal",
                ),
            )
        return {"space_id": space_id, "label": request.label, "role": "owner", "member_count": 1}

    def list_spaces(self, principal: MemoryPrincipal) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.space_id, s.label, s.description, s.owner_user_id, m.role,
                       (SELECT COUNT(*) FROM shared_space_members c WHERE c.space_id = s.space_id) AS member_count
                FROM shared_spaces s JOIN shared_space_members m ON m.space_id = s.space_id
                WHERE m.user_id = ? AND s.archived_at IS NULL ORDER BY s.label, s.space_id
                """,
                (principal.user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_space_invitations(self, principal: MemoryPrincipal) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT i.invitation_id, i.space_id, s.label AS space_label,
                       i.invited_user_id, i.role, i.state, i.invited_by_user_id,
                       i.created_at, i.responded_at, i.revoked_at,
                       CASE WHEN i.invited_user_id = ? THEN 'incoming' ELSE 'outgoing' END AS direction
                FROM shared_space_invitations i
                JOIN shared_spaces s ON s.space_id = i.space_id
                WHERE i.invited_user_id = ? OR (
                    i.invited_by_user_id = ? AND EXISTS (
                        SELECT 1 FROM shared_space_members m
                        WHERE m.space_id=i.space_id AND m.user_id=? AND m.role='owner'
                    )
                )
                ORDER BY i.created_at DESC, i.invitation_id DESC
                """,
                (
                    principal.user_id,
                    principal.user_id,
                    principal.user_id,
                    principal.user_id,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def respond_space_invitation(
        self,
        principal: MemoryPrincipal,
        invitation_id: str,
        request: SharedSpaceInvitationResponseRequest,
    ) -> dict[str, Any]:
        self.repository.assert_content_writes_ready()
        with self.repository.transaction() as conn:
            invitation = conn.execute(
                """
                SELECT invitation_id,space_id,invited_user_id,role,state,invited_by_user_id
                FROM shared_space_invitations WHERE invitation_id=?
                """,
                (invitation_id,),
            ).fetchone()
            if invitation is None or str(invitation["invited_user_id"]) != principal.user_id:
                raise MemoryNotFoundError("The shared-space invitation is unavailable.")
            if str(invitation["state"]) != "pending":
                raise MemoryFabricError("The shared-space invitation is no longer pending.")
            old_digest = _digest(dict(invitation))
            now = utc_now()
            if request.decision.value == "accept":
                existing = conn.execute(
                    "SELECT 1 FROM shared_space_members WHERE space_id=? AND user_id=?",
                    (invitation["space_id"], principal.user_id),
                ).fetchone()
                if existing is not None:
                    raise MemoryFabricError("The invited account is already a shared-space member.")
                conn.execute(
                    """
                    INSERT INTO shared_space_members (
                        space_id,user_id,role,added_by_user_id,created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        invitation["space_id"],
                        principal.user_id,
                        invitation["role"],
                        invitation["invited_by_user_id"],
                        now,
                    ),
                )
                state = "accepted"
                action = "shared_space_invitation_accepted"
            else:
                state = "declined"
                action = "shared_space_invitation_declined"
            conn.execute(
                "UPDATE shared_space_invitations SET state=?,responded_at=? WHERE invitation_id=?",
                (state, now, invitation_id),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action=action,
                    memory_id=None,
                    request_id=None,
                    old_state_digest=old_digest,
                    new_state_digest=_digest(
                        {
                            "invitation_id": invitation_id,
                            "space_id": invitation["space_id"],
                            "state": state,
                            "role": invitation["role"],
                        }
                    ),
                    scope="shared_space",
                    form=None,
                    privacy="normal",
                ),
            )
        return {
            "invitation_id": invitation_id,
            "space_id": str(invitation["space_id"]),
            "state": state,
            "role": str(invitation["role"]),
            "identity_blended": False,
        }

    def _space_state_digest(self, principal: MemoryPrincipal, space_id: str) -> str:
        self.ownership.assert_space_access(
            principal=principal, space_id=space_id, action="manage_members"
        )
        with self.repository.connect() as conn:
            space = conn.execute(
                "SELECT space_id, owner_user_id, updated_at FROM shared_spaces WHERE space_id = ?",
                (space_id,),
            ).fetchone()
            members = conn.execute(
                "SELECT user_id, role FROM shared_space_members WHERE space_id = ? ORDER BY user_id",
                (space_id,),
            ).fetchall()
            invitations = conn.execute(
                """
                SELECT invitation_id,invited_user_id,role,state
                FROM shared_space_invitations
                WHERE space_id=? AND state='pending'
                ORDER BY invitation_id
                """,
                (space_id,),
            ).fetchall()
        if space is None:
            raise MemoryNotFoundError("The shared space is unavailable.")
        return _digest(
            {
                "space": dict(space),
                "members": [dict(row) for row in members],
                "pending_invitations": [dict(row) for row in invitations],
            }
        )

    def preview_consequence(
        self,
        principal: MemoryPrincipal,
        target_id: str,
        request: ConsequencePreviewRequest,
    ) -> dict[str, Any]:
        self.repository.assert_content_writes_ready()
        if not self.policy.requires_approval(request.action):
            raise MemoryFabricError("The requested operation does not use consequence approval.")
        consequence: dict[str, Any] = {"action": request.action, "target_id": target_id}
        space_actions = {
            "add_space_member",
            "invite_space_member",
            "change_space_member_role",
            "remove_space_member",
        }
        if request.action in space_actions:
            needs_role = request.action != "remove_space_member"
            if not request.target_user_id or (needs_role and not request.target_role):
                raise MemoryFabricError("A target account and the required role are needed.")
            state_digest = self._space_state_digest(principal, target_id)
            self._assert_identity_user_exists(request.target_user_id)
            with self.repository.connect() as conn:
                space = conn.execute(
                    "SELECT owner_user_id FROM shared_spaces WHERE space_id=?",
                    (target_id,),
                ).fetchone()
                membership = conn.execute(
                    "SELECT role FROM shared_space_members WHERE space_id=? AND user_id=?",
                    (target_id, request.target_user_id),
                ).fetchone()
                pending = conn.execute(
                    """
                    SELECT invitation_id FROM shared_space_invitations
                    WHERE space_id=? AND invited_user_id=? AND state='pending'
                    """,
                    (target_id, request.target_user_id),
                ).fetchone()
            if space is None:
                raise MemoryNotFoundError("The shared space is unavailable.")
            target_is_owner = str(space["owner_user_id"]) == request.target_user_id
            if request.action == "invite_space_member":
                if membership is not None or pending is not None:
                    raise MemoryFabricError("The target account is already a member or has a pending invitation.")
                if request.target_role.value == "owner":
                    raise MemoryAuthorizationError("Shared-space ownership cannot be granted through an invitation.")
                effect = "The named account may accept or decline the exact pending role."
            elif request.action == "change_space_member_role":
                if membership is None:
                    raise MemoryFabricError("The target account is not a shared-space member.")
                if target_is_owner or request.target_role.value == "owner":
                    raise MemoryAuthorizationError("The canonical shared-space owner cannot be changed through a role update.")
                if str(membership["role"]) == request.target_role.value:
                    raise MemoryFabricError("A different shared-space role is required.")
                effect = "The existing member will receive the selected non-owner role."
            elif request.action == "remove_space_member":
                if membership is None:
                    raise MemoryFabricError("The target account is not a shared-space member.")
                if target_is_owner:
                    raise MemoryAuthorizationError("The canonical shared-space owner cannot be revoked.")
                effect = "The member will lose shared-space retrieval and mutation authority immediately."
            else:
                if membership is not None:
                    raise MemoryFabricError("The target account is already a member; use the role-change operation.")
                if pending is not None:
                    raise MemoryFabricError("The target account already has a pending invitation.")
                if request.target_role.value == "owner":
                    raise MemoryAuthorizationError("Shared-space ownership cannot be granted through direct membership.")
                effect = "The named local account will receive the selected shared-space role."
            consequence.update(
                {
                    "target_user_id": request.target_user_id,
                    "target_role": request.target_role.value if request.target_role else None,
                    "prior_role": str(membership["role"]) if membership else None,
                    "effect": effect,
                }
            )
        else:
            row = self.ownership.accessible_record(principal, target_id, action="delete" if request.action == "hard_delete" else "share")
            if str(row["owner_user_id"]) != principal.user_id:
                raise MemoryAuthorizationError("Only the memory owner may approve this operation.")
            state_digest = self._state_digest(row)
            if request.action == "hard_delete":
                from app.memory.release_service import MemoryReleaseService

                deletion_plan = MemoryReleaseService(
                    fabric=self, repository=self.repository
                ).delete_plan(principal, target_id)
                state_digest = _digest(
                    {"record_state": self._state_digest(row), "deletion_plan": deletion_plan}
                )
                consequence.update(
                    {
                        "deletion_plan": deletion_plan,
                        "derived_projections_purged": True,
                        "content_free_receipt_retained": True,
                        "recoverability": "Managed writable backups are purged. Disconnected or user-exported offline copies cannot be erased by Elysia.",
                    }
                )
            elif request.action == "change_privacy":
                if request.target_privacy is None or request.target_privacy.value == str(row["privacy"]):
                    raise MemoryFabricError("A different target privacy is required.")
                consequence.update(
                    {
                        "from_privacy": str(row["privacy"]),
                        "to_privacy": request.target_privacy.value,
                        "content_reencrypted": True,
                        "sealed_unlock_required": "sealed" in {str(row["privacy"]), request.target_privacy.value},
                    }
                )
            elif request.action == "move_to_space":
                if not request.target_space_id:
                    raise MemoryFabricError("A target shared space is required.")
                self.ownership.assert_space_access(
                    principal=principal, space_id=request.target_space_id, action="create"
                )
                if str(row["privacy"]) == "sealed":
                    raise MemoryAuthorizationError("Sealed memory cannot enter a shared space.")
                consequence.update(
                    {
                        "target_space_id": request.target_space_id,
                        "scope_becomes": "shared_space",
                        "private_declassified_to_normal": str(row["privacy"]) == "private",
                    }
                )
        approval_id = new_id("memapproval")
        token = secrets.token_urlsafe(32)
        expires_at = _iso_after(APPROVAL_TTL_SECONDS)
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_action_approvals (
                    approval_id, actor_user_id, action, target_id, state_digest,
                    consequence_json, token_hash, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    principal.user_id,
                    request.action,
                    target_id,
                    state_digest,
                    json.dumps(consequence, sort_keys=True),
                    sha256(token.encode("utf-8")).hexdigest(),
                    expires_at,
                    utc_now(),
                ),
            )
        return {
            "approval_id": approval_id,
            "approval_token": token,
            "expires_at_utc": expires_at,
            "one_time": True,
            "state_digest": state_digest,
            "consequence": consequence,
        }

    def apply_consequence(
        self,
        principal: MemoryPrincipal,
        target_id: str,
        request: ConsequenceApplyRequest,
    ) -> dict[str, Any]:
        self.repository.assert_content_writes_ready()
        with self.repository.connect() as conn:
            approval = conn.execute(
                "SELECT * FROM memory_action_approvals WHERE approval_id = ?",
                (request.approval_id,),
            ).fetchone()
        if approval is None or str(approval["actor_user_id"]) != principal.user_id:
            raise MemoryApprovalError("The exact memory approval is unavailable.")
        if str(approval["target_id"]) != target_id:
            raise MemoryApprovalError("The approval target does not match.")
        if approval["consumed_at"] is not None:
            raise MemoryApprovalError("The one-time memory approval was already consumed.")
        if datetime.now(UTC) >= _parse_iso(str(approval["expires_at"])):
            raise MemoryApprovalError("The memory approval expired.")
        supplied_hash = sha256(request.approval_token.encode("utf-8")).hexdigest()
        if not compare_digest(supplied_hash, str(approval["token_hash"])):
            raise MemoryApprovalError("The memory approval token does not match.")
        action = str(approval["action"])
        consequence = json.loads(str(approval["consequence_json"]))
        if action in {
            "add_space_member",
            "invite_space_member",
            "change_space_member_role",
            "remove_space_member",
        }:
            if action != "remove_space_member":
                # Identity and Memory are separate authorities. Revalidate at
                # application time so deletion of the target after preview
                # cannot strand an invitation or membership for a dead ID.
                self._assert_identity_user_exists(str(consequence["target_user_id"]))
            current_digest = self._space_state_digest(principal, target_id)
            if current_digest != str(approval["state_digest"]):
                raise MemoryApprovalError("The shared-space state changed after preview.")
            with self.repository.transaction() as conn:
                if action == "invite_space_member":
                    invitation_id = new_id("spaceinvite")
                    conn.execute(
                        """
                        INSERT INTO shared_space_invitations (
                            invitation_id,space_id,invited_user_id,role,state,
                            invited_by_user_id,created_at
                        ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                        """,
                        (
                            invitation_id,
                            target_id,
                            consequence["target_user_id"],
                            consequence["target_role"],
                            principal.user_id,
                            utc_now(),
                        ),
                    )
                    receipt_action = "shared_space_member_invited"
                elif action == "remove_space_member":
                    # Graph rows are a per-profile derived view. Revocation
                    # removes the former member's entire rebuildable graph so
                    # stale shared topology cannot remain in that account's
                    # local projection; canonical Memory is untouched.
                    conn.execute(
                        "DELETE FROM memory_graph_edges WHERE owner_user_id=?",
                        (consequence["target_user_id"],),
                    )
                    conn.execute(
                        "DELETE FROM memory_graph_nodes WHERE owner_user_id=?",
                        (consequence["target_user_id"],),
                    )
                    conn.execute(
                        "DELETE FROM shared_space_members WHERE space_id=? AND user_id=?",
                        (target_id, consequence["target_user_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE shared_space_invitations
                        SET state='revoked',revoked_at=?
                        WHERE space_id=? AND invited_user_id=? AND state='accepted'
                        """,
                        (utc_now(), target_id, consequence["target_user_id"]),
                    )
                    invitation_id = None
                    receipt_action = "shared_space_member_revoked"
                else:
                    conn.execute(
                        """
                        INSERT INTO shared_space_members (space_id, user_id, role, added_by_user_id, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(space_id, user_id) DO UPDATE SET
                            role=excluded.role, added_by_user_id=excluded.added_by_user_id,
                            created_at=excluded.created_at
                        """,
                        (
                            target_id,
                            consequence["target_user_id"],
                            consequence["target_role"],
                            principal.user_id,
                            utc_now(),
                        ),
                    )
                    invitation_id = None
                    receipt_action = (
                        "shared_space_member_role_changed"
                        if action == "change_space_member_role"
                        else "shared_space_member_added"
                    )
                self._consume_approval(conn, request.approval_id)
                conn.execute(
                    MUTATION_RECEIPT_INSERT,
                    mutation_receipt_row(
                        actor_user_id=principal.user_id,
                        action=receipt_action,
                        memory_id=None,
                        request_id=None,
                        old_state_digest=current_digest,
                        new_state_digest=_digest(consequence),
                        scope="shared_space",
                        form=None,
                        privacy="normal",
                        approval_id=request.approval_id,
                    ),
                )
            return {
                "applied": True,
                "action": action,
                "target_id": target_id,
                "invitation_id": invitation_id,
            }

        row = self.ownership.accessible_record(principal, target_id, action="delete" if action == "hard_delete" else "share")
        current_state_digest = self._state_digest(row)
        if action == "hard_delete":
            from app.memory.release_service import MemoryReleaseService

            release = MemoryReleaseService(fabric=self, repository=self.repository)
            current_state_digest = _digest(
                {
                    "record_state": current_state_digest,
                    "deletion_plan": release.delete_plan(principal, target_id),
                }
            )
        if current_state_digest != str(approval["state_digest"]):
            raise MemoryApprovalError("The memory changed after consequence preview.")
        old_digest = self._state_digest(row)
        if action == "hard_delete":
            with self.repository.connect() as conn:
                deleted_revision_ids = [
                    str(item[0])
                    for item in conn.execute(
                        "SELECT revision_id FROM memory_revisions WHERE memory_id=?",
                        (target_id,),
                    ).fetchall()
                ]
            from app.cognition.semantic_projection import (
                SemanticMemoryProjection,
                SemanticProjectionError,
            )
            from app.cognition.fts_projection import FtsMemoryProjection

            deletion_id = new_id("deletion")
            now = utc_now()
            with self.repository.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO memory_delete_operations (
                        deletion_id,approval_id,owner_user_id,memory_id,
                        revision_ids_json,original_activation_tier,phase,
                        created_at,updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'prepared', ?, ?)
                    """,
                    (
                        deletion_id,
                        request.approval_id,
                        principal.user_id,
                        target_id,
                        json.dumps(deleted_revision_ids, sort_keys=True),
                        str(row["activation_tier"]),
                        now,
                        now,
                    ),
                )
            canonical_committed = False
            try:
                # Validate/restore cold bytes before destructive work. This
                # changes only derived placement. An abrupt pre-commit exit is
                # repaired from canonical truth by the content-free journal.
                if str(row["activation_tier"]) == "cold":
                    release._restore_cold_payloads(principal, target_id)

                # Every external/derived authority is cleared before the
                # canonical commit. Offline user copies are deliberately
                # outside Elysia's reach and were disclosed in the plan.
                try:
                    semantic_projection_purge = SemanticMemoryProjection(
                        paths=self.repository.paths,
                        repository=self.repository,
                        fabric=self,
                    ).purge_record(target_id)
                except SemanticProjectionError as exc:
                    raise MemoryApprovalError(
                        "The configured semantic projection must be reachable before hard delete can safely purge every derived copy."
                    ) from exc
                projection_purge = FtsMemoryProjection(
                    paths=self.repository.paths,
                    repository=self.repository,
                    fabric=self,
                ).privacy_purge_record(principal, target_id)
                archive_rewrite = release.rewrite_archives_for_delete(
                    principal, target_id
                )
                part2e_purge = release.purge_part2e_derivatives(
                    principal, target_id
                )
                receipt = mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="hard_deleted",
                    # A hard-delete receipt proves that an approved operation
                    # completed; it must not retain a target/content equality
                    # oracle after the exhaustive purge.
                    memory_id=None,
                    request_id=None,
                    old_state_digest=None,
                    new_state_digest=None,
                    scope=None,
                    form=None,
                    privacy=None,
                    approval_id=request.approval_id,
                    reason_code="canonical_content_and_projections_purged",
                )
                with self.repository.transaction() as conn:
                    conn.execute(
                        "DELETE FROM memory_relations WHERE target_type='memory' AND target_id=?",
                        (target_id,),
                    )
                    conn.execute(
                        "DELETE FROM memory_records WHERE memory_id = ?", (target_id,)
                    )
                    # The approval carries the exact target, state digest, and
                    # deletion plan. It cannot survive a completed hard delete
                    # when the only retained authority is the minimized audit
                    # receipt. Delete the exact active approval first so this
                    # remains an atomic one-time operation, then remove any
                    # older target-bound approvals that could retain state.
                    consumed = conn.execute(
                        """
                        DELETE FROM memory_action_approvals
                        WHERE approval_id=? AND target_id=? AND consumed_at IS NULL
                        """,
                        (request.approval_id, target_id),
                    )
                    if consumed.rowcount != 1:
                        raise MemoryApprovalError(
                            "The one-time approval could not be consumed."
                        )
                    conn.execute(
                        "DELETE FROM memory_action_approvals WHERE target_id=?",
                        (target_id,),
                    )
                    conn.execute(MUTATION_RECEIPT_INSERT, receipt)
                    conn.execute(
                        """
                        UPDATE memory_delete_operations
                        SET phase='canonical_committed',updated_at=?
                        WHERE deletion_id=?
                        """,
                        (utc_now(), deletion_id),
                    )
                canonical_committed = True

                # SQLite secure-delete clears deleted cells. The durable saga
                # additionally truncates WAL and compacts free pages; startup
                # can repeat this step after an abrupt process exit.
                purge = self.repository.secure_purge_deleted_content()
                with self.repository.transaction() as conn:
                    conn.execute(
                        """
                        UPDATE memory_delete_operations
                        SET phase='physical_purged',updated_at=?
                        WHERE deletion_id=?
                        """,
                        (utc_now(), deletion_id),
                    )
                absence = release.verify_absence(
                    principal, target_id, revision_ids=deleted_revision_ids
                )
                if not absence["absent"]:
                    raise MemoryApprovalError(
                        "Hard deletion committed, but the exhaustive absence verifier found retained installation-managed state; recovery remains queued."
                    )
                with self.repository.transaction() as conn:
                    conn.execute(
                        "DELETE FROM memory_delete_operations WHERE deletion_id=?",
                        (deletion_id,),
                    )
            except Exception:
                if not canonical_committed:
                    # Canonical truth remains authoritative. Repair all
                    # rebuildable projections, backups, and cold placement.
                    # If compensation itself is interrupted, keep the journal
                    # for authenticated startup/Health recovery.
                    try:
                        release.recover_pending_deletions(principal)
                    except Exception:
                        pass
                raise
            return {
                "applied": True,
                "action": action,
                "memory_id": target_id,
                "content_retained_in_receipt": False,
                "physical_purge": purge,
                "derived_projection_purge": projection_purge,
                "semantic_projection_purge": semantic_projection_purge,
                "part2e_derivative_purge": part2e_purge,
                "archive_rewrite": archive_rewrite,
                "absence_verification": absence,
                "crash_recovery_journal_cleared": True,
                "offline_user_exports_erased": False,
            }
        if action == "change_privacy":
            target_privacy = MemoryPrivacy(str(consequence["to_privacy"]))
            return self._apply_privacy_change(
                principal, row, target_privacy, request.approval_id, old_digest
            )
        if action == "move_to_space":
            return self._apply_space_move(
                principal,
                row,
                str(consequence["target_space_id"]),
                request.approval_id,
                old_digest,
            )
        raise MemoryApprovalError("The approved memory action is unsupported.")

    @staticmethod
    def _consume_approval(conn, approval_id: str) -> None:
        result = conn.execute(
            """
            UPDATE memory_action_approvals SET consumed_at = ?
            WHERE approval_id = ? AND consumed_at IS NULL
            """,
            (utc_now(), approval_id),
        )
        if result.rowcount != 1:
            raise MemoryApprovalError("The one-time approval could not be consumed.")

    def _apply_privacy_change(
        self,
        principal: MemoryPrincipal,
        row,
        target_privacy: MemoryPrivacy,
        approval_id: str,
        old_digest: str,
    ) -> dict[str, Any]:
        source_privacy = MemoryPrivacy(str(row["privacy"]))
        semantic_projection_purge = None
        if source_privacy == MemoryPrivacy.NORMAL and target_privacy != MemoryPrivacy.NORMAL:
            from app.cognition.semantic_projection import (
                SemanticMemoryProjection,
                SemanticProjectionError,
            )

            try:
                semantic_projection_purge = SemanticMemoryProjection(
                    paths=self.repository.paths,
                    repository=self.repository,
                    fabric=self,
                ).purge_record(str(row["memory_id"]))
            except SemanticProjectionError as exc:
                raise MemoryApprovalError(
                    "The configured semantic projection must be reachable before a private transition can safely purge its derived vector."
                ) from exc
        with self.repository.connect() as conn:
            revision = self._revision_row(conn, row)
            revision_history = conn.execute(
                "SELECT * FROM memory_revisions WHERE memory_id = ? ORDER BY revision_number",
                (row["memory_id"],),
            ).fetchall()
        content = self._read_content(principal, row, revision)
        # Privacy applies to the whole record history, not only its newest
        # revision. Re-encrypt every immutable historical body in place so a
        # normal→private/sealed transition cannot leave plaintext remnants.
        historical_plaintext = [
            (
                history,
                self.encryption.decrypt_content(
                    principal=principal,
                    privacy=source_privacy,
                    memory_id=str(row["memory_id"]),
                    revision_id=str(history["revision_id"]),
                    row=history,
                ),
            )
            for history in revision_history
        ]
        with self.repository.transaction() as conn:
            for history, plaintext in historical_plaintext:
                encrypted = self.encryption.encrypt_content(
                    principal=principal,
                    privacy=target_privacy,
                    memory_id=str(row["memory_id"]),
                    revision_id=str(history["revision_id"]),
                    plaintext=plaintext,
                )
                conn.execute(
                    """
                    UPDATE memory_revisions SET content_ciphertext = ?, content_nonce = ?,
                        wrapped_data_key = ?, key_nonce = ?, key_id = ?,
                        content_format = ?, plaintext_hash = ?, digest_format = ?
                    WHERE revision_id = ?
                    """,
                    (
                        encrypted.ciphertext,
                        encrypted.nonce,
                        encrypted.wrapped_data_key,
                        encrypted.key_nonce,
                        encrypted.key_id,
                        encrypted.content_format,
                        encrypted.plaintext_hash,
                        self.encryption.digest_format(target_privacy),
                        history["revision_id"],
                    ),
                )
            revision_id, new_hash = self._insert_revision(
                conn,
                principal=principal,
                memory_id=str(row["memory_id"]),
                privacy=target_privacy,
                content=content,
                revision_number=int(row["revision_number"]) + 1,
                actor=principal.user_id,
                reason="Approved privacy transition.",
                supersedes_revision_id=str(row["current_revision_id"]),
            )
            conn.execute(
                """
                UPDATE memory_records SET privacy = ?, current_revision_id = ?,
                    title = ?, egress_allowed = 0, updated_at = ? WHERE memory_id = ?
                """,
                (
                    target_privacy.value,
                    revision_id,
                    content.title if target_privacy == MemoryPrivacy.NORMAL else None,
                    utc_now(),
                    row["memory_id"],
                ),
            )
            self._consume_approval(conn, approval_id)
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="privacy_changed",
                    memory_id=str(row["memory_id"]),
                    request_id=None,
                    old_state_digest=old_digest,
                    new_state_digest=new_hash,
                    scope=str(row["scope"]),
                    form=str(row["form"]),
                    privacy=target_privacy.value,
                    approval_id=approval_id,
                ),
            )
        purge = None
        projection_purge = None
        if source_privacy == MemoryPrivacy.NORMAL and target_privacy != MemoryPrivacy.NORMAL:
            purge = self.repository.secure_purge_deleted_content()
            from app.cognition.fts_projection import FtsMemoryProjection

            projection_purge = FtsMemoryProjection(
                paths=self.repository.paths,
                repository=self.repository,
                fabric=self,
            ).privacy_purge_record(principal, str(row["memory_id"]))
        return {
            "applied": True,
            "action": "change_privacy",
            "record": self.get(principal, str(row["memory_id"])).model_dump(mode="json"),
            "plaintext_history_purge": purge,
            "derived_projection_purge": projection_purge,
            "semantic_projection_purge": semantic_projection_purge,
        }

    def _apply_space_move(
        self,
        principal: MemoryPrincipal,
        row,
        space_id: str,
        approval_id: str,
        old_digest: str,
    ) -> dict[str, Any]:
        self.ownership.assert_space_access(principal=principal, space_id=space_id, action="create")
        privacy = MemoryPrivacy(str(row["privacy"]))
        revision_id = str(row["current_revision_id"])
        new_hash = str(row["plaintext_hash"])
        content = None
        if privacy == MemoryPrivacy.PRIVATE:
            with self.repository.connect() as conn:
                revision = self._revision_row(conn, row)
            content = self._read_content(principal, row, revision)
        with self.repository.transaction() as conn:
            if content is not None:
                revision_id, new_hash = self._insert_revision(
                    conn,
                    principal=principal,
                    memory_id=str(row["memory_id"]),
                    privacy=MemoryPrivacy.NORMAL,
                    content=content,
                    revision_number=int(row["revision_number"]) + 1,
                    actor=principal.user_id,
                    reason="Approved private-to-shared declassification.",
                    supersedes_revision_id=str(row["current_revision_id"]),
                )
            conn.execute(
                """
                UPDATE memory_records SET scope = 'shared_space', space_id = ?,
                    privacy = ?, current_revision_id = ?, title = COALESCE(?, title),
                    egress_allowed = 0, updated_at = ? WHERE memory_id = ?
                """,
                (
                    space_id,
                    "normal" if content is not None else privacy.value,
                    revision_id,
                    content.title if content is not None else None,
                    utc_now(),
                    row["memory_id"],
                ),
            )
            self._consume_approval(conn, approval_id)
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="moved_to_shared_space",
                    memory_id=str(row["memory_id"]),
                    request_id=None,
                    old_state_digest=old_digest,
                    new_state_digest=new_hash,
                    scope="shared_space",
                    form=str(row["form"]),
                    privacy="normal" if content is not None else privacy.value,
                    approval_id=approval_id,
                ),
            )
        return {"applied": True, "action": "move_to_space", "record": self.get(principal, str(row["memory_id"])).model_dump(mode="json")}

    def _assert_identity_user_exists(self, user_id: str) -> None:
        from app.api.account_service import AccountPaths, AccountStore

        identity_root = self.repository.paths.identity_dir
        store = AccountStore(
            AccountPaths(
                identity_root=identity_root,
                database_path=identity_root / "elysia_identity.sqlite",
                profile_photo_dir=identity_root / "profile_photos",
                current_session_path=identity_root / "current_session.json",
                elysia_paths=self.repository.paths,
            )
        )
        store.initialize()
        with store._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE id = ? AND disabled_at_utc IS NULL", (user_id,)
            ).fetchone()
        if row is None:
            raise MemoryFabricError("The target local account does not exist.")

    def receipts(self, principal: MemoryPrincipal, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT mutation_id, actor_user_id, request_id, memory_id, action,
                       old_state_digest, new_state_digest, scope, form, privacy,
                       approval_id, projection_invalidation_state, completion_status,
                       reason_code, created_at
                FROM memory_mutation_receipts WHERE actor_user_id = ?
                ORDER BY created_at DESC, mutation_id DESC LIMIT ?
                """,
                (principal.user_id, max(1, min(500, limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_approvals(self, principal: MemoryPrincipal) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT approval_id, action, target_id, consequence_json, expires_at, created_at
                FROM memory_action_approvals
                WHERE actor_user_id = ? AND consumed_at IS NULL AND expires_at > ?
                ORDER BY created_at DESC
                """,
                (principal.user_id, utc_now()),
            ).fetchall()
        return [
            {
                "approval_id": row["approval_id"],
                "action": row["action"],
                "target_id": row["target_id"],
                "consequence": json.loads(str(row["consequence_json"])),
                "expires_at_utc": row["expires_at"],
                "approval_token_exposed": False,
            }
            for row in rows
        ]

    def settings(self, principal: MemoryPrincipal) -> MemorySettings:
        self.repository.default_settings(principal.user_id)
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_settings WHERE owner_user_id = ?",
                (principal.user_id,),
            ).fetchone()
        return MemorySettings(
            memory_recording_enabled=bool(row["memory_recording_enabled"]),
            storage_resource_profile=str(row["storage_resource_profile"]),
            default_privacy=str(row["default_privacy"]),
            candidate_behavior=str(row["candidate_behavior"]),
            autonomy_level=int(row["autonomy_level"]),
            internet_master_enabled=bool(row["internet_master_enabled"]),
            retrieval_breadth=str(row["retrieval_breadth"]),
            research_initiative=str(row["research_initiative"]),
            safe_search_level=str(row["safe_search_level"]),
            preferred_reasoning_gear=str(row["preferred_reasoning_gear"]),
            autonomy_domain_overrides=json.loads(
                str(row["autonomy_domain_overrides_json"] or "{}")
            ),
            compute_preference=str(row["compute_preference"]),
            model_performance_preference=str(row["model_performance_preference"]),
            background_cognition_enabled=bool(row["background_cognition_enabled"]),
            cpu_percent_ceiling=int(row["cpu_percent_ceiling"]),
            ram_mb_ceiling=int(row["ram_mb_ceiling"]),
            vram_mb_ceiling=int(row["vram_mb_ceiling"]),
            max_background_jobs=int(row["max_background_jobs"]),
            memory_storage_profile=str(row["memory_storage_profile"]),
            storage_budget_mode=str(row["storage_budget_mode"]),
            storage_budget_value=float(row["storage_budget_value"]),
            emergency_free_space_reserve_mb=int(row["emergency_free_space_reserve_mb"]),
            consolidation_enabled=bool(row["consolidation_enabled"]),
            consolidation_schedule=str(row["consolidation_schedule"]),
            consolidation_resource_percent=int(row["consolidation_resource_percent"]),
            backup_enabled=bool(row["backup_enabled"]),
            backup_schedule=str(row["backup_schedule"]),
            backup_retention_count=int(row["backup_retention_count"]),
            retention_policy=str(row["retention_policy"]),
            hot_retention_days=int(row["hot_retention_days"]),
            cold_after_days=int(row["cold_after_days"]),
            prospective_notifications_enabled=bool(row["prospective_notifications_enabled"]),
        )

    def update_settings(
        self, principal: MemoryPrincipal, settings: MemorySettings
    ) -> MemorySettings:
        self.repository.assert_content_writes_ready()
        try:
            from app.api.account_service import get_authenticated_governance

            governance = get_authenticated_governance()
        except Exception:
            governance = {"managed": False, "managed_policy": None}
        policy = dict(governance.get("managed_policy") or {})
        if governance.get("managed"):
            if settings.consolidation_enabled and not bool(policy.get("consolidation_allowed", True)):
                raise MemoryAuthorizationError("Managed-profile policy does not allow consolidation.")
            if settings.backup_enabled and not bool(policy.get("managed_backups_allowed", True)):
                raise MemoryAuthorizationError("Managed-profile policy does not allow managed backups.")
            effective_budget_mb = (
                settings.storage_budget_value
                if settings.storage_budget_mode == "absolute_mb"
                else shutil.disk_usage(self.repository.paths.data_dir).total
                * settings.storage_budget_value
                / 100.0
                / (1024 * 1024)
            )
            if effective_budget_mb > int(policy.get("storage_budget_mb_ceiling", 32768)):
                raise MemoryAuthorizationError("The requested storage budget exceeds the managed-profile ceiling.")
            if settings.backup_retention_count > int(policy.get("backup_retention_maximum", 5)):
                raise MemoryAuthorizationError("The requested backup retention exceeds the managed-profile ceiling.")
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_settings (
                    owner_user_id, memory_recording_enabled, storage_resource_profile,
                    default_privacy, candidate_behavior, autonomy_level,
                    internet_master_enabled, retrieval_breadth, research_initiative,
                    safe_search_level, preferred_reasoning_gear,
                    autonomy_domain_overrides_json, compute_preference,
                    model_performance_preference, background_cognition_enabled,
                    cpu_percent_ceiling, ram_mb_ceiling, vram_mb_ceiling,
                    max_background_jobs, memory_storage_profile,
                    storage_budget_mode, storage_budget_value,
                    emergency_free_space_reserve_mb, consolidation_enabled,
                    consolidation_schedule, consolidation_resource_percent,
                    backup_enabled, backup_schedule, backup_retention_count,
                    retention_policy, hot_retention_days, cold_after_days,
                    prospective_notifications_enabled, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_user_id) DO UPDATE SET
                    memory_recording_enabled=excluded.memory_recording_enabled,
                    storage_resource_profile=excluded.storage_resource_profile,
                    default_privacy=excluded.default_privacy,
                    candidate_behavior=excluded.candidate_behavior,
                    autonomy_level=excluded.autonomy_level,
                    internet_master_enabled=excluded.internet_master_enabled,
                    retrieval_breadth=excluded.retrieval_breadth,
                    research_initiative=excluded.research_initiative,
                    safe_search_level=excluded.safe_search_level,
                    preferred_reasoning_gear=excluded.preferred_reasoning_gear,
                    autonomy_domain_overrides_json=excluded.autonomy_domain_overrides_json,
                    compute_preference=excluded.compute_preference,
                    model_performance_preference=excluded.model_performance_preference,
                    background_cognition_enabled=excluded.background_cognition_enabled,
                    cpu_percent_ceiling=excluded.cpu_percent_ceiling,
                    ram_mb_ceiling=excluded.ram_mb_ceiling,
                    vram_mb_ceiling=excluded.vram_mb_ceiling,
                    max_background_jobs=excluded.max_background_jobs,
                    memory_storage_profile=excluded.memory_storage_profile,
                    storage_budget_mode=excluded.storage_budget_mode,
                    storage_budget_value=excluded.storage_budget_value,
                    emergency_free_space_reserve_mb=excluded.emergency_free_space_reserve_mb,
                    consolidation_enabled=excluded.consolidation_enabled,
                    consolidation_schedule=excluded.consolidation_schedule,
                    consolidation_resource_percent=excluded.consolidation_resource_percent,
                    backup_enabled=excluded.backup_enabled,
                    backup_schedule=excluded.backup_schedule,
                    backup_retention_count=excluded.backup_retention_count,
                    retention_policy=excluded.retention_policy,
                    hot_retention_days=excluded.hot_retention_days,
                    cold_after_days=excluded.cold_after_days,
                    prospective_notifications_enabled=excluded.prospective_notifications_enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    principal.user_id,
                    int(settings.memory_recording_enabled),
                    settings.storage_resource_profile,
                    settings.default_privacy.value,
                    settings.candidate_behavior,
                    settings.autonomy_level,
                    int(settings.internet_master_enabled),
                    settings.retrieval_breadth,
                    settings.research_initiative,
                    settings.safe_search_level,
                    settings.preferred_reasoning_gear,
                    json.dumps(settings.autonomy_domain_overrides, sort_keys=True),
                    settings.compute_preference,
                    settings.model_performance_preference,
                    int(settings.background_cognition_enabled),
                    settings.cpu_percent_ceiling,
                    settings.ram_mb_ceiling,
                    settings.vram_mb_ceiling,
                    settings.max_background_jobs,
                    settings.memory_storage_profile,
                    settings.storage_budget_mode,
                    settings.storage_budget_value,
                    settings.emergency_free_space_reserve_mb,
                    int(settings.consolidation_enabled),
                    settings.consolidation_schedule,
                    settings.consolidation_resource_percent,
                    int(settings.backup_enabled),
                    settings.backup_schedule,
                    settings.backup_retention_count,
                    settings.retention_policy,
                    settings.hot_retention_days,
                    settings.cold_after_days,
                    int(settings.prospective_notifications_enabled),
                    utc_now(),
                ),
            )
            conn.execute(
                MUTATION_RECEIPT_INSERT,
                mutation_receipt_row(
                    actor_user_id=principal.user_id,
                    action="foundational_settings_updated",
                    memory_id=None,
                    request_id=None,
                    old_state_digest=None,
                    new_state_digest=_digest(settings.model_dump(mode="json")),
                    scope="user",
                    form="metacognitive",
                    privacy="private",
                ),
            )
        return self.settings(principal)

    def summary(self, principal: MemoryPrincipal) -> dict[str, Any]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT scope, form, privacy, status, pinned
                FROM memory_records r
                WHERE r.status != 'deleted' AND r.privacy != 'sealed' AND (
                    (r.owner_user_id = ? AND r.space_id IS NULL) OR EXISTS (
                        SELECT 1 FROM shared_space_members m
                        WHERE m.space_id = r.space_id AND m.user_id = ?
                    )
                )
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
            candidates = conn.execute(
                """
                SELECT COUNT(*) FROM memory_candidates c JOIN memory_records r ON r.memory_id = c.memory_id
                WHERE r.owner_user_id = ? AND c.review_state = 'pending'
                """,
                (principal.user_id,),
            ).fetchone()[0]
        counters = {
            key: Counter(str(row[key]) for row in rows)
            for key in ("scope", "form", "privacy", "status")
        }
        return {
            "total_items": len(rows),
            "scope_counts": dict(counters["scope"]),
            "form_counts": dict(counters["form"]),
            "privacy_counts": dict(counters["privacy"]),
            "status_counts": dict(counters["status"]),
            "pinned_count": sum(bool(row["pinned"]) for row in rows),
            "pending_candidate_count": int(candidates),
            "canonical_authority": "xdg_sqlite",
            "legacy_writer_active": False,
            "generated_at_utc": utc_now(),
        }

    def health(self, principal: MemoryPrincipal | None = None) -> dict[str, Any]:
        health = self.repository.health()
        if principal is not None:
            health["key_status"] = self.encryption.key_status(principal.user_id)
            health["sealed_status"] = self.encryption.sealed_status(principal)
            health["link_integrity"] = self.link_integrity(principal)
        health.update(
            {
                "private_memory_encrypted": True,
                "sealed_memory_encrypted": True,
                "sealed_persistent_index": False,
                "legacy_writer_active": False,
                "raw_path_exposed": False,
            }
        )
        return health

    def link_integrity(
        self, principal: MemoryPrincipal, *, limit: int = 5_000
    ) -> dict[str, Any]:
        """Diagnose accessible cross-authority links without mutating history."""
        from app.memory.source_adapters import validate_source_reference

        bounded = max(1, min(int(limit), 20_000))
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT rel.source_memory_id, rel.target_type, rel.target_id
                FROM memory_relations rel
                JOIN memory_records r ON r.memory_id = rel.source_memory_id
                WHERE r.status != 'deleted' AND (
                    (r.owner_user_id = ? AND r.space_id IS NULL) OR EXISTS (
                        SELECT 1 FROM shared_space_members m
                        WHERE m.space_id = r.space_id AND m.user_id = ?
                    )
                )
                ORDER BY rel.source_memory_id, rel.relation_id
                LIMIT ?
                """,
                (principal.user_id, principal.user_id, bounded + 1),
            ).fetchall()
        sampled = rows[:bounded]
        conversation_by_memory = {
            str(row["source_memory_id"]): str(row["target_id"])
            for row in sampled
            if str(row["target_type"]) == "conversation"
        }
        dangling: list[dict[str, str]] = []
        validated = 0
        for row in sampled:
            target_type = str(row["target_type"])
            target_id = str(row["target_id"])
            try:
                validate_source_reference(
                    target_type,
                    target_id,
                    context_id=(
                        conversation_by_memory.get(str(row["source_memory_id"]))
                        if target_type == "message"
                        else None
                    ),
                )
                validated += 1
            except Exception as exc:
                dangling.append(
                    {
                        "memory_id": str(row["source_memory_id"]),
                        "target_type": target_type,
                        "target_id": target_id,
                        "diagnostic": str(exc)[:240],
                    }
                )
        return {
            "state": "degraded" if dangling else "ready",
            "checked": len(sampled),
            "validated": validated,
            "dangling_count": len(dangling),
            "dangling": dangling[:100],
            "truncated": len(rows) > bounded or len(dangling) > 100,
            "records_deleted": 0,
        }

    @staticmethod
    def _trace_mutation(request_id: str | None, memory_id: str, action: str) -> None:
        if not request_id:
            return
        try:
            from app.api.request_trace_service import (
                mark_request_trace_completed,
                start_request_trace,
            )

            start_request_trace(
                request_id=request_id,
                route_used=f"memory.{action}",
                ui_surface="memory_room",
                selected_mode="canonical_memory",
                phase="memory_mutation",
                label="Memory mutation started",
                detail=f"{action}: {memory_id}",
            )
            mark_request_trace_completed(
                request_id=request_id,
                phase="memory_mutation",
                label="Memory mutation completed",
                detail=action,
                locality_state="local",
                approval_state="not_needed",
                approval_needed=False,
                execution_operation=f"memory_{action}",
                execution_status="completed",
                execution_summary="Durable sanitized memory receipt written.",
            )
        except Exception:
            return


class MemoryCandidateService:
    def __init__(self, fabric: MemoryFabricService | None = None) -> None:
        self.fabric = fabric or MemoryFabricService()

    def create(self, principal: MemoryPrincipal, request: MemoryCandidateCreateRequest):
        return self.fabric.create_candidate(principal, request)

    def decide(self, principal: MemoryPrincipal, memory_id: str, request: CandidateDecisionRequest):
        return self.fabric.decide_candidate(principal, memory_id, request)


class MemoryMutationService:
    def __init__(self, fabric: MemoryFabricService | None = None) -> None:
        self.fabric = fabric or MemoryFabricService()


class MemoryReceiptService:
    def __init__(self, fabric: MemoryFabricService | None = None) -> None:
        self.fabric = fabric or MemoryFabricService()

    def list(self, principal: MemoryPrincipal, limit: int = 100):
        return self.fabric.receipts(principal, limit=limit)


class MemorySummaryService:
    def __init__(self, fabric: MemoryFabricService | None = None, **_: Any) -> None:
        self.fabric = fabric or MemoryFabricService()

    def get_summary(self, *, principal: MemoryPrincipal | None = None, **_: Any):
        return self.fabric.summary(principal or self.fabric.current_principal())


class MemoryHealthService:
    def __init__(self, fabric: MemoryFabricService | None = None) -> None:
        self.fabric = fabric or MemoryFabricService()

    def status(self, principal: MemoryPrincipal | None = None):
        return self.fabric.health(principal)


__all__ = (
    "MemoryApprovalError",
    "MemoryAuthorizationError",
    "MemoryCandidateService",
    "MemoryFabricError",
    "MemoryFabricService",
    "MemoryHealthService",
    "MemoryMutationService",
    "MemoryNotFoundError",
    "MemoryOwnershipService",
    "MemoryPolicyService",
    "MemoryReceiptService",
    "MemorySummaryService",
)
