"""Governed content-addressed object authority for Memory and Artifacts.

The canonical Memory database owns references and lifecycle.  This store owns
immutable bytes.  Content equality is scoped to an authorization domain so
deduplication cannot become a cross-account or cross-privacy existence oracle.
"""

from __future__ import annotations

from hashlib import sha256
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import tempfile
from typing import Any
import zlib
import zstandard

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.ids import new_id
from app.memory.canonical_models import MemoryPrincipal, MemoryPrivacy
from app.memory.canonical_repository import MemoryRepository, utc_now
from app.memory.encryption_service import MemoryEncryptionService


OBJECT_FORMAT = "elysia-object-v1"
MAX_OBJECT_BYTES = 512 * 1024 * 1024


class MemoryObjectError(RuntimeError):
    """Object operation failed without exposing protected content or paths."""


class MemoryObjectStore:
    def __init__(self, *, repository: MemoryRepository | None = None) -> None:
        self.repository = repository or MemoryRepository()
        self.repository.initialize()
        self.root = self.repository.paths.memory_blob_dir / "objects-v1"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.pack_database = self.root / "cold-pack-v1.sqlite"
        with self._pack_connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS object_bytes (
                    path_token TEXT PRIMARY KEY,
                    stored BLOB NOT NULL,
                    stored_size INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
        self.pack_database.chmod(0o600)
        self.encryption = MemoryEncryptionService(self.repository)

    def _pack_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.pack_database, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _pack_put(self, token: str, stored: bytes) -> None:
        with self._pack_connect() as conn:
            conn.execute(
                "INSERT INTO object_bytes(path_token,stored,stored_size,created_at) VALUES(?,?,?,?)",
                (token, stored, len(stored), utc_now()),
            )
        self.pack_database.chmod(0o600)

    def _pack_read(self, token: str) -> bytes:
        with self._pack_connect() as conn:
            row = conn.execute(
                "SELECT stored,stored_size FROM object_bytes WHERE path_token=?", (token,)
            ).fetchone()
        if row is None or len(bytes(row["stored"])) != int(row["stored_size"]):
            raise MemoryObjectError("The packed object failed its storage-boundary check.")
        return bytes(row["stored"])

    def _pack_delete(self, token: str) -> bool:
        conn = self._pack_connect()
        try:
            deleted = conn.execute(
                "DELETE FROM object_bytes WHERE path_token=?", (token,)
            ).rowcount
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
        return bool(deleted)

    @staticmethod
    def _domain(
        *,
        principal: MemoryPrincipal,
        privacy: MemoryPrivacy,
        space_id: str | None,
        record_scope_id: str,
    ) -> str:
        if privacy == MemoryPrivacy.SEALED:
            return f"sealed:{principal.user_id}:{record_scope_id}"
        if space_id:
            return f"shared:{principal.user_id}:{space_id}:{privacy.value}"
        return f"account:{principal.user_id}:{privacy.value}"

    def _protection_key(
        self, principal: MemoryPrincipal, privacy: MemoryPrivacy, domain: str
    ) -> bytes | None:
        if privacy == MemoryPrivacy.NORMAL:
            return None
        master = (
            self.encryption.sealed_key(principal)
            if privacy == MemoryPrivacy.SEALED
            else self.encryption.account_key(principal)
        )
        return hmac.new(master, f"{OBJECT_FORMAT}:{domain}".encode(), "sha256").digest()

    @staticmethod
    def _digests(
        domain: str, raw: bytes, privacy: MemoryPrivacy, protection_key: bytes | None
    ) -> tuple[str, str]:
        ordinary = sha256(raw).hexdigest()
        if privacy == MemoryPrivacy.NORMAL:
            return ordinary, ordinary
        if protection_key is None:
            raise MemoryObjectError("Protected object key material is unavailable.")
        protected = hmac.new(
            protection_key,
            raw,
            "sha256",
        ).hexdigest()
        return protected, protected

    def _path(self, token: str) -> Path:
        if not token or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in token):
            raise MemoryObjectError("The managed object token is invalid.")
        candidate = self.root / token
        if candidate.parent != self.root:
            raise MemoryObjectError("The managed object location is invalid.")
        return candidate

    def _compression_level(self, principal: MemoryPrincipal) -> int:
        """Resolve the operator's real local-storage profile at the byte authority."""

        self.repository.default_settings(principal.user_id)
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT storage_resource_profile FROM memory_settings WHERE owner_user_id=?",
                (principal.user_id,),
            ).fetchone()
        profile = str(row[0]) if row is not None else "core_local"
        return {
            "core_local": 6,
            "balanced_local": 9,
            "minimal_local": 12,
        }.get(profile, 9)

    def put(
        self,
        *,
        principal: MemoryPrincipal,
        raw: bytes,
        privacy: MemoryPrivacy,
        space_id: str | None,
        ref_type: str,
        ref_id: str,
        purpose: str,
        media_type: str = "application/octet-stream",
        compress: bool = True,
        managed_object_id: str | None = None,
        managed_ref_id: str | None = None,
    ) -> dict[str, Any]:
        self.repository.assert_nonessential_writes_ready()
        if len(raw) > MAX_OBJECT_BYTES:
            raise MemoryObjectError("The managed object exceeds the local object-size limit.")
        if space_id:
            if privacy != MemoryPrivacy.NORMAL:
                raise MemoryObjectError(
                    "Shared-space object bytes must use the explicitly declassified normal domain."
                )
            with self.repository.connect() as conn:
                membership = conn.execute(
                    "SELECT 1 FROM shared_space_members WHERE space_id=? AND user_id=?",
                    (space_id, principal.user_id),
                ).fetchone()
            if membership is None:
                raise MemoryObjectError("The shared-space object domain is unavailable.")
        domain = self._domain(
            principal=principal,
            privacy=privacy,
            space_id=space_id,
            record_scope_id=ref_id,
        )
        protection_key = self._protection_key(principal, privacy, domain)
        storage_digest, original_digest = self._digests(
            domain, raw, privacy, protection_key
        )
        compression_level = self._compression_level(principal)
        compressed = (
            zstandard.ZstdCompressor(level=compression_level).compress(raw)
            if compress and raw
            else raw
        )
        if len(compressed) + 32 < len(raw):
            packed = compressed
            compression = f"zstd-{compression_level}"
        else:
            packed = raw
            compression = "none"
        if protection_key is not None:
            nonce = secrets.token_bytes(12)
            stored = b"ELYOBJENC1" + nonce + AESGCM(protection_key).encrypt(
                nonce, packed, f"{domain}:{storage_digest}:{compression}".encode()
            )
            storage_format = f"aes-256-gcm+{compression}"
        else:
            stored = packed
            storage_format = compression
        created_path: Path | None = None
        created_pack_token: str | None = None
        temporary: Path | None = None
        requested_ref_id = managed_ref_id or new_id("objref")
        object_ref_id = requested_ref_id
        try:
            with self.repository.transaction() as conn:
                existing = conn.execute(
                    "SELECT * FROM memory_objects WHERE security_domain = ? AND storage_digest = ?",
                    (domain, storage_digest),
                ).fetchone()
                if existing is not None:
                    object_id = str(existing["object_id"])
                    if managed_object_id and object_id != managed_object_id:
                        raise MemoryObjectError(
                            "The restored content already belongs to a different stable object identifier."
                        )
                    existing_token = str(existing["path_token"])
                    if existing_token.startswith("pack-"):
                        self._pack_read(existing_token)
                    else:
                        path = self._path(existing_token)
                        if not path.is_file() or path.is_symlink():
                            raise MemoryObjectError("A deduplicated object failed integrity validation.")
                else:
                    object_id = managed_object_id or new_id("memobj")
                    if conn.execute(
                        "SELECT 1 FROM memory_objects WHERE object_id = ?", (object_id,)
                    ).fetchone() is not None:
                        raise MemoryObjectError(
                            "The requested managed object identifier already exists."
                        )
                    packed_backend = ref_type == "cold_revision"
                    token = f"{'pack' if packed_backend else 'object'}-{object_id.removeprefix('memobj_')}"
                    if packed_backend:
                        self._pack_put(token, stored)
                        created_pack_token = token
                    else:
                        path = self._path(token)
                        descriptor, temporary_name = tempfile.mkstemp(prefix=".object-", dir=self.root)
                        temporary = Path(temporary_name)
                        with os.fdopen(descriptor, "wb") as handle:
                            handle.write(stored)
                            handle.flush()
                            os.fsync(handle.fileno())
                        temporary.chmod(0o600)
                        os.replace(temporary, path)
                        temporary = None
                        created_path = path
                        path.chmod(0o600)
                        directory_fd = os.open(
                            self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                        )
                        try:
                            os.fsync(directory_fd)
                        finally:
                            os.close(directory_fd)
                    conn.execute(
                        """
                        INSERT INTO memory_objects (
                            object_id, owner_user_id, space_id, security_domain,
                            privacy, storage_digest, original_digest, original_size,
                            stored_size, compression, media_type, path_token,
                            created_at, verified_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            object_id, principal.user_id, space_id, domain,
                            privacy.value, storage_digest, original_digest, len(raw),
                            len(stored), storage_format, media_type, token, utc_now(), utc_now(),
                        ),
                    )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO memory_object_refs (
                        object_ref_id, object_id, owner_user_id, ref_type, ref_id,
                        purpose, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        requested_ref_id, object_id, principal.user_id,
                        ref_type, ref_id, purpose, utc_now(),
                    ),
                )
                reference = conn.execute(
                    """
                    SELECT object_ref_id FROM memory_object_refs
                    WHERE object_id=? AND ref_type=? AND ref_id=? AND purpose=?
                    """,
                    (object_id, ref_type, ref_id, purpose),
                ).fetchone()
                if reference is None:
                    raise MemoryObjectError("The managed object reference was not committed.")
                object_ref_id = str(reference["object_ref_id"])
                if managed_ref_id and object_ref_id != managed_ref_id:
                    raise MemoryObjectError(
                        "The restored content already belongs to a different stable reference identifier."
                    )
        except Exception:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if created_path is not None:
                created_path.unlink(missing_ok=True)
            if created_pack_token is not None:
                self._pack_delete(created_pack_token)
            raise
        return {
            "object_id": object_id,
            "object_ref_id": object_ref_id,
            "deduplicated_within_security_domain": existing is not None,
            "privacy": privacy.value,
            "compression": compression,
            "protected_at_rest": protection_key is not None,
            "original_size": len(raw),
            "stored_size": len(stored),
            "raw_path_exposed": False,
        }

    def read(self, *, principal: MemoryPrincipal, object_id: str) -> bytes:
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT o.* FROM memory_objects o
                WHERE o.object_id = ? AND (
                    (o.owner_user_id = ? AND o.space_id IS NULL) OR EXISTS (
                        SELECT 1 FROM shared_space_members m
                        WHERE m.space_id = o.space_id AND m.user_id = ?
                    )
                )
                """,
                (object_id, principal.user_id, principal.user_id),
            ).fetchone()
        if row is None:
            raise MemoryObjectError("The managed object is unavailable.")
        token = str(row["path_token"])
        if token.startswith("pack-"):
            stored = self._pack_read(token)
        else:
            path = self._path(token)
            if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
                raise MemoryObjectError("The managed object failed its storage-boundary check.")
            stored = path.read_bytes()
        if len(stored) != int(row["stored_size"]):
            raise MemoryObjectError("The managed object failed its size check.")
        privacy = MemoryPrivacy(str(row["privacy"]))
        domain = str(row["security_domain"])
        protection_key = self._protection_key(principal, privacy, domain)
        storage_format = str(row["compression"])
        compression = storage_format.removeprefix("aes-256-gcm+")
        try:
            if storage_format.startswith("aes-256-gcm+"):
                if protection_key is None or not stored.startswith(b"ELYOBJENC1"):
                    raise MemoryObjectError("The protected object envelope is invalid.")
                nonce = stored[10:22]
                packed = AESGCM(protection_key).decrypt(
                    nonce,
                    stored[22:],
                    f"{domain}:{row['storage_digest']}:{compression}".encode(),
                )
            else:
                packed = stored
            if compression.startswith("zstd-"):
                raw = zstandard.ZstdDecompressor().decompress(packed)
            elif compression == "zlib-9":
                raw = zlib.decompress(packed)
            else:
                raw = packed
        except (InvalidTag, zlib.error, zstandard.ZstdError) as exc:
            raise MemoryObjectError("The managed object failed authenticated decoding.") from exc
        storage_digest, original_digest = self._digests(
            domain, raw, privacy, protection_key
        )
        if not hmac.compare_digest(storage_digest, str(row["storage_digest"])) or not hmac.compare_digest(
            original_digest, str(row["original_digest"])
        ):
            raise MemoryObjectError("The managed object failed integrity validation.")
        return raw

    def internal_managed_path(
        self, *, principal: MemoryPrincipal, object_id: str
    ) -> Path:
        """Return an internal path only after the same ownership/ACL check as read.

        This is for local governed consumers such as the Artifact renderer. It
        is never returned by the public Memory API.
        """

        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT o.path_token FROM memory_objects o
                WHERE o.object_id = ? AND (
                    (o.owner_user_id = ? AND o.space_id IS NULL) OR EXISTS (
                        SELECT 1 FROM shared_space_members m
                        WHERE m.space_id=o.space_id AND m.user_id=?
                    )
                )
                """,
                (object_id, principal.user_id, principal.user_id),
            ).fetchone()
        if row is None:
            raise MemoryObjectError("The managed object is unavailable.")
        path = self._path(str(row["path_token"]))
        if str(row["path_token"]).startswith("pack-"):
            raise MemoryObjectError("Packed cold bytes do not expose a filesystem path.")
        if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
            raise MemoryObjectError("The managed object failed its storage-boundary check.")
        return path

    def read_cold_revision(
        self, *, principal: MemoryPrincipal, memory_id: str, revision_id: str
    ) -> bytes:
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT c.object_id FROM memory_cold_revisions c
                JOIN memory_records r ON r.memory_id = c.memory_id
                WHERE c.revision_id = ? AND c.memory_id = ? AND (
                    (r.owner_user_id = ? AND r.space_id IS NULL) OR EXISTS (
                        SELECT 1 FROM shared_space_members m
                        WHERE m.space_id = r.space_id AND m.user_id = ?
                    )
                )
                """,
                (revision_id, memory_id, principal.user_id, principal.user_id),
            ).fetchone()
        if row is None:
            raise MemoryObjectError("The cold-memory payload is unavailable.")
        return self.read(principal=principal, object_id=str(row["object_id"]))

    def verify(self, *, principal: MemoryPrincipal) -> dict[str, Any]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT o.object_id FROM memory_objects o
                WHERE (o.owner_user_id = ? AND o.space_id IS NULL) OR EXISTS (
                    SELECT 1 FROM shared_space_members m
                    WHERE m.space_id=o.space_id AND m.user_id=?
                )
                ORDER BY o.object_id
                """,
                (principal.user_id, principal.user_id),
            ).fetchall()
            canonical_tokens = {
                str(row[0])
                for row in conn.execute(
                    "SELECT path_token FROM memory_objects"
                ).fetchall()
            }
        failed = 0
        for row in rows:
            try:
                self.read(principal=principal, object_id=str(row["object_id"]))
            except MemoryObjectError:
                failed += 1
        with self._pack_connect() as conn:
            pack_integrity = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            packed_tokens = {
                str(row[0])
                for row in conn.execute("SELECT path_token FROM object_bytes").fetchall()
            }
        file_tokens = {
            path.name
            for path in self.root.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and path.name.startswith("object-")
        }
        orphan_tokens = sorted((packed_tokens | file_tokens) - canonical_tokens)
        return {
            "state": (
                "ready"
                if failed == 0 and pack_integrity == "ok" and not orphan_tokens
                else "degraded"
            ),
            "object_count": len(rows),
            "failed_integrity_count": failed,
            "packed_store_integrity": pack_integrity,
            "orphan_object_count": len(orphan_tokens),
            "raw_paths_exposed": False,
        }

    def garbage_collect_orphans(self) -> dict[str, Any]:
        """Remove bytes left before an interrupted metadata commit.

        Canonical object metadata is authoritative. Only pack rows and object
        files with no canonical metadata token are eligible for removal.
        """

        with self.repository.connect() as conn:
            canonical_tokens = {
                str(row[0])
                for row in conn.execute(
                    "SELECT path_token FROM memory_objects"
                ).fetchall()
            }
            # A process crash can occur after immutable packed bytes and their
            # reference commit but before the canonical cold pointer commits.
            # Such a reference is derived and unreachable; the canonical
            # revision still contains its ciphertext, so exact cleanup is safe.
            unreachable_cold_refs = [
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT ref.object_ref_id
                    FROM memory_object_refs ref
                    LEFT JOIN memory_cold_revisions cold
                      ON cold.revision_id=ref.ref_id
                     AND cold.object_id=ref.object_id
                    WHERE ref.ref_type='cold_revision'
                      AND ref.purpose='canonical_cold_payload'
                      AND cold.revision_id IS NULL
                    """
                ).fetchall()
            ]
        unreachable_result = self.purge_reference_ids(unreachable_cold_refs)
        with self._pack_connect() as conn:
            packed_tokens = {
                str(row[0])
                for row in conn.execute("SELECT path_token FROM object_bytes").fetchall()
            }
        removed_pack = 0
        for token in sorted(packed_tokens - canonical_tokens):
            removed_pack += int(self._pack_delete(token))
        removed_files = 0
        for path in self.root.iterdir():
            if (
                path.is_file()
                and not path.is_symlink()
                and path.name.startswith("object-")
                and path.name not in canonical_tokens
            ):
                path.unlink()
                removed_files += 1
        return {
            "orphan_pack_rows_removed": removed_pack,
            "orphan_files_removed": removed_files,
            "unreachable_cold_references_removed": unreachable_result[
                "references_removed"
            ],
            "canonical_objects_removed": 0,
        }

    def purge_references(self, *, ref_type: str, ref_id: str) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            object_ids = [
                str(row[0])
                for row in conn.execute(
                    "SELECT object_id FROM memory_object_refs WHERE ref_type = ? AND ref_id = ?",
                    (ref_type, ref_id),
                ).fetchall()
            ]
            conn.execute(
                "DELETE FROM memory_object_refs WHERE ref_type = ? AND ref_id = ?",
                (ref_type, ref_id),
            )
            unreferenced: list[tuple[str, str]] = []
            for object_id in object_ids:
                if conn.execute(
                    "SELECT 1 FROM memory_object_refs WHERE object_id = ? LIMIT 1", (object_id,)
                ).fetchone() is None:
                    row = conn.execute(
                        "SELECT path_token FROM memory_objects WHERE object_id = ?", (object_id,)
                    ).fetchone()
                    if row:
                        unreferenced.append((object_id, str(row["path_token"])))
                        conn.execute("DELETE FROM memory_objects WHERE object_id = ?", (object_id,))
        deleted = 0
        for _object_id, token in unreferenced:
            if token.startswith("pack-"):
                deleted += self._pack_delete(token)
            else:
                path = self._path(token)
                if path.exists() and not path.is_symlink():
                    path.unlink()
                    deleted += 1
        return {
            "references_removed": len(object_ids),
            "unreferenced_objects_deleted": deleted,
            "content_retained_in_receipt": False,
        }

    def purge_reference_ids(self, object_ref_ids: list[str]) -> dict[str, Any]:
        """Remove an exact caller-owned reference set during atomic rollback."""

        bounded = sorted({str(value) for value in object_ref_ids if str(value)})
        if not bounded:
            return {
                "references_removed": 0,
                "unreferenced_objects_deleted": 0,
                "content_retained_in_receipt": False,
            }
        placeholders = ",".join("?" for _ in bounded)
        with self.repository.transaction() as conn:
            object_ids = [
                str(row[0])
                for row in conn.execute(
                    f"SELECT object_id FROM memory_object_refs WHERE object_ref_id IN ({placeholders})",
                    bounded,
                ).fetchall()
            ]
            removed = conn.execute(
                f"DELETE FROM memory_object_refs WHERE object_ref_id IN ({placeholders})",
                bounded,
            ).rowcount
            unreferenced: list[tuple[str, str]] = []
            for object_id in sorted(set(object_ids)):
                if conn.execute(
                    "SELECT 1 FROM memory_object_refs WHERE object_id = ? LIMIT 1",
                    (object_id,),
                ).fetchone() is not None:
                    continue
                row = conn.execute(
                    "SELECT path_token FROM memory_objects WHERE object_id = ?",
                    (object_id,),
                ).fetchone()
                if row is not None:
                    unreferenced.append((object_id, str(row["path_token"])))
                    conn.execute(
                        "DELETE FROM memory_objects WHERE object_id = ?", (object_id,)
                    )
        deleted = 0
        for _object_id, token in unreferenced:
            if token.startswith("pack-"):
                deleted += self._pack_delete(token)
            else:
                path = self._path(token)
                if path.exists() and not path.is_symlink():
                    path.unlink()
                    deleted += 1
        return {
            "references_removed": int(removed),
            "unreferenced_objects_deleted": deleted,
            "content_retained_in_receipt": False,
        }


__all__ = ("MemoryObjectError", "MemoryObjectStore", "OBJECT_FORMAT")
