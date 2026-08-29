from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import time
import zipfile

import pytest

from app.api import coding_archive_extraction_service, coding_archive_inspection_service
from app.api.coding_archive_extraction_service import (
    ArchiveExtractionFailure,
    _copy_member_stream,
    _destination_for_member,
)
from app.api.coding_archive_inspection_service import inspect_archive_path
from app.api.coding_archive_job_service import cancel_archive_job, get_archive_job
from app.api.coding_archive_service import apply_archive_extraction, inspect_archive, plan_archive_extraction
from app.api.coding_archive_type_registry import archive_registry_payload
from app.api.coding_audit_service import get_coding_audit_record
from app.api.capability_service import get_capabilities_status
from app.api.coding_file_type_registry import detect_file_type
from app.api.coding_operation_service import approve_operation
from app.api.main import create_app
from app.api.request_trace_service import get_request_trace_record
from app.api.routes.coding_archive import get_archive_types, post_archive_inspect
from app.api.schemas.archive import (
    ArchiveExtractionApplyRequest,
    ArchiveExtractionPlanRequest,
    ArchiveInspectRequest,
)
from app.api.schemas.coding_operations import CodingOperationApproveRequest
from sandbox.archiveforge_worker.worker import ExternalListError, list_external_archive


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)


def _mark_zip_members_encrypted(path: Path) -> None:
    raw = bytearray(path.read_bytes())
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        position = 0
        while (position := raw.find(signature, position)) >= 0:
            flags_at = position + flag_offset
            flags = int.from_bytes(raw[flags_at : flags_at + 2], "little") | 0x1
            raw[flags_at : flags_at + 2] = flags.to_bytes(2, "little")
            position += len(signature)
    path.write_bytes(raw)


