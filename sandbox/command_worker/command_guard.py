"""Exact-command allowlist guard for focused command execution."""

from __future__ import annotations

from pathlib import Path


ALLOWED_FIXED_COMMANDS: dict[str, list[str]] = {
    "frontend_typecheck": ["npm", "--prefix", "apps/elysia-desktop", "run", "typecheck"],
    "frontend_build": ["npm", "--prefix", "apps/elysia-desktop", "run", "build"],
}

BLOCKED_TOKENS = {
    "sudo",
    "rm",
    "curl",
    "wget",
    "ssh",
    "scp",
    "apt",
    "pip",
    "install",
    "push",
    "reset",
    "clean",
}


def _is_safe_test_path(value: str) -> bool:
    path = Path(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.parts
        and path.parts[0] == "tests"
        and path.suffix == ".py"
    )


def _is_safe_py_path(value: str) -> bool:
    path = Path(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.suffix == ".py"
        and not any(part in {"vault", ".git", "node_modules", "dist", "target"} for part in path.parts)
    )


def command_key_for_argv(argv: list[str]) -> tuple[str | None, str | None]:
    """Return an allowlist command key or a refusal reason."""
    if not isinstance(argv, list) or not all(isinstance(part, str) for part in argv):
        return None, "Command argv must be a list of strings."
    if not argv:
        return None, "Command argv is required."
    if any(not part or any(marker in part for marker in (";", "&&", "||", "|", ">", "<", "$(")) for part in argv):
        return None, "Shell chaining, pipes, redirects, and substitutions are blocked."
    lowered = {part.lower() for part in argv}
    if lowered & BLOCKED_TOKENS:
        return None, "Command contains a blocked token."

    for key, allowed in ALLOWED_FIXED_COMMANDS.items():
        if argv == allowed:
            return key, None

    if len(argv) in {5, 6} and argv[:3] == ["python", "-m", "pytest"] and argv[-1] == "-q":
        test_target = argv[3]
        if "::" in test_target:
            test_file, test_name = test_target.split("::", 1)
            if _is_safe_test_path(test_file) and test_name:
                return "pytest_single_test", None
        elif _is_safe_test_path(test_target):
            return "pytest_single_file", None

    if len(argv) == 4 and argv[:3] == ["python", "-m", "py_compile"] and _is_safe_py_path(argv[3]):
        return "py_compile_file", None

    return None, "Command does not match the focused allowlist."


def validate_command_cwd(repo_root: str | Path, cwd: str | Path) -> tuple[Path | None, str | None]:
    """Ensure command cwd is exactly inside the approved repo root."""
    root = Path(repo_root).expanduser().resolve(strict=False)
    target = Path(cwd).expanduser().resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        return None, "Command cwd must stay inside the approved repo root."
    return target, None


__all__ = ("ALLOWED_FIXED_COMMANDS", "command_key_for_argv", "validate_command_cwd")
