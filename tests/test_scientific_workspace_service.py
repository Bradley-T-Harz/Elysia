from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.api import scientific_workspace_service as service
from app.api.schemas.scientific_workspace import (
    ScientificWorkspaceApplyRequest,
    ScientificWorkspaceManifestRequest,
    ScientificWorkspacePlanRequest,
    ScientificWorkspaceRevokeRequest,
    ScientificWorkspaceStatusRequest,
)


@pytest.fixture(autouse=True)
def _clear_scientific_workspace_plans():
    service.clear_scientific_workspace_plans_for_tests()
    yield
    service.clear_scientific_workspace_plans_for_tests()


@pytest.fixture
def authority(tmp_path: Path, monkeypatch):
    state = {
        "owner": "owner-alpha",
    }

    project_owners = {
        "project-alpha": "owner-alpha",
        "project-alpha-2": "owner-alpha",
        "project-beta": "owner-beta",
    }

    def current_user_id():
        return state["owner"]

    def project_metadata(project_id: str):
        owner = project_owners.get(project_id)

        if owner is None:
            raise service.ProjectServiceError(
                "project_not_found"
            )

        return {
            "project_id": project_id,
            "owner_user_id": owner,
        }

    registry = (
        tmp_path
        / "authority"
        / "approved-scientific-workspaces.json"
    )

    monkeypatch.setattr(
        service,
        "current_user_id",
        current_user_id,
    )

    monkeypatch.setattr(
        service,
        "get_project_metadata",
        project_metadata,
    )

    monkeypatch.setattr(
        service,
        "scientific_workspace_registry_path",
        lambda: registry,
    )

    workspace = tmp_path / "scientific-workspace"
    workspace.mkdir()

    return {
        "state": state,
        "registry": registry,
        "workspace": workspace,
        "project_owners": project_owners,
    }


def _approve(
    *,
    project_id: str,
    workspace: Path,
):
    plan = service.plan_scientific_workspace_approval(
        ScientificWorkspacePlanRequest(
            project_id=project_id,
            workspace_root=str(workspace),
        )
    )

    assert plan.status == "approval_required"
    assert plan.plan_id
    assert plan.plan_hash
    assert plan.raw_path_exposed is False

    result = service.apply_scientific_workspace_approval(
        ScientificWorkspaceApplyRequest(
            project_id=project_id,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            operator_approved=True,
            confirmation_phrase=(
                "Approve exact scientific workspace"
            ),
        )
    )

    assert result.status == "approved"
    assert result.approved is True
    assert result.revoked is False
    assert result.raw_path_exposed is False

    return plan, result


def _manifest(
    *,
    project_id: str,
    workspace: Path,
    max_entries: int = 500,
):
    return service.build_scientific_workspace_manifest(
        ScientificWorkspaceManifestRequest(
            project_id=project_id,
            workspace_root=str(workspace),
            max_entries=max_entries,
        )
    )


def test_unauthenticated_and_cross_owner_access_fail_closed(
    authority,
):
    workspace = authority["workspace"]
    state = authority["state"]

    state["owner"] = None

    plan = service.plan_scientific_workspace_approval(
        ScientificWorkspacePlanRequest(
            project_id="project-alpha",
            workspace_root=str(workspace),
        )
    )

    assert plan.status == "blocked"
    assert (
        plan.blocked_reason
        == "scientific_workspace_authentication_required"
    )

    state["owner"] = "owner-beta"

    other_plan = service.plan_scientific_workspace_approval(
        ScientificWorkspacePlanRequest(
            project_id="project-alpha",
            workspace_root=str(workspace),
        )
    )

    assert other_plan.status == "blocked"
    assert (
        other_plan.blocked_reason
        == "scientific_workspace_project_owner_mismatch"
    )


def test_exact_approval_is_private_project_bound_and_single_use(
    authority,
):
    workspace = authority["workspace"]
    registry = authority["registry"]

    plan, _ = _approve(
        project_id="project-alpha",
        workspace=workspace,
    )

    assert registry.is_file()
    assert registry.stat().st_mode & 0o777 == 0o600
    assert registry.parent.stat().st_mode & 0o777 == 0o700

    status = service.scientific_workspace_status(
        ScientificWorkspaceStatusRequest(
            project_id="project-alpha",
            workspace_root=str(workspace),
        )
    )

    assert status.status == "approved"
    assert status.approved is True
    assert status.raw_path_exposed is False

    serialized = json.dumps(
        status.model_dump(mode="json")
    )

    assert str(workspace) not in serialized

    replay = service.apply_scientific_workspace_approval(
        ScientificWorkspaceApplyRequest(
            project_id="project-alpha",
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            operator_approved=True,
            confirmation_phrase=(
                "Approve exact scientific workspace"
            ),
        )
    )

    assert replay.status == "blocked"
    assert replay.blocked_reason == "plan_already_used"


