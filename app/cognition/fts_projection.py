"""Rebuildable SQLite FTS5 projection for normal canonical Memory.

Private Memory is deliberately searched only in authenticated process memory;
its decrypted text is never persisted in this plaintext derived index. Sealed
Memory is excluded from both persistent and ordinary ephemeral retrieval.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import re
import sqlite3
from time import perf_counter
from typing import Any

from app.install.paths import ElysiaPaths, ensure_memory_directories, resolve_elysia_paths
from app.memory.canonical_models import MemoryPrivacy, MemoryQuery
from app.memory.canonical_repository import MemoryRepository, utc_now
from app.memory.fabric_service import MemoryFabricService


PROJECTION_VERSION = "fts5-normal-memory-v1"
TOKENIZER_VERSION = "unicode61-remove_diacritics2-porter-v1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projection_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_fts_meta (
    candidate_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    space_id TEXT,
    scope TEXT NOT NULL,
    form TEXT NOT NULL,
    privacy TEXT NOT NULL,
    status TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    project_id TEXT,
    conversation_id TEXT,
    observed_at TEXT,
    valid_from TEXT,
    valid_until TEXT,
    importance REAL NOT NULL,
    confidence REAL,
    user_confirmed INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    candidate_id UNINDEXED,
    title,
    body,
    why_stored,
    tokenize='porter unicode61 remove_diacritics 2'
);
CREATE INDEX IF NOT EXISTS idx_fts_meta_owner_status
ON memory_fts_meta(owner_user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_fts_meta_space_status
ON memory_fts_meta(space_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_fts_meta_scope_form
ON memory_fts_meta(scope, form);
"""

_WORD = re.compile(r"[\w'-]+", re.UNICODE)


class FtsProjectionError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _safe_match_query(text: str) -> str:
    """Compile bounded user text into safe FTS syntax with phrase/prefix support."""
    raw = " ".join(str(text or "").split())[:1000]
    phrases = [match.group(1) for match in re.finditer(r'"([^"\n]{1,240})"', raw)]
    outside = re.sub(r'"[^"\n]{1,240}"', " ", raw)
    terms = _WORD.findall(outside)
    parts = [f'"{" ".join(_WORD.findall(value))}"' for value in phrases if _WORD.findall(value)]
    for term in terms[:48]:
        escaped = term.replace('"', '""')
        parts.append(f'"{escaped}"*' if raw.find(term + "*") >= 0 else f'"{escaped}"')
    # Natural recall should not disappear merely because a conversational
    # query contains framing words ("recall", "what did we decide", etc.).
    # Explicit quoted phrases remain atomic; otherwise retrieve the bounded
    # union and let the deterministic ranker reward broader overlap.
    return " OR ".join(parts)


def _token_overlap(query: str, text: str) -> float:
    requested = {item.casefold() for item in _WORD.findall(query)}
    if not requested:
        return 0.0
    present = {item.casefold() for item in _WORD.findall(text)}
    return len(requested & present) / len(requested)


