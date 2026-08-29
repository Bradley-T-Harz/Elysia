from __future__ import annotations

from app.api.capability_service import get_capabilities_status


def test_identity_account_capability_truth_is_live_and_privacy_bounded():
    payload = get_capabilities_status()
    capabilities = {
        entry["capability_key"]: entry
        for entry in payload["data"]["capabilities"]
    }

    identity = capabilities["identity_account"]
    notes = " ".join(identity["notes"])

    assert identity["state"] == "live"
    assert identity["locality"] == "local"
    assert identity["approval_state"] == "not_needed"
    assert identity["read_only"] is False
    assert identity["supporting_endpoint"] == "/account/state"
    assert "Sealed local account" in notes
    assert "not normal Memory" in notes
    assert "Runtime receives only username/name" in notes
    assert "Password hashes" in notes
    assert "session tokens" in notes
    assert "original photo paths" in notes