def _add_tar_bytes(archive: tarfile.TarFile, name: str, content: bytes, *, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = mode
    archive.addfile(info, io.BytesIO(content))


def _tar_gz_bytes(entries: list[tuple[str, bytes, int]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content, mode in entries:
            _add_tar_bytes(archive, name, content, mode=mode)
    return buffer.getvalue()


def _ar_member(name: str, content: bytes, *, mode: int = 0o100644) -> bytes:
    encoded_name = f"{name}/".encode("ascii")[:16].ljust(16, b" ")
    header = b"".join(
        (
            encoded_name,
            b"0".ljust(12, b" "),
            b"0".ljust(6, b" "),
            b"0".ljust(6, b" "),
            f"{mode:o}".encode("ascii").ljust(8, b" "),
            str(len(content)).encode("ascii").ljust(10, b" "),
            b"`\n",
        )
    )
    assert len(header) == 60
    return header + content + (b"\n" if len(content) % 2 else b"")


def _write_deb(path: Path) -> None:
    control = _tar_gz_bytes(
        [
            ("control", b"Package: synthetic\nVersion: 1\nArchitecture: all\n", 0o644),
            ("postinst", b"#!/bin/sh\nexit 0\n", 0o755),
        ]
    )
    data = _tar_gz_bytes(
        [
            ("usr/bin/synthetic-tool", b"not an executable fixture", 0o755),
            ("usr/lib/libsynthetic.so", b"not an elf fixture", 0o644),
        ]
    )
    path.write_bytes(
        b"!<arch>\n"
        + _ar_member("debian-binary", b"2.0\n")
        + _ar_member("control.tar.gz", control)
        + _ar_member("data.tar.gz", data)
    )


def _approve_plan(workspace_root: Path, archive_path: Path, plan) -> tuple[str, str]:
    approval = approve_operation(
        CodingOperationApproveRequest(
            operation_kind="archive_extract",
            operation_summary="Approve selected synthetic members into one disposable sandbox",
            workspace_root=str(workspace_root),
            exact_files=[str(archive_path)],
            source_hash=plan.archive_sha256,
            plan_hash=plan.plan_hash,
            allowed_mutation_class="archive_sandbox_extract",
            operator_approved=True,
            approval_phrase="approve exact selected archive members",
            rollback_note="Abort cleanup removes partial sandbox output.",
        )
    )
    assert approval.status == "approved"
    assert approval.approval_token is not None
    return approval.approval_id, approval.approval_token


def _apply_request(
    *,
    root: Path,
    source: Path,
    plan,
    approval_id: str,
    approval_token: str,
    sandbox_id: str | None = None,
) -> ArchiveExtractionApplyRequest:
    return ArchiveExtractionApplyRequest(
        operation_id=plan.operation_id,
        workspace_root=str(root),
        archive_path=str(source),
        selected_member_indexes=plan.selected_member_indexes,
        sandbox_id=sandbox_id or plan.sandbox_id,
        approval_granted=True,
        approval_id=approval_id,
        approval_token=approval_token,
        operator_approved=True,
        expected_archive_sha256=plan.archive_sha256,
        expected_manifest_digest=plan.manifest_digest,
        expected_plan_hash=plan.plan_hash,
    )


def test_archive_routes_registry_and_hard_boundaries_are_truthful():
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert {
        "/coding/archive/types",
        "/coding/archive/inspect",
        "/coding/archive/extract/plan",
        "/coding/archive/extract/apply",
        "/coding/archive/jobs/{operation_id}",
        "/coding/archive/jobs/{operation_id}/cancel",
        "/coding/archive/artifacts/{artifact_id}",
    } <= paths
    assert not any(
        marker in path
        for path in paths
        for marker in ("archive/install", "archive/execute", "archive/run", "archive/import", "archive/extract-all")
    )
    assert "app.api.routes.coding_archive" in app.state.registered_route_modules

    truth = archive_registry_payload()
    formats = {item["type_id"]: item for item in truth["formats"]}
    assert set(formats) == {"zip", "tar", "tar_gz", "7z", "rar", "whl", "jar", "vsix", "appimage", "deb"}
    assert formats["zip"]["extraction_state"] == "extract_sandbox_only"
    assert formats["tar"]["extraction_state"] == "extract_sandbox_only"
    assert formats["tar_gz"]["extraction_state"] == "extract_sandbox_only"
    assert formats["7z"]["extraction_state"] == "list_only"
    assert formats["rar"]["extraction_state"] == "lab_only"
    assert formats["rar"]["tool_license_status"] == "mixed_multiverse_nonfree_sensitive"
    assert formats["appimage"]["list_supported"] is False
    for package_type in ("whl", "jar", "vsix", "appimage", "deb"):
        assert formats[package_type]["install_state"] == "unavailable_by_design"
        assert formats[package_type]["execute_state"] == "unavailable_by_design"
        assert formats[package_type]["selected_sandbox_extraction_supported"] is False
    assert truth["autonomy"]["autonomous_extraction"] is False
    assert truth["hard_boundaries"]["project_root_extraction"] == "blocked"

    expected_file_types = {
        "sample.zip": "zip_archive",
        "sample.tar": "tar_archive",
        "sample.tar.gz": "tar_gz_archive",
        "sample.7z": "seven_zip_archive",
        "sample.rar": "rar_archive",
        "sample.whl": "python_wheel_container",
        "sample.jar": "java_archive_container",
        "sample.vsix": "vsix_extension_container",
        "sample.AppImage": "appimage_container",
        "sample.deb": "debian_package_container",
    }
    for filename, type_id in expected_file_types.items():
        descriptor = detect_file_type(filename)
        assert descriptor.type_id == type_id
        assert descriptor.category == "archive"
        assert descriptor.adapter == "archive"
        assert descriptor.writable is False
        assert descriptor.patchable is False

    route_truth = asyncio.run(get_archive_types())
    assert route_truth["status"] == "ok"
    assert route_truth["data"]["archive_types"]["policy_version"] == "archive-types-0.1"
    capabilities = {
        item["capability_key"]: item
        for item in get_capabilities_status()["data"]["capabilities"]
    }
    assert capabilities["archiveforge_stewardship"]["state"] == "live"
    assert capabilities["archiveforge_stewardship"]["approval_state"] == "needed"


def test_safe_zip_requires_inspection_approval_and_extracts_only_selected_to_private_sandbox(tmp_path: Path):
    source = tmp_path / "safe.zip"
    _write_zip(source, [("folder/selected.txt", b"selected payload"), ("folder/skipped.txt", b"skip me")])

    blocked = inspect_archive(
        ArchiveInspectRequest(workspace_root=str(tmp_path), archive_path=str(source), approval_granted=False)
    )
    assert blocked.status == "approval_required"
    assert blocked.member_count == 0

    inspection = inspect_archive(
        ArchiveInspectRequest(workspace_root=str(tmp_path), archive_path=str(source), approval_granted=True)
    )
    assert inspection.status == "completed"
    assert inspection.detected_type == "zip"
    assert inspection.extension_content_match is True
    assert inspection.member_count == 2
    assert len(inspection.artifacts) == 2

    sandbox_id = "sandbox_safe_zip"
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id=sandbox_id,
            approval_granted=True,
        )
    )
    assert plan.status == "planned"
    assert plan.selected_file_count == 1
    approval_id, approval_token = _approve_plan(tmp_path, source, plan)
    result = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )

    sandbox = coding_archive_extraction_service.archive_sandbox_root() / sandbox_id
    selected = sandbox / "extracted" / "folder" / "selected.txt"
    skipped = sandbox / "extracted" / "folder" / "skipped.txt"
    assert result.status == "completed"
    assert result.extracted_file_count == 1
    assert result.extracted_bytes == len(b"selected payload")
    assert result.source_mutated is False
    assert result.project_root_written is False
    assert result.install_performed is False
    assert result.execution_performed is False
    assert selected.read_bytes() == b"selected payload"
    assert not skipped.exists()
    assert stat.S_IMODE(selected.stat().st_mode) == 0o600
    assert stat.S_IMODE(sandbox.stat().st_mode) == 0o700
    assert stat.S_IMODE((sandbox / "extracted").stat().st_mode) == 0o700
    assert source.read_bytes().startswith(b"PK")
    job = get_archive_job(plan.operation_id)
    assert job is not None
    assert job.status == "completed"
    assert job.approval_id == approval_id
    assert {item.name for item in sandbox.iterdir()} == {
        "extracted",
        "manifest.json",
        "risk_report.json",
        "extraction_plan.json",
        "extraction_receipt.json",
    }


