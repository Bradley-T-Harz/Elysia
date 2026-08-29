#!/usr/bin/env python3
"""Disposable real-inference and restart proof for Pre-10D Part 2C.

Run `seed` and `recall` in separate processes against the same disposable XDG
root.  The synthetic password is accepted only through an environment variable
and is never printed or written by this script.
"""

from __future__ import annotations

import argparse
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _state_path() -> Path:
    value = os.environ.get("ELYSIA_PART2C_PROOF_STATE", "").strip()
    if not value:
        raise RuntimeError("ELYSIA_PART2C_PROOF_STATE must name a disposable state file.")
    return Path(value)


def _password() -> str:
    value = os.environ.get("ELYSIA_PART2C_SYNTHETIC_PASSWORD", "")
    if len(value) < 16:
        raise RuntimeError("A synthetic password of at least 16 characters is required.")
    return value


def _response_truth(envelope: dict[str, Any]) -> dict[str, Any]:
    data = dict(envelope.get("data") or {})
    receipt = dict(data.get("context_receipt") or {})
    response = str(data.get("response_text") or "")
    return {
        "envelope_status": envelope.get("status"),
        "response_source": data.get("response_source"),
        "invocation_status": data.get("invocation_status"),
        "selected_runtime": data.get("selected_runtime"),
        "selected_model_runtime_tag": data.get("selected_model_runtime_tag"),
        "used_fallback": bool(data.get("used_fallback")),
        "response_sha256": sha256(response.encode("utf-8")).hexdigest(),
        "response_preview": response[:700],
        "admitted_source_ids": [
            str(item.get("candidate_id"))
            for item in receipt.get("admitted", [])
            if isinstance(item, dict) and item.get("candidate_id")
        ],
        "excluded_source_ids": [
            str(item.get("candidate_id"))
            for item in receipt.get("excluded", [])
            if isinstance(item, dict) and item.get("candidate_id")
        ],
        "model_context_window": receipt.get("model_context_window"),
        "reasoning_gear": receipt.get("reasoning_gear"),
        "receipt_version": receipt.get("receipt_version"),
    }


async def _send(payload: dict[str, Any]) -> dict[str, Any]:
    from app.api.routes.chat import send_chat

    result = await send_chat(payload)
    if not isinstance(result, dict):
        raise RuntimeError("The governed chat route returned a non-object result.")
    return result


