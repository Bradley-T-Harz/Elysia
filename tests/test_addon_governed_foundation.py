from __future__ import annotations

from datetime import timedelta
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from app.api.addons import lifecycle_service, registry
from app.api.addons.manifest_validator import inspect_addon_package, load_permission_vocabulary, validate_manifest_payload
from app.api.addons.marketplace_review_service import (
    load_official_candidates,
    prepare_admin_review_preview,
    prepare_submission_preview,
)
from app.api.addons.permission_resolver import resolve_effective_permissions
from app.api.addons.preparation_service import prepare_developer_package_plan
from app.api.schemas.addons import (
    AddonSourceInventoryItem,
    AddonTransitionApplyRequest,
    AddonTransitionApprovalRequest,
    AddonTransitionPlanRequest,
    DeveloperAddonPackagePlanRequest,
    MarketplaceReviewPreviewRequest,
    MarketplaceSubmissionPreviewRequest,
)


def _redirect_addons_tree(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    def fake_tree() -> dict[str, Path]:
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
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return paths

    monkeypatch.setattr(registry, "addons_root", lambda: root)
    monkeypatch.setattr(registry, "ensure_addons_tree", fake_tree)
    lifecycle_service.clear_lifecycle_state_for_tests()


def _manifest(files: dict[str, str], **overrides: object) -> dict[str, object]:
    checksums = {name: hashlib.sha256(content.encode()).hexdigest() for name, content in files.items()}
    manifest: dict[str, object] = {
        "schema_version": "1.1",
        "addon_id": "org.ecosyneva.governed-test",
        "name": "Governed Test Add-on",
        "version": "1.0.0",
        "publisher": {"name": "Test Publisher", "identity": "test-only"},
        "compatibility": {
            "min_elysia_version": "0.1.0",
            "max_elysia_version": "1.0.0",
            "addon_api_version": "1",
        },
        "required_profiles": ["developer"],
        "entrypoints": {"tool": "files/tool.py"},
        "bridge": {"protocol": "json_rpc_stdio", "contract_version": "1", "execution_enabled": False},
        "permissions": [
            {"key": "model.invoke.local", "required": False, "reason": "Optional governed local model summary."}
        ],
        "network_policy": {"default": "deny", "declared_hosts": []},
        "filesystem_policy": {"default": "project_scoped", "mounts": []},
        "memory_policy": {"default": "deny", "classes": []},
        "model_provider_policy": {"default": "deny", "providers": []},
        "tool_worker_policy": {"default": "deny", "workers": []},
        "execution": {"requested": False},
        "sandbox": {"required": True, "network": "deny_by_default", "filesystem": "temporary_only"},
        "external_services": [],
        "license": {"spdx": "Apache-2.0"},
        "provenance": {"status": "self_declared", "source": "local"},
        "signing": {"publisher_key_id": None, "signature": None},
        "dependencies": [],
        "checksums": {"files": checksums},
        "binaries": [],
    }
    manifest.update(overrides)
    return manifest


def _package(tmp_path: Path, *, files: dict[str, str] | None = None, manifest_overrides: dict[str, object] | None = None) -> Path:
    files = files or {"files/tool.py": "def describe():\n    return 'static only'\n"}
    manifest = _manifest(files, **(manifest_overrides or {}))
    path = tmp_path / "governed.elysia-addon"
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _approve_apply(plan: dict[str, object]) -> dict[str, object]:
    approval = lifecycle_service.approve_transition(
        AddonTransitionApprovalRequest(
            plan_id=str(plan["plan_id"]),
            plan_hash=str(plan["plan_hash"]),
            operator_confirmed=True,
            actor="local_operator",
            confirmation=lifecycle_service.EXPECTED_CONFIRMATION,
        )
    )
    assert approval["approved"] is True
    return lifecycle_service.apply_transition(
        AddonTransitionApplyRequest(
            plan_id=str(plan["plan_id"]),
            plan_hash=str(plan["plan_hash"]),
            approval_id=str(approval["approval_id"]),
            approval_token=str(approval["approval_token"]),
        )
    )


def test_exact_plan_approval_stages_xdg_local_disabled_without_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "xdg-data" / "elysia" / "addons"
    _redirect_addons_tree(monkeypatch, root)
    package = _package(tmp_path)

    plan = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(action="install_disabled", package_path=str(package))
    )
    assert plan["plan_state"] == "ready_for_exact_approval"
    assert plan["current_state"] == "packaged"
    assert plan["proposed_state"] == "installed_disabled"
    assert plan["execution_enabled"] is False
    assert "package_path" not in plan

    result = _approve_apply(plan)
    assert result["ok"] is True
    assert result["entry"]["status"] == "installed_disabled"
    assert result["entry"]["storage_label"] == "XDG user add-on data"
    assert result["entry"]["permissions_effective"] == []
    assert result["execution_enabled"] is False
    assert (root / "installed" / "org.ecosyneva.governed-test" / "1.0.0" / "manifest.json").exists()
    assert str(root) not in json.dumps(result)