@pytest.mark.parametrize(("suffix", "mode"), ((".tar", "w"), (".tar.gz", "w:gz")))
def test_tar_variants_extract_selected_regular_files_without_preserving_execute_bits(
    tmp_path: Path,
    suffix: str,
    mode: str,
):
    source = tmp_path / f"safe{suffix}"
    with tarfile.open(source, mode) as archive:
        _add_tar_bytes(archive, "selected/tool.sh", b"#!/bin/sh\nexit 0\n", mode=0o755)
        _add_tar_bytes(archive, "skipped.txt", b"skip")
    expected_type = "tar_gz" if suffix == ".tar.gz" else "tar"
    sandbox_id = f"sandbox_safe_{expected_type}"
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id=sandbox_id,
            approval_granted=True,
        )
    )
    assert plan.status == "planned"
    assert plan.archive_type == expected_type
    approval_id, approval_token = _approve_plan(tmp_path, source, plan)
    result = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )
    extracted = coding_archive_extraction_service.archive_sandbox_root() / sandbox_id / "extracted"
    assert result.status == "completed"
    assert (extracted / "selected" / "tool.sh").read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert stat.S_IMODE((extracted / "selected" / "tool.sh").stat().st_mode) == 0o600
    assert not (extracted / "skipped.txt").exists()


def test_encrypted_zip_is_listed_as_blocked_and_never_opened(tmp_path: Path):
    source = tmp_path / "encrypted.zip"
    _write_zip(source, [("secret.txt", b"synthetic encrypted marker")])
    _mark_zip_members_encrypted(source)
    inspection = inspect_archive_path(source)
    assert inspection["status"] == "completed"
    assert inspection["encrypted"] is True
    encrypted_risk = next(risk for risk in inspection["risk_flags"] if risk.code == "encrypted")
    assert encrypted_risk.blocks_extraction is True
    assert inspection["members"][0].extractable is False


def test_zip_path_attacks_collisions_nested_encryption_and_bomb_are_reported(tmp_path: Path):
    source = tmp_path / "hostile.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../escape.txt", b"escape")
        archive.writestr("/absolute.txt", b"absolute")
        archive.writestr("C:\\Windows\\system.ini", b"drive")
        archive.writestr("\\\\server\\share\\secret.txt", b"unc")
        archive.writestr("duplicate.txt", b"first")
        with pytest.warns(UserWarning, match="Duplicate name: 'duplicate.txt'"):
            archive.writestr("duplicate.txt", b"second")
        archive.writestr("Case.txt", b"case one")
        archive.writestr("case.TXT", b"case two")
        archive.writestr("nested/inside.tar.gz", b"inert nested bytes")
        archive.writestr("zeros.bin", b"\x00" * (2 * 1024 * 1024))
        symlink = zipfile.ZipInfo("link-to-outside")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(symlink, "../../outside")
        socket = zipfile.ZipInfo("socket-entry")
        socket.create_system = 3
        socket.external_attr = (stat.S_IFSOCK | 0o777) << 16
        archive.writestr(socket, b"")

    inspection = inspect_archive_path(source)
    codes = {risk.code for risk in inspection["risk_flags"]}
    assert {
        "path_traversal",
        "absolute_path",
        "windows_unc_or_drive_path",
        "duplicate_path",
        "unicode_or_case_collision",
        "nested_archive",
        "symlink",
        "socket",
    } <= codes
    assert "high_compression_ratio" in codes or "extreme_compression_ratio" in codes
    assert any(risk.blocks_extraction for risk in inspection["risk_flags"])
    blocked_member_codes = {
        "path_traversal",
        "absolute_path",
        "windows_unc_or_drive_path",
        "duplicate_path",
        "unicode_or_case_collision",
        "nested_archive",
        "symlink",
        "socket",
    }
    assert all(
        not member.extractable
        for member in inspection["members"]
        if blocked_member_codes.intersection(member.risk_flags)
    )

    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_hostile_zip",
            approval_granted=True,
        )
    )
    assert plan.status == "blocked"
    assert plan.blocked_reason == "archive_has_blocking_risk"
    assert not (coding_archive_extraction_service.archive_sandbox_root() / "sandbox_hostile_zip").exists()


