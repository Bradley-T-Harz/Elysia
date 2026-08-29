"""Orchestrator for bounded public page fetch work."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import fetch_public_page
from .config import DEFAULT_FETCH_WORKER_CONFIG_PATH, load_fetch_worker_config
from .contract import FetchWorkerRequest, FetchWorkerResult, FetchWorkerStatus
from .url_guard import guard_fetch_url


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _blocked(
    request: FetchWorkerRequest,
    status: FetchWorkerStatus,
    *,
    sanitized_url: str = "",
    url_hash: str = "",
    reasons: list[str] | None = None,
    approval_required: bool = False,
) -> FetchWorkerResult:
    return FetchWorkerResult(
        status=status,
        request_id=request.request_id,
        ticket_id=request.ticket_id,
        requested_url=request.url,
        sanitized_url=sanitized_url,
        url_hash=url_hash,
        approval_required=approval_required,
        refusal_reasons=list(reasons or []),
        private_context_sent=False,
        network_access_used=False,
        page_fetch_used=False,
        cloud_search_used=False,
        cloud_model_used=False,
    )


def _evidence_packet(
    *,
    request: FetchWorkerRequest,
    url: str,
    title: str,
    snippet: str,
) -> dict[str, Any]:
    return {
        "source_url": url,
        "title": title or url,
        "retrieved_at_utc": _utc_now_iso(),
        "snippet": snippet,
        "claim": f"Fetched public page may be relevant to approved URL: {url}",
        "confidence": "low",
        "contradiction_notes": [],
        "source_type": "unknown",
        "retrieval_method": "public_page_fetch",
        "outward_boundary_state": "external_boundary_crossed",
        "private_context_sent": False,
        "network_access_used": True,
        "page_fetch_used": True,
        "live_web_research_used": True,
        "source_rank": None,
        "license_or_access_notes": "Bounded approved public page fetch; snippet only.",
        "warnings": [],
        "errors": [],
    }


def run_fetch_worker(
    request: FetchWorkerRequest,
    *,
    config_path: str | Path = DEFAULT_FETCH_WORKER_CONFIG_PATH,
    fetch_client: Callable[..., dict[str, Any]] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> FetchWorkerResult:
    try:
        config = load_fetch_worker_config(config_path)
    except Exception as exc:
        return FetchWorkerResult(
            status=FetchWorkerStatus.UNAVAILABLE,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            requested_url=request.url,
            errors=[f"Fetch worker config unavailable: {exc}"],
        )

    if config.service.get("enabled") is not True:
        return FetchWorkerResult(
            status=FetchWorkerStatus.UNAVAILABLE,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            requested_url=request.url,
            warnings=["Fetch worker is configured but disabled."],
        )

    if request.worker_key != config.worker_key:
        return _blocked(request, FetchWorkerStatus.BLOCKED, reasons=["Wrong worker key."])
    if request.private_context_allowed or request.private_context_sent:
        return _blocked(request, FetchWorkerStatus.BLOCKED, reasons=["Private context is blocked."])
    if request.cloud_search_allowed or request.cloud_model_allowed:
        return _blocked(request, FetchWorkerStatus.BLOCKED, reasons=["Cloud search/model use is blocked."])
    if request.browser_automation_allowed or request.crawling_allowed:
        return _blocked(request, FetchWorkerStatus.BLOCKED, reasons=["Browser automation and crawling are blocked."])

    guard = guard_fetch_url(
        request.url,
        config=config,
        approval_token=request.approval_token,
        approved_by_user=request.approved_by_user,
    )
    if not guard.allowed:
        return _blocked(
            request,
            FetchWorkerStatus.APPROVAL_REQUIRED if guard.approval_required else FetchWorkerStatus.BLOCKED,
            sanitized_url=guard.sanitized_url,
            url_hash=guard.url_hash,
            reasons=guard.refusal_reasons,
            approval_required=guard.approval_required,
        )

    active_client = fetch_client or fetch_public_page
    response = active_client(
        url=guard.sanitized_url,
        timeout_seconds=int(config.service.get("timeout_seconds", 10)),
        max_response_bytes=int(config.service.get("max_response_bytes", 120000)),
        max_snippet_chars=int(config.service.get("max_snippet_chars", 1200)),
        user_agent=str(config.service.get("user_agent", "Elysia-BoundedFetch/1.0")),
        follow_redirects=bool(config.service.get("follow_redirects", False)),
        allowed_public_ips=list(guard.resolved_public_ips),
        max_decompressed_bytes=int(config.service.get("max_decompressed_bytes", 480000)),
        max_redirects=int(config.service.get("max_redirects", 3)),
        redirect_validator=lambda target: guard_fetch_url(target, config=config),
        cancel_check=cancel_check,
    )
    errors = list(response.get("errors") or [])
    warnings = list(response.get("warnings") or [])
    status = FetchWorkerStatus.COMPLETED if not errors else FetchWorkerStatus.FAILED
    packet = []
    if not errors:
        packet = [
            _evidence_packet(
                request=request,
                url=str(response.get("final_url") or guard.sanitized_url),
                title=str(response.get("title") or ""),
                snippet=str(response.get("snippet") or ""),
            )
        ]

    return FetchWorkerResult(
        status=status,
        worker_used=status == FetchWorkerStatus.COMPLETED,
        request_id=request.request_id,
        ticket_id=request.ticket_id,
        requested_url=request.url,
        sanitized_url=guard.sanitized_url,
        url_hash=guard.url_hash,
        title=str(response.get("title") or ""),
        snippet=str(response.get("snippet") or ""),
        content_type=str(response.get("content_type") or ""),
        status_code=response.get("status_code"),
        bytes_read=int(response.get("bytes_read") or 0),
        evidence_packets=packet,
        network_access_used=True,
        page_fetch_used=True,
        private_context_sent=False,
        cloud_search_used=False,
        cloud_model_used=False,
        approval_required=False,
        warnings=warnings,
        errors=errors,
    )


__all__ = ("run_fetch_worker",)
