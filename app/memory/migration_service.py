"""Locked, backed-up, validated migration into the canonical Memory Fabric."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Iterator

from app.ids import new_id
from app.install.paths import ElysiaPaths
from app.memory.canonical_models import (
    ActivationTier,
    MemoryCreateRequest,
    MemoryForm,
    MemoryPrincipal,
    MemoryPrivacy,
    MemoryScope,
    MemorySourceInput,
)
from app.memory.canonical_repository import MemoryRepository, utc_now
from app.memory.encryption_service import MemoryEncryptionService
from app.memory.fabric_service import MemoryFabricService, MemoryPolicyService
from app.memory.schemas.memory_item import MemoryItem


class MemoryMigrationError(RuntimeError):
    """Migration failed and the prior authority remains available."""


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


class MemoryMigrationService:
    def __init__(
        self,
        repository: MemoryRepository | None = None,
        *,
        legacy_roots: list[Path] | None = None,
    ) -> None:
        self.repository = repository or MemoryRepository()
        self.paths = self.repository.paths
        self.policy = MemoryPolicyService()
        self.legacy_roots = legacy_roots if legacy_roots is not None else self._default_legacy_roots()

    def _default_legacy_roots(self) -> list[Path]:
        repo_root = Path(__file__).resolve().parents[2]
        roots = [
            repo_root / "app" / "memory" / "stores",
            self.paths.memory_dir / "stores",
        ]
        releases = self.paths.data_dir / "runtime" / "releases"
        if releases.is_dir():
            roots.extend(sorted(releases.glob("*/app/memory/stores")))
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve(strict=False))
            if key not in seen:
                seen.add(key)
                unique.append(root)
        return unique

    def discover(self) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for root_index, root in enumerate(self.legacy_roots):
            if not root.is_dir():
                continue
            for path in sorted(root.glob("**/*.json")):
                if not path.is_file() or path.is_symlink():
                    continue
                payload = path.read_bytes()
                records.append(
                    {
                        "root_index": root_index,
                        "relative_path": path.relative_to(root).as_posix(),
                        "path": path,
                        "sha256": sha256(payload).hexdigest(),
                        "byte_size": len(payload),
                    }
                )
        return records

    @contextmanager
    def migration_lock(self) -> Iterator[None]:
        self.paths.memory_lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = self.paths.memory_lock_dir / "canonical-migration.lock"
        with lock_path.open("a+b") as handle:
            try:
                lock_path.chmod(0o600)
            except OSError:
                pass
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise MemoryMigrationError("Another Memory Fabric migration is active.") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def migrate(
        self,
        *,
        principal: MemoryPrincipal,
        password: str | None = None,
        fail_stage: str | None = None,
    ) -> dict[str, object]:
        with self.migration_lock():
            return self._migrate_locked(
                principal=principal,
                password=password,
                fail_stage=fail_stage,
            )

    def _migrate_locked(
        self,
        *,
        principal: MemoryPrincipal,
        password: str | None,
        fail_stage: str | None,
    ) -> dict[str, object]:
        self.repository.initialize()
        discovered = self.discover()
        if discovered:
            self.repository.mark_migration_required()
        with self.repository.connect() as conn:
            migrated_rows = conn.execute(
                "SELECT memory_id FROM memory_records WHERE legacy_class IS NOT NULL"
            ).fetchall()
        existing_legacy_ids = {str(row["memory_id"]) for row in migrated_rows}

        pending: list[tuple[dict[str, object], MemoryItem]] = []
        seen_ids: dict[str, str] = {}
        for entry in discovered:
            path = entry["path"]
            try:
                item = MemoryItem.model_validate_json(Path(path).read_text(encoding="utf-8"))
            except Exception as exc:
                raise MemoryMigrationError(
                    "A legacy memory record failed schema validation; no cutover occurred."
                ) from exc
            prior_hash = seen_ids.get(item.memory_id)
            if prior_hash and prior_hash != entry["sha256"]:
                raise MemoryMigrationError(
                    "Conflicting duplicate legacy memory IDs were found; no cutover occurred."
                )
            if prior_hash == entry["sha256"]:
                continue
            seen_ids[item.memory_id] = str(entry["sha256"])
            if item.memory_id not in existing_legacy_ids:
                pending.append((entry, item))

        if not pending:
            self.repository.clear_migration_required()
            result = {
                "state": "ready",
                "migration_required": False,
                "discovered_count": len(discovered),
                "migrated_count": len(existing_legacy_ids),
                "single_writer": True,
                "legacy_writer_active": False,
                "rollback_performed": False,
            }
            self._write_job_receipt(result)
            return result

        stamp = _timestamp()
        database = self.repository.database_path
        candidate = database.with_name(f"{database.name}.next")
        backup = self.paths.memory_backup_dir / f"pre-migration-{stamp}.sqlite"
        failed_candidate = self.paths.memory_checkpoints_dir / f"failed-candidate-{stamp}.sqlite"
        self.paths.memory_backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.paths.memory_checkpoints_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if candidate.exists():
            stale = self.paths.memory_checkpoints_dir / f"stale-candidate-{stamp}.sqlite"
            candidate.replace(stale)
            stale.chmod(0o600)

        self.repository.backup(backup)
        self.repository.backup(candidate)
        if fail_stage == "after_backup":
            candidate.replace(failed_candidate)
            failed_candidate.chmod(0o600)
            raise MemoryMigrationError("Injected migration failure after backup.")

        candidate_repository = MemoryRepository(paths=self.paths, database_path=candidate)
        candidate_repository.initialize()
        encryption = MemoryEncryptionService(candidate_repository)
        if any(item.memory_class.value == "sealed_private" for _, item in pending):
            if not password:
                candidate.replace(failed_candidate)
                failed_candidate.chmod(0o600)
                raise MemoryMigrationError(
                    "Sealed legacy memory requires explicit reauthentication before migration."
                )
            try:
                encryption.unlock_sealed(
                    principal=principal,
                    password=password,
                    ttl_seconds=900,
                )
            except Exception as exc:
                candidate.replace(failed_candidate)
                failed_candidate.chmod(0o600)
                raise MemoryMigrationError(
                    "Sealed legacy memory reauthentication failed; no cutover occurred."
                ) from exc
        fabric = MemoryFabricService(
            repository=candidate_repository,
            encryption=encryption,
            policy=self.policy,
        )
        try:
            for _, item in pending:
                fabric.create(
                    principal,
                    self._translate(item),
                    actor="migration_service",
                    legacy_memory_id=item.memory_id,
                    legacy_class=item.memory_class.value,
                )
            if fail_stage == "after_candidate_build":
                raise MemoryMigrationError("Injected migration failure after candidate build.")
            health = candidate_repository.health()
            with candidate_repository.connect() as conn:
                migrated_count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM memory_records WHERE legacy_class IS NOT NULL"
                    ).fetchone()[0]
                )
                duplicate_count = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) FROM (
                            SELECT memory_id FROM memory_records GROUP BY memory_id HAVING COUNT(*) > 1
                        )
                        """
                    ).fetchone()[0]
                )
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            expected_legacy_ids = existing_legacy_ids | set(seen_ids)
            if health["state"] != "ready" or duplicate_count or migrated_count != len(expected_legacy_ids):
                raise MemoryMigrationError("The candidate Memory Fabric failed validation.")
            if fail_stage == "before_cutover":
                raise MemoryMigrationError("Injected migration failure before cutover.")

            self._archive_legacy_sources(discovered, stamp)
            self._move_sidecars_to_checkpoint(database, stamp)
            os.replace(candidate, database)
            database.chmod(0o600)
            post_health = self.repository.health()
            if fail_stage == "after_cutover" or post_health["state"] != "ready":
                if database.exists():
                    database.replace(failed_candidate)
                shutil.copy2(backup, database)
                database.chmod(0o600)
                result = {
                    "state": "rolled_back",
                    "migration_required": True,
                    "discovered_count": len(discovered),
                    "migrated_count": 0,
                    "single_writer": True,
                    "legacy_writer_active": False,
                    "rollback_performed": True,
                    "reason_code": "post_cutover_doctor_failed",
                }
                self._write_job_receipt(result)
                raise MemoryMigrationError(
                    "Post-cutover Memory Fabric verification failed and the prior database was restored."
                )
        except Exception:
            if candidate.exists():
                candidate.replace(failed_candidate)
                failed_candidate.chmod(0o600)
            raise
        finally:
            encryption.relock(principal.user_id)

        result = {
            "state": "migrated",
            "migration_required": False,
            "discovered_count": len(discovered),
            "migrated_count": len(existing_legacy_ids | set(seen_ids)),
            "input_hash_manifest": True,
            "backup_created": True,
            "candidate_validated": True,
            "atomic_cutover": True,
            "single_writer": True,
            "legacy_writer_active": False,
            "rollback_performed": False,
        }
        self.repository.clear_migration_required()
        self._write_job_receipt(result)
        return result

    def _translate(self, item: MemoryItem) -> MemoryCreateRequest:
        mapping = self.policy.legacy_mapping(item.memory_class.value)
        privacy = mapping.get("privacy")
        if not privacy:
            privacy = (
                "sealed"
                if item.sensitivity.value == "sealed"
                else "private"
                if item.sensitivity.value == "private"
                else "normal"
            )
        status = {
            "active": "active",
            "archived": "archived",
            "superseded": "superseded",
            "provisional": "candidate",
            "blocked": "blocked",
        }[item.status.value]
        scope = mapping.get("scope", "user")
        if scope == "conversation" and not item.context_links.conversation_id:
            scope = "user"
        if scope == "project" and not item.context_links.project_id:
            scope = "user"
        return MemoryCreateRequest(
            title=item.title,
            body=item.body,
            why_stored=item.why_stored,
            scope=MemoryScope(scope),
            form=MemoryForm(mapping.get("form", "semantic")),
            subtype=mapping.get("subtype"),
            privacy=MemoryPrivacy(privacy),
            status=status,
            activation_tier=ActivationTier(mapping.get("activation_tier", "warm")),
            importance=item.importance,
            confidence=item.confidence,
            user_confirmed=(
                bool(item.flags.user_declared) if status != "candidate" else False
            ),
            inference_kind="legacy_inference" if item.flags.inferred else None,
            observed_at=item.source.captured_at_utc.isoformat(),
            conversation_id=item.context_links.conversation_id,
            project_id=item.context_links.project_id,
            request_id=item.context_links.request_id,
            source=MemorySourceInput(
                source_type=item.source.source_kind.value,
                source_id=item.source.source_ref,
                source_label=item.source.source_label,
                source_time=item.source.captured_at_utc.isoformat(),
                source_authority="legacy_memory_item",
                retrieval_method="legacy_json_migration",
                provenance_status="preserved",
            ),
        )

    def _archive_legacy_sources(self, discovered: list[dict[str, object]], stamp: str) -> None:
        archive = self.paths.memory_archive_dir / f"legacy-{stamp}"
        archive.mkdir(mode=0o700, parents=True, exist_ok=False)
        manifest: list[dict[str, object]] = []
        for index, entry in enumerate(discovered):
            source = Path(entry["path"])
            destination = archive / f"root-{entry['root_index']}" / str(entry["relative_path"])
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            destination.chmod(stat.S_IRUSR)
            # Cutover retires the legacy authority in place as a migration
            # input.  Keeping the source readable supports rollback/forensics;
            # removing its write bits makes the no-dual-writer contract true
            # at the filesystem boundary as well as in the service facade.
            source.chmod(stat.S_IRUSR)
            manifest.append(
                {
                    "entry_index": index,
                    "root_index": entry["root_index"],
                    "relative_path": entry["relative_path"],
                    "sha256": entry["sha256"],
                    "byte_size": entry["byte_size"],
                }
            )
        manifest_path = archive / "migration-manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "contract": "elysia-memory-legacy-migration-1",
                    "created_at_utc": utc_now(),
                    "source_count": len(discovered),
                    "sources": manifest,
                    "private_content_recorded": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path.chmod(0o400)

    def _move_sidecars_to_checkpoint(self, database: Path, stamp: str) -> None:
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{database}{suffix}")
            if sidecar.exists():
                destination = self.paths.memory_checkpoints_dir / f"pre-cutover-{stamp}{suffix}"
                sidecar.replace(destination)
                destination.chmod(0o600)

    def _write_job_receipt(self, result: dict[str, object]) -> None:
        self.paths.memory_jobs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        receipt = self.paths.memory_jobs_dir / "last-migration.json"
        payload = {
            "job_id": new_id("memjob"),
            "job_kind": "canonical_memory_migration",
            "recorded_at_utc": utc_now(),
            **result,
            "raw_paths_exposed": False,
            "private_content_recorded": False,
        }
        temporary = receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, receipt)

    def status(self) -> dict[str, object]:
        maintenance_active = False
        self.paths.memory_lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = self.paths.memory_lock_dir / "canonical-migration.lock"
        with lock_path.open("a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                maintenance_active = True
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        receipt = self.paths.memory_jobs_dir / "last-migration.json"
        migration_required_marker = self.repository.migration_required_marker.is_file()
        if not receipt.is_file():
            return {
                "state": "maintenance" if maintenance_active or migration_required_marker else "not_recorded",
                "maintenance_active": maintenance_active,
                "migration_required": migration_required_marker or bool(self.discover()),
                "writes_paused": migration_required_marker or maintenance_active,
                "single_writer": True,
                "legacy_writer_active": False,
                "raw_paths_exposed": False,
            }
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "state": "degraded",
                "maintenance_active": maintenance_active,
                "reason_code": "migration_receipt_unreadable",
                "single_writer": True,
                "legacy_writer_active": False,
                "raw_paths_exposed": False,
            }
        allowlist = {
            "state",
            "migration_required",
            "discovered_count",
            "migrated_count",
            "input_hash_manifest",
            "backup_created",
            "candidate_validated",
            "atomic_cutover",
            "single_writer",
            "legacy_writer_active",
            "rollback_performed",
            "reason_code",
            "recorded_at_utc",
        }
        return {key: value for key, value in data.items() if key in allowlist} | {
            "raw_paths_exposed": False,
            "maintenance_active": maintenance_active,
            "state": "maintenance" if maintenance_active else data.get("state", "not_recorded"),
            "migration_required": migration_required_marker or bool(data.get("migration_required", False)),
            "writes_paused": migration_required_marker or maintenance_active,
        }