def test_direct_legacy_install_and_status_mutation_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_addons_tree(monkeypatch, tmp_path / "addons")
    package = _package(tmp_path)

    direct = registry.install_disabled(package)
    status = registry.update_status("org.ecosyneva.governed-test", "1.0.0", "enabled_limited")

    assert direct["installed"] is False
    assert direct["reason_code"] == "exact_transition_plan_required"
    assert status["ok"] is False
    assert status["reason_code"] == "exact_transition_plan_required"


def test_enable_limited_has_no_runtime_grants_then_disable_revoke_remove_are_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_addons_tree(monkeypatch, tmp_path / "addons")
    package = _package(tmp_path)
    installed = _approve_apply(
        lifecycle_service.plan_transition(AddonTransitionPlanRequest(action="install_disabled", package_path=str(package)))
    )
    entry = installed["entry"]

    enable_plan = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(
            action="enable_limited",
            addon_id=str(entry["addon_id"]),
            version=str(entry["version"]),
            expected_state="installed_disabled",
            expected_package_hash=str(entry["package_hash"]),
            approved_permissions=["model.invoke.local"],
        )
    )
    enabled = _approve_apply(enable_plan)
    assert enabled["entry"]["status"] == "enabled_limited"
    assert enabled["entry"]["permissions_approved"] == ["model.invoke.local"]
    assert enabled["entry"]["permissions_effective"] == []
    assert enabled["entry"]["bridge_authority_active"] is False

    disable_plan = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(action="disable", addon_id=str(entry["addon_id"]), version=str(entry["version"]))
    )
    disabled = _approve_apply(disable_plan)
    assert disabled["entry"]["status"] == "disabled"

    revoke_plan = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(action="revoke", addon_id=str(entry["addon_id"]), version=str(entry["version"]))
    )
    revoked = _approve_apply(revoke_plan)
    assert revoked["entry"]["status"] == "revoked"
    assert revoked["revocation_semantics"] == "trust_withdrawn_no_runtime_was_active"

    remove_plan = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(action="remove", addon_id=str(entry["addon_id"]), version=str(entry["version"]))
    )
    removed = _approve_apply(remove_plan)
    assert removed["entry"]["status"] == "removed"
    assert removed["files_retained"] is True
    assert removed["removal_semantics"] == "registry_marked_removed_files_retained"


def test_permission_widening_and_invalid_transition_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_addons_tree(monkeypatch, tmp_path / "addons")
    package = _package(tmp_path)
    widened = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(
            action="install_disabled",
            package_path=str(package),
            approved_permissions=["shell.run"],
        )
    )
    assert widened["reason_code"] == "permission_widening_refused"


def test_changed_package_hash_and_reused_approval_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_addons_tree(monkeypatch, tmp_path / "addons")
    package = _package(tmp_path)
    plan = lifecycle_service.plan_transition(AddonTransitionPlanRequest(action="install_disabled", package_path=str(package)))
    approval = lifecycle_service.approve_transition(
        AddonTransitionApprovalRequest(
            plan_id=str(plan["plan_id"]),
            plan_hash=str(plan["plan_hash"]),
            operator_confirmed=True,
            confirmation=lifecycle_service.EXPECTED_CONFIRMATION,
        )
    )
    package.write_bytes(package.read_bytes() + b"changed")
    request = AddonTransitionApplyRequest(
        plan_id=str(plan["plan_id"]),
        plan_hash=str(plan["plan_hash"]),
        approval_id=str(approval["approval_id"]),
        approval_token=str(approval["approval_token"]),
    )
    assert lifecycle_service.apply_transition(request)["reason_code"] == "package_hash_changed"
    assert lifecycle_service.apply_transition(request)["reason_code"] == "approval_already_used"


