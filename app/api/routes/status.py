"""
Status route module for the Elysia local API bridge.

This module owns:
- GET /status/runtime
- GET /status/health
- GET /status/invoker
- GET /status/capabilities
- GET /status/profiles

It should stay thin:
- accept simple read-only requests
- call the appropriate status/capability service
- return the structured envelope produced downstream

It must not become a second runtime, second governance layer, or second
capability catalog implementation.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(
    prefix="/status",
    tags=["status"],
)


def _load_status_service() -> Any:
    """
    Import the status service lazily so this route module can exist before every
    downstream service organ is finished.
    """
    try:
        return importlib.import_module("app.api.status_service")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Status service is not available yet: {exc}",
        ) from exc


def _load_capability_service() -> Any:
    """
    Import the capability service lazily so this route module can exist before
    every downstream service organ is finished.
    """
    try:
        return importlib.import_module("app.api.capability_service")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Capability service is not available yet: {exc}",
        ) from exc


def _load_install_profile_service() -> Any:
    """Import the non-mutating install-profile resolver lazily."""
    try:
        return importlib.import_module("app.install.profile_service")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Install-profile service is not available yet.",
        ) from exc


def _load_doctor_service() -> Any:
    """Import the bounded install doctor lazily."""
    try:
        return importlib.import_module("app.install.doctor_service")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Install doctor is not available yet.",
        ) from exc


async def _invoke_service_callable(service_module: Any, fn_name: str) -> dict[str, Any]:
    """
    Call a named service function and require a dictionary envelope result.
    """
    service_fn = getattr(service_module, fn_name, None)
    if service_fn is None:
        raise HTTPException(
            status_code=503,
            detail=f"Required service function '{fn_name}' is not available yet.",
        )

    result = service_fn()
    if inspect.isawaitable(result):
        result = await result

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail=f"Service function '{fn_name}' returned a non-dictionary response.",
        )

    return result


@router.get("/runtime")
async def get_runtime_status() -> dict[str, Any]:
    """
    Return a compact governed runtime-status envelope.

    This route does not build runtime truth itself. It delegates to status_service.
    """
    status_service = _load_status_service()
    return await _invoke_service_callable(status_service, "get_runtime_status")


@router.get("/health")
async def get_health_status() -> dict[str, Any]:
    """
    Return a compact governed health-status envelope.

    This route does not build health truth itself. It delegates to status_service.
    """
    status_service = _load_status_service()
    return await _invoke_service_callable(status_service, "get_health_status")


@router.get("/invoker")
async def get_invoker_status() -> dict[str, Any]:
    """
    Return a compact governed invoker-status envelope.

    This route does not build invoker truth itself. It delegates to status_service.
    """
    status_service = _load_status_service()
    return await _invoke_service_callable(status_service, "get_invoker_status")


@router.get("/capabilities")
async def get_capabilities_status() -> dict[str, Any]:
    """
    Return a compact governed capability-catalog envelope.

    This route does not build capability truth itself. It delegates to
    capability_service.
    """
    capability_service = _load_capability_service()
    return await _invoke_service_callable(
        capability_service,
        "get_capabilities_status",
    )


@router.get("/profiles")
async def get_install_profile_status() -> dict[str, Any]:
    """Return read-only profile, dependency, provider, and worker readiness truth."""
    profile_service = _load_install_profile_service()
    return await _invoke_service_callable(
        profile_service,
        "get_install_profile_status",
    )


@router.get("/doctor")
async def get_install_doctor_status(
    probe_local_services: bool = Query(default=False),
) -> dict[str, Any]:
    """Return non-repairing Core/XDG/auth/profile readiness truth."""
    doctor_service = _load_doctor_service()
    service_fn = getattr(doctor_service, "get_doctor_status", None)
    if service_fn is None:
        raise HTTPException(status_code=503, detail="Install doctor contract is unavailable.")
    result = service_fn(probe_local_services=probe_local_services)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="Install doctor returned an invalid response.")
    return result
