"""Canonical XDG-local SQLite authority for explicit Elysia memory."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Iterator

from app.ids import new_id
from app.install.paths import ElysiaPaths, ensure_memory_directories, resolve_elysia_paths


SCHEMA_VERSION = 4
SCHEMA_NAME = "pass10d-gate-zero-shared-space-lifecycle-v4"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_records (
    memory_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    space_id TEXT,
    scope TEXT NOT NULL CHECK (scope IN ('user','conversation','project','research','operational','system','shared_space')),
    form TEXT NOT NULL CHECK (form IN ('episodic','semantic','procedural','prospective','relational','predictive','corrective','metacognitive','audit')),
    subtype TEXT,
    privacy TEXT NOT NULL CHECK (privacy IN ('normal','private','sealed')),
    status TEXT NOT NULL CHECK (status IN ('candidate','active','working','archived','superseded','blocked','deleted')),
    title TEXT,
    current_revision_id TEXT NOT NULL,
    importance REAL NOT NULL CHECK (importance >= 0.0 AND importance <= 1.0),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    user_confirmed INTEGER NOT NULL CHECK (user_confirmed IN (0,1)),
    inference_kind TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    observed_at TEXT,
    valid_from TEXT,
    valid_until TEXT,
    activation_tier TEXT NOT NULL CHECK (activation_tier IN ('working','hot','warm','cold','archived')),
    pinned INTEGER NOT NULL CHECK (pinned IN (0,1)),
    egress_allowed INTEGER NOT NULL CHECK (egress_allowed IN (0,1)),
    legacy_class TEXT,
    schema_version INTEGER NOT NULL,
    FOREIGN KEY (current_revision_id) REFERENCES memory_revisions(revision_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (space_id) REFERENCES shared_spaces(space_id)
);

CREATE TABLE IF NOT EXISTS memory_revisions (
    revision_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
    content_ciphertext BLOB NOT NULL,
    content_nonce BLOB,
    wrapped_data_key BLOB,
    key_nonce BLOB,
    key_id TEXT,
    content_format TEXT NOT NULL,
    plaintext_hash TEXT NOT NULL,
    digest_format TEXT NOT NULL DEFAULT 'legacy-sha256-v1',
    created_by_actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT,
    supersedes_revision_id TEXT,
    UNIQUE (memory_id, revision_number),
    FOREIGN KEY (memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (supersedes_revision_id) REFERENCES memory_revisions(revision_id)
);

CREATE TABLE IF NOT EXISTS memory_sources (
    source_row_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    source_label TEXT,
    source_time TEXT,
    source_authority TEXT NOT NULL,
    retrieval_method TEXT,
    provenance_status TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_relations (
    relation_id TEXT PRIMARY KEY,
    source_memory_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    confidence REAL,
    is_inferred INTEGER NOT NULL CHECK (is_inferred IN (0,1)),
    provenance_source_id TEXT,
    valid_from TEXT,
    valid_until TEXT,
    status TEXT NOT NULL,
    FOREIGN KEY (source_memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE,
    FOREIGN KEY (provenance_source_id) REFERENCES memory_sources(source_row_id)
);

CREATE TABLE IF NOT EXISTS memory_contradictions (
    contradiction_id TEXT PRIMARY KEY,
    left_memory_id TEXT NOT NULL,
    right_memory_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    rationale TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (left_memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE,
    FOREIGN KEY (right_memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_candidates (
    candidate_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL UNIQUE,
    candidate_kind TEXT NOT NULL,
    review_state TEXT NOT NULL CHECK (review_state IN ('pending','approved','rejected')),
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by_user_id TEXT,
    FOREIGN KEY (memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_mutation_receipts (
    mutation_id TEXT PRIMARY KEY,
    actor_user_id TEXT NOT NULL,
    request_id TEXT,
    memory_id TEXT,
    action TEXT NOT NULL,
    old_state_digest TEXT,
    new_state_digest TEXT,
    scope TEXT,
    form TEXT,
    privacy TEXT,
    approval_id TEXT,
    projection_invalidation_state TEXT NOT NULL,
    completion_status TEXT NOT NULL,
    reason_code TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shared_spaces (
    space_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS shared_space_members (
    space_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner','editor','contributor','reader')),
    added_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (space_id, user_id),
    FOREIGN KEY (space_id) REFERENCES shared_spaces(space_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_keys (
    key_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    key_kind TEXT NOT NULL CHECK (key_kind IN ('account_master','sealed_vault')),
    wrapping_method TEXT NOT NULL,
    wrapped_key BLOB NOT NULL,
    nonce BLOB NOT NULL,
    salt BLOB NOT NULL,
    kdf_parameters_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0,1)),
    UNIQUE (owner_user_id, key_kind)
);

CREATE TABLE IF NOT EXISTS memory_session_keys (
    session_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    wrapped_key BLOB NOT NULL,
    nonce BLOB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    schema_version INTEGER PRIMARY KEY,
    migration_name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    result TEXT NOT NULL,
    rollback_metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_jobs (
    job_id TEXT PRIMARY KEY,
    owner_user_id TEXT,
    job_kind TEXT NOT NULL,
    state TEXT NOT NULL,
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    result_code TEXT
);

CREATE TABLE IF NOT EXISTS memory_action_approvals (
    approval_id TEXT PRIMARY KEY,
    actor_user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_id TEXT NOT NULL,
    state_digest TEXT NOT NULL,
    consequence_json TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_settings (
    owner_user_id TEXT PRIMARY KEY,
    memory_recording_enabled INTEGER NOT NULL CHECK (memory_recording_enabled IN (0,1)),
    storage_resource_profile TEXT NOT NULL,
    default_privacy TEXT NOT NULL CHECK (default_privacy IN ('normal','private','sealed')),
    candidate_behavior TEXT NOT NULL,
    autonomy_level INTEGER NOT NULL CHECK (autonomy_level BETWEEN 1 AND 5),
    internet_master_enabled INTEGER NOT NULL CHECK (internet_master_enabled IN (0,1)),
    retrieval_breadth TEXT NOT NULL DEFAULT 'balanced' CHECK (retrieval_breadth IN ('focused','balanced','broad')),
    research_initiative TEXT NOT NULL DEFAULT 'balanced' CHECK (research_initiative IN ('manual','balanced','proactive')),
    safe_search_level TEXT NOT NULL DEFAULT 'strict' CHECK (safe_search_level IN ('strict','moderate','off')),
    preferred_reasoning_gear TEXT NOT NULL DEFAULT 'automatic',
    autonomy_domain_overrides_json TEXT NOT NULL DEFAULT '{}',
    compute_preference TEXT NOT NULL DEFAULT 'automatic',
    model_performance_preference TEXT NOT NULL DEFAULT 'balanced',
    background_cognition_enabled INTEGER NOT NULL DEFAULT 0 CHECK (background_cognition_enabled IN (0,1)),
    cpu_percent_ceiling INTEGER NOT NULL DEFAULT 85,
    ram_mb_ceiling INTEGER NOT NULL DEFAULT 16384,
    vram_mb_ceiling INTEGER NOT NULL DEFAULT 12288,
    max_background_jobs INTEGER NOT NULL DEFAULT 2,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_owner_status_updated ON memory_records(owner_user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_space_status ON memory_records(space_id, status);
CREATE INDEX IF NOT EXISTS idx_memory_scope_form ON memory_records(scope, form);
CREATE INDEX IF NOT EXISTS idx_memory_privacy ON memory_records(privacy);
CREATE INDEX IF NOT EXISTS idx_memory_sources_authority ON memory_sources(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_memory_receipts_actor_time ON memory_mutation_receipts(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_approvals_actor_expiry ON memory_action_approvals(actor_user_id, expires_at);

CREATE TRIGGER IF NOT EXISTS memory_projection_queue_after_insert
AFTER INSERT ON memory_records
BEGIN
    INSERT INTO memory_jobs (
        job_id, owner_user_id, job_kind, state, progress_current,
        progress_total, created_at, updated_at, result_code
    ) VALUES (
        'job_fts_' || lower(hex(randomblob(16))), NEW.owner_user_id,
        'fts_upsert:' || NEW.memory_id, 'pending', 0, 1,
        strftime('%Y-%m-%dT%H:%M:%SZ','now'),
        strftime('%Y-%m-%dT%H:%M:%SZ','now'), NULL
    );
END;

CREATE TRIGGER IF NOT EXISTS memory_projection_queue_after_update
AFTER UPDATE OF current_revision_id, title, privacy, status, owner_user_id,
                space_id, scope, form, valid_from, valid_until ON memory_records
BEGIN
    INSERT INTO memory_jobs (
        job_id, owner_user_id, job_kind, state, progress_current,
        progress_total, created_at, updated_at, result_code
    ) VALUES (
        'job_fts_' || lower(hex(randomblob(16))), NEW.owner_user_id,
        'fts_upsert:' || NEW.memory_id, 'pending', 0, 1,
        strftime('%Y-%m-%dT%H:%M:%SZ','now'),
        strftime('%Y-%m-%dT%H:%M:%SZ','now'), NULL
    );
END;

CREATE TRIGGER IF NOT EXISTS memory_projection_queue_after_delete
AFTER DELETE ON memory_records
BEGIN
    INSERT INTO memory_jobs (
        job_id, owner_user_id, job_kind, state, progress_current,
        progress_total, created_at, updated_at, result_code
    ) VALUES (
        'job_fts_' || lower(hex(randomblob(16))), OLD.owner_user_id,
        'fts_delete:' || OLD.memory_id, 'pending', 0, 1,
        strftime('%Y-%m-%dT%H:%M:%SZ','now'),
        strftime('%Y-%m-%dT%H:%M:%SZ','now'), NULL
    );
END;

-- Semantic vectors are a separate rebuildable projection job, never a second
-- canonical writer.  They intentionally share no transaction authority with
-- the external projection service: canonical commits succeed locally and the
-- deterministic queue is replayed when the optional profile is available.
CREATE TRIGGER IF NOT EXISTS memory_semantic_queue_after_insert
AFTER INSERT ON memory_records
BEGIN
    INSERT INTO memory_jobs (
        job_id, owner_user_id, job_kind, state, progress_current,
        progress_total, created_at, updated_at, result_code
    ) VALUES (
        'job_semantic_' || lower(hex(randomblob(16))), NEW.owner_user_id,
        'semantic_upsert:' || NEW.memory_id, 'pending', 0, 1,
        strftime('%Y-%m-%dT%H:%M:%SZ','now'),
        strftime('%Y-%m-%dT%H:%M:%SZ','now'), NULL
    );
END;

CREATE TRIGGER IF NOT EXISTS memory_semantic_queue_after_update
AFTER UPDATE OF current_revision_id, title, privacy, status, owner_user_id,
                space_id, scope, form, valid_from, valid_until ON memory_records
BEGIN
    INSERT INTO memory_jobs (
        job_id, owner_user_id, job_kind, state, progress_current,
        progress_total, created_at, updated_at, result_code
    ) VALUES (
        'job_semantic_' || lower(hex(randomblob(16))), NEW.owner_user_id,
        'semantic_upsert:' || NEW.memory_id, 'pending', 0, 1,
        strftime('%Y-%m-%dT%H:%M:%SZ','now'),
        strftime('%Y-%m-%dT%H:%M:%SZ','now'), NULL
    );
END;

CREATE TRIGGER IF NOT EXISTS memory_semantic_queue_after_delete
AFTER DELETE ON memory_records
BEGIN
    INSERT INTO memory_jobs (
        job_id, owner_user_id, job_kind, state, progress_current,
        progress_total, created_at, updated_at, result_code
    ) VALUES (
        'job_semantic_' || lower(hex(randomblob(16))), OLD.owner_user_id,
        'semantic_delete:' || OLD.memory_id, 'pending', 0, 1,
        strftime('%Y-%m-%dT%H:%M:%SZ','now'),
        strftime('%Y-%m-%dT%H:%M:%SZ','now'), NULL
    );
END;
"""