def test_stale_registry_revision_refuses_an_otherwise_valid_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_addons_tree(monkeypatch, tmp_path / "addons")
    installed = _approve_apply(
        lifecycle_service.plan_transition(
            AddonTransitionPlanRequest(action="install_disabled", package_path=str(_package(tmp_path)))
        )
    )
    entry = installed["entry"]
    stale_plan = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(
            action="enable_limited",
            addon_id=str(entry["addon_id"]),
            version=str(entry["version"]),
            expected_state="installed_disabled",
            expected_package_hash=str(entry["package_hash"]),
        )
    )
    stale_approval = lifecycle_service.approve_transition(
        AddonTransitionApprovalRequest(
            plan_id=str(stale_plan["plan_id"]),
            plan_hash=str(stale_plan["plan_hash"]),
            operator_confirmed=True,
            confirmation=lifecycle_service.EXPECTED_CONFIRMATION,
        )
    )
    _approve_apply(
        lifecycle_service.plan_transition(
            AddonTransitionPlanRequest(
                action="disable",
                addon_id=str(entry["addon_id"]),
                version=str(entry["version"]),
                expected_state="installed_disabled",
                expected_package_hash=str(entry["package_hash"]),
            )
        )
    )
    refused = lifecycle_service.apply_transition(
        AddonTransitionApplyRequest(
            plan_id=str(stale_plan["plan_id"]),
            plan_hash=str(stale_plan["plan_hash"]),
            approval_id=str(stale_approval["approval_id"]),
            approval_token=str(stale_approval["approval_token"]),
        )
    )
    assert refused["reason_code"] == "stale_registry_revision"


def test_expired_and_tampered_approval_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_addons_tree(monkeypatch, tmp_path / "addons")
    plan = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(action="install_disabled", package_path=str(_package(tmp_path)))
    )
    wrong = lifecycle_service.approve_transition(
        AddonTransitionApprovalRequest(
            plan_id=str(plan["plan_id"]),
            plan_hash="0" * 64,
            operator_confirmed=True,
            confirmation=lifecycle_service.EXPECTED_CONFIRMATION,
        )
    )
    assert wrong["reason_code"] == "plan_hash_mismatch"
    approval = lifecycle_service.approve_transition(
        AddonTransitionApprovalRequest(
            plan_id=str(plan["plan_id"]),
            plan_hash=str(plan["plan_hash"]),
            operator_confirmed=True,
            confirmation=lifecycle_service.EXPECTED_CONFIRMATION,
        )
    )
    future = lifecycle_service._now() + timedelta(seconds=lifecycle_service.APPROVAL_TTL_SECONDS + 1)
    monkeypatch.setattr(lifecycle_service, "_now", lambda: future)
    expired = lifecycle_service.apply_transition(
        AddonTransitionApplyRequest(
            plan_id=str(plan["plan_id"]),
            plan_hash=str(plan["plan_hash"]),
            approval_id=str(approval["approval_id"]),
            approval_token=str(approval["approval_token"]),
        )
    )
    assert expired["reason_code"] == "approval_expired"


def test_effective_permissions_are_a_strict_intersection() -> None:
    vocabulary = {
        "permissions": {
            "safe.bridge": {"default": "deny", "allowed_profiles": ["core"]},
            "shell.run": {"default": "blocked", "allowed_profiles": []},
        }
    }
    resolution = resolve_effective_permissions(
        ["safe.bridge", "shell.run"],
        approved_permissions=["safe.bridge", "shell.run", "undeclared.extra"],
        active_profiles=["core"],
        policy_allowed_permissions=["safe.bridge", "shell.run"],
        doctor_proven_permissions=["safe.bridge", "shell.run"],
        runtime_available_permissions=["safe.bridge", "shell.run"],
        bridge_ready=True,
        vocabulary=vocabulary,
    )
    assert resolution.effective == ("safe.bridge",)
    assert resolution.denied_reasons["shell.run"] == "hard_blocked_by_policy"
    assert resolution.denied_reasons["undeclared.extra"] == "permission_widening_refused"


def test_tracked_permission_vocabulary_is_deny_by_default_and_runtime_off() -> None:
    permissions = load_permission_vocabulary()["permissions"]
    assert permissions
    for definition in permissions.values():
        assert definition["default"] in {"deny", "blocked"}
        assert definition["runtime_available"] is False
    assert permissions["shell.run"]["default"] == "blocked"
    assert permissions["memory.read_scoped"]["allowed_profiles"] == []


