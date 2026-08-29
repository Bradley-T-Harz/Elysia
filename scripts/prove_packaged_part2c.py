#!/usr/bin/env python3
"""Disposable packaged-runtime proof for Pre-10D Parts 2C through 2E.

The script starts the frozen Core twice against one synthetic XDG profile. It
never prints the generated account password, local API credential, memory body,
or model response. Only content-free identifiers, hashes, and boolean truth are
emitted.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_api(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError("Packaged Core exited before readiness: " + output[-2000:])
        try:
            with urlopen(base_url + "/openapi.json", timeout=1):
                return
        except (OSError, URLError, TimeoutError):
            time.sleep(0.25)
    raise RuntimeError("Packaged Core did not become ready within 60 seconds.")


def _credential(runtime_root: Path) -> str:
    path = runtime_root / "elysia" / "auth" / "local-api.credential"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        time.sleep(0.1)
    raise RuntimeError("Packaged Core did not initialize its local API credential.")


def _request(
    base_url: str,
    credential: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = base_url + path
    if query:
        url += "?" + urlencode(query)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
            "X-Elysia-Client": "part2c-packaged-proof",
        },
    )
    try:
        with urlopen(request, timeout=600) as response:
            value = json.load(response)
    except HTTPError as exc:
        safe_body = exc.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {safe_body}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{method} {path} returned a non-object response.")
    return value


def _start(binary: Path, env: dict[str, str]) -> tuple[subprocess.Popen[str], str, str]:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            str(binary),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--mode",
            "packaged",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    _wait_for_api(base_url, process)
    credential = _credential(Path(env["XDG_RUNTIME_DIR"]))
    return process, base_url, credential


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def _chat_truth(envelope: dict[str, Any], memory_id: str) -> dict[str, Any]:
    data = dict(envelope.get("data") or {})
    receipt = dict(data.get("context_receipt") or {})
    governor = dict(data.get("governor") or {})
    compute = dict(data.get("compute") or {})
    admitted = [
        str(item.get("candidate_id"))
        for item in receipt.get("admitted", [])
        if isinstance(item, dict) and item.get("candidate_id")
    ]
    response = str(data.get("response_text") or "")
    return {
        "envelope_status": envelope.get("status"),
        "capability_state": envelope.get("capability_state"),
        "errors": [str(item)[:500] for item in (envelope.get("errors") or [])],
        "warnings": [str(item)[:500] for item in (envelope.get("warnings") or [])],
        "response_source": data.get("response_source"),
        "invocation_status": data.get("invocation_status"),
        "selected_runtime": data.get("selected_runtime"),
        "selected_model_runtime_tag": data.get("selected_model_runtime_tag"),
        "used_fallback": bool(data.get("used_fallback")),
        "memory_admitted": f"memory:{memory_id}" in admitted,
        "admitted_source_count": len(admitted),
        "model_context_window": receipt.get("model_context_window"),
        "receipt_version": receipt.get("receipt_version"),
        "reasoning_gear": data.get("reasoning_gear") or governor.get("selected_gear"),
        "governor_version": governor.get("version"),
        "compute_device": compute.get("selected_device"),
        "effective_autonomy_level": governor.get("effective_autonomy_level"),
        "cognition_receipt_content_free": bool(governor.get("content_free")),
        "response_sha256": sha256(response.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument(
        "--profile-label",
        default="one_file",
        choices=("one_file", "deb", "appimage"),
    )
    parser.add_argument(
        "--xdg-root",
        type=Path,
        help="Caller-owned disposable /tmp root, used for optional-profile package proof.",
    )
    parser.add_argument("--expect-semantic", action="store_true")
    parser.add_argument(
        "--expect-part2d",
        action="store_true",
        help="Also prove Part 2D identity, policy, cognition, and stop contracts.",
    )
    parser.add_argument(
        "--expect-part2e",
        action="store_true",
        help="Also prove Part 2E forms, tiers, jobs, archive/restore, deletion, and restart contracts.",
    )
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"Packaged Core does not exist: {binary}")

    password = secrets.token_urlsafe(32)
    managed_password = secrets.token_urlsafe(32)
    restore_password = secrets.token_urlsafe(32)
    archive_recovery = secrets.token_urlsafe(32)
    marker = "cobalt estuary lantern seventy-three"
    part2e_archive_base64: str | None = None
    part2e_record_ids: dict[str, str] = {}
    part2e_first: dict[str, Any] = {}
    if args.xdg_root is not None:
        requested_root = args.xdg_root.resolve()
        if not str(requested_root).startswith("/tmp/"):
            raise SystemExit("A caller-owned proof root must be an explicit disposable /tmp path.")
        requested_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_context = nullcontext(str(requested_root))
    else:
        root_context = tempfile.TemporaryDirectory(prefix=f"elysia-part2c-{args.profile_label}-")
    with root_context as root:
        proof_root = Path(root)
        runtime = proof_root / "runtime"
        runtime.mkdir(mode=0o700, exist_ok=True)
        runtime.chmod(0o700)
        env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(proof_root / "config"),
            "XDG_DATA_HOME": str(proof_root / "data"),
            "XDG_CACHE_HOME": str(proof_root / "cache"),
            "XDG_STATE_HOME": str(proof_root / "state"),
            "XDG_RUNTIME_DIR": str(runtime),
            "ELYSIA_QA_RUN_ID": f"pass10d-i-{proof_root.name}",
        }

        first_process, first_url, first_credential = _start(binary, env)
        try:
            created = _request(
                first_url,
                first_credential,
                "POST",
                "/account/create",
                {"username": "part2c-packaged-synthetic", "password": password},
            )
            if created.get("status") != "ok":
                raise RuntimeError("Synthetic packaged account creation did not succeed.")
            created_state = dict(((created.get("data") or {}).get("state") or {}))
            if args.expect_part2d and created_state.get("active_role") != "installation_owner":
                raise RuntimeError("The first packaged identity was not Installation Owner.")

            stored = _request(
                first_url,
                first_credential,
                "POST",
                "/memory/items",
                {
                    "title": "Synthetic packaged continuity marker",
                    "body": f"The synthetic packaged continuity marker is {marker}.",
                    "why_stored": "Disposable Part 2C packaged-runtime proof.",
                    "scope": "user",
                    "form": "semantic",
                    "privacy": "normal",
                    "status": "active",
                    "user_confirmed": True,
                },
            )
            memory_id = str(((stored.get("data") or {}).get("record") or {}).get("memory_id") or "")
            if not memory_id:
                raise RuntimeError("Packaged Memory Fabric did not return a stable memory id.")

            found = _request(
                first_url,
                first_credential,
                "GET",
                "/memory/items",
                query={"search": "cobalt estuary lantern"},
            )
            items = list((found.get("data") or {}).get("items") or [])
            if not any(str(item.get("memory_id")) == memory_id for item in items):
                raise RuntimeError("Packaged FTS projection did not retrieve the synthetic memory.")
            query_truth = dict((found.get("data") or {}).get("query_truth") or {})
            expected_semantic_state = "ready" if args.expect_semantic else "optional_not_installed"
            if query_truth.get("semantic_projection_state") != expected_semantic_state:
                raise RuntimeError("Packaged Memory search did not expose the expected semantic state.")

            health = _request(first_url, first_credential, "GET", "/memory/health")
            health_data = dict((health.get("data") or {}).get("health") or {})
            lexical = dict(health_data.get("lexical_projection") or {})
            evidence = dict(health_data.get("research_evidence") or {})
            semantic = dict(health_data.get("semantic_projection") or {})
            if lexical.get("state") != "ready":
                raise RuntimeError("Packaged FTS projection did not report ready health.")
            if evidence.get("state") != "ready":
                raise RuntimeError("Packaged research Evidence Store did not report ready health.")
            expected_health_state = "ready" if args.expect_semantic else "optional_not_installed"
            if not (
                semantic.get("state") == expected_health_state
                and semantic.get("promotion_decision") == "promoted_optional_local_profile"
                and semantic.get("private_vectors_persisted") is False
                and semantic.get("sealed_vectors_persisted") is False
            ):
                raise RuntimeError("Packaged Core omitted the optional semantic production contract.")

            doctor = _request(
                first_url,
                first_credential,
                "GET",
                "/status/doctor",
                query={"probe_local_services": "true"},
            )
            doctor_data = dict(doctor.get("data") or {})
            doctor_checks = {
                str(item.get("check_id")): item
                for item in (doctor_data.get("checks") or [])
                if isinstance(item, dict)
            }
            semantic_doctor = dict(doctor_checks.get("semantic_projection_service") or {})
            expected_doctor_status = "present" if args.expect_semantic else "optional_missing"
            if semantic_doctor.get("status") != expected_doctor_status:
                raise RuntimeError("Packaged doctor did not report the expected semantic profile truth.")

            blocked = _request(
                first_url,
                first_credential,
                "POST",
                "/research/search",
                {
                    "question": "Synthetic public research boundary proof",
                    "queries": ["synthetic public boundary proof"],
                },
            )
            blocked_data = dict(blocked.get("data") or {})
            if not (
                blocked.get("status") == "blocked"
                and blocked_data.get("internet_master_enabled") is False
                and blocked_data.get("network_access_used") is False
                and blocked_data.get("private_context_sent") is False
            ):
                raise RuntimeError("Packaged Internet-OFF research boundary was not fail-closed.")

            if args.expect_part2e:
                unlocked = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/memory/sealed/unlock",
                    {"password": password, "ttl_seconds": 900},
                )
                if unlocked.get("status") != "ok":
                    raise RuntimeError("Packaged Sealed vault did not unlock for Part 2E proof.")
                form_data = {
                    "episodic": {"actors": ["synthetic-operator"], "outcome": "observed"},
                    "semantic": {"confirmation": "explicit"},
                    "procedural": {"steps": ["inspect", "verify"], "verified": False},
                    "prospective": {"due_at": "2030-01-01T00:00:00Z", "state": "pending"},
                    "relational": {"relation": "supports", "target": "synthetic-project"},
                    "predictive": {"basis": "synthetic baseline", "prediction": "improves"},
                    "corrective": {"change_kind": "direct_correction"},
                    "metacognitive": {"metric": "retrieval_precision", "value": 0.8},
                    "audit": {"event_code": "synthetic_operation", "content_minimized": True},
                }
                for form, details in form_data.items():
                    created_form = _request(
                        first_url,
                        first_credential,
                        "POST",
                        "/memory/items",
                        {
                            "title": f"Synthetic packaged {form}",
                            "body": f"SYNTHETIC_PACKAGED_{form.upper()}",
                            "why_stored": "Disposable Part 2E nine-form proof.",
                            "form": form,
                            "privacy": "normal",
                            "form_data": details,
                            "observed_at": "2026-08-22T00:00:00Z",
                        },
                    )
                    form_record = dict((created_form.get("data") or {}).get("record") or {})
                    if form_record.get("form") != form or not form_record.get("memory_id"):
                        raise RuntimeError(f"Packaged {form} memory behavior was unavailable.")
                    part2e_record_ids[form] = str(form_record["memory_id"])

                private_record = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/memory/items",
                    {
                        "title": "Synthetic packaged private",
                        "body": "SYNTHETIC_PACKAGED_PRIVATE_CANARY",
                        "why_stored": "Disposable Private archive proof.",
                        "form": "semantic",
                        "privacy": "private",
                        "form_data": {"confirmation": "explicit"},
                    },
                )
                sealed_record = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/memory/items",
                    {
                        "title": "Synthetic packaged sealed",
                        "body": "SYNTHETIC_PACKAGED_SEALED_CANARY",
                        "why_stored": "Disposable Sealed archive proof.",
                        "form": "semantic",
                        "privacy": "sealed",
                        "form_data": {"confirmation": "explicit"},
                    },
                )
                part2e_record_ids["private"] = str(
                    ((private_record.get("data") or {}).get("record") or {}).get("memory_id")
                    or ""
                )
                part2e_record_ids["sealed"] = str(
                    ((sealed_record.get("data") or {}).get("record") or {}).get("memory_id")
                    or ""
                )
                if not part2e_record_ids["private"] or not part2e_record_ids["sealed"]:
                    raise RuntimeError("Packaged Private/Sealed memory creation failed.")

                prospective_action = _request(
                    first_url,
                    first_credential,
                    "POST",
                    f"/memory/items/{part2e_record_ids['prospective']}/form-action",
                    {"action": "snooze", "reason": "Synthetic package proof.", "due_at": "2031-01-01T00:00:00Z"},
                )
                if (
                    ((prospective_action.get("data") or {}).get("record") or {}).get("form_data", {}).get("due_at")
                    != "2031-01-01T00:00:00Z"
                ):
                    raise RuntimeError("Packaged prospective memory did not snooze durably.")

                cold_id = part2e_record_ids["episodic"]
                cold = _request(
                    first_url,
                    first_credential,
                    "PUT",
                    f"/memory/items/{cold_id}/tier",
                    {"tier": "cold", "reason": "Synthetic packaged cold proof."},
                )
                if ((cold.get("data") or {}).get("record") or {}).get("activation_tier") != "cold":
                    raise RuntimeError("Packaged memory did not enter real cold placement.")
                warm = _request(
                    first_url,
                    first_credential,
                    "PUT",
                    f"/memory/items/{cold_id}/tier",
                    {"tier": "warm", "reason": "Synthetic packaged rehydration proof."},
                )
                if not (warm.get("data") or {}).get("rehydrated"):
                    raise RuntimeError("Packaged cold memory did not rehydrate.")

                settings_envelope = _request(
                    first_url, first_credential, "GET", "/memory/settings"
                )
                release_settings = dict(
                    (settings_envelope.get("data") or {}).get("settings") or {}
                )
                release_settings.update(
                    memory_storage_profile="efficient",
                    backup_enabled=True,
                    backup_schedule="manual",
                    backup_retention_count=2,
                    consolidation_enabled=True,
                    consolidation_schedule="manual",
                    prospective_notifications_enabled=True,
                )
                updated_release_settings = _request(
                    first_url,
                    first_credential,
                    "PUT",
                    "/memory/settings",
                    release_settings,
                )
                if (
                    ((updated_release_settings.get("data") or {}).get("settings") or {}).get(
                        "memory_storage_profile"
                    )
                    != "efficient"
                ):
                    raise RuntimeError("Packaged Part 2E Settings did not persist.")

                graph_job = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/memory/jobs",
                    {"job_kind": "projection_rebuild"},
                )
                graph_job_id = str(
                    ((graph_job.get("data") or {}).get("job") or {}).get("job_id") or ""
                )
                graph_run = _request(
                    first_url,
                    first_credential,
                    "POST",
                    f"/memory/jobs/{graph_job_id}/run",
                    {},
                )
                if ((graph_run.get("data") or {}).get("job") or {}).get("state") != "completed":
                    raise RuntimeError("Packaged projection rebuild job did not complete.")

                managed_job = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/memory/jobs",
                    {"job_kind": "managed_backup"},
                )
                managed_job_id = str(
                    ((managed_job.get("data") or {}).get("job") or {}).get("job_id") or ""
                )
                managed_run = _request(
                    first_url,
                    first_credential,
                    "POST",
                    f"/memory/jobs/{managed_job_id}/run",
                    {},
                )
                if ((managed_run.get("data") or {}).get("job") or {}).get("state") != "completed":
                    raise RuntimeError("Packaged encrypted managed backup did not complete.")

                portable = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/memory/archives/export",
                    {
                        "recovery_material": archive_recovery,
                        "archive_kind": "portable_export",
                        "scope": "full_account",
                    },
                )
                portable_data = dict((portable.get("data") or {}).get("archive") or {})
                part2e_archive_base64 = str(portable_data.get("archive_base64") or "")
                if not (
                    portable_data.get("encrypted") is True
                    and portable_data.get("portable") is True
                    and part2e_archive_base64
                ):
                    raise RuntimeError("Packaged portable encrypted archive was not created.")
                part2e_first = {
                    "nine_forms_created": len(form_data),
                    "private_created": True,
                    "sealed_created": True,
                    "prospective_snoozed": True,
                    "cold_rehydrated": True,
                    "settings_persisted": True,
                    "projection_job_completed": True,
                    "managed_backup_completed": True,
                    "portable_archive_created": True,
                }

            part2d_first: dict[str, Any] = {}
            if args.expect_part2d:
                settings_envelope = _request(
                    first_url, first_credential, "GET", "/memory/settings"
                )
                settings = dict((settings_envelope.get("data") or {}).get("settings") or {})
                settings.update(
                    autonomy_level=5,
                    autonomy_domain_overrides={
                        "web_initiative": 3,
                        "external_mutations": 1,
                    },
                    preferred_reasoning_gear="standard",
                    compute_preference="automatic",
                    # Package proof validates live governed cognition and
                    # continuity, not maximum model size.  The resource policy
                    # earns the configured local 8B route and remains viable
                    # during honest thermal CPU fallback.
                    model_performance_preference="resource",
                    background_cognition_enabled=True,
                    max_background_jobs=2,
                )
                updated = _request(
                    first_url, first_credential, "PUT", "/memory/settings", settings
                )
                updated_settings = dict((updated.get("data") or {}).get("settings") or {})
                if not (
                    updated_settings.get("autonomy_level") == 5
                    and updated_settings.get("autonomy_domain_overrides", {}).get(
                        "external_mutations"
                    ) == 1
                ):
                    raise RuntimeError("Packaged Part 2D controls did not persist through the API.")

                second = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/account/create",
                    {
                        "username": "part2d-managed-synthetic",
                        "password": managed_password,
                        "managed_profile": True,
                    },
                )
                if second.get("status") != "ok":
                    raise RuntimeError("Owner could not create a packaged managed profile.")
                second_state = dict(((second.get("data") or {}).get("state") or {}))
                if second_state.get("active_role") != "installation_owner":
                    raise RuntimeError("Managed-profile creation silently switched the Owner session.")

                admin = _request(first_url, first_credential, "GET", "/admin/summary")
                admin_data = dict(admin.get("data") or {})
                if not (
                    len(admin_data.get("roster") or []) == 2
                    and admin_data.get("content_authorities_queried") == []
                    and admin_data.get("admin_content_access_granted") is False
                    and admin_data.get("local_online_identity_federated") is False
                ):
                    raise RuntimeError("Packaged Admin truth crossed its content boundary.")

                _request(first_url, first_credential, "POST", "/account/logout")
                managed_login = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/account/login",
                    {
                        "username": "part2d-managed-synthetic",
                        "password": managed_password,
                    },
                )
                managed_state = dict(((managed_login.get("data") or {}).get("state") or {}))
                if not (
                    managed_state.get("active_profile_managed") is True
                    and managed_state.get("supervision_notice")
                ):
                    raise RuntimeError("Packaged managed supervision was not conspicuous.")
                isolated = _request(
                    first_url,
                    first_credential,
                    "GET",
                    "/memory/items",
                    query={"search": "cobalt estuary lantern"},
                )
                if (isolated.get("data") or {}).get("items"):
                    raise RuntimeError("Packaged account isolation exposed the Owner's memory.")
                managed_cognition = _request(
                    first_url, first_credential, "GET", "/cognition/status"
                )
                managed_controls = dict(
                    (managed_cognition.get("data") or {}).get("effective_controls") or {}
                )
                if not (
                    managed_controls.get("managed_profile") is True
                    and managed_controls.get("autonomy_level", 99) <= 3
                ):
                    raise RuntimeError("Packaged managed policy did not narrow autonomy.")
                marketplace = _request(
                    first_url, first_credential, "GET", "/marketplace/link/status"
                )
                marketplace_state = dict(
                    (marketplace.get("data") or {}).get("marketplace_link") or {}
                )
                if not (
                    marketplace_state.get("identity_federated") is False
                    and marketplace_state.get("local_admin_granted_by_marketplace") is False
                    and marketplace_state.get("marketplace_admin_granted_by_local") is False
                ):
                    raise RuntimeError("Packaged Marketplace/local identity separation failed.")
                _request(first_url, first_credential, "POST", "/account/logout")
                owner_login = _request(
                    first_url,
                    first_credential,
                    "POST",
                    "/account/login",
                    {
                        "username": "part2c-packaged-synthetic",
                        "password": password,
                    },
                )
                if (
                    ((owner_login.get("data") or {}).get("state") or {}).get("active_role")
                    != "installation_owner"
                ):
                    raise RuntimeError("Packaged Owner authority was not restored after profile switch.")
                part2d_first = {
                    "first_account_owner": True,
                    "managed_profile_created_without_session_switch": True,
                    "managed_profile_visibly_supervised": True,
                    "managed_policy_narrowed_autonomy": True,
                    "account_memory_isolation": True,
                    "admin_content_authorities_queried": [],
                    "admin_content_access_granted": False,
                    "local_online_identity_federated": False,
                    "part2d_controls_persisted": True,
                }
        finally:
            _stop(first_process)

        second_process, second_url, second_credential = _start(binary, env)
        try:
            account_state = _request(second_url, second_credential, "GET", "/account/state")
            state = dict(account_state.get("data") or {})
            if not (state.get("has_user") and state.get("is_authenticated")):
                raise RuntimeError("Synthetic packaged account/session did not survive Core restart.")

            part2d_second: dict[str, Any] = {}
            if args.expect_part2d:
                cognition = _request(
                    second_url, second_credential, "GET", "/cognition/status"
                )
                cognition_data = dict(cognition.get("data") or {})
                controls = dict(cognition_data.get("effective_controls") or {})
                levels = dict(cognition_data.get("autonomy_levels") or {})
                gears = list(cognition_data.get("reasoning_gears") or [])
                if not (
                    controls.get("autonomy_level") == 5
                    and controls.get("preferred_reasoning_gear") == "standard"
                    and controls.get("model_performance_preference") == "resource"
                    and len(levels) == 5
                    and len(gears) == 6
                ):
                    raise RuntimeError("Packaged Part 2D cognition controls did not survive restart.")
                part2d_second = {
                    "controls_survived_restart": True,
                    "reasoning_gear_count": len(gears),
                    "autonomy_level_count": len(levels),
                    "governor_contract": cognition_data.get("governor_contract"),
                    "compute_lease_ledger_state": (
                        cognition_data.get("compute") or {}
                    ).get("lease_ledger_state"),
                }

            recalled = _request(
                second_url,
                second_credential,
                "GET",
                "/memory/items",
                query={"search": "cobalt estuary lantern"},
            )
            recalled_items = list((recalled.get("data") or {}).get("items") or [])
            if not any(str(item.get("memory_id")) == memory_id for item in recalled_items):
                raise RuntimeError("Canonical memory did not survive packaged Core restart.")

            part2e_second: dict[str, Any] = {}
            if args.expect_part2e:
                for form in (
                    "episodic", "semantic", "procedural", "prospective",
                    "relational", "predictive", "corrective", "metacognitive", "audit",
                ):
                    restored_form = _request(
                        second_url,
                        second_credential,
                        "GET",
                        f"/memory/items/{part2e_record_ids[form]}",
                    )
                    if (
                        ((restored_form.get("data") or {}).get("record") or {}).get("form")
                        != form
                    ):
                        raise RuntimeError(f"Packaged {form} memory did not survive restart.")
                _request(
                    second_url,
                    second_credential,
                    "POST",
                    "/memory/sealed/unlock",
                    {"password": password, "ttl_seconds": 900},
                )
                private_after_restart = _request(
                    second_url,
                    second_credential,
                    "GET",
                    f"/memory/items/{part2e_record_ids['private']}",
                )
                sealed_after_restart = _request(
                    second_url,
                    second_credential,
                    "GET",
                    f"/memory/items/{part2e_record_ids['sealed']}",
                )
                if not (
                    ((private_after_restart.get("data") or {}).get("record") or {}).get("content_state")
                    == "available"
                    and ((sealed_after_restart.get("data") or {}).get("record") or {}).get("content_state")
                    == "available"
                ):
                    raise RuntimeError("Packaged Private/Sealed content did not survive restart.")
                archive_status = _request(
                    second_url, second_credential, "GET", "/memory/archives"
                )
                if len((archive_status.get("data") or {}).get("archives") or []) < 2:
                    raise RuntimeError("Packaged managed/portable archive registry did not survive restart.")
                homeostasis = dict(
                    (
                        _request(
                            second_url,
                            second_credential,
                            "GET",
                            "/memory/homeostasis",
                        ).get("data")
                        or {}
                    ).get("homeostasis")
                    or {}
                )
                if not (
                    homeostasis.get("silent_hard_delete_allowed") is False
                    and homeostasis.get("cross_account_accounting_exposed") is False
                ):
                    raise RuntimeError("Packaged storage homeostasis crossed ownership law.")

                sacrificial = _request(
                    second_url,
                    second_credential,
                    "POST",
                    "/memory/items",
                    {
                        "title": "Synthetic packaged deletion target",
                        "body": "SYNTHETIC_PACKAGED_DELETE_CANARY",
                        "why_stored": "Disposable exhaustive delete proof.",
                        "form": "semantic",
                        "privacy": "normal",
                        "form_data": {"confirmation": "explicit"},
                    },
                )
                sacrificial_id = str(
                    ((sacrificial.get("data") or {}).get("record") or {}).get("memory_id")
                    or ""
                )
                delete_preview = _request(
                    second_url,
                    second_credential,
                    "POST",
                    f"/memory/targets/{sacrificial_id}/consequences/preview",
                    {
                        "action": "hard_delete",
                        "reason": "Synthetic exhaustive packaged deletion proof.",
                    },
                )
                delete_approval = dict(
                    (delete_preview.get("data") or {}).get("approval") or {}
                )
                delete_plan = dict(
                    (delete_approval.get("consequence") or {}).get("deletion_plan") or {}
                )
                if not delete_plan.get("managed_state_fingerprint"):
                    raise RuntimeError("Packaged hard-delete preview lacked exact managed-state binding.")
                deleted = _request(
                    second_url,
                    second_credential,
                    "POST",
                    f"/memory/targets/{sacrificial_id}/consequences/apply",
                    {
                        "approval_id": delete_approval.get("approval_id"),
                        "approval_token": delete_approval.get("approval_token"),
                    },
                )
                delete_result = dict(deleted.get("data") or {})
                if not (
                    delete_result.get("content_retained_in_receipt") is False
                    and (delete_result.get("absence_verification") or {}).get("absent") is True
                    and delete_result.get("offline_user_exports_erased") is False
                ):
                    raise RuntimeError("Packaged hard deletion did not prove exhaustive managed absence.")
                part2e_second = {
                    "all_forms_survived_restart": True,
                    "private_survived_restart": True,
                    "sealed_survived_restart": True,
                    "archive_registry_survived_restart": True,
                    "homeostasis_content_blind": True,
                    "hard_delete_absence_verified": True,
                    "offline_copy_limit_truthful": True,
                }

            chat = _request(
                second_url,
                second_credential,
                "POST",
                "/chat/send",
                {
                    "message": "What is the exact synthetic packaged continuity marker?",
                    "requested_mode": "researcher",
                    "ui_surface": "packaged_part2c_proof",
                },
            )
            chat_truth = _chat_truth(chat, memory_id)
            if not (
                chat_truth["response_source"] == "live_invoker"
                and chat_truth["invocation_status"] == "ok"
                and chat_truth["memory_admitted"] is True
            ):
                raise RuntimeError(
                    "Packaged live cognition did not admit the durable memory: "
                    + json.dumps(chat_truth, sort_keys=True)
                )
            if args.expect_part2d and not (
                chat_truth["governor_version"]
                and chat_truth["reasoning_gear"] in {
                    "reflex", "quick", "standard", "deep", "deliberative",
                    "research_engineering",
                }
                and chat_truth["cognition_receipt_content_free"] is True
            ):
                raise RuntimeError("Packaged live cognition omitted the Part 2D Governor receipt.")

            receipts = _request(
                second_url,
                second_credential,
                "GET",
                "/research/context-receipts",
            )
            receipt_rows = list((receipts.get("data") or {}).get("context_receipts") or [])
            if not receipt_rows:
                raise RuntimeError("Packaged cognition did not persist a context receipt.")

            if args.expect_part2d:
                stopped = _request(
                    second_url,
                    second_credential,
                    "POST",
                    "/emergency/stop",
                    {"reason": "Synthetic packaged Part 2D stop proof"},
                )
                stopped_data = dict(stopped.get("data") or {})
                if not (
                    stopped_data.get("active") is True
                    and stopped_data.get("runtime_autonomy_override") == 1
                ):
                    raise RuntimeError("Packaged emergency stop did not enter safe posture.")
                stopped_status = _request(
                    second_url, second_credential, "GET", "/emergency/status"
                )
                if (stopped_status.get("data") or {}).get("active") is not True:
                    raise RuntimeError("Packaged emergency posture was not observable.")
                reset = _request(
                    second_url,
                    second_credential,
                    "POST",
                    "/emergency/reset",
                    {"acknowledge_safe_restart": True},
                )
                if (reset.get("data") or {}).get("active") is not False:
                    raise RuntimeError("Packaged Owner could not explicitly reset emergency posture.")
                part2d_second.update(
                    governor_receipt_content_free=True,
                    emergency_stop_and_reset=True,
                    emergency_runtime_autonomy_override=1,
                )

            clean_restore: dict[str, Any] = {}
            if args.expect_part2e:
                if not part2e_archive_base64:
                    raise RuntimeError("Packaged portable archive bytes were not retained for restore proof.")
                target_root = proof_root / "clean-restore-installation"
                target_runtime = target_root / "runtime"
                target_runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
                target_runtime.chmod(0o700)
                target_env = {
                    **os.environ,
                    "XDG_CONFIG_HOME": str(target_root / "config"),
                    "XDG_DATA_HOME": str(target_root / "data"),
                    "XDG_CACHE_HOME": str(target_root / "cache"),
                    "XDG_STATE_HOME": str(target_root / "state"),
                    "XDG_RUNTIME_DIR": str(target_runtime),
                }
                target_process, target_url, target_credential = _start(binary, target_env)
                try:
                    target_created = _request(
                        target_url,
                        target_credential,
                        "POST",
                        "/account/create",
                        {
                            "username": "part2e-clean-restore-synthetic",
                            "password": restore_password,
                        },
                    )
                    if target_created.get("status") != "ok":
                        raise RuntimeError("Clean packaged restore account creation failed.")
                    # A portable archive containing Sealed records must not
                    # bypass the target account's explicit user-unlock law.
                    # Unlock before import so those records can be re-enveloped
                    # for this clean installation; the archive recovery
                    # material alone is deliberately insufficient authority.
                    target_unlock = _request(
                        target_url,
                        target_credential,
                        "POST",
                        "/memory/sealed/unlock",
                        {"password": restore_password, "ttl_seconds": 900},
                    )
                    if (
                        ((target_unlock.get("data") or {}).get("sealed") or {}).get(
                            "unlocked"
                        )
                        is not True
                    ):
                        raise RuntimeError(
                            "Clean packaged restore could not establish the explicit Sealed unlock boundary."
                        )
                    preview_envelope = _request(
                        target_url,
                        target_credential,
                        "POST",
                        "/memory/archives/restore/preview",
                        {
                            "archive_base64": part2e_archive_base64,
                            "recovery_material": archive_recovery,
                        },
                    )
                    preview = dict((preview_envelope.get("data") or {}).get("restore") or {})
                    plan = dict(preview.get("plan") or {})
                    if not (
                        int(plan.get("additions") or 0) >= len(part2e_record_ids)
                        and int(plan.get("conflicts") or 0) == 0
                    ):
                        raise RuntimeError("Clean packaged restore preview was incomplete or conflicted.")
                    applied_envelope = _request(
                        target_url,
                        target_credential,
                        "POST",
                        "/memory/archives/restore/apply",
                        {
                            "restore_plan_id": preview.get("restore_plan_id"),
                            "approval_id": preview.get("approval_id"),
                            "approval_token": preview.get("approval_token"),
                            "recovery_material": archive_recovery,
                        },
                    )
                    applied = dict((applied_envelope.get("data") or {}).get("restore") or {})
                    if not (
                        applied.get("projection_rebuild_verified") is True
                        and int(applied.get("restored_record_count") or 0)
                        >= len(part2e_record_ids)
                    ):
                        projection_states = {
                            str(name): str((result or {}).get("state"))
                            for name, result in dict(
                                applied.get("projection_results") or {}
                            ).items()
                            if isinstance(result, dict)
                        }
                        raise RuntimeError(
                            "Clean packaged restore did not atomically rebuild projections: "
                            f"envelope_status={applied_envelope.get('status')!r}, "
                            f"errors={[str(value)[:300] for value in (applied_envelope.get('errors') or [])]}, "
                            f"verified={applied.get('projection_rebuild_verified')!r}, "
                            f"restored_record_count={int(applied.get('restored_record_count') or 0)}, "
                            f"expected_minimum={len(part2e_record_ids)}, "
                            f"projection_states={projection_states}"
                        )
                    _request(
                        target_url,
                        target_credential,
                        "POST",
                        "/memory/sealed/unlock",
                        {"password": restore_password, "ttl_seconds": 900},
                    )
                    for label, record_id in part2e_record_ids.items():
                        restored = _request(
                            target_url,
                            target_credential,
                            "GET",
                            f"/memory/items/{record_id}",
                        )
                        record = dict((restored.get("data") or {}).get("record") or {})
                        if label in {"private", "sealed"}:
                            if record.get("content_state") != "available":
                                raise RuntimeError(
                                    f"Clean packaged restore could not decrypt {label} memory."
                                )
                        elif record.get("form") != label:
                            raise RuntimeError(
                                f"Clean packaged restore lost the {label} memory form."
                            )
                finally:
                    _stop(target_process)

                target_restart, target_url, target_credential = _start(binary, target_env)
                try:
                    target_state = dict(
                        (
                            _request(
                                target_url,
                                target_credential,
                                "GET",
                                "/account/state",
                            ).get("data")
                            or {}
                        )
                    )
                    if not (
                        target_state.get("has_user")
                        and target_state.get("is_authenticated")
                    ):
                        raise RuntimeError("Clean restored packaged identity did not survive restart.")
                    continuity = _request(
                        target_url,
                        target_credential,
                        "GET",
                        f"/memory/items/{part2e_record_ids['episodic']}",
                    )
                    if (
                        ((continuity.get("data") or {}).get("record") or {}).get("form")
                        != "episodic"
                    ):
                        raise RuntimeError("Clean packaged restore did not survive Core restart.")
                finally:
                    _stop(target_restart)
                clean_restore = {
                    "clean_install_account_created": True,
                    "staged_preview_conflict_free": True,
                    "atomic_restore_applied": True,
                    "projection_rebuild_verified": True,
                    "nine_forms_restored": True,
                    "private_and_sealed_decrypted_by_target_owner": True,
                    "restored_identity_and_memory_survived_restart": True,
                    "archive_secret_values_emitted": False,
                }

            result = {
                "profile_label": args.profile_label,
                "binary_sha256": sha256(binary.read_bytes()).hexdigest(),
                "disposable_xdg": True,
                "synthetic_account_created": True,
                "account_session_survived_restart": True,
                "canonical_memory_survived_restart": True,
                "lexical_projection_retrieved": True,
                "lexical_projection_status": lexical.get("state"),
                "evidence_store_status": evidence.get("state"),
                "semantic_projection_status": semantic.get("state"),
                "semantic_search_state": query_truth.get("semantic_projection_state"),
                "semantic_promotion_decision": semantic.get("promotion_decision"),
                "semantic_private_vectors_persisted": semantic.get("private_vectors_persisted"),
                "semantic_sealed_vectors_persisted": semantic.get("sealed_vectors_persisted"),
                "semantic_doctor_status": semantic_doctor.get("status"),
                "internet_off_blocked": True,
                "internet_off_network_access_used": False,
                "private_context_sent": False,
                "context_receipt_count": len(receipt_rows),
                "live_cognition": chat_truth,
                "secret_values_emitted": False,
                "operator_data_used": False,
                "part2d": {**part2d_first, **part2d_second}
                if args.expect_part2d
                else {"not_requested": True},
                "part2e": {**part2e_first, **part2e_second, **clean_restore}
                if args.expect_part2e
                else {"not_requested": True},
            }
            print(json.dumps(result, indent=2, sort_keys=True))
        finally:
            _stop(second_process)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
