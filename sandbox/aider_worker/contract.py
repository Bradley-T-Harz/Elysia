from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AiderWorkerStatus(str, Enum):
    """Small status vocabulary for the future Aider worker lane."""

    CONTRACT_ONLY = "contract_only"
    DRY_RUN_READY = "dry_run_ready"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class AiderWorkerRequest:
    """Structured request for no-op Aider worker dry-run validation."""

    request_id: str
    worker_key: str = "aider_worker"
    repo_key: str = "elysia"
    repo_root: str = ""
    trust_zone: str = "project_local"
    user_goal: str = ""
    mode: str = "dry_run"
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    selected_files: list[str] = field(default_factory=list)
    dry_run_only: bool = True
    network_allowed: bool = False
    shell_allowed: bool = False
    test_execution_allowed: bool = False
    mutation_allowed: bool = False
    git_mutation_allowed: bool = False
    package_install_allowed: bool = False
    credentials_allowed: bool = False
    vault_allowed: bool = False
    home_access_allowed: bool = False
    cloud_model_allowed: bool = False
    approval_token: str | None = None
    model_provider_policy: str = "local_only"
    privacy_notice: str = "local_first_no_mutation"
    trace_parent_id: str | None = None


@dataclass
class AiderWorkerResult:
    """Structured result for no-op Aider worker dry-run validation."""

    status: AiderWorkerStatus
    worker_key: str = "aider_worker"
    worker_used: bool = False
    aider_invoked: bool = False
    repo_key: str | None = None
    repo_root: str = ""
    trust_zone: str = "project_local"
    files_considered: list[str] = field(default_factory=list)
    files_proposed: list[str] = field(default_factory=list)
    diff_preview: str = ""
    diff_preview_hash: str = ""
    commands_requested: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    tests_requested: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    mutated_files: bool = False
    network_used: bool = False
    shell_used: bool = False
    test_execution_used: bool = False
    git_mutation_used: bool = False
    package_install_used: bool = False
    external_model_used: bool = False
    approval_required: bool = True
    approval_reason: str = "Approval is required before any future mutation."
    refusal_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    trace_summary: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-safe payload."""
        return {
            "status": self.status.value,
            "worker_key": self.worker_key,
            "worker_used": self.worker_used,
            "aider_invoked": self.aider_invoked,
            "repo_key": self.repo_key,
            "repo_root": self.repo_root,
            "trust_zone": self.trust_zone,
            "files_considered": list(self.files_considered),
            "files_proposed": list(self.files_proposed),
            "diff_preview": self.diff_preview,
            "diff_preview_hash": self.diff_preview_hash,
            "commands_requested": list(self.commands_requested),
            "commands_run": list(self.commands_run),
            "tests_requested": list(self.tests_requested),
            "tests_run": list(self.tests_run),
            "mutated_files": self.mutated_files,
            "network_used": self.network_used,
            "shell_used": self.shell_used,
            "test_execution_used": self.test_execution_used,
            "git_mutation_used": self.git_mutation_used,
            "package_install_used": self.package_install_used,
            "external_model_used": self.external_model_used,
            "approval_required": self.approval_required,
            "approval_reason": self.approval_reason,
            "refusal_reasons": list(self.refusal_reasons),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "trace_summary": dict(self.trace_summary),
        }