def prepare_memory_authority_for_startup(paths: ElysiaPaths) -> dict[str, object]:
    """Stage migration before normal packaged operation without prompting.

    A password is never recovered or bypassed. If a pre-foundation account has
    no usable memory key, or sealed legacy input needs reauthentication, the API
    starts in truthful maintenance so Desktop can request the exact password.
    """
    repository = MemoryRepository(paths=paths)
    repository.initialize()
    migration = MemoryMigrationService(repository=repository)
    if not migration.discover():
        repository.clear_migration_required()
        return {
            "state": "ready",
            "migration_required": False,
            "writes_paused": False,
        }
    repository.mark_migration_required("packaged_startup_legacy_discovery")
    try:
        from app.api.account_service import AccountPaths, AccountStore

        identity_root = paths.identity_dir
        store = AccountStore(
            AccountPaths(
                identity_root=identity_root,
                database_path=identity_root / "elysia_identity.sqlite",
                profile_photo_dir=identity_root / "profile_photos",
                current_session_path=identity_root / "current_session.json",
                elysia_paths=paths,
            )
        )
        principal = MemoryPrincipal.model_validate(store.authenticated_principal())
        key_state = MemoryEncryptionService(repository).key_status(principal.user_id)
        if not bool(key_state["account_key_present"]):
            raise MemoryMigrationError("Account reauthentication is required.")
        result = migration.migrate(principal=principal, password=None)
        return {**result, "writes_paused": False}
    except Exception:
        return {
            "state": "maintenance",
            "migration_required": True,
            "writes_paused": True,
            "reauthentication_required": True,
            "raw_paths_exposed": False,
        }


__all__ = (
    "MemoryMigrationError",
    "MemoryMigrationService",
    "prepare_memory_authority_for_startup",
)
