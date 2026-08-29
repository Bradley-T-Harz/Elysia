from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from app.install.hardware_service import detect_local_hardware
from app.install.paths import ElysiaPaths, RuntimeMode
from app.install.setup_service import (
    SetupApplyRequest,
    SetupError,
    SetupPreviewRequest,
    SetupService,
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


def test_core_setup_preview_and_apply_are_exact_private_and_transactional(tmp_path: Path) -> None:
    custom_root = tmp_path / "Install Roots" / "Elysia Ω"
    custom_root.mkdir(parents=True)
    service = SetupService(_paths(tmp_path / "xdg"))
    preview = service.preview(
        SetupPreviewRequest(
            profile_id="core",
            distribution_form="onefile_core",
            install_root=str(custom_root),
            internet_available=False,
        )
    )
    assert preview["ready_to_apply"] is True
    assert preview["path_truth"]["contains_spaces"] is True
    assert preview["path_truth"]["contains_unicode"] is True
    assert preview["path_truth"]["raw_path_exposed"] is False
    assert preview["network_preview"]["personal_data_egress"] is False
    assert preview["privilege_preview"]["silent_sudo"] is False
    assert preview["dependency_install_dispositions"]["contract_version"] == (
        "elysia-dependency-install-dispositions-1.0"
    )
    assert preview["dependency_install_dispositions"]["dependency_count"] == 14
    assert preview["dependency_install_dispositions"]["category_counts"] == {
        "A": 14,
        "B": 0,
        "C": 0,
        "D": 0,
        "E": 0,
    }
    assert preview["dependency_install_dispositions"]["category_e_actions"] == []
    assert preview["dependency_install_dispositions"]["system_dependency_count"] == 9
    assert preview["dependency_install_dispositions"]["system_category_counts"] == {
        "A": 0,
        "B": 0,
        "C": 9,
        "D": 0,
        "E": 0,
    }
    assert service.state()["configured"] is False

    with pytest.raises(SetupError):
        service.apply(
            SetupApplyRequest(
                preview_id=preview["preview_id"],
                approval_token="x" * 32,
                operator_approved=True,
            )
        )
    applied = service.apply(
        SetupApplyRequest(
            preview_id=preview["preview_id"],
            approval_token=preview["approval_token"],
            operator_approved=True,
        )
    )
    assert applied["configured"] is True
    assert applied["machine_ready"] is False
    assert applied["status"] == "doctor_pending"
    assert applied["doctor_required"] is True
    assert applied["profile_id"] == "core"
    profile = yaml.safe_load(service.profile_override_path.read_text(encoding="utf-8"))
    assert profile["active_profile"] == "core"
    assert profile["additional_profiles"] == []
    assert service.profile_override_path.stat().st_mode & 0o077 == 0
    assert service.receipt_path.stat().st_mode & 0o077 == 0
    receipt = json.loads(service.receipt_path.read_text(encoding="utf-8"))
    assert receipt["install_root"] == str(custom_root.resolve())
    assert receipt["install_root_sha256"] == preview["path_truth"]["path_hash"]
    assert receipt["personal_onboarding_started"] is False

    from app.install.component_install_service import ComponentInstallService
    component_service = ComponentInstallService(service.paths)
    assert component_service.component_root == custom_root.resolve() / "components"
    assert str(custom_root) not in json.dumps(service.state())


def test_setup_requires_and_records_final_selected_profile_doctor(
    tmp_path: Path, monkeypatch,
) -> None:
    service = SetupService(_paths(tmp_path / "xdg"))
    target = tmp_path / "target"
    target.mkdir()
    preview = service.preview(SetupPreviewRequest(
        profile_id="core",
        distribution_form="onefile_core",
        install_root=str(target),
    ))
    service.apply(SetupApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    report = SimpleNamespace(
        doctor_version="1",
        active_profile_id="core",
        checks=[],
    )
    monkeypatch.setattr("app.install.setup_service.run_doctor", lambda **_kwargs: report)
    monkeypatch.setattr("app.install.setup_service.record_doctor_result", lambda *_args, **_kwargs: None)
    closed = service.run_final_doctor()
    assert closed["doctor_passed"] is True
    assert closed["machine_ready"] is True
    assert closed["status"] == "ready"
    assert service.doctor_receipt_path.stat().st_mode & 0o077 == 0


def test_setup_doctor_blocks_required_missing_check(tmp_path: Path, monkeypatch) -> None:
    service = SetupService(_paths(tmp_path / "xdg"))
    target = tmp_path / "target"
    target.mkdir()
    preview = service.preview(SetupPreviewRequest(
        profile_id="core",
        distribution_form="source",
        install_root=str(target),
    ))
    service.apply(SetupApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    report = SimpleNamespace(
        doctor_version="1",
        active_profile_id="core",
        checks=[SimpleNamespace(
            check_id="core_failure", required=True,
            status="missing", summary="Core is absent.",
        )],
    )
    monkeypatch.setattr("app.install.setup_service.run_doctor", lambda **_kwargs: report)
    monkeypatch.setattr("app.install.setup_service.record_doctor_result", lambda *_args, **_kwargs: None)
    with pytest.raises(SetupError, match="core_failure"):
        service.run_final_doctor()
    assert service.state()["doctor_passed"] is False


def test_setup_rejects_broad_relative_targets_and_separates_acquisition_approval(tmp_path: Path) -> None:
    service = SetupService(_paths(tmp_path / "xdg"))
    with pytest.raises(SetupError):
        service.preview(SetupPreviewRequest(profile_id="core", distribution_form="source", install_root="relative"))
    with pytest.raises(SetupError):
        service.preview(SetupPreviewRequest(profile_id="custom", distribution_form="source", install_root="/", custom_components=[]))
    target = tmp_path / "target"
    target.mkdir()
    scientific = service.preview(
        SetupPreviewRequest(
            profile_id="scientific_engineering_mega",
            distribution_form="source",
            install_root=str(target),
            internet_available=True,
        )
    )
    assert scientific["ready_to_apply"] is True
    assert "scientific_engineering" in scientific["unresolved_acquisition_component_ids"]
    configured = service.apply(
        SetupApplyRequest(
            preview_id=scientific["preview_id"],
            approval_token=scientific["approval_token"],
            operator_approved=True,
        )
    )
    assert configured["status"] == "components_pending"
    assert "scientific_engineering" in configured["pending_component_ids"]
    assert configured["setup_required"] is False  # TEST mode does not enforce the packaged gate.


def test_setup_blocks_low_disk_and_rechecks_target_safety_at_apply(
    tmp_path: Path, monkeypatch,
) -> None:
    service = SetupService(_paths(tmp_path / "xdg"))
    target = tmp_path / "target"
    target.mkdir()
    real_statvfs = __import__("os").statvfs
    monkeypatch.setattr(
        "app.install.setup_service.os.statvfs",
        lambda _path: SimpleNamespace(f_flag=0, f_bavail=1, f_frsize=1),
    )
    low_disk = service.preview(SetupPreviewRequest(
        profile_id="core", distribution_form="onefile_core", install_root=str(target),
    ))
    assert low_disk["ready_to_apply"] is False
    assert any("lifecycle free-space reserve" in item for item in low_disk["blockers"])

    monkeypatch.setattr("app.install.setup_service.os.statvfs", real_statvfs)
    preview = service.preview(SetupPreviewRequest(
        profile_id="core", distribution_form="onefile_core", install_root=str(target),
    ))
    monkeypatch.setattr("app.install.setup_service.os.access", lambda *_args: False)
    with pytest.raises(SetupError, match="no longer safely writable"):
        service.apply(SetupApplyRequest(
            preview_id=preview["preview_id"],
            approval_token=preview["approval_token"],
            operator_approved=True,
        ))


def test_packaged_setup_binds_receipt_to_detected_distribution_form(
    tmp_path: Path, monkeypatch,
) -> None:
    paths = _paths(tmp_path / "xdg")
    paths = ElysiaPaths(
        mode=RuntimeMode.PACKAGED,
        config_dir=paths.config_dir,
        data_dir=paths.data_dir,
        cache_dir=paths.cache_dir,
        state_dir=paths.state_dir,
        runtime_dir=paths.runtime_dir,
        runtime_fallback_used=False,
    )
    monkeypatch.setenv("ELYSIA_DISTRIBUTION_FORM", "appimage")
    service = SetupService(paths)
    state = service.state()
    assert state["detected_distribution_form"] == "appimage"
    assert state["distribution_form_locked"] is True
    with pytest.raises(SetupError, match="does not match the running"):
        service.preview(SetupPreviewRequest(
            profile_id="core", distribution_form="deb",
        ))
    preview = service.preview(SetupPreviewRequest(
        profile_id="core", distribution_form="appimage",
    ))
    assert preview["distribution_form"] == "appimage"


def test_hardware_decision_selects_cpu_or_supported_cuda_without_fingerprinting(monkeypatch) -> None:
    monkeypatch.setattr("app.install.hardware_service.shutil.which", lambda name: "/usr/bin/nvidia-smi")

    def supported(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, "NVIDIA RTX 4090, 580.82, 24564\n", "")

    result = detect_local_hardware(command_runner=supported)
    assert result["neurofabric_variant"] == "cuda_mega"
    assert result["gpu"]["cuda_variant_supported"] is True
    assert result["external_fingerprinting"] is False
    assert result["serial_numbers_returned"] is False

    def unsupported(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, "NVIDIA GPU, 570.1, 8192\n", "")

    result = detect_local_hardware(command_runner=unsupported)
    assert result["neurofabric_variant"] == "cpu"
    assert result["gpu"]["status"] == "unsupported_driver"

    def low_vram(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, "NVIDIA RTX 4060, 580.82, 4096\n", "")

    result = detect_local_hardware(command_runner=low_vram)
    assert result["neurofabric_variant"] == "cpu"
    assert result["gpu"]["status"] == "insufficient_vram"
    assert result["minimum_cuda_vram_mb"] == 8192


def test_hardware_decision_fails_closed_below_scientific_cpu_baseline(
    tmp_path: Path,
) -> None:
    unsupported = tmp_path / "cpuinfo-unsupported"
    unsupported.write_text("processor: 0\nflags: fpu sse sse2 pni\n", encoding="utf-8")
    result = detect_local_hardware(cpuinfo_path=unsupported)
    assert result["cpu_only_supported"] is False
    assert result["minimum_cpu_features"] == ["sse4_1"]
    assert result["missing_cpu_features"] == ["sse4_1"]
    assert result["cpu_feature_requirements"] == {"sse4_1": False}

    supported = tmp_path / "cpuinfo-supported"
    supported.write_text(
        "processor: 0\nflags: fpu sse sse2 pni ssse3 sse4_1 sse4_2\n",
        encoding="utf-8",
    )
    result = detect_local_hardware(cpuinfo_path=supported)
    assert result["cpu_only_supported"] is True
    assert result["missing_cpu_features"] == []
    assert result["cpu_feature_requirements"] == {"sse4_1": True}


@pytest.mark.parametrize(
    "profile_id", ["creator_perception", "scientific_engineering_mega"]
)
def test_hardware_sensitive_setup_blocks_before_install_on_unsupported_cpu(
    tmp_path: Path, monkeypatch, profile_id: str,
) -> None:
    service = SetupService(_paths(tmp_path / "xdg"))
    target = tmp_path / "target"
    target.mkdir()
    hardware = detect_local_hardware()
    hardware.update({
        "cpu_only_supported": False,
        "missing_cpu_features": ["sse4_1"],
    })
    monkeypatch.setattr(
        "app.install.setup_service.detect_local_hardware", lambda: hardware
    )
    preview = service.preview(SetupPreviewRequest(
        profile_id=profile_id,
        distribution_form="source",
        install_root=str(target),
        internet_available=True,
    ))
    assert preview["ready_to_apply"] is False
    assert any("sse4_1" in item for item in preview["blockers"])
