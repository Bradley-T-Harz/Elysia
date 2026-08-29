from __future__ import annotations

from pathlib import Path

from core.repo_context_gatherer import (
    CHANGED_FILES_NOTE,
    REPO_CONTEXT_OPERATION,
    REPO_CONTEXT_TOOL_KIND,
    RepoContextStatus,
    gather_repo_context,
    load_approved_repos_config,
)


def write_file(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_config(path: Path, repo_root: Path, *, default_key: str = "demo") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "version: 1",
                f"default_repo_key: {default_key}",
                "",
                "inspection_defaults:",
                "  max_depth: 4",
                "  max_entries: 200",
                "  max_file_size_bytes: 250000",
                "  changed_files_live: false",
                "  shell_allowed: false",
                "  network_allowed: false",
                "  file_mutation_allowed: false",
                "",
                "repos:",
                f"  {default_key}:",
                "    label: Demo repo",
                f"    root: {repo_root}",
                "    trust_zone: project_local",
                "    allowed: true",
                "    notes:",
                "      - Approved test repo.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def make_demo_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"

    write_file(repo / "README.md", "# Demo\n")
    write_file(repo / "app" / "api" / "main.py", "from fastapi import FastAPI\n")
    write_file(repo / "core" / "runtime.py", "print('runtime')\n")
    write_file(repo / "tests" / "test_runtime.py", "def test_demo(): assert True\n")
    write_file(repo / "apps" / "elysia-desktop" / "package.json", "{}\n")
    write_file(repo / "apps" / "elysia-desktop" / "src" / "App.tsx", "export default function App() { return null }\n")
    write_file(repo / "apps" / "elysia-desktop" / "src-tauri" / "tauri.conf.json", "{}\n")
    write_file(repo / "apps" / "elysia-desktop" / "vite.config.ts", "export default {}\n")
    write_file(repo / "scripts" / "test_backend.sh", "#!/usr/bin/env bash\n")
    write_file(repo / "config" / "models" / "routing.yaml", "version: 1\n")
    write_file(repo / ".git" / "HEAD", "ref: refs/heads/main\n")

    return repo


def test_loads_simple_approved_repos_config_without_yaml_dependency(tmp_path):
    repo = make_demo_repo(tmp_path)
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    loaded = load_approved_repos_config(config)

    assert loaded["version"] == 1
    assert loaded["default_repo_key"] == "demo"
    assert loaded["inspection_defaults"]["max_depth"] == 4
    assert loaded["repos"]["demo"]["root"] == str(repo)
    assert loaded["repos"]["demo"]["allowed"] is True
    assert loaded["repos"]["demo"]["notes"] == ["Approved test repo."]


def test_approved_repo_context_completes_with_local_boundary_truth(tmp_path):
    repo = make_demo_repo(tmp_path)
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    result = gather_repo_context(repo_key="demo", config_path=config)

    assert result.ok is True
    assert result.status == RepoContextStatus.COMPLETED
    assert result.tool_kind == REPO_CONTEXT_TOOL_KIND
    assert result.operation == REPO_CONTEXT_OPERATION
    assert result.repo_key == "demo"
    assert result.repo_label == "Demo repo"
    assert result.repo_root == str(repo.resolve(strict=False))
    assert result.trust_zone == "project_local"

    assert result.appears_git_repo is True
    assert result.current_branch == "main"
    assert result.git_head_read is True
    assert result.changed_files_live is False
    assert result.changed_files_note == CHANGED_FILES_NOTE

    assert "README.md" in result.important_top_level_files
    assert "app" in result.top_level_directories
    assert "core" in result.top_level_directories
    assert "tests" in result.top_level_directories

    assert "Python" in result.language_hints
    assert "TypeScript" in result.language_hints
    assert "Markdown" in result.language_hints
    assert "JSON" in result.language_hints
    assert "YAML" in result.language_hints

    assert "FastAPI local API bridge" in result.framework_hints
    assert "React desktop UI" in result.framework_hints
    assert "Tauri desktop shell" in result.framework_hints
    assert "Vite frontend build" in result.framework_hints
    assert "Pytest backend tests" in result.framework_hints
    assert "Core Python organs" in result.framework_hints
    assert "Local model/API routing config" in result.framework_hints

    assert "./scripts/test_backend.sh -q" in result.test_command_hints
    assert "npm --prefix apps/elysia-desktop run typecheck" in result.test_command_hints
    assert "npm --prefix apps/elysia-desktop run build" in result.test_command_hints

    assert result.locality == "local"
    assert result.read_only is True
    assert result.approval_required is False
    assert result.network_access_used is False
    assert result.shell_used is False
    assert result.mutated_files is False
    assert "No shell commands were run." in result.boundary_notes
    assert result.errors == []


def test_default_repo_key_is_used_when_no_repo_is_requested(tmp_path):
    repo = make_demo_repo(tmp_path)
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    result = gather_repo_context(config_path=config)

    assert result.ok is True
    assert result.repo_key == "demo"
    assert result.repo_root == str(repo.resolve(strict=False))


def test_approved_repo_root_can_be_selected_directly(tmp_path):
    repo = make_demo_repo(tmp_path)
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    result = gather_repo_context(repo_root=repo, config_path=config)

    assert result.ok is True
    assert result.repo_key == "demo"
    assert result.requested_path == str(repo)


def test_unapproved_repo_root_is_blocked(tmp_path):
    repo = make_demo_repo(tmp_path)
    unapproved = tmp_path / "not_approved"
    unapproved.mkdir()
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    result = gather_repo_context(repo_root=unapproved, config_path=config)

    assert result.ok is False
    assert result.status == RepoContextStatus.BLOCKED
    assert "not an approved repository root" in result.errors[0]
    assert result.network_access_used is False
    assert result.shell_used is False
    assert result.mutated_files is False


def test_parent_path_traversal_is_blocked(tmp_path):
    repo = make_demo_repo(tmp_path)
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    result = gather_repo_context(repo_root=tmp_path, config_path=config)

    assert result.ok is False
    assert result.status == RepoContextStatus.BLOCKED
    assert "not an approved repository root" in result.errors[0]


def test_restricted_and_secret_looking_paths_are_skipped(tmp_path):
    repo = tmp_path / "repo"
    write_file(repo / "normal.py", "print('safe')\n")
    write_file(repo / "README.md", "# Demo\n")
    write_file(repo / "vault" / "private.md", "secret\n")
    write_file(repo / ".env", "TOKEN=abc\n")
    write_file(repo / "secrets" / "token.txt", "abc\n")
    write_file(repo / "node_modules" / "pkg" / "index.js", "bad\n")
    write_file(repo / ".venv" / "bin" / "python", "bad\n")
    write_file(repo / "__pycache__" / "x.pyc", "bad\n")
    write_file(repo / "id_rsa", "bad\n")
    write_file(repo / "deploy.pem", "bad\n")
    write_file(repo / ".git" / "HEAD", "ref: refs/heads/main\n")

    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    result = gather_repo_context(repo_key="demo", config_path=config)

    assert result.ok is True
    assert "normal.py" in result.safe_tree_entries
    assert "README.md" in result.safe_tree_entries

    assert "vault/private.md" not in result.safe_tree_entries
    assert ".env" not in result.safe_tree_entries
    assert "secrets/token.txt" not in result.safe_tree_entries
    assert "node_modules/pkg/index.js" not in result.safe_tree_entries
    assert ".venv/bin/python" not in result.safe_tree_entries
    assert "__pycache__/x.pyc" not in result.safe_tree_entries
    assert "id_rsa" not in result.safe_tree_entries
    assert "deploy.pem" not in result.safe_tree_entries
    assert ".git/HEAD" not in result.safe_tree_entries

    assert "vault" in result.skipped_paths
    assert ".env" in result.skipped_paths
    assert "secrets" in result.skipped_paths
    assert "node_modules" in result.skipped_paths
    assert ".venv" in result.skipped_paths
    assert "__pycache__" in result.skipped_paths
    assert "id_rsa" in result.skipped_paths
    assert "deploy.pem" in result.skipped_paths
    assert ".git" in result.skipped_paths


def test_reads_only_minimal_git_head_truth(tmp_path):
    repo = tmp_path / "repo"
    write_file(repo / "README.md", "# Demo\n")
    write_file(repo / ".git" / "HEAD", "ref: refs/heads/feature/coder-mode\n")
    write_file(repo / ".git" / "objects" / "aa" / "object", "do not inspect\n")
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    result = gather_repo_context(repo_key="demo", config_path=config)

    assert result.ok is True
    assert result.appears_git_repo is True
    assert result.current_branch == "feature/coder-mode"
    assert result.git_head_read is True
    assert result.changed_files_live is False
    assert result.changed_files_note == CHANGED_FILES_NOTE
    assert ".git/objects/aa/object" not in result.safe_tree_entries
    assert ".git" in result.skipped_paths


def test_missing_config_fails_safely(tmp_path):
    result = gather_repo_context(config_path=tmp_path / "missing.yaml")

    assert result.ok is False
    assert result.status == RepoContextStatus.FAILED
    assert "Approved repo config could not be loaded" in result.errors[0]
    assert "Approved repo config not found" in result.errors[0]
    assert result.network_access_used is False
    assert result.shell_used is False
    assert result.mutated_files is False


def test_missing_repo_key_is_blocked(tmp_path):
    repo = make_demo_repo(tmp_path)
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    result = gather_repo_context(repo_key="unknown", config_path=config)

    assert result.ok is False
    assert result.status == RepoContextStatus.BLOCKED
    assert "Repo key is not approved" in result.errors[0]


def test_result_payload_is_json_safe(tmp_path):
    repo = make_demo_repo(tmp_path)
    config = write_config(tmp_path / "config" / "approved_repos.yaml", repo)

    payload = gather_repo_context(repo_key="demo", config_path=config).to_payload()

    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert payload["tool_kind"] == REPO_CONTEXT_TOOL_KIND
    assert payload["operation"] == REPO_CONTEXT_OPERATION
    assert payload["repo_key"] == "demo"
    assert payload["locality"] == "local"
    assert payload["read_only"] is True
    assert payload["network_access_used"] is False
    assert payload["shell_used"] is False
    assert payload["mutated_files"] is False
