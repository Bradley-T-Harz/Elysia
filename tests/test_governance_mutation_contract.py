from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
import httpx
import yaml

from app.api import governance_mutation_service as mutation_service
from app.api.capability_service import get_capabilities_status
from app.api.governance_service import get_governance_state
from app.api.main import create_app
import app.api.routes.governance as governance_route
from app.api.schemas.governance_mutation import (
    GovernanceChangeApplyRequest,
    GovernanceChangePlanRequest,
)
from app.governance.governance_control_registry import (
    GovernanceControlRegistry,
    GovernanceControlRule,
    GovernanceMutationClassification,
    GovernanceMutationRisk,
    governance_config_hash,
    load_governance_control_registry,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _receipt(payload: dict) -> dict:
    data = payload["data"]
    for key in ("plan", "apply_result", "restore_result"):
        if key in data:
            return data[key]["receipt"]
    raise AssertionError("No governance receipt found.")


def test_production_registry_classifies_every_surface_and_grants_no_write_target():
    registry = load_governance_control_registry()
    state = get_governance_state()["data"]
    controls = state["control_states"]

    assert controls
    assert len(state["governance_config_hash"]) == 64
    assert state["mutation_contract_version"] == registry.contract_version
    assert state["mutation_summary"].get("safe-live-editable-now", 0) == 0

    for control in controls:
        rule = registry.rule_for(control["control_id"])
        assert control["mutation_classification"] == rule.classification.value
        assert control["mutation_risk"] == rule.risk.value
        assert control["mutation_allowed"] is False
        assert control["approval_required"] is False
        assert control["mutation_reason"]
        assert rule.mutation_allowed is False


def test_capability_truth_reports_live_contract_without_claiming_live_controls():
    payload = get_capabilities_status()
    capabilities = {
        item["capability_key"]: item for item in payload["data"]["capabilities"]
    }

    mutation = capabilities["governance_mutation_contract"]
    approval = capabilities["approval_resolve"]
    assert mutation["state"] == "live"
    assert mutation["read_only"] is True
    assert mutation["approval_state"] == "needed"
    assert "no production control" in mutation["summary"]
    assert approval["state"] == "live"
    assert approval["approval_state"] == "needed"


def test_mutation_schema_rejects_extra_fields_and_non_scalar_values():
    with pytest.raises(ValidationError):
        GovernanceChangePlanRequest(
            control_id="routing_mode",
            proposed_value={"unsafe": True},
            expected_config_hash="0" * 64,
        )

    with pytest.raises(ValidationError):
        GovernanceChangeApplyRequest(
            plan_id="govplan_1",
            plan_hash="1" * 64,
            expected_config_hash="2" * 64,
            confirmed=True,
            frontend_authority=True,
        )

    with pytest.raises(ValidationError):
        GovernanceChangePlanRequest(
            control_id="routing_mode",
            proposed_value="local_only",
            expected_config_hash="not-a-sha256-value".ljust(64, "x"),
        )

    with pytest.raises(ValidationError):
        GovernanceChangePlanRequest(
            control_id="routing_mode",
            proposed_value="x" * 241,
            expected_config_hash="0" * 64,
        )


def test_governance_public_contract_docs_parse_and_match_live_routes():
    mutation_doc = yaml.safe_load(
        (REPO_ROOT / "docs" / "api" / "governance_mutation_schema.yaml").read_text(
            encoding="utf-8"
        )
    )["governance_mutation_schema"]
    approval_doc = yaml.safe_load(
        (REPO_ROOT / "docs" / "api" / "approval_resolve_schema.yaml").read_text(
            encoding="utf-8"
        )
    )["approval_resolve_schema"]
    state_doc_text = (
        REPO_ROOT / "docs" / "api" / "governance_state_schema.yaml"
    ).read_text(encoding="utf-8")

    assert mutation_doc["routes"] == {
        "plan": "POST /governance/changes/plan",
        "apply": "POST /governance/changes/apply",
        "restore": "POST /governance/changes/restore",
        "approve": "POST /approval/resolve",
    }
    assert approval_doc["current_scope"]["live"]
    assert "the operator" not in state_doc_text
    assert "the operator" not in json.dumps(approval_doc)


def test_hard_prohibited_and_read_only_controls_return_sanitized_blocked_receipts():
    mutation_service.clear_governance_mutation_state_for_tests()
    state = get_governance_state()["data"]
    config_hash = state["governance_config_hash"]

    hard = mutation_service.plan_governance_change(
        {
            "control_id": "routing_silent_cloud_fallback",
            "proposed_value": True,
            "expected_config_hash": config_hash,
            "reason": "/private/path token=should-never-enter-receipt",
        }
    )
    constitutional = mutation_service.plan_governance_change(
        {
            "control_id": "approval_destructive_actions",
            "proposed_value": False,
            "expected_config_hash": config_hash,
        }
    )

    assert hard["status"] == "blocked"
    assert hard["data"]["plan"]["classification"] == "hard-prohibited-by-default"
    assert constitutional["status"] == "blocked"
    assert constitutional["data"]["plan"]["classification"] == "read-only-constitutional"
    for payload in (hard, constitutional):
        receipt = _receipt(payload)
        serialized = json.dumps(receipt).lower()
        assert receipt["sanitized"] is True
        assert receipt["raw_values_logged"] is False
        assert receipt["raw_paths_logged"] is False
        assert "/private/path" not in serialized
        assert "token=" not in serialized


def test_unknown_control_and_stale_hash_fail_closed():
    state = get_governance_state()["data"]
    current_hash = state["governance_config_hash"]

    unknown = mutation_service.plan_governance_change(
        {
            "control_id": "not_a_governance_control",
            "proposed_value": True,
            "expected_config_hash": current_hash,
        }
    )
    stale = mutation_service.plan_governance_change(
        {
            "control_id": "routing_mode",
            "proposed_value": "other",
            "expected_config_hash": "f" * 64,
        }
    )

    assert _receipt(unknown)["reason_code"] == "unknown_control_id"
    assert _receipt(stale)["reason_code"] == "stale_config_hash"
    assert _receipt(stale)["outcome"] == "stale"


@pytest.fixture
def safe_test_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mutation_service.clear_governance_mutation_state_for_tests()
    config_root = tmp_path / "config"
    backup_root = tmp_path / "state" / "backups"
    target = config_root / "test" / "governance.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("governance:\n  safe_flag: false\n", encoding="utf-8")

    default_rule = GovernanceControlRule(
        rule_id="default",
        classification=GovernanceMutationClassification.READ_ONLY_CONSTITUTIONAL,
        risk=GovernanceMutationRisk.CRITICAL,
        reason="Fail closed.",
    )
    safe_rule = GovernanceControlRule(
        rule_id="test_safe_flag",
        classification=GovernanceMutationClassification.SAFE_LIVE_EDITABLE_NOW,
        risk=GovernanceMutationRisk.LOW,
        reason="Test-only low-risk mutation adapter.",
        exact=("test_safe_flag",),
        allowed_values=(False, True),
        target_relative_path="test/governance.yaml",
        yaml_key_path=("governance", "safe_flag"),
    )
    registry = GovernanceControlRegistry(
        contract_version="governance-mutation-test-1.0",
        default_rule=default_rule,
        rules=(safe_rule,),
    )

    def read_state() -> tuple[dict, str]:
        value = yaml.safe_load(target.read_text(encoding="utf-8"))["governance"]["safe_flag"]
        controls = [{"control_id": "test_safe_flag", "value": value}]
        return {"control_states": controls}, governance_config_hash(
            controls,
            registry=registry,
        )

    monkeypatch.setattr(mutation_service, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(mutation_service, "BACKUP_ROOT", backup_root)
    monkeypatch.setattr(mutation_service, "_registry", lambda: registry)
    monkeypatch.setattr(mutation_service, "_read_authoritative_state", read_state)

    def create_plan() -> dict:
        _, config_hash = read_state()
        return mutation_service.plan_governance_change(
            {
                "control_id": "test_safe_flag",
                "proposed_value": True,
                "expected_config_hash": config_hash,
            }
        )

    yield SimpleNamespace(
        target=target,
        backup_root=backup_root,
        read_state=read_state,
        create_plan=create_plan,
    )
    mutation_service.clear_governance_mutation_state_for_tests()


def _approve(plan: dict) -> tuple[str, str]:
    approval_request_id = plan["data"]["plan"]["approval_request_id"]
    resolution = mutation_service.resolve_governance_approval(
        {
            "request_id": approval_request_id,
            "decision": "approved",
            "resolver_identity": "local_user",
            "reason": "exact test approval",
        }
    )
    data = resolution["data"]["approval_resolution"]
    assert data["can_proceed"] is True
    return data["approval_id"], data["approval_token"]


def _apply_request(plan: dict, approval_id: str | None = None, approval_token: str | None = None) -> dict:
    data = plan["data"]["plan"]
    return {
        "plan_id": data["plan_id"],
        "plan_hash": data["plan_hash"],
        "expected_config_hash": data["config_hash"],
        "approval_id": approval_id,
        "approval_token": approval_token,
        "confirmed": True,
    }


def test_safe_framework_refuses_missing_expired_tampered_and_reused_approval(
    safe_test_contract,
):
    plan = safe_test_contract.create_plan()
    assert plan["status"] == "ok"
    assert plan["data"]["plan"]["mutation_allowed"] is True

    missing = mutation_service.apply_governance_change(_apply_request(plan))
    assert _receipt(missing)["reason_code"] == "approval_missing"

    approval_id, approval_token = _approve(plan)
    tampered_request = _apply_request(plan, approval_id, approval_token)
    tampered_request["plan_hash"] = "a" * 64
    tampered = mutation_service.apply_governance_change(tampered_request)
    assert _receipt(tampered)["outcome"] == "tampered"
    assert _receipt(tampered)["reason_code"] == "plan_hash_mismatch"

    approval_request_id = plan["data"]["plan"]["approval_request_id"]
    mutation_service._APPROVAL_REQUESTS[approval_request_id].expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    expired = mutation_service.apply_governance_change(
        _apply_request(plan, approval_id, approval_token)
    )
    assert _receipt(expired)["reason_code"] == "approval_expired"

    fresh_plan = safe_test_contract.create_plan()
    fresh_approval_id, fresh_approval_token = _approve(fresh_plan)
    request = _apply_request(fresh_plan, fresh_approval_id, fresh_approval_token)
    applied = mutation_service.apply_governance_change(request)
    reused = mutation_service.apply_governance_change(request)

    assert applied["status"] == "ok"
    assert _receipt(applied)["outcome"] == "applied"
    assert _receipt(reused)["reason_code"] == "approval_already_used"


def test_atomic_apply_concurrency_backup_and_approved_restore(safe_test_contract):
    plan = safe_test_contract.create_plan()
    approval_id, approval_token = _approve(plan)
    request = _apply_request(plan, approval_id, approval_token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: mutation_service.apply_governance_change(request), range(2)))

    assert sorted(payload["status"] for payload in results) == ["blocked", "ok"]
    applied = next(payload for payload in results if payload["status"] == "ok")
    blocked = next(payload for payload in results if payload["status"] == "blocked")
    assert _receipt(blocked)["reason_code"] == "approval_already_used"
    assert yaml.safe_load(safe_test_contract.target.read_text(encoding="utf-8"))["governance"]["safe_flag"] is True

    backup_files = list(safe_test_contract.backup_root.glob("backup_*.yaml"))
    assert len(backup_files) == 1
    assert backup_files[0].stat().st_mode & 0o777 == 0o600
    assert safe_test_contract.backup_root.stat().st_mode & 0o777 == 0o700

    apply_result = applied["data"]["apply_result"]
    restore_resolution = mutation_service.resolve_governance_approval(
        {
            "request_id": apply_result["restore_approval_request_id"],
            "decision": "approved",
        }
    )["data"]["approval_resolution"]
    restored = mutation_service.restore_governance_change(
        {
            "restore_id": apply_result["restore_id"],
            "restore_plan_hash": apply_result["restore_plan_hash"],
            "expected_config_hash": apply_result["config_hash_after"],
            "approval_id": restore_resolution["approval_id"],
            "approval_token": restore_resolution["approval_token"],
            "confirmed": True,
        }
    )

    assert restored["status"] == "ok"
    assert _receipt(restored)["outcome"] == "restored"
    assert yaml.safe_load(safe_test_contract.target.read_text(encoding="utf-8"))["governance"]["safe_flag"] is False
    assert list(safe_test_contract.backup_root.glob("pre_restore_*.yaml"))


def test_governance_routes_delegate_typed_change_payloads(monkeypatch: pytest.MonkeyPatch):
    expected = {"status": "blocked", "data": {"contract": "tested"}}
    calls: list[tuple[str, object]] = []
    service = SimpleNamespace(
        plan_governance_change=lambda payload: calls.append(("plan", payload)) or expected,
        apply_governance_change=lambda payload: calls.append(("apply", payload)) or expected,
        restore_governance_change=lambda payload: calls.append(("restore", payload)) or expected,
    )
    monkeypatch.setattr(governance_route, "_load_governance_service", lambda: service)

    asyncio.run(
        governance_route.post_governance_change_plan(
            mutation_service.GovernanceChangePlanRequest(
                control_id="routing_mode",
                proposed_value="local_only",
                expected_config_hash="0" * 64,
            )
        )
    )
    asyncio.run(
        governance_route.post_governance_change_apply(
            mutation_service.GovernanceChangeApplyRequest(
                plan_id="plan_1",
                plan_hash="1" * 64,
                expected_config_hash="2" * 64,
                confirmed=False,
            )
        )
    )
    asyncio.run(
        governance_route.post_governance_change_restore(
            mutation_service.GovernanceRestoreRequest(
                restore_id="restore_1",
                restore_plan_hash="3" * 64,
                expected_config_hash="4" * 64,
                confirmed=False,
            )
        )
    )

    assert [name for name, _ in calls] == ["plan", "apply", "restore"]


def test_governance_routes_are_mounted_and_fail_closed_over_asgi():
    async def exercise_routes() -> None:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as client:
            state_response = await client.get("/governance/state")
            assert state_response.status_code == 200
            state = state_response.json()["data"]

            plan_response = await client.post(
                "/governance/changes/plan",
                json={
                    "control_id": "routing_silent_cloud_fallback",
                    "proposed_value": True,
                    "expected_config_hash": state["governance_config_hash"],
                },
            )
            assert plan_response.status_code == 200
            assert plan_response.json()["status"] == "blocked"

            approval_response = await client.post(
                "/approval/resolve",
                json={"request_id": "unknown_request", "decision": "approved"},
            )
            assert approval_response.status_code == 200
            assert approval_response.json()["status"] == "blocked"

            invalid_approval = await client.post(
                "/approval/resolve",
                json={
                    "request_id": "unknown_request",
                    "decision": "approved",
                    "frontend_authority": True,
                },
            )
            assert invalid_approval.status_code == 400
            assert invalid_approval.json()["status"] == "error"

    asyncio.run(exercise_routes())
