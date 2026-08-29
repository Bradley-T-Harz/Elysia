from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_desktop_user.sh"
UNINSTALLER = ROOT / "scripts" / "uninstall_desktop_user.sh"


def _make_deb(tmp_path: Path, marker: str) -> Path:
    if shutil.which("dpkg-deb") is None:
        pytest.skip("dpkg-deb is unavailable")
    package = tmp_path / f"package-{marker}"
    (package / "DEBIAN").mkdir(parents=True)
    (package / "usr/bin").mkdir(parents=True)
    icon_root = package / "usr/share/icons/hicolor/128x128/apps"
    icon_root.mkdir(parents=True)
    (package / "DEBIAN/control").write_text(
        "Package: elysia-test\nVersion: 0.1.0\nArchitecture: amd64\nMaintainer: Test\nDescription: synthetic launcher fixture\n",
        encoding="utf-8",
    )
    for binary in ("elysia", "elysia-desktop"):
        target = package / "usr/bin" / binary
        target.write_text(f"#!/bin/sh\necho {marker}\n", encoding="utf-8")
        target.chmod(0o755)
    (icon_root / "elysia-desktop.png").write_bytes(f"icon-{marker}".encode())
    artifact = tmp_path / f"elysia-{marker}.deb"
    subprocess.run(
        ["dpkg-deb", "--build", str(package), str(artifact)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return artifact


def _install(tmp_path: Path, artifact: Path) -> tuple[Path, list[Path]]:
    home = tmp_path / "home"
    mega = home / "MEGA (Elysia)" / "Desktop"
    desktop = home / "Desktop"
    convenience = home / "Projects" / "Elysia_App"
    environment = {
        **os.environ,
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
    }
    subprocess.run(
        [
            "bash",
            str(INSTALLER),
            "--apply",
            "--deb",
            str(artifact),
            "--shortcut-dir",
            str(mega),
            "--shortcut-dir",
            str(desktop),
            "--shortcut-dir",
            str(convenience),
        ],
        check=True,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    entries = [
        home / ".local/share/applications/Elysia.desktop",
        mega / "Elysia.desktop",
        desktop / "Elysia.desktop",
        convenience / "Elysia.desktop",
    ]
    return home, entries


def _environment(home: Path) -> dict[str, str]:
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
    }


def test_user_local_installer_converges_every_entry_and_preserves_prior_release(
    tmp_path: Path,
) -> None:
    first = _make_deb(tmp_path, "first")
    home, entries = _install(tmp_path, first)
    stable_launcher = home / ".local/bin/elysia-desktop"
    expected_exec = f"Exec={stable_launcher}"

    assert stable_launcher.stat().st_mode & 0o777 == 0o700
    assert "elysia/current/usr/bin/elysia-desktop" in stable_launcher.read_text(
        encoding="utf-8"
    )
    assert "ELYSIA_LOCAL_API_PORT" in stable_launcher.read_text(encoding="utf-8")
    for entry in entries:
        assert entry.is_file()
        assert expected_exec in entry.read_text(encoding="utf-8")
        assert "elysia-package-" not in entry.read_text(encoding="utf-8")
    assert sorted((home / ".local/share/applications").glob("*.desktop")) == [
        entries[0]
    ]
    assert list((home / ".local/state/elysia").glob("generated-desktop-entry-*.desktop"))

    first_target = (home / ".local/lib/elysia/current").resolve()
    assert (first_target / "usr/bin/elysia-desktop").is_file()

    second = _make_deb(tmp_path, "second")
    _, second_entries = _install(tmp_path, second)
    second_target = (home / ".local/lib/elysia/current").resolve()

    assert second_target != first_target
    assert first_target.is_dir()
    assert second_target.is_dir()
    assert entries == second_entries
    for entry in entries:
        assert expected_exec in entry.read_text(encoding="utf-8")


def test_user_local_launcher_source_is_portable_and_fail_closed() -> None:
    source = INSTALLER.read_text(encoding="utf-8")
    assert "MAIN" + "_Projects" not in source
    assert "MEGA (Elysia)" not in source
    assert "/ho" + "me/" not in source
    assert "current/usr/bin/elysia-desktop" in source
    assert "-u ELYSIA_LOCAL_API_PORT" in source
    assert "user_data_preserved\":true" in source


def test_user_local_repair_rollback_uninstall_and_reinstall_preserve_xdg_data(
    tmp_path: Path,
) -> None:
    first = _make_deb(tmp_path, "first")
    second = _make_deb(tmp_path, "second")
    home, _ = _install(tmp_path, first)
    environment = _environment(home)
    first_id = sha256(first.read_bytes()).hexdigest()[:12]
    first_payload = home / ".local/lib/elysia/releases" / first_id
    (first_payload / "usr/bin/elysia-desktop").write_text("corrupt", encoding="utf-8")
    _install(tmp_path, first)
    assert "echo first" in (first_payload / "usr/bin/elysia-desktop").read_text(encoding="utf-8")
    assert list((home / ".local/state/elysia/recoverable-desktop-payloads").glob(f"{first_id}-*"))

    _install(tmp_path, second)
    subprocess.run(
        ["bash", str(INSTALLER), "--apply", "--rollback-release", first_id],
        check=True, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert (home / ".local/lib/elysia/current").resolve() == first_payload.resolve()

    private_data = home / ".local/share/elysia/memory/private-proof"
    private_data.parent.mkdir(parents=True, exist_ok=True)
    private_data.write_text("preserve-me", encoding="utf-8")
    subprocess.run(
        ["bash", str(UNINSTALLER), "--apply"],
        check=True, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert not (home / ".local/lib/elysia").exists()
    assert not (home / ".local/bin/elysia-desktop").exists()
    assert private_data.read_text(encoding="utf-8") == "preserve-me"
    assert list((home / ".local/state/elysia/uninstalled-desktop").iterdir())

    _install(tmp_path, second)
    assert (home / ".local/bin/elysia-desktop").is_file()
    assert private_data.read_text(encoding="utf-8") == "preserve-me"
