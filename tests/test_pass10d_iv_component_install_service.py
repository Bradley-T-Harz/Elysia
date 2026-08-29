from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from app.install.component_install_service import (
    ComponentApplyRequest,
    ComponentInstallError,
    ComponentInstallService,
    ComponentPreviewRequest,
    _registry_plan,
)
from app.install.paths import ElysiaPaths, RuntimeMode
from app.install.python_artifact_resolver import PythonArtifactResolutionError


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


def _wait(service: ComponentInstallService, job_id: str) -> dict:
    for _ in range(100):
        state = service.job(job_id)
        if state["status"] not in {"queued", "running"}:
            return state
        time.sleep(0.02)
    raise AssertionError("component job did not finish")


def _codev_vsix(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("extension/package.json", json.dumps({
            "name": "elysia-codev",
            "publisher": "ecosyneva-commons",
            "version": "1.0.0",
        }))
        archive.writestr("extension/THIRD_PARTY_NOTICES.txt", "Codev notices\n")


def _codev_release_identity(root: Path, artifact: Path) -> Path:
    target = root / "release_identity.json"
    target.write_text(json.dumps({
        "version": "1.0.0",
        "official_codev": {
            "version": "1.0.0",
            "repository_url": "https://github.com/Bradley-T-Harz/elysia-codev",
            "vsix_url": (
                "https://github.com/Bradley-T-Harz/elysia-codev/releases/"
                "download/v1.0.0/elysia-codev-1.0.0.vsix"
            ),
            "vsix_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "vsix_size_bytes": artifact.stat().st_size,
        },
    }), encoding="utf-8")
    return target


def test_component_preview_separates_profile_selection_from_network_approval(tmp_path: Path) -> None:
    service = ComponentInstallService(_paths(tmp_path))
    with pytest.raises(ComponentInstallError, match="network approval"):
        service.preview(ComponentPreviewRequest(
            component_id="workstation_adapters",
            operation="install",
            metadata_network_approved=False,
        ))


def test_scientific_component_preview_rejects_unsupported_cpu_before_resolution(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.install.component_install_service.detect_local_hardware",
        lambda: {
            "cpu_only_supported": False,
            "missing_cpu_features": ["sse4_1"],
            "gpu": {"cuda_variant_supported": False},
        },
    )
    service = ComponentInstallService(
        _paths(tmp_path),
        wheel_resolver=lambda _path: pytest.fail("resolver must not run"),
    )
    with pytest.raises(ComponentInstallError, match="sse4_1"):
        service.preview(ComponentPreviewRequest(
            component_id="scientific_engineering",
            operation="install",
            metadata_network_approved=True,
        ))


@pytest.mark.parametrize(
    ("cuda_supported", "expected_variant", "expected_lock"),
    [
        (False, "cpu", "creator-cpu-py312.lock.txt"),
        (True, "cuda", "creator-cuda-py312.lock.txt"),
    ],
)
def test_creator_preview_selects_exact_hardware_variant_without_cross_installing_cuda(
    tmp_path: Path,
    monkeypatch,
    cuda_supported: bool,
    expected_variant: str,
    expected_lock: str,
) -> None:
    resolved: list[str] = []

    monkeypatch.setattr(
        "app.install.component_install_service.detect_local_hardware",
        lambda: {
            "cpu_only_supported": True,
            "missing_cpu_features": [],
            "gpu": {"cuda_variant_supported": cuda_supported},
        },
    )

    def resolve(lock_path: Path) -> dict:
        resolved.append(lock_path.name)
        return {
            "artifact_count": 1,
            "exact_download_bytes": 123,
            "artifacts": [{
                "package": "demo", "version": "1", "filename": "demo.whl",
                "sha256": "a" * 64, "size_bytes": 123, "artifact_type": "wheel",
            }],
            "build_tools": [],
        }

    preview = ComponentInstallService(
        _paths(tmp_path), wheel_resolver=resolve,
    ).preview(ComponentPreviewRequest(
        component_id="creator_perception",
        operation="install",
        metadata_network_approved=True,
    ))

    assert resolved == [expected_lock]
    assert preview["hardware_variant"] == expected_variant


def test_creator_preview_rejects_unsupported_cpu_before_resolution(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.install.component_install_service.detect_local_hardware",
        lambda: {
            "cpu_only_supported": False,
            "missing_cpu_features": ["sse4_1"],
            "gpu": {"cuda_variant_supported": False},
        },
    )
    service = ComponentInstallService(
        _paths(tmp_path),
        wheel_resolver=lambda _path: pytest.fail("resolver must not run"),
    )
    with pytest.raises(ComponentInstallError, match="sse4_1"):
        service.preview(ComponentPreviewRequest(
            component_id="creator_perception",
            operation="install",
            metadata_network_approved=True,
        ))


def test_creator_preview_keeps_unselected_models_truthfully_gated(tmp_path: Path) -> None:
    service = ComponentInstallService(
        _paths(tmp_path),
        wheel_resolver=lambda _path: {
            "artifact_count": 1,
            "exact_download_bytes": 123,
            "artifacts": [{
                "package": "demo", "version": "1", "filename": "demo.whl",
                "sha256": "a" * 64, "size_bytes": 123, "artifact_type": "wheel",
            }],
            "build_tools": [],
        },
    )
    preview = service.preview(ComponentPreviewRequest(
        component_id="creator_perception",
        operation="install",
        metadata_network_approved=True,
    ))
    assert preview["exact_download_bytes"] == 123
    assert preview["model_selection_complete"] is False
    assert preview["model_gates_after_install"] == [
        "flux1_schnell", "kokoro_onnx_v1", "whisper_cpp_base_en",
    ]
    assert preview["model_plan"]["selected_model_ids"] == []


def test_python_acquisition_resolution_failure_is_a_structured_component_block(
    tmp_path: Path,
) -> None:
    def fail_resolution(_lock_path: Path) -> dict:
        raise PythonArtifactResolutionError("synthetic exact-lock mismatch")

    service = ComponentInstallService(
        _paths(tmp_path), wheel_resolver=fail_resolution
    )
    with pytest.raises(
        ComponentInstallError,
        match="exact creator perception acquisition plan is invalid",
    ):
        service.preview(ComponentPreviewRequest(
            component_id="creator_perception",
            operation="install",
            metadata_network_approved=True,
        ))


def test_creator_model_selection_requires_explicit_terms_acceptance(tmp_path: Path) -> None:
    service = ComponentInstallService(
        _paths(tmp_path),
        wheel_resolver=lambda _path: {
            "artifact_count": 0, "exact_download_bytes": 0,
            "artifacts": [], "build_tools": [],
        },
    )
    with pytest.raises(ComponentInstallError, match="acceptance"):
        service.preview(ComponentPreviewRequest(
            component_id="creator_perception",
            operation="install",
            metadata_network_approved=True,
            selected_model_ids=["whisper_cpp_base_en"],
        ))
    with pytest.raises(ComponentInstallError, match="Package-bound"):
        service.preview(ComponentPreviewRequest(
            component_id="identity_memory_fabric",
            operation="repair",
        ))


def test_registry_plan_binds_index_and_linux_amd64_child_without_pull(
    monkeypatch,
) -> None:
    child = json.dumps({
        "schemaVersion": 2,
        "config": {"digest": "sha256:" + "c" * 64, "size": 101},
        "layers": [
            {"digest": "sha256:" + "d" * 64, "size": 202},
            {"digest": "sha256:" + "e" * 64, "size": 303},
        ],
    }, separators=(",", ":")).encode()
    child_digest = "sha256:" + hashlib.sha256(child).hexdigest()
    index = json.dumps({
        "schemaVersion": 2,
        "manifests": [{
            "digest": child_digest,
            "size": 123,
            "platform": {"os": "linux", "architecture": "amd64"},
        }],
    }, separators=(",", ":")).encode()
    image = "docker.io/example/tool@sha256:" + hashlib.sha256(index).hexdigest()
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        output = index if len(calls) == 1 else child
        return subprocess.CompletedProcess(command, 0, output, b"")

    monkeypatch.setattr(
        "app.install.component_install_service.shutil.which",
        lambda command: (
            f"/usr/bin/{command}" if command in {"podman", "skopeo"} else None
        ),
    )
    monkeypatch.setattr("app.install.component_install_service.subprocess.run", run)
    plan = _registry_plan(image)
    assert len(calls) == 2
    assert calls[0][:4] == [
        "/usr/bin/skopeo", "inspect", "--raw", f"docker://{image}",
    ]
    assert calls[1][-1].endswith("@" + child_digest)
    assert plan["platform_manifest_digest"] == child_digest
    assert plan["exact_download_bytes"] == 606
    assert plan["artifact_count"] == 3
    assert plan["container_bytes_pulled"] is False


def test_failed_container_install_attempts_owned_cleanup(tmp_path: Path, monkeypatch) -> None:
    commands: list[list[str]] = []
    cleanup_commands: list[list[str]] = []

    def runner(command, _cancel, _working):
        commands.append(command)
        raise ComponentInstallError("synthetic install failure")

    def cleanup(command, **_kwargs):
        cleanup_commands.append(command)
        return subprocess.CompletedProcess(command, 0, "cleaned", "")

    monkeypatch.setattr(
        "app.install.component_install_service.shutil.which",
        lambda command: "/usr/bin/bash" if command == "bash" else None,
    )
    monkeypatch.setattr("app.install.component_install_service.subprocess.run", cleanup)
    service = ComponentInstallService(
        _paths(tmp_path),
        registry_resolver=lambda _image: {
            "artifact_count": 2,
            "exact_download_bytes": 303,
            "image": "docker.io/example/tool@sha256:" + "a" * 64,
            "layer_digests": ["sha256:" + "b" * 64],
            "metadata_network_used": True,
            "container_bytes_pulled": False,
        },
        command_runner=runner,
    )
    preview = service.preview(ComponentPreviewRequest(
        component_id="governed_research",
        operation="install",
        metadata_network_approved=True,
    ))
    result = service.apply(ComponentApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    state = _wait(service, result["job_id"])
    assert state["status"] == "failed"
    assert commands[0][-1] == "install"
    assert cleanup_commands[0][-1] == "uninstall"


def test_container_scripts_bound_slow_clean_vm_readiness() -> None:
    for relative in ("scripts/manage_searxng.sh", "scripts/manage_qdrant.sh"):
        text = Path(relative).read_text(encoding="utf-8")
        assert "seq 1 120" in text
        assert "sleep 0.5" in text
        assert "within 60 seconds" in text


def test_searxng_rootless_bind_mounts_remain_owned_by_local_user() -> None:
    text = Path("scripts/manage_searxng.sh").read_text(encoding="utf-8")

    assert "repair_rootless_bind_ownership" in text
    assert 'podman unshare chown -R 0:0 "$target"' in text
    assert "repair_rootless_bind_ownership\n  mkdir -p" in text
    assert "--env FORCE_OWNERSHIP=false" in text


def test_component_command_drains_large_progress_streams_without_pipe_deadlock(
    tmp_path: Path,
) -> None:
    service = ComponentInstallService(_paths(tmp_path))
    output = service._run_command(
        [
            sys.executable,
            "-c",
            (
                "import sys;"
                "sys.stdout.write('o' * (3 * 1024 * 1024) + 'STDOUT_COMPLETE');"
                "sys.stderr.write('e' * (3 * 1024 * 1024) + 'STDERR_COMPLETE')"
            ),
        ],
        threading.Event(),
        tmp_path,
    )

    assert output.endswith("STDOUT_COMPLETE")
    assert len(output.encode()) <= 2 * 1024 * 1024


def test_component_command_applies_explicit_child_umask(tmp_path: Path) -> None:
    service = ComponentInstallService(_paths(tmp_path))
    output = tmp_path / "mode-proof"

    service._run_command(
        [sys.executable, "-c", f"from pathlib import Path;Path({str(output)!r}).write_text('proof')"],
        threading.Event(),
        tmp_path,
        child_umask=0o002,
    )

    assert stat.S_IMODE(output.stat().st_mode) == 0o664


def test_existing_local_provider_adoption_is_exact_approved_and_receipted(
    tmp_path: Path, monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    monkeypatch.setattr(
        "app.install.component_install_service.shutil.which",
        lambda command: "/usr/local/bin/ollama" if command == "ollama" else None,
    )
    service = ComponentInstallService(paths)
    preview = service.preview(ComponentPreviewRequest(
        component_id="local_model_provider", operation="install",
    ))
    assert preview["provider_adoption_only"] is True
    assert preview["exact_download_bytes"] == 0
    result = service.apply(ComponentApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    state = _wait(service, result["job_id"])
    assert state["status"] == "succeeded"
    receipt = json.loads((service.receipt_root / "local_model_provider.json").read_text())
    assert receipt["managed_by_elysia"] is False
    assert receipt["raw_paths_exposed"] is False


def test_component_remove_requires_ownership_and_moves_payload_recoverably(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    service = ComponentInstallService(paths)
    with pytest.raises(ComponentInstallError, match="ownership receipt"):
        service.preview(ComponentPreviewRequest(
            component_id="workstation_adapters", operation="remove",
        ))
    environment = service.component_root / "elysia_workstation"
    environment.mkdir(parents=True)
    (environment / "marker").write_text("preserve", encoding="utf-8")
    service.receipt_root.mkdir(mode=0o700, parents=True)
    receipt_path = service.receipt_root / "workstation_adapters.json"
    receipt_path.write_text(json.dumps({
        "contract_version": "elysia-component-install-1.0",
        "component_id": "workstation_adapters",
        "environment_id": "elysia_workstation",
        "status": "ready",
        "managed_by_elysia": True,
        "user_data_present": False,
        "raw_paths_exposed": False,
    }), encoding="utf-8")
    receipt_path.chmod(0o600)
    preview = service.preview(ComponentPreviewRequest(
        component_id="workstation_adapters", operation="remove",
    ))
    result = service.apply(ComponentApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    state = _wait(service, result["job_id"])
    assert state["status"] == "succeeded"
    assert not environment.exists()
    recovered = list(service.recovery_root.glob("elysia_workstation-*"))
    assert len(recovered) == 1
    assert (recovered[0] / "marker").read_text() == "preserve"
    assert json.loads(receipt_path.read_text())["status"] == "removed"


def test_persisted_running_job_without_live_worker_is_truthfully_interrupted(tmp_path: Path) -> None:
    service = ComponentInstallService(_paths(tmp_path))
    job_id = "component_job_" + "a" * 24
    path = service.job_root / f"{job_id}.json"
    path.parent.mkdir(mode=0o700, parents=True)
    path.write_text(json.dumps({
        "contract_version": "elysia-component-install-1.0",
        "job_id": job_id,
        "component_id": "workstation_adapters",
        "operation": "install",
        "status": "running",
        "cancel_requested": False,
        "created_at_utc": "2026-08-24T00:00:00Z",
        "updated_at_utc": "2026-08-24T00:00:00Z",
        "raw_paths_exposed": False,
    }), encoding="utf-8")
    path.chmod(0o600)
    assert service.job(job_id)["status"] == "interrupted"


def test_codev_apply_refuses_vsix_changed_after_exact_preview(
    tmp_path: Path, monkeypatch,
) -> None:
    artifact = tmp_path / "elysia-codev-1.0.0.vsix"
    _codev_vsix(artifact)
    commands: list[list[str]] = []

    def runner(command: list[str], _cancel, _working: Path) -> str:
        commands.append(command)
        return ""

    monkeypatch.setattr(
        "app.install.component_install_service.shutil.which",
        lambda command: "/usr/bin/code" if command == "code" else None,
    )
    service = ComponentInstallService(
        _paths(tmp_path / "xdg"),
        command_runner=runner,
        release_identity_path=_codev_release_identity(tmp_path, artifact),
    )
    preview = service.preview(ComponentPreviewRequest(
        component_id="codev_companion",
        operation="install",
        local_artifact_path=str(artifact),
    ))
    assert preview["canonical_release_url"].endswith(
        "/releases/download/v1.0.0/elysia-codev-1.0.0.vsix"
    )
    artifact.write_bytes(b"changed after preview")
    result = service.apply(ComponentApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    state = _wait(service, result["job_id"])
    assert state["status"] == "failed"
    assert commands == []


def test_codev_component_install_and_remove_verify_editor_reality(
    tmp_path: Path, monkeypatch,
) -> None:
    artifact = tmp_path / "elysia-codev-1.0.0.vsix"
    _codev_vsix(artifact)
    installed = False
    commands: list[list[str]] = []

    def runner(command: list[str], _cancel, _working: Path) -> str:
        nonlocal installed
        commands.append(command)
        if "--install-extension" in command:
            installed = True
        elif "--uninstall-extension" in command:
            installed = False
        elif "--list-extensions" in command:
            return "ecosyneva-commons.elysia-codev@1.0.0\n" if installed else ""
        return ""

    monkeypatch.setattr(
        "app.install.component_install_service.shutil.which",
        lambda command: "/usr/bin/code" if command == "code" else None,
    )
    service = ComponentInstallService(
        _paths(tmp_path / "xdg"),
        command_runner=runner,
        release_identity_path=_codev_release_identity(tmp_path, artifact),
    )
    preview = service.preview(ComponentPreviewRequest(
        component_id="codev_companion",
        operation="install",
        local_artifact_path=str(artifact),
    ))
    result = service.apply(ComponentApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    assert _wait(service, result["job_id"])["status"] == "succeeded"
    install_receipt = json.loads(
        (service.paths.data_dir / "developer" / "codev-install.json").read_text()
    )
    assert install_receipt["package_sha256"] == preview["artifact_sha256"]


def test_codev_component_can_acquire_exact_first_party_release_without_local_file(
    tmp_path: Path, monkeypatch,
) -> None:
    artifact = tmp_path / "fixture.vsix"
    _codev_vsix(artifact)
    payload = artifact.read_bytes()
    installed = False
    commands: list[list[str]] = []

    def runner(command: list[str], _cancel, _working: Path) -> str:
        nonlocal installed
        commands.append(command)
        if "--install-extension" in command:
            installed = True
        elif "--uninstall-extension" in command:
            installed = False
        elif "--list-extensions" in command:
            return "ecosyneva-commons.elysia-codev@1.0.0\n" if installed else ""
        return ""

    monkeypatch.setattr(
        "app.install.component_install_service.shutil.which",
        lambda command: "/usr/bin/code" if command == "code" else None,
    )
    monkeypatch.setattr(
        "app.install.component_install_service.urlopen",
        lambda _request, timeout: io.BytesIO(payload),
    )
    service = ComponentInstallService(
        _paths(tmp_path / "xdg"),
        command_runner=runner,
        release_identity_path=_codev_release_identity(tmp_path, artifact),
    )
    with pytest.raises(ComponentInstallError, match="network approval"):
        service.preview(ComponentPreviewRequest(
            component_id="codev_companion",
            operation="install",
        ))
    preview = service.preview(ComponentPreviewRequest(
        component_id="codev_companion",
        operation="install",
        metadata_network_approved=True,
    ))
    assert preview["automatic_acquisition"] is True
    assert preview["exact_download_bytes"] == len(payload)
    result = service.apply(ComponentApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    assert _wait(service, result["job_id"])["status"] == "succeeded"
    assert not (service.root / "staging" / result["job_id"]).exists()

    removal = service.preview(ComponentPreviewRequest(
        component_id="codev_companion", operation="remove",
    ))
    result = service.apply(ComponentApplyRequest(
        preview_id=removal["preview_id"],
        approval_token=removal["approval_token"],
        operator_approved=True,
    ))
    assert _wait(service, result["job_id"])["status"] == "succeeded"
    assert installed is False
    component_receipt = json.loads(
        (service.receipt_root / "codev_companion.json").read_text()
    )
    assert component_receipt["status"] == "removed"
    assert component_receipt["workspace_and_repository_data_preserved"] is True
    assert any("--install-extension" in command for command in commands)
    assert any("--uninstall-extension" in command for command in commands)


def test_codev_remote_acquisition_failure_cleans_private_staging(
    tmp_path: Path, monkeypatch,
) -> None:
    artifact = tmp_path / "fixture.vsix"
    _codev_vsix(artifact)
    monkeypatch.setattr(
        "app.install.component_install_service.shutil.which",
        lambda command: "/usr/bin/code" if command == "code" else None,
    )
    monkeypatch.setattr(
        "app.install.component_install_service.urlopen",
        lambda _request, timeout: io.BytesIO(b"not the approved VSIX"),
    )
    service = ComponentInstallService(
        _paths(tmp_path / "xdg"),
        command_runner=lambda *_args: "",
        release_identity_path=_codev_release_identity(tmp_path, artifact),
    )
    preview = service.preview(ComponentPreviewRequest(
        component_id="codev_companion",
        operation="install",
        metadata_network_approved=True,
    ))
    result = service.apply(ComponentApplyRequest(
        preview_id=preview["preview_id"],
        approval_token=preview["approval_token"],
        operator_approved=True,
    ))
    job = _wait(service, result["job_id"])
    assert job["status"] == "failed"
    assert "differs from the exact approved" in job["error_summary"]
    assert not (service.root / "staging" / result["job_id"]).exists()
