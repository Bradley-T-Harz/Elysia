"""Versioned, verified, recoverable local application lifecycle transactions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import sqlite3
import tarfile
import tempfile
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .paths import ElysiaPaths, resolve_elysia_paths
from .release_trust import ReleaseArtifactManifest, ReleaseTrustError, verify_release_artifact
from .component_install_service import ComponentInstallError, ComponentInstallService


LIFECYCLE_CONTRACT_VERSION = "elysia-application-lifecycle-1.0"
PREVIEW_TTL_SECONDS = 900
Operation = Literal[
    "update", "repair", "rollback", "uninstall_preserve",
    "export_then_remove", "purge_local_data",
]
EXPORT_REMOVE_CONFIRMATION = "EXPORT THEN REMOVE ALL LOCAL ELYSIA DATA"
PURGE_CONFIRMATION = "PURGE ALL LOCAL ELYSIA DATA"


class LifecycleError(RuntimeError):
    """A lifecycle plan or transaction failed closed."""


class LifecyclePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation: Operation
    artifact_path: str | None = Field(default=None, max_length=4096)
    manifest_path: str | None = Field(default=None, max_length=4096)
    signature_path: str | None = Field(default=None, max_length=4096)
    target_release_id: str | None = Field(default=None, max_length=128)
    export_path: str | None = Field(default=None, max_length=4096)
    destructive_confirmation: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_operation_inputs(self) -> "LifecyclePreviewRequest":
        supplied = (self.artifact_path, self.manifest_path, self.signature_path)
        if self.operation in {"update", "repair"} and not all(supplied):
            raise ValueError("Update and repair require exact artifact, manifest, and signature files.")
        if self.operation == "rollback" and not self.target_release_id:
            raise ValueError("Rollback requires an exact prior release identifier.")
        if self.operation in {"rollback", "uninstall_preserve", "export_then_remove", "purge_local_data"} and any(supplied):
            raise ValueError("This lifecycle operation does not accept an artifact.")
        if self.operation == "export_then_remove":
            if not self.export_path or self.destructive_confirmation != EXPORT_REMOVE_CONFIRMATION:
                raise ValueError("Export-then-remove requires an exact export path and typed destructive confirmation.")
        elif self.export_path:
            raise ValueError("Only export-then-remove accepts an export path.")
        if self.operation == "purge_local_data" and self.destructive_confirmation != PURGE_CONFIRMATION:
            raise ValueError("Total local-data purge requires its exact typed destructive confirmation.")
        if self.operation not in {"export_then_remove", "purge_local_data"} and self.destructive_confirmation:
            raise ValueError("This lifecycle operation does not accept destructive confirmation.")
        return self


class LifecycleApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    preview_id: str = Field(pattern=r"^lifecycle_[a-f0-9]{24}$")
    approval_token: str = Field(min_length=32, max_length=256)
    operator_approved: bool


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LifecycleError("A lifecycle preview timestamp is invalid.") from exc
    if parsed.tzinfo is None:
        raise LifecycleError("A lifecycle preview timestamp lacks UTC authority.")
    return parsed.astimezone(UTC)


def _private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}-", delete=False
    ) as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def _read_private_json(path: Path, *, description: str) -> dict[str, Any]:
    try:
        stat = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise LifecycleError(f"The {description} is not a safe regular file.")
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise LifecycleError(f"The {description} has unsafe ownership or permissions.")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except LifecycleError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"The {description} is unavailable or invalid.") from exc
    if not isinstance(payload, dict):
        raise LifecycleError(f"The {description} is invalid.")
    return payload


def _safe_local_file(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise LifecycleError("A lifecycle input is not a safe regular local file.")
    return path.resolve(strict=True)


def _safe_release_id(value: str) -> str:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-" for character in value):
        raise LifecycleError("A release identifier is unsafe.")
    return value


def _inventory_digest(root: Path, relative_path: str) -> str:
    candidate = root / relative_path
    if not candidate.is_file() or candidate.is_symlink():
        raise LifecycleError("A signed package-owned file is missing or unsafe.")
    return sha256(candidate.read_bytes()).hexdigest()


def _extract_verified_payload(
    artifact: Path,
    staging: Path,
    manifest: ReleaseArtifactManifest,
) -> None:
    staging.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        with tarfile.open(artifact, mode="r:*") as archive:
            members = archive.getmembers()
            for member in members:
                pure = PurePosixPath(member.name)
                if (
                    pure.is_absolute()
                    or ".." in pure.parts
                    or not pure.parts
                    or pure.parts[0] != "payload"
                    or member.issym()
                    or member.islnk()
                    or member.isdev()
                ):
                    raise LifecycleError("The release archive contains an unsafe entry.")
            archive.extractall(staging, members=members, filter="data")
        payload = staging / "payload"
        observed_files = {
            path.relative_to(payload).as_posix()
            for path in payload.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        if observed_files != set(manifest.file_inventory):
            raise LifecycleError("The release archive file inventory differs from its signed manifest.")
        for relative_path, expected in manifest.file_inventory.items():
            pure = PurePosixPath(relative_path)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise LifecycleError("The signed file inventory contains an unsafe path.")
            if _inventory_digest(payload, relative_path) != expected:
                raise LifecycleError("A package-owned file hash differs from its signed manifest.")
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


class LifecycleService:
    def __init__(
        self,
        paths: ElysiaPaths | None = None,
        *,
        trust_policy_path: Path | None = None,
        doctor_runner: Callable[[ElysiaPaths], bool] | None = None,
        migration_runner: Callable[[ElysiaPaths, int], int] | None = None,
        governance_provider: Callable[[], dict[str, Any]] | None = None,
        fail_after_phase: str | None = None,
    ) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.runtime_root = self.paths.data_dir / "runtime"
        self.releases_root = self.runtime_root / "releases"
        self.current_link = self.runtime_root / "current"
        self.lifecycle_root = self.paths.state_dir / "lifecycle"
        self.preview_root = self.lifecycle_root / "previews"
        self.receipt_root = self.lifecycle_root / "releases"
        self.checkpoint_root = self.lifecycle_root / "checkpoints"
        self.recovery_root = self.lifecycle_root / "recoverable-application"
        self.interrupted_path = self.lifecycle_root / "interrupted.json"
        self.trust_policy_path = trust_policy_path or (
            Path(__file__).resolve().parents[2] / "config" / "install" / "update_trust.yaml"
        )
        self.doctor_runner = doctor_runner or self._default_doctor
        self.migration_runner = migration_runner or self._default_migration
        self.governance_provider = governance_provider or self._default_governance
        self.fail_after_phase = fail_after_phase

    @staticmethod
    def _default_doctor(paths: ElysiaPaths) -> bool:
        from .doctor_service import run_doctor

        return bool(run_doctor(paths=paths, api_reachable=True).core_ready)

    @staticmethod
    def _default_migration(paths: ElysiaPaths, target_schema: int) -> int:
        from app.memory.canonical_repository import CanonicalMemoryRepository, SCHEMA_VERSION

        if target_schema != SCHEMA_VERSION:
            raise LifecycleError(
                "The signed candidate targets a memory schema this installed updater cannot migrate."
            )
        repository = CanonicalMemoryRepository(paths=paths)
        repository.initialize()
        return int(repository.health()["schema_version"])

    @staticmethod
    def _default_governance() -> dict[str, Any]:
        from app.api import account_service

        return account_service.get_authenticated_governance()

    def _local_admin_actor(self) -> dict[str, str]:
        try:
            actor = self.governance_provider()
        except Exception as exc:
            raise LifecycleError(
                "A valid Local Admin or Installation Owner session is required for lifecycle authority."
            ) from exc
        role = str(actor.get("role") or "")
        user_id = str(actor.get("user_id") or "")
        if role not in {"installation_owner", "admin"} or not user_id:
            raise LifecycleError(
                "Only the Local Admin or Installation Owner may initiate update, repair, rollback, or removal."
            )
        return {"user_id": user_id, "role": role}

    def _phase(self, name: str) -> None:
        if self.fail_after_phase == name:
            raise LifecycleError(f"Injected interruption after {name}.")

    def _current_release_id(self) -> str | None:
        if not self.current_link.is_symlink():
            return None
        try:
            target = self.current_link.resolve(strict=True)
            target.relative_to(self.releases_root.resolve(strict=True))
        except (OSError, ValueError):
            return None
        return target.name

    def _memory_schema(self) -> int:
        database = self.paths.memory_database_path
        if not database.exists():
            return 0
        if not database.is_file() or database.is_symlink():
            raise LifecycleError("Canonical memory is not a safe regular database.")
        try:
            with sqlite3.connect(
                f"file:{database.as_posix()}?mode=ro", uri=True, timeout=1.0
            ) as connection:
                return int(connection.execute(
                    "SELECT COALESCE(MAX(schema_version),0) FROM schema_migrations"
                ).fetchone()[0])
        except sqlite3.Error as exc:
            raise LifecycleError("Canonical memory schema could not be verified read-only.") from exc

    def _release_receipt(self, release_id: str) -> dict[str, Any]:
        path = self.receipt_root / f"{_safe_release_id(release_id)}.json"
        payload = _read_private_json(path, description="selected release lifecycle receipt")
        if payload.get("release_id") != release_id:
            raise LifecycleError("The selected release receipt identity is invalid.")
        return payload

    def _owned_roots(self) -> list[tuple[str, Path]]:
        candidates = [
            ("config", self.paths.config_dir),
            ("data", self.paths.data_dir),
            ("state", self.paths.state_dir),
            ("cache", self.paths.cache_dir),
            ("runtime", self.paths.runtime_dir),
        ]
        resolved: list[tuple[str, Path]] = []
        for label, path in candidates:
            absolute = path.resolve(strict=False)
            if not absolute.is_absolute() or absolute.name != "elysia" or absolute == absolute.parent:
                raise LifecycleError("A local-data lifecycle root is outside the bounded Elysia namespace.")
            if any(absolute == existing or absolute in existing.parents for _, existing in resolved):
                continue
            if any(existing in absolute.parents for _, existing in resolved):
                raise LifecycleError("Local-data lifecycle roots overlap unsafely.")
            resolved.append((label, absolute))
        return resolved

    def _local_data_inventory(self) -> dict[str, Any]:
        file_count = 0
        exact_bytes = 0
        roots_present = 0
        for _, root in self._owned_roots():
            if not root.exists():
                continue
            if not root.is_dir() or root.is_symlink():
                raise LifecycleError("An Elysia local-data root is not a safe directory.")
            roots_present += 1
            for path in root.rglob("*"):
                if path.is_symlink():
                    raise LifecycleError("A local-data export/purge root contains a symlink and fails closed.")
                if path.is_file():
                    file_count += 1
                    exact_bytes += path.stat().st_size
        return {"root_count": roots_present, "file_count": file_count, "exact_bytes": exact_bytes}

    def _safe_export_target(self, value: str) -> Path:
        target = Path(value).expanduser()
        if not target.is_absolute() or target.exists() or target.suffix not in {".gz", ".tgz"}:
            raise LifecycleError("The private export target must be a new absolute .tar.gz or .tgz path.")
        parent = target.parent.resolve(strict=True)
        if not parent.is_dir() or parent.is_symlink():
            raise LifecycleError("The private export parent is unsafe.")
        resolved_target = parent / target.name
        if any(resolved_target == root or root in resolved_target.parents for _, root in self._owned_roots()):
            raise LifecycleError("The private export must be stored outside Elysia local-data roots.")
        return resolved_target

    def state(self) -> dict[str, Any]:
        current = self._current_release_id()
        releases = []
        if self.receipt_root.is_dir():
            for path in sorted(self.receipt_root.glob("*.json")):
                try:
                    payload = _read_private_json(path, description="release lifecycle receipt")
                except LifecycleError:
                    continue
                releases.append({
                    "release_id": payload.get("release_id"),
                    "version": payload.get("version"),
                    "active": payload.get("release_id") == current,
                    "verified": payload.get("verified") is True,
                    "rollback_compatible": (
                        int(payload.get("minimum_memory_schema", -1)) <= self._memory_schema()
                        <= int(payload.get("maximum_memory_schema", -1))
                    ),
                })
        return {
            "contract_version": LIFECYCLE_CONTRACT_VERSION,
            "current_release_id": current,
            "installed": current is not None,
            "releases": releases,
            "incomplete_operation_detected": self.interrupted_path.is_file(),
            "incomplete_operation_recovery": (
                "A new exact update/repair may recover the preserved prior release; a successful transaction clears the marker."
                if self.interrupted_path.is_file()
                else "not_required"
            ),
            "update_verification_configured": self.trust_policy_path.is_file(),
            "user_data_preserved_by_default": True,
            "raw_paths_exposed": False,
        }

    def _verified_candidate(self, request: LifecyclePreviewRequest) -> tuple[ReleaseArtifactManifest, dict[str, str]]:
        artifact = _safe_local_file(str(request.artifact_path))
        manifest_path = _safe_local_file(str(request.manifest_path))
        signature = _safe_local_file(str(request.signature_path))
        try:
            manifest = verify_release_artifact(
                artifact_path=artifact,
                manifest_path=manifest_path,
                signature_path=signature,
                trust_policy_path=self.trust_policy_path,
            )
        except ReleaseTrustError as exc:
            raise LifecycleError(str(exc)) from exc
        schema = self._memory_schema()
        if not (manifest.minimum_memory_schema <= schema <= manifest.maximum_memory_schema):
            raise LifecycleError("The signed candidate is incompatible with current user-data schema.")
        return manifest, {
            "artifact_path": str(artifact),
            "manifest_path": str(manifest_path),
            "signature_path": str(signature),
        }

    def preview(self, request: LifecyclePreviewRequest) -> dict[str, Any]:
        actor = self._local_admin_actor()
        current = self._current_release_id()
        private: dict[str, Any] = {}
        public: dict[str, Any] = {
            "operation": request.operation,
            "current_release_id": current,
            "user_data_preserved": True,
            "network_used": False,
            "silent_privilege": False,
            "raw_paths_exposed": False,
            "incomplete_operation_detected": self.interrupted_path.is_file(),
            "mutation_authority": "local_admin_explicit",
            "local_admin_authorized": True,
            "silent_update_allowed": False,
        }
        if request.operation in {"update", "repair"}:
            manifest, private = self._verified_candidate(request)
            public.update({
                "target_release_id": manifest.release_id,
                "target_version": manifest.version,
                "artifact_sha256": manifest.artifact_sha256,
                "artifact_size_bytes": manifest.artifact_size_bytes,
                "file_count": len(manifest.file_inventory),
                "memory_schema_compatible": True,
                "current_memory_schema": self._memory_schema(),
                "target_memory_schema": (
                    manifest.memory_schema_target
                    if manifest.memory_schema_target is not None
                    else self._memory_schema()
                ),
                "memory_migration_ids": list(manifest.memory_migration_ids),
                "component_changes": list(manifest.component_changes),
                "checkpoint_required": True,
                "signature_verified": True,
            })
            private["release_manifest"] = manifest.model_dump(mode="json")
        elif request.operation == "rollback":
            target = _safe_release_id(str(request.target_release_id))
            receipt = self._release_receipt(target)
            schema = self._memory_schema()
            if not (
                int(receipt["minimum_memory_schema"]) <= schema
                <= int(receipt["maximum_memory_schema"])
            ):
                raise LifecycleError("Rollback would cross an incompatible user-data schema boundary.")
            release_dir = self.releases_root / target
            if not release_dir.is_dir() or release_dir.is_symlink():
                raise LifecycleError("The rollback payload is missing or unsafe.")
            public.update({
                "target_release_id": target,
                "target_version": receipt.get("version"),
                "memory_schema_compatible": True,
                "checkpoint_required": True,
                "signature_verified": receipt.get("verified") is True,
            })
            private["target_release_id"] = target
        elif request.operation == "uninstall_preserve":
            public.update({
                "target_release_id": None,
                "application_payload_removed": True,
                "profiles_memory_projects_conversations_preserved": True,
                "models_and_external_vaults_preserved": True,
                "recoverable_application_state": True,
            })
        else:
            inventory = self._local_data_inventory()
            public.update({
                "target_release_id": None,
                "destructive_user_data_removal": True,
                "identity_memory_projects_conversations_removed": True,
                "model_vaults_inside_elysia_data_removed": True,
                "external_model_vaults_removed": False,
                "local_data_inventory": inventory,
                "typed_confirmation_matched": True,
                "recoverable_application_state": False,
            })
            private["destructive_confirmation"] = request.destructive_confirmation
            if request.operation == "export_then_remove":
                export = self._safe_export_target(str(request.export_path))
                public.update({
                    "private_export_created_before_removal": True,
                    "export_encrypted": False,
                    "export_permissions": "0600",
                    "operator_must_protect_export": True,
                })
                private["export_path"] = str(export)
        private["actor_user_id"] = actor["user_id"]
        private["actor_role"] = actor["role"]
        preview_id = f"lifecycle_{secrets.token_hex(12)}"
        token = secrets.token_urlsafe(32)
        created = datetime.now(UTC).replace(microsecond=0)
        _private_json(self.preview_root / f"{preview_id}.json", {
            "preview_id": preview_id,
            "approval_token_hash": sha256(token.encode()).hexdigest(),
            "created_at_utc": created.isoformat().replace("+00:00", "Z"),
            "expires_at_utc": (created + timedelta(seconds=PREVIEW_TTL_SECONDS)).isoformat().replace("+00:00", "Z"),
            "public": public,
            "private": private,
        })
        return {**public, "preview_id": preview_id, "approval_token": token, "mutation_performed": False}

    def _load_preview(self, request: LifecycleApplyRequest) -> tuple[Path, dict[str, Any]]:
        if not request.operator_approved:
            raise LifecycleError("Lifecycle apply requires explicit Local Admin approval.")
        actor = self._local_admin_actor()
        path = self.preview_root / f"{request.preview_id}.json"
        payload = _read_private_json(path, description="exact lifecycle preview")
        if _parse_utc(str(payload["expires_at_utc"])) < datetime.now(UTC):
            raise LifecycleError("The lifecycle preview expired.")
        if not secrets.compare_digest(
            str(payload["approval_token_hash"]), sha256(request.approval_token.encode()).hexdigest()
        ):
            raise LifecycleError("The lifecycle approval token is invalid.")
        private = payload.get("private")
        if not isinstance(private, dict) or not secrets.compare_digest(
            str(private.get("actor_user_id") or ""), actor["user_id"]
        ):
            raise LifecycleError("Lifecycle approval is bound to the initiating Local Admin session.")
        return path, payload

    def _checkpoint(self, operation_id: str) -> dict[str, Any]:
        checkpoint = self.checkpoint_root / operation_id
        checkpoint.mkdir(mode=0o700, parents=True, exist_ok=False)
        memory = self.paths.memory_database_path
        memory_backup = False
        if memory.is_file() and not memory.is_symlink():
            with sqlite3.connect(
                f"file:{memory.as_posix()}?mode=ro", uri=True, timeout=1.0
            ) as source, sqlite3.connect(checkpoint / "memory.sqlite") as target:
                source.backup(target)
            (checkpoint / "memory.sqlite").chmod(0o600)
            memory_backup = True
        _private_json(checkpoint / "checkpoint.json", {
            "operation_id": operation_id,
            "current_release_id": self._current_release_id(),
            "memory_schema": self._memory_schema(),
            "memory_backup_present": memory_backup,
            "user_data_mutated": False,
            "created_at_utc": _utc_now(),
        })
        return {
            "operation_id": operation_id,
            "memory_backup_present": memory_backup,
            "user_data_mutated": False,
        }

    def _restore_memory_checkpoint(self, operation_id: str) -> None:
        checkpoint = self.checkpoint_root / _safe_release_id(operation_id) / "memory.sqlite"
        database = self.paths.memory_database_path
        if not checkpoint.is_file() or checkpoint.is_symlink():
            return
        database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = database.with_name(f".{database.name}.lifecycle-restore-{secrets.token_hex(6)}")
        source = sqlite3.connect(checkpoint)
        target = sqlite3.connect(temporary)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        temporary.chmod(0o600)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{database}{suffix}")
            if sidecar.exists() and not sidecar.is_symlink():
                sidecar.unlink()
        os.replace(temporary, database)

    def _activate(self, release_id: str) -> None:
        self.runtime_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        relative = f"releases/{release_id}"
        temporary = self.runtime_root / f".current-{secrets.token_hex(8)}"
        temporary.symlink_to(relative)
        os.replace(temporary, self.current_link)

    def _record_interrupted(self, operation: str, prior: str | None, phase: str) -> None:
        _private_json(self.interrupted_path, {
            "operation": operation,
            "prior_release_id": prior,
            "failed_phase": phase,
            "recoverable": True,
            "user_data_mutated": False,
            "recorded_at_utc": _utc_now(),
        })

    def _apply_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        public = payload["public"]
        private = payload["private"]
        operation = str(public["operation"])
        prior = self._current_release_id()
        manifest = ReleaseArtifactManifest.model_validate(private["release_manifest"])
        artifact = Path(private["artifact_path"])
        manifest_path = Path(private["manifest_path"])
        signature_path = Path(private["signature_path"])
        checkpoint: dict[str, Any] | None = None
        migration_started = False
        migration_performed = False
        try:
            verified = verify_release_artifact(
                artifact_path=artifact,
                manifest_path=manifest_path,
                signature_path=signature_path,
                trust_policy_path=self.trust_policy_path,
            )
            if verified != manifest:
                raise LifecycleError("The exact approved release manifest changed after preview.")
            self._phase("verify")
            operation_id = f"{operation}-{secrets.token_hex(8)}"
            checkpoint = self._checkpoint(operation_id)
            self._phase("checkpoint")
            base_release_id = _safe_release_id(f"{manifest.release_id}-{manifest.artifact_sha256[:12]}")
            final_release_id = base_release_id
            final_release = self.releases_root / final_release_id
            staging = self.releases_root / f".staging-{secrets.token_hex(12)}"
            self.releases_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            existing_valid = final_release.is_dir() and not final_release.is_symlink()
            if existing_valid:
                try:
                    existing_valid = all(
                        _inventory_digest(final_release, relative_path) == expected
                        for relative_path, expected in manifest.file_inventory.items()
                    )
                except LifecycleError:
                    existing_valid = False
            if operation == "repair" or (final_release.exists() and not existing_valid):
                final_release_id = _safe_release_id(
                    f"{base_release_id}.repair.{secrets.token_hex(4)}"
                )
                final_release = self.releases_root / final_release_id
                existing_valid = False
            if not existing_valid:
                _extract_verified_payload(artifact, staging, manifest)
                self._phase("staging")
                (staging / "payload").replace(final_release)
                staging.rmdir()
            for relative_path, expected in manifest.file_inventory.items():
                if _inventory_digest(final_release, relative_path) != expected:
                    raise LifecycleError("The staged release failed final package integrity.")
            self._phase("package_integrity")
            before_schema = self._memory_schema()
            target_schema = (
                manifest.memory_schema_target
                if manifest.memory_schema_target is not None
                else before_schema
            )
            if target_schema != before_schema:
                if not manifest.memory_migration_ids:
                    raise LifecycleError(
                        "A schema-changing release lacks a signed migration plan."
                    )
                migration_started = True
                observed_schema = self.migration_runner(self.paths, target_schema)
                if observed_schema != target_schema or self._memory_schema() != target_schema:
                    raise LifecycleError(
                        "The transactional memory migration did not reach its signed target schema."
                    )
                migration_performed = True
            self._phase("migration")
            _private_json(self.receipt_root / f"{final_release_id}.json", {
                "release_id": final_release_id,
                "signed_release_id": manifest.release_id,
                "version": manifest.version,
                "artifact_sha256": manifest.artifact_sha256,
                "file_inventory": manifest.file_inventory,
                "component_graph_sha256": manifest.component_graph_sha256,
                "minimum_memory_schema": manifest.minimum_memory_schema,
                "maximum_memory_schema": manifest.maximum_memory_schema,
                "memory_schema_before": before_schema,
                "memory_schema_target": target_schema,
                "memory_migration_ids": manifest.memory_migration_ids,
                "component_changes": manifest.component_changes,
                "verified": True,
                "installed_at_utc": _utc_now(),
            })
            self._activate(final_release_id)
            self._phase("activation")
            if not self.doctor_runner(self.paths):
                if prior:
                    self._activate(prior)
                else:
                    self.current_link.unlink(missing_ok=True)
                raise LifecycleError("Post-activation Doctor failed; the prior healthy release was restored.")
            self._phase("doctor")
            self.interrupted_path.unlink(missing_ok=True)
            return {
                "operation": operation,
                "applied": True,
                "prior_release_id": prior,
                "current_release_id": final_release_id,
                "signature_verified": True,
                "checkpoint": checkpoint,
                "memory_schema_before": before_schema,
                "memory_schema_after": self._memory_schema(),
                "memory_migration_ids": list(manifest.memory_migration_ids),
                "migration_performed": migration_performed,
                "doctor_passed": True,
                "atomic_activation": True,
                "user_data_preserved": True,
                "raw_paths_exposed": False,
            }
        except Exception as exc:
            phase = str(exc)
            if self._current_release_id() != prior:
                if prior:
                    self._activate(prior)
                else:
                    self.current_link.unlink(missing_ok=True)
            if migration_started and checkpoint and checkpoint.get("memory_backup_present"):
                self._restore_memory_checkpoint(str(checkpoint["operation_id"]))
            self._record_interrupted(operation, prior, phase[:200])
            if isinstance(exc, LifecycleError):
                raise
            raise LifecycleError("The lifecycle transaction failed and retained/restored prior state.") from exc

    def _apply_rollback(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = str(payload["private"]["target_release_id"])
        prior = self._current_release_id()
        self._release_receipt(target)
        checkpoint = self._checkpoint(f"rollback-{secrets.token_hex(8)}")
        self._activate(target)
        if not self.doctor_runner(self.paths):
            if prior:
                self._activate(prior)
            else:
                self.current_link.unlink(missing_ok=True)
            raise LifecycleError("Rollback Doctor failed; the prior release was restored.")
        self.interrupted_path.unlink(missing_ok=True)
        return {
            "operation": "rollback",
            "applied": True,
            "prior_release_id": prior,
            "current_release_id": target,
            "checkpoint": checkpoint,
            "doctor_passed": True,
            "user_data_preserved": True,
            "raw_paths_exposed": False,
        }

    def _apply_uninstall_preserve(self) -> dict[str, Any]:
        if not self.runtime_root.exists():
            return {
                "operation": "uninstall_preserve",
                "applied": True,
                "application_payload_removed": False,
                "already_absent": True,
                "user_data_preserved": True,
                "raw_paths_exposed": False,
            }
        try:
            component_result = ComponentInstallService(self.paths).uninstall_managed_optional_components()
        except ComponentInstallError as exc:
            raise LifecycleError(str(exc)) from exc
        self.recovery_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.recovery_root / f"runtime-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
        self.runtime_root.replace(target)
        _private_json(self.lifecycle_root / "uninstall-receipt.json", {
            "contract_version": LIFECYCLE_CONTRACT_VERSION,
            "application_payload_removed": True,
            "recoverable": True,
            "user_data_preserved": True,
            "identity_memory_projects_conversations_deleted": False,
            "removed_at_utc": _utc_now(),
        })
        return {
            "operation": "uninstall_preserve",
            "applied": True,
            "application_payload_removed": True,
            "recoverable": True,
            "user_data_preserved": True,
            "optional_components": component_result,
            "raw_paths_exposed": False,
        }

    def _create_private_export(self, target: Path) -> dict[str, Any]:
        temporary = target.parent / f".{target.name}-{secrets.token_hex(8)}.tmp"
        try:
            with tarfile.open(temporary, "w:gz") as archive:
                for label, root in self._owned_roots():
                    if root.is_dir() and not root.is_symlink():
                        archive.add(root, arcname=label, recursive=True)
            with tarfile.open(temporary, "r:gz") as archive:
                members = archive.getmembers()
                if any(
                    PurePosixPath(member.name).is_absolute()
                    or ".." in PurePosixPath(member.name).parts
                    or member.issym() or member.islnk() or member.isdev()
                    for member in members
                ):
                    raise LifecycleError("The private export failed safe archive verification.")
            digest_state = sha256()
            with temporary.open("rb") as handle:
                while chunk := handle.read(8 * 1024 * 1024):
                    digest_state.update(chunk)
            digest = digest_state.hexdigest()
            size = temporary.stat().st_size
            temporary.chmod(0o600)
            temporary.replace(target)
            return {"sha256": digest, "size_bytes": size, "file_count": len(members), "permissions": "0600"}
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _purge_owned_roots(self) -> dict[str, Any]:
        roots = self._owned_roots()
        quarantine_parent = Path(tempfile.mkdtemp(prefix="elysia-purge-", dir=self.paths.state_dir.parent))
        quarantine_parent.chmod(0o700)
        moved: list[tuple[Path, Path]] = []
        try:
            for label, root in roots:
                if root.exists():
                    destination = quarantine_parent / label
                    root.replace(destination)
                    moved.append((root, destination))
            for _, destination in moved:
                shutil.rmtree(destination)
            quarantine_parent.rmdir()
        except Exception as exc:
            for root, destination in reversed(moved):
                if destination.exists() and not root.exists():
                    root.parent.mkdir(parents=True, exist_ok=True)
                    destination.replace(root)
            if quarantine_parent.exists() and not any(quarantine_parent.iterdir()):
                quarantine_parent.rmdir()
            raise LifecycleError("Total local-data removal failed; moved roots were restored where possible.") from exc
        return {
            "purged_root_count": len(moved),
            "identity_memory_projects_conversations_removed": True,
            "external_model_vaults_removed": False,
            "recoverable": False,
        }

    def _apply_destructive_removal(self, payload: dict[str, Any]) -> dict[str, Any]:
        operation = str(payload["public"]["operation"])
        confirmation = str(payload["private"].get("destructive_confirmation") or "")
        expected = EXPORT_REMOVE_CONFIRMATION if operation == "export_then_remove" else PURGE_CONFIRMATION
        if not secrets.compare_digest(confirmation, expected):
            raise LifecycleError("The destructive confirmation changed after preview.")
        export_receipt = None
        if operation == "export_then_remove":
            target = self._safe_export_target(str(payload["private"]["export_path"]))
            export_receipt = self._create_private_export(target)
        purge = self._purge_owned_roots()
        return {
            "operation": operation,
            "applied": True,
            "private_export": export_receipt,
            "local_data": purge,
            "user_data_preserved": operation == "export_then_remove",
            "raw_paths_exposed": False,
        }

    def apply(self, request: LifecycleApplyRequest) -> dict[str, Any]:
        preview_path, payload = self._load_preview(request)
        operation = str(payload["public"]["operation"])
        if operation in {"update", "repair"}:
            result = self._apply_candidate(payload)
        elif operation == "rollback":
            result = self._apply_rollback(payload)
        elif operation == "uninstall_preserve":
            result = self._apply_uninstall_preserve()
        elif operation in {"export_then_remove", "purge_local_data"}:
            result = self._apply_destructive_removal(payload)
        else:
            raise LifecycleError("The approved lifecycle operation is unsupported.")
        preview_path.unlink(missing_ok=True)
        return result


__all__ = (
    "LIFECYCLE_CONTRACT_VERSION",
    "EXPORT_REMOVE_CONFIRMATION",
    "PURGE_CONFIRMATION",
    "LifecycleApplyRequest",
    "LifecycleError",
    "LifecyclePreviewRequest",
    "LifecycleService",
    "PREVIEW_TTL_SECONDS",
)
