from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import io
import json
from pathlib import Path
import sqlite3
import tarfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
import yaml

from app.install.lifecycle_service import (
    EXPORT_REMOVE_CONFIRMATION,
    LifecycleApplyRequest,
    LifecycleError,
    LifecyclePreviewRequest,
    LifecycleService,
    PURGE_CONFIRMATION,
)
from app.install.paths import ElysiaPaths, RuntimeMode
from app.install.release_trust import ReleaseArtifactManifest


def _paths(root: Path) -> ElysiaPaths:
    return ElysiaPaths(
        mode=RuntimeMode.TEST,
        config_dir=root / "config" / "elysia",
        data_dir=root / "data" / "elysia",
        cache_dir=root / "cache" / "elysia",
        state_dir=root / "state" / "elysia",
        runtime_dir=root / "run" / "elysia",
        runtime_fallback_used=False,
    )


def _admin_actor() -> dict[str, str]:
    return {"user_id": "synthetic-local-admin", "role": "installation_owner"}


def _service(
    paths: ElysiaPaths,
    *,
    trust_policy_path: Path,
    doctor_runner,
    **kwargs,
) -> LifecycleService:
    return LifecycleService(
        paths,
        trust_policy_path=trust_policy_path,
        doctor_runner=doctor_runner,
        governance_provider=_admin_actor,
        **kwargs,
    )


def _trust(root: Path) -> tuple[Ed25519PrivateKey, Path]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    path = root / "trust.yaml"
    now = datetime.now(UTC)
    path.write_text(yaml.safe_dump({
        "version": 1,
        "contract_version": "elysia-update-trust-1.0",
        "state": "active",
        "algorithm": "ed25519",
        "publisher": "EcoSyneva Commons LLC",
        "key_id": "disposable-lifecycle-test",
        "public_key_base64": base64.b64encode(public).decode("ascii"),
        "not_before_utc": (now - timedelta(hours=1)).isoformat(),
        "not_after_utc": (now + timedelta(hours=1)).isoformat(),
        "channel": "candidate",
        "notes": ["Disposable test key."],
    }), encoding="utf-8")
    return private, path


def _candidate(
    root: Path,
    private: Ed25519PrivateKey,
    release_id: str,
    content: bytes,
    *,
    memory_schema_target: int | None = None,
    memory_migration_ids: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    artifact = root / f"{release_id}.tar"
    with tarfile.open(artifact, "w") as archive:
        info = tarfile.TarInfo("payload/bin/elysia")
        info.mode = 0o700
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    now = datetime.now(UTC)
    manifest = ReleaseArtifactManifest(
        contract_version="elysia-release-artifact-manifest-1.0",
        publisher="EcoSyneva Commons LLC",
        product="Elysia",
        release_id=release_id,
        version="0.1.0",
        channel="candidate",
        signing_key_id="disposable-lifecycle-test",
        artifact_filename=artifact.name,
        artifact_sha256=sha256(artifact.read_bytes()).hexdigest(),
        artifact_size_bytes=artifact.stat().st_size,
        component_graph_sha256="b" * 64,
        minimum_memory_schema=0,
        maximum_memory_schema=99,
        memory_schema_target=memory_schema_target,
        memory_migration_ids=memory_migration_ids or [],
        component_changes=["desktop_shell:update"],
        created_at_utc=now.isoformat(),
        expires_at_utc=(now + timedelta(hours=1)).isoformat(),
        file_inventory={"bin/elysia": sha256(content).hexdigest()},
    )
    manifest_path = root / f"{release_id}.manifest.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    signature = root / f"{release_id}.sig"
    signature.write_text(base64.b64encode(private.sign(manifest.canonical_bytes())).decode("ascii"), encoding="ascii")
    return artifact, manifest_path, signature


def _apply(service: LifecycleService, candidate: tuple[Path, Path, Path], operation: str = "update") -> dict:
    preview = service.preview(LifecyclePreviewRequest(
        operation=operation,
        artifact_path=str(candidate[0]),
        manifest_path=str(candidate[1]),
        signature_path=str(candidate[2]),
    ))
    return service.apply(LifecycleApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))


