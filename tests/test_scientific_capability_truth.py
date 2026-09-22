from app.api import capability_service
from app.api.schemas.common import CapabilityState


def test_scientific_lane_is_visible_without_hiding_legacy_math(isolated_account_store):
    payload = capability_service.get_capabilities_status()
    entries = {row["capability_key"]: row for row in payload["data"]["capabilities"]}
    scientific = entries["scientific_workflows"]
    assert scientific["supporting_endpoint"] == "/chat/send"
    assert scientific["state"] == "live"
    assert entries["math_execution"]["supporting_endpoint"] == "/chat/send"
    assert entries["data_execution"]["supporting_endpoint"] == "/chat/send"
    assert "matrix_multiply" in " ".join(scientific["notes"])
    assert "installed-product qualification" in " ".join(scientific["notes"])


def test_absent_optional_backend_does_not_hide_the_workflow_or_other_operations(monkeypatch):
    actual = capability_service.importlib.util.find_spec
    monkeypatch.setattr(capability_service.importlib.util, "find_spec",
                        lambda name: None if name == "sympy" else actual(name))
    state, notes = capability_service._scientific_workflow_state()
    assert state == CapabilityState.DEGRADED
    assert "sympy" in notes[-1]
    assert "independently usable" in notes[-1]


def test_broken_service_is_unavailable_not_claimed_live(monkeypatch):
    monkeypatch.setattr(capability_service, "_module_attr_is_callable", lambda *a: False)
    assert capability_service._scientific_workflow_state()[0] == CapabilityState.UNAVAILABLE
