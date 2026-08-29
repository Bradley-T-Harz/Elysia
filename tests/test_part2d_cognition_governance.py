from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
import yaml

from app.api.account_service import AccountPaths, AccountStore
from app.api.admin_service import AdminService
from app.api.schemas.account import AccountCreateRequest, AccountLoginRequest, LocalAccountRole
from app.api.schemas.admin import (
    AdminChangeApplyRequest,
    AdminChangeKind,
    AdminChangePreviewRequest,
    ManagedProfilePolicy,
)
from app.cognition.compute_governor import (
    ComputeLedger,
    WorkloadDescriptor,
    decide_compute,
    resource_snapshot,
)
from app.cognition import emergency_control
from app.cognition.governor import (
    GEARS,
    GovernorInput,
    decide_cognition,
    effective_autonomy,
    escalate_decision,
    resolve_autonomy_policy,
)
from app.cognition.model_registry import ModelRegistry, model_resource_estimate
from app.cognition.uncertainty import extend_uncertainty, operational_self_model
from app.install.paths import resolve_elysia_paths
from app.api.user_control_service import current_user_controls, managed_capability_allowed
from app.api.main import _managed_policy_requirements
from app.api.main import create_app
from core.runtime import SessionState
from tests.asgi_test_client import ASGITestClient


