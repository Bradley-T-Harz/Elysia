from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from app.api.addons import registry


def _redirect_addons_tree(monkeypatch, root: Path) -> None:
    def fake_tree():
        paths = {
            "root": root,
            "installed": root / "installed",
            "staged": root / "staged",
            "disabled": root / "disabled",
            "removed": root / "removed",
            "cache": root / "cache",
            "rollback": root / "rollback",
            "manifests": root / "manifests",
            "audit": root / "audit",
            "quarantine": root / "quarantine",
            "samples": root / "samples",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    monkeypatch.setattr(registry, "addons_root", lambda: root)
    monkeypatch.setattr(registry, "ensure_addons_tree", fake_tree)


def _make_package(tmp_path: Path) -> Path:
    files = {"files/tool.py": "def describe():\n    return 'safe sample'\n"}
    checksums = {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in files.items()}
    manifest = {
        "schema_version": "1.0",
        "addon_id": "org.ecosyneva.registry-test",
        "name": "Registry Test",
        "version": "0.1.0",
        "publisher": {"name": "Tester"},
        "compatibility": {"min_elysia_version": "0.1.0", "addon_api_version": "1"},
        "entrypoints": {"tool": "files/tool.py"},
        "permissions": [{"key": "model.invoke.local", "required": False, "reason": "Local test only."}],
        "sandbox": {"required": True, "network": "deny_by_default", "filesystem": "temporary_only"},
        "checksums": {"files": checksums},
        "binaries": [],
    }
    package = tmp_path / "registry-test.elysia-addon"
    with ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, content in files.items():
            archive.writestr(name, content)
    return package


def test_install_plan_is_preview_only(tmp_path: Path, monkeypatch):
    _redirect_addons_tree(monkeypatch, tmp_path / "Add-ons")
    package = _make_package(tmp_path)

    plan = registry.create_install_plan(package)

    assert plan["plan_state"] == "exact_transition_plan_required"
    assert plan["execution_enabled"] is False
    assert plan["enable_requires_separate_approval"] is True
    assert plan["private_core_access_allowed"] is False


def test_legacy_direct_install_and_registry_transitions_are_blocked(tmp_path: Path, monkeypatch):
    _redirect_addons_tree(monkeypatch, tmp_path / "Add-ons")
    package = _make_package(tmp_path)

    installed = registry.install_disabled(package)
    assert installed["installed"] is False
    assert installed["reason_code"] == "exact_transition_plan_required"

    enabled = registry.update_status("org.ecosyneva.registry-test", "0.1.0", "enabled_limited")
    assert enabled["ok"] is False
    assert enabled["reason_code"] == "exact_transition_plan_required"

    audit = registry.read_audit()
    assert any(record["action"] == "install_disabled" and record["result"] == "blocked" for record in audit)


def test_validation_only_sandbox_runs_no_code(tmp_path: Path, monkeypatch):
    _redirect_addons_tree(monkeypatch, tmp_path / "Add-ons")
    package = _make_package(tmp_path)

    result = registry.validation_only_sandbox(package)

    assert result["sandbox_mode"] == "validation_only"
    assert result["executed_code"] is False
    assert result["network_allowed"] is False
    assert result["result"] == "passed"


def test_rollback_without_snapshot_is_blocked(tmp_path: Path, monkeypatch):
    _redirect_addons_tree(monkeypatch, tmp_path / "Add-ons")
    package = _make_package(tmp_path)
    result = registry.rollback("org.ecosyneva.registry-test", "0.1.0")

    assert result["ok"] is False
    assert "error" in result
