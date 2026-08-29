from __future__ import annotations

import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

import pytest

from app.install.codev_installer import (
    CodevInstallError,
    inspect_codev_vsix,
    install_codev_vsix,
)
from app.install.paths import RuntimeMode, resolve_elysia_paths


def _vsix(path: Path, *, extra_name: str | None = None) -> Path:
    manifest = {
        "name": "elysia-codev",
        "publisher": "ecosyneva-commons",
        "version": "1.0.0",
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("extension/package.json", json.dumps(manifest))
        archive.writestr("extension/out/src/extension.js", "exports.activate = () => {};\n")
        if extra_name:
            archive.writestr(extra_name, "bounded test\n")
    return path


def test_packaged_codev_installer_validates_exact_local_archive(tmp_path: Path) -> None:
    target = _vsix(tmp_path / "elysia-codev-1.0.0.vsix")
    result = inspect_codev_vsix(target)
    assert result.extension_id == "ecosyneva-commons.elysia-codev"
    assert result.version == "1.0.0"
    assert result.entry_count == 2
    assert len(result.sha256) == 64


@pytest.mark.parametrize(
    "unsafe_name",
    ("../outside.txt", "extension/.env", "extension/private.key"),
)
def test_packaged_codev_installer_refuses_unsafe_members(tmp_path: Path, unsafe_name: str) -> None:
    target = _vsix(tmp_path / "unsafe.vsix", extra_name=unsafe_name)
    with pytest.raises(CodevInstallError):
        inspect_codev_vsix(target)


def test_packaged_codev_installer_invokes_fixed_editor_and_writes_private_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _vsix(tmp_path / "elysia-codev-1.0.0.vsix")
    editor = tmp_path / "code"
    editor.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    editor.chmod(0o700)
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        assert kwargs["shell"] is False
        assert kwargs["stdin"] is subprocess.DEVNULL
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("app.install.codev_installer.subprocess.run", fake_run)
    paths = resolve_elysia_paths(
        environ={}, home=tmp_path / "home", mode=RuntimeMode.TEST
    )
    result = install_codev_vsix(
        target,
        editor=str(editor),
        select_profile=True,
        paths=paths,
    )
    assert calls == [[str(editor), "--install-extension", str(target), "--force"]]
    assert result.public_summary()["raw_paths_exposed"] is False
    receipt = paths.data_dir / "developer" / "codev-install.json"
    profile = paths.config_dir / "install" / "profiles.yaml"
    assert json.loads(receipt.read_text(encoding="utf-8"))["package_sha256"] == result.package.sha256
    assert receipt.stat().st_mode & 0o077 == 0
    assert profile.stat().st_mode & 0o077 == 0
    assert "active_profile: developer" in profile.read_text(encoding="utf-8")


def test_explicit_codev_profile_selection_replaces_core_and_preserves_non_core_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _vsix(tmp_path / "elysia-codev-1.0.0.vsix")
    editor = tmp_path / "code"
    editor.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    editor.chmod(0o700)
    monkeypatch.setattr(
        "app.install.codev_installer.subprocess.run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    paths = resolve_elysia_paths(
        environ={}, home=tmp_path / "home", mode=RuntimeMode.TEST
    )
    profile = paths.config_dir / "install" / "profiles.yaml"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        "version: 1\n"
        "contract_version: elysia-local-profile-selection-1.0\n"
        "active_profile: core\n"
        "additional_profiles:\n"
        "  - workstation\n",
        encoding="utf-8",
    )

    result = install_codev_vsix(
        target,
        editor=str(editor),
        select_profile=True,
        paths=paths,
    )

    selected = profile.read_text(encoding="utf-8")
    assert result.profile_selected is True
    assert result.existing_profile_preserved is True
    assert "active_profile: developer" in selected
    assert "- workstation" in selected
    assert "- core" not in selected


def test_invalid_existing_profile_is_refused_before_editor_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _vsix(tmp_path / "elysia-codev-1.0.0.vsix")
    editor = tmp_path / "code"
    editor.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    editor.chmod(0o700)
    paths = resolve_elysia_paths(
        environ={}, home=tmp_path / "home", mode=RuntimeMode.TEST
    )
    profile = paths.config_dir / "install" / "profiles.yaml"
    profile.parent.mkdir(parents=True)
    profile.write_text("version: 99\nactive_profile: unknown\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("app.install.codev_installer.subprocess.run", fake_run)
    with pytest.raises(CodevInstallError):
        install_codev_vsix(
            target,
            editor=str(editor),
            select_profile=True,
            paths=paths,
        )
    assert calls == []


def test_packaged_cli_exposes_only_bounded_codev_install_arguments() -> None:
    source = (Path(__file__).resolve().parents[1] / "packaging" / "elysia_cli.py").read_text(encoding="utf-8")
    assert '"codev-install"' in source
    assert 'codev_install.add_argument("--vsix", required=True)' in source
    assert 'codev_install.add_argument("--select-profile", action="store_true")' in source
    assert "shell" in source
    assert "command" in source
