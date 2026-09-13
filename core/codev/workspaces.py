"""Native workspace operations governed by the shared Codev grant authority."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import difflib
from hashlib import sha256
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.api.coding_path_guard_service import guard_workspace_path
from app.api.coding_repo_approval_service import _candidate
from app.api.coding_secret_scan_service import scan_preview_for_secrets
from core.codev.approvals import PLANS
from core.codev.contracts import Actor, ChangePlan, FileChange, OperationReceipt, ResultArtifact, WorkspaceDescriptor, WorkspaceFile
from core.codev.filesystem import read_bytes, _directory
from core.codev.grants import GRANTS, GrantDenied, iso_now, utc_now
from core.codev.identity import bind_client, bind_workspace
from core.codev.revisions import denied_path, relative_path, workspace_hash


@dataclass
class NativeWorkspace:
    workspace_id: str
    actor: Actor
    root: Path
    identity: tuple[int, int]
    revision: int = 0
    base_revision: int = 0
    base_hash: str | None = None
    snapshot_hash: str = field(default_factory=lambda: workspace_hash([]))
    files: list[WorkspaceFile] = field(default_factory=list)
    receipts: list[OperationReceipt] = field(default_factory=list)
    command_runs: set[str] = field(default_factory=set)
    lock: RLock = field(default_factory=RLock)


_WORKSPACES: dict[str, NativeWorkspace] = {}
_LOCK = RLock()


def select_workspace(actor: Actor, root_path: str) -> WorkspaceDescriptor:
    if actor.client_kind != "native":
        raise GrantDenied("native_workspace_selection_required")
    root, _, error = _candidate(root_path)
    if error:
        raise GrantDenied(error)
    info = root.lstat()
    if info.st_uid != os.getuid():
        raise GrantDenied("workspace_root_not_owned_by_local_user")
    # Selection creates a descriptor; it grants no files or operation authority.
    value = NativeWorkspace(f"workspace_{uuid4().hex}", actor, root, (info.st_dev, info.st_ino))
    with _LOCK:
        if len(_WORKSPACES) >= 128:
            raise GrantDenied("workspace_capacity_reached")
        _WORKSPACES[value.workspace_id] = value
    return _descriptor(value)


def get_workspace(actor: Actor, workspace_id: str, *, require_directory: bool = True) -> NativeWorkspace:
    with _LOCK:
        value = _WORKSPACES.get(workspace_id)
    if not value or value.actor != actor:
        raise GrantDenied("workspace_not_found_for_client")
    if not require_directory:
        return value
    try:
        info = value.root.lstat()
        if value.root.is_symlink() or (info.st_dev, info.st_ino) != value.identity:
            raise GrantDenied("workspace_directory_changed")
    except OSError as exc:
        raise GrantDenied("workspace_unavailable") from exc
    return value


@contextmanager
def _scope(value: NativeWorkspace):
    with bind_client(value.actor.client_id), bind_workspace(value.root):
        guarded = guard_workspace_path(workspace_root=str(value.root), target_path=".", allow_directory=True)
        if not guarded.allowed:
            raise GrantDenied(guarded.reason)
        yield


def _descriptor(value: NativeWorkspace) -> WorkspaceDescriptor:
    grant = GRANTS.get(value.actor, value.workspace_id)
    active = grant and not grant.revoked and datetime.fromisoformat(grant.expires_at) > utc_now()
    return WorkspaceDescriptor(workspace_id=value.workspace_id, workspace_type="local_repository",
        label=value.root.name[:120] or "Selected repository", owner=value.actor, base_revision=value.base_revision,
        current_revision=value.revision, base_hash=value.base_hash or value.snapshot_hash, content_hash=value.snapshot_hash,
        files=[item.model_copy(deep=True) for item in value.files] if active else [],
        allowed_operations=list(grant.scopes) if active else [], grant_epoch=grant.epoch if grant else 0,
        denied_classes=["secrets", "sealed_memory", "symlinks", "hardlinks", "generated_dependencies", "arbitrary_shell", "network"],
        dirty=value.base_hash is not None and value.snapshot_hash != value.base_hash)


def grant_workspace(actor: Actor, workspace_id: str, *, scopes: list[str], files: list[str],
                    command_ids: list[str], expected_epoch: int, explicitly_approved: bool) -> dict:
    value = get_workspace(actor, workspace_id)
    with value.lock, _scope(value):
        for path in files:
            guarded = guard_workspace_path(workspace_root=str(value.root), target_path=relative_path(path))
            if not guarded.allowed:
                raise GrantDenied(guarded.reason)
        grant = GRANTS.issue(actor=actor, workspace_id=workspace_id, scopes=scopes, files=files,
            command_ids=command_ids, expected_epoch=expected_epoch, explicitly_approved=explicitly_approved)
        _refresh(value)
        return {"workspace": _descriptor(value).model_dump(), "grant": grant.model_dump()}


def revoke_workspace(actor: Actor, workspace_id: str) -> dict:
    # Revocation remains possible after the directory is deleted or replaced.
    with _LOCK:
        value = _WORKSPACES.get(workspace_id)
    if not value or value.actor != actor:
        raise GrantDenied("workspace_not_found_for_client")
    with value.lock, bind_client(actor.client_id):
        from app.api.coding_process_service import cancel_command
        from app.api.schemas.coding_commands import CodingCommandCancelRequest
        grant = GRANTS.revoke(actor, workspace_id)
        PLANS.discard(actor, workspace_id)
        from core.codev.actions import cancel_workspace_chats
        cancel_workspace_chats(actor, workspace_id)
        for run_id in value.command_runs:
            cancel_command(CodingCommandCancelRequest(run_id=run_id))
        value.files = []
        return {"revoked": True, "grant_epoch": grant.epoch if grant else 0}


def tree(actor: Actor, workspace_id: str) -> dict:
    value = get_workspace(actor, workspace_id)
    GRANTS.require(actor, workspace_id, "metadata")
    entries = []
    visited = 0
    with value.lock, _scope(value), _directory(value.root) as root_fd:
        for current, directories, filenames, directory_fd in os.fwalk(".", dir_fd=root_fd, follow_symlinks=False):
            prefix = current.removeprefix("./")
            prefix = "" if prefix == "." else prefix + "/"
            directories[:] = sorted(name for name in directories if not _denied(prefix + name))
            if len(Path(prefix).parts) >= 12:
                directories[:] = []
            visited += 1
            for name in sorted(filenames):
                path = prefix + name
                if _denied(path):
                    continue
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                import stat
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    continue
                entries.append({"path": path, "size_bytes": info.st_size})
                if len(entries) >= 2000:
                    return {"files": entries, "truncated": True}
            if visited >= 4000:
                return {"files": entries, "truncated": True}
    return {"files": entries, "truncated": False}


def _denied(path: str) -> bool:
    try:
        return denied_path(path)
    except ValueError:
        return True


def _refresh(value: NativeWorkspace) -> None:
    grant = GRANTS.get(value.actor, value.workspace_id)
    selected = grant.files if grant and "read" in grant.scopes and not grant.revoked else []
    files = []
    with _scope(value):
        for path in selected:
            GRANTS.require(value.actor, value.workspace_id, "read", files=[path], epoch=grant.epoch)
            guarded = guard_workspace_path(workspace_root=str(value.root), target_path=path)
            if not guarded.allowed:
                raise GrantDenied(guarded.reason)
            size = guarded.target_path.lstat().st_size
            if size > 131072:
                files.append(WorkspaceFile(path=path, size_bytes=size, availability="oversized", provenance="local_file"))
                continue
            raw = read_bytes(value.root, path, limit=131072)
            digest = sha256(raw).hexdigest()
            try:
                text = raw.decode("utf-8")
                if "\0" in text:
                    raise UnicodeError()
                availability = "excluded" if scan_preview_for_secrets(text) else "text"
                text = text if availability == "text" else None
            except UnicodeError:
                text, availability = None, "binary"
            files.append(WorkspaceFile(path=path, size_bytes=len(raw), content_hash=digest,
                                       availability=availability, text=text, provenance="local_file"))
    digest = workspace_hash(files)
    if digest != value.snapshot_hash:
        value.revision += 1
        value.snapshot_hash = digest
    if value.base_hash is None and files:
        value.base_hash, value.base_revision = digest, value.revision
    value.files = files


def snapshot(actor: Actor, workspace_id: str) -> WorkspaceDescriptor:
    value = get_workspace(actor, workspace_id)
    GRANTS.require(actor, workspace_id, "metadata")
    with value.lock:
        _refresh(value)
        return _descriptor(value)


def plan_patch(actor: Actor, workspace_id: str, *, edits: dict[str, str], revision: int, summary: str) -> ChangePlan:
    value = get_workspace(actor, workspace_id)
    with value.lock:
        grant = GRANTS.require(actor, workspace_id, "propose", files=list(edits))
        _refresh(value)
        if value.revision != revision:
            raise GrantDenied("workspace_revision_conflict")
        if not edits or len(edits) > 20:
            raise GrantDenied("bounded_change_set_required")
        by_path = {item.path: item for item in value.files}
        changes = []
        for path, updated in edits.items():
            original = by_path.get(path)
            if not original or original.text is None:
                raise GrantDenied("approved_text_source_unavailable")
            if len(updated.encode()) > 131072 or scan_preview_for_secrets(updated):
                raise GrantDenied("proposed_content_limit_or_secret")
            from app.api.coding_file_type_registry import detect_file_type
            from app.api.coding_file_adapter_service import validate_patch_for_descriptor
            okay, reason = validate_patch_for_descriptor(detect_file_type(Path(path), original.text.encode()[:4096]), new_text=updated)
            if not okay:
                raise GrantDenied(reason)
            if updated == original.text:
                continue
            lines = difflib.unified_diff(original.text.splitlines(keepends=True), updated.splitlines(keepends=True),
                                         fromfile="a/" + path, tofile="b/" + path)
            diff = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines)
            changes.append(FileChange(path=path, base_hash=original.content_hash, new_text=updated,
                                      new_hash=sha256(updated.encode()).hexdigest(), diff=diff))
        return PLANS.register(ChangePlan(plan_id=f"plan_{uuid4().hex}", workspace_id=workspace_id, actor=actor,
            base_revision=value.revision, workspace_hash=value.snapshot_hash, grant_epoch=grant.epoch,
            plan_hash="0" * 64, summary=summary[:2000], changes=changes, cwd_label=value.root.name,
            expected_checks=["Exact source hash", "File type and syntax guard", "Secret scan", "Post-write hash"],
            risks=["Each file requires its current source hash. Multi-file failure is reported as partial."],
            expires_at=(utc_now() + timedelta(minutes=5)).isoformat(), recovery_note="A private exact-byte backup precedes each replacement."))


def _remember(value: NativeWorkspace, receipt: OperationReceipt) -> OperationReceipt:
    with value.lock:
        value.receipts = [item for item in value.receipts if item.operation_id != receipt.operation_id][-39:] + [receipt]
    return receipt


def apply_plan(actor: Actor, workspace_id: str, *, plan_id: str, approval_id: str, approval_token: str) -> OperationReceipt:
    from app.api.coding_operation_service import approve_operation
    from app.api.schemas.coding_operations import CodingOperationApproveRequest
    from app.api.schemas.coding_patch import CodingPatchApplyRequest
    from core.codev.service import apply_patch_with_approval
    value = get_workspace(actor, workspace_id)
    with value.lock, _scope(value):
        _refresh(value)
        if PLANS.get(actor, plan_id).workspace_id != workspace_id:
            raise GrantDenied("approval_workspace_mismatch")
        plan = PLANS.consume(actor, approval_id, approval_token, plan_id=plan_id,
                             revision=value.revision, workspace_hash=value.snapshot_hash)
        if plan.command_id:
            raise GrantDenied("wrong_operation_class")
        changed, artifacts, warnings = [], [], []
        audit_written, verification = True, "passed"
        for change in plan.changes:
            try:
                GRANTS.require(actor, workspace_id, "apply", files=[change.path], epoch=plan.grant_epoch)
                patch_hash = sha256(change.diff.encode()).hexdigest()[:32]
                child = approve_operation(CodingOperationApproveRequest(operation_kind="patch_apply",
                    operation_summary=plan.summary, workspace_root=str(value.root), exact_files=[change.path],
                    source_hash=change.base_hash, plan_hash=patch_hash, allowed_mutation_class="text_patch",
                    operator_approved=True, rollback_note=plan.recovery_note))
                result = apply_patch_with_approval(CodingPatchApplyRequest(workspace_root=str(value.root), target_file=change.path,
                    proposed_diff=change.diff, expected_content_hash=change.base_hash, patch_hash=patch_hash,
                    approval_mode="apply_with_approval", approval_id=child.approval_id, approval_token=child.approval_token,
                    operator_approved=True))
                audit_written = audit_written and result.audit_written
                warnings.extend(result.warnings)
                if result.mutation_performed:
                    changed.append(change.path)
                if result.rollback_receipt_id:
                    artifacts.append(ResultArtifact(artifact_id=result.rollback_receipt_id, label="Source backup: " + change.path,
                        content_type="application/octet-stream", relative_path=result.backup_relative_path))
                if result.status != "applied":
                    raise GrantDenied(result.blocked_reason or result.status)
                if sha256(read_bytes(value.root, change.path, limit=131072)).hexdigest() != change.new_hash:
                    raise GrantDenied("post_write_verification_failed")
            except (ValueError, OSError) as exc:
                warnings.append(str(exc) if isinstance(exc, GrantDenied) else type(exc).__name__)
                verification = "required"
                break
        try:
            _refresh(value)
        except (ValueError, OSError):
            verification = "required"
        status = "completed" if len(changed) == len(plan.changes) and verification == "passed" else "partial" if changed else "failed"
        return _remember(value, OperationReceipt(operation_id=f"operation_{uuid4().hex}", request_id=plan.plan_id,
            workspace_id=workspace_id, status=status, summary="Reviewed changes applied." if status == "completed" else "Inspect the partial result before continuing.",
            base_revision=plan.base_revision, resulting_revision=value.revision, files_inspected=[item.path for item in plan.changes],
            files_changed=changed, artifacts=artifacts, recovery_note="Restore an exact backup only after reviewing the current file.",
            verification=verification, audit_written=audit_written, warnings=warnings, created_at=iso_now()))


def receipts(actor: Actor, workspace_id: str) -> list[dict]:
    value = get_workspace(actor, workspace_id, require_directory=False)
    with value.lock:
        return [receipt.model_dump() for receipt in value.receipts]