def test_workspace_grant_does_not_cross_project_or_account(
    authority,
):
    workspace = authority["workspace"]
    state = authority["state"]

    _approve(
        project_id="project-alpha",
        workspace=workspace,
    )

    same_owner_other_project = _manifest(
        project_id="project-alpha-2",
        workspace=workspace,
    )

    assert same_owner_other_project.status == "blocked"
    assert (
        "scientific_workspace_not_approved"
        in same_owner_other_project.warnings
    )

    state["owner"] = "owner-beta"

    cross_account = _manifest(
        project_id="project-alpha",
        workspace=workspace,
    )

    assert cross_account.status == "blocked"
    assert (
        "scientific_workspace_project_owner_mismatch"
        in cross_account.warnings
    )


def test_revocation_wins_immediately(
    authority,
):
    workspace = authority["workspace"]

    _approve(
        project_id="project-alpha",
        workspace=workspace,
    )

    before = _manifest(
        project_id="project-alpha",
        workspace=workspace,
    )

    assert before.status == "completed"

    revoked = service.revoke_scientific_workspace(
        ScientificWorkspaceRevokeRequest(
            project_id="project-alpha",
            workspace_root=str(workspace),
            operator_approved=True,
            confirmation_phrase=(
                "Revoke scientific workspace approval"
            ),
        )
    )

    assert revoked.revoked is True
    assert revoked.approved is False

    after = _manifest(
        project_id="project-alpha",
        workspace=workspace,
    )

    assert after.status == "blocked"
    assert (
        "scientific_workspace_revoked"
        in after.warnings
    )


def test_broad_and_symlink_workspace_roots_are_not_grantable(
    authority,
    tmp_path: Path,
):
    broad = service.plan_scientific_workspace_approval(
        ScientificWorkspacePlanRequest(
            project_id="project-alpha",
            workspace_root="/tmp",
        )
    )

    assert broad.status == "blocked"
    assert broad.blocked_reason == "workspace_root_too_broad"

    real_root = tmp_path / "real-science-root"
    real_root.mkdir()

    linked_root = tmp_path / "linked-science-root"
    linked_root.symlink_to(
        real_root,
        target_is_directory=True,
    )

    linked = service.plan_scientific_workspace_approval(
        ScientificWorkspacePlanRequest(
            project_id="project-alpha",
            workspace_root=str(linked_root),
        )
    )

    assert linked.status == "blocked"
    assert linked.blocked_reason == "workspace_root_symlink"


