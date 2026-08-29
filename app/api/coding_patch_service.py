"""Non-mutating patch proposal service for Elysia Codev."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_backup_service import create_coding_backup
from app.api.coding_approval_modes import approval_mode_policy, mode_required_message
from app.api.coding_file_adapter_service import validate_patch_for_descriptor
from app.api.coding_file_type_registry import detect_file_type
from app.api.coding_path_guard_service import guard_workspace_path
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_patch_validation_service import validate_patch_targets
from app.api.coding_policy_service import coding_boundary_flags, load_coding_policy, patch_preview_limit
from app.api.coding_secret_scan_service import scan_preview_for_secrets
from app.api.schemas.coding_patch import (
    CodingPatchApplyRequest,
    CodingPatchApplyResult,
    CodingPatchProposeRequest,
    CodingPatchProposeResult,
)


def _preview_diff(diff_text: str | None, limit: int) -> tuple[str | None, bool]:
    if not diff_text:
        return None, False
    encoded = diff_text.encode("utf-8")
    if len(encoded) <= limit:
        return diff_text, False
    return encoded[:limit].decode("utf-8", errors="replace") + "\n[diff preview truncated]", True


def propose_patch(payload: CodingPatchProposeRequest) -> CodingPatchProposeResult:
    policy = load_coding_policy()
    capabilities = policy.get("capabilities") or {}
    mode_policy = approval_mode_policy(payload.approval_mode)
    flags = coding_boundary_flags(policy)
    allowed_files, blocked_files = validate_patch_targets(payload.workspace_root, payload.target_files)
    limit = patch_preview_limit(policy)
    diff_preview, truncated = _preview_diff(payload.proposed_diff, limit)
    hash_material = "\n".join(
        [
            payload.change_summary,
            "\n".join(allowed_files),
            diff_preview or "",
        ]
    )
    patch_hash = sha256((diff_preview or hash_material).encode("utf-8")).hexdigest()[:32]
    status = "preview_only" if capabilities.get("patch_proposal", False) and mode_policy.can_propose_patch else "proposal_disabled"
    warnings = [
        "Patch proposal does not mutate files.",
        "Apply requires explicit operator approval, a matching content hash, patch hash validation, and rollback note.",
    ]
    if not mode_policy.can_propose_patch:
        warnings.append(mode_required_message("apply_with_approval"))
    if blocked_files:
        warnings.append("Some requested patch targets were blocked by the workspace path guard.")

    return CodingPatchProposeResult(
        status=status,
        patch_id=f"patch_{uuid4().hex[:16]}",
        patch_hash=patch_hash,
        expected_content_hash=None,
        change_summary=payload.change_summary,
        target_files=payload.target_files,
        allowed_target_files=allowed_files,
        blocked_target_files=blocked_files,
        diff_preview=diff_preview,
        truncated=truncated,
        apply_allowed=mode_policy.can_apply_patch,
        approval_required_for_apply=True,
        rollback_note="No files were changed. Future apply paths must record exact files, diff hash, and rollback note.",
        warnings=warnings,
        boundaries=flags,
    )


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _apply_unified_diff(original: str, diff_text: str) -> str:
    original_lines = original.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)
    result: list[str] = []
    original_index = 0
    diff_index = 0

    while diff_index < len(diff_lines):
        line = diff_lines[diff_index]
        if line.startswith("--- ") or line.startswith("+++ "):
            diff_index += 1
            continue
        if not line.startswith("@@"):
            diff_index += 1
            continue

        header = line
        try:
            old_spec = header.split(" ", 2)[1]
            old_start = int(old_spec.split(",", 1)[0].removeprefix("-"))
        except (IndexError, ValueError) as exc:
            raise ValueError("invalid_unified_diff_header") from exc

        hunk_start = max(old_start - 1, 0)
        result.extend(original_lines[original_index:hunk_start])
        original_index = hunk_start
        diff_index += 1

        while diff_index < len(diff_lines) and not diff_lines[diff_index].startswith("@@"):
            hunk_line = diff_lines[diff_index]
            if hunk_line.startswith(" "):
                expected = hunk_line[1:]
                if original_index >= len(original_lines) or original_lines[original_index] != expected:
                    raise ValueError("patch_context_mismatch")
                result.append(expected)
                original_index += 1
            elif hunk_line.startswith("-"):
                expected = hunk_line[1:]
                if original_index >= len(original_lines) or original_lines[original_index] != expected:
                    raise ValueError("patch_remove_mismatch")
                original_index += 1
            elif hunk_line.startswith("+"):
                result.append(hunk_line[1:])
            elif hunk_line.startswith("\\"):
                pass
            else:
                raise ValueError("invalid_unified_diff_line")
            diff_index += 1

    result.extend(original_lines[original_index:])
    return "".join(result)


def apply_patch_with_approval(payload: CodingPatchApplyRequest) -> CodingPatchApplyResult:
    mode_policy = approval_mode_policy(payload.approval_mode)
    if not mode_policy.can_apply_patch:
        return CodingPatchApplyResult(
            status="blocked_by_approval_mode",
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            blocked_reason=f"{mode_policy.mode}_does_not_allow_patch_apply",
            rollback_note="No files were changed.",
            warnings=[mode_required_message("apply_with_approval")],
        )

    if not payload.operator_approved:
        return CodingPatchApplyResult(
            status="approval_required",
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            blocked_reason="operator_approval_required",
            rollback_note="No files were changed.",
            warnings=["Patch apply requires exact local operator approval."],
        )

    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.target_file,
        require_existing=True,
        allow_directory=False,
    )
    if not guarded.allowed:
        return CodingPatchApplyResult(
            status="blocked",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            blocked_reason=guarded.reason,
            rollback_note="No files were changed.",
        )

    policy = load_coding_policy()
    max_text_bytes = int((policy.get("limits") or {}).get("max_text_file_bytes", 1024 * 1024))
    if guarded.target_path.stat().st_size > max_text_bytes:
        return CodingPatchApplyResult(
            status="blocked",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            blocked_reason="text_file_too_large",
            rollback_note="No files were changed.",
        )
    current = guarded.target_path.read_text(encoding="utf-8")
    with guarded.target_path.open("rb") as stream:
        raw_sample = stream.read(4096)
    descriptor = detect_file_type(guarded.target_path, raw_sample)
    descriptor_ok, descriptor_reason = validate_patch_for_descriptor(descriptor)
    if not descriptor_ok:
        return CodingPatchApplyResult(
            status="blocked",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            blocked_reason=descriptor_reason,
            rollback_note="No files were changed.",
            warnings=list(descriptor.notes),
        )
    current_hash = _hash_text(current)
    if current_hash != payload.expected_content_hash:
        return CodingPatchApplyResult(
            status="blocked",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            previous_content_hash=current_hash,
            blocked_reason="current_content_hash_mismatch",
            rollback_note="No files were changed. Re-read approved preview before applying.",
        )

    computed_patch_hash = sha256(payload.proposed_diff.encode("utf-8")).hexdigest()[:32]
    if computed_patch_hash != payload.patch_hash:
        return CodingPatchApplyResult(
            status="blocked",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            previous_content_hash=current_hash,
            blocked_reason="patch_hash_mismatch",
            rollback_note="No files were changed.",
        )

    try:
        updated = _apply_unified_diff(current, payload.proposed_diff)
    except ValueError as exc:
        return CodingPatchApplyResult(
            status="blocked",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            previous_content_hash=current_hash,
            blocked_reason=str(exc),
            rollback_note="No files were changed.",
        )

    new_hash = _hash_text(updated)
    descriptor_ok, descriptor_reason = validate_patch_for_descriptor(descriptor, new_text=updated)
    if not descriptor_ok:
        return CodingPatchApplyResult(
            status="blocked",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            previous_content_hash=current_hash,
            blocked_reason=descriptor_reason,
            rollback_note="No files were changed.",
            warnings=list(descriptor.notes),
        )
    secret_findings = scan_preview_for_secrets(updated)
    if secret_findings:
        return CodingPatchApplyResult(
            status="blocked",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            previous_content_hash=current_hash,
            blocked_reason="proposed_content_contains_possible_secret",
            rollback_note="No files were changed.",
            warnings=["Patched content was refused by the secret scanner.", *sorted(secret_findings)],
        )
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind="patch_apply",
        workspace_root=payload.workspace_root,
        exact_files=[payload.target_file],
        source_hash=current_hash,
        plan_hash=payload.patch_hash,
        allowed_mutation_class="text_patch",
    )
    if not approval.allowed:
        return CodingPatchApplyResult(
            status="approval_required",
            target_relative_path=guarded.relative_path,
            patch_hash=payload.patch_hash,
            expected_content_hash=payload.expected_content_hash,
            previous_content_hash=current_hash,
            approval_id=payload.approval_id,
            blocked_reason=approval.reason,
            rollback_note="No files were changed.",
            warnings=["A matching, unexpired, one-time patch approval is required."],
        )
    backup = create_coding_backup(
        workspace_root=guarded.workspace_root,
        source_path=guarded.target_path,
        source_relative_path=guarded.relative_path or guarded.target_path.name,
        operation_kind="patch_apply",
        session_id=payload.session_id,
    )
    guarded.target_path.write_text(updated, encoding="utf-8")
    audit_written = write_coding_audit_record(
        "patch_apply",
        f"{uuid4().hex[:16]}",
        {
            "session_id": payload.session_id,
            "target_relative_path": guarded.relative_path,
            "file_type": descriptor.type_id,
            "adapter": descriptor.adapter,
            "patch_hash": payload.patch_hash,
            "previous_content_hash": current_hash,
            "new_content_hash": new_hash,
            "operator_approved": True,
            "approval_phrase_present": bool(payload.approval_phrase),
            "approval_id": payload.approval_id,
            "backup_relative_path": backup.backup_relative_path,
            "rollback_receipt_id": backup.receipt_id,
        },
    )
    return CodingPatchApplyResult(
        status="applied",
        target_relative_path=guarded.relative_path,
        patch_hash=payload.patch_hash,
        expected_content_hash=payload.expected_content_hash,
        previous_content_hash=current_hash,
        new_content_hash=new_hash,
        backup_relative_path=backup.backup_relative_path,
        rollback_receipt_id=backup.receipt_id,
        approval_id=payload.approval_id,
        mutation_performed=True,
        audit_written=audit_written,
        rollback_note=f"Restore from {backup.backup_relative_path} using receipt {backup.receipt_id}.",
        warnings=["Patch was applied with Python text I/O only; no shell, git, package manager, or command runner was used."],
    )


def patch_hash_for_diff(diff_text: str) -> str:
    return sha256(diff_text.encode("utf-8")).hexdigest()[:32]


__all__ = ("apply_patch_with_approval", "patch_hash_for_diff", "propose_patch")