PART2E_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shared_space_invitations (
    invitation_id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    invited_user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('editor','contributor','reader')),
    state TEXT NOT NULL CHECK (state IN ('pending','accepted','declined','revoked')),
    invited_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    responded_at TEXT,
    revoked_at TEXT,
    FOREIGN KEY (space_id) REFERENCES shared_spaces(space_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_tier_events (
    event_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    from_tier TEXT NOT NULL,
    to_tier TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    explanation TEXT NOT NULL,
    automatic INTEGER NOT NULL CHECK (automatic IN (0,1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_access_metrics (
    memory_id TEXT PRIMARY KEY,
    retrieval_count INTEGER NOT NULL DEFAULT 0,
    last_retrieved_at TEXT,
    last_rehydrated_at TEXT,
    rehydration_count INTEGER NOT NULL DEFAULT 0,
    last_retrieval_latency_ms REAL,
    retrieval_latency_total_ms REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_objects (
    object_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    space_id TEXT,
    security_domain TEXT NOT NULL,
    privacy TEXT NOT NULL CHECK (privacy IN ('normal','private','sealed')),
    storage_digest TEXT NOT NULL,
    original_digest TEXT NOT NULL,
    original_size INTEGER NOT NULL CHECK (original_size >= 0),
    stored_size INTEGER NOT NULL CHECK (stored_size >= 0),
    compression TEXT NOT NULL,
    media_type TEXT NOT NULL,
    path_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    UNIQUE (security_domain, storage_digest)
);

CREATE TABLE IF NOT EXISTS memory_object_refs (
    object_ref_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    ref_type TEXT NOT NULL,
    ref_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (object_id, ref_type, ref_id, purpose),
    FOREIGN KEY (object_id) REFERENCES memory_objects(object_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_cold_revisions (
    revision_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    ciphertext_digest TEXT NOT NULL,
    archive_format TEXT NOT NULL,
    offloaded_at TEXT NOT NULL,
    last_verified_at TEXT NOT NULL,
    FOREIGN KEY (revision_id) REFERENCES memory_revisions(revision_id) ON DELETE CASCADE,
    FOREIGN KEY (memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE,
    FOREIGN KEY (object_id) REFERENCES memory_objects(object_id)
);

CREATE TABLE IF NOT EXISTS memory_graph_nodes (
    node_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    space_id TEXT,
    node_type TEXT NOT NULL,
    authority_id TEXT NOT NULL,
    privacy TEXT NOT NULL CHECK (privacy = 'normal'),
    status TEXT NOT NULL,
    provenance_digest TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (owner_user_id, node_type, authority_id)
);

CREATE TABLE IF NOT EXISTS memory_graph_edges (
    edge_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    space_id TEXT,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    inference_status TEXT NOT NULL,
    confidence REAL,
    provenance_digest TEXT NOT NULL,
    valid_from TEXT,
    valid_until TEXT,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (owner_user_id, source_node_id, target_node_id, relation_type),
    FOREIGN KEY (source_node_id) REFERENCES memory_graph_nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES memory_graph_nodes(node_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_truth_events (
    truth_event_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    related_memory_id TEXT,
    change_kind TEXT NOT NULL CHECK (change_kind IN (
        'correction','refinement','changed_reality','direct_contradiction','retraction'
    )),
    prior_revision_id TEXT,
    resulting_revision_id TEXT,
    rationale TEXT NOT NULL,
    observed_at TEXT,
    valid_from TEXT,
    valid_until TEXT,
    transaction_at TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE,
    FOREIGN KEY (related_memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memory_truth_events_record
ON memory_truth_events(owner_user_id, memory_id, transaction_at);

CREATE TABLE IF NOT EXISTS memory_archive_registry (
    archive_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    archive_kind TEXT NOT NULL CHECK (archive_kind IN ('managed_backup','portable_export')),
    format_version INTEGER NOT NULL,
    scope TEXT NOT NULL,
    path_token TEXT NOT NULL UNIQUE,
    encrypted INTEGER NOT NULL CHECK (encrypted IN (0,1)),
    size_bytes INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    record_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory_restore_plans (
    restore_plan_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    archive_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    state TEXT NOT NULL,
    additions INTEGER NOT NULL,
    conflicts INTEGER NOT NULL,
    staging_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    applied_at TEXT
);

-- A hard delete spans canonical SQLite, rebuildable projections, managed
-- archives, and the packed object store. This journal contains identifiers
-- and phase truth only: never memory content, plaintext hashes, ciphertext,
-- keys, titles, source labels, or recovery material. It lets startup finish
-- the physical SQLite scrub after an abrupt process exit without consuming a
-- second approval or pretending the purge completed.
CREATE TABLE IF NOT EXISTS memory_delete_operations (
    deletion_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL UNIQUE,
    owner_user_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    revision_ids_json TEXT NOT NULL,
    original_activation_tier TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN (
        'prepared','canonical_committed','physical_purged'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_tier_events_memory_time
    ON memory_tier_events(memory_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_objects_owner_domain
    ON memory_objects(owner_user_id, security_domain);
CREATE INDEX IF NOT EXISTS idx_memory_object_refs_ref
    ON memory_object_refs(ref_type, ref_id);
CREATE INDEX IF NOT EXISTS idx_memory_graph_nodes_owner_authority
    ON memory_graph_nodes(owner_user_id, authority_id);
CREATE INDEX IF NOT EXISTS idx_memory_graph_edges_owner_source
    ON memory_graph_edges(owner_user_id, source_node_id);
CREATE INDEX IF NOT EXISTS idx_memory_archive_owner_time
    ON memory_archive_registry(owner_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shared_space_invitations_recipient_state
    ON shared_space_invitations(invited_user_id, state, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shared_space_invitations_space_state
    ON shared_space_invitations(space_id, state, created_at DESC);
"""


class MemoryRepositoryError(RuntimeError):
    """Canonical repository operation failed safely."""


class MemoryRepository:
    def __init__(
        self,
        *,
        paths: ElysiaPaths | None = None,
        database_path: Path | None = None,
    ) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.database_path = database_path or self.paths.memory_database_path

    @property
    def migration_required_marker(self) -> Path:
        return self.paths.memory_checkpoints_dir / "canonical-migration-required.json"

    @property
    def storage_pressure_marker(self) -> Path:
        return self.paths.memory_checkpoints_dir / "storage-pressure-write-pause.json"

    def mark_migration_required(self, reason_code: str = "legacy_input_discovered") -> None:
        self.paths.memory_checkpoints_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        marker = self.migration_required_marker
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "contract": "elysia-memory-maintenance-1",
                    "state": "migration_required",
                    "reason_code": reason_code,
                    "raw_paths_exposed": False,
                    "private_content_recorded": False,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, marker)

    def clear_migration_required(self) -> None:
        try:
            self.migration_required_marker.unlink()
        except FileNotFoundError:
            pass

    def assert_content_writes_ready(self) -> None:
        if (
            self.database_path == self.paths.memory_database_path
            and self.migration_required_marker.is_file()
        ):
            raise MemoryRepositoryError(
                "Canonical memory writes are paused until the verified migration completes."
            )

    def set_storage_pressure_pause(self, paused: bool) -> None:
        marker = self.storage_pressure_marker
        if not paused:
            marker.unlink(missing_ok=True)
            return
        marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "contract": "elysia-memory-homeostasis-1",
                    "state": "nonessential_writes_paused",
                    "reason_code": "emergency_free_space_reserve",
                    "content_included": False,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, marker)

    def assert_nonessential_writes_ready(self) -> None:
        if (
            self.database_path == self.paths.memory_database_path
            and self.storage_pressure_marker.is_file()
        ):
            raise MemoryRepositoryError(
                "Nonessential memory writes are paused to preserve the configured free-space reserve."
            )

    def _pre_upgrade_snapshot(self) -> tuple[Path | None, int]:
        if not self.database_path.is_file() or self.database_path.is_symlink():
            return None, 0
        try:
            with sqlite3.connect(
                f"file:{self.database_path.as_posix()}?mode=ro", uri=True, timeout=2.0
            ) as conn:
                has_records = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_records'"
                ).fetchone()
                has_migrations = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                ).fetchone()
                old_version = int(
                    conn.execute(
                        "SELECT COALESCE(MAX(schema_version),0) FROM schema_migrations"
                    ).fetchone()[0]
                ) if has_migrations else 0
        except sqlite3.Error as exc:
            raise MemoryRepositoryError(
                "The existing Memory Fabric cannot be validated for schema upgrade."
            ) from exc
        if not has_records or old_version >= SCHEMA_VERSION:
            return None, old_version
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self.paths.memory_backup_dir / (
            f"pre-schema-v{old_version}-to-v{SCHEMA_VERSION}-{stamp}.sqlite"
        )
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source = sqlite3.connect(self.database_path)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        self._private_file(destination)
        return destination, old_version

    def _rollback_schema_upgrade(self, snapshot: Path, old_version: int) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        self.paths.memory_checkpoints_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.database_path}{suffix}")
            if sidecar.exists() and not sidecar.is_symlink():
                os.replace(
                    sidecar,
                    self.paths.memory_checkpoints_dir
                    / f"failed-schema-v{old_version}{suffix}-{stamp}",
                )
        failed = self.paths.memory_checkpoints_dir / (
            f"failed-schema-v{old_version}-to-v{SCHEMA_VERSION}-{stamp}.sqlite"
        )
        if self.database_path.exists() and not self.database_path.is_symlink():
            os.replace(self.database_path, failed)
            self._private_file(failed)
        temporary = self.database_path.with_suffix(".schema-rollback")
        source = sqlite3.connect(snapshot)
        target = sqlite3.connect(temporary)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        self._private_file(temporary)
        os.replace(temporary, self.database_path)
        self._private_file(self.database_path)

    def initialize(self) -> None:
        ensure_memory_directories(self.paths)
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        snapshot, old_version = self._pre_upgrade_snapshot()
        rollback_metadata = {
            "from_schema_version": old_version,
            "backup_created": snapshot is not None,
            "backup_path_exposed": False,
            "automatic_rollback": True,
        }
        try:
            self._initialize_unchecked(rollback_metadata)
        except Exception:
            if snapshot is not None:
                self._rollback_schema_upgrade(snapshot, old_version)
            raise

    def _initialize_unchecked(self, rollback_metadata: dict[str, object]) -> None:
        ensure_memory_directories(self.paths)
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.executescript(PART2E_SCHEMA_SQL)
            existing_record_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(memory_records)").fetchall()
            }
            for name, declaration in {
                "automatic_recall_suppressed": "INTEGER NOT NULL DEFAULT 0 CHECK (automatic_recall_suppressed IN (0,1))",
                "expires_at": "TEXT",
                "retention_hold": "INTEGER NOT NULL DEFAULT 0 CHECK (retention_hold IN (0,1))",
            }.items():
                if name not in existing_record_columns:
                    conn.execute(f"ALTER TABLE memory_records ADD COLUMN {name} {declaration}")
            existing_revision_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(memory_revisions)").fetchall()
            }
            if "digest_format" not in existing_revision_columns:
                conn.execute(
                    "ALTER TABLE memory_revisions ADD COLUMN digest_format "
                    "TEXT NOT NULL DEFAULT 'legacy-sha256-v1'"
                )
            existing_job_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(memory_jobs)").fetchall()
            }
            for name, declaration in {
                "priority": "TEXT NOT NULL DEFAULT 'background'",
                "checkpoint_json": "TEXT NOT NULL DEFAULT '{}'",
                "cancel_requested": "INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0,1))",
                "attempt_count": "INTEGER NOT NULL DEFAULT 0",
                "error_code": "TEXT",
                "started_at": "TEXT",
                "completed_at": "TEXT",
            }.items():
                if name not in existing_job_columns:
                    conn.execute(f"ALTER TABLE memory_jobs ADD COLUMN {name} {declaration}")
            existing_candidate_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(memory_candidates)").fetchall()
            }
            for name, declaration in {
                "deferred_until": "TEXT",
                "feedback_code": "TEXT",
                "proposed_wording": "TEXT",
                "evidence_summary": "TEXT",
            }.items():
                if name not in existing_candidate_columns:
                    conn.execute(f"ALTER TABLE memory_candidates ADD COLUMN {name} {declaration}")
            existing_access_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(memory_access_metrics)").fetchall()
            }
            for name, declaration in {
                "last_retrieval_latency_ms": "REAL",
                "retrieval_latency_total_ms": "REAL NOT NULL DEFAULT 0",
            }.items():
                if name not in existing_access_columns:
                    conn.execute(
                        f"ALTER TABLE memory_access_metrics ADD COLUMN {name} {declaration}"
                    )
            existing_settings_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(memory_settings)").fetchall()
            }
            additive_settings_columns = {
                "retrieval_breadth": "TEXT NOT NULL DEFAULT 'balanced' CHECK (retrieval_breadth IN ('focused','balanced','broad'))",
                "research_initiative": "TEXT NOT NULL DEFAULT 'balanced' CHECK (research_initiative IN ('manual','balanced','proactive'))",
                "safe_search_level": "TEXT NOT NULL DEFAULT 'strict' CHECK (safe_search_level IN ('strict','moderate','off'))",
                "preferred_reasoning_gear": "TEXT NOT NULL DEFAULT 'automatic'",
                "autonomy_domain_overrides_json": "TEXT NOT NULL DEFAULT '{}'",
                "compute_preference": "TEXT NOT NULL DEFAULT 'automatic'",
                "model_performance_preference": "TEXT NOT NULL DEFAULT 'balanced'",
                "background_cognition_enabled": "INTEGER NOT NULL DEFAULT 0 CHECK (background_cognition_enabled IN (0,1))",
                "cpu_percent_ceiling": "INTEGER NOT NULL DEFAULT 85",
                "ram_mb_ceiling": "INTEGER NOT NULL DEFAULT 16384",
                "vram_mb_ceiling": "INTEGER NOT NULL DEFAULT 12288",
                "max_background_jobs": "INTEGER NOT NULL DEFAULT 2",
                "memory_storage_profile": "TEXT NOT NULL DEFAULT 'balanced'",
                "storage_budget_mode": "TEXT NOT NULL DEFAULT 'absolute_mb'",
                "storage_budget_value": "REAL NOT NULL DEFAULT 8192",
                "emergency_free_space_reserve_mb": "INTEGER NOT NULL DEFAULT 2048",
                "consolidation_enabled": "INTEGER NOT NULL DEFAULT 1 CHECK (consolidation_enabled IN (0,1))",
                "consolidation_schedule": "TEXT NOT NULL DEFAULT 'daily'",
                "consolidation_resource_percent": "INTEGER NOT NULL DEFAULT 25",
                "backup_enabled": "INTEGER NOT NULL DEFAULT 0 CHECK (backup_enabled IN (0,1))",
                "backup_schedule": "TEXT NOT NULL DEFAULT 'weekly'",
                "backup_retention_count": "INTEGER NOT NULL DEFAULT 3",
                "retention_policy": "TEXT NOT NULL DEFAULT 'balanced'",
                "hot_retention_days": "INTEGER NOT NULL DEFAULT 14",
                "cold_after_days": "INTEGER NOT NULL DEFAULT 180",
                "prospective_notifications_enabled": "INTEGER NOT NULL DEFAULT 1 CHECK (prospective_notifications_enabled IN (0,1))",
            }
            for name, declaration in additive_settings_columns.items():
                if name not in existing_settings_columns:
                    conn.execute(f"ALTER TABLE memory_settings ADD COLUMN {name} {declaration}")
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (
                    schema_version, migration_name, applied_at, source_hash,
                    result, rollback_metadata_json
                ) VALUES (?, ?, ?, ?, 'applied', ?)
                """,
                (
                    SCHEMA_VERSION, SCHEMA_NAME, utc_now(), self.schema_digest(),
                    json.dumps(rollback_metadata, sort_keys=True),
                ),
            )
        self._private_file(self.database_path)
        for suffix in ("-wal", "-shm"):
            candidate = Path(f"{self.database_path}{suffix}")
            if candidate.exists():
                self._private_file(candidate)

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        except sqlite3.Error as exc:
            raise MemoryRepositoryError("The canonical Memory Fabric database is unavailable.") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        # SQLite's secure-delete mode overwrites deleted cells instead of
        # leaving plaintext in freelist pages. Hard deletion also checkpoints
        # and compacts the WAL through ``secure_purge_deleted_content`` below.
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        guard = None
        if self.database_path == self.paths.memory_database_path:
            self.paths.memory_lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            guard_path = self.paths.memory_lock_dir / "canonical-migration.lock"
            guard = guard_path.open("a+b")
            try:
                guard_path.chmod(0o600)
            except OSError:
                pass
            try:
                fcntl.flock(guard.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                guard.close()
                raise MemoryRepositoryError(
                    "Canonical memory writes are paused while migration maintenance is active."
                ) from exc
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()
            if guard is not None:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
                guard.close()
            if self.database_path.exists():
                self._private_file(self.database_path)

    def schema_digest(self) -> str:
        import hashlib

        return hashlib.sha256((SCHEMA_SQL + PART2E_SCHEMA_SQL).encode("utf-8")).hexdigest()

    def health(self) -> dict[str, object]:
        self.initialize()
        with self.connect() as conn:
            quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            foreign_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
            version_row = conn.execute("SELECT MAX(schema_version) FROM schema_migrations").fetchone()
            count_row = conn.execute("SELECT COUNT(*) FROM memory_records").fetchone()
            journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
        return {
            "state": "ready" if quick == "ok" and not foreign_rows else "degraded",
            "schema_version": int(version_row[0] or 0),
            "record_count": int(count_row[0] or 0),
            "foreign_keys_enabled": True,
            "foreign_key_violations": len(foreign_rows),
            "quick_check": quick,
            "journal_mode": journal_mode,
            "authority": "XDG local SQLite Memory Fabric",
            "raw_path_exposed": False,
            "single_writer": True,
        }

    def backup(self, destination: Path) -> None:
        self.initialize()
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source = self.connect()
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        self._private_file(destination)

    def backup_status(self) -> dict[str, object]:
        """Return sanitized backup truth without exposing names, paths, or bodies."""
        if not self.paths.memory_backup_dir.is_dir():
            return {
                "backup_count": 0,
                "last_backup_at_utc": None,
                "latest_integrity": "not_available",
                "latest_private_permissions": True,
                "raw_path_exposed": False,
            }
        backups = [
            candidate
            for candidate in self.paths.memory_backup_dir.glob("*.sqlite")
            if candidate.is_file() and not candidate.is_symlink()
        ]
        if not backups:
            return {
                "backup_count": 0,
                "last_backup_at_utc": None,
                "latest_integrity": "not_available",
                "latest_private_permissions": True,
                "raw_path_exposed": False,
            }
        latest = max(backups, key=lambda candidate: candidate.stat().st_mtime_ns)
        integrity = "failed"
        try:
            with sqlite3.connect(
                f"file:{latest.as_posix()}?mode=ro", uri=True, timeout=1.0
            ) as conn:
                row = conn.execute("PRAGMA quick_check").fetchone()
            if row and str(row[0]).lower() == "ok":
                integrity = "verified"
        except (OSError, sqlite3.Error):
            integrity = "failed"
        timestamp = datetime.fromtimestamp(latest.stat().st_mtime, UTC)
        return {
            "backup_count": len(backups),
            "last_backup_at_utc": timestamp.replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"
            ),
            "latest_integrity": integrity,
            "latest_private_permissions": latest.stat().st_mode & 0o077 == 0,
            "raw_path_exposed": False,
        }

    def secure_purge_deleted_content(self) -> dict[str, object]:
        """Checkpoint and compact after an approved canonical hard delete.

        ``secure_delete=ON`` clears deleted cells at mutation time. Truncating
        the WAL removes prior frames and VACUUM rebuilds the remaining database
        without freelist pages. A busy checkpoint is reported as a failure so
        callers never falsely claim that physical purge completed.
        """

        with self.connect() as conn:
            before = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if before is None or int(before[0]) != 0:
                raise MemoryRepositoryError(
                    "Canonical hard delete committed, but physical purge is waiting for active readers."
                )
            conn.execute("VACUUM")
            after = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if after is None or int(after[0]) != 0:
                raise MemoryRepositoryError(
                    "Canonical hard delete committed, but final WAL purge is waiting for active readers."
                )
        self._private_file(self.database_path)
        return {
            "secure_delete": True,
            "freelist_compacted": True,
            "wal_truncated": True,
        }

    def default_settings(self, owner_user_id: str) -> None:
        now = utc_now()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_settings (
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
                ) VALUES (?, 1, 'core_local', 'normal', 'review_personal_inference', 3,
                          0, 'balanced', 'balanced', 'strict', 'automatic', '{}',
                          'automatic', 'balanced', 0, 85, 16384, 12288, 2,
                          'balanced', 'absolute_mb', 8192, 2048, 1, 'daily', 25,
                          0, 'weekly', 3, 'balanced', 14, 180, 1, ?)
                """,
                (owner_user_id, now),
            )

    @staticmethod
    def _private_file(path: Path) -> None:
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def mutation_receipt_row(
    *,
    actor_user_id: str,
    action: str,
    memory_id: str | None,
    request_id: str | None,
    old_state_digest: str | None,
    new_state_digest: str | None,
    scope: str | None,
    form: str | None,
    privacy: str | None,
    approval_id: str | None = None,
    completion_status: str = "applied",
    reason_code: str | None = None,
) -> tuple[object, ...]:
    return (
        new_id("memmut"),
        actor_user_id,
        request_id,
        memory_id,
        action,
        old_state_digest,
        new_state_digest,
        scope,
        form,
        privacy,
        approval_id,
        "queued_for_rebuild",
        completion_status,
        reason_code,
        utc_now(),
    )


MUTATION_RECEIPT_INSERT = """
INSERT INTO memory_mutation_receipts (
    mutation_id, actor_user_id, request_id, memory_id, action,
    old_state_digest, new_state_digest, scope, form, privacy,
    approval_id, projection_invalidation_state, completion_status,
    reason_code, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


__all__ = (
    "MUTATION_RECEIPT_INSERT",
    "MemoryRepository",
    "MemoryRepositoryError",
    "SCHEMA_NAME",
    "SCHEMA_SQL",
    "SCHEMA_VERSION",
    "mutation_receipt_row",
    "utc_now",
)
