"""Audited AEAD key hierarchy for private and sealed canonical memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import secrets
from threading import RLock
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.ids import new_id
from app.memory.canonical_models import MemoryPrincipal, MemoryPrivacy
from app.memory.canonical_repository import MemoryRepository, utc_now


KDF_PARAMETERS = {"name": "scrypt", "n": 32768, "r": 8, "p": 1, "length": 32}
SEALED_TTL_MIN = 30
SEALED_TTL_MAX = 900


class MemoryEncryptionError(RuntimeError):
    """Encryption or key-unlock operation failed without exposing secrets."""


class SealedMemoryLockedError(MemoryEncryptionError):
    """The current account's sealed vault is not explicitly unlocked."""


@dataclass(frozen=True)
class EncryptedContent:
    ciphertext: bytes
    nonce: bytes | None
    wrapped_data_key: bytes | None
    key_nonce: bytes | None
    key_id: str | None
    content_format: str
    plaintext_hash: str


@dataclass
class _UnlockedVault:
    key: bytes
    session_id: str
    expires_monotonic: float
    expires_at: str


_SEALED_CACHE: dict[str, _UnlockedVault] = {}
_CACHE_LOCK = RLock()


def _password_kek(password: str, salt: bytes) -> bytes:
    if not password:
        raise MemoryEncryptionError("Reauthentication material is required.")
    kdf = Scrypt(
        salt=salt,
        length=int(KDF_PARAMETERS["length"]),
        n=int(KDF_PARAMETERS["n"]),
        r=int(KDF_PARAMETERS["r"]),
        p=int(KDF_PARAMETERS["p"]),
    )
    return kdf.derive(password.encode("utf-8"))


def _session_kek(session_token: str) -> bytes:
    if len(session_token) < 32:
        raise MemoryEncryptionError("The authenticated local session is unavailable.")
    return hashlib.sha256(
        b"elysia-memory-session-wrap-v1\x00" + session_token.encode("utf-8")
    ).digest()


def _aad(owner_user_id: str, purpose: str) -> bytes:
    return f"elysia-memory-v1:{owner_user_id}:{purpose}".encode("utf-8")


def _wrap(raw_key: bytes, wrapping_key: bytes, aad: bytes) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    return AESGCM(wrapping_key).encrypt(nonce, raw_key, aad), nonce