def test_update_repair_rollback_and_uninstall_preserve_user_data(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "xdg")
    paths.memory_database_path.parent.mkdir(parents=True)
    with sqlite3.connect(paths.memory_database_path) as connection:
        connection.execute("CREATE TABLE schema_migrations(schema_version INTEGER)")
        connection.execute("INSERT INTO schema_migrations VALUES (4)")
        connection.execute("CREATE TABLE private_user_proof(value TEXT)")
        connection.execute("INSERT INTO private_user_proof VALUES ('preserve-me')")
    memory_hash = sha256(paths.memory_database_path.read_bytes()).hexdigest()
    private, trust = _trust(tmp_path)
    service = _service(paths, trust_policy_path=trust, doctor_runner=lambda _: True)

    first = _apply(service, _candidate(tmp_path, private, "release-a", b"first"))
    assert first["atomic_activation"] is True
    first_id = first["current_release_id"]
    second = _apply(service, _candidate(tmp_path, private, "release-b", b"second"))
    assert second["prior_release_id"] == first_id
    second_id = second["current_release_id"]

    active_file = service.current_link.resolve(strict=True) / "bin" / "elysia"
    active_file.write_bytes(b"corrupt")
    repaired = _apply(service, _candidate(tmp_path, private, "release-b", b"second"), "repair")
    assert (service.current_link.resolve(strict=True) / "bin" / "elysia").read_bytes() == b"second"
    assert repaired["doctor_passed"] is True

    rollback_preview = service.preview(LifecyclePreviewRequest(
        operation="rollback", target_release_id=first_id
    ))
    rollback = service.apply(LifecycleApplyRequest(
        preview_id=rollback_preview["preview_id"],
        approval_token=rollback_preview["approval_token"],
        operator_approved=True,
    ))
    assert rollback["current_release_id"] == first_id
    assert sha256(paths.memory_database_path.read_bytes()).hexdigest() == memory_hash

    uninstall_preview = service.preview(LifecyclePreviewRequest(operation="uninstall_preserve"))
    uninstalled = service.apply(LifecycleApplyRequest(
        preview_id=uninstall_preview["preview_id"],
        approval_token=uninstall_preview["approval_token"],
        operator_approved=True,
    ))
    assert uninstalled["user_data_preserved"] is True
    assert not service.runtime_root.exists()
    assert paths.memory_database_path.is_file()
    with sqlite3.connect(paths.memory_database_path) as connection:
        assert connection.execute("SELECT value FROM private_user_proof").fetchone()[0] == "preserve-me"


@pytest.mark.parametrize("phase", ["verify", "checkpoint", "staging", "package_integrity", "migration", "activation", "doctor"])
def test_interruption_never_leaves_half_current_or_changes_memory(tmp_path: Path, phase: str) -> None:
    paths = _paths(tmp_path / "xdg")
    paths.memory_database_path.parent.mkdir(parents=True)
    with sqlite3.connect(paths.memory_database_path) as connection:
        connection.execute("CREATE TABLE schema_migrations(schema_version INTEGER)")
        connection.execute("INSERT INTO schema_migrations VALUES (4)")
    memory_hash = sha256(paths.memory_database_path.read_bytes()).hexdigest()
    private, trust = _trust(tmp_path)
    healthy = _service(paths, trust_policy_path=trust, doctor_runner=lambda _: True)
    installed = _apply(healthy, _candidate(tmp_path, private, "healthy", b"healthy"))
    prior = installed["current_release_id"]
    interrupted = _service(
        paths,
        trust_policy_path=trust,
        doctor_runner=lambda _: True,
        fail_after_phase=phase,
    )
    with pytest.raises(LifecycleError):
        _apply(interrupted, _candidate(tmp_path, private, f"next-{phase}", b"new"))
    assert interrupted._current_release_id() == prior
    assert (interrupted.current_link.resolve(strict=True) / "bin" / "elysia").read_bytes() == b"healthy"
    assert sha256(paths.memory_database_path.read_bytes()).hexdigest() == memory_hash
    assert interrupted.state()["incomplete_operation_detected"] is True