def seed() -> dict[str, Any]:
    from app.api import account_service
    from app.api.account_service import get_active_elysia_paths
    from app.api.project_service import create_project, update_project_metadata
    from app.api.conversation_service import ensure_conversation
    from app.api.schemas.account import AccountCreateRequest, AccountLoginRequest
    from app.cognition.evidence_repository import EvidenceRepository
    from app.memory.canonical_models import (
        MemoryCorrectionRequest,
        MemoryCreateRequest,
        MemoryForm,
        MemoryPrincipal,
        MemoryScope,
        MemorySettings,
    )
    from app.memory.canonical_repository import MemoryRepository
    from app.memory.fabric_service import MemoryFabricService

    username = "p2c-synthetic-owner"
    account_service.create_account(
        AccountCreateRequest(username=username, password=_password())
    )
    # Multi-account creation is an authenticated local operation. Create the
    # isolated control account now, then return to the owner before any domain
    # objects exist.
    account_service.create_account(
        AccountCreateRequest(username="p2c-synthetic-control", password=_password())
    )
    repository = MemoryRepository(paths=get_active_elysia_paths())
    fabric = MemoryFabricService(repository=repository)
    proof_settings = MemorySettings(
        internet_master_enabled=False,
        retrieval_breadth="broad",
        research_initiative="manual",
        safe_search_level="strict",
        # This fixture proves real continuity and authorization, not the
        # workstation's maximum model size. Use the same persisted,
        # production-governed resource route as packaged qualification so
        # the local 8B model is earned under constrained VRAM/thermal state.
        preferred_reasoning_gear="standard",
        model_performance_preference="resource",
    )
    account_service.login(
        AccountLoginRequest(username="p2c-synthetic-control", password=_password())
    )
    control_principal = MemoryPrincipal.model_validate(
        account_service.get_authenticated_principal()
    )
    fabric.update_settings(control_principal, proof_settings)
    account_service.login(
        AccountLoginRequest(username=username, password=_password())
    )
    principal = MemoryPrincipal.model_validate(
        account_service.get_authenticated_principal()
    )
    project = create_project(
        name="Synthetic Watershed Continuity",
        description="Disposable Part 2C inference proof; contains no operator data.",
        status="active",
        state_summary="Field-monitoring plan is active.",
    )
    project_id = str(project["project_id"])
    update_project_metadata(
        project_id,
        current_state="The corrected monitoring cadence is authoritative.",
        latest_chunk="A synthetic baseline packet was prepared.",
        decisions=[
            {
                "label": "Use a 17-day observation cadence",
                "summary": "This supersedes the earlier 14-day draft.",
                "status": "decided",
            }
        ],
        next_actions=[
            {
                "label": "Calibrate the sensor array",
                "summary": "Use the amber reference marker during calibration.",
                "status": "planned",
            }
        ],
        unresolved_questions=["Whether the third station needs a duplicate sensor."],
        corrections=[
            {
                "label": "Cadence correction",
                "summary": "The 14-day draft is superseded by 17 days.",
                "status": "complete",
            }
        ],
    )
    conversation = ensure_conversation(
        title="Synthetic continuity proof",
        project_id=project_id,
        requested_mode="default",
    )
    conversation_id = conversation.conversation_id

    fabric.update_settings(principal, proof_settings)
    memory = fabric.create(
        principal,
        MemoryCreateRequest(
            title="Synthetic monitoring cadence",
            body="The old synthetic draft used a 14-day observation cadence.",
            why_stored="Disposable correction and supersession inference proof.",
            scope=MemoryScope.PROJECT,
            form=MemoryForm.SEMANTIC,
            project_id=project_id,
            conversation_id=conversation_id,
            importance=0.95,
            confidence=1.0,
            user_confirmed=True,
        ),
    )
    fabric.correct(
        principal,
        memory.memory_id,
        MemoryCorrectionRequest(
            body=(
                "The corrected synthetic observation cadence is 17 days; "
                "the prior 14-day draft is superseded."
            ),
            reason="Synthetic Part 2C correction proof.",
        ),
    )

    evidence = EvidenceRepository(paths=get_active_elysia_paths())
    evidence_id = evidence.record_evidence(
        owner_user_id=principal.user_id,
        packet={
            "source_url": "https://example.invalid/synthetic-calibration-record",
            "title": "Synthetic calibration record",
            "retrieved_at_utc": "2026-08-22T00:00:00Z",
            "snippet": "The approved calibration reference marker is amber.",
            "claim": "The sensor calibration uses an amber reference marker.",
            "retrieval_method": "synthetic_local_fixture",
            "source_type": "primary",
            "outward_boundary_state": "local_contract_only",
            "network_access_used": False,
            "private_context_sent": False,
        },
        request_id="req_p2c_seed_evidence",
        project_id=project_id,
        conversation_id=conversation_id,
        verification_status="verified",
        quarantine_state="verified_local_evidence",
    )

    first = asyncio.run(
        _send(
            {
                "request_id": "req_p2c_seed_inference",
                "message": (
                    "Using only the governed project context, acknowledge our decision, "
                    "correction, next action, and evidence marker. Keep future continuity "
                    "answers to four labeled clauses."
                ),
                "conversation_id": conversation_id,
                "project_id": project_id,
                "requested_mode": "default",
                "ui_surface": "conversations_room",
            }
        )
    )
    first_truth = _response_truth(first)
    if first_truth["response_source"] != "live_invoker":
        raise RuntimeError("Seed request did not use the live local invoker.")

    state = {
        "username": username,
        "owner_user_id": principal.user_id,
        "project_id": project_id,
        "conversation_id": conversation_id,
        "memory_id": memory.memory_id,
        "evidence_id": evidence_id,
    }
    path = _state_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return {"phase": "seed", "state": state, "inference": first_truth}


