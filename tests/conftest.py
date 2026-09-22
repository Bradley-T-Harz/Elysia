from __future__ import annotations

import os

import pytest


@pytest.fixture
def safe_resource_samples(monkeypatch):
    """Explicit cool telemetry for fake-provider transport tests (not live proof)."""
    import time
    from app.cognition import resource_guard
    monkeypatch.setattr(resource_guard, "sample_resources", lambda:
        resource_guard.ResourceSample(time.monotonic(), 60, 50, 32000))


@pytest.fixture
def isolated_scientific_compute(monkeypatch, safe_resource_samples):
    """Keep mathematical behavior tests independent of unrelated host load.

    Real governor admission, reservations, worker processes and OS limits remain
    active. Thermal/placement tests supply their own explicit sensor snapshots.
    """
    from app.cognition import compute_governor
    monkeypatch.setattr(compute_governor, "resource_snapshot", lambda: {
        "system": {"cpu_percent": 5, "cpu_temperature_c": 60,
                   "ram_available_mb": 32000},
        "gpu": {"available": False, "devices": []},
    })


@pytest.fixture(autouse=True)
def isolate_coding_workspace_and_audit(tmp_path, monkeypatch):
    """Keep all coding authority and audit writes inside this test's temp root."""
    monkeypatch.setenv("ELYSIA_CODING_APPROVED_ROOTS", str(tmp_path))
    monkeypatch.setenv("ELYSIA_CODING_AUDIT_ROOT", str(tmp_path / "coding-audit"))
    monkeypatch.setenv("ELYSIA_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ELYSIA_ARCHIVE_ARTIFACT_ROOT", str(tmp_path / "archive-artifacts"))
    monkeypatch.setenv("ELYSIA_ENGINEERING_ARTIFACT_ROOT", str(tmp_path / "engineering-artifacts"))
    monkeypatch.setenv(
        "ELYSIA_ARCHIVE_SANDBOX_ROOT",
        str(tmp_path.parent / f".{tmp_path.name}-archive-sandboxes"),
    )
    from app.api.coding_archive_job_service import clear_archive_jobs_for_tests
    from app.api.coding_engineering_job_service import clear_engineering_jobs_for_tests
    from app.api.coding_operation_service import clear_operation_state_for_tests
    from app.api.videoforge_service import clear_video_jobs_for_tests

    clear_archive_jobs_for_tests()
    clear_engineering_jobs_for_tests()
    clear_operation_state_for_tests()
    clear_video_jobs_for_tests()
    yield
    clear_video_jobs_for_tests()
    clear_operation_state_for_tests()
    clear_archive_jobs_for_tests()
    clear_engineering_jobs_for_tests()


@pytest.fixture
def isolated_account_store(tmp_path, monkeypatch):
    """Give authority-sensitive tests a real account in isolated XDG storage."""
    from app.api import account_service
    from app.api.account_service import AccountPaths, AccountStore
    from app.api.schemas.account import AccountCreateRequest
    from app.install.paths import resolve_elysia_paths

    for name, directory in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        monkeypatch.setenv(name, str(tmp_path / directory))
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))

    paths = resolve_elysia_paths()
    identity = paths.data_dir / "identity"
    store = AccountStore(AccountPaths(
        identity_root=identity,
        database_path=identity / "elysia_identity.sqlite",
        profile_photo_dir=identity / "profile_photos",
        current_session_path=identity / "current_session.json",
        elysia_paths=paths,
    ))
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    store.create_account(AccountCreateRequest(
        username="isolated-test-owner",
        password="synthetic isolated test owner password",
    ))
    return store


@pytest.fixture
def isolated_project_store(isolated_account_store, monkeypatch):
    """Bind project and conversation lookups to the same test account paths."""
    from app.api import conversation_service, project_service

    paths = isolated_account_store.elysia_paths
    monkeypatch.setattr(project_service, "PROJECTS_DIR", paths.project_dir)
    monkeypatch.setattr(
        project_service,
        "ACTIVE_PROJECT_PATH",
        paths.project_dir / "_active_project.json",
    )
    monkeypatch.setattr(conversation_service, "CONVERSATIONS_DIR", paths.conversation_dir)
    return isolated_account_store
