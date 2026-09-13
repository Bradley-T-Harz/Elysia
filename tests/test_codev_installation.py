import json
from types import SimpleNamespace

import pytest

from core.codev import installation


def receipt(tmp_path, monkeypatch, **updates):
    target = tmp_path / "codev-install.json"
    payload = {"schema_version": 1, "extension_id": "ecosyneva-commons.elysia-codev",
               "version": "1.0.0", "contract_version": "vscode-coding-agent-contract-0.1",
               "install_state": "installed_by_user", "package_sha256": "a" * 64}
    payload.update(updates)
    target.write_text(json.dumps(payload))
    target.chmod(0o600)
    monkeypatch.setattr(installation, "codev_receipt_path", lambda paths: target)
    monkeypatch.setattr(installation, "_runtime_available", lambda: (True, "Ready with separate grants."))
    return target


def test_absent_does_not_probe_runtime_processes_profiles_or_network(tmp_path, monkeypatch):
    monkeypatch.setattr(installation, "codev_receipt_path", lambda paths: tmp_path / "absent.json")
    monkeypatch.setattr(installation, "_runtime_available", lambda: pytest.fail("Absent Codev probed runtime"))
    status = installation.resolve_installation()
    assert status.state == "absent" and not status.usable
    assert not status.capabilities


def test_trusted_legacy_receipt_drives_neutral_manifest_without_editor_process(tmp_path, monkeypatch):
    receipt(tmp_path, monkeypatch)
    status = installation.resolve_installation()
    assert status.state == "installed_ready"
    assert status.usable and status.version == "1.0.0"
    capabilities = {item.id: item for item in status.capabilities}
    assert capabilities["workspace_read"].requires == ["workspace_grant", "selected_files"]
    for capability in ("cloud_model", "remote_repo_write", "package_install", "build_execute", "test_execute"):
        assert not capabilities[capability].available
    assert str(tmp_path) not in status.model_dump_json()


@pytest.mark.parametrize("change,expected", [
    ({"version": "2.0.0"}, "incompatible"),
    ({"contract_version": "unknown"}, "incompatible"),
    ({"package_sha256": ""}, "installed_unavailable"),
    ({"extension_id": "untrusted"}, "degraded"),
    ({"schema_version": 12}, "degraded"),
])
def test_unproven_or_incompatible_installation_cannot_enable_clients(tmp_path, monkeypatch, change, expected):
    receipt(tmp_path, monkeypatch, **change)
    status = installation.resolve_installation()
    assert status.state == expected
    assert not status.usable


def test_receipt_links_and_loose_permissions_fail_closed(tmp_path, monkeypatch):
    target = receipt(tmp_path, monkeypatch)
    target.chmod(0o644)
    assert installation.resolve_installation().state == "degraded"
    target.chmod(0o600)
    real = tmp_path / "real.json"
    target.rename(real)
    target.symlink_to(real)
    assert installation.resolve_installation().state == "degraded"


def test_local_capability_unavailability_is_distinct_from_absence(tmp_path, monkeypatch):
    receipt(tmp_path, monkeypatch)
    monkeypatch.setattr(installation, "_runtime_available", lambda: (False, "Managed profile restriction."))
    status = installation.resolve_installation()
    assert status.installed and not status.usable
    assert status.state == "installed_unavailable"
    assert not any(item.available for item in status.capabilities)


def test_native_endpoint_exposes_same_neutral_contract(tmp_path, monkeypatch):
    from app.api.routes.codev import installation_status
    receipt(tmp_path, monkeypatch)
    response = installation_status()
    assert response["api_version"] == "1.0.0"
    assert response["contract_version"] == "codev-client-1"
    assert response["data"]["codev_installation"]["usable"]
