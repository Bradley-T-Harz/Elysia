"""Approval-mode gates for the governed coding bridge."""

from __future__ import annotations

from dataclasses import dataclass


APPROVAL_MODES = (
    "read_only",
    "plan_only",
    "path_preview",
    "apply_with_approval",
    "test_with_approval",
)

LEGACY_MODE_ALIASES = {
    "ask_first": "apply_with_approval",
    "patch_preview": "apply_with_approval",
}


@dataclass(frozen=True)
class ApprovalModePolicy:
    mode: str
    can_read_approved_file: bool
    can_inspect_paths: bool
    can_propose_patch: bool
    can_apply_patch: bool
    can_run_tests: bool
    description: str


_POLICIES = {
    "read_only": ApprovalModePolicy(
        mode="read_only",
        can_read_approved_file=True,
        can_inspect_paths=False,
        can_propose_patch=False,
        can_apply_patch=False,
        can_run_tests=False,
        description="Read only: explain approved file previews; no patches, mutation, or commands.",
    ),
    "plan_only": ApprovalModePolicy(
        mode="plan_only",
        can_read_approved_file=True,
        can_inspect_paths=False,
        can_propose_patch=False,
        can_apply_patch=False,
        can_run_tests=False,
        description="Plan only: reason and outline changes; no apply-ready patch, mutation, or commands.",
    ),
    "path_preview": ApprovalModePolicy(
        mode="path_preview",
        can_read_approved_file=True,
        can_inspect_paths=True,
        can_propose_patch=False,
        can_apply_patch=False,
        can_run_tests=False,
        description="Path preview: inspect bounded workspace metadata and approved file previews only.",
    ),
    "apply_with_approval": ApprovalModePolicy(
        mode="apply_with_approval",
        can_read_approved_file=True,
        can_inspect_paths=True,
        can_propose_patch=True,
        can_apply_patch=True,
        can_run_tests=False,
        description="Apply with approval: propose patches and apply only after exact local approval.",
    ),
    "test_with_approval": ApprovalModePolicy(
        mode="test_with_approval",
        can_read_approved_file=True,
        can_inspect_paths=True,
        can_propose_patch=True,
        can_apply_patch=True,
        can_run_tests=True,
        description="Test with approval: apply-with-approval plus exact allowlisted checks after approval.",
    ),
}


def normalize_approval_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or "plan_only").strip().lower()
    mode = LEGACY_MODE_ALIASES.get(mode, mode)
    if mode not in _POLICIES:
        return "plan_only"
    return mode


def approval_mode_policy(raw_mode: str | None) -> ApprovalModePolicy:
    return _POLICIES[normalize_approval_mode(raw_mode)]


def mode_required_message(required_mode: str) -> str:
    required = approval_mode_policy(required_mode)
    return f"This action requires `{required.mode}` mode. {required.description}"


__all__ = (
    "APPROVAL_MODES",
    "ApprovalModePolicy",
    "approval_mode_policy",
    "mode_required_message",
    "normalize_approval_mode",
)
