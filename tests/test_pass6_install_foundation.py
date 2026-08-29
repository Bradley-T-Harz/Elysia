from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess

import httpx
import pytest

from app.api.main import create_app
from app.install.doctor_service import record_doctor_result, run_doctor
from app.memory.canonical_repository import MemoryRepository
from app.install.local_auth import (
    LocalApiAuthPolicy,
    build_local_api_auth_policy,
    ensure_local_api_credential,
    rotate_local_api_credential,
    validate_local_api_credential,
)
from app.install.paths import (
    RuntimeMode,
    XdgPathError,
    ensure_elysia_directories,
    resolve_elysia_paths,
)


ROOT = Path(__file__).resolve().parents[1]


def _environment(tmp_path: Path, *, with_runtime: bool = True) -> dict[str, str]:
    values = {
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg" / "config"),
        "XDG_DATA_HOME": str(tmp_path / "xdg" / "data"),
        "XDG_CACHE_HOME": str(tmp_path / "xdg" / "cache"),
        "XDG_STATE_HOME": str(tmp_path / "xdg" / "state"),
        "ELYSIA_RUNTIME_MODE": "packaged",
    }
    if with_runtime:
        values["XDG_RUNTIME_DIR"] = str(tmp_path / "xdg" / "runtime")
    return values


def test_xdg_paths_are_portable_private_roots_and_never_source_tree(tmp_path: Path) -> None:
    values = _environment(tmp_path)
    paths = resolve_elysia_paths(values)

    assert paths.mode == RuntimeMode.PACKAGED
    assert paths.config_dir == tmp_path / "xdg" / "config" / "elysia"
    assert paths.data_dir == tmp_path / "xdg" / "data" / "elysia"
    assert paths.cache_dir == tmp_path / "xdg" / "cache" / "elysia"
    assert paths.state_dir == tmp_path / "xdg" / "state" / "elysia"
    assert paths.runtime_dir == tmp_path / "xdg" / "runtime" / "elysia"
    assert paths.runtime_fallback_used is False
    summary = json.dumps(paths.public_summary())
    assert str(tmp_path) not in summary
    assert summary.count("XDG") >= 5
    assert paths.data_dir != ROOT / "data"

    created = ensure_elysia_directories(paths)
    assert set(created) == {"config", "data", "cache", "state", "runtime"}
    for directory in (
        paths.config_dir,
        paths.data_dir,
        paths.cache_dir,
        paths.state_dir,
        paths.runtime_dir,
    ):
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o077 == 0


def test_xdg_runtime_fallback_and_invalid_relative_override(tmp_path: Path) -> None:
    values = _environment(tmp_path, with_runtime=False)
    paths = resolve_elysia_paths(values)
    assert paths.runtime_fallback_used is True
    assert paths.runtime_dir == tmp_path / "xdg" / "state" / "elysia" / "runtime"

    values["XDG_CONFIG_HOME"] = "relative/config"
    with pytest.raises(XdgPathError):
        resolve_elysia_paths(values)


def test_local_api_credential_is_private_rotatable_and_not_in_summary(tmp_path: Path) -> None:
    paths = resolve_elysia_paths(_environment(tmp_path))
    first = ensure_local_api_credential(paths)
    credential_path = paths.auth_dir / "local-api.credential"
    assert len(first) >= 32
    assert credential_path.stat().st_mode & 0o077 == 0

    policy = LocalApiAuthPolicy(
        required=True,
        credential_path=credential_path,
        runtime_mode=RuntimeMode.PACKAGED,
        source="test",
    )
    assert validate_local_api_credential(policy, {"authorization": f"Bearer {first}"})
    assert not validate_local_api_credential(policy, {})
    assert not validate_local_api_credential(policy, {"authorization": "Bearer wrong"})
    assert first not in json.dumps(policy.public_summary())

    second = rotate_local_api_credential(paths)
    assert second != first
    assert not validate_local_api_credential(policy, {"authorization": f"Bearer {first}"})
    assert validate_local_api_credential(policy, {"authorization": f"Bearer {second}"})

    other_paths = resolve_elysia_paths(_environment(tmp_path / "other"))
    other = ensure_local_api_credential(other_paths)
    assert not validate_local_api_credential(policy, {"authorization": f"Bearer {other}"})


