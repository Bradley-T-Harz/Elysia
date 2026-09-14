from pathlib import Path

import pytest

from app.install.platform_service import core_platform_supported, operating_system
from app.install.setup_service import SetupPreviewRequest, SetupService
from app.install.hardware_service import detect_local_hardware
from app.install.paths import resolve_elysia_paths


@pytest.mark.parametrize("distribution,version,expected", [
    ("debian", "13", True), ("debian", "13.6", True), ("ubuntu", "24.04", True),
    ("debian", "12", False), ("ubuntu", "22.04", False), ("ubuntu", "24.040", False),
    ("fedora", "44", False),
])
def test_native_platform_scope_is_explicit(distribution, version, expected):
    assert core_platform_supported({"id": distribution, "version_id": version}) is expected


def test_os_release_is_read_as_data_and_never_executed(tmp_path):
    marker = tmp_path / "must-not-exist"
    source = tmp_path / "os-release"
    source.write_text(f'ID=debian\nVERSION_ID="13"\nNAME="$(touch {marker})"\n')
    assert operating_system(source) == {"id": "debian", "version_id": "13"}
    assert not marker.exists()


def test_debian_core_preview_does_not_qualify_other_optional_profiles(monkeypatch, tmp_path):
    hardware = detect_local_hardware()
    hardware.update(supported_ubuntu=False, supported_core_platform=True,
                    operating_system={"id": "debian", "version_id": "13"})
    monkeypatch.setattr("app.install.setup_service.detect_local_hardware", lambda: hardware)
    service = SetupService(resolve_elysia_paths())
    install_root = tmp_path / "ordinary install"
    install_root.mkdir()
    core = service.preview(SetupPreviewRequest(profile_id="core", distribution_form="source", install_root=str(install_root)))
    assert core["ready_to_apply"]
    optional = service.preview(SetupPreviewRequest(profile_id="creator_perception", distribution_form="source", install_root=str(install_root)))
    assert not optional["ready_to_apply"]
    assert any("not been qualified on Debian" in reason for reason in optional["blockers"])
