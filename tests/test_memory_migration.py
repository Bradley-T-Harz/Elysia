from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import app.api.account_service as account_service
from app.api.routes import memory as memory_routes
from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest
from app.memory.canonical_models import MemoryCreateRequest, MemoryPrincipal, MemoryQuery
from app.memory.canonical_repository import MemoryRepository, MemoryRepositoryError
from app.memory.fabric_service import MemoryFabricService
from app.memory.migration_service import MemoryMigrationError, MemoryMigrationService, prepare_memory_authority_for_startup
from app.memory.schemas.memory_item import (
    MemoryActorKind,
    MemoryClass,
    MemoryFlags,
    MemoryItem,
    MemoryMutability,
    MemorySensitivity,
    MemorySource,
    MemorySourceKind,
)


PASSWORD = "migration account password"


def profile(tmp_path: Path):
    identity = tmp_path / "profile" / "identity"
    store = AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )
    store.create_account(AccountCreateRequest(username="migration-user", password=PASSWORD))
    return store, MemoryPrincipal.model_validate(store.authenticated_principal())


def write_legacy(
    root: Path,
    memory_id: str,
    body: str,
    *,
    memory_class: MemoryClass = MemoryClass.preference,
) -> Path:
    path = root / memory_class.value / f"{memory_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    item = MemoryItem(
        memory_id=memory_id,
        memory_class=memory_class,
        title=f"Legacy {memory_id}",
        body=body,
        source=MemorySource(
            source_kind=MemorySourceKind.manual_entry,
            source_ref=f"source-{memory_id}",
            source_label="Synthetic legacy source",
        ),
        why_stored="Migration rollback proof.",
        sensitivity=(
            MemorySensitivity.sealed
            if memory_class == MemoryClass.sealed_private
            else MemorySensitivity.private
        ),
        mutability=MemoryMutability.review_required,
        created_by=MemoryActorKind.user,
        flags=MemoryFlags(user_declared=True),
    )
    path.write_text(item.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def migrated_ids(repository: MemoryRepository) -> set[str]:
    with repository.connect() as conn:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT memory_id FROM memory_records WHERE legacy_class IS NOT NULL"
            ).fetchall()
        }


def test_migration_candidate_failure_preserves_input_then_cutover_is_idempotent(tmp_path):
    store, principal = profile(tmp_path)
    repository = MemoryRepository(paths=store.elysia_paths)
    legacy_root = tmp_path / "legacy"
    legacy_path = write_legacy(legacy_root, "mem_legacy_one", "LEGACY_PRIVATE_CANARY")
    migration = MemoryMigrationService(repository=repository, legacy_roots=[legacy_root])

    with pytest.raises(MemoryMigrationError):
        migration.migrate(principal=principal, password=PASSWORD, fail_stage="after_candidate_build")
    assert legacy_path.exists()
    assert migrated_ids(repository) == set()
    assert not repository.database_path.with_name(f"{repository.database_path.name}.next").exists()

    result = migration.migrate(principal=principal, password=PASSWORD)
    assert result["state"] == "migrated"
    assert result["candidate_validated"] is True
    assert result["atomic_cutover"] is True
    assert migrated_ids(repository) == {"mem_legacy_one"}
    assert legacy_path.exists()
    assert legacy_path.stat().st_mode & 0o777 == 0o400

    again = migration.migrate(principal=principal, password=PASSWORD)
    assert again["migration_required"] is False
    assert migrated_ids(repository) == {"mem_legacy_one"}
    records, _ = MemoryFabricService(repository=repository).list(
        principal, MemoryQuery(privacy="private")
    )
    assert records[0].body == "LEGACY_PRIVATE_CANARY"


def test_post_cutover_doctor_failure_rolls_back_without_losing_prior_memory(tmp_path):
    store, principal = profile(tmp_path)
    repository = MemoryRepository(paths=store.elysia_paths)
    first_root = tmp_path / "legacy-first"
    write_legacy(first_root, "mem_prior", "PRIOR_CANARY")
    MemoryMigrationService(repository=repository, legacy_roots=[first_root]).migrate(
        principal=principal, password=PASSWORD
    )
    assert migrated_ids(repository) == {"mem_prior"}

    second_root = tmp_path / "legacy-second"
    second_path = write_legacy(second_root, "mem_new_record", "NEW_CANARY")
    migration = MemoryMigrationService(repository=repository, legacy_roots=[second_root])
    with pytest.raises(MemoryMigrationError, match="restored"):
        migration.migrate(principal=principal, password=PASSWORD, fail_stage="after_cutover")

    assert second_path.exists()
    assert migrated_ids(repository) == {"mem_prior"}
    status = migration.status()
    assert status["state"] == "rolled_back"
    assert status["rollback_performed"] is True


