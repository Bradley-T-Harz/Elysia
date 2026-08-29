"""Approved-root, fixed-argv, read-only Git status truth for Codev."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.schemas.coding_git import CodingGitChangedFile, CodingGitPreview, CodingGitPreviewRequest


_STATUS_LABELS = {
    ".": "unchanged",
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "type_changed",
    "U": "unmerged",
    "?": "untracked",
}


def _read_head(git_dir: Path) -> tuple[str | None, str | None]:
    try:
        head_text = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None, None
    if head_text.startswith("ref: "):
        ref = head_text.removeprefix("ref: ").strip()
        return ref.rsplit("/", 1)[-1] if ref else None, ref or None
    return None, "detached_head" if head_text else None


def _safe_git_env() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/nonexistent",
        "XDG_CONFIG_HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _run_git(git: str, root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [git, "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "credential.helper=", "-C", str(root), *arguments],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
        shell=False,
        close_fds=True,
        env=_safe_git_env(),
    )


def _parse_status(output: str, *, max_entries: int) -> tuple[dict[str, str | None], list[CodingGitChangedFile]]:
    branch: dict[str, str | None] = {"head": None, "oid": None, "upstream": None}
    changed: list[CodingGitChangedFile] = []
    for line in output.splitlines():
        if line.startswith("# branch.head "):
            branch["head"] = line.removeprefix("# branch.head ").strip()
            continue
        if line.startswith("# branch.oid "):
            value = line.removeprefix("# branch.oid ").strip()
            branch["oid"] = None if value == "(initial)" else value
            continue
        if line.startswith("# branch.upstream "):
            branch["upstream"] = line.removeprefix("# branch.upstream ").strip() or None
            continue
        if len(changed) >= max_entries:
            continue
        if line.startswith("? "):
            changed.append(
                CodingGitChangedFile(
                    relative_path=line[2:],
                    status="untracked",
                    index_status="unchanged",
                    working_tree_status="untracked",
                    staged=False,
                    unstaged=True,
                )
            )
            continue
        if line.startswith("! "):
            continue
        if line.startswith(("1 ", "2 ", "u ")):
            fields = line.split(" ")
            if len(fields) < 2:
                continue
            xy = fields[1] if len(fields[1]) >= 2 else ".."
            if line.startswith("1 "):
                relative = line.split(" ", 8)[-1]
            elif line.startswith("2 "):
                relative = line.split(" ", 9)[-1].split("\t", 1)[0]
            else:
                relative = line.split(" ", 10)[-1]
            if relative.startswith('"') and relative.endswith('"'):
                try:
                    decoded = json.loads(relative)
                    relative = decoded if isinstance(decoded, str) else relative
                except json.JSONDecodeError:
                    relative = "quoted_path"
            index = _STATUS_LABELS.get(xy[0], "unknown")
            working = _STATUS_LABELS.get(xy[1], "unknown")
            effective = working if working != "unchanged" else index
            changed.append(
                CodingGitChangedFile(
                    relative_path=relative,
                    status=effective,
                    index_status=index,
                    working_tree_status=working,
                    staged=index != "unchanged",
                    unstaged=working != "unchanged",
                )
            )
    return branch, changed


def preview_git_state(payload: CodingGitPreviewRequest) -> CodingGitPreview:
    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=".",
        require_existing=True,
        allow_directory=True,
    )
    if not guarded.allowed:
        return CodingGitPreview(
            status="blocked",
            repo_detected=False,
            approved_repo=False,
            blocked_reason=guarded.reason or "workspace_root_not_approved",
            warnings=["Git state was not inspected because the repository root is not approved."],
        )
    root = guarded.workspace_root
    root_hash = hash_path(root)
    git_dir = root / ".git"
    if not git_dir.exists():
        return CodingGitPreview(
            status="not_a_git_repo",
            repo_detected=False,
            approved_repo=True,
            workspace_root_hash=root_hash,
            warnings=["No Git repository metadata was found at the approved workspace root."],
        )
    branch_fallback, head_ref = _read_head(git_dir)
    git = shutil.which("git")
    if not git:
        return CodingGitPreview(
            status="degraded",
            repo_detected=True,
            approved_repo=True,
            branch=branch_fallback,
            head_ref=head_ref,
            workspace_root_hash=root_hash,
            mutation_allowed=False,
            shell_git_used=False,
            git_command_used=False,
            warnings=["Git executable is unavailable; only .git/HEAD branch metadata was read."],
        )
    try:
        status = _run_git(
            git,
            root,
            ["status", "--porcelain=v2", "--branch", "--untracked-files=normal"],
        )
        remotes = _run_git(git, root, ["remote"])
    except (OSError, subprocess.TimeoutExpired):
        return CodingGitPreview(
            status="degraded",
            repo_detected=True,
            approved_repo=True,
            branch=branch_fallback,
            head_ref=head_ref,
            workspace_root_hash=root_hash,
            warnings=["The fixed read-only Git status check did not complete."],
        )
    if status.returncode != 0:
        return CodingGitPreview(
            status="degraded",
            repo_detected=True,
            approved_repo=True,
            branch=branch_fallback,
            head_ref=head_ref,
            workspace_root_hash=root_hash,
            git_command_used=True,
            warnings=["Git status returned a non-zero result; no output or private path was surfaced."],
        )
    branch_data, changed = _parse_status(status.stdout[:200_000], max_entries=payload.max_changed_files)
    staged = sum(1 for item in changed if item.staged)
    unstaged = sum(1 for item in changed if item.unstaged and item.status != "untracked")
    untracked = sum(1 for item in changed if item.status == "untracked")
    return CodingGitPreview(
        status="read_only_status",
        repo_detected=True,
        approved_repo=True,
        branch=branch_data["head"] or branch_fallback,
        head_ref=head_ref,
        head_commit=(branch_data["oid"] or "")[:12] or None,
        upstream=branch_data["upstream"],
        remote_present=bool(remotes.returncode == 0 and remotes.stdout.strip()),
        dirty=bool(changed),
        changed_count=len(changed),
        staged_count=staged,
        unstaged_count=unstaged,
        untracked_count=untracked,
        changed_files=changed,
        workspace_root_hash=root_hash,
        mutation_allowed=False,
        shell_git_used=False,
        git_command_used=True,
        output_truncated=len(changed) >= payload.max_changed_files,
        warnings=[
            "Git truth used fixed read-only argv with shell=False; no commit, checkout, stash, reset, clean, or push authority exists."
        ],
    )


__all__ = ("preview_git_state",)
