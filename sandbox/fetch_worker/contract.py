"""Dataclasses for the bounded public page fetch worker."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class FetchWorkerStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class FetchWorkerRequest:
    request_id: str
    ticket_id: str
    url: str
    worker_key: str = "bounded_fetch_worker"
    approval_token: str | None = None
    approval_reference: str | None = None
    approved_by_user: bool = False
    private_context_allowed: bool = False
    private_context_sent: bool = False
    cloud_search_allowed: bool = False
    cloud_model_allowed: bool = False
    browser_automation_allowed: bool = False
    crawling_allowed: bool = False


@dataclass
class FetchWorkerResult:
    status: FetchWorkerStatus
    worker_key: str = "bounded_fetch_worker"
    worker_used: bool = False
    request_id: str = ""
    ticket_id: str = ""
    requested_url: str = ""
    sanitized_url: str = ""
    url_hash: str = ""
    title: str = ""
    snippet: str = ""
    content_type: str = ""
    status_code: int | None = None
    bytes_read: int = 0
    evidence_packets: list[dict[str, Any]] = field(default_factory=list)
    network_access_used: bool = False
    page_fetch_used: bool = False
    private_context_sent: bool = False
    cloud_search_used: bool = False
    cloud_model_used: bool = False
    browser_automation_used: bool = False
    crawling_used: bool = False
    approval_required: bool = False
    approval_reason: str = ""
    refusal_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


__all__ = (
    "FetchWorkerRequest",
    "FetchWorkerResult",
    "FetchWorkerStatus",
)