def test_tracked_manifest_example_is_portable_valid_and_unsigned() -> None:
    root = Path(__file__).resolve().parents[1]
    raw = json.loads((root / "config" / "addons" / "manifest.example.json").read_text(encoding="utf-8"))
    manifest, errors, _, _ = validate_manifest_payload(raw)
    assert errors == []
    assert manifest is not None
    assert manifest.schema_version == "1.1"
    assert manifest.signing["signature"] is None
    assert "/home/" not in json.dumps(raw)
    private_workspace_marker = "MAIN" + "_Projects"
    assert private_workspace_marker not in json.dumps(raw)


def test_static_validator_refuses_duplicate_manifest_private_paths_secrets_network_and_special_files(tmp_path: Path) -> None:
    files = {"files/tool.py": "requests.get('https://example.invalid')\npassword=do-not-ship\npath='/home/person/private'\n"}
    package = _package(tmp_path, files=files)
    inspection = inspect_addon_package(package)
    assert inspection.valid is False
    joined = " ".join(inspection.errors)
    assert "Network behavior" in joined
    assert "Credential/secret-shaped" in joined
    assert "Private absolute-path" in joined
    assert "/home/person" not in joined

    manifest_private = _package(
        tmp_path,
        manifest_overrides={"publisher": {"name": "/home/person/private token=do-not-render"}},
    )
    private_inspection = inspect_addon_package(manifest_private)
    private_payload = json.dumps(private_inspection.to_payload())
    assert private_inspection.valid is False
    assert "/home/person" not in private_payload
    assert "do-not-render" not in private_payload
    assert "[local path hidden]" in private_payload
    assert "[private value hidden]" in private_payload

    duplicate = tmp_path / "duplicate.elysia-addon"
    with pytest.warns(UserWarning):
        with ZipFile(duplicate, "w") as archive:
            archive.writestr("manifest.json", "{}")
            archive.writestr("manifest.json", "{}")
    assert any("duplicate manifest.json" in error for error in inspect_addon_package(duplicate).errors)

    special = tmp_path / "special.elysia-addon"
    with ZipFile(special, "w") as archive:
        archive.writestr("manifest.json", "{}")
        info = ZipInfo("device")
        info.external_attr = 0o020666 << 16
        archive.writestr(info, "not-a-device")
    assert any("Special-file" in error for error in inspect_addon_package(special).errors)


