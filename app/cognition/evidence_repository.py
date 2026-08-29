"""Canonical XDG-local authority for research sessions, evidence, and receipts."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
import json
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Iterator

from app.ids import new_id
from app.install.paths import ElysiaPaths, ensure_memory_directories, resolve_elysia_paths


EVIDENCE_SCHEMA_VERSION = 4
EVIDENCE_SCHEMA_NAME = "part2c-research-evidence-v4"

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_schema_migrations (
    schema_version INTEGER PRIMARY KEY,
    migration_name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    source_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_sessions (
    session_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','paused','completed','cancelled','failed')),
    project_id TEXT,
    conversation_id TEXT,
    request_id TEXT,
    reasoning_gear TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    working_conclusion TEXT,
    contradiction_state TEXT NOT NULL DEFAULT 'not_evaluated',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS research_queries (
    query_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    query_hash TEXT NOT NULL,
    sanitized_query TEXT NOT NULL,
    state TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    domain_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    UNIQUE(session_id, sequence_number)
);
CREATE TABLE IF NOT EXISTS research_progress (
    progress_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    stage TEXT NOT NULL,
    state TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    UNIQUE(session_id, sequence_number)
);
CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_url_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    request_id TEXT,
    project_id TEXT,
    conversation_id TEXT,
    content_digest TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    claim TEXT NOT NULL,
    retrieval_method TEXT NOT NULL,
    source_classification TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    boundary_state TEXT NOT NULL,
    citation_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    contradiction_json TEXT NOT NULL,
    quarantine_state TEXT NOT NULL,
    promotion_state TEXT NOT NULL DEFAULT 'evidence_only',
    memory_id TEXT,
    record_status TEXT NOT NULL DEFAULT 'active',
    supersedes_evidence_id TEXT,
    superseded_by_evidence_id TEXT,
    high_stakes INTEGER NOT NULL DEFAULT 0 CHECK(high_stakes IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_session_evidence (
    session_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    PRIMARY KEY(session_id, evidence_id),
    FOREIGN KEY(session_id) REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY(evidence_id) REFERENCES evidence_records(evidence_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS context_receipts (
    receipt_id TEXT PRIMARY KEY,
    owner_user_id TEXT,
    request_id TEXT NOT NULL UNIQUE,
    conversation_id TEXT,
    project_id TEXT,
    receipt_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_egress_approvals (
    approval_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    destination_class TEXT NOT NULL,
    data_categories_json TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    preview_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','approved','denied','consumed','expired')),
    token_hash TEXT,
    expires_at TEXT NOT NULL,
    one_time INTEGER NOT NULL CHECK(one_time IN (0,1)),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    consumed_at TEXT
    ,request_payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_evidence_owner_time ON evidence_records(owner_user_id, retrieved_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence_records(owner_user_id, project_id, retrieved_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_owner_status ON research_sessions(owner_user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_progress_session ON research_progress(session_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_receipts_owner_time ON context_receipts(owner_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_egress_owner_state ON research_egress_approvals(owner_user_id, state, expires_at);
"""