def test_tar_links_devices_fifo_and_dangerous_permissions_are_never_materialized(tmp_path: Path):
    source = tmp_path / "specials.tar"
    with tarfile.open(source, "w") as archive:
        _add_tar_bytes(archive, "safe.txt", b"safe")
        _add_tar_bytes(archive, "setid.sh", b"#!/bin/sh\n", mode=0o6755)
        symlink = tarfile.TarInfo("link")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "../../outside"
        archive.addfile(symlink)
        hardlink = tarfile.TarInfo("hard")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "safe.txt"
        archive.addfile(hardlink)
        device = tarfile.TarInfo("device")
        device.type = tarfile.CHRTYPE
        device.devmajor = 1
        device.devminor = 3
        archive.addfile(device)
        fifo = tarfile.TarInfo("fifo")
        fifo.type = tarfile.FIFOTYPE
        archive.addfile(fifo)
        traversal = tarfile.TarInfo("../tar-escape")
        traversal.size = 1
        archive.addfile(traversal, io.BytesIO(b"x"))

    inspection = inspect_archive_path(source)
    codes = {risk.code for risk in inspection["risk_flags"]}
    assert {"symlink", "hardlink", "device", "fifo", "setid_permission", "executable_permission", "path_traversal"} <= codes
    assert all(not member.extractable for member in inspection["members"] if member.kind in {"symlink", "hardlink", "device", "fifo"})
    assert not (tmp_path / "tar-escape").exists()


def test_extension_content_mismatch_invalidates_extraction(tmp_path: Path):
    source = tmp_path / "pretends-to-be.tar"
    _write_zip(source, [("safe.txt", b"safe")])
    inspection = inspect_archive_path(source)
    assert inspection["extension_type"] == "tar"
    assert inspection["detected_type"] == "zip"
    assert inspection["extension_content_match"] is False
    mismatch = next(risk for risk in inspection["risk_flags"] if risk.code == "extension_content_mismatch")
    assert mismatch.blocks_extraction is True

    mislabeled_tar_gz = tmp_path / "raw-tar.tar.gz"
    with tarfile.open(mislabeled_tar_gz, "w") as archive:
        info = tarfile.TarInfo("safe.txt")
        info.size = 4
        archive.addfile(info, io.BytesIO(b"safe"))
    tar_inspection = inspect_archive_path(mislabeled_tar_gz)
    assert tar_inspection["extension_type"] == "tar_gz"
    assert tar_inspection["detected_type"] == "tar"
    assert tar_inspection["extension_content_match"] is False


def test_inspection_hard_limits_block_before_extraction(tmp_path: Path, monkeypatch):
    source = tmp_path / "limits.zip"
    _write_zip(source, [("long-name-one.txt", b"123456"), ("long-name-two.txt", b"abcdef")])
    original_loader = coding_archive_inspection_service.load_archive_limits

    def small_limits():
        policy = original_loader()
        policy["limits"].update(
            max_members=1,
            max_projected_uncompressed_bytes=8,
            max_single_file_bytes=5,
            max_output_path_chars=8,
        )
        return policy

    monkeypatch.setattr(coding_archive_inspection_service, "load_archive_limits", small_limits)
    inspection = inspect_archive_path(source)
    codes = {risk.code for risk in inspection["risk_flags"]}
    assert {"member_count_limit", "projected_size_limit", "single_file_size_limit", "path_too_long"} <= codes
    assert all(next(risk for risk in inspection["risk_flags"] if risk.code == code).blocks_extraction for code in codes if code in {"member_count_limit", "projected_size_limit", "single_file_size_limit", "path_too_long"})


