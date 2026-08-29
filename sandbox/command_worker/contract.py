"""Contract models for focused approved command execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandWorkerStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class CommandWorkerRequest:
    request_id: str
    repo_key: str
    cwd: str
    command_key: str
    argv: list[str]
    approval_reference: str
    approved_by_user: bool = False
    timeout_seconds: int = 120
    max_output_chars: int = 6000


@dataclass
class CommandWorkerResult:
    status: CommandWorkerStatus
    request_id: str = ""
    repo_key: str = ""
    command_key: str = ""
    argv: list[str] = field(default_factory=list)
    cwd: str = ""
    allowlist_matched: bool = False
    approved_by_user: bool = False
    approval_reference: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    stdout_preview: str = ""
    stderr_preview: str = ""
    output_truncated: bool = False
    timeout_seconds: int = 0
    shell_used: bool = False
    network_access_used: bool = False
    mutated_files: bool = False
    git_mutation_used: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == CommandWorkerStatus.COMPLETED and self.exit_code == 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status.value,
            "request_id": self.request_id,
            "repo_key": self.repo_key,
            "command_key": self.command_key,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "allowlist_matched": self.allowlist_matched,
            "approved_by_user": self.approved_by_user,
            "approval_reference": self.approval_reference,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stdout_preview": self.stdout_preview,
            "stderr_preview": self.stderr_preview,
            "output_truncated": self.output_truncated,
            "timeout_seconds": self.timeout_seconds,
            "shell_used": self.shell_used,
            "network_access_used": self.network_access_used,
            "mutated_files": self.mutated_files,
            "git_mutation_used": self.git_mutation_used,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


__all__ = ("CommandWorkerRequest", "CommandWorkerResult", "CommandWorkerStatus")
