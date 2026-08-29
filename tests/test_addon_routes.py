from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import httpx

from app.api.addons import lifecycle_service, registry
from app.api.account_service import AccountPaths, AccountStore
from app.api.main import create_app
from app.api.routes import addons as addon_routes
from app.api.schemas.account import AccountCreateRequest
from app.install.paths import resolve_elysia_paths
from app.api.schemas.addons import AddonMarketplaceIntentRequest, AddonPackagePathRequest


def _make_package(tmp_path: Path) -> Path:
    files = {"files/tool.py": "def describe():\n    return 'route safe'\n"}
    checksums = {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in files.items()}
    manifest = {
        "schema_version": "1.0",
        "addon_id": "org.ecosyneva.route-test",
        "name": "Route Test",
        "version": "0.1.0",
        "publisher": {"name": "Tester"},
        "compatibility": {"min_elysia_version": "0.1.0", "addon_api_version": "1"},
        "entrypoints": {"tool": "files/tool.py"},
        "permissions": [{"key": "model.invoke.local", "required": False, "reason": "Route test only."}],
        "sandbox": {"required": True, "network": "deny_by_default", "filesystem": "temporary_only"},
        "checksums": {"files": checksums},
        "binaries": [],
    }
    package = tmp_path / "route-test.elysia-addon"
    with ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, content in files.items():
            archive.writestr(name, content)
    return package


def _redirect_addons_tree(monkeypatch, root: Path) -> None:
    def fake_tree():
        paths = {
            key: root / key
            for key in ("installed", "staged", "disabled", "removed", "cache", "rollback", "manifests", "audit", "quarantine", "samples")
        }
        paths["root"] = root
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    monkeypatch.setattr(registry, "addons_root", lambda: root)
    monkeypatch.setattr(registry, "ensure_addons_tree", fake_tree)
    lifecycle_service.clear_lifecycle_state_for_tests()


def test_addons_routes_registered_and_inspect_package(tmp_path: Path, monkeypatch):
    _redirect_addons_tree(monkeypatch, tmp_path / "addons")
    package = _make_package(tmp_path)

    status = asyncio.run(addon_routes.get_addons_status())
    assert status["data"]["addons_status"]["install_requires_local_approval"] is True

    response = asyncio.run(addon_routes.inspect_package(AddonPackagePathRequest(package_path=str(package))))
    assert response["data"]["inspection"]["valid"] is True
    assert response["data"]["inspection"]["manifest"]["addon_id"] == "org.ecosyneva.route-test"


def test_marketplace_intent_route_does_not_install(monkeypatch):
    monkeypatch.setattr(addon_routes, "append_audit", lambda *args, **kwargs: None)

    response = asyncio.run(
        addon_routes.open_marketplace_intent(
            AddonMarketplaceIntentRequest(deep_link_url="elysia://marketplace/install?intent_id=abc-123&nonce=nonce_ok")
        )
    )

    assert response["data"]["trusted_as_authority"] is False
    assert response["data"]["will_install"] is False


def test_governed_addon_routes_through_async_asgi_are_truthful_and_nonexecuting(tmp_path: Path, monkeypatch) -> None:
    for variable, leaf in (
        ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        monkeypatch.setenv(variable, str(tmp_path / leaf))
    elysia_paths = resolve_elysia_paths()
    identity_root = elysia_paths.identity_dir
    account_store = AccountStore(AccountPaths(
        identity_root=identity_root,
        database_path=identity_root / "elysia_identity.sqlite",
        profile_photo_dir=identity_root / "profile_photos",
        current_session_path=identity_root / "current_session.json",
        elysia_paths=elysia_paths,
    ))
    account_store.create_account(AccountCreateRequest(
        username="synthetic-addon-owner",
        password="synthetic addon owner password",
    ))
    monkeypatch.setattr(
        "app.api.user_control_service.get_authenticated_governance",
        account_store.authenticated_governance,
    )
    _redirect_addons_tree(monkeypatch, tmp_path / "addons")

    async def exercise() -> tuple[dict, dict, dict, dict]:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://elysia.local") as client:
            status = (await client.get("/addons/status")).json()
            candidates = (await client.get("/addons/official-candidates")).json()
            blocked = (
                await client.post(
                    "/addons/enable",
                    json={"addon_id": "org.ecosyneva.route-test", "version": "0.1.0"},
                )
            ).json()
            submission = (
                await client.post(
                    "/addons/marketplace/submission-preview",
                    json={
                        "addon_id": "org.ecosyneva.route-test",
                        "version": "0.1.0",
                        "package_hash": "a" * 64,
                        "source_kind": "elysia_addon",
                        "publisher_identity": "test.publisher",
                        "static_scan_passed": True,
                        "privacy_notice_acknowledged": True,
                    },
                )
            ).json()
            return status, candidates, blocked, submission

    status, candidates, blocked, submission = asyncio.run(exercise())
    rendered = json.dumps((status, candidates, blocked, submission))
    assert status["data"]["addons_status"]["execution_enabled"] is False
    assert status["data"]["addons_status"]["cloud_sandbox_required"] is False
    assert candidates["data"]["official_candidates"][0]["listing_state"] == "official_v1_release"
    assert candidates["data"]["official_candidates"][0]["install_action_live"] is True
    assert candidates["data"]["official_candidates"][0]["public_distribution_supported"] is True
    assert candidates["data"]["official_candidates"][0]["in_app_install_control_live"] is False
    assert blocked["status"] == "blocked"
    assert blocked["approval_state"] == "needed"
    assert blocked["data"]["operation_result"]["reason_code"] == "exact_transition_approval_required"
    assert submission["data"]["submission_preview"]["will_upload"] is False
    assert submission["data"]["submission_preview"]["will_publish"] is False
    assert str(tmp_path) not in rendered
    assert "approval_token" not in rendered
