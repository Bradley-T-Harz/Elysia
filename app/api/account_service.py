"""Sealed local account service for Elysia's identity gate."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import secrets
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pwdlib import PasswordHash

from app.ids import new_id

from app.api.schemas.account import (
    AccountColorOption,
    AccountCreateRequest,
    AccountDeleteRequest,
    AccountDeletionInventory,
    AccountLoginRequest,
    AccountPrivacyPolicyView,
    AccountProfileArchiveExportRequest,
    AccountProfileArchiveRestoreRequest,
    AccountProfilePrivate,
    AccountProfileUpdateRequest,
    AccountStateData,
    AccountStatus,
    ElysiaVisibleProfile,
    LocalAccountRole,
    ProfilePhotoAsset,
)
from app.api.schemas.admin import ManagedProfilePolicy
from app.install.paths import ElysiaPaths, RuntimeMode, resolve_elysia_paths

IDENTITY_ROOT = resolve_elysia_paths().identity_dir
DATABASE_PATH = IDENTITY_ROOT / "elysia_identity.sqlite"
PROFILE_PHOTO_DIR = IDENTITY_ROOT / "profile_photos"
CURRENT_SESSION_PATH = IDENTITY_ROOT / "current_session.json"
ACCOUNT_PRIVACY_PATH = Path("config/policies/account_privacy.yaml")
ACCOUNT_COLORS_PATH = Path("config/ui/account_colors.yaml")

MAX_PROFILE_PHOTO_BYTES = 10 * 1024 * 1024
ALLOWED_PROFILE_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

_password_hash = PasswordHash.recommended()

OPERATOR_RESET_CONFIRMATION = "RESET ALL LOCAL ELYSIA ACCOUNTS"
PROFILE_ARCHIVE_CONTRACT = "elysia-local-profile-archive-1.0"


class AccountServiceError(RuntimeError):
    """Base exception for local account-service failures."""


class AccountBlockedError(AccountServiceError):
    """Raised when a request is refused by the identity boundary."""


class AccountAuthError(AccountServiceError):
    """Raised when authentication is required or failed."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _profile_archive_key(recovery_material: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        recovery_material.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _password_hash.verify(password, hashed_password)


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_string_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(";", ",").split(",")]
        return [part for part in parts if part]
    return [str(item).strip() for item in value if str(item).strip()]


def _json_list(value: list[str] | str | None) -> str:
    return json.dumps(_normalize_string_list(value), ensure_ascii=False)


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _ensure_private_path(path: Path, *, directory: bool = False) -> None:
    try:
        path.chmod(0o700 if directory else 0o600)
    except OSError:
        pass


@dataclass(frozen=True)
class AccountPaths:
    identity_root: Path = IDENTITY_ROOT
    database_path: Path = DATABASE_PATH
    profile_photo_dir: Path = PROFILE_PHOTO_DIR
    current_session_path: Path = CURRENT_SESSION_PATH
    elysia_paths: ElysiaPaths | None = None