def test_manifest_is_metadata_only_private_and_source_immutable(
    authority,
    monkeypatch,
):
    workspace = authority["workspace"]

    csv_file = workspace / "measurements.csv"
    csv_file.write_bytes(
        b"site,value\nalpha,1\nbeta,2\n"
    )

    geojson = workspace / "watershed.geojson"
    geojson.write_text(
        '{"type":"FeatureCollection","features":[]}',
        encoding="utf-8",
    )

    parquet = workspace / "observations.parquet"
    parquet.write_bytes(
        b"not parsed by manifest"
    )

    notes = workspace / "notes.txt"
    notes.write_text(
        "manifest must not read this",
        encoding="utf-8",
    )

    nested = workspace / "nested"
    nested.mkdir()

    netcdf = nested / "climate.nc"
    netcdf.write_bytes(
        b"netcdf fixture bytes"
    )

    blocked_git = workspace / ".git"
    blocked_git.mkdir()

    blocked_secret = blocked_git / "secret.csv"
    blocked_secret.write_bytes(
        b"secret,value\nx,7\n"
    )

    symlink_target = workspace / "symlink-target.csv"
    symlink_target.write_bytes(
        b"a,b\n1,2\n"
    )

    symlink_entry = workspace / "linked.csv"
    symlink_entry.symlink_to(
        symlink_target,
    )

    hard_source = workspace / "hard-source.csv"
    hard_source.write_bytes(
        b"a,b\n3,4\n"
    )

    hard_alias = workspace / "hard-alias.csv"
    os.link(
        hard_source,
        hard_alias,
    )

    zarr = workspace / "hydrology.zarr"
    zarr.mkdir()

    (zarr / ".zgroup").write_text(
        '{"zarr_format":2}',
        encoding="utf-8",
    )

    array = zarr / "flow"
    array.mkdir()

    (array / ".zarray").write_text(
        (
            '{"zarr_format":2,'
            '"shape":[2],'
            '"chunks":[2],'
            '"dtype":"<f8",'
            '"compressor":null,'
            '"fill_value":0,'
            '"order":"C",'
            '"filters":null}'
        ),
        encoding="utf-8",
    )

    (array / "0").write_bytes(
        b"\x00" * 16
    )

    source_files = [
        csv_file,
        geojson,
        parquet,
        notes,
        netcdf,
        blocked_secret,
        symlink_target,
        hard_source,
        hard_alias,
        zarr / ".zgroup",
        array / ".zarray",
        array / "0",
    ]

    before = {
        path.relative_to(workspace).as_posix():
        path.read_bytes()
        for path in source_files
        if not path.is_symlink()
    }

    _approve(
        project_id="project-alpha",
        workspace=workspace,
    )

    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    workspace_absolute = Path(
        os.path.abspath(str(workspace))
    )

    def inside_workspace(path: Path) -> bool:
        lexical = Path(
            os.path.abspath(str(path))
        )

        try:
            lexical.relative_to(
                workspace_absolute
            )
            return True
        except ValueError:
            return False

    def guarded_read_bytes(path: Path):
        if inside_workspace(path):
            raise AssertionError(
                "manifest attempted source-content read_bytes"
            )

        return original_read_bytes(path)

    def guarded_read_text(
        path: Path,
        *args,
        **kwargs,
    ):
        if inside_workspace(path):
            raise AssertionError(
                "manifest attempted source-content read_text"
            )

        return original_read_text(
            path,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "read_bytes",
        guarded_read_bytes,
    )

    monkeypatch.setattr(
        Path,
        "read_text",
        guarded_read_text,
    )

    manifest = _manifest(
        project_id="project-alpha",
        workspace=workspace,
    )

    monkeypatch.setattr(
        Path,
        "read_bytes",
        original_read_bytes,
    )

    monkeypatch.setattr(
        Path,
        "read_text",
        original_read_text,
    )

    assert manifest.status == "completed"
    assert manifest.source_mutated is False
    assert manifest.network_used is False
    assert manifest.raw_paths_exposed is False

    entries = {
        item.relative_path: item
        for item in manifest.entries
    }

    assert "measurements.csv" in entries
    assert "watershed.geojson" in entries
    assert "observations.parquet" in entries
    assert "notes.txt" in entries
    assert "nested/climate.nc" in entries
    assert "hydrology.zarr" in entries

    assert entries["measurements.csv"].supported_scientific_data
    assert entries["watershed.geojson"].supported_scientific_data
    assert entries["observations.parquet"].supported_scientific_data
    assert entries["nested/climate.nc"].supported_scientific_data

    assert (
        entries["notes.txt"].supported_scientific_data
        is False
    )

    assert (
        entries["hydrology.zarr"].entry_kind
        == "directory_store"
    )

    assert not any(
        key.startswith("hydrology.zarr/")
        for key in entries
    )

    assert "linked.csv" not in entries
    assert "hard-source.csv" not in entries
    assert "hard-alias.csv" not in entries

    assert not any(
        key.startswith(".git/")
        for key in entries
    )

    serialized = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
    )

    assert str(workspace) not in serialized

    for item in manifest.entries:
        assert not Path(
            item.relative_path
        ).is_absolute()

        assert (
            item.raw_absolute_path_exposed
            is False
        )

        assert item.source_mutated is False

    after = {
        path.relative_to(workspace).as_posix():
        path.read_bytes()
        for path in source_files
        if not path.is_symlink()
    }

    assert after == before


def test_manifest_limit_truncates_without_expanding_authority(
    authority,
):
    workspace = authority["workspace"]

    for index in range(8):
        (
            workspace
            / f"dataset-{index}.csv"
        ).write_text(
            "x,y\n1,2\n",
            encoding="utf-8",
        )

    _approve(
        project_id="project-alpha",
        workspace=workspace,
    )

    manifest = _manifest(
        project_id="project-alpha",
        workspace=workspace,
        max_entries=3,
    )

    assert manifest.status == "completed"
    assert manifest.truncated is True
    assert len(manifest.entries) == 3
    assert manifest.raw_paths_exposed is False


def test_invalid_private_registry_fails_closed(
    authority,
):
    workspace = authority["workspace"]
    registry = authority["registry"]

    registry.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    registry.write_text(
        "{broken-json",
        encoding="utf-8",
    )

    status = service.scientific_workspace_status(
        ScientificWorkspaceStatusRequest(
            project_id="project-alpha",
            workspace_root=str(workspace),
        )
    )

    assert status.status == "blocked"
    assert (
        status.blocked_reason
        == "scientific_workspace_registry_requires_recovery"
    )
