"""Compact synchronous job truth for EngineeringForge operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.schemas.engineering import EngineeringJobState


_JOBS: dict[str, EngineeringJobState] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def start_engineering_job(operation_id: str, operation_kind: str, source_sha256: str | None = None) -> EngineeringJobState:
    existing = _JOBS.get(operation_id)
    if existing is not None and existing.cancel_requested:
        existing.operation_kind = operation_kind
        existing.status = "cancel_requested"
        return existing
    job = EngineeringJobState(
        operation_id=operation_id,
        operation_kind=operation_kind,
        status="running",
        source_sha256=source_sha256,
        started_at_utc=_now(),
    )
    _JOBS[operation_id] = job
    return job


def finish_engineering_job(
    operation_id: str,
    *,
    status: str,
    approval_id: str | None = None,
    artifact_id: str | None = None,
    compact_summary: dict[str, Any] | None = None,
) -> EngineeringJobState | None:
    job = _JOBS.get(operation_id)
    if job is None:
        return None
    job.status = status
    job.approval_id = approval_id
    job.artifact_id = artifact_id
    job.compact_summary = dict(compact_summary or {})
    job.completed_at_utc = _now()
    return job


def get_engineering_job(operation_id: str) -> EngineeringJobState | None:
    return _JOBS.get(operation_id)


def cancel_engineering_job(operation_id: str) -> EngineeringJobState | None:
    job = _JOBS.get(operation_id)
    if job is None:
        return None
    job.cancel_requested = True
    if job.status in {"planned", "queued"}:
        job.status = "cancelled"
        job.completed_at_utc = _now()
    return job


def cancel_all_engineering_jobs() -> int:
    count = 0
    for operation_id, job in list(_JOBS.items()):
        if job.status not in {"completed", "cancelled", "failed", "blocked"}:
            cancel_engineering_job(operation_id)
            count += 1
    return count


def clear_engineering_jobs_for_tests() -> None:
    _JOBS.clear()


__all__ = (
    "cancel_engineering_job",
    "cancel_all_engineering_jobs",
    "clear_engineering_jobs_for_tests",
    "finish_engineering_job",
    "get_engineering_job",
    "start_engineering_job",
)