def test_archive_input_size_limit_stops_member_parsing(tmp_path: Path, monkeypatch):
    source = tmp_path / "input-limit.zip"
    _write_zip(source, [("safe.txt", b"safe")])
    original_loader = coding_archive_inspection_service.load_archive_limits

    def one_byte_limit():
        policy = original_loader()
        policy["limits"]["max_archive_input_bytes"] = 1
        return policy

    monkeypatch.setattr(coding_archive_inspection_service, "load_archive_limits", one_byte_limit)
    monkeypatch.setattr(
        coding_archive_inspection_service,
        "hash_file",
        lambda _path: pytest.fail("over-limit input must be rejected before full hashing"),
    )
    inspection = inspect_archive_path(source)
    assert inspection["status"] == "blocked"
    assert inspection["blocked_reason"] == "archive_input_size_limit"
    assert inspection["members"] == []


def test_selected_write_projection_limit_blocks_before_approval_or_sandbox(tmp_path: Path, monkeypatch):
    source = tmp_path / "selected-limit.zip"
    _write_zip(source, [("selected.txt", b"0123456789")])
    original_loader = coding_archive_extraction_service.load_archive_limits

    def tiny_write_limit():
        policy = original_loader()
        policy["limits"]["max_extraction_bytes_written"] = 4
        return policy

    monkeypatch.setattr(coding_archive_extraction_service, "load_archive_limits", tiny_write_limit)
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_selected_limit",
            approval_granted=True,
        )
    )
    assert plan.status == "blocked"
    assert plan.blocked_reason == "selected_write_bytes_limit"
    assert not (coding_archive_extraction_service.archive_sandbox_root() / "sandbox_selected_limit").exists()


def test_preexisting_sandbox_is_never_overwritten_and_plan_is_blocked(tmp_path: Path):
    source = tmp_path / "preexisting-sandbox.zip"
    _write_zip(source, [("selected.txt", b"safe")])
    sandbox_path = coding_archive_extraction_service.archive_sandbox_root() / "sandbox_preexisting"
    sandbox_path.mkdir(parents=True, mode=0o700)
    marker = sandbox_path / "owned-by-another-operation.txt"
    marker.write_text("preserve", encoding="utf-8")

    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_preexisting",
            approval_granted=True,
        )
    )

    assert plan.status == "blocked"
    assert plan.blocked_reason == "sandbox_already_exists"
    assert marker.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize(
    ("suffix", "entries", "expected_type", "risk_code"),
    [
        (
            ".whl",
            [
                ("synthetic-1.0.dist-info/WHEEL", b"Wheel-Version: 1.0\nTag: py3-none-any\n"),
                ("synthetic-1.0.dist-info/METADATA", b"Name: synthetic\nVersion: 1.0\n"),
                ("synthetic-1.0.dist-info/entry_points.txt", b"[console_scripts]\nsynthetic = pkg:main\n"),
                ("pkg/native.so", b"inert native marker"),
            ],
            "whl",
            "package_scripts",
        ),
        (
            ".jar",
            [("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\nMain-Class: Synthetic\n"), ("Synthetic.class", b"\xca\xfe\xba\xbe")],
            "jar",
            "package_scripts",
        ),
        (
            ".vsix",
            [
                ("extension.vsixmanifest", b"<PackageManifest />"),
                (
                    "extension/package.json",
                    json.dumps({"name": "synthetic", "publisher": "local", "version": "1", "activationEvents": ["*"], "scripts": {"postinstall": "never run"}}).encode(),
                ),
            ],
            "vsix",
            "package_scripts",
        ),
    ],
)
def test_zip_package_containers_are_static_inspect_only(
    tmp_path: Path,
    suffix: str,
    entries: list[tuple[str, bytes]],
    expected_type: str,
    risk_code: str,
):
    source = tmp_path / f"synthetic{suffix}"
    _write_zip(source, entries)
    inspection = inspect_archive_path(source)
    assert inspection["status"] == "completed"
    assert inspection["detected_type"] == expected_type
    assert inspection["package_metadata"].install_supported is False
    assert inspection["package_metadata"].execute_supported is False
    assert risk_code in {risk.code for risk in inspection["risk_flags"]}

    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id=f"sandbox_{expected_type}_inspect",
            approval_granted=True,
        )
    )
    assert plan.status == "blocked"
    assert plan.blocked_reason == "format_not_enabled_for_sandbox_extraction"


def test_deb_and_appimage_are_inspected_without_install_mount_or_execution(tmp_path: Path):
    deb = tmp_path / "synthetic.deb"
    _write_deb(deb)
    deb_inspection = inspect_archive_path(deb)
    assert deb_inspection["status"] == "completed"
    assert deb_inspection["detected_type"] == "deb"
    metadata = deb_inspection["package_metadata"]
    assert metadata.install_supported is False
    assert metadata.execute_supported is False
    assert "postinst" in metadata.scripts_present
    assert metadata.summary["system_binary_count"] == 1
    assert metadata.native_binary_count == 1

    appimage = tmp_path / "synthetic.AppImage"
    appimage.write_bytes(b"\x7fELF\x02\x01\x01\x00AI\x02" + b"\x00" * 128)
    image_inspection = inspect_archive_path(appimage)
    assert image_inspection["status"] == "completed"
    assert image_inspection["detected_type"] == "appimage"
    assert image_inspection["tool_used"] == "static_elf_header"
    assert image_inspection["member_count"] == 0
    assert image_inspection["package_metadata"].summary["payload_listing_state"].startswith("unavailable_by_design")
    assert image_inspection["package_metadata"].execute_supported is False


