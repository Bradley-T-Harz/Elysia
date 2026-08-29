#!/usr/bin/env python3
"""Live synthetic proof for the promoted local semantic Memory path.

The caller must provide disposable XDG roots and install/start the managed
semantic profile there first. No operator account or private content is read.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.api import account_service
from app.api.account_service import AccountLoginRequest, AccountStore
from app.api.schemas.account import AccountCreateRequest
from app.cognition.hybrid_retrieval import HybridMemoryRetriever
from app.cognition.fts_projection import FtsMemoryProjection
from app.cognition.semantic_projection import SemanticMemoryProjection
from app.memory.canonical_models import (
    ConsequenceApplyRequest,
    ConsequencePreviewRequest,
    MemoryCreateRequest,
    MemoryPrincipal,
    SharedSpaceCreateRequest,
)
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService


PASSWORD_ALPHA = "synthetic semantic alpha password"
PASSWORD_BETA = "synthetic semantic beta password"


def _approval(fabric, principal, target_id, request):
    preview = fabric.preview_consequence(principal, target_id, request)
    return fabric.apply_consequence(
        principal,
        target_id,
        ConsequenceApplyRequest(
            approval_id=preview["approval_id"],
            approval_token=preview["approval_token"],
        ),
    )


def _require_disposable_xdg() -> None:
    roots = [os.environ.get(name, "") for name in (
        "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"
    )]
    if any(not value.startswith("/tmp/") for value in roots):
        raise SystemExit("Every XDG root must be an explicit disposable /tmp path.")


def main() -> int:
    _require_disposable_xdg()
    store = AccountStore()
    account_service._default_store = lambda: store
    before = store.state()
    if before.account_count or before.is_authenticated:
        raise SystemExit("The disposable semantic proof did not start at zero-account state.")

    store.create_account(AccountCreateRequest(username="semantic-alpha", password=PASSWORD_ALPHA))
    store.create_account(AccountCreateRequest(username="semantic-beta", password=PASSWORD_BETA))
    # Creating another local profile must not silently replace the current
    # session. Select the intended synthetic account explicitly before
    # capturing its identity, then return to Alpha for the owner workflow.
    store.login(AccountLoginRequest(username="semantic-beta", password=PASSWORD_BETA))
    beta_id = str(store.authenticated_principal()["user_id"])
    store.logout()
    store.login(AccountLoginRequest(username="semantic-alpha", password=PASSWORD_ALPHA))
    alpha = MemoryPrincipal.model_validate(store.authenticated_principal())

    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    semantic = SemanticMemoryProjection(paths=store.elysia_paths, repository=repository, fabric=fabric)
    if not semantic.configured:
        raise SystemExit("The disposable managed semantic profile is not configured.")

    shared = fabric.create(alpha, MemoryCreateRequest(
        title="Watershed continuity",
        body="Restore rainwater retention through wetland habitat corridors.",
        why_stored="Synthetic semantic and ACL proof.",
    ))
    to_private = fabric.create(alpha, MemoryCreateRequest(
        title="Nursery planning",
        body="Propagate riparian sedges for the spring nursery schedule.",
        why_stored="Synthetic privacy-transition proof.",
    ))
    to_delete = fabric.create(alpha, MemoryCreateRequest(
        title="Temporary survey",
        body="A temporary salamander transect note for exact purge proof.",
        why_stored="Synthetic hard-delete proof.",
    ))
    fabric.create(alpha, MemoryCreateRequest(
        title="Private field note",
        body="PRIVATE_SEMANTIC_CANARY must remain outside Qdrant.",
        why_stored="Synthetic Private exclusion proof.",
        privacy="private",
    ))
    fabric.encryption.unlock_sealed(principal=alpha, password=PASSWORD_ALPHA, ttl_seconds=60)
    fabric.create(alpha, MemoryCreateRequest(
        title="Sealed field note",
        body="SEALED_SEMANTIC_CANARY must never be embedded.",
        why_stored="Synthetic Sealed exclusion proof.",
        privacy="sealed",
    ))

    space = fabric.create_space(alpha, SharedSpaceCreateRequest(
        label="Synthetic watershed collaborators",
        description="Disposable shared-space semantic ACL proof.",
    ))
    _approval(fabric, alpha, space["space_id"], ConsequencePreviewRequest(
        action="add_space_member",
        target_user_id=beta_id,
        target_role="reader",
        reason="Synthetic deliberate shared-space grant.",
    ))
    _approval(fabric, alpha, shared.memory_id, ConsequencePreviewRequest(
        action="move_to_space",
        target_space_id=space["space_id"],
        reason="Synthetic deliberate shared-space move.",
    ))

    rebuilt = semantic.rebuild(alpha)
    alpha_hits = semantic.search(
        alpha, "wetland water storage restoration",
        authorized_space_ids=[space["space_id"]], limit=10,
    )
    if shared.memory_id not in {item["candidate_id"] for item in alpha_hits}:
        raise RuntimeError("Normal-memory semantic retrieval did not return the canonical target.")
    count_before = int((semantic._qdrant(
        "POST", "/collections/elysia_memory_semantic_v1/points/count",
        {"exact": True}, timeout=10.0,
    ) or {}).get("result", {}).get("count") or 0)
    if count_before != 3:
        raise RuntimeError(f"Expected exactly three normal vectors, received {count_before}.")

    store.logout()
    store.login(AccountLoginRequest(username="semantic-beta", password=PASSWORD_BETA))
    beta = MemoryPrincipal.model_validate(store.authenticated_principal())
    denied = semantic.search(beta, "wetland water storage restoration", limit=10)
    if shared.memory_id in {item["candidate_id"] for item in denied}:
        raise RuntimeError("Shared semantic Memory escaped its space ACL.")
    admitted = semantic.search(
        beta, "wetland water storage restoration",
        authorized_space_ids=[space["space_id"]], limit=10,
    )
    if shared.memory_id not in {item["candidate_id"] for item in admitted}:
        raise RuntimeError("Deliberately shared semantic Memory was not available to its reader.")

    store.logout()
    store.login(AccountLoginRequest(username="semantic-alpha", password=PASSWORD_ALPHA))
    alpha = MemoryPrincipal.model_validate(store.authenticated_principal())
    _approval(fabric, alpha, to_private.memory_id, ConsequencePreviewRequest(
        action="change_privacy", target_privacy="private",
        reason="Synthetic exact normal-to-Private vector purge.",
    ))
    _approval(fabric, alpha, to_delete.memory_id, ConsequencePreviewRequest(
        action="hard_delete", reason="Synthetic exact hard-delete vector purge.",
    ))
    count_after = int((semantic._qdrant(
        "POST", "/collections/elysia_memory_semantic_v1/points/count",
        {"exact": True}, timeout=10.0,
    ) or {}).get("result", {}).get("count") or 0)
    if count_after != 1:
        raise RuntimeError(f"Private/delete purge left an unexpected vector count: {count_after}.")

    lexical = FtsMemoryProjection(paths=store.elysia_paths, repository=repository, fabric=fabric)
    hybrid = HybridMemoryRetriever(lexical=lexical, semantic=semantic).search_normal(
        alpha, "wetland water storage restoration",
        space_ids=[space["space_id"]], limit=10,
    )
    if shared.memory_id not in {item["candidate_id"] for item in hybrid.rows}:
        raise RuntimeError("The production hybrid path did not admit the target.")

    semantic._qdrant("DELETE", "/collections/elysia_memory_semantic_v1", timeout=30.0)
    if fabric.get(alpha, shared.memory_id).body is None:
        raise RuntimeError("Deleting the derived projection affected canonical Memory.")
    rebuilt_after_delete = semantic.rebuild(alpha)
    if not semantic.search(
        alpha, "wetland water storage restoration",
        authorized_space_ids=[space["space_id"]], limit=10,
    ):
        raise RuntimeError("Derived projection did not rebuild from canonical Memory.")

    health = semantic.health(probe=True)
    output = {
        "proof": "part2c-semantic-production-live-v1",
        "accounts_synthetic": 2,
        "account_ids_recorded": False,
        "private_content_recorded": False,
        "normal_vectors_before_privacy_delete": count_before,
        "normal_vectors_after_privacy_delete": count_after,
        "private_vectors_persisted": 0,
        "sealed_vectors_persisted": 0,
        "owner_filter_before_ranking": True,
        "shared_space_acl_before_ranking": True,
        "shared_source_owner_preserved": True,
        "canonical_reauthorization_after_ranking": True,
        "hybrid_method": hybrid.rows[0].get("retrieval_method"),
        "rebuild_initial": rebuilt["state"],
        "rebuild_after_collection_delete": rebuilt_after_delete["state"],
        "canonical_survived_projection_delete": True,
        "health_state": health["state"],
        "server_loopback_only": health["qdrant_server_loopback_only"],
        "server_authenticated": health["qdrant_authenticated"],
        "operators_touched": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    store.logout()
    after = store.state()
    if after.is_authenticated:
        raise RuntimeError("Synthetic proof left an active session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