def make_store(tmp_path: Path, monkeypatch) -> AccountStore:
    for key, leaf in (
        ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        target = tmp_path / leaf
        target.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(key, str(target))
    paths = resolve_elysia_paths()
    identity = paths.identity_dir
    return AccountStore(AccountPaths(
        identity_root=identity,
        database_path=identity / "elysia_identity.sqlite",
        profile_photo_dir=identity / "profile_photos",
        current_session_path=identity / "current_session.json",
        elysia_paths=paths,
    ))


def test_six_gears_are_deterministic_and_effort_never_increases_authority():
    fixtures = {
        "reflex": "hello",
        "quick": "Can you name the four seasons?",
        "standard": "Explain how a wetland carbon budget works with assumptions and a concise example for a restoration team.",
        "deep": "Analyze and plan the tradeoffs in a multi-stage watershed restoration measurement program with uncertainty.",
        "deliberative": "Audit the privacy and governance threat model and independently verify its security tradeoffs.",
        "research_engineering": "Research and benchmark a CUDA database migration architecture with sources.",
    }
    assert tuple(fixtures) == GEARS
    for expected, message in fixtures.items():
        value = GovernorInput(
            request_id=f"request-{expected}", message=message, mode="default",
            intent={"primary": "ordinary"}, autonomy_level=3,
            requested_gear=expected,
        )
        first = decide_cognition(value)
        second = decide_cognition(value)
        assert first == second
        assert first.selected_gear == expected
        assert first.authority_increased is False
        assert first.content_free is True


def test_governor_operationally_consumes_context_time_queue_privacy_and_thermal_state():
    decision = decide_cognition(GovernorInput(
        request_id="request-resource-inputs",
        message="Analyze this bounded but novel dataset carefully.",
        mode="generalist",
        intent={"primary": "analysis"},
        autonomy_level=3,
        privacy_state="private",
        context_window=4096,
        context_size=3500,
        novelty_score=0.9,
        expected_data_size=120_000,
        time_budget_ms=2400,
        queue_depth=2,
        resource_state={
            "gpu": {
                "available": True,
                "devices": [{"temperature_c": 91, "memory_free_mb": 8000}],
            }
        },
        power_thermal_state={"gpu": [{"temperature_c": 91}]},
    ))
    assert decision.selected_gear == "deep"
    assert decision.context_token_budget == 596
    assert decision.output_token_budget == 300
    assert decision.device_preference == "cpu"
    assert "respect_existing_compute_queue_and_leases" in decision.model_constraints
    assert "private_content_local_only" in decision.model_constraints
    assert "gpu_thermal_ceiling_requires_cpu_fallback" in decision.reasons
    assert decision.authority_increased is False


def test_first_class_uncertainty_signals_escalate_without_increasing_authority():
    base = decide_cognition(GovernorInput(
        request_id="request-monitor", message="Please assess this.",
        mode="default", intent={"primary": "conversation"}, autonomy_level=2,
        requested_gear="quick",
    ))
    assessment = extend_uncertainty(
        {"score": 0.1, "band": "low", "reasons": []},
        model_disagreement=True,
        tool_mismatch=True,
        low_evidence_quality=True,
        ambiguity_score=0.8,
        verifier_failure=True,
    )
    escalated = escalate_decision(
        base,
        uncertainty_score=assessment.score,
        model_disagreement=assessment.model_disagreement,
        tool_mismatch=assessment.tool_mismatch,
        low_evidence_quality=assessment.low_evidence_quality,
        ambiguous_intent=assessment.ambiguous_intent,
        verification_failed=assessment.verifier_failure,
    )
    assert assessment.band == "high"
    assert set(assessment.reasons) >= {
        "model_disagreement", "tool_mismatch", "low_evidence_quality",
        "ambiguous_user_intent", "verifier_failure",
    }
    assert escalated.selected_gear == "deliberative"
    assert escalated.authority_increased is False
    assert escalated.effective_autonomy_level == base.effective_autonomy_level


def test_domain_ceiling_applies_only_to_the_active_domain():
    overrides = {"external_mutations": 1, "project_initiative": 4}
    assert effective_autonomy(5, overrides, "project_initiative") == 4
    assert effective_autonomy(5, overrides, "external_mutations") == 1
    assert effective_autonomy(5, overrides, None) == 5


def test_all_five_autonomy_levels_resolve_distinct_bounded_capability_policy():
    policies = {level: resolve_autonomy_policy(level, {})[1] for level in range(1, 6)}
    assert policies[1]["direct_user_instructions"] is True
    assert policies[1]["propose_next_steps"] is False
    assert policies[2]["propose_next_steps"] is True
    assert policies[2]["initiate_bounded_web_research"] is False
    assert policies[3]["initiate_bounded_web_research"] is True
    assert policies[3]["broaden_bounded_investigations"] is False
    assert policies[4]["broaden_bounded_investigations"] is True
    assert policies[4]["sustain_multistage_research_engineering"] is False
    assert policies[5]["sustain_multistage_research_engineering"] is True
    for policy in policies.values():
        assert policy["self_increase_authority"] is False
        assert policy["bypass_approval"] is False
        assert policy["unlock_sealed_memory"] is False
        assert policy["silent_publish_or_push"] is False

    domains, narrowed = resolve_autonomy_policy(5, {
        "web_initiative": 1,
        "coding_execution": 2,
        "external_mutations": 1,
    })
    assert domains["web_initiative"] == 1
    assert narrowed["initiate_bounded_web_research"] is False
    assert narrowed["sustain_multistage_research_engineering"] is False
    assert narrowed["mutate_external_systems_without_approval"] is False


def test_canonical_autonomy_contract_is_exactly_one_through_five():
    contract_path = Path(__file__).parents[1] / "config" / "policies" / "autonomy_levels.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    assert contract["default_level"] == 3
    assert set(contract["levels"]) == {1, 2, 3, 4, 5}
    assert [contract["levels"][level]["name"] for level in range(1, 6)] == [
        "directed", "assisted", "collaborative", "proactive", "stewarded_initiative",
    ]
    assert SessionState().autonomy_level == 3
    assert SessionState(autonomy_level=0).autonomy_level == 1
    assert SessionState(autonomy_level=6).autonomy_level == 5


def test_directed_level_allows_explicit_tools_and_research_but_never_initiative():
    explicit = decide_cognition(GovernorInput(
        request_id="directed-explicit", message="Research this requested public topic",
        mode="researcher", intent={"primary": "research"}, autonomy_level=1,
        internet_enabled=True, research_required=True, tool_required=True,
    ))
    assert explicit.research_allowed is True
    assert explicit.tool_execution_allowed is True
    assert explicit.capability_policy["initiate_bounded_web_research"] is False
    automatic = decide_cognition(GovernorInput(
        request_id="directed-automatic", message="Explain this local note",
        mode="default", intent={"primary": "ordinary"}, autonomy_level=1,
        internet_enabled=True,
    ))
    assert automatic.research_allowed is False


def test_owner_creates_isolated_managed_profile_without_switching_session(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    store.create_account(AccountCreateRequest(username="owner", password="synthetic owner password"))
    owner_id = store.state().active_user_id
    store.create_account(AccountCreateRequest(
        username="managed", password="synthetic managed password",
        managed_profile=True,
    ))
    assert store.state().active_user_id == owner_id
    assert store.state().active_role == LocalAccountRole.INSTALLATION_OWNER
    with store._connect() as conn:
        managed = conn.execute("SELECT * FROM users WHERE username = 'managed'").fetchone()
        sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (managed["id"],)).fetchone()[0]
    assert managed["local_role"] == "user"
    assert managed["managed"] == 1
    assert sessions == 0
    store.logout()
    state = store.login(AccountLoginRequest(username="managed", password="synthetic managed password"))
    assert state.active_profile_managed is True
    assert state.supervision_notice


def test_admin_summary_and_policy_change_never_serialize_content(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    store.create_account(AccountCreateRequest(username="owner", password="synthetic owner password"))
    store.create_account(AccountCreateRequest(username="user", password="synthetic user password"))
    service = AdminService(store)
    summary = service.summary()
    rendered = repr(summary)
    assert summary["content_authorities_queried"] == []
    assert summary["metadata_authorities_queried"] == ["canonical_memory_metadata"]
    assert all(
        row["content_included"] is False
        for row in summary["memory_storage_by_profile"]
    )
    assert summary["admin_content_access_granted"] is False
    assert summary["local_online_identity_federated"] is False
    assert "memory body canary" not in rendered
    target = next(row for row in summary["roster"] if row["username"] == "user")
    preview = service.preview(AdminChangePreviewRequest(
        change_kind=AdminChangeKind.SET_MANAGED_POLICY,
        target_user_id=target["user_id"], managed=True,
        managed_policy=ManagedProfilePolicy(autonomy_maximum=2),
        reason="Synthetic managed-profile ceiling proof",
    ))
    applied = service.apply(AdminChangeApplyRequest(
        preview_id=preview["preview_id"], approval_token=preview["approval_token"]
    ))
    assert applied["content_access_changed"] is False
    assert applied["effective_state"]["managed_policy"]["autonomy_maximum"] == 2


def test_every_managed_profile_ceiling_is_consumed_by_authoritative_gates(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    store.create_account(AccountCreateRequest(username="owner", password="synthetic owner password"))
    store.create_account(AccountCreateRequest(username="managed", password="synthetic managed password"))
    target = next(row for row in AdminService(store).summary()["roster"] if row["username"] == "managed")
    policy = ManagedProfilePolicy(
        autonomy_maximum=2,
        internet_allowed=False,
        addons_allowed=False,
        connectors_allowed=False,
        coding_execution_allowed=False,
        project_agent_limit=0,
        external_mutations_allowed=False,
        background_cognition_allowed=False,
        cpu_percent_ceiling=40,
        ram_mb_ceiling=2048,
        vram_mb_ceiling=1024,
        network_filter_level="strict",
    )
    preview = AdminService(store).preview(AdminChangePreviewRequest(
        change_kind=AdminChangeKind.SET_MANAGED_POLICY,
        target_user_id=target["user_id"], managed=True, managed_policy=policy,
        reason="Synthetic complete managed-policy consumption proof",
    ))
    AdminService(store).apply(AdminChangeApplyRequest(
        preview_id=preview["preview_id"], approval_token=preview["approval_token"]
    ))
    store.logout()
    store.login(AccountLoginRequest(username="managed", password="synthetic managed password"))
    monkeypatch.setattr(
        "app.api.user_control_service.get_active_elysia_paths", lambda: store.elysia_paths
    )
    monkeypatch.setattr(
        "app.api.user_control_service.get_authenticated_governance",
        store.authenticated_governance,
    )
    monkeypatch.setattr(
        "app.api.account_service.get_authenticated_principal",
        store.authenticated_principal,
    )
    controls = current_user_controls()
    assert controls.autonomy_level <= 2
    assert controls.internet_master_enabled is False
    assert controls.addons_allowed is False
    assert controls.connectors_allowed is False
    assert controls.coding_execution_allowed is False
    assert controls.project_agent_limit == 0
    assert controls.external_mutations_allowed is False
    assert controls.background_cognition_enabled is False
    assert controls.cpu_percent_ceiling == 40
    assert controls.ram_mb_ceiling == 2048
    assert controls.vram_mb_ceiling == 1024
    assert controls.network_filter_level == "strict"
    for capability in ("addons", "connectors", "coding_execution", "external_mutations"):
        assert managed_capability_allowed(capability) is False
    assert _managed_policy_requirements("/coding/task/advance", "POST") == ("coding_execution",)
    assert _managed_policy_requirements("/marketplace/link", "DELETE") == ()
    assert _managed_policy_requirements(
        "/projects/synthetic/connectors/soundcloud/authorize", "POST"
    ) == ("connectors", "external_mutations")


def test_protected_mutation_fails_closed_when_managed_policy_truth_is_unavailable(
    monkeypatch,
):
    def unavailable(_capability: str) -> bool:
        raise RuntimeError("synthetic policy authority outage")

    monkeypatch.setattr(
        "app.api.user_control_service.managed_capability_allowed", unavailable
    )
    response = ASGITestClient(create_app()).post(
        "/coding/task/advance", json={"synthetic": True}
    )
    assert response.status_code == 503
    payload = response.json()
    assert payload["result_type"] == "managed_profile_policy_unavailable"
    assert payload["data"]["policy_verification_failed_closed"] is True
    assert payload["data"]["content_inspected"] is False


def test_compute_ledger_preemption_restart_and_cpu_fallback(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    paths = store.elysia_paths
    monkeypatch.setattr(
        "app.cognition.compute_governor.resource_snapshot",
        lambda: {
            "system": {"cpu_percent": 10, "ram_available_mb": 64000},
            "gpu": {"available": True, "devices": [{"memory_free_mb": 10000}]},
            "ollama_residency": [],
        },
    )
    low = WorkloadDescriptor(
        workload_id="background", owner_user_id="synthetic", task_kind="embedding",
        priority="background", estimated_vram_mb=7000,
    )
    high = WorkloadDescriptor(
        workload_id="interactive", owner_user_id="synthetic", task_kind="model",
        priority="interactive", interactive=True, estimated_vram_mb=8000,
        preemptible=False,
    )
    first = decide_compute(low, preference="gpu", paths=paths)
    second = decide_compute(high, preference="gpu", paths=paths)
    assert first.lease_id
    assert second.selected_device == "cpu"
    assert any("preemption_requested" in item for item in second.reasons)
    ledger = ComputeLedger(paths)
    assert [row["workload_id"] for row in ledger.active_leases()] == ["background"]
    assert ledger.active_leases()[0]["state"] == "preempting"
    ledger.cancel_all()
    monkeypatch.setattr(
        "app.cognition.compute_governor.resource_snapshot",
        lambda: {"system": {"cpu_percent": 10}, "gpu": {"available": False, "devices": []}, "ollama_residency": []},
    )
    fallback = decide_compute(high, preference="gpu", paths=paths)
    assert fallback.selected_device == "cpu"
    assert fallback.fallback is None


def test_compute_reuses_resident_model_without_double_counting_weights(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    state = {
        "system": {"cpu_percent": 10, "ram_available_mb": 64000},
        "gpu": {"available": True, "devices": [{
            "memory_free_mb": 2200, "temperature_c": 50,
            "utilization_percent": 5,
        }]},
        "ollama_residency": [{"model": "synthetic:24b", "size_vram_mb": 13800}],
    }
    workload = WorkloadDescriptor(
        workload_id="resident-model", owner_user_id="synthetic",
        task_kind="language_model", interactive=True, priority="interactive",
        estimated_ram_mb=14800, estimated_vram_mb=13800,
        incremental_vram_mb=1024, required_model="synthetic:24b",
        required_resources=("local_ollama",), hard_vram_limit_mb=16000,
        estimate_source="ollama_live_residency_size_vram",
    )
    decision = decide_compute(
        workload, preference="automatic", ram_mb_ceiling=16000,
        vram_mb_ceiling=16000, paths=store.elysia_paths, resource_state=state,
    )
    assert decision.selected_device == "cuda:0"
    assert decision.workload["estimated_vram_mb"] == 13800
    assert decision.workload["incremental_vram_mb"] == 1024
    lease = ComputeLedger(store.elysia_paths).active_leases()[0]
    assert lease["estimated_vram_mb"] == 13800
    assert lease["incremental_vram_mb"] == 1024
    assert lease["hard_vram_limit_mb"] == 16000
    assert lease["required_model"] == "synthetic:24b"
    assert ComputeLedger(store.elysia_paths).release(decision.lease_id, reason="test")
    assert ComputeLedger(store.elysia_paths).release_job(decision.reservation_id, reason="test")

    over_ceiling = decide_compute(
        replace(workload, workload_id="resident-over-ceiling"),
        preference="automatic", ram_mb_ceiling=16000, vram_mb_ceiling=12000,
        paths=store.elysia_paths, resource_state=state,
    )
    assert over_ceiling.selected_device == "cpu"
    assert "workload_total_vram_ceiling_exceeded" in over_ceiling.reasons
    assert ComputeLedger(store.elysia_paths).release_job(over_ceiling.reservation_id, reason="test")


def test_compute_background_queue_deadline_and_job_release(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    paths = store.elysia_paths
    state = {
        "system": {"cpu_percent": 10, "ram_available_mb": 64000},
        "gpu": {"available": False, "devices": []},
        "ollama_residency": [],
    }
    first = decide_compute(
        WorkloadDescriptor(
            workload_id="background-1", owner_user_id="synthetic",
            task_kind="bounded_background", priority="background",
        ),
        max_background_jobs=1, paths=paths, resource_state=state,
    )
    assert first.reservation_id
    second = decide_compute(
        WorkloadDescriptor(
            workload_id="background-2", owner_user_id="synthetic",
            task_kind="bounded_background", priority="background",
        ),
        max_background_jobs=1, paths=paths, resource_state=state,
    )
    assert second.decision == "deferred"
    assert "background_queue_ceiling_reached" in second.reasons
    assert ComputeLedger(paths).release_job(first.reservation_id, reason="test_complete")
    expired = decide_compute(
        WorkloadDescriptor(
            workload_id="expired", owner_user_id="synthetic", task_kind="test",
            deadline_utc="2000-01-01T00:00:00Z",
        ),
        paths=paths, resource_state=state,
    )
    assert expired.decision == "rejected"
    assert "workload_deadline_expired" in expired.reasons


def test_compute_oom_history_is_durable_bounded_and_content_free(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    ledger = ComputeLedger(store.elysia_paths)
    incident_id = ledger.record_oom(
        workload_id="request-synthetic-oom",
        task_kind="model_inference",
        selected_device="cuda:0",
        observed_vram_mb=15000,
        hard_vram_limit_mb=12288,
        recovery_action="lease_released_cpu_fallback_allowed",
    )
    history = ComputeLedger(store.elysia_paths).recent_oom_history(limit=1)
    assert history == [
        {
            "incident_id": incident_id,
            "workload_id": "request-synthetic-oom",
            "task_kind": "model_inference",
            "selected_device": "cuda:0",
            "incident_code": "accelerator_out_of_memory",
            "observed_vram_mb": 15000,
            "hard_vram_limit_mb": 12288,
            "recovery_action": "lease_released_cpu_fallback_allowed",
            "created_at_utc": history[0]["created_at_utc"],
            "content_free": 1,
        }
    ]
    assert "password" not in json.dumps(history).casefold()


def test_compute_stdlib_metrics_and_thermal_fallback_are_truthful(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    snapshot = resource_snapshot()
    assert snapshot["private_content_included"] is False
    assert snapshot["system"]["logical_cpus"] >= 1
    if Path("/proc/meminfo").is_file():
        assert snapshot["system"]["ram_total_mb"] is not None
        assert snapshot["system"]["ram_available_mb"] is not None
        assert snapshot["system"]["process_rss_mb"] is not None
    hot = decide_compute(
        WorkloadDescriptor(
            workload_id="thermal", owner_user_id="synthetic", task_kind="model",
            estimated_vram_mb=1000,
        ),
        preference="gpu", paths=store.elysia_paths,
        resource_state={
            "system": {"cpu_percent": 10, "ram_available_mb": 64000},
            "gpu": {"available": True, "devices": [{
                "memory_free_mb": 12000, "temperature_c": 91,
                "utilization_percent": 10,
            }]},
            "ollama_residency": [],
        },
    )
    assert hot.selected_device == "cpu"
    assert "gpu_thermal_safety_fallback" in hot.reasons
    assert hot.reservation_id
    assert ComputeLedger(store.elysia_paths).release_job(
        hot.reservation_id, reason="thermal_test_complete"
    )


def test_operational_self_model_is_content_free_and_non_anthropomorphic():
    payload = operational_self_model(
        selected_gear="deep", selected_model="synthetic-local", selected_device="cpu",
        autonomy_level=3, internet_enabled=False, stop_active=False,
        assessment={"score": 0.8, "band": "high", "conflict_count": 1,
                    "retrieval_insufficient": True, "reasons": ["conflict"]},
        active_memory_banks=["memory", "conversation"],
        active_projections=["fts5", "qdrant"],
        resource_state={
            "system": {"cpu_percent": 12, "ram_available_mb": 32000},
            "gpu": {"available": True, "devices": [{"name": "synthetic"}]},
            "compute_queue": {"active_job_count": 1},
        },
        current_constraints=["local_first"],
        recent_failures=["conflict"],
        benchmarked_weaknesses=["synthetic_fixture_only"],
    )
    assert payload["consciousness_claimed"] is False
    assert payload["hidden_reasoning_exposed"] is False
    assert payload["private_content_included"] is False
    assert payload["active_memory_banks"] == ["conversation", "memory"]
    assert payload["active_projections"] == ["fts5", "qdrant"]
    assert payload["resource_state"]["gpu_device_count"] == 1
    assert payload["current_constraints"] == ["local_first"]
    assert payload["recent_tool_model_failures"] == ["conflict"]


def test_model_registry_reports_digest_quantization_roles_residency_and_history(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.cognition.model_registry._get_json",
        lambda url, _timeout: (
            {"models": [{
                "name": "mistral-small3.1:24b", "digest": "sha256:synthetic",
                "size": 12_000_000_000, "modified_at": "2026-08-22T00:00:00Z",
                "details": {"format": "gguf", "family": "mistral", "families": ["mistral"],
                            "parameter_size": "24B", "quantization_level": "Q4_K_M"},
            }]}
            if url.endswith("/api/tags") else
            {"models": [{"name": "mistral-small3.1:24b", "size_vram": 10_000_000_000,
                         "context_length": 32768, "expires_at": "2026-08-22T00:05:00Z"}]}
        ),
    )
    registry = ModelRegistry(store.elysia_paths)
    monkeypatch.setattr(registry, "_history", lambda: {
        "mistral-small3.1:24b": {"sample_count": 3, "success_count": 3,
                                  "failure_count": 0, "median_latency_ms": 900,
                                  "median_load_duration_ms": 120.5}
    })
    snapshot = registry.snapshot()
    model = snapshot["models"][0]
    assert model["digest"] == "sha256:synthetic"
    assert model["quantization_level"] == "Q4_K_M"
    assert model["role_ids"] == ["primary_general"]
    assert model["loaded"] is True
    assert model["history"]["median_load_duration_ms"] == 120.5
    assert model["license_provenance_state"] == "not_reported_by_ollama_api_requires_model_manifest"
    assert model["capabilities"]
    assert model["benchmark_classes"] == ["primary_general"]
    assert model["local_external_state"] == "installed_local_ollama"
    estimate = model_resource_estimate(snapshot, "mistral-small3.1:24b")
    assert estimate["measurement_source"] == "ollama_live_residency_size_vram"
    assert estimate["estimated_vram_mb"] > estimate["incremental_vram_mb"]


def test_emergency_stop_is_idempotent_cancels_requests_and_requires_explicit_reset(tmp_path, monkeypatch):
    store = make_store(tmp_path, monkeypatch)
    paths = store.elysia_paths
    actor = {"user_id": "owner-synthetic", "role": "installation_owner"}
    monkeypatch.setattr(emergency_control.account_service, "get_active_elysia_paths", lambda: paths)
    monkeypatch.setattr(emergency_control.account_service, "get_authenticated_governance", lambda: actor)
    emergency_control._STOP_EVENT.clear()
    event = emergency_control.request_cancel_event("request-synthetic")
    called = []
    emergency_control.register_canceller("synthetic_worker", lambda: called.append(True) or 1)
    pending_connector = (
        paths.state_dir
        / "connectors"
        / "soundcloud"
        / "synthetic-owner-hash"
        / "pending.json"
    )
    pending_connector.parent.mkdir(mode=0o700, parents=True)
    pending_connector.write_text('{"synthetic": true}\n', encoding="utf-8")
    try:
        first = emergency_control.activate_emergency_stop(reason="Synthetic operator stop", paths=paths)
        second = emergency_control.activate_emergency_stop(reason="Repeat", paths=paths)
        assert first["active"] is True
        assert second["trigger_id"] == first["trigger_id"]
        assert second["idempotent_repeat"] is True
        assert event.is_set()
        assert called == [True]
        assert first["internet_effectively_enabled"] is False
        assert first["runtime_autonomy_override"] == 1
        assert first["cleanup"]["external_connector_network_closed"] is True
        assert first["cleanup"]["soundcloud_pending_authorizations_closed"] == 1
        assert pending_connector.exists() is False
        assert first["reason"] == "Operator emergency stop"
        assert first["reason_code"] == "operator_requested"
        assert first["reason_detail_stored"] is False
        assert "Synthetic operator stop" not in paths.emergency_state_path.read_text(encoding="utf-8")
        emergency_control._STOP_EVENT.clear()
        recovered = emergency_control.initialize_emergency_state(paths)
        assert recovered["active"] is True
        assert recovered["restart_recovery_performed"] is True
        assert recovered["resume_required"] is True
        reset = emergency_control.reset_emergency_stop(paths)
        assert reset["active"] is False
        assert emergency_control.emergency_active(paths) is False
    finally:
        emergency_control.unregister_canceller("synthetic_worker")
        emergency_control.release_request("request-synthetic")
        emergency_control._STOP_EVENT.clear()


def test_per_request_cancellation_is_owner_scoped_and_content_free():
    request_id = "request-owner-scoped-synthetic"
    event = emergency_control.request_cancel_event(request_id)
    emergency_control.bind_request_owner(request_id, "owner-a")
    try:
        assert emergency_control.cancel_request(request_id, "owner-b") is False
        assert event.is_set() is False
        assert emergency_control.cancel_request(request_id, "owner-a") is True
        assert event.is_set() is True
    finally:
        emergency_control.release_request(request_id)