def test_exact_approval_is_one_time_and_archive_hash_mutation_invalidates_plan(tmp_path: Path):
    source = tmp_path / "mutable.zip"
    _write_zip(source, [("selected.txt", b"original")])
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_one_time",
            approval_granted=True,
        )
    )
    approval_id, approval_token = _approve_plan(tmp_path, source, plan)
    request = _apply_request(
        root=tmp_path,
        source=source,
        plan=plan,
        approval_id=approval_id,
        approval_token=approval_token,
    )
    first = apply_archive_extraction(request)
    second = apply_archive_extraction(request)
    assert first.status == "completed"
    assert second.status == "approval_required"
    assert second.blocked_reason == "approval_already_used"

    changed_plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_hash_change",
            approval_granted=True,
        )
    )
    changed_approval_id, changed_approval_token = _approve_plan(tmp_path, source, changed_plan)
    _write_zip(source, [("selected.txt", b"mutated after approval")])
    changed = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=changed_plan,
            approval_id=changed_approval_id,
            approval_token=changed_approval_token,
        )
    )
    assert changed.status == "blocked"
    assert changed.blocked_reason == "archive_hash_changed"
    assert not (coding_archive_extraction_service.archive_sandbox_root() / "sandbox_hash_change").exists()


def test_sandbox_destination_change_invalidates_exact_plan_without_consuming_approval(tmp_path: Path):
    source = tmp_path / "destination.zip"
    _write_zip(source, [("selected.txt", b"destination-bound")])
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_destination_a",
            approval_granted=True,
        )
    )
    approval_id, approval_token = _approve_plan(tmp_path, source, plan)
    changed_destination = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
            sandbox_id="sandbox_destination_b",
        )
    )
    assert changed_destination.status == "blocked"
    assert changed_destination.blocked_reason == "extraction_plan_changed"
    assert not (coding_archive_extraction_service.archive_sandbox_root() / "sandbox_destination_a").exists()
    assert not (coding_archive_extraction_service.archive_sandbox_root() / "sandbox_destination_b").exists()

    exact = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )
    assert exact.status == "completed"


def test_operation_id_change_invalidates_exact_plan_without_consuming_approval(tmp_path: Path):
    source = tmp_path / "operation-id.zip"
    _write_zip(source, [("selected.txt", b"safe")])
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_operation_id",
            approval_granted=True,
        )
    )
    approval_id, approval_token = _approve_plan(tmp_path, source, plan)
    changed = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
        ).model_copy(update={"operation_id": "archive_plan_deadbeefdeadbeef"})
    )
    assert changed.status == "blocked"
    assert changed.blocked_reason == "extraction_plan_changed"

    exact = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )
    assert exact.status == "completed"


def test_cancelled_archive_job_cannot_start_sandbox_extraction(tmp_path: Path):
    source = tmp_path / "cancelled.zip"
    _write_zip(source, [("selected.txt", b"cancel me")])
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_cancelled_job",
            approval_granted=True,
        )
    )
    cancelled = cancel_archive_job(plan.operation_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    approval_id, approval_token = _approve_plan(tmp_path, source, plan)
    result = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )
    assert result.status == "cancelled"
    assert result.blocked_reason == "extraction_cancelled"
    assert not (coding_archive_extraction_service.archive_sandbox_root() / "sandbox_cancelled_job").exists()


def test_sandbox_escape_guard_rejects_parent_and_symlink_ancestor(tmp_path: Path):
    extracted = tmp_path / "sandbox" / "extracted"
    extracted.mkdir(parents=True)
    with pytest.raises(ArchiveExtractionFailure, match="sandbox_escape_blocked"):
        _destination_for_member(extracted, "../../escape.txt")

    outside = tmp_path / "outside"
    outside.mkdir()
    (extracted / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArchiveExtractionFailure, match="sandbox_(?:escape|symlink_ancestor)_blocked"):
        _destination_for_member(extracted, "linked/escape.txt")
    assert not (outside / "escape.txt").exists()