class EvidenceRepositoryError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class EvidenceRepository:
    def __init__(
        self,
        *,
        paths: ElysiaPaths | None = None,
        database_path: Path | None = None,
    ) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.database_path = database_path or self.paths.evidence_database_path

    def initialize(self) -> None:
        ensure_memory_directories(self.paths)
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.database_path.parent.chmod(0o700)
        except OSError:
            pass
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(evidence_records)").fetchall()
            }
            additive = {
                "record_status": "TEXT NOT NULL DEFAULT 'active'",
                "supersedes_evidence_id": "TEXT",
                "superseded_by_evidence_id": "TEXT",
                "high_stakes": "INTEGER NOT NULL DEFAULT 0 CHECK(high_stakes IN (0,1))",
            }
            for name, declaration in additive.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE evidence_records ADD COLUMN {name} {declaration}")
            approval_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(research_egress_approvals)").fetchall()
            }
            if "request_payload_json" not in approval_columns:
                conn.execute(
                    "ALTER TABLE research_egress_approvals ADD COLUMN request_payload_json TEXT NOT NULL DEFAULT '{}'"
                )
            conn.execute(
                "INSERT OR IGNORE INTO evidence_schema_migrations VALUES(?,?,?,?)",
                (EVIDENCE_SCHEMA_VERSION, EVIDENCE_SCHEMA_NAME, utc_now(), _digest(SCHEMA)),
            )
        try:
            self.database_path.chmod(0o600)
        except OSError:
            pass

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        conn = sqlite3.connect(self.database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA secure_delete=ON")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_session(
        self,
        *,
        owner_user_id: str,
        question: str,
        request_id: str | None,
        project_id: str | None,
        conversation_id: str | None,
        reasoning_gear: str,
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = new_id("research_session")
        now = utc_now()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO research_sessions
                (session_id,owner_user_id,question,status,project_id,conversation_id,
                 request_id,reasoning_gear,budget_json,created_at,updated_at)
                VALUES(?,?,?,'active',?,?,?,?,?,?,?)""",
                (
                    session_id, owner_user_id, question, project_id, conversation_id,
                    request_id, reasoning_gear, _json(budget), now, now,
                ),
            )
        return self.get_session(owner_user_id, session_id)

    def record_query(
        self,
        *,
        owner_user_id: str,
        session_id: str,
        query: str,
        state: str,
        result_count: int,
        domain_count: int,
    ) -> str:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence_number),0)+1 FROM research_queries q JOIN research_sessions s ON s.session_id=q.session_id WHERE q.session_id=? AND s.owner_user_id=?",
                (session_id, owner_user_id),
            ).fetchone()
            if row is None:
                raise EvidenceRepositoryError("Research session is unavailable to this account.")
            query_id = new_id("research_query")
            conn.execute(
                "INSERT INTO research_queries VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    query_id, session_id, int(row[0]), _digest(query), query, state,
                    max(0, result_count), max(0, domain_count), utc_now(),
                ),
            )
            conn.execute(
                "UPDATE research_sessions SET updated_at=? WHERE session_id=? AND owner_user_id=?",
                (utc_now(), session_id, owner_user_id),
            )
        return query_id

    def record_progress(
        self,
        *,
        owner_user_id: str,
        session_id: str,
        stage: str,
        state: str,
        detail: dict[str, Any] | None = None,
    ) -> str:
        """Append sanitized restart-safe progress; never persist query secrets here."""
        with self.transaction() as conn:
            owner = conn.execute(
                "SELECT 1 FROM research_sessions WHERE session_id=? AND owner_user_id=?",
                (session_id, owner_user_id),
            ).fetchone()
            if owner is None:
                raise EvidenceRepositoryError("Research session is unavailable to this account.")
            sequence = int(
                conn.execute(
                    "SELECT COALESCE(MAX(sequence_number),0)+1 FROM research_progress WHERE session_id=?",
                    (session_id,),
                ).fetchone()[0]
            )
            progress_id = new_id("research_progress")
            safe_detail = {
                str(key): value
                for key, value in dict(detail or {}).items()
                if key in {
                    "query_sequence", "fetch_sequence", "domain", "authority_class",
                    "result_count", "bytes_read", "reason",
                }
            }
            conn.execute(
                "INSERT INTO research_progress VALUES(?,?,?,?,?,?,?)",
                (
                    progress_id, session_id, sequence, str(stage)[:64], str(state)[:64],
                    _json(safe_detail), utc_now(),
                ),
            )
            conn.execute(
                "UPDATE research_sessions SET updated_at=? WHERE session_id=?",
                (utc_now(), session_id),
            )
        return progress_id

    def record_evidence(
        self,
        *,
        owner_user_id: str,
        packet: dict[str, Any],
        session_id: str | None = None,
        request_id: str | None = None,
        project_id: str | None = None,
        conversation_id: str | None = None,
        verification_status: str = "candidate",
        quarantine_state: str = "untrusted_web_evidence",
    ) -> str:
        source_url = str(packet.get("source_url") or "source:unknown")[:4096]
        excerpt = str(packet.get("snippet") or "")[:12000]
        title = str(packet.get("title") or "Untitled evidence")[:500]
        claim = str(packet.get("claim") or "Evidence candidate")[:2000]
        evidence_id = str(packet.get("evidence_id") or new_id("evidence"))
        now = utc_now()
        citation = {
            key: packet.get(key)
            for key in ("source_date", "publisher", "authors", "quote_span", "license_or_access_notes")
            if packet.get(key) is not None
        }
        provenance = {
            "worker_key": packet.get("worker_key"),
            "source_rank": packet.get("source_rank"),
            "network_access_used": bool(packet.get("network_access_used")),
            "private_context_sent": False,
            "page_fetch_used": bool(packet.get("page_fetch_used")),
        }
        contradictions = {
            "notes": list(packet.get("contradiction_notes") or [])[:40],
            "supports_claim": packet.get("supports_claim"),
        }
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO evidence_records (
                    evidence_id,owner_user_id,source_url,source_url_hash,title,
                    retrieved_at,request_id,project_id,conversation_id,content_digest,
                    excerpt,claim,retrieval_method,source_classification,
                    verification_status,boundary_state,citation_json,provenance_json,
                    contradiction_json,quarantine_state,promotion_state,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    title=excluded.title, excerpt=excluded.excerpt, claim=excluded.claim,
                    verification_status=excluded.verification_status,
                    contradiction_json=excluded.contradiction_json,
                    updated_at=excluded.updated_at""",
                (
                    evidence_id, owner_user_id, source_url, _digest(source_url), title,
                    str(packet.get("retrieved_at_utc") or now), request_id, project_id,
                    conversation_id, _digest(excerpt), excerpt, claim,
                    str(packet.get("retrieval_method") or "unknown"),
                    str(packet.get("source_type") or "unknown"), verification_status,
                    str(packet.get("outward_boundary_state") or "local"),
                    _json(citation), _json(provenance), _json(contradictions),
                    quarantine_state, "evidence_only", now, now,
                ),
            )
            if session_id:
                owner = conn.execute(
                    "SELECT 1 FROM research_sessions WHERE session_id=? AND owner_user_id=?",
                    (session_id, owner_user_id),
                ).fetchone()
                if owner is None:
                    raise EvidenceRepositoryError("Research session is unavailable to this account.")
                sequence = int(conn.execute(
                    "SELECT COALESCE(MAX(sequence_number),0)+1 FROM research_session_evidence WHERE session_id=?",
                    (session_id,),
                ).fetchone()[0])
                conn.execute(
                    "INSERT OR IGNORE INTO research_session_evidence VALUES(?,?,?)",
                    (session_id, evidence_id, sequence),
                )
            if bool(packet.get("high_stakes")):
                conn.execute(
                    "UPDATE evidence_records SET high_stakes=1 WHERE evidence_id=? AND owner_user_id=?",
                    (evidence_id, owner_user_id),
                )
        return evidence_id

    def transition_session(
        self,
        owner_user_id: str,
        session_id: str,
        status: str,
        *,
        working_conclusion: str | None = None,
        contradiction_state: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"active", "paused", "completed", "cancelled", "failed"}:
            raise EvidenceRepositoryError("Unsupported research-session state.")
        now = utc_now()
        with self.transaction() as conn:
            cursor = conn.execute(
                """UPDATE research_sessions SET status=?, working_conclusion=?,
                   contradiction_state=COALESCE(?,contradiction_state), updated_at=?,
                   completed_at=? WHERE session_id=? AND owner_user_id=?""",
                (
                    status, working_conclusion, contradiction_state, now,
                    now if status in {"completed", "cancelled", "failed"} else None,
                    session_id, owner_user_id,
                ),
            )
            if cursor.rowcount != 1:
                raise EvidenceRepositoryError("Research session is unavailable to this account.")
        return self.get_session(owner_user_id, session_id)

    def update_session_budget(
        self,
        owner_user_id: str,
        session_id: str,
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        with self.transaction() as conn:
            cursor = conn.execute(
                "UPDATE research_sessions SET budget_json=?,updated_at=? WHERE session_id=? AND owner_user_id=?",
                (_json(budget), utc_now(), session_id, owner_user_id),
            )
            if cursor.rowcount != 1:
                raise EvidenceRepositoryError("Research session is unavailable to this account.")
        return self.get_session(owner_user_id, session_id)

    def get_session(self, owner_user_id: str, session_id: str) -> dict[str, Any]:
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_sessions WHERE session_id=? AND owner_user_id=?",
                (session_id, owner_user_id),
            ).fetchone()
            if row is None:
                raise EvidenceRepositoryError("Research session is unavailable to this account.")
            queries = conn.execute(
                "SELECT * FROM research_queries WHERE session_id=? ORDER BY sequence_number",
                (session_id,),
            ).fetchall()
            progress = conn.execute(
                "SELECT * FROM research_progress WHERE session_id=? ORDER BY sequence_number",
                (session_id,),
            ).fetchall()
            evidence = conn.execute(
                """SELECT e.* FROM evidence_records e JOIN research_session_evidence x
                   ON x.evidence_id=e.evidence_id WHERE x.session_id=?
                   ORDER BY x.sequence_number""",
                (session_id,),
            ).fetchall()
        payload = dict(row)
        payload["budget"] = json.loads(payload.pop("budget_json"))
        payload["queries"] = [dict(item) for item in queries]
        payload["progress"] = [
            {
                **{key: value for key, value in dict(item).items() if key != "detail_json"},
                "detail": json.loads(str(item["detail_json"]) or "{}"),
            }
            for item in progress
        ]
        payload["evidence"] = [self._public_evidence(dict(item)) for item in evidence]
        return payload

    def list_sessions(
        self,
        owner_user_id: str,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.initialize()
        clauses = ["owner_user_id=?"]
        values: list[Any] = [owner_user_id]
        if project_id:
            clauses.append("project_id=?")
            values.append(project_id)
        if conversation_id:
            clauses.append("conversation_id=?")
            values.append(conversation_id)
        values.append(max(1, min(limit, 200)))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM research_sessions WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",
                values,
            ).fetchall()
        payloads = []
        for row in rows:
            item = dict(row)
            item["budget"] = json.loads(item.pop("budget_json"))
            payloads.append(item)
        return payloads

    def list_evidence(
        self,
        owner_user_id: str,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.initialize()
        clauses = ["owner_user_id=?"]
        values: list[Any] = [owner_user_id]
        if project_id:
            clauses.append("project_id=?")
            values.append(project_id)
        if conversation_id:
            clauses.append("conversation_id=?")
            values.append(conversation_id)
        values.append(max(1, min(limit, 500)))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM evidence_records WHERE {' AND '.join(clauses)} ORDER BY retrieved_at DESC,evidence_id LIMIT ?",
                values,
            ).fetchall()
        return [self._public_evidence(dict(row)) for row in rows]

    def get_evidence(self, owner_user_id: str, evidence_id: str) -> dict[str, Any]:
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evidence_records WHERE evidence_id=? AND owner_user_id=?",
                (evidence_id, owner_user_id),
            ).fetchone()
        if row is None:
            raise EvidenceRepositoryError("Evidence is unavailable to this account.")
        return self._public_evidence(dict(row))

    def set_verification(
        self,
        owner_user_id: str,
        evidence_id: str,
        *,
        verification_status: str,
        contradiction_notes: list[str] | None = None,
    ) -> dict[str, Any]:
        if verification_status not in {"candidate", "verified", "rejected", "contradicted"}:
            raise EvidenceRepositoryError("Unsupported evidence verification state.")
        with self.transaction() as conn:
            cursor = conn.execute(
                "UPDATE evidence_records SET verification_status=?,contradiction_json=?,updated_at=? WHERE evidence_id=? AND owner_user_id=? AND record_status='active'",
                (
                    verification_status,
                    _json({"notes": list(contradiction_notes or [])[:40]}),
                    utc_now(), evidence_id, owner_user_id,
                ),
            )
            if cursor.rowcount != 1:
                raise EvidenceRepositoryError("Evidence is unavailable to this account.")
        return self.get_evidence(owner_user_id, evidence_id)

    def correct_evidence(
        self,
        owner_user_id: str,
        evidence_id: str,
        *,
        claim: str,
        excerpt: str,
        reason: str,
    ) -> dict[str, Any]:
        current = self.get_evidence(owner_user_id, evidence_id)
        replacement = new_id("evidence")
        packet = {
            "evidence_id": replacement,
            "source_url": current["source_url"],
            "title": current["title"],
            "retrieved_at_utc": utc_now(),
            "snippet": excerpt,
            "claim": claim,
            "retrieval_method": "user_correction",
            "source_type": current["source_classification"],
            "outward_boundary_state": "local",
            "network_access_used": False,
            "page_fetch_used": False,
            "contradiction_notes": [reason],
            "high_stakes": bool(current.get("high_stakes")),
        }
        self.record_evidence(
            owner_user_id=owner_user_id,
            packet=packet,
            request_id=current.get("request_id"),
            project_id=current.get("project_id"),
            conversation_id=current.get("conversation_id"),
            verification_status="candidate",
            quarantine_state="corrected_local_evidence",
        )
        with self.transaction() as conn:
            conn.execute(
                "UPDATE evidence_records SET record_status='superseded',superseded_by_evidence_id=?,updated_at=? WHERE evidence_id=? AND owner_user_id=?",
                (replacement, utc_now(), evidence_id, owner_user_id),
            )
            conn.execute(
                "UPDATE evidence_records SET supersedes_evidence_id=? WHERE evidence_id=? AND owner_user_id=?",
                (evidence_id, replacement, owner_user_id),
            )
        return self.get_evidence(owner_user_id, replacement)

    def promote_to_memory_candidate(
        self,
        owner_user_id: str,
        evidence_id: str,
    ) -> dict[str, Any]:
        evidence = self.get_evidence(owner_user_id, evidence_id)
        if evidence.get("record_status") != "active":
            raise EvidenceRepositoryError("Only active evidence may be promoted.")
        if evidence.get("verification_status") != "verified":
            raise EvidenceRepositoryError("Evidence must be verified before candidate promotion.")
        if evidence.get("promotion_state") != "evidence_only":
            raise EvidenceRepositoryError("Evidence has already entered Memory governance.")
        from app.memory.canonical_models import (
            MemoryCandidateCreateRequest,
            MemoryForm,
            MemoryPrivacy,
            MemoryScope,
            MemorySourceInput,
        )
        from app.memory.canonical_repository import MemoryRepository
        from app.memory.fabric_service import MemoryFabricService

        fabric = MemoryFabricService(repository=MemoryRepository(paths=self.paths))
        principal = fabric.current_principal()
        if principal.user_id != owner_user_id:
            raise EvidenceRepositoryError("Evidence ownership changed during promotion.")
        memory = fabric.create_candidate(
            principal,
            MemoryCandidateCreateRequest(
                title=str(evidence.get("title") or "Research claim")[:240],
                body=str(evidence.get("claim") or "")[:64000],
                why_stored="Verified research evidence proposed as semantic Memory; user review is required.",
                scope=MemoryScope.RESEARCH,
                form=MemoryForm.SEMANTIC,
                privacy=MemoryPrivacy.NORMAL,
                importance=0.65,
                confidence=0.75,
                candidate_kind=(
                    "high_stakes_research_claim"
                    if evidence.get("high_stakes")
                    else "verified_research_claim"
                ),
                evidence_summary=str(evidence.get("excerpt") or "")[:2000],
                evidence_id=evidence_id,
                project_id=evidence.get("project_id"),
                conversation_id=evidence.get("conversation_id"),
                request_id=None,
                source=MemorySourceInput(
                    source_type="research_evidence",
                    source_id=evidence_id,
                    source_label=str(evidence.get("title") or "Research evidence")[:200],
                    source_time=evidence.get("retrieved_at"),
                    source_authority="verified_evidence",
                    retrieval_method=evidence.get("retrieval_method"),
                    provenance_status="verified_candidate",
                ),
            ),
        )
        with self.transaction() as conn:
            conn.execute(
                "UPDATE evidence_records SET promotion_state='memory_candidate',memory_id=?,updated_at=? WHERE evidence_id=? AND owner_user_id=?",
                (memory.memory_id, utc_now(), evidence_id, owner_user_id),
            )
        return {
            "evidence_id": evidence_id,
            "memory_id": memory.memory_id,
            "promotion_state": "memory_candidate",
            "high_stakes": bool(evidence.get("high_stakes")),
            "requires_user_review": True,
        }

    @staticmethod
    def _public_evidence(row: dict[str, Any]) -> dict[str, Any]:
        for key in ("citation_json", "provenance_json", "contradiction_json"):
            row[key.removesuffix("_json")] = json.loads(row.pop(key) or "{}")
        row.pop("owner_user_id", None)
        return row

    def store_context_receipt(
        self,
        *,
        owner_user_id: str | None,
        request_id: str,
        conversation_id: str | None,
        project_id: str | None,
        receipt: dict[str, Any],
    ) -> str:
        receipt_id = new_id("context_receipt")
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO context_receipts VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(request_id) DO UPDATE SET receipt_json=excluded.receipt_json,
                   conversation_id=excluded.conversation_id,project_id=excluded.project_id""",
                (receipt_id, owner_user_id, request_id, conversation_id, project_id, _json(receipt), utc_now()),
            )
            row = conn.execute(
                "SELECT receipt_id FROM context_receipts WHERE request_id=?",
                (request_id,),
            ).fetchone()
        return str(row["receipt_id"] if row else receipt_id)

    def get_context_receipt(self, owner_user_id: str | None, request_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT receipt_id,receipt_json,created_at FROM context_receipts WHERE request_id=? AND (owner_user_id=? OR (owner_user_id IS NULL AND ? IS NULL))",
                (request_id, owner_user_id, owner_user_id),
            ).fetchone()
        if row is None:
            return None
        return {"receipt_id": row["receipt_id"], "created_at": row["created_at"], **json.loads(row["receipt_json"])}

    def list_context_receipts(
        self,
        owner_user_id: str,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return bounded, content-free cognition receipts for one account."""
        self.initialize()
        clauses = ["owner_user_id=?"]
        values: list[Any] = [owner_user_id]
        if project_id:
            clauses.append("project_id=?")
            values.append(project_id)
        if conversation_id:
            clauses.append("conversation_id=?")
            values.append(conversation_id)
        values.append(max(1, min(limit, 200)))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT receipt_id,request_id,conversation_id,project_id,receipt_json,created_at FROM context_receipts WHERE {' AND '.join(clauses)} ORDER BY created_at DESC,receipt_id LIMIT ?",
                values,
            ).fetchall()
        receipts: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(str(row["receipt_json"]) or "{}")
            receipts.append(
                {
                    "receipt_id": row["receipt_id"],
                    "request_id": row["request_id"],
                    "conversation_id": row["conversation_id"],
                    "project_id": row["project_id"],
                    "created_at": row["created_at"],
                    **payload,
                }
            )
        return receipts

    def preview_egress(
        self,
        *,
        owner_user_id: str,
        operation: str,
        destination_class: str,
        data_categories: list[str],
        request_hash: str,
        preview: dict[str, Any],
        execution_payload: dict[str, Any] | None = None,
        ttl_seconds: int = 300,
    ) -> dict[str, Any]:
        approval_id = new_id("egress_approval")
        expires = (datetime.now(UTC) + timedelta(seconds=max(30, min(ttl_seconds, 900)))).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO research_egress_approvals (
                    approval_id,owner_user_id,operation,destination_class,
                    data_categories_json,request_hash,preview_json,state,token_hash,
                    expires_at,one_time,created_at,resolved_at,consumed_at,request_payload_json
                ) VALUES(?,?,?,?,?,?,?,'pending',NULL,?,1,?,NULL,NULL,?)""",
                (
                    approval_id, owner_user_id, operation, destination_class,
                    _json(sorted(set(data_categories))), request_hash, _json(preview),
                    expires, utc_now(), _json(execution_payload or {}),
                ),
            )
        return {
            "approval_id": approval_id,
            "state": "pending",
            "operation": operation,
            "destination_class": destination_class,
            "data_categories": sorted(set(data_categories)),
            "request_hash": request_hash,
            "preview": preview,
            "expires_at": expires,
            "one_time": True,
        }

    def resolve_egress(
        self,
        *,
        owner_user_id: str,
        approval_id: str,
        approve: bool,
    ) -> dict[str, Any]:
        token = secrets.token_urlsafe(32) if approve else None
        now = utc_now()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM research_egress_approvals WHERE approval_id=? AND owner_user_id=?",
                (approval_id, owner_user_id),
            ).fetchone()
            if row is None or row["state"] != "pending":
                raise EvidenceRepositoryError("The egress approval is unavailable or already resolved.")
            if _parse_time(row["expires_at"]) <= datetime.now(UTC):
                conn.execute("UPDATE research_egress_approvals SET state='expired',resolved_at=? WHERE approval_id=?", (now, approval_id))
                raise EvidenceRepositoryError("The egress approval expired.")
            conn.execute(
                "UPDATE research_egress_approvals SET state=?,token_hash=?,resolved_at=? WHERE approval_id=?",
                ("approved" if approve else "denied", _digest(token) if token else None, now, approval_id),
            )
        return {"approval_id": approval_id, "state": "approved" if approve else "denied", "approval_token": token, "one_time": True}

    def get_egress_execution_payload(
        self, owner_user_id: str, approval_id: str
    ) -> dict[str, Any]:
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT request_payload_json FROM research_egress_approvals WHERE approval_id=? AND owner_user_id=? AND state IN ('pending','approved')",
                (approval_id, owner_user_id),
            ).fetchone()
        if row is None:
            raise EvidenceRepositoryError("The egress approval is unavailable to this account.")
        payload = json.loads(str(row["request_payload_json"] or "{}"))
        if not isinstance(payload, dict) or not payload:
            raise EvidenceRepositoryError("The approval has no restart-safe initiating request.")
        return payload

    def consume_egress(
        self,
        *,
        owner_user_id: str,
        approval_id: str | None,
        approval_token: str | None,
        operation: str,
        destination_class: str,
        data_categories: list[str],
        request_hash: str,
    ) -> tuple[bool, str]:
        if not approval_id or not approval_token:
            return False, "exact_approval_required"
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM research_egress_approvals WHERE approval_id=? AND owner_user_id=?",
                (approval_id, owner_user_id),
            ).fetchone()
            if row is None or row["state"] != "approved":
                return False, "approval_not_approved"
            if _parse_time(row["expires_at"]) <= datetime.now(UTC):
                conn.execute("UPDATE research_egress_approvals SET state='expired' WHERE approval_id=?", (approval_id,))
                return False, "approval_expired"
            checks = (
                compare_digest(str(row["token_hash"] or ""), _digest(approval_token)),
                compare_digest(str(row["operation"]), operation),
                compare_digest(str(row["destination_class"]), destination_class),
                compare_digest(str(row["request_hash"]), request_hash),
                json.loads(row["data_categories_json"]) == sorted(set(data_categories)),
            )
            if not all(checks):
                return False, "approval_scope_mismatch"
            conn.execute(
                "UPDATE research_egress_approvals SET state='consumed',consumed_at=? WHERE approval_id=?",
                (utc_now(), approval_id),
            )
        return True, "consumed"

    def pending_egress(self, owner_user_id: str) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT approval_id,operation,destination_class,data_categories_json,request_hash,preview_json,state,expires_at,one_time,created_at FROM research_egress_approvals WHERE owner_user_id=? AND state='pending' ORDER BY created_at DESC",
                (owner_user_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "data_categories": json.loads(row["data_categories_json"]),
                "preview": json.loads(row["preview_json"]),
                "one_time": bool(row["one_time"]),
            }
            for row in rows
        ]

    def health(self) -> dict[str, Any]:
        try:
            self.initialize()
            with self.connect() as conn:
                quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
                evidence = int(conn.execute("SELECT COUNT(*) FROM evidence_records").fetchone()[0])
                sessions = int(conn.execute("SELECT COUNT(*) FROM research_sessions").fetchone()[0])
            return {
                "state": "ready" if quick == "ok" else "degraded",
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "quick_check": quick,
                "evidence_count": evidence,
                "research_session_count": sessions,
                "authority": "XDG local SQLite research evidence",
                "raw_path_exposed": False,
            }
        except Exception:
            return {"state": "degraded", "schema_version": EVIDENCE_SCHEMA_VERSION, "raw_path_exposed": False}


__all__ = ("EvidenceRepository", "EvidenceRepositoryError", "EVIDENCE_SCHEMA_VERSION")
