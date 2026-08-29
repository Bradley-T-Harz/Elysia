#!/usr/bin/env python3
"""Disposable Internet OFF/ON and durable research proof for Part 2C."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Any
from unittest.mock import patch
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _password() -> str:
    value = os.environ.get("ELYSIA_PART2C_SYNTHETIC_PASSWORD", "")
    if len(value) < 16:
        raise RuntimeError("A synthetic password of at least 16 characters is required.")
    return value


def _state_path() -> Path:
    value = os.environ.get("ELYSIA_PART2C_RESEARCH_STATE", "").strip()
    if not value:
        raise RuntimeError("ELYSIA_PART2C_RESEARCH_STATE is required.")
    return Path(value)


def live() -> dict[str, Any]:
    from app.api import account_service
    from app.api.research_service import (
        WebResearchPort,
        run_bounded_public_fetch,
        run_bounded_public_research,
    )
    from app.api.schemas.account import AccountCreateRequest
    from app.api.account_service import get_active_elysia_paths
    from app.cognition.evidence_repository import EvidenceRepository
    from app.memory.canonical_models import MemoryPrincipal, MemorySettings
    from app.memory.canonical_repository import MemoryRepository
    from app.memory.fabric_service import MemoryFabricService
    import sandbox.searxng_worker.config as searx_config

    username = "p2c-synthetic-research"
    account_service.create_account(
        AccountCreateRequest(username=username, password=_password())
    )
    principal = MemoryPrincipal.model_validate(account_service.get_authenticated_principal())
    fabric = MemoryFabricService(
        repository=MemoryRepository(paths=get_active_elysia_paths())
    )

    # Real egress trap: with Internet OFF, the governed services must return
    # before DNS, a worker, or a non-loopback socket can be reached.
    attempted_nonlocal: list[str] = []
    original_create_connection = socket.create_connection

    def trap(address, *args, **kwargs):
        host = str(address[0] if isinstance(address, tuple) else address).casefold()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            attempted_nonlocal.append(host)
            raise AssertionError(f"non-local egress while Internet OFF: {host}")
        return original_create_connection(address, *args, **kwargs)

    with patch("socket.create_connection", trap):
        off_search = run_bounded_public_research(
            {
                "request_id": "req_p2c_live_off_search",
                "question": "Synthetic public guidance question",
                "queries": ["synthetic public wetland guidance"],
            }
        )
        off_fetch = run_bounded_public_fetch(
            {
                "request_id": "req_p2c_live_off_fetch",
                "question": "Synthetic public guidance source",
                "url": "https://example.com/",
            }
        )
    if attempted_nonlocal:
        raise RuntimeError("Internet OFF attempted non-local egress.")
    if off_search.get("status") != "blocked" or off_fetch.get("status") != "blocked":
        raise RuntimeError("Internet OFF did not fail closed.")

    fabric.update_settings(
        principal,
        MemorySettings(
            internet_master_enabled=True,
            retrieval_breadth="broad",
            research_initiative="proactive",
            safe_search_level="strict",
        ),
    )
    operator_override = Path.home() / ".config" / "elysia" / "workers" / "searxng.yaml"
    if not operator_override.is_file():
        raise RuntimeError("The sealed baseline SearXNG enablement override is unavailable.")
    searx_config.DEFAULT_LOCAL_OVERRIDE_PATH = operator_override

    question = (
        "Research online and compare official public wetland restoration monitoring "
        "guidance with peer-reviewed ecological indicators. My name is Synthetic Person, "
        "my email is synthetic.private@example.invalid, and use "
        "/" + "home/synthetic/private-notes.txt only as local context."
    )
    result = WebResearchPort().investigate(
        question=question,
        request_id="req_p2c_live_research",
        conversation_id=None,
        project_id=None,
        reasoning_gear="research_engineering",
        autonomy_level=3,
    )
    if result.get("state") != "completed":
        raise RuntimeError(f"Live governed research did not complete: {result.get('errors')}")
    if not result.get("network_access_used") or result.get("private_context_sent"):
        raise RuntimeError("Live research boundary truth is incorrect.")
    query_privacy = dict(result.get("query_privacy") or {})
    removed = set(query_privacy.get("removed_categories") or [])
    if not {"email_address", "local_path", "declared_name"} <= removed:
        raise RuntimeError(f"Minimum-necessary query scrubber missed categories: {removed}")
    if int(result.get("query_count") or 0) < 2:
        raise RuntimeError("The major public investigation did not iterate queries.")
    if int(result.get("domain_count") or 0) < 2:
        raise RuntimeError("The major public investigation did not compare domains.")
    evidence_ids = [str(value) for value in result.get("evidence_ids", []) if str(value)]
    if not evidence_ids or not result.get("session_id"):
        raise RuntimeError("Live research did not retain durable evidence/session IDs.")
    repository = EvidenceRepository(paths=get_active_elysia_paths())
    evidence = repository.list_evidence(principal.user_id, limit=200)
    domains = sorted(
        {
            str(urlparse(str(item.get("source_url") or "")).hostname or "")
            for item in evidence
            if item.get("source_url")
        }
        - {""}
    )
    if len(domains) < 2:
        raise RuntimeError("Durable evidence lacks source-domain diversity.")
    state = {
        "username": username,
        "owner_user_id": principal.user_id,
        "session_id": result["session_id"],
        "evidence_ids": evidence_ids,
    }
    path = _state_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    account_service.logout()
    return {
        "phase": "live",
        "internet_off": {
            "search_status": off_search.get("status"),
            "fetch_status": off_fetch.get("status"),
            "attempted_nonlocal_sockets": 0,
        },
        "internet_on": {
            "state": result.get("state"),
            "query_count": result.get("query_count"),
            "fetch_count": result.get("fetch_count"),
            "domain_count": result.get("domain_count"),
            "authority_class_count": result.get("authority_class_count"),
            "bytes_read": result.get("bytes_read"),
            "network_access_used": result.get("network_access_used"),
            "private_context_sent": result.get("private_context_sent"),
            "untrusted_content_quarantined": result.get("untrusted_content_quarantined"),
            "query_privacy": query_privacy,
            "evidence_count": len(evidence_ids),
            "source_domains": domains,
            "errors": result.get("errors"),
        },
        "state": state,
    }


def reopen() -> dict[str, Any]:
    from app.api import account_service
    from app.api.schemas.account import AccountLoginRequest
    from app.api.account_service import get_active_elysia_paths
    from app.cognition.evidence_repository import EvidenceRepository

    state = json.loads(_state_path().read_text(encoding="utf-8"))
    account_service.login(
        AccountLoginRequest(username=state["username"], password=_password())
    )
    repository = EvidenceRepository(paths=get_active_elysia_paths())
    session = repository.get_session(state["owner_user_id"], state["session_id"])
    evidence = repository.list_evidence(state["owner_user_id"], limit=500)
    actual_ids = {str(item.get("evidence_id")) for item in evidence}
    missing = sorted(set(state["evidence_ids"]) - actual_ids)
    if missing:
        raise RuntimeError("Durable evidence IDs were missing after process restart.")
    if session.get("status") != "completed":
        raise RuntimeError("Durable research session was not completed after restart.")
    account_service.logout()
    return {
        "phase": "reopen",
        "session_status": session.get("status"),
        "durable_evidence_count": len(evidence),
        "expected_evidence_count": len(state["evidence_ids"]),
        "missing_evidence_ids": [],
        "operator_profile_used": False,
    }


def orchestrate() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="elysia-part2c-live-research-"))
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    environment = dict(os.environ)
    environment.update(
        {
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "XDG_RUNTIME_DIR": str(runtime),
            "ELYSIA_QA_RUN_ID": f"pass10d-i-{root.name}",
            "ELYSIA_PART2C_RESEARCH_STATE": str(root / "research-state.json"),
            "ELYSIA_PART2C_SYNTHETIC_PASSWORD": secrets.token_urlsafe(32),
        }
    )
    phases: dict[str, Any] = {}
    try:
        for phase in ("live", "reopen"):
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), phase],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=900,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Part 2C research {phase} failed without exposing its synthetic secret: "
                    f"{completed.stderr[-3000:]}"
                )
            phases[phase] = json.loads(completed.stdout)
    finally:
        shutil.rmtree(root)
    return {
        "disposable_xdg_destroyed": not root.exists(),
        "disposable_qa_run_id": environment["ELYSIA_QA_RUN_ID"],
        "process_restart_boundary": True,
        "synthetic_secret_persisted": False,
        "operator_profile_used": False,
        "phases": phases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("live", "reopen", "orchestrate"))
    phase = parser.parse_args().phase
    result = live() if phase == "live" else reopen() if phase == "reopen" else orchestrate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