def test_static_validator_enforces_count_compression_and_signing_truth(tmp_path: Path) -> None:
    too_many = tmp_path / "too-many.elysia-addon"
    with ZipFile(too_many, "w") as archive:
        archive.writestr("manifest.json", "{}")
        for index in range(501):
            archive.writestr(f"files/{index}.txt", "x")
    assert any("file count" in error.lower() for error in inspect_addon_package(too_many).errors)

    compressed = tmp_path / "compressed.elysia-addon"
    with ZipFile(compressed, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("files/repeated.txt", "A" * 1_000_000)
    assert any("compression ratio" in error.lower() for error in inspect_addon_package(compressed).errors)

    inspection = inspect_addon_package(_package(tmp_path))
    assert inspection.manifest is not None
    manifest_summary = inspection.to_payload()["manifest"]
    assert manifest_summary["signature_status"] == "unsigned"
    assert manifest_summary["raw_manifest_exposed"] is False
    assert "checksums" not in manifest_summary
    assert "entrypoints" not in manifest_summary


def test_developer_forge_plan_is_local_nonwriting_and_nonuploading() -> None:
    files = {"files/tool.py": "safe"}
    request = DeveloperAddonPackagePlanRequest(
        source_kind="external_tool_output",
        manifest=_manifest(files),
        files=[
            AddonSourceInventoryItem(
                relative_path="files/tool.py",
                size_bytes=4,
                sha256=hashlib.sha256(b"safe").hexdigest(),
                kind="source",
            )
        ],
    )
    result = prepare_developer_package_plan(request)
    assert result["plan_state"] == "ready_for_local_package_build"
    assert result["package_written"] is False
    assert result["will_upload"] is False
    assert result["will_push"] is False
    assert result["will_execute"] is False


def test_marketplace_submission_and_admin_review_are_nonmutating_hash_bound_previews() -> None:
    digest = "a" * 64
    blocked = prepare_submission_preview(
        MarketplaceSubmissionPreviewRequest(
            addon_id="org.ecosyneva.sample",
            version="1.0.0",
            package_hash=digest,
            source_kind="elysia_addon",
            publisher_identity="test.publisher",
            static_scan_passed=True,
            privacy_notice_acknowledged=False,
        )
    )
    assert blocked["preview_state"] == "blocked"
    assert "will leave your computer" in blocked["privacy_notice"]
    ready = prepare_submission_preview(
        MarketplaceSubmissionPreviewRequest(
            addon_id="org.ecosyneva.sample",
            version="1.0.0",
            package_hash=digest,
            source_kind="elysia_addon",
            publisher_identity="test.publisher",
            static_scan_passed=True,
            privacy_notice_acknowledged=True,
        )
    )
    assert ready["proposed_marketplace_state"] == "pending_review"
    assert ready["will_upload"] is False
    assert ready["will_publish"] is False

    review = prepare_admin_review_preview(
        MarketplaceReviewPreviewRequest(
            addon_id="org.ecosyneva.sample",
            version="1.0.0",
            package_hash=digest,
            publisher_identity="test.publisher",
            requested_permissions=["filesystem.read_project"],
            dependency_count=1,
            reviewer="admin-reviewer",
            decision="approved",
            permission_review_complete=True,
            compatibility_review_complete=True,
            dependency_review_complete=True,
            license_provenance_review_complete=True,
            static_scan_passed=True,
            known_risks=["Local code if a future execution profile is enabled."],
        )
    )
    assert review["review_state"] == "review_contract_valid"
    assert review["exact_hash_binding"] is True
    assert review["review_timestamp_utc"].endswith("Z")
    assert review["publisher_identity"] == "test.publisher"
    assert review["dependency_review_complete"] is True
    assert "not guaranteed safe" in review["disclaimer"]
    assert review["will_persist_review"] is False
    assert review["will_publish"] is False


def test_codev_is_an_official_qualified_v1_release() -> None:
    candidates = load_official_candidates()
    codev = next(item for item in candidates if item["name"] == "Codev")
    assert codev["listing_state"] == "official_v1_release"
    assert codev["required_profile"] == "developer"
    assert codev["install_action_live"] is True
    assert codev["public_distribution_supported"] is True
    assert codev["in_app_install_control_live"] is False
    assert codev["admin_reviewed"] is True
    assert codev["silent_shell_allowed"] is False
    assert codev["silent_push_allowed"] is False


def test_audit_and_status_are_sanitized_and_execution_stays_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_addons_tree(monkeypatch, tmp_path / "private" / "addons")
    registry.append_audit(
        "test",
        "blocked",
        addon_id="org.example.safe",
        details={"package_path": "/home/private/secret", "reason_code": "token=private"},
    )
    audit = registry.read_audit()
    status = registry.status_payload()
    rendered = json.dumps({"audit": audit, "status": status})
    assert "/home/private" not in rendered
    assert "token=private" not in rendered
    assert "addons_root" not in status
    assert status["storage_label"] == "XDG user add-on data"
    assert status["execution_enabled"] is False
    assert status["cloud_sandbox_required"] is False
    assert status["host_docker_socket_allowed"] is False


def test_blocked_approval_attempt_writes_sanitized_receipt_without_confirmation_or_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_addons_tree(monkeypatch, tmp_path / "private" / "addons")
    plan = lifecycle_service.plan_transition(
        AddonTransitionPlanRequest(action="install_disabled", package_path=str(_package(tmp_path)))
    )
    refused = lifecycle_service.approve_transition(
        AddonTransitionApprovalRequest(
            plan_id=str(plan["plan_id"]),
            plan_hash=str(plan["plan_hash"]),
            operator_confirmed=True,
            confirmation="wrong secret-shaped confirmation",
        )
    )
    assert refused["reason_code"] == "explicit_confirmation_required"
    rendered = json.dumps(registry.read_audit())
    assert "explicit_confirmation_required" in rendered
    assert "wrong secret-shaped confirmation" not in rendered
    assert "approval_token" not in rendered
    assert str(tmp_path) not in rendered


def test_addon_foundation_has_no_core_import_or_host_execution_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = "\n".join(
        (root / relative).read_text(encoding="utf-8")
        for relative in (
            "app/api/addons/manifest_validator.py",
            "app/api/addons/lifecycle_service.py",
            "app/api/addons/permission_resolver.py",
            "app/api/addons/preparation_service.py",
            "app/api/addons/registry.py",
        )
    )
    for forbidden in (
        "importlib.import_module",
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "docker.sock",
        "exec(",
        "eval(",
    ):
        assert forbidden not in sources