def _unwrap(ciphertext: bytes, nonce: bytes, wrapping_key: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(wrapping_key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise MemoryEncryptionError("The memory key could not be unlocked.") from exc


class MemoryEncryptionService:
    def __init__(self, repository: MemoryRepository | None = None) -> None:
        self.repository = repository or MemoryRepository()

    def provision_account(
        self,
        *,
        owner_user_id: str,
        password: str,
        session_id: str,
        session_token: str,
    ) -> None:
        self.repository.initialize()
        with self.repository.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_keys WHERE owner_user_id = ? AND active = 1",
                (owner_user_id,),
            ).fetchall()
            keyed = {str(row["key_kind"]): row for row in rows}
            if not keyed:
                account_master = secrets.token_bytes(32)
                sealed_vault = secrets.token_bytes(32)
                for kind, raw_key in (
                    ("account_master", account_master),
                    ("sealed_vault", sealed_vault),
                ):
                    salt = secrets.token_bytes(16)
                    wrapped, nonce = _wrap(
                        raw_key,
                        _password_kek(password, salt),
                        _aad(owner_user_id, f"password:{kind}"),
                    )
                    now = utc_now()
                    conn.execute(
                        """
                        INSERT INTO memory_keys (
                            key_id, owner_user_id, key_kind, wrapping_method,
                            wrapped_key, nonce, salt, kdf_parameters_json,
                            created_at, updated_at, active
                        ) VALUES (?, ?, ?, 'password-scrypt-aesgcm', ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            new_id("memkey"),
                            owner_user_id,
                            kind,
                            wrapped,
                            nonce,
                            salt,
                            json.dumps(KDF_PARAMETERS, sort_keys=True),
                            now,
                            now,
                        ),
                    )
            else:
                account_master = self._unwrap_password_row(
                    keyed.get("account_master"), owner_user_id, password
                )
                if "sealed_vault" not in keyed:
                    raise MemoryEncryptionError("The sealed-vault key metadata is incomplete.")

            session_wrapped, session_nonce = _wrap(
                account_master,
                _session_kek(session_token),
                _aad(owner_user_id, f"session:{session_id}"),
            )
            conn.execute(
                """
                INSERT INTO memory_session_keys (
                    session_id, owner_user_id, wrapped_key, nonce, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    owner_user_id=excluded.owner_user_id,
                    wrapped_key=excluded.wrapped_key,
                    nonce=excluded.nonce,
                    created_at=excluded.created_at
                """,
                (session_id, owner_user_id, session_wrapped, session_nonce, utc_now()),
            )
        self.repository.default_settings(owner_user_id)
        self.upgrade_authenticated_digests(
            MemoryPrincipal(
                user_id=owner_user_id,
                username="local-account",
                session_id=session_id,
                session_token=session_token,
            ),
            include_sealed=False,
        )

    def discard_unactivated_account(self, owner_user_id: str) -> bool:
        """Remove key metadata left by an account activation that rolled back.

        Canonical records are an explicit safety boundary: once any record is
        owned by the account, key destruction is refused because that would
        make encrypted memory unrecoverable.
        """

        self.repository.initialize()
        with self.repository.transaction() as conn:
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM memory_records WHERE owner_user_id = ?",
                    (owner_user_id,),
                ).fetchone()[0]
            )
            if count:
                return False
            conn.execute(
                "DELETE FROM memory_session_keys WHERE owner_user_id = ?", (owner_user_id,)
            )
            conn.execute("DELETE FROM memory_settings WHERE owner_user_id = ?", (owner_user_id,))
            conn.execute("DELETE FROM memory_keys WHERE owner_user_id = ?", (owner_user_id,))
        self.relock(owner_user_id)
        return True

    def _unwrap_password_row(self, row, owner_user_id: str, password: str) -> bytes:
        if row is None:
            raise MemoryEncryptionError("The account memory key is unavailable.")
        kind = str(row["key_kind"])
        return _unwrap(
            bytes(row["wrapped_key"]),
            bytes(row["nonce"]),
            _password_kek(password, bytes(row["salt"])),
            _aad(owner_user_id, f"password:{kind}"),
        )

    def account_key(self, principal: MemoryPrincipal) -> bytes:
        # Callers such as revision insertion may already hold the canonical
        # write transaction. Re-running schema DDL here would wait on our own
        # transaction; the owning Fabric service initializes the repository.
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT wrapped_key, nonce FROM memory_session_keys
                WHERE session_id = ? AND owner_user_id = ?
                """,
                (principal.session_id, principal.user_id),
            ).fetchone()
        if row is None:
            raise MemoryEncryptionError(
                "The authenticated memory key is unavailable; sign in again."
            )
        return _unwrap(
            bytes(row["wrapped_key"]),
            bytes(row["nonce"]),
            _session_kek(principal.session_token),
            _aad(principal.user_id, f"session:{principal.session_id}"),
        )

    def rewrap_password(
        self,
        *,
        principal: MemoryPrincipal,
        current_password: str,
        new_password: str,
    ) -> None:
        self.repository.initialize()
        with self.repository.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_keys WHERE owner_user_id = ? AND active = 1",
                (principal.user_id,),
            ).fetchall()
            if len(rows) != 2:
                raise MemoryEncryptionError("The account memory key hierarchy is incomplete.")
            unwrapped = {
                str(row["key_kind"]): self._unwrap_password_row(
                    row, principal.user_id, current_password
                )
                for row in rows
            }
            for row in rows:
                kind = str(row["key_kind"])
                salt = secrets.token_bytes(16)
                wrapped, nonce = _wrap(
                    unwrapped[kind],
                    _password_kek(new_password, salt),
                    _aad(principal.user_id, f"password:{kind}"),
                )
                conn.execute(
                    """
                    UPDATE memory_keys SET wrapped_key = ?, nonce = ?, salt = ?,
                        kdf_parameters_json = ?, updated_at = ?
                    WHERE key_id = ?
                    """,
                    (
                        wrapped,
                        nonce,
                        salt,
                        json.dumps(KDF_PARAMETERS, sort_keys=True),
                        utc_now(),
                        row["key_id"],
                    ),
                )

    def unlock_sealed(
        self,
        *,
        principal: MemoryPrincipal,
        password: str,
        ttl_seconds: int,
    ) -> dict[str, object]:
        ttl = max(SEALED_TTL_MIN, min(SEALED_TTL_MAX, int(ttl_seconds)))
        self.repository.initialize()
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_keys
                WHERE owner_user_id = ? AND key_kind = 'sealed_vault' AND active = 1
                """,
                (principal.user_id,),
            ).fetchone()
        key = self._unwrap_password_row(row, principal.user_id, password)
        expires = datetime.now(UTC) + timedelta(seconds=ttl)
        with _CACHE_LOCK:
            _SEALED_CACHE[principal.user_id] = _UnlockedVault(
                key=key,
                session_id=principal.session_id,
                expires_monotonic=time.monotonic() + ttl,
                expires_at=expires.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            )
        self.upgrade_authenticated_digests(principal, include_sealed=True)
        return {
            "unlocked": True,
            "ttl_seconds": ttl,
            "expires_at_utc": _SEALED_CACHE[principal.user_id].expires_at,
            "persistent_plaintext_index": False,
            "egress_allowed": False,
        }

    def sealed_key(self, principal: MemoryPrincipal) -> bytes:
        with _CACHE_LOCK:
            unlocked = _SEALED_CACHE.get(principal.user_id)
            if (
                unlocked is None
                or unlocked.session_id != principal.session_id
                or time.monotonic() >= unlocked.expires_monotonic
            ):
                _SEALED_CACHE.pop(principal.user_id, None)
                raise SealedMemoryLockedError("Sealed memory is locked.")
            return unlocked.key

    def sealed_status(self, principal: MemoryPrincipal) -> dict[str, object]:
        try:
            self.sealed_key(principal)
        except SealedMemoryLockedError:
            return {"unlocked": False, "expires_at_utc": None, "egress_allowed": False}
        with _CACHE_LOCK:
            unlocked = _SEALED_CACHE[principal.user_id]
            return {
                "unlocked": True,
                "expires_at_utc": unlocked.expires_at,
                "egress_allowed": False,
            }

    def relock(self, owner_user_id: str) -> None:
        with _CACHE_LOCK:
            _SEALED_CACHE.pop(owner_user_id, None)

    @staticmethod
    def digest_format(privacy: MemoryPrivacy) -> str:
        return (
            "sha256-v1"
            if privacy == MemoryPrivacy.NORMAL
            else f"hmac-sha256-{privacy.value}-v1"
        )

    def protected_digest(
        self,
        *,
        principal: MemoryPrincipal,
        privacy: MemoryPrivacy,
        plaintext: bytes,
    ) -> str:
        if privacy == MemoryPrivacy.NORMAL:
            return hashlib.sha256(plaintext).hexdigest()
        key = (
            self.account_key(principal)
            if privacy == MemoryPrivacy.PRIVATE
            else self.sealed_key(principal)
        )
        return hmac.new(
            key,
            f"elysia-{privacy.value}-plaintext-digest-v1\0".encode() + plaintext,
            "sha256",
        ).hexdigest()

    def upgrade_authenticated_digests(
        self, principal: MemoryPrincipal, *, include_sealed: bool
    ) -> dict[str, int]:
        """Replace legacy raw protected-content hashes after authorization.

        Private rows are upgraded when an authenticated session is provisioned.
        Sealed rows remain untouched until the owner explicitly unlocks the
        vault. Ciphertext is not rewritten by this metadata-only migration.
        """

        allowed = [MemoryPrivacy.PRIVATE]
        if include_sealed:
            allowed.append(MemoryPrivacy.SEALED)
        placeholders = ",".join("?" for _ in allowed)
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT v.*, r.privacy FROM memory_revisions v
                JOIN memory_records r ON r.memory_id=v.memory_id
                WHERE r.owner_user_id=? AND r.privacy IN ({placeholders})
                  AND v.digest_format='legacy-sha256-v1'
                ORDER BY v.revision_id
                """,
                (principal.user_id, *(privacy.value for privacy in allowed)),
            ).fetchall()
        upgraded = 0
        for row in rows:
            privacy = MemoryPrivacy(str(row["privacy"]))
            plaintext = self.decrypt_content(
                principal=principal,
                privacy=privacy,
                memory_id=str(row["memory_id"]),
                revision_id=str(row["revision_id"]),
                row=row,
            )
            digest = self.protected_digest(
                principal=principal, privacy=privacy, plaintext=plaintext
            )
            with self.repository.transaction() as conn:
                changed = conn.execute(
                    """
                    UPDATE memory_revisions
                    SET plaintext_hash=?, digest_format=?
                    WHERE revision_id=? AND digest_format='legacy-sha256-v1'
                    """,
                    (
                        digest,
                        self.digest_format(privacy),
                        row["revision_id"],
                    ),
                ).rowcount
            upgraded += int(changed)
        if upgraded:
            self.repository.secure_purge_deleted_content()
        return {"protected_digests_upgraded": upgraded}

    @staticmethod
    def relock_all() -> int:
        """Remove every process-local Sealed unlock during emergency posture."""
        with _CACHE_LOCK:
            count = len(_SEALED_CACHE)
            _SEALED_CACHE.clear()
        return count

    def revoke_session(self, session_id: str, owner_user_id: str) -> None:
        self.relock(owner_user_id)
        self.repository.initialize()
        with self.repository.transaction() as conn:
            conn.execute(
                "DELETE FROM memory_session_keys WHERE session_id = ? AND owner_user_id = ?",
                (session_id, owner_user_id),
            )

    def encrypt_content(
        self,
        *,
        principal: MemoryPrincipal,
        privacy: MemoryPrivacy,
        memory_id: str,
        revision_id: str,
        plaintext: bytes,
    ) -> EncryptedContent:
        aad = _aad(principal.user_id, f"content:{memory_id}:{revision_id}:{privacy.value}")
        if privacy == MemoryPrivacy.NORMAL:
            digest = self.protected_digest(
                principal=principal, privacy=privacy, plaintext=plaintext
            )
            return EncryptedContent(plaintext, None, None, None, None, "json/plaintext", digest)
        if privacy == MemoryPrivacy.PRIVATE:
            account_key = self.account_key(principal)
            digest = self.protected_digest(
                principal=principal, privacy=privacy, plaintext=plaintext
            )
            nonce = secrets.token_bytes(12)
            return EncryptedContent(
                AESGCM(account_key).encrypt(nonce, plaintext, aad),
                nonce,
                None,
                None,
                "account_master",
                "json/aesgcm-account",
                digest,
            )
        vault_key = self.sealed_key(principal)
        digest = self.protected_digest(
            principal=principal, privacy=privacy, plaintext=plaintext
        )
        data_key = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)
        key_nonce = secrets.token_bytes(12)
        return EncryptedContent(
            AESGCM(data_key).encrypt(nonce, plaintext, aad),
            nonce,
            AESGCM(vault_key).encrypt(key_nonce, data_key, aad + b":data-key"),
            key_nonce,
            "sealed_vault",
            "json/aesgcm-sealed-envelope",
            digest,
        )

    def decrypt_content(
        self,
        *,
        principal: MemoryPrincipal,
        privacy: MemoryPrivacy,
        memory_id: str,
        revision_id: str,
        row,
    ) -> bytes:
        ciphertext = bytes(row["content_ciphertext"])
        if privacy == MemoryPrivacy.NORMAL:
            return ciphertext
        nonce = bytes(row["content_nonce"])
        aad = _aad(principal.user_id, f"content:{memory_id}:{revision_id}:{privacy.value}")
        try:
            if privacy == MemoryPrivacy.PRIVATE:
                return AESGCM(self.account_key(principal)).decrypt(nonce, ciphertext, aad)
            vault_key = self.sealed_key(principal)
            data_key = AESGCM(vault_key).decrypt(
                bytes(row["key_nonce"]),
                bytes(row["wrapped_data_key"]),
                aad + b":data-key",
            )
            return AESGCM(data_key).decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise MemoryEncryptionError("The encrypted memory content failed authentication.") from exc

    def key_status(self, owner_user_id: str) -> dict[str, object]:
        self.repository.initialize()
        with self.repository.connect() as conn:
            rows = conn.execute(
                "SELECT key_kind, wrapping_method, active FROM memory_keys WHERE owner_user_id = ?",
                (owner_user_id,),
            ).fetchall()
        kinds = sorted(str(row["key_kind"]) for row in rows if int(row["active"]) == 1)
        return {
            "account_key_present": "account_master" in kinds,
            "sealed_vault_key_present": "sealed_vault" in kinds,
            "wrapping_method": "password-scrypt-aesgcm" if rows else "unavailable",
            "raw_key_exposed": False,
        }


__all__ = (
    "EncryptedContent",
    "MemoryEncryptionError",
    "MemoryEncryptionService",
    "SEALED_TTL_MAX",
    "SEALED_TTL_MIN",
    "SealedMemoryLockedError",
)