def test_empty_store_all_legacy_classes_and_package_relative_source(tmp_path):
    store, principal = profile(tmp_path)
    repository = MemoryRepository(paths=store.elysia_paths)
    empty = MemoryMigrationService(
        repository=repository, legacy_roots=[tmp_path / "empty-stores"]
    ).migrate(principal=principal, password=PASSWORD)
    assert empty["migration_required"] is False
    assert empty["migrated_count"] == 0

    packaged_root = (
        tmp_path
        / "installed-runtime"
        / "releases"
        / "synthetic-release"
        / "app"
        / "memory"
        / "stores"
    )
    classes = list(MemoryClass)
    for index, legacy_class in enumerate(classes):
        write_legacy(
            packaged_root,
            f"legacy_{legacy_class.value}",
            f"LEGACY_CLASS_CANARY_{index}",
            memory_class=legacy_class,
        )
    result = MemoryMigrationService(
        repository=repository, legacy_roots=[packaged_root]
    ).migrate(principal=principal, password=PASSWORD)
    assert result["migrated_count"] == len(classes)
    with repository.connect() as conn:
        rows = conn.execute(
            "SELECT legacy_class, scope, form, privacy FROM memory_records ORDER BY legacy_class"
        ).fetchall()
    assert {row["legacy_class"] for row in rows} == {
        legacy_class.value for legacy_class in classes
    }
    assert next(row for row in rows if row["legacy_class"] == "sealed_private")[
        "privacy"
    ] == "sealed"
    archives = list(repository.paths.memory_archive_dir.glob("legacy-*/migration-manifest.json"))
    assert archives
    assert all(path.stat().st_mode & 0o777 == 0o400 for path in archives)


def test_conflicting_ids_interruption_and_global_write_pause(tmp_path):
    store, principal = profile(tmp_path)
    repository = MemoryRepository(paths=store.elysia_paths)
    first = tmp_path / "collision-a"
    second = tmp_path / "collision-b"
    write_legacy(first, "mem_conflict", "FIRST_CONFLICT_CANARY")
    write_legacy(second, "mem_conflict", "SECOND_CONFLICT_CANARY")
    collision = MemoryMigrationService(
        repository=repository, legacy_roots=[first, second]
    )
    with pytest.raises(MemoryMigrationError, match="Conflicting duplicate"):
        collision.migrate(principal=principal, password=PASSWORD)
    assert migrated_ids(repository) == set()

    interrupted_root = tmp_path / "interrupted"
    write_legacy(interrupted_root, "mem_interrupted", "INTERRUPTION_CANARY")
    interrupted = MemoryMigrationService(
        repository=repository, legacy_roots=[interrupted_root]
    )
    with pytest.raises(MemoryMigrationError, match="after backup"):
        interrupted.migrate(
            principal=principal, password=PASSWORD, fail_stage="after_backup"
        )
    assert migrated_ids(repository) == set()
    assert not repository.database_path.with_name(
        f"{repository.database_path.name}.next"
    ).exists()

    with interrupted.migration_lock():
        assert interrupted.status()["maintenance_active"] is True
        with pytest.raises(MemoryRepositoryError, match="paused"):
            with repository.transaction():
                pass


def test_packaged_startup_pauses_writes_until_sealed_upgrade_reauthentication(
    monkeypatch, tmp_path
):
    store, principal = profile(tmp_path)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    legacy_root = store.elysia_paths.memory_dir / "stores"
    write_legacy(
        legacy_root,
        "legacy_sealed_upgrade",
        "SEALED_UPGRADE_CANARY",
        memory_class=MemoryClass.sealed_private,
    )

    startup = prepare_memory_authority_for_startup(store.elysia_paths)
    assert startup["state"] == "maintenance"
    assert startup["writes_paused"] is True
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    with pytest.raises(MemoryRepositoryError, match="migration completes"):
        fabric.create(
            principal,
            MemoryCreateRequest(
                title="Blocked during upgrade",
                body="This write must wait.",
                why_stored="Maintenance gate proof.",
            ),
        )

    wrong = asyncio.run(memory_routes.apply_migration(password="wrong password"))
    assert wrong["status"] == "blocked"
    assert repository.migration_required_marker.is_file()

    applied = asyncio.run(memory_routes.apply_migration(password=PASSWORD))
    assert applied["status"] == "ok"
    assert applied["data"]["migration"]["atomic_cutover"] is True
    assert not repository.migration_required_marker.exists()
    created = fabric.create(
        principal,
        MemoryCreateRequest(
            title="After upgrade",
            body="Writes resume only after verified cutover.",
            why_stored="Post-migration proof.",
        ),
    )
    assert created.body == "Writes resume only after verified cutover."
