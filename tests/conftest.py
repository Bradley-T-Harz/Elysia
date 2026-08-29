from __future__ import annotations

import os

import pytest


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
