"""Measured cognition, model, compute, and emergency truth surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.routes.account import _envelope
from app.api.schemas.cognition import CognitionStatusData
from app.api.user_control_service import current_user_controls
from app.cognition.compute_governor import ComputeLedger, resource_snapshot
from app.cognition.emergency_control import cancel_request, emergency_status
from app.cognition.governor import AUTONOMY_LEVELS, GEARS, GOVERNOR_VERSION
from app.cognition.model_registry import ModelRegistry


router = APIRouter(prefix="/cognition", tags=["cognition"])


@router.post("/requests/{request_id}/cancel")
async def cancel_active_request(request_id: str) -> dict[str, Any]:
    from app.api.account_service import AccountStore

    store = AccountStore()
    principal = store.authenticated_principal()
    cancelled = cancel_request(request_id, str(principal["user_id"]))
    if cancelled:
        store.record_governance_event(
            "request_cancelled_by_operator",
            safe_details={
                "request_id": request_id,
                "content_included": False,
            },
        )
    return _envelope(
        result_type="cognition_request_cancel",
        data={
            "request_id": request_id,
            "cancel_requested": cancelled,
            "content_inspected": False,
        },
    )


@router.get("/status")
async def cognition_status() -> dict[str, Any]:
    try:
        controls = current_user_controls()
        effective = {
            "autonomy_level": controls.autonomy_level,
            "domain_overrides": dict(controls.autonomy_domain_overrides),
            "preferred_reasoning_gear": controls.preferred_reasoning_gear,
            "compute_preference": controls.compute_preference,
            "model_performance_preference": controls.model_performance_preference,
            "background_cognition_enabled": controls.background_cognition_enabled,
            "internet_master_enabled": controls.internet_master_enabled,
            "retrieval_breadth": controls.retrieval_breadth,
            "cpu_percent_ceiling": controls.cpu_percent_ceiling,
            "ram_mb_ceiling": controls.ram_mb_ceiling,
            "vram_mb_ceiling": controls.vram_mb_ceiling,
            "max_background_jobs": controls.max_background_jobs,
            "managed_profile": controls.managed_profile,
            "managed_policy_version": controls.managed_policy_version,
        }
    except Exception:
        effective = {"state": "authenticated_profile_unavailable"}
    try:
        ledger = ComputeLedger()
        leases = ledger.active_leases()
        jobs = ledger.active_jobs()
        oom_history = ledger.recent_oom_history()
        lease_state = "durable"
    except Exception:
        leases = []
        jobs = []
        oom_history = []
        lease_state = "unavailable"
    data = CognitionStatusData(
        governor_contract=GOVERNOR_VERSION,
        reasoning_gears=list(GEARS),
        autonomy_levels=dict(AUTONOMY_LEVELS),
        effective_controls=effective,
        model_registry=ModelRegistry().snapshot(),
        compute={
            **resource_snapshot(),
            "lease_ledger_state": lease_state,
            "active_job_count": len(jobs),
            "active_jobs": [
                {
                    "reservation_id": item.get("reservation_id"),
                    "workload_id": item.get("workload_id"),
                    "task_kind": item.get("task_kind"),
                    "priority": item.get("priority"),
                    "deadline_utc": item.get("deadline_utc"),
                }
                for item in jobs
            ],
            "oom_history": oom_history,
            "oom_history_content_free": True,
            "private_content_included": False,
        },
        active_gpu_leases=leases,
        emergency=emergency_status(),
    )
    return _envelope(result_type="cognition_status", data=data.to_payload())


__all__ = ("router",)
