"""Exact-planned, selected-file, sandbox-only archive extraction."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import time
from typing import Any, BinaryIO, Callable
from uuid import uuid4
import zipfile

from app.api.coding_archive_artifact_service import create_archive_artifact
from app.api.coding_archive_inspection_service import canonical_digest
from app.api.coding_archive_job_service import archive_job_cancel_requested
from app.api.coding_archive_policy_service import load_archive_limits
from app.api.coding_operation_hash_service import operation_plan_hash
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_path_guard_service import GuardedPath, hash_path
from app.api.project_paths import elysia_repo_root
from app.api.schemas.archive import (
    ArchiveExtractionApplyRequest,
    ArchiveExtractionPlan,
    ArchiveExtractionPlanRequest,
    ArchiveExtractionResult,
)


SANDBOX_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,63}$")
DEFAULT_SANDBOX_ROOT = Path("/tmp/elysia-archiveforge-sandboxes")
CHUNK_SIZE = 1024 * 1024


class ArchiveExtractionFailure(RuntimeError):
    """Bounded extraction refusal/abort with a stable compact reason."""


def archive_sandbox_root() -> Path:
    configured = os.environ.get("ELYSIA_ARCHIVE_SANDBOX_ROOT", "").strip()
    return Path(configured).expanduser().resolve(strict=False) if configured else DEFAULT_SANDBOX_ROOT


def _paths_overlap(first: Path, second: Path) -> bool:
    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def _validate_sandbox_root(
    root: Path,
    *,
    workspace_root: Path | None = None,
    approved_root: Path | None = None,
) -> None:
    if root.is_symlink():
        raise ArchiveExtractionFailure("sandbox_root_symlink_blocked")
    if root.exists():
        root_stat = root.stat()
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ArchiveExtractionFailure("sandbox_root_not_directory")
        if hasattr(os, "geteuid") and root_stat.st_uid != os.geteuid():
            raise ArchiveExtractionFailure("sandbox_root_not_owned_by_process_user")
    resolved = root.resolve(strict=False)
    repo = elysia_repo_root().resolve(strict=False)
    try:
        resolved.relative_to(repo)
    except ValueError:
        pass
    else:
        raise ArchiveExtractionFailure("sandbox_root_inside_elysia_source")
    if resolved in {Path("/"), Path.home().resolve(), Path("/home"), Path("/tmp")}:
        raise ArchiveExtractionFailure("sandbox_root_too_broad")
    for forbidden in (workspace_root, approved_root):
        if forbidden is not None and _paths_overlap(resolved, forbidden.resolve(strict=False)):
            raise ArchiveExtractionFailure("sandbox_root_overlaps_project_root")


def _sandbox_id(value: str | None) -> str:
    candidate = value or f"sandbox_{uuid4().hex[:20]}"
    if not SANDBOX_ID_RE.fullmatch(candidate):
        raise ArchiveExtractionFailure("invalid_sandbox_id")
    return candidate


def _selected_digest(members: list[Any]) -> str:
    payload = [
        {
            "index": member.index,
            "path_hash": member.path_hash,
            "uncompressed_size": member.uncompressed_size,
            "kind": member.kind,
        }
        for member in members
    ]
    return canonical_digest(payload)


def build_extraction_plan(
    payload: ArchiveExtractionPlanRequest,
    *,
    guarded: GuardedPath,
    inspection: dict[str, Any],
    operation_id: str,
    check_destination_exists: bool = True,
) -> ArchiveExtractionPlan:
    archive_sha256 = str(inspection["archive_sha256"] or "unavailable_by_policy")
    manifest_digest = str(inspection["manifest_digest"])
    detected_type = str(inspection["detected_type"])
    sandbox_id = _sandbox_id(payload.sandbox_id)
    sandbox_root = archive_sandbox_root()
    sandbox_boundary_reason: str | None = None
    try:
        _validate_sandbox_root(
            sandbox_root,
            workspace_root=guarded.workspace_root,
            approved_root=guarded.approved_root,
        )
    except ArchiveExtractionFailure as exc:
        sandbox_boundary_reason = str(exc)
    destination = (sandbox_root / sandbox_id / "extracted").resolve(strict=False)
    destination_hash = hash_path(destination)
    selected_indexes = sorted(set(int(index) for index in payload.selected_member_indexes))
    members_by_index = {member.index: member for member in inspection["members"]}
    selected = [members_by_index[index] for index in selected_indexes if index in members_by_index]
    projected_write = sum(member.uncompressed_size for member in selected if member.is_regular_file)
    policy = load_archive_limits()
    blocked_reason: str | None = sandbox_boundary_reason
    warnings = [
        "This plan extracts only the selected regular files into a new server-owned sandbox.",
        "No extracted content will be opened, executed, imported, installed, trusted, indexed, or moved into a project.",
    ]
    descriptor = inspection["descriptor"]
    if blocked_reason:
        pass
    elif check_destination_exists and (
        (sandbox_root / sandbox_id).exists() or (sandbox_root / sandbox_id).is_symlink()
    ):
        blocked_reason = "sandbox_already_exists"
    elif detected_type not in {"zip", "tar", "tar_gz"} or not descriptor.selected_sandbox_extraction_supported:
        blocked_reason = "format_not_enabled_for_sandbox_extraction"
    elif not payload.approval_granted:
        blocked_reason = "explicit_plan_approval_required"
    elif not selected_indexes:
        blocked_reason = "selected_members_required"
    elif len(selected) != len(selected_indexes):
        blocked_reason = "selected_member_index_not_found"
    elif any(risk.blocks_extraction for risk in inspection["risk_flags"]):
        blocked_reason = "archive_has_blocking_risk"
    elif any(not member.extractable for member in selected):
        blocked_reason = "selected_member_not_extractable"
    elif any(member.is_directory for member in selected):
        blocked_reason = "select_regular_files_only"
    elif projected_write > policy["limits"]["max_extraction_bytes_written"]:
        blocked_reason = "selected_write_bytes_limit"
    selected_digest = _selected_digest(selected)
    plan_hash = operation_plan_hash(
        action="archive_sandbox_extract_selected",
        source_relative_path=guarded.relative_path,
        target_relative_path=None,
        source_hash=archive_sha256,
        details={
            "operation_id": operation_id,
            "archive_type": detected_type,
            "archive_size_bytes": inspection["archive_size_bytes"],
            "manifest_digest": manifest_digest,
            "selected_members_digest": selected_digest,
            "selected_member_count": len(selected),
            "projected_write_bytes": projected_write,
            "sandbox_id": sandbox_id,
            "sandbox_destination_hash": destination_hash,
            "limits": policy["limits"],
            "policy_version": policy["version"],
        },
    )
    artifact = create_archive_artifact(
        "extraction_plan",
        {
            "operation_id": operation_id,
            "status": "blocked" if blocked_reason else "planned",
            "archive_sha256": archive_sha256,
            "manifest_digest": manifest_digest,
            "archive_type": detected_type,
            "selected_members": [member.to_payload() for member in selected],
            "selected_members_digest": selected_digest,
            "sandbox_id": sandbox_id,
            "sandbox_destination_hash": destination_hash,
            "projected_write_bytes": projected_write,
            "plan_hash": plan_hash,
            "policy_version": policy["version"],
            "blocked_reason": blocked_reason,
        },
    )
    return ArchiveExtractionPlan(
        status="blocked" if blocked_reason else "planned",
        operation_id=operation_id,
        file_label=guarded.target_path.name,
        relative_path=guarded.relative_path,
        archive_type=detected_type,
        archive_sha256=archive_sha256,
        archive_size_bytes=int(inspection["archive_size_bytes"]),
        manifest_digest=manifest_digest,
        selected_member_indexes=selected_indexes,
        selected_members_digest=selected_digest,
        selected_file_count=sum(1 for member in selected if member.is_regular_file),
        projected_write_bytes=projected_write,
        sandbox_id=sandbox_id,
        sandbox_destination_hash=destination_hash,
        plan_hash=plan_hash,
        policy_version=str(policy["version"]),
        exact_approval={
            "operation_kind": "archive_extract",
            "exact_files": [guarded.relative_path] if guarded.relative_path else [],
            "source_hash": archive_sha256,
            "plan_hash": plan_hash,
            "allowed_mutation_class": "archive_sandbox_extract",
            "expires_in_seconds": 600,
            "rollback_note": "The operation creates a disposable sandbox only; abort cleanup removes partial output.",
        },
        artifact=artifact,
        blocked_reason=blocked_reason,
        warnings=warnings,
    )


def _destination_for_member(extracted_root: Path, normalized: str) -> Path:
    candidate = (extracted_root / normalized).resolve(strict=False)
    try:
        candidate.relative_to(extracted_root.resolve(strict=False))
    except ValueError as exc:
        raise ArchiveExtractionFailure("sandbox_escape_blocked") from exc
    current = extracted_root
    for part in Path(normalized).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ArchiveExtractionFailure("sandbox_symlink_ancestor_blocked")
    return candidate


def _open_private_member_destination(extracted_root: Path, normalized: str) -> tuple[int, int, str]:
    _destination_for_member(extracted_root, normalized)
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArchiveExtractionFailure("invalid_normalized_member_path")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
    current_descriptor = os.open(extracted_root, directory_flags)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current_descriptor)
            except FileExistsError:
                pass
            next_descriptor = os.open(part, directory_flags, dir_fd=current_descriptor)
            try:
                os.fchmod(next_descriptor, 0o700)
            except Exception:
                os.close(next_descriptor)
                raise
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            file_flags |= os.O_CLOEXEC
        descriptor = os.open(parts[-1], file_flags, 0o600, dir_fd=current_descriptor)
        parent_descriptor = current_descriptor
        current_descriptor = -1
        return descriptor, parent_descriptor, parts[-1]
    finally:
        if current_descriptor >= 0:
            os.close(current_descriptor)


def _copy_member_stream(
    stream: BinaryIO,
    extracted_root: Path,
    normalized: str,
    *,
    member_limit: int,
    total_limit: int,
    current_total: int,
    deadline: float,
    cancel_check: Callable[[], bool],
) -> int:
    descriptor, parent_descriptor, leaf_name = _open_private_member_destination(extracted_root, normalized)
    written = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            while chunk := stream.read(CHUNK_SIZE):
                if cancel_check():
                    raise ArchiveExtractionFailure("extraction_cancelled")
                if time.monotonic() > deadline:
                    raise ArchiveExtractionFailure("extraction_runtime_limit")
                written += len(chunk)
                if written > member_limit:
                    raise ArchiveExtractionFailure("actual_single_file_size_limit")
                if current_total + written > total_limit:
                    raise ArchiveExtractionFailure("actual_extraction_bytes_limit")
                output.write(chunk)
            os.fchmod(output.fileno(), 0o600)
    except Exception:
        try:
            os.unlink(leaf_name, dir_fd=parent_descriptor)
        except FileNotFoundError:
            pass
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)
    return written


def _write_sandbox_json(path: Path, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)


def _snapshot_archive(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    max_input_bytes: int,
    deadline: float,
    cancel_check: Callable[[], bool],
) -> None:
    read_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        read_flags |= os.O_NOFOLLOW
    source_descriptor = -1
    destination_descriptor = -1
    digest = sha256()
    copied = 0
    try:
        source_descriptor = os.open(source, read_flags)
        destination_descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        source_stat = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size != expected_size:
            raise ArchiveExtractionFailure("archive_changed_before_snapshot")
        with os.fdopen(source_descriptor, "rb") as input_stream, os.fdopen(destination_descriptor, "wb") as output_stream:
            source_descriptor = -1
            destination_descriptor = -1
            while chunk := input_stream.read(CHUNK_SIZE):
                if cancel_check():
                    raise ArchiveExtractionFailure("extraction_cancelled")
                if time.monotonic() > deadline:
                    raise ArchiveExtractionFailure("extraction_runtime_limit")
                copied += len(chunk)
                if copied > max_input_bytes or copied > expected_size:
                    raise ArchiveExtractionFailure("archive_snapshot_size_limit")
                digest.update(chunk)
                output_stream.write(chunk)
            os.fchmod(output_stream.fileno(), 0o600)
        if copied != expected_size or digest.hexdigest() != expected_sha256:
            raise ArchiveExtractionFailure("archive_changed_during_snapshot")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if source_descriptor >= 0:
            os.close(source_descriptor)
        if destination_descriptor >= 0:
            os.close(destination_descriptor)


def _extract_zip(
    source: Path,
    *,
    selected_indexes: set[int],
    members_by_index: dict[int, Any],
    extracted_root: Path,
    limits: dict[str, int],
    deadline: float,
    cancel_check: Callable[[], bool],
) -> tuple[int, int]:
    extracted_count = 0
    extracted_bytes = 0
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        for index in sorted(selected_indexes):
            member = members_by_index[index]
            info = infos[index]
            if not member.extractable or not member.is_regular_file or not member.normalized_relative_path:
                raise ArchiveExtractionFailure("selected_member_became_unextractable")
            with archive.open(info, mode="r") as stream:
                extracted_bytes += _copy_member_stream(
                    stream,
                    extracted_root,
                    member.normalized_relative_path,
                    member_limit=limits["max_single_file_bytes"],
                    total_limit=limits["max_extraction_bytes_written"],
                    current_total=extracted_bytes,
                    deadline=deadline,
                    cancel_check=cancel_check,
                )
            extracted_count += 1
    return extracted_count, extracted_bytes


def _extract_tar(
    source: Path,
    *,
    selected_indexes: set[int],
    members_by_index: dict[int, Any],
    extracted_root: Path,
    limits: dict[str, int],
    deadline: float,
    cancel_check: Callable[[], bool],
) -> tuple[int, int]:
    extracted_count = 0
    extracted_bytes = 0
    with tarfile.open(source, mode="r:*") as archive:
        infos = archive.getmembers()
        for index in sorted(selected_indexes):
            member = members_by_index[index]
            info = infos[index]
            if not member.extractable or not member.is_regular_file or not member.normalized_relative_path or not info.isfile():
                raise ArchiveExtractionFailure("selected_member_became_unextractable")
            stream = archive.extractfile(info)
            if stream is None:
                raise ArchiveExtractionFailure("tar_member_stream_unavailable")
            with stream:
                extracted_bytes += _copy_member_stream(
                    stream,
                    extracted_root,
                    member.normalized_relative_path,
                    member_limit=limits["max_single_file_bytes"],
                    total_limit=limits["max_extraction_bytes_written"],
                    current_total=extracted_bytes,
                    deadline=deadline,
                    cancel_check=cancel_check,
                )
            extracted_count += 1
    return extracted_count, extracted_bytes


def apply_extraction_plan(
    payload: ArchiveExtractionApplyRequest,
    *,
    guarded: GuardedPath,
    inspection: dict[str, Any],
    plan: ArchiveExtractionPlan,
    operation_id: str,
) -> ArchiveExtractionResult:
    detected_type = str(inspection["detected_type"])
    base = {
        "operation_id": operation_id,
        "approval_id": payload.approval_id,
        "archive_type": detected_type,
        "archive_sha256": str(inspection["archive_sha256"] or "unavailable_by_policy"),
        "manifest_digest": str(inspection["manifest_digest"]),
        "plan_hash": plan.plan_hash,
        "sandbox_id": plan.sandbox_id,
        "sandbox_destination_hash": plan.sandbox_destination_hash,
    }
    reason: str | None = None
    if archive_job_cancel_requested(operation_id):
        reason = "extraction_cancelled"
    elif not payload.operator_approved:
        reason = "fresh_operator_approval_required"
    elif plan.status != "planned":
        reason = plan.blocked_reason or "extraction_plan_not_ready"
    elif payload.expected_archive_sha256 != inspection["archive_sha256"]:
        reason = "archive_hash_changed"
    elif payload.expected_manifest_digest != inspection["manifest_digest"]:
        reason = "manifest_digest_changed"
    elif payload.expected_plan_hash != plan.plan_hash:
        reason = "extraction_plan_changed"
    if reason:
        return ArchiveExtractionResult(
            status="cancelled" if reason == "extraction_cancelled" else "approval_required" if "approval" in reason else "blocked",
            blocked_reason=reason,
            warnings=["No sandbox was created and no archive member was written."],
            **base,
        )
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind="archive_extract",
        workspace_root=payload.workspace_root,
        exact_files=[payload.archive_path],
        source_hash=str(inspection["archive_sha256"]),
        plan_hash=plan.plan_hash,
        allowed_mutation_class="archive_sandbox_extract",
    )
    if not approval.allowed:
        return ArchiveExtractionResult(
            status="approval_required",
            blocked_reason=approval.reason,
            warnings=["A matching, fresh, unexpired, one-time exact approval is required."],
            **base,
        )
    policy = load_archive_limits()
    limits = policy["limits"]
    sandbox_root = archive_sandbox_root()
    _validate_sandbox_root(
        sandbox_root,
        workspace_root=guarded.workspace_root,
        approved_root=guarded.approved_root,
    )
    sandbox_path = sandbox_root / plan.sandbox_id
    extracted_root = sandbox_path / "extracted"
    if sandbox_path.exists() or sandbox_path.is_symlink():
        return ArchiveExtractionResult(
            status="blocked",
            blocked_reason="sandbox_already_exists",
            warnings=["Approval was consumed, but no existing sandbox was overwritten."],
            **base,
        )
    cleanup_performed = False
    sandbox_created = False
    selected = set(plan.selected_member_indexes)
    members_by_index = {member.index: member for member in inspection["members"]}
    try:
        sandbox_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _validate_sandbox_root(
            sandbox_root,
            workspace_root=guarded.workspace_root,
            approved_root=guarded.approved_root,
        )
        sandbox_root.chmod(0o700)
        sandbox_path.mkdir(mode=0o700)
        sandbox_created = True
        sandbox_path.chmod(0o700)
        extracted_root.mkdir(mode=0o700)
        extracted_root.chmod(0o700)
        deadline = time.monotonic() + limits["max_extraction_runtime_seconds"]
        cancel_check = lambda: archive_job_cancel_requested(operation_id)
        archive_snapshot = sandbox_path / ".archive-input"
        _snapshot_archive(
            guarded.target_path,
            archive_snapshot,
            expected_sha256=str(inspection["archive_sha256"]),
            expected_size=int(inspection["archive_size_bytes"]),
            max_input_bytes=limits["max_archive_input_bytes"],
            deadline=deadline,
            cancel_check=cancel_check,
        )
        if detected_type == "zip":
            extracted_count, extracted_bytes = _extract_zip(
                archive_snapshot,
                selected_indexes=selected,
                members_by_index=members_by_index,
                extracted_root=extracted_root,
                limits=limits,
                deadline=deadline,
                cancel_check=cancel_check,
            )
        elif detected_type in {"tar", "tar_gz"}:
            extracted_count, extracted_bytes = _extract_tar(
                archive_snapshot,
                selected_indexes=selected,
                members_by_index=members_by_index,
                extracted_root=extracted_root,
                limits=limits,
                deadline=deadline,
                cancel_check=cancel_check,
            )
        else:
            raise ArchiveExtractionFailure("format_not_enabled_for_sandbox_extraction")
        if extracted_bytes > plan.projected_write_bytes:
            raise ArchiveExtractionFailure("actual_bytes_exceeded_approved_projection")
        archive_snapshot.unlink(missing_ok=True)
        receipt_payload = {
            **base,
            "status": "completed",
            "selected_members_digest": plan.selected_members_digest,
            "extracted_file_count": extracted_count,
            "extracted_bytes": extracted_bytes,
            "file_mode": "0600",
            "directory_mode": "0700",
            "source_mutated": False,
            "project_root_written": False,
            "install_performed": False,
            "execution_performed": False,
            "network_used": False,
            "policy_version": policy["version"],
        }
        _write_sandbox_json(sandbox_path / "manifest.json", inspection["manifest_payload"])
        _write_sandbox_json(sandbox_path / "risk_report.json", {"risk_flags": [risk.to_payload() for risk in inspection["risk_flags"]]})
        _write_sandbox_json(sandbox_path / "extraction_plan.json", plan.to_payload())
        _write_sandbox_json(sandbox_path / "extraction_receipt.json", receipt_payload)
        artifact = create_archive_artifact("extraction_receipt", receipt_payload)
        return ArchiveExtractionResult(
            status="completed",
            extracted_file_count=extracted_count,
            extracted_bytes=extracted_bytes,
            blocked_member_count=sum(1 for member in inspection["members"] if not member.extractable),
            skipped_member_count=max(0, len(inspection["members"]) - extracted_count),
            artifact=artifact,
            mutation_performed=True,
            warnings=[
                "Selected regular files were written with mode 0600 inside a new mode-0700 disposable sandbox.",
                "The source archive was not changed. No output was installed, executed, imported, opened, trusted, or moved into a project.",
            ],
            **base,
        )
    except (ArchiveExtractionFailure, OSError, RuntimeError, tarfile.TarError, zipfile.BadZipFile) as exc:
        if sandbox_created and sandbox_path.exists():
            shutil.rmtree(sandbox_path)
            cleanup_performed = True
        reason = str(exc) if isinstance(exc, ArchiveExtractionFailure) else "sandbox_extraction_failed"
        return ArchiveExtractionResult(
            status="cancelled" if reason == "extraction_cancelled" else "failed",
            cleanup_performed=cleanup_performed,
            blocked_reason=reason,
            warnings=["Partial sandbox output was removed; the source archive was not changed."],
            **base,
        )


__all__ = (
    "ArchiveExtractionFailure",
    "DEFAULT_SANDBOX_ROOT",
    "apply_extraction_plan",
    "archive_sandbox_root",
    "build_extraction_plan",
)
