from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_distinguishes_bounded_live_paths_from_broad_authority() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Patch application | Live in current development" in text
    assert "Broad/free-form shell is not live" in text
    assert "Page fetch | Live in current development" in text
    assert "separate exact, expiring, one-time approval" in text
    assert "exact-approved focused test/typecheck/build commands" in text

    assert "| Patch application | Not live |" not in text
    assert "| Page fetch | Not live |" not in text
    assert "- no patch application from patch proposals" not in text


def test_repo_context_and_patch_proposal_copy_do_not_hide_separate_governed_paths() -> None:
    approved_repos = (ROOT / "config" / "coder" / "approved_repos.yaml").read_text(
        encoding="utf-8"
    )
    capability_service = (ROOT / "app" / "api" / "capability_service.py").read_text(
        encoding="utf-8"
    )

    assert "Repo-context approval alone grants no command" in approved_repos
    assert "separate exact-approved patch/file and focused-command paths" in approved_repos
    assert "This proposal-only path does not apply patches" in capability_service
    assert "separate exact-approved patch path remains independently state-bound" in capability_service

    assert "No shell commands, network access, file mutation, or git status/diff inspection is live in v0." not in approved_repos
    assert "Patch application is not live here" not in capability_service