def recall() -> dict[str, Any]:
    from app.api import account_service
    from app.api.schemas.account import AccountLoginRequest
    from app.api.conversation_service import get_conversation_thread
    from app.cognition.evidence_repository import EvidenceRepository

    state = json.loads(_state_path().read_text(encoding="utf-8"))
    password = _password()

    # First prove that an unrelated account cannot restore the first account's
    # transcript/project/memory/evidence context into a real model request.
    account_service.logout()
    account_service.login(
        AccountLoginRequest(username="p2c-synthetic-control", password=password)
    )
    control = asyncio.run(
        _send(
            {
                "request_id": "req_p2c_control_inference",
                "message": (
                    "Without guessing, report the corrected cadence and calibration marker "
                    "from my authorized records. If none exist, say unavailable."
                ),
                "requested_mode": "default",
                "ui_surface": "conversations_room",
            }
        )
    )
    control_truth = _response_truth(control)
    control_text = str((control.get("data") or {}).get("response_text") or "").casefold()
    if control_truth["response_source"] != "live_invoker":
        raise RuntimeError("Isolation control did not use the live local invoker.")
    if "amber" in control_text or "17-day" in control_text or "17 day" in control_text:
        raise RuntimeError("Another account received synthetic owner context.")

    account_service.logout()
    account_service.login(
        AccountLoginRequest(username=state["username"], password=password)
    )
    thread_before = get_conversation_thread(state["conversation_id"])
    if len(thread_before.get("messages", [])) < 2:
        raise RuntimeError("The prior real-inference exchange did not survive restart.")

    recalled = asyncio.run(
        _send(
            {
                "request_id": "req_p2c_recall_inference",
                "message": (
                    "Continue where we left off. Follow the prior four-clause constraint and "
                    "state: (a) the corrected current cadence, (b) the superseded cadence, "
                    "(c) the next action, and (d) the evidence-backed reference marker."
                ),
                "conversation_id": state["conversation_id"],
                "project_id": state["project_id"],
                "requested_mode": "default",
                "ui_surface": "conversations_room",
            }
        )
    )
    recall_truth = _response_truth(recalled)
    recall_text = str((recalled.get("data") or {}).get("response_text") or "").casefold()
    required_markers = {
        "corrected_cadence": "17" in recall_text,
        "superseded_cadence": "14" in recall_text,
        "next_action": "calibrat" in recall_text and "sensor" in recall_text,
        "evidence_marker": "amber" in recall_text,
    }
    if recall_truth["response_source"] != "live_invoker":
        raise RuntimeError("Recall request did not use the live local invoker.")
    if not all(required_markers.values()):
        raise RuntimeError(f"Live recall missed synthetic grounded facts: {required_markers}")
    admitted = recall_truth["admitted_source_ids"]
    expected_prefixes = ("conversation:", "project:", "memory:", "evidence:")
    admitted_kinds = {
        prefix.rstrip(":"): any(item.startswith(prefix) for item in admitted)
        for prefix in expected_prefixes
    }
    if not all(admitted_kinds.values()):
        raise RuntimeError(f"The model receipt missed required cognition sources: {admitted_kinds}")
    durable_receipts = EvidenceRepository().list_context_receipts(
        state["owner_user_id"],
        conversation_id=state["conversation_id"],
        project_id=state["project_id"],
        limit=20,
    )
    if not any(item.get("request_id") == "req_p2c_recall_inference" for item in durable_receipts):
        raise RuntimeError("The recall context receipt was not durable.")
    thread_after = get_conversation_thread(state["conversation_id"])
    account_service.logout()
    return {
        "phase": "recall",
        "control_account": control_truth,
        "owner_recall": recall_truth,
        "grounded_markers": required_markers,
        "admitted_source_kinds": admitted_kinds,
        "conversation_messages_before": len(thread_before.get("messages", [])),
        "conversation_messages_after": len(thread_after.get("messages", [])),
        "durable_context_receipt_count": len(durable_receipts),
        "operator_data_used": False,
    }


def orchestrate() -> dict[str, Any]:
    """Run seed and recall as distinct processes with one in-memory secret."""
    root = Path(tempfile.mkdtemp(prefix="elysia-part2c-real-inference-"))
    runtime_dir = root / "runtime"
    runtime_dir.mkdir(mode=0o700)
    environment = dict(os.environ)
    environment.update(
        {
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "ELYSIA_QA_RUN_ID": f"pass10d-i-{root.name}",
            "ELYSIA_PART2C_PROOF_STATE": str(root / "proof-state.json"),
            "ELYSIA_PART2C_SYNTHETIC_PASSWORD": secrets.token_urlsafe(32),
        }
    )
    results: dict[str, Any] = {}
    try:
        for phase in ("seed", "recall"):
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), phase],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                text=True,
                capture_output=True,
                timeout=900,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Part 2C {phase} subprocess failed without exposing its synthetic secret: "
                    f"{completed.stderr[-3000:]}"
                )
            results[phase] = json.loads(completed.stdout)
    finally:
        shutil.rmtree(root)
    return {
        "disposable_xdg_destroyed": not root.exists(),
        "disposable_qa_run_id": environment["ELYSIA_QA_RUN_ID"],
        "process_restart_boundary": True,
        "synthetic_secret_persisted": False,
        "operator_profile_used": False,
        "phases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("seed", "recall", "orchestrate"))
    args = parser.parse_args()
    result = (
        seed()
        if args.phase == "seed"
        else recall()
        if args.phase == "recall"
        else orchestrate()
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
