"""In-memory compact job truth for synchronous ArchiveForge operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.schemas.archive import ArchiveJobState


_JOBS: dict[str, ArchiveJobState] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def start_archive_job(operation_id: str, operation_kind: str, archive_sha256: str | None = None) -> ArchiveJobState:
    existing = _JOBS.get(operation_id)
    if existing is not None and existing.cancel_requested:
        existing.operation_kind = operation_kind
        existing.status = "cancel_requested"
        return existing
    job = ArchiveJobState(
        operation_id=operation_id,
        operation_kind=operation_kind,
        status="running",
        archive_sha256=archive_sha256,
        started_at_utc=_now(),
    )
    _JOBS[operation_id] = job
    return job


def finish_archive_job(
    operation_id: str,
    *,
    status: str,
    approval_id: str | None = None,
    artifact_id: str | None = None,
    compact_summary: dict[str, Any] | None = None,
) -> ArchiveJobState | None:
    job = _JOBS.get(operation_id)
    if not job:
        return None
    job.status = status
    job.approval_id = approval_id
    job.artifact_id = artifact_id
    job.compact_summary = dict(compact_summary or {})
    job.completed_at_utc = _now()
    return job


def get_archive_job(operation_id: str) -> ArchiveJobState | None:
    return _JOBS.get(operation_id)


def cancel_archive_job(operation_id: str) -> ArchiveJobState | None:
    job = _JOBS.get(operation_id)
    if not job:
        return None
    job.cancel_requested = True
    if job.status in {"planned", "queued"}:
        job.status = "cancelled"
        job.completed_at_utc = _now()
    return job


def cancel_all_archive_jobs() -> int:
    count = 0
    for operation_id, job in list(_JOBS.items()):
        if job.status not in {"completed", "cancelled", "failed", "blocked"}:
            cancel_archive_job(operation_id)
            count += 1
    return count


def archive_job_cancel_requested(operation_id: str) -> bool:
    job = _JOBS.get(operation_id)
    return bool(job and job.cancel_requested)


def clear_archive_jobs_for_tests() -> None:
    _JOBS.clear()


__all__ = (
    "archive_job_cancel_requested",
    "cancel_archive_job",
    "cancel_all_archive_jobs",
    "clear_archive_jobs_for_tests",
    "finish_archive_job",
    "get_archive_job",
    "start_archive_job",
)