def test_packaged_auth_policy_cannot_be_disabled(tmp_path: Path) -> None:
    values = _environment(tmp_path)
    values["ELYSIA_API_AUTH_MODE"] = "development-disabled"
    paths = resolve_elysia_paths(values)
    with pytest.raises(Exception, match="Packaged mode cannot disable"):
        build_local_api_auth_policy(paths=paths, environ=values, initialize=False)


def test_packaged_mutations_require_auth_and_tauri_origin_is_allowlisted(tmp_path: Path) -> None:
    paths = resolve_elysia_paths(_environment(tmp_path))
    token = ensure_local_api_credential(paths)
    policy = LocalApiAuthPolicy(
        required=True,
        credential_path=paths.auth_dir / "local-api.credential",
        runtime_mode=RuntimeMode.PACKAGED,
        source="test",
    )

    async def exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=create_app(auth_policy=policy))
        async with httpx.AsyncClient(transport=transport, base_url="http://elysia.local") as client:
            read = await client.get("/install/lifecycle")
            blocked = await client.post("/install/auth/probe")
            allowed = await client.post(
                "/install/auth/probe",
                headers={"Authorization": f"Bearer {token}"},
            )
            preflight = await client.options(
                "/install/auth/probe",
                headers={
                    "Origin": "http://tauri.localhost",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            return read, blocked, allowed, preflight

    read, blocked, allowed, preflight = asyncio.run(exercise())
    assert read.status_code == 200
    assert blocked.status_code == 401
    assert blocked.json()["result_type"] == "local_client_auth_guard"
    assert token not in json.dumps(blocked.json())
    assert allowed.status_code == 200
    assert allowed.json()["data"]["credential_exposed"] is False
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://tauri.localhost"


def test_doctor_is_sanitized_non_repairing_and_records_only_allowlisted_truth(tmp_path: Path) -> None:
    values = _environment(tmp_path)
    paths = resolve_elysia_paths(values)
    ensure_elysia_directories(paths)
    policy = build_local_api_auth_policy(paths=paths, environ=values, initialize=True)
    missing = tmp_path / "missing.yaml"
    report = run_doctor(
        paths=paths,
        auth_policy=policy,
        api_reachable=True,
        probe_local_services=False,
        profile_override_path=missing,
        model_override_path=missing,
        desktop_package_state="present",
    )
    rendered = json.dumps(report.to_payload())
    assert report.local_api_reachable is True
    assert report.desktop_api_compatible is True
    assert report.core_ready is True
    assert report.local_auth["required_for_mutations"] is True
    assert report.local_auth["initialized"] is True
    assert report.worker_execution_enabled is False
    assert report.install_authority_available is False
    assert report.repair_authority_available is False
    assert report.raw_paths_exposed is False
    repo_check = next(
        check for check in report.checks if check.check_id == "codev_repo_approval"
    )
    assert repo_check.status == "optional_missing"
    assert repo_check.required is False
    assert str(tmp_path) not in repo_check.summary
    assert str(tmp_path) not in rendered
    assert "credential" not in rendered.lower() or "credential_exposed" in rendered

    record_doctor_result(report, paths=paths)
    receipt_path = paths.doctor_state_dir / "last-run.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert set(receipt) == {
        "active_profile_id",
        "core_ready",
        "doctor_version",
        "generated_at_utc",
        "overall_status",
        "raw_paths_exposed",
    }
    assert str(tmp_path) not in json.dumps(receipt)


def test_doctor_does_not_claim_core_ready_without_desktop_package_proof(tmp_path: Path) -> None:
    values = _environment(tmp_path)
    paths = resolve_elysia_paths(values)
    ensure_elysia_directories(paths)
    policy = build_local_api_auth_policy(paths=paths, environ=values, initialize=True)
    missing = tmp_path / "missing.yaml"
    report = run_doctor(
        paths=paths,
        auth_policy=policy,
        api_reachable=True,
        profile_override_path=missing,
        model_override_path=missing,
        desktop_package_state="",
    )
    desktop_check = next(
        check for check in report.checks if check.check_id == "desktop_api_contract"
    )
    assert report.core_ready is False
    assert report.desktop_api_compatible is False
    assert desktop_check.status == "unknown"


def test_doctor_reports_memory_corruption_and_backup_without_paths_or_repair(tmp_path: Path) -> None:
    values = _environment(tmp_path)
    paths = resolve_elysia_paths(values)
    ensure_elysia_directories(paths)
    repository = MemoryRepository(paths=paths)
    repository.initialize()
    repository.backup(paths.memory_backup_dir / "verified-synthetic.sqlite")
    with repository.connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for suffix in ("-wal", "-shm"):
        Path(f"{paths.memory_database_path}{suffix}").unlink(missing_ok=True)
    corruption_canary = b"CORRUPT_PRIVATE_MEMORY_CANARY"
    paths.memory_database_path.write_bytes(corruption_canary)
    policy = build_local_api_auth_policy(paths=paths, environ=values, initialize=True)
    missing = tmp_path / "missing.yaml"

    report = run_doctor(
        paths=paths,
        auth_policy=policy,
        api_reachable=True,
        profile_override_path=missing,
        model_override_path=missing,
        desktop_package_state="present",
    )
    memory_check = next(
        check for check in report.checks if check.check_id == "canonical_memory_fabric"
    )
    rendered = json.dumps(report.to_payload())
    assert memory_check.status == "missing"
    assert memory_check.required is True
    assert "backup is available" in memory_check.summary
    assert report.core_ready is False
    assert str(tmp_path) not in rendered
    assert corruption_canary.decode() not in rendered
    assert paths.memory_database_path.read_bytes() == corruption_canary


def test_doctor_and_lifecycle_routes_expose_no_private_path_or_authority(tmp_path: Path) -> None:
    paths = resolve_elysia_paths(_environment(tmp_path))
    policy = LocalApiAuthPolicy(
        required=True,
        credential_path=paths.auth_dir / "local-api.credential",
        runtime_mode=RuntimeMode.PACKAGED,
        source="test",
        expected_credential="x" * 48,
    )

    async def exercise() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=create_app(auth_policy=policy))
        async with httpx.AsyncClient(transport=transport, base_url="http://elysia.local") as client:
            return [await client.get("/status/doctor"), await client.get("/install/lifecycle")]

    for response in asyncio.run(exercise()):
        assert response.status_code == 200
        rendered = response.text
        assert str(tmp_path) not in rendered
        assert "install_authority_available\":true" not in rendered.replace(" ", "").lower()


