"""Encrypted, account-scoped personal onboarding and explicit memory import."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import yaml

from app.api.account_service import AccountAuthError, AccountServiceError, AccountStore
from app.memory.canonical_models import (
    MemoryCreateRequest,
    MemoryForm,
    MemoryPrincipal,
    MemoryPrivacy,
    MemorySourceInput,
)
from app.memory.canonical_repository import MemoryRepository
from app.memory.encryption_service import MemoryEncryptionService
from app.memory.fabric_service import MemoryFabricService

from .schemas import (
    OnboardingAnswer,
    OnboardingDraftRequest,
    OnboardingFinalizeAction,
    OnboardingFinalizeRequest,
    OnboardingRetention,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONNAIRE_PATH = ROOT / "config" / "onboarding" / "personal_questionnaire.yaml"
DATABASE_FILENAME = "personal_onboarding.sqlite"
CONTRACT_VERSION = "elysia-personal-onboarding-1.0"


class OnboardingError(AccountServiceError):
    """Onboarding failed without exposing account-owned answer content."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PersonalOnboardingService:
    def __init__(
        self,
        account_store: AccountStore | None = None,
        *,
        questionnaire_path: Path = DEFAULT_QUESTIONNAIRE_PATH,
    ) -> None:
        self.account_store = account_store or AccountStore()
        self.paths = self.account_store.elysia_paths
        self.database_path = self.paths.identity_dir / DATABASE_FILENAME
        self.questionnaire_path = questionnaire_path

    def _questionnaire(self) -> dict[str, Any]:
        try:
            payload = yaml.safe_load(self.questionnaire_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise OnboardingError("The personal onboarding contract could not be loaded.") from exc
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise OnboardingError("The personal onboarding contract is invalid.")
        sections = payload.get("sections")
        if not isinstance(sections, list):
            raise OnboardingError("The personal onboarding questions are unavailable.")
        ids = [
            question.get("question_id")
            for section in sections
            for question in section.get("questions", [])
            if isinstance(section, dict) and isinstance(question, dict)
        ]
        if len(ids) != 33 or len(set(ids)) != 33:
            raise OnboardingError("The complete voluntary questionnaire is required.")
        return payload

    def _principal(self) -> MemoryPrincipal:
        try:
            return MemoryPrincipal.model_validate(self.account_store.authenticated_principal())
        except AccountServiceError as exc:
            raise OnboardingError("A valid local account session is required for onboarding.") from exc

    def _connect(self) -> sqlite3.Connection:
        self.paths.identity_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.paths.identity_dir.chmod(0o700)
        except OSError:
            pass
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onboarding_state (
                owner_user_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                encrypted_draft BLOB,
                nonce BLOB,
                draft_sha256 TEXT,
                imported_memory_ids_json TEXT NOT NULL DEFAULT '{}',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                completed_at_utc TEXT
            )
            """
        )
        try:
            self.database_path.chmod(0o600)
        except OSError:
            pass
        return conn

    @staticmethod
    def _aad(owner_user_id: str) -> bytes:
        return f"elysia-personal-onboarding-v1:{owner_user_id}".encode("utf-8")

    def _key(self, principal: MemoryPrincipal) -> bytes:
        repository = MemoryRepository(paths=self.paths)
        return MemoryEncryptionService(repository).account_key(principal)

    def _encrypt(self, principal: MemoryPrincipal, draft: OnboardingDraftRequest) -> tuple[bytes, bytes, str]:
        plaintext = draft.model_dump_json().encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key(principal)).encrypt(
            nonce, plaintext, self._aad(principal.user_id)
        )
        return ciphertext, nonce, hashlib.sha256(plaintext).hexdigest()

    def _decrypt(self, principal: MemoryPrincipal, row: sqlite3.Row) -> OnboardingDraftRequest:
        if row["encrypted_draft"] is None or row["nonce"] is None:
            return OnboardingDraftRequest()
        try:
            plaintext = AESGCM(self._key(principal)).decrypt(
                bytes(row["nonce"]),
                bytes(row["encrypted_draft"]),
                self._aad(principal.user_id),
            )
            if hashlib.sha256(plaintext).hexdigest() != str(row["draft_sha256"]):
                raise OnboardingError("The encrypted onboarding draft failed integrity verification.")
            return OnboardingDraftRequest.model_validate_json(plaintext)
        except OnboardingError:
            raise
        except Exception as exc:
            raise OnboardingError("The encrypted onboarding draft could not be opened.") from exc

    def state(self) -> dict[str, Any]:
        principal = self._principal()
        questionnaire = self._questionnaire()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM onboarding_state WHERE owner_user_id=?",
                (principal.user_id,),
            ).fetchone()
        draft = self._decrypt(principal, row) if row is not None else OnboardingDraftRequest()
        imported = json.loads(str(row["imported_memory_ids_json"])) if row is not None else {}
        return {
            "contract_version": CONTRACT_VERSION,
            "status": str(row["status"]) if row is not None else "not_started",
            "sections": questionnaire["sections"],
            "answers": [answer.model_dump(mode="json") for answer in draft.answers],
            "answered_count": sum(bool(answer.exact_answer) for answer in draft.answers),
            "imported_memory_ids": imported,
            "account_scoped": True,
            "encrypted_at_rest": True,
            "external_egress": False,
            "canonical_memory_before_review": False,
            "may_skip_all": True,
            "raw_paths_exposed": False,
        }

    def save(self, request: OnboardingDraftRequest) -> dict[str, Any]:
        principal = self._principal()
        questionnaire = self._questionnaire()
        known = {
            question["question_id"]
            for section in questionnaire["sections"]
            for question in section["questions"]
        }
        if any(answer.question_id not in known for answer in request.answers):
            raise OnboardingError("The onboarding draft references an unknown question.")
        ciphertext, nonce, digest = self._encrypt(principal, request)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO onboarding_state (
                    owner_user_id,status,encrypted_draft,nonce,draft_sha256,
                    imported_memory_ids_json,created_at_utc,updated_at_utc
                ) VALUES (?, 'in_progress', ?, ?, ?, '{}', ?, ?)
                ON CONFLICT(owner_user_id) DO UPDATE SET
                    status='in_progress', encrypted_draft=excluded.encrypted_draft,
                    nonce=excluded.nonce, draft_sha256=excluded.draft_sha256,
                    updated_at_utc=excluded.updated_at_utc, completed_at_utc=NULL
                """,
                (principal.user_id, ciphertext, nonce, digest, now, now),
            )
            conn.commit()
        return self.state()

    def _write_terminal_state(self, principal: MemoryPrincipal, status: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO onboarding_state (
                    owner_user_id,status,encrypted_draft,nonce,draft_sha256,
                    imported_memory_ids_json,created_at_utc,updated_at_utc,completed_at_utc
                ) VALUES (?, ?, NULL, NULL, NULL, '{}', ?, ?, ?)
                ON CONFLICT(owner_user_id) DO UPDATE SET
                    status=excluded.status, encrypted_draft=NULL, nonce=NULL,
                    draft_sha256=NULL, updated_at_utc=excluded.updated_at_utc,
                    completed_at_utc=excluded.completed_at_utc
                """,
                (principal.user_id, status, now, now, now),
            )
            conn.commit()

    def finalize(self, request: OnboardingFinalizeRequest) -> dict[str, Any]:
        principal = self._principal()
        if request.action == OnboardingFinalizeAction.SKIP:
            self._write_terminal_state(principal, "skipped")
            return self.state()
        if request.action == OnboardingFinalizeAction.DISCARD:
            self._write_terminal_state(principal, "discarded")
            return self.state()
        if request.action == OnboardingFinalizeAction.RETAIN_DRAFT:
            return self.state()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM onboarding_state WHERE owner_user_id=?",
                (principal.user_id,),
            ).fetchone()
        if row is None:
            raise OnboardingError("No onboarding draft exists to review.")
        draft = self._decrypt(principal, row)
        if request.action == OnboardingFinalizeAction.IMPORT_NONE:
            self._write_terminal_state(principal, "completed_without_import")
            return self.state()

        selected = set(request.selected_question_ids)
        if request.action == OnboardingFinalizeAction.IMPORT_ALL:
            selected = {answer.question_id for answer in draft.answers}
        elif not selected:
            raise OnboardingError("Select at least one reviewed answer to import.")
        known = {answer.question_id for answer in draft.answers}
        if selected - known:
            raise OnboardingError("The reviewed import selection is invalid.")

        to_import = [
            answer
            for answer in draft.answers
            if answer.question_id in selected
            and answer.exact_answer
            and answer.retention == OnboardingRetention.PERSISTENT
        ]
        needs_sealed = any(answer.privacy.value == "sealed" for answer in to_import)
        repository = MemoryRepository(paths=self.paths)
        encryption = MemoryEncryptionService(repository)
        if needs_sealed:
            if not request.sealed_password:
                raise OnboardingError("Reauthentication is required for Sealed onboarding memory.")
            encryption.unlock_sealed(
                principal=principal,
                password=request.sealed_password,
                ttl_seconds=60,
            )
        try:
            imported = json.loads(str(row["imported_memory_ids_json"] or "{}"))
            fabric = MemoryFabricService(repository=repository)
            now = _utc_now()
            for answer in to_import:
                if answer.question_id in imported:
                    continue
                title = answer.proposed_title or f"Personal onboarding {answer.question_id.upper()}"
                record = fabric.create(
                    principal,
                    MemoryCreateRequest(
                        title=title,
                        body=answer.proposed_wording or answer.exact_answer,
                        why_stored="The account owner explicitly reviewed and imported this onboarding declaration.",
                        form=MemoryForm.SEMANTIC,
                        privacy=MemoryPrivacy(answer.privacy.value),
                        confidence=1.0,
                        user_confirmed=True,
                        observed_at=now,
                        form_data={
                            "confirmation": "explicit_user_onboarding_import",
                            "claim_kind": "account_owner_declaration",
                            "subject": "account_owner",
                            "onboarding_question_id": answer.question_id,
                            "retention": answer.retention.value,
                        },
                        source=MemorySourceInput(
                            source_type="onboarding_declaration",
                            source_id=answer.question_id,
                            source_label="Voluntary personal onboarding",
                            source_time=now,
                            source_authority="user",
                            provenance_status="reviewed_and_confirmed",
                        ),
                    ),
                )
                imported[answer.question_id] = record.memory_id
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE onboarding_state SET status='importing', imported_memory_ids_json=?, updated_at_utc=? WHERE owner_user_id=?",
                        (json.dumps(imported, sort_keys=True), _utc_now(), principal.user_id),
                    )
                    conn.commit()
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE onboarding_state SET status='completed', encrypted_draft=NULL,
                        nonce=NULL, draft_sha256=NULL, imported_memory_ids_json=?,
                        updated_at_utc=?, completed_at_utc=? WHERE owner_user_id=?
                    """,
                    (
                        json.dumps(imported, sort_keys=True),
                        _utc_now(),
                        _utc_now(),
                        principal.user_id,
                    ),
                )
                conn.commit()
        finally:
            if needs_sealed:
                encryption.relock(principal.user_id)
        return self.state()


__all__ = (
    "CONTRACT_VERSION",
    "DEFAULT_QUESTIONNAIRE_PATH",
    "OnboardingError",
    "PersonalOnboardingService",
)
