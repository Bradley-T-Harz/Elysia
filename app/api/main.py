"""
Elysia local API bridge entrypoint.

This module creates the local API app, enforces local-only posture by default,
registers route modules when they exist, and exposes a minimal root/ping/locality
surface using the shared structured-envelope shape.

This file should stay thin.
It is the front door of the local bridge, not the runtime, not the services,
and not the route-business-logic layer.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import importlib
import ipaddress
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ids import new_id

from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.install.local_auth import (
    LocalApiAuthPolicy,
    MUTATING_METHODS,
    build_local_api_auth_policy,
    validate_local_api_credential,
)

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"
BRIDGE_NAME = "Elysia Local API Bridge"

LOCAL_ONLY_BY_DEFAULT = True
ALLOWED_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

ROUTE_MODULES: tuple[tuple[str, str], ...] = (
    ("app.api.routes.chat", "router"),
    ("app.api.routes.conversations", "router"),
    ("app.api.routes.projects", "router"),
    ("app.api.routes.project_capabilities", "router"),
    ("app.api.routes.memory", "router"),
    ("app.api.routes.files", "router"),
    ("app.api.routes.artifacts", "router"),
    ("app.api.routes.status", "router"),
    ("app.api.routes.install", "router"),
    ("app.api.routes.governance", "router"),
    ("app.api.routes.approval", "router"),
    ("app.api.routes.requests", "router"),
    ("app.api.routes.request_trace", "router"),
    ("app.api.routes.research", "router"),
    ("app.api.routes.code", "router"),
    ("app.api.routes.account", "router"),
    ("app.api.routes.onboarding", "router"),
    ("app.api.routes.admin", "router"),
    ("app.api.routes.emergency", "router"),
    ("app.api.routes.cognition", "router"),
    ("app.api.routes.marketplace", "router"),
    ("app.api.routes.addon_actions", "router"),
    ("app.api.routes.addons", "router"),
    ("app.api.routes.coding", "router"),
    ("app.api.routes.coding_file_types", "router"),
    ("app.api.routes.coding_files", "router"),
    ("app.api.routes.coding_documents", "router"),
    ("app.api.routes.coding_data", "router"),
    ("app.api.routes.coding_visual", "router"),
    ("app.api.routes.coding_media", "router"),
    ("app.api.routes.coding_archive", "router"),
    ("app.api.routes.coding_database", "router"),
    ("app.api.routes.coding_binary", "router"),
    ("app.api.routes.coding_engineering", "router"),
    ("app.api.routes.media_workers", "router"),
    ("app.api.routes.coding_patches", "router"),
    ("app.api.routes.coding_file_operations", "router"),
    ("app.api.routes.coding_operations", "router"),
    ("app.api.routes.coding_commands", "router"),
    ("app.api.routes.coding_git", "router"),
    ("app.api.routes.coding_tasks", "router"),
)


def _new_request_id(prefix: str = "req") -> str:
    """
    Create a compact request identifier for bridge-level responses.
    """
    return new_id(prefix)


def _is_local_client(host: str | None) -> bool:
    """
    Decide whether a client host should be treated as local.

    The bridge is loopback-only by default. We also allow 'testclient' so local
    test harnesses are not blocked by the locality guard.
    """
    if host is None:
        return True

    normalized_host = host.split("%", 1)[0].strip().lower()

    if normalized_host in ALLOWED_LOOPBACK_HOSTS:
        return True

    try:
        return ipaddress.ip_address(normalized_host).is_loopback
    except ValueError:
        return False


def _managed_policy_requirements(path: str, method: str) -> tuple[str, ...]:
    """Map mutating product surfaces to installation-policy ceilings.

    Revocation/disconnect operations stay available so a managed profile is
    never trapped in an existing connector relationship.
    """
    verb = method.upper()
    if verb not in MUTATING_METHODS:
        return ()
    if path.startswith("/coding/") or path == "/coding":
        return ("coding_execution",)
    if path.startswith("/addon-actions/") or path.startswith("/addons/"):
        return ("addons",)
    if path == "/marketplace/link" and verb == "POST":
        return ("connectors",)
    if path.startswith("/marketplace/profile-sync/"):
        return ("connectors", "external_mutations")
    if "/connectors/" in path and not path.endswith("/disconnect"):
        return ("connectors", "external_mutations")
    return ()


def _try_include_router(app: FastAPI, module_path: str, router_attr: str) -> None:
    """
    Attempt to include a router module if it exists.

    This allows staged bridge bring-up before every route module is created.
    Missing route modules are recorded on app.state instead of crashing the
    bridge entrypoint.
    """
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, router_attr)
    except Exception as exc:  # route truth is retained while optional adapters degrade independently
        LOGGER.exception("Required route module %s could not be registered", module_path)
        app.state.pending_route_modules.append(
            {
                "module": module_path,
                "router_attr": router_attr,
                "reason": f"{type(exc).__name__}: route module unavailable",
            }
        )
        return

    app.include_router(router)
    app.state.registered_route_modules.append(module_path)


def create_app(
    *,
    auth_policy: LocalApiAuthPolicy | None = None,
) -> FastAPI:
    """
    Create the FastAPI app for Elysia's local API bridge.
    """
    async def part2e_maintenance_loop() -> None:
        """Run only user-enabled work through the canonical/Compute ledgers."""

        while True:
            await asyncio.sleep(30)
            try:
                from app.api.account_service import (
                    get_active_elysia_paths,
                    get_authenticated_principal,
                )
                from app.memory.canonical_models import MemoryPrincipal
                from app.memory.canonical_repository import MemoryRepository
                from app.memory.fabric_service import MemoryFabricService
                from app.memory.release_service import MemoryReleaseService

                repository = MemoryRepository(paths=get_active_elysia_paths())
                principal = MemoryPrincipal.model_validate(
                    get_authenticated_principal()
                )
                fabric = MemoryFabricService(repository=repository)
                release = MemoryReleaseService(
                    fabric=fabric, repository=repository
                )
                await asyncio.to_thread(release.run_scheduled_tick, principal)
            except asyncio.CancelledError:
                raise
            except Exception:
                # No account/session, disabled background cognition, storage
                # pressure, or a bounded maintenance failure is represented by
                # its owning authority. The API loop never gains content access
                # or retries aggressively.
                pass
            await asyncio.sleep(270)

    @asynccontextmanager
    async def lifespan(lifecycle_app: FastAPI):
        """Recover bounded memory work and own its cancellable maintenance task."""

        try:
            from app.api.account_service import get_active_elysia_paths
            from app.memory.canonical_repository import MemoryRepository
            from app.memory.release_service import MemoryReleaseService

            repository = MemoryRepository(paths=get_active_elysia_paths())
            MemoryReleaseService.recover_after_restart(repository)
        except Exception:
            pass
        lifecycle_app.state.part2e_maintenance_task = asyncio.create_task(
            part2e_maintenance_loop(), name="elysia-part2e-maintenance"
        )
        try:
            yield
        finally:
            task = getattr(lifecycle_app.state, "part2e_maintenance_task", None)
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title=BRIDGE_NAME,
        version=API_VERSION,
        description=(
            "Local-first governed API bridge for Elysia. "
            "This bridge is intended for local use only by default."
        ),
        lifespan=lifespan,
    )

    resolved_auth_policy = auth_policy or build_local_api_auth_policy(initialize=False)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-Elysia-Client"],
    )

    app.state.local_only_by_default = LOCAL_ONLY_BY_DEFAULT
    app.state.allowed_loopback_hosts = sorted(ALLOWED_LOOPBACK_HOSTS)
    app.state.registered_route_modules = []
    app.state.pending_route_modules = []
    app.state.local_api_auth_policy = resolved_auth_policy

    @app.middleware("http")
    async def enforce_local_only_by_default(
        request: Request,
        call_next,
    ) -> JSONResponse | Any:
        """
        Reject non-local clients by default with a structured envelope response.
        """
        client_host = request.client.host if request.client else None

        if LOCAL_ONLY_BY_DEFAULT and not _is_local_client(client_host):
            envelope = build_response_envelope(
                status=EnvelopeStatus.BLOCKED,
                request_id=_new_request_id(),
                api_version=API_VERSION,
                contract_version=CONTRACT_VERSION,
                result_type="locality_guard",
                capability_state=CapabilityState.LIVE,
                locality=LocalityState.CROSSED_BOUNDARY,
                approval_state=ApprovalState.DENIED,
                warnings=[],
                errors=[
                    "Local API bridge rejects non-local clients by default.",
                ],
                trace_summary=TraceSummary(
                    route_used="locality_guard",
                    log_written=False,
                    journal_written=False,
                ),
                data={
                    "bridge_name": BRIDGE_NAME,
                    "local_only_by_default": True,
                    "client_host": client_host or "",
                    "allowed_loopback_hosts": sorted(ALLOWED_LOOPBACK_HOSTS),
                },
            )
            return JSONResponse(status_code=403, content=envelope.to_payload())

        if (
            request.method.upper() in MUTATING_METHODS
            and resolved_auth_policy.required
            and not validate_local_api_credential(resolved_auth_policy, request.headers)
        ):
            envelope = build_response_envelope(
                status=EnvelopeStatus.BLOCKED,
                request_id=_new_request_id(),
                api_version=API_VERSION,
                contract_version=CONTRACT_VERSION,
                result_type="local_client_auth_guard",
                capability_state=CapabilityState.LIVE,
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.DENIED,
                warnings=[],
                errors=["A valid local client credential is required for mutating API calls."],
                trace_summary=TraceSummary(
                    route_used="local_client_auth_guard",
                    log_written=False,
                    journal_written=False,
                ),
                data={
                    "authentication_required": True,
                    "credential_exposed": False,
                    "runtime_mode": resolved_auth_policy.runtime_mode.value,
                },
            )
            return JSONResponse(status_code=401, content=envelope.to_payload())

        if request.method.upper() in MUTATING_METHODS and request.url.path not in {
            "/emergency/stop",
            "/emergency/reset",
            "/account/login",
            "/account/logout",
            "/account/create",
        }:
            try:
                from app.cognition.emergency_control import emergency_active

                stop_active = emergency_active()
            except Exception:
                stop_active = True
            if stop_active:
                envelope = build_response_envelope(
                    status=EnvelopeStatus.BLOCKED,
                    request_id=_new_request_id("emergency"),
                    api_version=API_VERSION,
                    contract_version=CONTRACT_VERSION,
                    result_type="emergency_posture_guard",
                    capability_state=CapabilityState.LIVE,
                    locality=LocalityState.LOCAL,
                    approval_state=ApprovalState.DENIED,
                    warnings=[],
                    errors=[
                        "System emergency posture is active. An Installation Owner or Admin must explicitly reset it."
                    ],
                    trace_summary=TraceSummary(
                        route_used="emergency_posture_guard",
                        log_written=False,
                        journal_written=False,
                    ),
                    data={
                        "emergency_stop_active": True,
                        "new_mutation_blocked": True,
                        "runtime_autonomy_override": 1,
                    },
                )
                return JSONResponse(status_code=423, content=envelope.to_payload())

        requirements = _managed_policy_requirements(request.url.path, request.method)
        if requirements:
            try:
                from app.api.account_service import AccountStore
                from app.api.user_control_service import managed_capability_allowed

                denied = [item for item in requirements if not managed_capability_allowed(item)]
                if denied:
                    try:
                        AccountStore().record_governance_event(
                            "managed_policy_operation_blocked",
                            safe_details={
                                "capabilities": denied,
                                "method": request.method.upper(),
                                "route_family": request.url.path.split("/", 2)[1],
                                "content_included": False,
                            },
                        )
                    except Exception:
                        pass
                    envelope = build_response_envelope(
                        status=EnvelopeStatus.BLOCKED,
                        request_id=_new_request_id("managedpolicy"),
                        api_version=API_VERSION,
                        contract_version=CONTRACT_VERSION,
                        result_type="managed_profile_policy_guard",
                        capability_state=CapabilityState.LIVE,
                        locality=LocalityState.LOCAL,
                        approval_state=ApprovalState.DENIED,
                        warnings=[],
                        errors=[
                            "This operation exceeds the visible managed-profile installation policy."
                        ],
                        trace_summary=TraceSummary(
                            route_used="managed_profile_policy_guard",
                            log_written=True,
                            journal_written=False,
                        ),
                        data={
                            "managed_profile": True,
                            "blocked_capabilities": denied,
                            "content_inspected": False,
                        },
                    )
                    return JSONResponse(status_code=403, content=envelope.to_payload())
            except Exception:
                # A protected mutation must never become more powerful because
                # Identity/governance truth is temporarily unavailable. Account
                # bootstrap routes are excluded from this mapping, so fail
                # closed here and leave retry/recovery to the owning surface.
                envelope = build_response_envelope(
                    status=EnvelopeStatus.BLOCKED,
                    request_id=_new_request_id("managedpolicy"),
                    api_version=API_VERSION,
                    contract_version=CONTRACT_VERSION,
                    result_type="managed_profile_policy_unavailable",
                    capability_state=CapabilityState.DEGRADED,
                    locality=LocalityState.LOCAL,
                    approval_state=ApprovalState.DENIED,
                    warnings=[],
                    errors=[
                        "Installation policy could not be verified; the protected operation was not run."
                    ],
                    trace_summary=TraceSummary(
                        route_used="managed_profile_policy_guard",
                        log_written=False,
                        journal_written=False,
                    ),
                    data={
                        "policy_verification_failed_closed": True,
                        "content_inspected": False,
                    },
                )
                return JSONResponse(status_code=503, content=envelope.to_payload())

        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def structured_http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """
        Return HTTP exceptions in the structured envelope shape.
        """
        del request

        status = EnvelopeStatus.ERROR
        approval_state = ApprovalState.UNKNOWN
        capability_state = CapabilityState.UNKNOWN

        if exc.status_code == 403:
            status = EnvelopeStatus.BLOCKED
            approval_state = ApprovalState.DENIED
        elif exc.status_code == 503:
            status = EnvelopeStatus.UNAVAILABLE
            capability_state = CapabilityState.UNAVAILABLE

        envelope = build_response_envelope(
            status=status,
            request_id=_new_request_id(),
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="http_error",
            capability_state=capability_state,
            locality=LocalityState.LOCAL,
            approval_state=approval_state,
            warnings=[],
            errors=[str(exc.detail)],
            trace_summary=TraceSummary(
                route_used="http_exception_handler",
                log_written=False,
                journal_written=False,
            ),
            data={
                "http_status_code": exc.status_code,
            },
        )
        return JSONResponse(status_code=exc.status_code, content=envelope.to_payload())

    @app.exception_handler(Exception)
    async def structured_unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """
        Return unexpected exceptions in the structured envelope shape.
        """
        LOGGER.exception("Unhandled exception on local API bridge", exc_info=exc)

        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=_new_request_id(),
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bridge_error",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[
                "Local API bridge encountered an unexpected error.",
            ],
            trace_summary=TraceSummary(
                route_used="unhandled_exception_handler",
                log_written=False,
                journal_written=False,
            ),
            data={
                "path": str(request.url.path),
                "method": request.method,
            },
        )
        return JSONResponse(status_code=500, content=envelope.to_payload())

    @app.get("/")
    async def root() -> dict[str, Any]:
        """
        Minimal root surface for bridge identity and staged route visibility.
        """
        route_registration_healthy = not app.state.pending_route_modules
        envelope = build_response_envelope(
            status=EnvelopeStatus.OK if route_registration_healthy else EnvelopeStatus.DEGRADED,
            request_id=_new_request_id(),
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bridge_info",
            capability_state=CapabilityState.LIVE if route_registration_healthy else CapabilityState.DEGRADED,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            warnings=[] if route_registration_healthy else ["One or more required API route modules failed to register; inspect pending_route_modules."],
            errors=[],
            trace_summary=TraceSummary(
                route_used="root",
                log_written=False,
                journal_written=False,
            ),
            data={
                "bridge_name": BRIDGE_NAME,
                "local_only_by_default": LOCAL_ONLY_BY_DEFAULT,
                "api_version": API_VERSION,
                "contract_version": CONTRACT_VERSION,
                "registered_route_modules": app.state.registered_route_modules,
                "pending_route_modules": app.state.pending_route_modules,
                "route_registration_healthy": route_registration_healthy,
                "local_client_auth": resolved_auth_policy.public_summary(),
            },
        )
        return envelope.to_payload()

    @app.get("/ping")
    async def ping() -> dict[str, Any]:
        """
        Tiny local reachability marker for startup and manual checks.
        """
        envelope = build_response_envelope(
            status=EnvelopeStatus.OK,
            request_id=_new_request_id(),
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="bridge_ping",
            capability_state=CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            warnings=[],
            errors=[],
            trace_summary=TraceSummary(
                route_used="ping",
                log_written=False,
                journal_written=False,
            ),
            data={
                "ok": True,
                "bridge_name": BRIDGE_NAME,
            },
        )
        return envelope.to_payload()

    @app.get("/locality")
    async def locality() -> dict[str, Any]:
        """
        Small trust surface describing bridge locality posture.
        """
        envelope = build_response_envelope(
            status=EnvelopeStatus.OK,
            request_id=_new_request_id(),
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="locality_state",
            capability_state=CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            warnings=[],
            errors=[],
            trace_summary=TraceSummary(
                route_used="locality",
                log_written=False,
                journal_written=False,
            ),
            data={
                "local_only_by_default": LOCAL_ONLY_BY_DEFAULT,
                "allowed_loopback_hosts": sorted(ALLOWED_LOOPBACK_HOSTS),
                "notes": [
                    "This bridge is intended for local use only by default.",
                    "Non-local clients are rejected unless bridge posture is deliberately changed later.",
                ],
            },
        )
        return envelope.to_payload()

    for module_path, router_attr in ROUTE_MODULES:
        _try_include_router(app, module_path, router_attr)

    return app


app = create_app()