def test_csp_and_native_lifecycle_are_local_and_fixed() -> None:
    tauri = json.loads(
        (ROOT / "apps" / "elysia-desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    csp = tauri["app"]["security"]["csp"]
    native = (ROOT / "apps" / "elysia-desktop" / "src-tauri" / "src" / "main.rs").read_text(
        encoding="utf-8"
    )
    bridge_client = (
        ROOT / "apps" / "elysia-desktop" / "src" / "api" / "bridgeClient.ts"
    ).read_text(encoding="utf-8")
    package_build = (ROOT / "scripts" / "tauri_build_linux.sh").read_text(
        encoding="utf-8"
    )
    appimage_sanitizer = (
        ROOT / "scripts" / "sanitize_appimage_bundle.sh"
    ).read_text(encoding="utf-8")
    appstream_shim = (
        ROOT / "scripts" / "packaging_bin" / "appstreamcli"
    ).read_text(encoding="utf-8")
    package_json = json.loads(
        (ROOT / "apps" / "elysia-desktop" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    assert csp and "default-src 'self'" in csp
    assert "http://127.0.0.1:8000" in csp
    assert "https://*.supabase.co" in csp
    assert "connect-src *" not in csp
    assert "default-src *" not in csp
    assert "script-src 'self'" in csp
    assert "Command::new(&self.launcher_path)" in native
    assert "packaged_runtime_path()" in native
    assert 'parent.join("elysia")' in native
    assert 'join("runtime").join("bin").join("elysia-api")' not in native
    assert "sh -c" not in native
    assert "bash -c" not in native
    assert "host Docker" not in native
    assert "unverified_listener" in native
    assert "metadata.permissions().mode() & 0o077" in native
    assert "process.try_wait()" in native
    assert "command.process_group(0)" in native
    assert "libc::killpg(process.id() as i32, libc::SIGTERM)" in native
    assert "tauri::WindowEvent::CloseRequested" in native
    assert "rawResponse" not in bridge_client
    assert "--remap-path-prefix=${HOME}=/build/user" in package_build
    assert "CARGO_ENCODED_RUSTFLAGS" in package_build
    assert "/home/private-operator" not in package_build
    assert "sanitize_appimage_bundle.sh" in package_build
    assert "generate_appimage_native_notices.py" in package_build
    assert "validate_desktop_csp_assets.py" in package_build
    assert "normalize_deb_bundle.py" in package_build
    assert "The AppImage native notice payload is stale" in package_build
    assert 'export PATH="$APPSTREAM_SHIM_DIR:$PATH"' in package_build
    assert 'package_build_tools.py" prepare-runtime' in package_build
    assert 'export LDAI_RUNTIME_FILE="$APPIMAGE_RUNTIME_FILE"' in package_build
    assert 'export ELYSIA_APPIMAGE_RUNTIME_FILE="$APPIMAGE_RUNTIME_FILE"' in package_build
    assert "private build-path marker" in appimage_sanitizer
    assert "sanitize_appimage_hook.py" in appimage_sanitizer
    assert 'root = Path(sys.argv[1]).parents[1]' in appimage_sanitizer
    assert "sanitize_appimage_root.py" in appimage_sanitizer
    assert "normalize_appimage_metadata.py" in appimage_sanitizer
    assert "write_appimage_sort_file.py" in appimage_sanitizer
    assert "--mksquashfs-opt=-sort" in appimage_sanitizer
    assert "--mksquashfs-opt=-no-xattrs" in appimage_sanitizer
    assert 'package_build_tools.py" prepare-runtime' in appimage_sanitizer
    assert '--runtime-file "$RUNTIME_FILE"' in appimage_sanitizer
    assert "THIRD_PARTY_NOTICES.native.txt" in appimage_sanitizer
    assert 'cmp -s -- "$TAURI_ALIAS" "$CANONICAL"' in appstream_shim
    assert "validate-tree --no-net" in appstream_shim
    assert "restore_alias" in appstream_shim
    assert package_json["scripts"]["tauri:build:linux"] == "../../scripts/tauri_build_linux.sh"
    assert tauri["bundle"]["externalBin"] == ["binaries/elysia"]
    assert tauri["bundle"]["license"] == "Apache-2.0"
    assert tauri["bundle"]["resources"] == {
        "../../../LICENSE": "LICENSE",
        "../../../LICENSES": "LICENSES",
        "../../../LICENSING.md": "LICENSING.md",
        "../../../NOTICE": "NOTICE",
        "../../../THIRD_PARTY_NOTICES.md": "THIRD_PARTY_NOTICES.md",
        "../../../MODEL_ASSET_NOTICES.md": "MODEL_ASSET_NOTICES.md",
        "../../../TRADEMARKS.md": "TRADEMARKS.md",
        "../THIRD_PARTY_NOTICES.txt": "THIRD_PARTY_NOTICES.desktop.txt",
        "../THIRD_PARTY_NOTICES.native.txt": "THIRD_PARTY_NOTICES.native.txt",
        "../../../scripts/manage_qdrant.sh": "scripts/manage_qdrant.sh",
        "../../../scripts/manage_neurofabric.sh": "scripts/manage_neurofabric.sh",
        "../../../scripts/manage_searxng.sh": "scripts/manage_searxng.sh",
        "../../../scripts/prove_neurofabric_runtime.py": "scripts/prove_neurofabric_runtime.py",
        "../../../requirements/neurofabric-cpu.txt": "requirements/neurofabric-cpu.txt",
        "../../../requirements/neurofabric-cuda.txt": "requirements/neurofabric-cuda.txt",
        "../../../requirements/THIRD_PARTY_NOTICES.txt": "requirements/THIRD_PARTY_NOTICES.txt",
        "../../../config/install": "config/install",
        "../../../docs/release/CODEV_DEVELOPER_PROFILE_INSTALL.md": "docs/CODEV_DEVELOPER_PROFILE_INSTALL.md",
        "../../../docs/release/DEPENDENCY_ACQUISITION_AND_MANUAL_ACTIONS.md": "docs/DEPENDENCY_ACQUISITION_AND_MANUAL_ACTIONS.md",
        "../../../docs/release/INSTALLER_DOCTOR_RUNTIME.md": "docs/INSTALLER_DOCTOR_RUNTIME.md",
        "../../../docs/release/INSTALL_PROFILES.md": "docs/INSTALL_PROFILES.md",
        "../../../docs/release/SYSTEM_REQUIREMENTS_v1.0.0.md": "docs/SYSTEM_REQUIREMENTS_v1.0.0.md",
    }
    native_notices = ROOT / "apps" / "elysia-desktop" / "THIRD_PARTY_NOTICES.native.txt"
    assert native_notices.stat().st_size > 1_000_000
    assert "Elysia AppImage native-library notices" in native_notices.read_text(encoding="utf-8")
    assert (ROOT / "scripts" / "generate_appimage_native_notices.py").is_file()
    assert tauri["bundle"]["linux"]["appimage"]["files"] == {
        "/elysia-desktop.png": "icons/128x128@2x.png",
        "/usr/share/metainfo/llc.ecosyneva.elysia.metainfo.xml": "linux/llc.ecosyneva.elysia.metainfo.xml",
    }
    assert tauri["bundle"]["linux"]["deb"]["files"] == {
        "/usr/share/metainfo/llc.ecosyneva.elysia.metainfo.xml": "linux/llc.ecosyneva.elysia.metainfo.xml"
    }
    appstream = (
        ROOT
        / "apps"
        / "elysia-desktop"
        / "src-tauri"
        / "linux"
        / "llc.ecosyneva.elysia.metainfo.xml"
    ).read_text(encoding="utf-8")
    assert "<id>llc.ecosyneva.elysia</id>" in appstream
    assert "<launchable type=\"desktop-id\">Elysia.desktop</launchable>" in appstream


def test_release_installer_builds_self_contained_core_before_tauri() -> None:
    build = (ROOT / "scripts" / "build_packaged_core_runtime.sh").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "scripts" / "build_elysia_desktop_installer.sh").read_text(
        encoding="utf-8"
    )
    package_build = (ROOT / "scripts" / "tauri_build_linux.sh").read_text(
        encoding="utf-8"
    )
    entrypoint = (ROOT / "packaging" / "elysia_cli.py").read_text(encoding="utf-8")

    assert '"$ROOT_DIR/scripts/build_packaged_core_runtime.sh"' in package_build
    assert "run tauri:build:linux" in installer
    assert "--onefile" in build
    assert "--exclude-module psutil" in build
    assert "--copy-metadata" in build
    assert "--hidden-import" in build
    assert '--add-data "$ROOT_DIR/skills:skills"' in build
    assert '--add-data "$ROOT_DIR/packaging/core_runtime_prompts:derived/runtime"' in build
    assert "--add-binary \"$PACKAGED_LIBEXPAT:elysia-native\"" in build
    assert "pyi_rth_elysia_native.py" in build
    assert "verify_packaged_core_routes.py" in build
    assert "env -u PYTHONPATH" in build
    assert "PYTHONHASHSEED=0" in build
    assert "for marker in (sys.argv[2], sys.argv[3])" in build
    assert "for marker in (sys.argv[2], sys.argv[3]):" in build
    assert "serve" in entrypoint
    assert "doctor" in entrypoint
    assert "subprocess" not in entrypoint
    assert "os.system" not in entrypoint


def test_core_payload_and_python_selection_contract_are_explicit() -> None:
    installer = (ROOT / "scripts" / "install_core.sh").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts" / "elysia-api").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify_install.sh").read_text(encoding="utf-8")

    assert "--python ABSOLUTE_PATH" in installer
    assert "app core config derived skills" in installer
    assert "sandbox/command_worker" in installer
    assert "sandbox/searxng_worker" in installer
    assert "config/system/machine_profile.yaml" in installer
    assert "config/workers/*forge_worker.yaml" in installer
    assert "config/models/imageforge_models.yaml" in installer
    assert "python-interpreter" in installer
    assert "python-interpreter" in launcher
    assert "python-interpreter" in verifier
    assert "sudo" not in installer
    assert "curl" not in installer
    assert "wget" not in installer


def test_source_desktop_launcher_refuses_unverified_python_environments() -> None:
    launcher = (ROOT / "launch_elysia_dev.sh").read_text(encoding="utf-8")

    assert "python_command_is_ready" in launcher
    assert "ELYSIA_DEV_PYTHON" in launcher
    assert "ELYSIA_DEV_CONDA_ENV" in launcher
    assert "ELYSIA_DEV_PREFLIGHT_ONLY" in launcher
    assert "python-interpreter" in launcher
    assert "import fastapi, pydantic, uvicorn, yaml" in launcher
    assert '"${PYTHON_CMD[@]}" -m app.cli.runtime serve' in launcher


def test_core_install_and_uninstall_default_to_non_mutating_dry_run(tmp_path: Path) -> None:
    environment = {**os.environ, **_environment(tmp_path)}
    install = subprocess.run(
        ["bash", "scripts/install_core.sh"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    uninstall = subprocess.run(
        ["bash", "scripts/uninstall_core.sh"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0
    assert uninstall.returncode == 0
    assert "no files were changed" in install.stdout.lower()
    assert "no files were changed" in uninstall.stdout.lower()
    assert not (tmp_path / "xdg").exists()