def test_configured_sandbox_root_may_not_overlap_selected_project(tmp_path: Path, monkeypatch):
    source = tmp_path / "overlap.zip"
    _write_zip(source, [("safe.txt", b"safe")])
    monkeypatch.setenv("ELYSIA_ARCHIVE_SANDBOX_ROOT", str(tmp_path / "forbidden-sandbox"))
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_overlap",
            approval_granted=True,
        )
    )
    assert plan.status == "blocked"
    assert plan.blocked_reason == "sandbox_root_overlaps_project_root"
    assert not (tmp_path / "forbidden-sandbox").exists()


def test_sandbox_root_symlink_is_blocked(tmp_path: Path, monkeypatch):
    source = tmp_path / "sandbox-root-link.zip"
    _write_zip(source, [("selected.txt", b"safe")])
    real_root = tmp_path.parent / f"archive-real-root-{tmp_path.name}"
    real_root.mkdir(mode=0o700)
    linked_root = tmp_path.parent / f"archive-linked-root-{tmp_path.name}"
    linked_root.symlink_to(real_root, target_is_directory=True)
    monkeypatch.setattr(coding_archive_extraction_service, "archive_sandbox_root", lambda: linked_root)

    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_linked_root",
            approval_granted=True,
        )
    )

    assert plan.status == "blocked"
    assert plan.blocked_reason == "sandbox_root_symlink_blocked"
    assert not (real_root / "sandbox_linked_root").exists()


def test_actual_byte_limit_removes_member_and_aborted_apply_cleans_sandbox(tmp_path: Path, monkeypatch):
    extracted_root = tmp_path / "bounded-member-root"
    extracted_root.mkdir(mode=0o700)
    with pytest.raises(ArchiveExtractionFailure, match="actual_extraction_bytes_limit"):
        _copy_member_stream(
            io.BytesIO(b"0123456789"),
            extracted_root,
            "selected.txt",
            member_limit=100,
            total_limit=4,
            current_total=0,
            deadline=time.monotonic() + 5,
            cancel_check=lambda: False,
        )
    assert not (extracted_root / "selected.txt").exists()

    source = tmp_path / "bounded.zip"
    _write_zip(source, [("selected.txt", b"0123456789")])
    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_abort_cleanup",
            approval_granted=True,
        )
    )
    approval_id, approval_token = _approve_plan(tmp_path, source, plan)

    def abort_after_partial_write(*args, extracted_root: Path, **kwargs):
        del args, kwargs
        (extracted_root / "partial.txt").write_bytes(b"partial")
        raise ArchiveExtractionFailure("extraction_runtime_limit")

    monkeypatch.setattr(coding_archive_extraction_service, "_extract_zip", abort_after_partial_write)
    result = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )
    assert result.status == "failed"
    assert result.blocked_reason == "extraction_runtime_limit"
    assert result.cleanup_performed is True
    assert not (coding_archive_extraction_service.archive_sandbox_root() / "sandbox_abort_cleanup").exists()


def test_archive_audit_and_request_trace_keep_only_compact_truth(tmp_path: Path):
    sensitive_name = "private-customer-identity.txt"
    sensitive_content = "SECRET-CONTENT-MUST-NOT-ENTER-CENTRAL-AUDIT"
    source = tmp_path / "private-client-sensitive.zip"
    _write_zip(source, [(sensitive_name, sensitive_content.encode())])
    inspection = inspect_archive(
        ArchiveInspectRequest(
            session_id="archive-sanitization-test",
            workspace_root=str(tmp_path),
            archive_path=str(source),
            approval_granted=True,
        )
    )
    assert inspection.status == "completed"
    audit = get_coding_audit_record(inspection.operation_id)
    assert audit is not None
    assert audit["archive_type"] == "zip"
    assert audit["archive_hash"] == inspection.archive_sha256
    assert audit["member_count"] == 1
    assert audit["manifest_hash"] == inspection.manifest_digest
    assert audit["raw_content_logged"] is False

    audit_text = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "coding-audit").glob("*.json"))
    assert sensitive_name not in audit_text
    assert source.name not in audit_text
    assert sensitive_content not in audit_text
    assert "archive-sanitization-test" not in audit_text
    assert str(tmp_path) not in audit_text
    trace = get_request_trace_record(inspection.request_id or "")
    assert trace is not None
    rendered_trace = json.dumps(trace, sort_keys=True)
    assert sensitive_name not in rendered_trace
    assert source.name not in rendered_trace
    assert sensitive_content not in rendered_trace
    assert "archive-sanitization-test" not in rendered_trace
    assert str(tmp_path) not in rendered_trace
    tool = trace["snapshot"]["tools_used"][0]
    assert tool["archive_hash"] == inspection.archive_sha256
    assert tool["manifest_hash"] == inspection.manifest_digest
    assert tool["member_count"] == 1
    assert tool["project_files_mutated"] is False

    plan = plan_archive_extraction(
        ArchiveExtractionPlanRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            selected_member_indexes=[0],
            sandbox_id="sandbox_audit_proof",
            approval_granted=True,
        )
    )
    approval_id, approval_token = _approve_plan(tmp_path, source, plan)
    result = apply_archive_extraction(
        _apply_request(
            root=tmp_path,
            source=source,
            plan=plan,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )
    assert result.status == "completed"
    apply_trace = get_request_trace_record(result.request_id or "")
    assert apply_trace is not None
    apply_tool = apply_trace["snapshot"]["tools_used"][0]
    assert apply_tool["sandbox_files_written"] is True
    assert apply_tool["project_files_mutated"] is False
    assert apply_tool["extracted_file_count"] == 1

    audit_text = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "coding-audit").glob("*.json"))
    assert sensitive_name not in audit_text
    assert source.name not in audit_text
    assert sensitive_content not in audit_text
    assert "archive-sanitization-test" not in audit_text
    assert str(tmp_path) not in audit_text
    rendered_apply_trace = json.dumps(apply_trace, sort_keys=True)
    assert sensitive_name not in rendered_apply_trace
    assert source.name not in rendered_apply_trace
    assert sensitive_content not in rendered_apply_trace
    assert str(tmp_path) not in rendered_apply_trace

    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "archive-artifacts").glob("*.json"))
    assert sensitive_name in artifact_text
    assert sensitive_content not in artifact_text