class AccountStore:
    def __init__(self, paths: AccountPaths | None = None) -> None:
        self.paths = paths or AccountPaths()
        if self.paths.elysia_paths is not None:
            self.elysia_paths = self.paths.elysia_paths
        elif paths is None:
            self.elysia_paths = resolve_elysia_paths()
        else:
            # Tests and embedders that inject an Identity root must not leak
            # canonical memory into the operator's real XDG profile.
            sandbox_root = self.paths.identity_root.parent
            self.elysia_paths = ElysiaPaths(
                mode=RuntimeMode.TEST,
                config_dir=sandbox_root / "config",
                data_dir=sandbox_root,
                cache_dir=sandbox_root / "cache",
                state_dir=sandbox_root / "state",
                runtime_dir=sandbox_root / "runtime",
                runtime_fallback_used=True,
            )

    def initialize(self) -> None:
        try:
            self.paths.identity_root.mkdir(parents=True, exist_ok=True)
            self.paths.profile_photo_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AccountServiceError(
                "The private Identity storage location could not be prepared."
            ) from exc
        _ensure_private_path(self.paths.identity_root, directory=True)
        _ensure_private_path(self.paths.profile_photo_dir, directory=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    disabled_at_utc TEXT,
                    local_role TEXT NOT NULL DEFAULT 'user',
                    managed INTEGER NOT NULL DEFAULT 0,
                    managed_by_user_id TEXT,
                    managed_policy_json TEXT,
                    policy_version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY,
                    interests TEXT NOT NULL DEFAULT '',
                    bio TEXT NOT NULL DEFAULT '',
                    birthdate TEXT,
                    emails_json TEXT NOT NULL DEFAULT '[]',
                    phone_number TEXT,
                    social_media_json TEXT NOT NULL DEFAULT '[]',
                    github TEXT,
                    city_state TEXT,
                    profile_color_id TEXT NOT NULL DEFAULT 'meteor_rose',
                    profile_photo_asset_id TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    last_seen_at_utc TEXT NOT NULL,
                    revoked_at_utc TEXT,
                    revocation_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS profile_photo_assets (
                    asset_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    deleted_at_utc TEXT
                );
                CREATE TABLE IF NOT EXISTS account_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    safe_summary TEXT NOT NULL,
                    actor_user_id TEXT,
                    target_user_id TEXT,
                    safe_details_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            self._ensure_column(conn, "users", "local_role", "TEXT NOT NULL DEFAULT 'user'")
            self._ensure_column(conn, "users", "managed", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "managed_by_user_id", "TEXT")
            self._ensure_column(conn, "users", "managed_policy_json", "TEXT")
            self._ensure_column(conn, "users", "policy_version", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "account_events", "actor_user_id", "TEXT")
            self._ensure_column(conn, "account_events", "target_user_id", "TEXT")
            self._ensure_column(
                conn,
                "account_events",
                "safe_details_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            owner = conn.execute(
                "SELECT id FROM users WHERE local_role = ? ORDER BY created_at_utc, id LIMIT 1",
                (LocalAccountRole.INSTALLATION_OWNER.value,),
            ).fetchone()
            if owner is None:
                earliest = conn.execute(
                    "SELECT id FROM users ORDER BY created_at_utc, id LIMIT 1"
                ).fetchone()
                if earliest is not None:
                    conn.execute(
                        "UPDATE users SET local_role = ?, managed = 0, managed_by_user_id = NULL, managed_policy_json = NULL WHERE id = ?",
                        (LocalAccountRole.INSTALLATION_OWNER.value, str(earliest["id"])),
                    )
        _ensure_private_path(self.paths.database_path)

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        declaration: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}"
            )

    def _connect(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = None
        try:
            self.paths.identity_root.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.paths.database_path, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=15000")
            return conn
        except (OSError, sqlite3.Error) as exc:
            if conn is not None:
                conn.close()
            raise AccountServiceError(
                "The private Identity database is unavailable. Check local storage permissions."
            ) from exc

    def _record_event(
        self,
        conn: sqlite3.Connection,
        event_type: str,
        *,
        actor_user_id: str | None = None,
        target_user_id: str | None = None,
        safe_details: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO account_events (
                event_id, event_type, created_at_utc, safe_summary,
                actor_user_id, target_user_id, safe_details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("acctevt"),
                event_type,
                _utc_now(),
                event_type.replace("_", " "),
                actor_user_id,
                target_user_id,
                json.dumps(safe_details or {}, sort_keys=True),
            ),
        )

    def account_count(self) -> int:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE disabled_at_utc IS NULL"
            ).fetchone()
        return int(row["count"] if row else 0)

    def record_governance_event(
        self,
        event_type: str,
        *,
        target_user_id: str | None = None,
        safe_details: dict[str, Any] | None = None,
    ) -> None:
        """Record objective installation-policy truth without content fields."""
        actor = self.authenticated_governance()
        self.initialize()
        with self._connect() as conn:
            self._record_event(
                conn,
                event_type,
                actor_user_id=str(actor["user_id"]),
                target_user_id=target_user_id or str(actor["user_id"]),
                safe_details=safe_details,
            )

    def has_user(self) -> bool:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE disabled_at_utc IS NULL LIMIT 1"
            ).fetchone()
        return row is not None

    def current_session(self) -> dict[str, str] | None:
        try:
            data = json.loads(self.paths.current_session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        session_id = _normalize_text(data.get("session_id"))
        token = _normalize_text(data.get("token"))
        if not session_id or not token:
            return None
        return {"session_id": session_id, "token": token}

    def _write_current_session(self, session_id: str, token: str) -> None:
        self.paths.identity_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".current-session-",
            suffix=".json",
            dir=self.paths.identity_root,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"session_id": session_id, "token": token}, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            _ensure_private_path(temporary)
            temporary.replace(self.paths.current_session_path)
        except OSError as exc:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise AccountServiceError(
                "The private local account session could not be established."
            ) from exc
        _ensure_private_path(self.paths.current_session_path)

    def _clear_current_session(self) -> None:
        try:
            self.paths.current_session_path.unlink()
        except FileNotFoundError:
            pass

    def validate_current_session(self) -> sqlite3.Row | None:
        self.initialize()
        session = self.current_session()
        if session is None:
            return None
        token_hash = _sha256_text(session["token"])
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sessions.id AS session_id, users.id AS user_id, users.username,
                       users.local_role, users.managed, users.managed_policy_json,
                       users.policy_version
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.id = ?
                  AND sessions.token_hash = ?
                  AND sessions.revoked_at_utc IS NULL
                  AND users.disabled_at_utc IS NULL
                """,
                (session["session_id"], token_hash),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE sessions SET last_seen_at_utc = ? WHERE id = ?",
                    (_utc_now(), session["session_id"]),
                )
        return row

    def state(self) -> AccountStateData:
        account_count = self.account_count()
        has_user = account_count > 0
        current = self.validate_current_session()
        if not has_user:
            return AccountStateData(account_count=0)
        if current is not None:
            return AccountStateData(
                has_user=True,
                is_authenticated=True,
                requires_user_creation=False,
                requires_login=False,
                active_username=str(current["username"]),
                active_user_id=str(current["user_id"]),
                active_role=LocalAccountRole(str(current["local_role"])),
                active_profile_managed=bool(current["managed"]),
                supervision_notice=(
                    "This local profile is visibly managed by installation governance; "
                    "content ownership remains private."
                    if bool(current["managed"])
                    else None
                ),
                account_count=account_count,
                multiple_accounts_available=account_count > 1,
                account_status=AccountStatus.LOGGED_IN,
            )
        return AccountStateData(
            has_user=True,
            is_authenticated=False,
            requires_user_creation=False,
            requires_login=True,
            active_username=None,
            account_count=account_count,
            multiple_accounts_available=account_count > 1,
            account_status=AccountStatus.LOGGED_OUT,
        )

    def _create_session(self, conn: sqlite3.Connection, user_id: str) -> tuple[str, str]:
        session_id = new_id("session")
        token = secrets.token_urlsafe(32)
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO sessions (id, user_id, token_hash, created_at_utc, last_seen_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, _sha256_text(token), now, now),
        )
        return session_id, token

    def _provision_memory_session(
        self,
        *,
        user_id: str,
        password: str,
        session_id: str,
        session_token: str,
    ) -> None:
        try:
            from app.memory.canonical_models import MemoryPrincipal
            from app.memory.canonical_repository import MemoryRepository
            from app.memory.encryption_service import MemoryEncryptionService
            from app.memory.migration_service import MemoryMigrationService

            repository = MemoryRepository(paths=self.elysia_paths)
            MemoryEncryptionService(repository).provision_account(
                owner_user_id=user_id,
                password=password,
                session_id=session_id,
                session_token=session_token,
            )
            MemoryMigrationService(repository=repository).migrate(
                principal=MemoryPrincipal(
                    user_id=user_id,
                    username="local-account",
                    session_id=session_id,
                    session_token=session_token,
                ),
                password=password,
            )
            from app.domain_ownership_migration import claim_unowned_domain_records

            claim_unowned_domain_records(self.elysia_paths.conversation_dir, user_id)
            claim_unowned_domain_records(self.elysia_paths.project_dir, user_id)
        except Exception as exc:
            raise AccountServiceError(
                "The local account was not activated because its private memory key could not be prepared."
            ) from exc

    def _discard_unactivated_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def _rollback_new_account_activation(self, user_id: str) -> None:
        """Remove a not-yet-public account after any activation-stage failure."""
        try:
            from app.memory.canonical_repository import MemoryRepository
            from app.memory.encryption_service import MemoryEncryptionService

            MemoryEncryptionService(
                MemoryRepository(paths=self.elysia_paths)
            ).discard_unactivated_account(user_id)
        except Exception:
            # Content-free orphan key metadata is unusable without an Identity
            # principal and is reported by maintenance diagnostics.
            pass
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def create_account(self, request: AccountCreateRequest) -> AccountProfilePrivate:
        self.initialize()
        username = _normalize_text(request.username)
        if not username:
            raise AccountBlockedError("Username is required.")
        had_user = self.has_user()
        actor = self.validate_current_session() if had_user else None
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, password_hash FROM users WHERE lower(username) = lower(?) AND disabled_at_utc IS NULL",
                (username,),
            ).fetchone()
        if existing is not None:
            if actor is not None and str(existing["id"]) != str(actor["user_id"]):
                raise AccountBlockedError("That local username already exists.")
            if not verify_password(request.password, str(existing["password_hash"])):
                raise AccountBlockedError("That local username already exists.")
            with self._connect() as conn:
                session_id, token = self._create_session(conn, str(existing["id"]))
                self._record_event(conn, "account_create_retry_authenticated")
            try:
                self._provision_memory_session(
                    user_id=str(existing["id"]),
                    password=request.password,
                    session_id=session_id,
                    session_token=token,
                )
            except AccountServiceError:
                self._discard_unactivated_session(session_id)
                raise
            try:
                self._write_current_session(session_id, token)
            except AccountServiceError:
                try:
                    from app.memory.canonical_repository import MemoryRepository
                    from app.memory.encryption_service import MemoryEncryptionService

                    MemoryEncryptionService(
                        MemoryRepository(paths=self.elysia_paths)
                    ).revoke_session(session_id, str(existing["id"]))
                finally:
                    self._discard_unactivated_session(session_id)
                raise
            return self.private_profile()

        if had_user and actor is None:
            raise AccountAuthError(
                "Sign in as the local Installation Owner or an Admin before adding another account."
            )
        actor_role = (
            LocalAccountRole(str(actor["local_role"]))
            if actor is not None
            else LocalAccountRole.INSTALLATION_OWNER
        )
        if had_user and actor_role not in {
            LocalAccountRole.INSTALLATION_OWNER,
            LocalAccountRole.ADMIN,
        }:
            raise AccountAuthError(
                "Only local installation governance may add another account."
            )
        requested_role = (
            LocalAccountRole.INSTALLATION_OWNER
            if not had_user
            else LocalAccountRole(request.requested_role)
        )
        if had_user and requested_role == LocalAccountRole.INSTALLATION_OWNER:
            raise AccountBlockedError("An installation already has its one Owner.")
        if actor_role == LocalAccountRole.ADMIN and requested_role != LocalAccountRole.USER:
            raise AccountBlockedError("Only the Installation Owner may create another Admin.")
        if request.managed_profile and requested_role != LocalAccountRole.USER:
            raise AccountBlockedError("Owner and Admin profiles cannot be managed profiles.")
        now = _utc_now()
        user_id = new_id("user")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, username, password_hash, created_at_utc, updated_at_utc,
                    local_role, managed, managed_by_user_id, managed_policy_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    hash_password(request.password),
                    now,
                    now,
                    requested_role.value,
                    1 if request.managed_profile else 0,
                    str(actor["user_id"]) if request.managed_profile and actor else None,
                    (
                        ManagedProfilePolicy().model_dump_json()
                        if request.managed_profile
                        else None
                    ),
                ),
            )
            conn.execute(
                """
                INSERT INTO profiles (
                    user_id, interests, bio, birthdate, emails_json, phone_number,
                    social_media_json, github, city_state, profile_color_id,
                    profile_photo_asset_id, created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    _normalize_text(request.interests),
                    _normalize_text(request.bio),
                    _normalize_optional_text(request.birthdate),
                    _json_list(request.emails),
                    _normalize_optional_text(request.phone_number),
                    _json_list(request.social_media),
                    _normalize_optional_text(request.github),
                    _normalize_optional_text(request.city_state),
                    _normalize_text(request.profile_color_id) or "meteor_rose",
                    _normalize_optional_text(request.profile_photo_asset_id),
                    now,
                    now,
                ),
            )
            session_id, token = self._create_session(conn, user_id)
            self._record_event(
                conn,
                "account_created",
                actor_user_id=str(actor["user_id"]) if actor else user_id,
                target_user_id=user_id,
                safe_details={
                    "role": requested_role.value,
                    "managed": bool(request.managed_profile),
                },
            )
        try:
            self._provision_memory_session(
                user_id=user_id,
                password=request.password,
                session_id=session_id,
                session_token=token,
            )
        except AccountServiceError:
            self._rollback_new_account_activation(user_id)
            raise
        if had_user:
            # Installation governance creates another isolated profile without
            # silently switching the active chamber or exposing its password.
            try:
                from app.memory.canonical_repository import MemoryRepository
                from app.memory.encryption_service import MemoryEncryptionService

                MemoryEncryptionService(
                    MemoryRepository(paths=self.elysia_paths)
                ).revoke_session(session_id, user_id)
            finally:
                self._discard_unactivated_session(session_id)
            return self._private_profile_for_user(user_id)
        try:
            self._write_current_session(session_id, token)
        except AccountServiceError:
            self._rollback_new_account_activation(user_id)
            raise
        return self._private_profile_for_user(user_id)

    def login(self, request: AccountLoginRequest) -> AccountStateData:
        self.initialize()
        username = _normalize_text(request.username)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, disabled_at_utc FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if (
                row is None
                or row["disabled_at_utc"] is not None
                or not verify_password(request.password, str(row["password_hash"]))
            ):
                self._record_event(
                    conn,
                    "authentication_failed",
                    target_user_id=str(row["id"]) if row is not None else None,
                    safe_details={
                        "known_local_profile": row is not None,
                        "account_disabled": bool(
                            row is not None and row["disabled_at_utc"] is not None
                        ),
                        "credential_material_recorded": False,
                    },
                )
                conn.commit()
                raise AccountAuthError("Invalid username or password.")
            session_id, token = self._create_session(conn, str(row["id"]))
            self._record_event(conn, "session_created")
        try:
            self._provision_memory_session(
                user_id=str(row["id"]),
                password=request.password,
                session_id=session_id,
                session_token=token,
            )
        except AccountServiceError:
            self._discard_unactivated_session(session_id)
            raise
        self._write_current_session(session_id, token)
        return self.state()

    def logout(self) -> AccountStateData:
        self.initialize()
        session = self.current_session()
        current = self.validate_current_session()
        with self._connect() as conn:
            if session is not None:
                conn.execute(
                    """
                    UPDATE sessions
                    SET revoked_at_utc = ?, revocation_reason = ?
                    WHERE id = ? AND revoked_at_utc IS NULL
                    """,
                    (_utc_now(), "user_logout", session["session_id"]),
                )
            self._record_event(conn, "session_revoked")
        if session is not None and current is not None:
            try:
                from app.memory.canonical_repository import MemoryRepository
                from app.memory.encryption_service import MemoryEncryptionService

                MemoryEncryptionService(
                    MemoryRepository(paths=self.elysia_paths)
                ).revoke_session(
                    str(session["session_id"]), str(current["user_id"])
                )
            except Exception:
                try:
                    from app.memory.canonical_repository import MemoryRepository
                    from app.memory.encryption_service import MemoryEncryptionService

                    MemoryEncryptionService(
                        MemoryRepository(paths=self.elysia_paths)
                    ).relock(str(current["user_id"]))
                except Exception:
                    pass
        self._clear_current_session()
        return self.state()

    def _authenticated_user_id(self) -> str:
        current = self.validate_current_session()
        if current is None:
            raise AccountAuthError("A valid local account session is required.")
        return str(current["user_id"])

    def authenticated_principal(self) -> dict[str, str]:
        current = self.validate_current_session()
        session = self.current_session()
        if current is None or session is None:
            raise AccountAuthError("A valid local account session is required.")
        return {
            "user_id": str(current["user_id"]),
            "username": str(current["username"]),
            "session_id": str(current["session_id"]),
            "session_token": session["token"],
        }

    def authenticated_governance(self) -> dict[str, Any]:
        current = self.validate_current_session()
        if current is None:
            raise AccountAuthError("A valid local account session is required.")
        policy: dict[str, Any] | None = None
        if current["managed_policy_json"]:
            try:
                policy = ManagedProfilePolicy.model_validate_json(
                    str(current["managed_policy_json"])
                ).model_dump(mode="json")
            except Exception:
                policy = ManagedProfilePolicy().model_dump(mode="json")
        return {
            "user_id": str(current["user_id"]),
            "username": str(current["username"]),
            "role": str(current["local_role"]),
            "managed": bool(current["managed"]),
            "managed_policy": policy,
            "policy_version": int(current["policy_version"] or 1),
            "content_access_granted": False,
        }

    def reauthenticate_current(self, password: str) -> dict[str, str]:
        """Verify fresh user material without returning hashes or key material."""
        principal = self.authenticated_principal()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ? AND disabled_at_utc IS NULL",
                (principal["user_id"],),
            ).fetchone()
        if row is None or not verify_password(password, str(row["password_hash"])):
            raise AccountAuthError("Reauthentication failed.")
        return principal

    @staticmethod
    def _owned_domain_record_count(root: Path, owner_user_id: str) -> int:
        """Count owner-tagged JSON records without returning private paths/content."""

        if not root.is_dir():
            return 0
        count = 0
        for path in root.rglob("*.json"):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            candidates = [payload]
            if isinstance(payload, dict):
                candidates.extend(
                    value for value in payload.values() if isinstance(value, dict)
                )
            if any(
                candidate.get("owner_user_id") == owner_user_id
                for candidate in candidates
                if isinstance(candidate, dict)
            ):
                count += 1
        return count

    def deletion_inventory(self, owner_user_id: str | None = None) -> AccountDeletionInventory:
        """Return bounded counts that must be zero before Identity key destruction."""

        user_id = owner_user_id or self._authenticated_user_id()
        memory_records = 0
        shared_spaces = 0
        try:
            from app.memory.canonical_repository import MemoryRepository

            repository = MemoryRepository(paths=self.elysia_paths)
            repository.initialize()
            with repository.connect() as conn:
                memory_records = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM memory_records WHERE owner_user_id = ?",
                        (user_id,),
                    ).fetchone()[0]
                )
                shared_spaces = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM shared_spaces WHERE owner_user_id = ?",
                        (user_id,),
                    ).fetchone()[0]
                )
        except Exception as exc:
            raise AccountServiceError(
                "Account deletion inventory could not verify the private memory boundary."
            ) from exc
        with self._connect() as conn:
            profile_photo_assets = int(
                conn.execute(
                    "SELECT COUNT(*) FROM profile_photo_assets WHERE user_id = ? AND deleted_at_utc IS NULL",
                    (user_id,),
                ).fetchone()[0]
            )
        project_records = self._owned_domain_record_count(
            self.elysia_paths.project_dir, user_id
        )
        conversation_records = self._owned_domain_record_count(
            self.elysia_paths.conversation_dir, user_id
        )
        return AccountDeletionInventory(
            memory_records=memory_records,
            shared_spaces=shared_spaces,
            project_records=project_records,
            conversation_records=conversation_records,
            profile_photo_assets=profile_photo_assets,
            blocking_owned_records=(
                memory_records + shared_spaces + project_records + conversation_records
            ),
        )

    def _delete_user_with_empty_owned_state(
        self, user_id: str
    ) -> tuple[AccountDeletionInventory, int, int]:
        inventory = self.deletion_inventory(user_id)
        if inventory.blocking_owned_records:
            raise AccountBlockedError(
                "This account still owns Memory, Project, Conversation, or shared-space records. "
                "Export or intentionally remove those records before deleting the Identity authority."
            )
        try:
            from app.memory.canonical_repository import MemoryRepository
            from app.memory.encryption_service import MemoryEncryptionService

            memory_repository = MemoryRepository(paths=self.elysia_paths)
            memory_repository.initialize()
            # Membership and invitation authority is distinct from owned
            # memory. An account that owns no records/spaces may leave a
            # Shared Space, but deletion must not strand a discoverable local
            # identity identifier in the ACL or invitation queue.
            with memory_repository.transaction() as memory_conn:
                memory_conn.execute(
                    "DELETE FROM memory_graph_edges WHERE owner_user_id=?", (user_id,)
                )
                memory_conn.execute(
                    "DELETE FROM memory_graph_nodes WHERE owner_user_id=?", (user_id,)
                )
                memory_conn.execute(
                    "DELETE FROM shared_space_members WHERE user_id=?", (user_id,)
                )
                memory_conn.execute(
                    "DELETE FROM shared_space_invitations WHERE invited_user_id=?",
                    (user_id,),
                )
            cleared = MemoryEncryptionService(
                memory_repository
            ).discard_unactivated_account(user_id)
        except Exception as exc:
            raise AccountServiceError(
                "The account memory authority could not be safely retired."
            ) from exc
        if not cleared:
            raise AccountBlockedError(
                "The account memory authority still protects owned records; deletion was refused."
            )

        photo_files: list[Path] = []
        with self._connect() as conn:
            photo_rows = conn.execute(
                "SELECT stored_filename FROM profile_photo_assets WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            sessions_removed = int(
                conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
            )
            for row in photo_rows:
                filename = str(row["stored_filename"] or "")
                if filename and Path(filename).name == filename:
                    photo_files.append(self.paths.profile_photo_dir / filename)
            conn.execute("DELETE FROM profile_photo_assets WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self._record_event(conn, "account_deleted_after_empty_owned_state_verification")
        removed_assets = 0
        for path in photo_files:
            try:
                path.unlink()
                removed_assets += 1
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise AccountServiceError(
                    "The Identity row was removed, but a private profile-photo file needs operator cleanup."
                ) from exc
        return inventory, sessions_removed, removed_assets

    def delete_current_account(
        self, request: AccountDeleteRequest
    ) -> tuple[AccountStateData, AccountDeletionInventory, int, int]:
        principal = self.reauthenticate_current(request.current_password)
        if not secrets.compare_digest(
            _normalize_text(request.confirmation_username), principal["username"]
        ):
            raise AccountBlockedError(
                "Type the current username exactly to confirm local account deletion."
            )
        inventory, sessions_removed, assets_removed = (
            self._delete_user_with_empty_owned_state(principal["user_id"])
        )
        self._clear_current_session()
        return self.state(), inventory, sessions_removed, assets_removed

    def reset_all_accounts_after_verified_preservation(
        self, *, confirmation: str, preservation_verified: bool
    ) -> dict[str, int]:
        """Operator-only reset used after an independently verified private archive.

        This method is deliberately not exposed as an HTTP route. It refuses
        account-owned domain data and therefore cannot silently destroy
        projects, conversations, shared spaces, or canonical memory.
        """

        if not preservation_verified:
            raise AccountBlockedError("Private preservation must be verified first.")
        if not secrets.compare_digest(confirmation, OPERATOR_RESET_CONFIRMATION):
            raise AccountBlockedError("The exact local reset confirmation was not supplied.")
        self.initialize()
        with self._connect() as conn:
            user_ids = [str(row["id"]) for row in conn.execute("SELECT id FROM users")]
        totals = {"users_removed": 0, "sessions_removed": 0, "profile_assets_removed": 0}
        for user_id in user_ids:
            _, sessions_removed, assets_removed = self._delete_user_with_empty_owned_state(user_id)
            totals["users_removed"] += 1
            totals["sessions_removed"] += sessions_removed
            totals["profile_assets_removed"] += assets_removed
        self._clear_current_session()
        return totals

    def _profile_row(self, user_id: str) -> sqlite3.Row:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT users.username, profiles.*
                FROM profiles
                JOIN users ON users.id = profiles.user_id
                WHERE profiles.user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            raise AccountServiceError("Account profile is missing.")
        return row

    def _photo_asset(self, asset_id: str | None) -> ProfilePhotoAsset | None:
        if not asset_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM profile_photo_assets
                WHERE asset_id = ? AND deleted_at_utc IS NULL
                """,
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        return ProfilePhotoAsset(
            asset_id=str(row["asset_id"]),
            mime_type=str(row["mime_type"]),
            extension=str(row["extension"]),
            byte_size=int(row["byte_size"]),
            sha256=str(row["sha256"]),
            preview_available=True,
        )

    def profile_photo_preview(self, asset_id: str) -> tuple[Path, str]:
        user_id = self._authenticated_user_id()
        clean_asset_id = _normalize_text(asset_id)
        if not clean_asset_id:
            raise AccountBlockedError("Profile photo asset id is required.")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT stored_filename, mime_type
                FROM profile_photo_assets
                WHERE asset_id = ?
                  AND user_id = ?
                  AND deleted_at_utc IS NULL
                """,
                (clean_asset_id, user_id),
            ).fetchone()
        if row is None:
            raise AccountAuthError("Profile photo asset is unavailable for the current local user.")
        stored_filename = str(row["stored_filename"] or "")
        if Path(stored_filename).name != stored_filename:
            raise AccountBlockedError("Stored profile photo reference is invalid.")
        path = self.paths.profile_photo_dir / stored_filename
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise AccountServiceError("Profile photo file is missing.")
        return path, str(row["mime_type"] or "application/octet-stream")

    def _private_profile_for_user(self, user_id: str) -> AccountProfilePrivate:
        row = self._profile_row(user_id)
        asset = self._photo_asset(row["profile_photo_asset_id"])
        return AccountProfilePrivate(
            username=str(row["username"]),
            interests=str(row["interests"] or ""),
            bio=str(row["bio"] or ""),
            birthdate=row["birthdate"],
            emails=_parse_json_list(row["emails_json"]),
            phone_number=row["phone_number"],
            social_media=_parse_json_list(row["social_media_json"]),
            github=row["github"],
            city_state=row["city_state"],
            profile_color_id=str(row["profile_color_id"] or "meteor_rose"),
            profile_photo_asset_id=row["profile_photo_asset_id"],
            profile_photo_available=asset is not None,
            profile_photo=asset,
        )

    def private_profile(self) -> AccountProfilePrivate:
        return self._private_profile_for_user(self._authenticated_user_id())

    def export_profile_archive(
        self, request: AccountProfileArchiveExportRequest
    ) -> dict[str, Any]:
        principal = self.reauthenticate_current(request.current_password)
        profile = self._private_profile_for_user(principal["user_id"])
        profile_payload = profile.model_dump(mode="json")
        profile_payload["profile_photo_asset_id"] = None
        profile_payload["profile_photo_available"] = False
        profile_payload["profile_photo"] = None
        photo: dict[str, Any] | None = None
        if profile.profile_photo_asset_id:
            path, mime_type = self.profile_photo_preview(profile.profile_photo_asset_id)
            raw = path.read_bytes()
            photo = {
                "extension": path.suffix.lower().lstrip("."),
                "mime_type": mime_type,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "byte_size": len(raw),
                "base64": base64.b64encode(raw).decode("ascii"),
            }
        payload = {
            "contract": PROFILE_ARCHIVE_CONTRACT,
            "schema_version": 1,
            "created_at_utc": _utc_now(),
            "source_username": profile.username,
            "profile": profile_payload,
            "profile_photo": photo,
            "contains_password": False,
            "contains_role_or_admin_authority": False,
            "contains_memory": False,
            "contains_projects_or_conversations": False,
        }
        plaintext = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        salt = os.urandom(16)
        nonce = os.urandom(12)
        aad = PROFILE_ARCHIVE_CONTRACT.encode("ascii")
        ciphertext = AESGCM(_profile_archive_key(request.recovery_material, salt)).encrypt(
            nonce, plaintext, aad
        )
        envelope = {
            "contract": PROFILE_ARCHIVE_CONTRACT,
            "schema_version": 1,
            "kdf": "scrypt-n16384-r8-p1",
            "cipher": "aes-256-gcm",
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        archive = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        with self._connect() as conn:
            self._record_event(
                conn,
                "profile_archive_exported",
                actor_user_id=principal["user_id"],
                target_user_id=principal["user_id"],
                safe_details={
                    "encrypted": True,
                    "photo_included": photo is not None,
                    "memory_included": False,
                },
            )
        return {
            "archive_base64": base64.b64encode(archive).decode("ascii"),
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "archive_size_bytes": len(archive),
            "encrypted": True,
            "profile_photo_included": photo is not None,
            "password_included": False,
            "role_or_admin_authority_included": False,
            "memory_included": False,
            "companion_memory_archive_required_for_memory_recovery": True,
            "raw_paths_exposed": False,
        }

    @staticmethod
    def _decrypt_profile_archive(
        archive_base64: str, recovery_material: str
    ) -> dict[str, Any]:
        try:
            raw = base64.b64decode(archive_base64, validate=True)
            envelope = json.loads(raw)
            if (
                not isinstance(envelope, dict)
                or envelope.get("contract") != PROFILE_ARCHIVE_CONTRACT
                or envelope.get("schema_version") != 1
                or envelope.get("kdf") != "scrypt-n16384-r8-p1"
                or envelope.get("cipher") != "aes-256-gcm"
            ):
                raise ValueError("contract")
            salt = base64.b64decode(str(envelope["salt"]), validate=True)
            nonce = base64.b64decode(str(envelope["nonce"]), validate=True)
            ciphertext = base64.b64decode(str(envelope["ciphertext"]), validate=True)
            plaintext = AESGCM(_profile_archive_key(recovery_material, salt)).decrypt(
                nonce, ciphertext, PROFILE_ARCHIVE_CONTRACT.encode("ascii")
            )
            payload = json.loads(plaintext)
        except Exception as exc:
            raise AccountAuthError(
                "The profile archive could not be authenticated with the supplied recovery material."
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("contract") != PROFILE_ARCHIVE_CONTRACT
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("profile"), dict)
        ):
            raise AccountBlockedError("The authenticated profile archive is invalid.")
        return payload

    def restore_profile_archive(
        self, request: AccountProfileArchiveRestoreRequest
    ) -> dict[str, Any]:
        if not request.operator_confirmed:
            raise AccountBlockedError("Profile recovery requires explicit confirmation.")
        principal = self.reauthenticate_current(request.current_password)
        payload = self._decrypt_profile_archive(
            request.archive_base64, request.recovery_material
        )
        profile = AccountProfilePrivate.model_validate(payload["profile"])
        photo_payload = payload.get("profile_photo")
        staged_photo: Path | None = None
        stored_filename: str | None = None
        asset_id: str | None = None
        old_photo_filename: str | None = None
        if photo_payload is not None:
            if not isinstance(photo_payload, dict):
                raise AccountBlockedError("The profile archive photo record is invalid.")
            try:
                photo_bytes = base64.b64decode(str(photo_payload["base64"]), validate=True)
                extension = str(photo_payload["extension"]).lower()
                expected_sha = str(photo_payload["sha256"])
                expected_size = int(photo_payload["byte_size"])
            except Exception as exc:
                raise AccountBlockedError("The profile archive photo record is invalid.") from exc
            if (
                extension not in ALLOWED_PROFILE_PHOTO_EXTENSIONS
                or len(photo_bytes) > MAX_PROFILE_PHOTO_BYTES
                or len(photo_bytes) != expected_size
                or hashlib.sha256(photo_bytes).hexdigest() != expected_sha
            ):
                raise AccountBlockedError("The profile archive photo failed integrity or size policy.")
            self.paths.profile_photo_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".profile-restore-", suffix=f".{extension}", dir=self.paths.profile_photo_dir
            )
            staged_photo = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(photo_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            staged_photo.chmod(0o600)
            asset_id = new_id("profile_photo")
            stored_filename = f"{asset_id}.{extension}"
        now = _utc_now()
        try:
            with self._connect() as conn:
                old = conn.execute(
                    "SELECT profile_photo_asset_id FROM profiles WHERE user_id=?",
                    (principal["user_id"],),
                ).fetchone()
                if old and old["profile_photo_asset_id"]:
                    old_row = conn.execute(
                        "SELECT stored_filename FROM profile_photo_assets WHERE asset_id=?",
                        (old["profile_photo_asset_id"],),
                    ).fetchone()
                    old_photo_filename = str(old_row["stored_filename"]) if old_row else None
                conn.execute(
                    """
                    UPDATE profiles SET interests=?,bio=?,birthdate=?,emails_json=?,
                        phone_number=?,social_media_json=?,github=?,city_state=?,
                        profile_color_id=?,profile_photo_asset_id=?,updated_at_utc=?
                    WHERE user_id=?
                    """,
                    (
                        _normalize_text(profile.interests),
                        _normalize_text(profile.bio),
                        _normalize_optional_text(profile.birthdate),
                        _json_list(profile.emails),
                        _normalize_optional_text(profile.phone_number),
                        _json_list(profile.social_media),
                        _normalize_optional_text(profile.github),
                        _normalize_optional_text(profile.city_state),
                        _normalize_text(profile.profile_color_id) or "meteor_rose",
                        asset_id,
                        now,
                        principal["user_id"],
                    ),
                )
                if asset_id and staged_photo and stored_filename:
                    destination = self.paths.profile_photo_dir / stored_filename
                    staged_photo.replace(destination)
                    staged_photo = None
                    conn.execute(
                        """
                        INSERT INTO profile_photo_assets (
                            asset_id,user_id,stored_filename,mime_type,extension,
                            sha256,byte_size,created_at_utc
                        ) VALUES (?,?,?,?,?,?,?,?)
                        """,
                        (
                            asset_id,
                            principal["user_id"],
                            stored_filename,
                            str(photo_payload.get("mime_type") or mimetypes.guess_type(stored_filename)[0] or "application/octet-stream"),
                            Path(stored_filename).suffix.lstrip("."),
                            str(photo_payload["sha256"]),
                            int(photo_payload["byte_size"]),
                            now,
                        ),
                    )
                if old and old["profile_photo_asset_id"]:
                    conn.execute(
                        "UPDATE profile_photo_assets SET deleted_at_utc=? WHERE asset_id=?",
                        (now, old["profile_photo_asset_id"]),
                    )
                self._record_event(
                    conn,
                    "profile_archive_restored",
                    actor_user_id=principal["user_id"],
                    target_user_id=principal["user_id"],
                    safe_details={
                        "source_username_changed": False,
                        "password_changed": False,
                        "role_changed": False,
                        "photo_restored": asset_id is not None,
                    },
                )
            if old_photo_filename and Path(old_photo_filename).name == old_photo_filename:
                (self.paths.profile_photo_dir / old_photo_filename).unlink(missing_ok=True)
        except Exception:
            if staged_photo is not None:
                staged_photo.unlink(missing_ok=True)
            if stored_filename:
                (self.paths.profile_photo_dir / stored_filename).unlink(missing_ok=True)
            raise
        return {
            "restored": True,
            "profile": self.private_profile().to_payload(),
            "source_username": str(payload.get("source_username") or ""),
            "username_changed": False,
            "password_changed": False,
            "role_or_admin_authority_changed": False,
            "memory_restored": False,
            "companion_memory_archive_required_for_memory_recovery": True,
            "raw_paths_exposed": False,
        }

    def visible_profile(self) -> ElysiaVisibleProfile | None:
        current = self.validate_current_session()
        if current is None:
            return None
        row = self._profile_row(str(current["user_id"]))
        asset = self._photo_asset(row["profile_photo_asset_id"])
        return ElysiaVisibleProfile(
            name_or_username=str(row["username"]),
            interests=str(row["interests"] or ""),
            bio=str(row["bio"] or ""),
            profile_photo_asset_id=row["profile_photo_asset_id"] if asset else None,
            profile_photo_available=asset is not None,
        )

    def update_profile(self, request: AccountProfileUpdateRequest) -> tuple[AccountProfilePrivate, bool]:
        user_id = self._authenticated_user_id()
        updates: dict[str, Any] = {}
        password_changed = False
        if request.interests is not None:
            updates["interests"] = _normalize_text(request.interests)
        if request.bio is not None:
            updates["bio"] = _normalize_text(request.bio)
        if request.birthdate is not None:
            updates["birthdate"] = _normalize_optional_text(request.birthdate)
        if request.emails is not None:
            updates["emails_json"] = _json_list(request.emails)
        if request.phone_number is not None:
            updates["phone_number"] = _normalize_optional_text(request.phone_number)
        if request.social_media is not None:
            updates["social_media_json"] = _json_list(request.social_media)
        if request.github is not None:
            updates["github"] = _normalize_optional_text(request.github)
        if request.city_state is not None:
            updates["city_state"] = _normalize_optional_text(request.city_state)
        if request.profile_color_id is not None:
            updates["profile_color_id"] = _normalize_text(request.profile_color_id) or "meteor_rose"
        if request.profile_photo_asset_id is not None:
            updates["profile_photo_asset_id"] = _normalize_optional_text(request.profile_photo_asset_id)

        prior_password_hash: str | None = None
        replacement_password_hash: str | None = None
        if request.password:
            if not request.current_password:
                raise AccountAuthError("Current password is required to change the password.")
            with self._connect() as conn:
                password_row = conn.execute(
                    "SELECT password_hash FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            if password_row is None or not verify_password(
                request.current_password, str(password_row["password_hash"])
            ):
                raise AccountAuthError("Current password is incorrect.")
            prior_password_hash = str(password_row["password_hash"])
            replacement_password_hash = hash_password(request.password)

        with self._connect() as conn:
            if request.username is not None:
                username = _normalize_text(request.username)
                if username:
                    conn.execute(
                        "UPDATE users SET username = ?, updated_at_utc = ? WHERE id = ?",
                        (username, _utc_now(), user_id),
                    )
            if request.password:
                conn.execute(
                    "UPDATE users SET password_hash = ?, updated_at_utc = ? WHERE id = ?",
                    (replacement_password_hash, _utc_now(), user_id),
                )
                password_changed = True
            if updates:
                updates["updated_at_utc"] = _utc_now()
                assignments = ", ".join(f"{key} = ?" for key in updates)
                conn.execute(
                    f"UPDATE profiles SET {assignments} WHERE user_id = ?",
                    (*updates.values(), user_id),
                )
            self._record_event(conn, "profile_updated")
            if password_changed:
                self._record_event(conn, "password_changed")
        if password_changed:
            try:
                from app.memory.canonical_models import MemoryPrincipal
                from app.memory.canonical_repository import MemoryRepository
                from app.memory.encryption_service import MemoryEncryptionService

                MemoryEncryptionService(
                    MemoryRepository(paths=self.elysia_paths)
                ).rewrap_password(
                    principal=MemoryPrincipal(**self.authenticated_principal()),
                    current_password=str(request.current_password),
                    new_password=str(request.password),
                )
            except Exception as exc:
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE users SET password_hash = ?, updated_at_utc = ? WHERE id = ?",
                        (prior_password_hash, _utc_now(), user_id),
                    )
                    self._record_event(conn, "password_change_rolled_back")
                raise AccountServiceError(
                    "The password change was rolled back because memory keys could not be rewrapped."
                ) from exc
        return self.private_profile(), password_changed

    def copy_profile_photo(self, source_path: str | Path) -> ProfilePhotoAsset:
        user_id = self._authenticated_user_id()
        source = Path(str(source_path)).expanduser()
        if not source.exists() or not source.is_file() or source.is_symlink():
            raise AccountBlockedError("Selected profile photo must be a regular local file.")
        extension = source.suffix.lower().lstrip(".")
        if extension not in ALLOWED_PROFILE_PHOTO_EXTENSIONS:
            raise AccountBlockedError("Profile photo must be jpg, jpeg, png, or webp.")
        size = source.stat().st_size
        if size > MAX_PROFILE_PHOTO_BYTES:
            raise AccountBlockedError("Profile photo exceeds the 10 MB size limit.")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        asset_id = new_id("profile_photo")
        stored_filename = f"{asset_id}.{extension}"
        destination = self.paths.profile_photo_dir / stored_filename
        self.paths.profile_photo_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        _ensure_private_path(destination)
        mime_type = mimetypes.guess_type(destination.name)[0] or "application/octet-stream"
        now = _utc_now()
        with self._connect() as conn:
            old = conn.execute(
                "SELECT profile_photo_asset_id FROM profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO profile_photo_assets (
                    asset_id, user_id, stored_filename, mime_type, extension,
                    sha256, byte_size, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, user_id, stored_filename, mime_type, extension, digest, size, now),
            )
            conn.execute(
                "UPDATE profiles SET profile_photo_asset_id = ?, updated_at_utc = ? WHERE user_id = ?",
                (asset_id, now, user_id),
            )
            if old and old["profile_photo_asset_id"]:
                self._mark_photo_deleted(conn, str(old["profile_photo_asset_id"]))
            self._record_event(conn, "photo_replaced")
        return self._photo_asset(asset_id)  # type: ignore[return-value]

    def _mark_photo_deleted(self, conn: sqlite3.Connection, asset_id: str) -> None:
        row = conn.execute(
            "SELECT stored_filename FROM profile_photo_assets WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        conn.execute(
            "UPDATE profile_photo_assets SET deleted_at_utc = ? WHERE asset_id = ?",
            (_utc_now(), asset_id),
        )
        if row is not None:
            try:
                (self.paths.profile_photo_dir / str(row["stored_filename"])).unlink()
            except FileNotFoundError:
                pass

    def delete_profile_photo(self) -> bool:
        user_id = self._authenticated_user_id()
        deleted = False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT profile_photo_asset_id FROM profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row and row["profile_photo_asset_id"]:
                self._mark_photo_deleted(conn, str(row["profile_photo_asset_id"]))
                deleted = True
            conn.execute(
                "UPDATE profiles SET profile_photo_asset_id = NULL, updated_at_utc = ? WHERE user_id = ?",
                (_utc_now(), user_id),
            )
            self._record_event(conn, "photo_deleted")
        return deleted