def test_rollback_rejects_incompatible_memory_schema(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "xdg")
    paths.memory_database_path.parent.mkdir(parents=True)
    with sqlite3.connect(paths.memory_database_path) as connection:
        connection.execute("CREATE TABLE schema_migrations(schema_version INTEGER)")
        connection.execute("INSERT INTO schema_migrations VALUES (100)")
    service = _service(paths, trust_policy_path=tmp_path / "missing", doctor_runner=lambda _: True)
    service.receipt_root.mkdir(parents=True)
    release = service.releases_root / "old"
    release.mkdir(parents=True)
    (service.receipt_root / "old.json").write_text(json.dumps({
        "release_id": "old", "version": "0.1.0", "minimum_memory_schema": 0,
        "maximum_memory_schema": 4, "verified": True,
    }), encoding="utf-8")
    (service.receipt_root / "old.json").chmod(0o600)
    with pytest.raises(LifecycleError):
        service.preview(LifecyclePreviewRequest(operation="rollback", target_release_id="old"))


def test_schema_migration_is_previewed_and_restored_if_post_migration_doctor_fails(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path / "xdg")
    paths.memory_database_path.parent.mkdir(parents=True)
    with sqlite3.connect(paths.memory_database_path) as connection:
        connection.execute("CREATE TABLE schema_migrations(schema_version INTEGER)")
        connection.execute("INSERT INTO schema_migrations VALUES (3)")
        connection.execute("CREATE TABLE private_user_proof(value TEXT)")
        connection.execute("INSERT INTO private_user_proof VALUES ('preserve-me')")
    private, trust = _trust(tmp_path)

    def migrate(target_paths: ElysiaPaths, target: int) -> int:
        with sqlite3.connect(target_paths.memory_database_path) as connection:
            connection.execute("INSERT INTO schema_migrations VALUES (?)", (target,))
            connection.execute("UPDATE private_user_proof SET value='migrated'")
        return target

    service = _service(
        paths,
        trust_policy_path=trust,
        doctor_runner=lambda _: False,
        migration_runner=migrate,
    )
    candidate = _candidate(
        tmp_path,
        private,
        "schema-four",
        b"new",
        memory_schema_target=4,
        memory_migration_ids=["canonical_memory_schema_v4"],
    )
    preview = service.preview(LifecyclePreviewRequest(
        operation="update",
        artifact_path=str(candidate[0]),
        manifest_path=str(candidate[1]),
        signature_path=str(candidate[2]),
    ))
    assert preview["current_memory_schema"] == 3
    assert preview["target_memory_schema"] == 4
    assert preview["memory_migration_ids"] == ["canonical_memory_schema_v4"]
    with pytest.raises(LifecycleError, match="Doctor failed"):
        service.apply(LifecycleApplyRequest(
            preview_id=preview["preview_id"],
            approval_token=preview["approval_token"],
            operator_approved=True,
        ))
    with sqlite3.connect(paths.memory_database_path) as connection:
        assert connection.execute("SELECT MAX(schema_version) FROM schema_migrations").fetchone()[0] == 3
        assert connection.execute("SELECT value FROM private_user_proof").fetchone()[0] == "preserve-me"


def test_failed_first_activation_leaves_no_unhealthy_current_release(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "xdg")
    private, trust = _trust(tmp_path)
    service = _service(paths, trust_policy_path=trust, doctor_runner=lambda _: False)
    with pytest.raises(LifecycleError, match="Doctor failed"):
        _apply(service, _candidate(tmp_path, private, "unhealthy-first", b"bad"))
    assert service._current_release_id() is None
    assert not service.current_link.exists()
    assert service.state()["incomplete_operation_detected"] is True