def test_archive_route_requires_explicit_approval_before_member_listing(tmp_path: Path):
    source = tmp_path / "route.zip"
    _write_zip(source, [("safe.txt", b"safe")])
    request = ArchiveInspectRequest(workspace_root=str(tmp_path), archive_path=str(source), approval_granted=False)
    blocked = post_archive_inspect(request)
    assert blocked["approval_state"] == "needed"
    assert blocked["data"]["archive"]["status"] == "approval_required"
    assert blocked["data"]["archive"]["members"] == []
    completed = post_archive_inspect(request.model_copy(update={"approval_granted": True}))
    assert completed["approval_state"] == "approved"
    assert completed["data"]["archive"]["status"] == "completed"
    assert completed["data"]["archive"]["member_count"] == 1


def test_archive_source_must_be_a_regular_file(tmp_path: Path):
    source = tmp_path / "not-a-file.zip"
    os.mkfifo(source)
    response = inspect_archive(
        ArchiveInspectRequest(
            workspace_root=str(tmp_path),
            archive_path=str(source),
            approval_granted=True,
        )
    )
    assert response.status == "blocked"
    assert response.blocked_reason == "regular_file_required"
    assert response.member_count == 0


def test_external_worker_lane_is_list_only_and_rejects_other_formats(tmp_path: Path):
    source = tmp_path / "synthetic.zip"
    source.write_bytes(b"not opened")
    with pytest.raises(ExternalListError, match="unsupported_external_archive_type"):
        list_external_archive(source, archive_type="zip")


def test_7z_worker_lists_synthetic_fixture_without_enabling_extraction(tmp_path: Path):
    executable = shutil.which("7zz") or shutil.which("7z")
    if executable is None:
        pytest.skip("7z listing tool is unavailable")
    input_file = tmp_path / "synthetic-input.txt"
    input_file.write_text("synthetic 7z payload", encoding="utf-8")
    source = tmp_path / "synthetic.7z"
    completed = subprocess.run(
        [executable, "a", "-t7z", "-bd", "-y", str(source), input_file.name],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0
    inspection = inspect_archive_path(source)
    assert inspection["status"] == "completed"
    assert inspection["detected_type"] == "7z"
    assert inspection["member_count"] == 1
    assert inspection["members"][0].extractable is False
    assert inspection["descriptor"].extraction_state == "list_only"


def test_rar_signature_uses_license_sensitive_list_only_lane_and_fails_closed(tmp_path: Path):
    source = tmp_path / "synthetic.rar"
    source.write_bytes(b"Rar!\x1a\x07\x01\x00" + b"synthetic malformed RAR fixture")
    inspection = inspect_archive_path(source)
    assert inspection["detected_type"] == "rar"
    assert inspection["descriptor"].extraction_state == "lab_only"
    assert inspection["descriptor"].tool_license_status == "mixed_multiverse_nonfree_sensitive"
    assert inspection["status"] == "blocked"
    assert inspection["member_count"] == 0
    assert inspection["blocked_reason"].startswith("archive_") or "listing" in inspection["blocked_reason"]
