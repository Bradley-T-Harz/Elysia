from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from app.install.paths import ElysiaPaths, RuntimeMode
from app.install.system_prerequisite_service import (
    SystemPrerequisiteApplyRequest,
    SystemPrerequisiteError,
    SystemPrerequisitePreviewRequest,
    SystemPrerequisiteService,
    _load_manifest,
)


def _paths(root: Path) -> ElysiaPaths:
    return ElysiaPaths(
        mode=RuntimeMode.TEST,
        config_dir=root / "config" / "elysia",
        data_dir=root / "data" / "elysia",
        cache_dir=root / "cache" / "elysia",
        state_dir=root / "state" / "elysia",
        runtime_dir=root / "runtime" / "elysia",
        runtime_fallback_used=False,
    )


def test_manifest_covers_every_graph_system_dependency() -> None:
    payload = _load_manifest()
    assert payload["rules"]["silent_sudo"] is False
    assert payload["rules"]["exact_package_version_preview"] is True
    assert payload["rules"]["full_setup_runs_as_root"] is False


def test_rootless_podman_dependencies_survive_no_recommends_install() -> None:
    payload = _load_manifest()
    required = {"podman", "skopeo", "uidmap", "slirp4netns", "fuse-overlayfs"}
    for dependency_id in (
        "rootless_podman_or_bounded_docker",
        "rootless_sandbox",
    ):
        dependency = payload["dependencies"][dependency_id]
        assert dependency["kind"] == "apt"
        assert set(dependency["packages"]) == required


def test_prerequisite_preview_is_exact_and_apply_uses_only_pkexec_apt(
    tmp_path: Path, monkeypatch,
) -> None:
    versions = {"libc6": None, "libexpat1": "1", "sqlite3": "1", "libcairo2": "1", "libpango-1.0-0": "1"}
    monkeypatch.setattr(
        "app.install.system_prerequisite_service._installed_version",
        lambda package: versions.get(package),
    )
    monkeypatch.setattr(
        "app.install.system_prerequisite_service._candidate_version",
        lambda package: "2.39-0ubuntu8.6" if package == "libc6" else None,
    )
    monkeypatch.setattr(
        "app.install.system_prerequisite_service.shutil.which",
        lambda command: f"/usr/bin/{command}" if command in {"pkexec", "apt-get"} else None,
    )
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        versions["libc6"] = "2.39-0ubuntu8.6"
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.install.system_prerequisite_service.subprocess.run", run)
    service = SystemPrerequisiteService(_paths(tmp_path))
    preview = service.preview(SystemPrerequisitePreviewRequest(
        component_ids=["core_python_runtime"],
    ))
    assert preview["exact_package_operations"] == ["libc6=2.39-0ubuntu8.6"]
    assert preview["silent_sudo"] is False
    with pytest.raises(SystemPrerequisiteError):
        service.apply(SystemPrerequisiteApplyRequest(
            preview_id=preview["preview_id"], approval_token="x" * 32,
            operator_approved=True,
        ))
    applied = service.apply(SystemPrerequisiteApplyRequest(
        preview_id=preview["preview_id"], approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    assert commands == [[
        "/usr/bin/pkexec", "/usr/bin/apt-get", "install",
        "--no-install-recommends", "--yes", "libc6=2.39-0ubuntu8.6",
    ]]
    assert applied["receipt_written"] is True
    receipt = json.loads(service.receipt_path.read_text(encoding="utf-8"))
    assert receipt["exact_package_operations"] == ["libc6=2.39-0ubuntu8.6"]
    assert service.receipt_path.stat().st_mode & 0o077 == 0


def test_prerequisite_preview_rejects_unknown_component(tmp_path: Path) -> None:
    with pytest.raises(SystemPrerequisiteError, match="unknown component"):
        SystemPrerequisiteService(_paths(tmp_path)).preview(
            SystemPrerequisitePreviewRequest(component_ids=["not_real"])
        )


def test_external_prerequisite_exposes_complete_user_guidance(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.install.system_prerequisite_service._installed_version",
        lambda _package: "1",
    )
    monkeypatch.setattr(
        "app.install.system_prerequisite_service.shutil.which",
        lambda _command: None,
    )
    preview = SystemPrerequisiteService(_paths(tmp_path)).inspect(
        ["codev_companion"]
    )
    assert preview["external_missing_dependency_ids"] == ["vscode"]
    assert preview["external_missing_guidance"] == [
        {
            "dependency_id": "vscode",
            "setup_category": "E",
            "title": "VS Code-family Extension Host",
            "why": preview["external_missing_guidance"][0]["why"],
            "official_source": "https://code.visualstudio.com/docs/setup/linux",
            "signup_required": (
                "No account is required for a local editor or local VSIX "
                "installation."
            ),
            "data_leaving_local_control": preview["external_missing_guidance"][0]["data_leaving_local_control"],
            "license_privacy_security": preview["external_missing_guidance"][0]["license_privacy_security"],
            "supported_steps": preview["external_missing_guidance"][0]["supported_steps"],
            "doctor_detection": preview["external_missing_guidance"][0]["doctor_detection"],
            "retry_repair": preview["external_missing_guidance"][0]["retry_repair"],
        }
    ]
    assert len(preview["external_missing_guidance"][0]["supported_steps"]) == 4