def test_export_then_remove_creates_verified_private_archive_before_total_removal(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "xdg")
    paths.memory_database_path.parent.mkdir(parents=True)
    paths.memory_database_path.write_bytes(b"synthetic-private-memory")
    paths.config_dir.mkdir(parents=True)
    (paths.config_dir / "profile.json").write_text("synthetic-profile", encoding="utf-8")
    paths.runtime_dir.mkdir(parents=True)
    (paths.runtime_dir / "credential").write_text("synthetic-credential", encoding="utf-8")
    export = tmp_path / "elysia-private-export.tar.gz"
    service = _service(paths, trust_policy_path=tmp_path / "missing", doctor_runner=lambda _: True)
    preview = service.preview(LifecyclePreviewRequest(
        operation="export_then_remove",
        export_path=str(export),
        destructive_confirmation=EXPORT_REMOVE_CONFIRMATION,
    ))
    assert preview["destructive_user_data_removal"] is True
    result = service.apply(LifecycleApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    assert result["private_export"]["sha256"] == sha256(export.read_bytes()).hexdigest()
    assert export.stat().st_mode & 0o077 == 0
    with tarfile.open(export, "r:gz") as archive:
        names = set(archive.getnames())
    assert "data/memory/elysia_memory.sqlite" in names
    assert "runtime/credential" in names
    assert all(not path.exists() for _, path in service._owned_roots())


def test_total_purge_requires_exact_phrase_and_does_not_touch_external_vault(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "xdg")
    paths.data_dir.mkdir(parents=True)
    (paths.data_dir / "synthetic-user-content").write_text("delete-me", encoding="utf-8")
    external_vault = tmp_path / "external-model-vault"
    external_vault.mkdir()
    (external_vault / "model").write_text("preserve-me", encoding="utf-8")
    with pytest.raises(ValueError):
        LifecyclePreviewRequest(
            operation="purge_local_data", destructive_confirmation="almost",
        )
    service = _service(paths, trust_policy_path=tmp_path / "missing", doctor_runner=lambda _: True)
    preview = service.preview(LifecyclePreviewRequest(
        operation="purge_local_data", destructive_confirmation=PURGE_CONFIRMATION,
    ))
    result = service.apply(LifecycleApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    assert result["local_data"]["recoverable"] is False
    assert (external_vault / "model").read_text() == "preserve-me"
    assert all(not path.exists() for _, path in service._owned_roots())


def test_lifecycle_preview_requires_authenticated_local_admin(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "xdg")
    ordinary_user = LifecycleService(
        paths,
        trust_policy_path=tmp_path / "missing",
        doctor_runner=lambda _: True,
        governance_provider=lambda: {"user_id": "ordinary-user", "role": "user"},
    )
    with pytest.raises(LifecycleError, match="Only the Local Admin"):
        ordinary_user.preview(LifecyclePreviewRequest(operation="uninstall_preserve"))

    missing_session = LifecycleService(
        paths,
        trust_policy_path=tmp_path / "missing",
        doctor_runner=lambda _: True,
        governance_provider=lambda: {},
    )
    with pytest.raises(LifecycleError, match="Only the Local Admin"):
        missing_session.preview(LifecyclePreviewRequest(operation="uninstall_preserve"))


def test_lifecycle_apply_is_bound_to_same_local_admin_session(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "xdg")
    actor = {"user_id": "admin-a", "role": "admin"}
    service = LifecycleService(
        paths,
        trust_policy_path=tmp_path / "missing",
        doctor_runner=lambda _: True,
        governance_provider=lambda: dict(actor),
    )
    preview = service.preview(LifecyclePreviewRequest(operation="uninstall_preserve"))
    actor["user_id"] = "admin-b"
    with pytest.raises(LifecycleError, match="initiating Local Admin session"):
        service.apply(LifecycleApplyRequest(
            preview_id=preview["preview_id"],
            approval_token=preview["approval_token"],
            operator_approved=True,
        ))


def test_lifecycle_apply_requires_explicit_local_admin_approval(tmp_path: Path) -> None:
    service = _service(
        _paths(tmp_path / "xdg"),
        trust_policy_path=tmp_path / "missing",
        doctor_runner=lambda _: True,
    )
    preview = service.preview(LifecyclePreviewRequest(operation="uninstall_preserve"))
    with pytest.raises(LifecycleError, match="explicit Local Admin approval"):
        service.apply(LifecycleApplyRequest(
            preview_id=preview["preview_id"],
            approval_token=preview["approval_token"],
            operator_approved=False,
        ))