def _default_store() -> AccountStore:
    return AccountStore()


def get_account_state() -> AccountStateData:
    return _default_store().state()


def get_authenticated_principal() -> dict[str, str]:
    return _default_store().authenticated_principal()


def get_authenticated_governance() -> dict[str, Any]:
    """Return content-free role/managed policy truth for the active profile."""
    return _default_store().authenticated_governance()


def get_active_elysia_paths() -> ElysiaPaths:
    """Return the internal path context shared by Identity and Memory."""
    return _default_store().elysia_paths


def reauthenticate_current(password: str) -> dict[str, str]:
    return _default_store().reauthenticate_current(password)


def create_account(request: AccountCreateRequest) -> AccountProfilePrivate:
    return _default_store().create_account(request)


def login(request: AccountLoginRequest) -> AccountStateData:
    return _default_store().login(request)


def logout() -> AccountStateData:
    return _default_store().logout()


def get_private_profile() -> AccountProfilePrivate:
    return _default_store().private_profile()


def update_profile(request: AccountProfileUpdateRequest) -> tuple[AccountProfilePrivate, bool]:
    return _default_store().update_profile(request)


def export_profile_archive(request: AccountProfileArchiveExportRequest) -> dict[str, Any]:
    return _default_store().export_profile_archive(request)


