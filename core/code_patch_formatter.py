"""
Disciplined code patch plan formatter v0 for Elysia.

This module gives future Coder mode a bounded, reviewable way to express code
change intent. It formats proposed changes into a structured patch plan.

It does not inspect files, write files, apply patches, run tests, run shell
commands, touch the network, mutate git state, install dependencies, or invoke
external coding workers such as Aider/OpenHands.

v0 is proposal-only:
- summarize the intended change
- list proposed files to touch
- list patch steps
- list suggested tests
- list risks and rollback notes
- force approval-required truth before any future file mutation
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any


CODE_PATCH_FORMATTER_TOOL_KIND = "code_patch_formatter"
CODE_PATCH_FORMATTER_OPERATION = "format_code_patch_plan"

DEFAULT_MAX_FILES_TO_TOUCH = 12
DEFAULT_MAX_PATCH_STEPS = 20
DEFAULT_MAX_TEST_COMMANDS = 12
DEFAULT_MAX_TEXT_LENGTH = 2_000

APPROVAL_REASON = "Code/file mutation requires explicit approval before application."

BLOCKED_PATH_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    "coverage",
    ".next",
    ".turbo",
    "vault",
    "secrets",
    "credentials",
    "private",
    "browser_profiles",
    "browser profile",
    "browser profiles",
}

BLOCKED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "known_hosts",
    "authorized_keys",
}

BLOCKED_FILE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".der",
    ".sqlite",
    ".db",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
}

SECRET_NAME_FRAGMENTS = {
    "token",
    "secret",
    "credential",
    "password",
    "passwd",
    "apikey",
    "api_key",
    "private_key",
}

FALSE_COMPLETION_PHRASES = {
    "i applied",
    "applied the patch",
    "already applied",
    "i wrote the file",
    "wrote the file",
    "i ran the tests",
    "ran the tests",
    "i committed",
    "committed the change",
    "committed it",
    "git commit",
    "git push",
}


class CodePatchPlanStatus(str, Enum):
    """Small status vocabulary for code patch plan formatting."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class CodePatchPlanResult:
    """Structured result for a proposal-only code patch plan."""

    ok: bool
    status: CodePatchPlanStatus
    tool_kind: str = CODE_PATCH_FORMATTER_TOOL_KIND
    operation: str = CODE_PATCH_FORMATTER_OPERATION

    summary: str = ""
    repo_key: str | None = None
    repo_root: str | None = None
    files_to_touch: list[str] = field(default_factory=list)
    patch_plan: list[str] = field(default_factory=list)
    tests_to_run: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    rollback_notes: list[str] = field(default_factory=list)

    approval_needed: bool = True
    approval_reason: str = APPROVAL_REASON
    can_apply_patch: bool = False
    patch_application_live: bool = False
    shell_execution_used: bool = False
    network_access_used: bool = False
    mutated_files: bool = False
    external_workers_used: bool = False

    boundary_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-safe payload."""
        return {
            "ok": self.ok,
            "status": self.status.value,
            "tool_kind": self.tool_kind,
            "operation": self.operation,
            "summary": self.summary,
            "repo_key": self.repo_key,
            "repo_root": self.repo_root,
            "files_to_touch": list(self.files_to_touch),
            "patch_plan": list(self.patch_plan),
            "tests_to_run": list(self.tests_to_run),
            "risk_notes": list(self.risk_notes),
            "rollback_notes": list(self.rollback_notes),
            "approval_needed": self.approval_needed,
            "approval_reason": self.approval_reason,
            "can_apply_patch": self.can_apply_patch,
            "patch_application_live": self.patch_application_live,
            "shell_execution_used": self.shell_execution_used,
            "network_access_used": self.network_access_used,
            "mutated_files": self.mutated_files,
            "external_workers_used": self.external_workers_used,
            "boundary_notes": list(self.boundary_notes),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _default_boundary_notes() -> list[str]:
    return [
        "Patch plan only. No files were mutated.",
        "No shell commands were run.",
        "No network access was used.",
        "No external coding worker was invoked.",
        "Approval is required before applying changes.",
        "Patch application is not live in code patch formatter v0.",
    ]


def _blocked_result(
    *,
    summary: str = "",
    repo_key: str | None = None,
    repo_root: str | None = None,
    files_to_touch: list[str] | None = None,
    patch_plan: list[str] | None = None,
    tests_to_run: list[str] | None = None,
    risk_notes: list[str] | None = None,
    rollback_notes: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> CodePatchPlanResult:
    return CodePatchPlanResult(
        ok=False,
        status=CodePatchPlanStatus.BLOCKED,
        summary=summary,
        repo_key=repo_key,
        repo_root=repo_root,
        files_to_touch=list(files_to_touch or []),
        patch_plan=list(patch_plan or []),
        tests_to_run=list(tests_to_run or []),
        risk_notes=list(risk_notes or []),
        rollback_notes=list(rollback_notes or []),
        approval_needed=True,
        can_apply_patch=False,
        patch_application_live=False,
        shell_execution_used=False,
        network_access_used=False,
        mutated_files=False,
        external_workers_used=False,
        boundary_notes=_default_boundary_notes(),
        warnings=list(warnings or []),
        errors=list(errors or []),
    )


def _get_field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)

    attr = getattr(value, key, None)
    if attr is not None:
        return attr

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:
            dumped = None

        if isinstance(dumped, Mapping):
            return dumped.get(key, default)

    as_dict = getattr(value, "dict", None)
    if callable(as_dict):
        try:
            dumped = as_dict()
        except Exception:
            dumped = None

        if isinstance(dumped, Mapping):
            return dumped.get(key, default)

    return default


def _clean_text(value: Any, *, max_length: int = DEFAULT_MAX_TEXT_LENGTH) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text

    return text[: max(1, max_length - 1)].rstrip() + "…"


def _clean_text_list(
    values: list[str] | tuple[str, ...] | None,
    *,
    max_items: int,
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []

    if not values:
        return [], warnings

    cleaned: list[str] = []
    for raw_value in values:
        text = _clean_text(raw_value, max_length=max_length)
        if not text:
            continue

        cleaned.append(text)

    if len(cleaned) > max_items:
        warnings.append(
            f"List was limited to {max_items} items for code patch formatter v0."
        )
        cleaned = cleaned[:max_items]

    return cleaned, warnings


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        ordered.append(value)

    return ordered


def _name_looks_secret(name: str) -> bool:
    lowered = name.lower()

    if lowered in BLOCKED_FILE_NAMES:
        return True

    if any(fragment in lowered for fragment in SECRET_NAME_FRAGMENTS):
        return True

    return False


def _normalize_file_path(path_text: str) -> tuple[str | None, str | None]:
    raw = str(path_text or "").strip()

    if not raw:
        return None, "Proposed file path is empty."

    if "\x00" in raw:
        return None, f"Proposed file path contains a null byte: {raw!r}"

    if "://" in raw:
        return None, f"Proposed file path must be local and relative, not a URL: {raw}"

    if raw.startswith("~"):
        return None, f"Proposed file path must not target a home directory shortcut: {raw}"

    if any(char in raw for char in ("*", "?", "[", "]")):
        return None, f"Proposed file path must not contain glob characters: {raw}"

    normalized_separators = raw.replace("\\", "/")

    if Path(normalized_separators).is_absolute() or PurePosixPath(
        normalized_separators
    ).is_absolute():
        return None, f"Proposed file path must be relative to an approved repo: {raw}"

    pure_path = PurePosixPath(normalized_separators)
    parts = [part for part in pure_path.parts if part not in {"", "."}]

    if not parts:
        return None, f"Proposed file path is not a usable relative path: {raw}"

    lowered_parts = [part.lower() for part in parts]
    if any(part == ".." for part in lowered_parts):
        return None, f"Proposed file path must not traverse outside the repo: {raw}"

    if any(part in BLOCKED_PATH_PARTS for part in lowered_parts):
        return None, f"Proposed file path targets a sealed/generated path: {raw}"

    file_name = lowered_parts[-1]
    if _name_looks_secret(file_name):
        return None, f"Proposed file path looks secret-bearing or sealed: {raw}"

    if PurePosixPath(file_name).suffix.lower() in BLOCKED_FILE_SUFFIXES:
        return None, f"Proposed file path has a blocked file type: {raw}"

    return "/".join(parts), None


def _validate_files_to_touch(files_to_touch: list[str]) -> tuple[list[str], list[str]]:
    normalized_files: list[str] = []
    errors: list[str] = []

    for path_text in files_to_touch:
        normalized, error = _normalize_file_path(path_text)
        if error:
            errors.append(error)
            continue

        if normalized:
            normalized_files.append(normalized)

    return _ordered_unique(normalized_files), errors


def _contains_false_completion_claim(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in FALSE_COMPLETION_PHRASES)


def _validate_truthful_proposal_language(
    *,
    summary: str,
    patch_plan: list[str],
) -> list[str]:
    errors: list[str] = []

    if _contains_false_completion_claim(summary):
        errors.append(
            "Patch plan summary must not claim files were already changed, tested, or committed."
        )

    for step in patch_plan:
        if _contains_false_completion_claim(step):
            errors.append(
                "Patch plan steps must describe proposed work, not completed file edits, test runs, commits, or pushes."
            )
            break

    return errors


def _extract_repo_context_fields(repo_context: Any | None) -> tuple[str | None, str | None, list[str]]:
    if repo_context is None:
        return None, None, []

    repo_key = _get_field(repo_context, "repo_key", None)
    repo_root = _get_field(repo_context, "repo_root", None)
    test_command_hints = _get_field(repo_context, "test_command_hints", [])

    clean_hints: list[str] = []
    if isinstance(test_command_hints, list):
        clean_hints = [
            _clean_text(command)
            for command in test_command_hints
            if _clean_text(command)
        ]

    return (
        str(repo_key) if repo_key is not None else None,
        str(repo_root) if repo_root is not None else None,
        clean_hints,
    )


def _default_risk_notes() -> list[str]:
    return [
        "Review the proposed files and patch steps before approving any mutation.",
        "Run focused tests before broader tests after any approved patch is applied.",
    ]


def _default_rollback_notes(files_to_touch: list[str]) -> list[str]:
    file_list = " ".join(files_to_touch)
    return [
        "Use git diff to review proposed touched files before approval.",
        f"Use git restore {file_list} before commit if an applied patch needs to be reverted.",
    ]


def format_code_patch_plan(
    *,
    summary: str,
    files_to_touch: list[str],
    patch_plan: list[str],
    tests_to_run: list[str] | None = None,
    risk_notes: list[str] | None = None,
    rollback_notes: list[str] | None = None,
    repo_context: Any | None = None,
    approval_needed: bool = True,
) -> CodePatchPlanResult:
    """
    Format and guard a proposal-only code patch plan.

    The caller supplies the proposed files, steps, tests, risks, and rollback
    guidance. This formatter validates the shape and boundary truth, but it does
    not inspect, write, patch, test, run shell commands, or invoke workers.
    """
    clean_summary = _clean_text(summary)
    clean_files, file_warnings = _clean_text_list(
        files_to_touch,
        max_items=DEFAULT_MAX_FILES_TO_TOUCH,
    )
    clean_steps, step_warnings = _clean_text_list(
        patch_plan,
        max_items=DEFAULT_MAX_PATCH_STEPS,
    )
    clean_tests, test_warnings = _clean_text_list(
        tests_to_run,
        max_items=DEFAULT_MAX_TEST_COMMANDS,
    )
    clean_risks, risk_warnings = _clean_text_list(
        risk_notes,
        max_items=DEFAULT_MAX_PATCH_STEPS,
    )
    clean_rollbacks, rollback_warnings = _clean_text_list(
        rollback_notes,
        max_items=DEFAULT_MAX_PATCH_STEPS,
    )

    repo_key, repo_root, repo_test_hints = _extract_repo_context_fields(repo_context)

    warnings = (
        file_warnings
        + step_warnings
        + test_warnings
        + risk_warnings
        + rollback_warnings
    )
    errors: list[str] = []

    if not clean_summary:
        errors.append("Patch plan summary is required.")

    if not clean_files:
        errors.append("At least one proposed file path is required.")

    if not clean_steps:
        errors.append("At least one patch step is required.")

    normalized_files, file_errors = _validate_files_to_touch(clean_files)
    errors.extend(file_errors)

    if not approval_needed:
        warnings.append(
            "Approval was forced to required because patch application is not live in v0."
        )

    if not clean_tests and repo_test_hints:
        clean_tests = repo_test_hints[:DEFAULT_MAX_TEST_COMMANDS]
        warnings.append(
            "Tests to run were filled from repo context hints; no tests were executed."
        )

    if not clean_risks:
        clean_risks = _default_risk_notes()

    if normalized_files and not clean_rollbacks:
        clean_rollbacks = _default_rollback_notes(normalized_files)

    errors.extend(
        _validate_truthful_proposal_language(
            summary=clean_summary,
            patch_plan=clean_steps,
        )
    )

    if errors:
        return _blocked_result(
            summary=clean_summary,
            repo_key=repo_key,
            repo_root=repo_root,
            files_to_touch=normalized_files or clean_files,
            patch_plan=clean_steps,
            tests_to_run=clean_tests,
            risk_notes=clean_risks,
            rollback_notes=clean_rollbacks,
            warnings=warnings,
            errors=errors,
        )

    return CodePatchPlanResult(
        ok=True,
        status=CodePatchPlanStatus.COMPLETED,
        summary=clean_summary,
        repo_key=repo_key,
        repo_root=repo_root,
        files_to_touch=normalized_files,
        patch_plan=clean_steps,
        tests_to_run=clean_tests,
        risk_notes=clean_risks,
        rollback_notes=clean_rollbacks,
        approval_needed=True,
        approval_reason=APPROVAL_REASON,
        can_apply_patch=False,
        patch_application_live=False,
        shell_execution_used=False,
        network_access_used=False,
        mutated_files=False,
        external_workers_used=False,
        boundary_notes=_default_boundary_notes(),
        warnings=warnings,
        errors=[],
    )


__all__ = (
    "APPROVAL_REASON",
    "CODE_PATCH_FORMATTER_OPERATION",
    "CODE_PATCH_FORMATTER_TOOL_KIND",
    "DEFAULT_MAX_FILES_TO_TOUCH",
    "DEFAULT_MAX_PATCH_STEPS",
    "DEFAULT_MAX_TEST_COMMANDS",
    "DEFAULT_MAX_TEXT_LENGTH",
    "CodePatchPlanResult",
    "CodePatchPlanStatus",
    "format_code_patch_plan",
)