class FtsMemoryProjection:
    def __init__(
        self,
        *,
        paths: ElysiaPaths | None = None,
        database_path: Path | None = None,
        repository: MemoryRepository | None = None,
        fabric: MemoryFabricService | None = None,
    ) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.database_path = database_path or self.paths.memory_fts_database_path
        self.repository = repository or MemoryRepository(paths=self.paths)
        self.fabric = fabric or MemoryFabricService(repository=self.repository)

    def _current_space_ids(
        self, principal: Any, requested: list[str] | None = None
    ) -> list[str]:
        requested_set = (
            {str(value) for value in requested if str(value)}
            if requested is not None
            else None
        )
        with self.repository.connect() as canonical:
            rows = canonical.execute(
                "SELECT space_id FROM shared_space_members WHERE user_id=? ORDER BY space_id",
                (principal.user_id,),
            ).fetchall()
        current = [str(row["space_id"]) for row in rows]
        if requested_set is None:
            return current
        return [space_id for space_id in current if space_id in requested_set]

    def _authorization_signature(self, principal: Any) -> str:
        spaces = self._current_space_ids(principal)
        payload = "\0".join([str(principal.user_id), *spaces]).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def connect(self) -> sqlite3.Connection:
        ensure_memory_directories(self.paths)
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.database_path.parent.chmod(0o700)
        except OSError:
            pass
        conn = sqlite3.connect(self.database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO projection_meta(key,value) VALUES('projection_version',?)",
            (PROJECTION_VERSION,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO projection_meta(key,value) VALUES('tokenizer_version',?)",
            (TOKENIZER_VERSION,),
        )
        conn.commit()
        _private(self.database_path)
        return conn

    @staticmethod
    def _linked_id(record: Any, target_type: str) -> str | None:
        for relation in list(getattr(record, "relations", []) or []):
            if str(relation.get("target_type")) == target_type:
                return str(relation.get("target_id") or "") or None
        return None

    def _delete(self, conn: sqlite3.Connection, memory_id: str) -> None:
        row = conn.execute(
            "SELECT rowid FROM memory_fts WHERE candidate_id = ?", (memory_id,)
        ).fetchone()
        if row is not None:
            conn.execute("DELETE FROM memory_fts WHERE rowid = ?", (row[0],))
        conn.execute("DELETE FROM memory_fts_meta WHERE candidate_id = ?", (memory_id,))

    def upsert_record(self, conn: sqlite3.Connection, record: Any) -> str:
        memory_id = str(record.memory_id)
        self._delete(conn, memory_id)
        if str(getattr(record.privacy, "value", record.privacy)) != "normal":
            return "excluded_non_normal"
        status = str(getattr(record.status, "value", record.status))
        if status not in {"active", "working"}:
            return f"excluded_status_{status}"
        form = str(getattr(record.form, "value", record.form))
        if form == "audit":
            return "excluded_audit_authority"
        if form == "prospective" and str(
            (getattr(record, "form_data", {}) or {}).get("state") or "pending"
        ) != "pending":
            return "excluded_resolved_prospective"
        tier = str(getattr(record.activation_tier, "value", record.activation_tier))
        if tier in {"cold", "archived"}:
            return f"excluded_tier_{tier}"
        if bool(getattr(record, "automatic_recall_suppressed", False)):
            return "excluded_automatic_recall_suppressed"
        if record.valid_until and str(record.valid_until) <= utc_now():
            return "excluded_expired_validity"
        conn.execute(
            """
            INSERT INTO memory_fts_meta (
                candidate_id, owner_user_id, space_id, scope, form, privacy,
                status, source_type, source_id, project_id, conversation_id,
                observed_at, valid_from, valid_until, importance, confidence,
                user_confirmed, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                memory_id,
                record.owner_user_id,
                record.space_id,
                str(getattr(record.scope, "value", record.scope)),
                form,
                "normal",
                status,
                "memory",
                memory_id,
                self._linked_id(record, "project"),
                self._linked_id(record, "conversation"),
                record.observed_at,
                record.valid_from,
                record.valid_until,
                float(record.importance),
                record.confidence,
                int(record.user_confirmed),
                record.updated_at,
            ),
        )
        conn.execute(
            "INSERT INTO memory_fts(candidate_id,title,body,why_stored) VALUES(?,?,?,?)",
            (memory_id, record.title, record.body or "", record.why_stored or ""),
        )
        return "indexed"

    def process_pending(self, principal: Any, *, limit: int = 500) -> dict[str, Any]:
        self.repository.initialize()
        processed = 0
        failed = 0
        with self.repository.connect() as canonical:
            jobs = canonical.execute(
                """
                SELECT job_id, job_kind FROM memory_jobs
                WHERE state IN ('pending','failed')
                  AND (job_kind LIKE 'fts_upsert:%' OR job_kind LIKE 'fts_delete:%')
                  AND (
                    job_kind LIKE 'fts_delete:%'
                    OR EXISTS (
                        SELECT 1 FROM memory_records r
                        WHERE r.memory_id = substr(memory_jobs.job_kind, 12)
                          AND (
                            (r.space_id IS NULL AND r.owner_user_id = ?)
                            OR EXISTS (
                                SELECT 1 FROM shared_space_members sm
                                WHERE sm.space_id = r.space_id AND sm.user_id = ?
                            )
                          )
                    )
                  )
                ORDER BY created_at, job_id LIMIT ?
                """,
                (principal.user_id, principal.user_id, limit),
            ).fetchall()
        projection = self.connect()
        try:
            for job in jobs:
                job_id = str(job["job_id"])
                kind, memory_id = str(job["job_kind"]).split(":", 1)
                result_code = "deleted"
                try:
                    if kind == "fts_delete":
                        self._delete(projection, memory_id)
                    else:
                        try:
                            record = self.fabric.get(principal, memory_id)
                        except Exception:
                            self._delete(projection, memory_id)
                            result_code = "missing_or_inaccessible"
                        else:
                            result_code = self.upsert_record(projection, record)
                    projection.commit()
                    with self.repository.transaction() as canonical:
                        canonical.execute(
                            "UPDATE memory_jobs SET state='completed', progress_current=1, updated_at=?, result_code=? WHERE job_id=?",
                            (utc_now(), result_code, job_id),
                        )
                    processed += 1
                except Exception:
                    projection.rollback()
                    with self.repository.transaction() as canonical:
                        canonical.execute(
                            "UPDATE memory_jobs SET state='failed', updated_at=?, result_code='projection_apply_failed' WHERE job_id=?",
                            (utc_now(), job_id),
                        )
                    failed += 1
        finally:
            projection.close()
        return {"processed": processed, "failed": failed}

    def purge_record(self, memory_id: str) -> dict[str, Any]:
        """Physically invalidate one derived record without touching canonical truth.

        This is the privacy/hard-delete fast path. The canonical trigger remains
        the authoritative idempotent job; this eager purge closes the at-rest
        window before the next ordinary retrieval processes that queue.
        """
        if not self.database_path.exists():
            return {
                "state": "absent",
                "memory_id": memory_id,
                "plaintext_projection_present": False,
                "canonical_memory_mutated": False,
            }
        conn = self.connect()
        try:
            self._delete(conn, memory_id)
            conn.commit()
            checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is None or int(checkpoint[0]) != 0:
                raise FtsProjectionError("The lexical projection WAL is busy.")
            conn.execute("VACUUM")
            final = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if final is None or int(final[0]) != 0:
                raise FtsProjectionError("The lexical projection WAL did not truncate.")
        finally:
            conn.close()
        _private(self.database_path)
        return {
            "state": "purged",
            "memory_id": memory_id,
            "plaintext_projection_present": False,
            "secure_delete": True,
            "wal_truncated": True,
            "freelist_compacted": True,
            "canonical_memory_mutated": False,
        }

    def repair_and_rebuild(self, principal: Any) -> dict[str, Any]:
        """Rebuild, quarantining a corrupt derived database when necessary."""
        try:
            return self.rebuild(principal)
        except (sqlite3.Error, FtsProjectionError):
            quarantine = self.paths.memory_fts_rebuild_dir
            quarantine.mkdir(mode=0o700, parents=True, exist_ok=True)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            moved: list[str] = []
            for suffix in ("", "-wal", "-shm"):
                source = Path(str(self.database_path) + suffix)
                if not source.exists() or source.is_symlink():
                    continue
                destination = quarantine / f"corrupt-{timestamp}-{self.database_path.name}{suffix}"
                source.replace(destination)
                _private(destination)
                moved.append(suffix or "database")
            rebuilt = self.rebuild(principal)
            rebuilt.update(
                {
                    "repair_performed": True,
                    "quarantined_components": moved,
                    "canonical_memory_mutated": False,
                }
            )
            return rebuilt

    def privacy_purge_record(self, principal: Any, memory_id: str) -> dict[str, Any]:
        """Guarantee stale plaintext removal for privacy transitions/deletion.

        A corrupt derived cache has no preservation authority. If an exact-row
        purge cannot be proved, discard every projection component and rebuild
        from canonical truth, which already excludes the private/deleted row.
        """
        try:
            return self.purge_record(memory_id)
        except Exception:
            discarded: list[str] = []
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(str(self.database_path) + suffix)
                if candidate.exists() and not candidate.is_symlink():
                    candidate.unlink()
                    discarded.append(suffix or "database")
            rebuilt = self.rebuild(principal)
            return {
                **rebuilt,
                "state": "discarded_and_rebuilt",
                "memory_id": memory_id,
                "discarded_components": discarded,
                "plaintext_projection_present": False,
                "canonical_memory_mutated": False,
            }

    def rebuild(self, principal: Any) -> dict[str, Any]:
        started = perf_counter()
        current_spaces = self._current_space_ids(principal)
        records: list[Any] = []
        offset = 0
        while True:
            page, total = self.fabric.list(
                principal,
                MemoryQuery(
                    privacy=MemoryPrivacy.NORMAL,
                    include_archived=True,
                    limit=200,
                    offset=offset,
                ),
            )
            records.extend(page)
            offset += len(page)
            if not page or offset >= total:
                break
        conn = self.connect()
        indexed = 0
        try:
            clauses = ["(owner_user_id = ? AND space_id IS NULL)"]
            values: list[Any] = [principal.user_id]
            if current_spaces:
                placeholders = ",".join("?" for _ in current_spaces)
                clauses.append(f"space_id IN ({placeholders})")
                values.extend(current_spaces)
            replace_rows = conn.execute(
                f"SELECT candidate_id FROM memory_fts_meta WHERE {' OR '.join(clauses)}",
                values,
            ).fetchall()
            for row in replace_rows:
                self._delete(conn, str(row["candidate_id"]))
            for record in records:
                indexed += self.upsert_record(conn, record) == "indexed"
            conn.execute(
                "INSERT OR REPLACE INTO projection_meta(key,value) VALUES(?,?)",
                (f"owner_rebuilt:{principal.user_id}", self._authorization_signature(principal)),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "state": "ready",
            "indexed": int(indexed),
            "duration_ms": round((perf_counter() - started) * 1000, 3),
            "projection_version": PROJECTION_VERSION,
        }

    def ensure_ready(self, principal: Any) -> dict[str, Any]:
        conn = self.connect()
        try:
            rebuilt = conn.execute(
                "SELECT value FROM projection_meta WHERE key = ?",
                (f"owner_rebuilt:{principal.user_id}",),
            ).fetchone()
        finally:
            conn.close()
        if rebuilt is None or str(rebuilt["value"]) != self._authorization_signature(principal):
            result = self.rebuild(principal)
        else:
            result = {"state": "ready", "indexed": None, "projection_version": PROJECTION_VERSION}
        result["queue"] = self.process_pending(principal)
        return result

    def search(
        self,
        principal: Any,
        text: str,
        *,
        scope: str | None = None,
        form: str | None = None,
        status: str | None = None,
        space_id: str | None = None,
        project_id: str | None = None,
        conversation_id: str | None = None,
        space_ids: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.ensure_ready(principal)
        match = _safe_match_query(text)
        if not match:
            return []
        clauses = ["memory_fts MATCH ?", "m.status IN ('active','working')"]
        values: list[Any] = [match]
        authorized_spaces = self._current_space_ids(principal, list(space_ids or []))
        if authorized_spaces:
            placeholders = ",".join("?" for _ in authorized_spaces)
            clauses.append(
                f"((m.owner_user_id = ? AND m.space_id IS NULL) OR m.space_id IN ({placeholders}))"
            )
            values.append(principal.user_id)
            values.extend(authorized_spaces)
        else:
            clauses.append("m.owner_user_id = ? AND m.space_id IS NULL")
            values.append(principal.user_id)
        for column, value in (
            ("scope", scope),
            ("form", form),
            ("status", status),
            ("space_id", space_id),
            ("project_id", project_id),
            ("conversation_id", conversation_id),
        ):
            if value:
                clauses.append(f"m.{column} = ?")
                values.append(value)
        now = _now()
        clauses.extend([
            "(m.valid_from IS NULL OR m.valid_from <= ?)",
            "(m.valid_until IS NULL OR m.valid_until > ?)",
        ])
        values.extend([now, now, max(1, min(limit, 100_000)), max(0, offset)])
        sql = f"""
            SELECT m.*, f.title, f.body, f.why_stored,
                   bm25(memory_fts, 0.0, 2.0, 1.0, 0.4) AS raw_rank
            FROM memory_fts f
            JOIN memory_fts_meta m ON m.candidate_id = f.candidate_id
            WHERE {' AND '.join(clauses)}
            ORDER BY raw_rank ASC, m.importance DESC, m.updated_at DESC,
                     m.candidate_id ASC
            LIMIT ? OFFSET ?
        """
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(sql, values).fetchall()]
        except sqlite3.OperationalError as exc:
            raise FtsProjectionError("The lexical projection query was rejected safely.") from exc
        finally:
            conn.close()

    def search_private_ephemeral(
        self,
        principal: Any,
        text: str,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        scope: str | None = None,
        form: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Authenticated decrypt-and-rank path that persists no private plaintext."""
        records: list[Any] = []
        page_offset = 0
        while True:
            page, total = self.fabric.list(
                principal,
                MemoryQuery(
                    privacy=MemoryPrivacy.PRIVATE,
                    scope=scope,
                    form=form,
                    status=status,
                    include_archived=False,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    limit=200,
                    offset=page_offset,
                ),
            )
            records.extend(page)
            page_offset += len(page)
            if not page or page_offset >= total:
                break
        ranked = []
        for record in records:
            content = "\n".join((record.title, record.body or "", record.why_stored or ""))
            score = _token_overlap(text, content)
            if score <= 0:
                continue
            ranked.append(
                {
                    "candidate_id": record.memory_id,
                    "owner_user_id": record.owner_user_id,
                    "space_id": record.space_id,
                    "scope": str(getattr(record.scope, "value", record.scope)),
                    "form": str(getattr(record.form, "value", record.form)),
                    "privacy": "private",
                    "status": str(getattr(record.status, "value", record.status)),
                    "source_type": "memory",
                    "source_id": record.memory_id,
                    "project_id": self._linked_id(record, "project"),
                    "conversation_id": self._linked_id(record, "conversation"),
                    "observed_at": record.observed_at,
                    "valid_from": record.valid_from,
                    "valid_until": record.valid_until,
                    "importance": record.importance,
                    "pinned": bool(record.pinned),
                    "confidence": record.confidence,
                    "user_confirmed": int(record.user_confirmed),
                    "updated_at": record.updated_at,
                    "title": record.title,
                    "body": record.body or "",
                    "why_stored": record.why_stored or "",
                    "raw_rank": -score,
                    "ephemeral_private": True,
                }
            )
        ranked.sort(key=lambda row: (row["raw_rank"], -float(row["importance"]), row["candidate_id"]))
        bounded_offset = max(0, offset)
        bounded_limit = max(1, min(limit, 100_000))
        return ranked[bounded_offset : bounded_offset + bounded_limit]

    def count_search(
        self,
        principal: Any,
        text: str,
        *,
        scope: str | None = None,
        form: str | None = None,
        status: str | None = None,
        space_id: str | None = None,
        project_id: str | None = None,
        conversation_id: str | None = None,
        space_ids: list[str] | None = None,
    ) -> int:
        """Count authorized normal-memory matches without materializing plaintext."""
        self.ensure_ready(principal)
        match = _safe_match_query(text)
        if not match:
            return 0
        clauses = ["memory_fts MATCH ?", "m.status IN ('active','working')"]
        values: list[Any] = [match]
        authorized_spaces = self._current_space_ids(principal, list(space_ids or []))
        if authorized_spaces:
            placeholders = ",".join("?" for _ in authorized_spaces)
            clauses.append(
                f"((m.owner_user_id = ? AND m.space_id IS NULL) OR m.space_id IN ({placeholders}))"
            )
            values.append(principal.user_id)
            values.extend(authorized_spaces)
        else:
            clauses.append("m.owner_user_id = ? AND m.space_id IS NULL")
            values.append(principal.user_id)
        for column, value in (
            ("scope", scope),
            ("form", form),
            ("status", status),
            ("space_id", space_id),
            ("project_id", project_id),
            ("conversation_id", conversation_id),
        ):
            if value:
                clauses.append(f"m.{column} = ?")
                values.append(value)
        now = _now()
        clauses.extend([
            "(m.valid_from IS NULL OR m.valid_from <= ?)",
            "(m.valid_until IS NULL OR m.valid_until > ?)",
        ])
        values.extend([now, now])
        conn = self.connect()
        try:
            row = conn.execute(
                f"""SELECT COUNT(*) FROM memory_fts f
                    JOIN memory_fts_meta m ON m.candidate_id=f.candidate_id
                    WHERE {' AND '.join(clauses)}""",
                values,
            ).fetchone()
            return int(row[0] if row else 0)
        except sqlite3.OperationalError as exc:
            raise FtsProjectionError("The lexical projection count was rejected safely.") from exc
        finally:
            conn.close()

    def health(self) -> dict[str, Any]:
        pending = failed = 0
        try:
            self.repository.initialize()
            with self.repository.connect() as canonical:
                pending = int(canonical.execute("SELECT COUNT(*) FROM memory_jobs WHERE state='pending' AND job_kind LIKE 'fts_%'").fetchone()[0])
                failed = int(canonical.execute("SELECT COUNT(*) FROM memory_jobs WHERE state='failed' AND job_kind LIKE 'fts_%'").fetchone()[0])
            conn = self.connect()
            try:
                quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
                indexed = int(conn.execute("SELECT COUNT(*) FROM memory_fts_meta").fetchone()[0])
            finally:
                conn.close()
            state = "ready" if quick == "ok" and failed == 0 else "degraded"
            return {
                "state": state,
                "projection_version": PROJECTION_VERSION,
                "tokenizer_version": TOKENIZER_VERSION,
                "indexed_normal_records": indexed,
                "pending_jobs": pending,
                "failed_jobs": failed,
                "quick_check": quick,
                "private_strategy": "authenticated_ephemeral_decrypt_scan_no_persistent_plaintext",
                "sealed_persistent_index": False,
                "rebuildable": True,
                "raw_path_exposed": False,
            }
        except Exception:
            return {
                "state": "degraded",
                "projection_version": PROJECTION_VERSION,
                "pending_jobs": pending,
                "failed_jobs": failed,
                "private_strategy": "authenticated_ephemeral_decrypt_scan_no_persistent_plaintext",
                "sealed_persistent_index": False,
                "rebuildable": True,
                "raw_path_exposed": False,
            }


__all__ = (
    "FtsMemoryProjection",
    "FtsProjectionError",
    "PROJECTION_VERSION",
    "TOKENIZER_VERSION",
)