def restore_profile_archive(request: AccountProfileArchiveRestoreRequest) -> dict[str, Any]:
    return _default_store().restore_profile_archive(request)


def get_elysia_visible_profile() -> ElysiaVisibleProfile | None:
    return _default_store().visible_profile()


def select_profile_photo(source_path: str | Path) -> ProfilePhotoAsset:
    return _default_store().copy_profile_photo(source_path)


def get_profile_photo_preview(asset_id: str) -> tuple[Path, str]:
    return _default_store().profile_photo_preview(asset_id)


def delete_profile_photo() -> bool:
    return _default_store().delete_profile_photo()


def get_account_deletion_inventory() -> AccountDeletionInventory:
    return _default_store().deletion_inventory()


def delete_current_account(
    request: AccountDeleteRequest,
) -> tuple[AccountStateData, AccountDeletionInventory, int, int]:
    return _default_store().delete_current_account(request)


def load_account_colors(path: Path = ACCOUNT_COLORS_PATH) -> list[AccountColorOption]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    colors = data.get("colors") if isinstance(data, dict) else []
    return [AccountColorOption(**color) for color in colors if isinstance(color, dict)]


def load_privacy_policy_view(path: Path = ACCOUNT_PRIVACY_PATH) -> AccountPrivacyPolicyView:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AccountServiceError("Account privacy policy is not a mapping.")
    return AccountPrivacyPolicyView(
        elysia_visible_fields=list(data.get("elysia_visible_fields") or []),
        sealed_fields=list(data.get("sealed_fields") or []),
        runtime_private_access=bool(data.get("runtime_access", {}).get("private_profile_allowed", False)),
        tools_private_access=bool(data.get("tools_access", {}).get("private_profile_allowed", False)),
        workers_private_access=bool(data.get("workers_access", {}).get("private_profile_allowed", False)),
        memory_import_private_profile=bool(data.get("memory_import", {}).get("private_profile_allowed", False)),
        prudence_note=str(data.get("prudence_note", {}).get("text") or ""),
    )


__all__ = (
    "AccountAuthError",
    "AccountBlockedError",
    "AccountPaths",
    "AccountServiceError",
    "AccountStore",
    "create_account",
    "delete_current_account",
    "delete_profile_photo",
    "export_profile_archive",
    "get_account_state",
    "get_active_elysia_paths",
    "get_authenticated_principal",
    "get_authenticated_governance",
    "get_elysia_visible_profile",
    "get_profile_photo_preview",
    "get_private_profile",
    "reauthenticate_current",
    "restore_profile_archive",
    "hash_password",
    "load_account_colors",
    "load_privacy_policy_view",
    "login",
    "logout",
    "select_profile_photo",
    "update_profile",
    "verify_password",
)
