from __future__ import annotations

from pathlib import Path

from sandbox.aider_worker.config import load_aider_worker_config
from sandbox.aider_worker.contract import AiderWorkerRequest, AiderWorkerStatus
from sandbox.aider_worker.worker import run_aider_worker_dry_run


def write_file(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_aider_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "worker_key: aider_worker",
                "worker_kind: governed_coding_worker",
                "state: skeleton",
                "default_repo_key: demo",
                "contract_doc: docs/coder/aider_worker_contract.md",
                "",
                "posture:",
                "  dry_run_only: true",
                "  mutation_allowed: false",
                "  shell_allowed: false",
                "  test_execution_allowed: false",
                "  network_allowed: false",
                "  git_mutation_allowed: false",
                "  package_install_allowed: false",
                "  credentials_allowed: false",
                "  vault_allowed: false",
                "  home_access_allowed: false",
                "  cloud_model_allowed: false",
                "  external_worker_invocation_allowed: false",
                "  approval_required_before_mutation: true",
                "  human_review_required: true",
                "",
                "filesystem:",
                "  selected_repo_mounts_only: true",
                "  repo_key_required: true",
                "  allow_absolute_paths: false",
                "  allow_path_traversal: false",
                "  max_selected_files: 24",
                "  max_file_size_bytes: 250000",
                "  max_path_length: 512",
                "",
                "denied_path_fragments:",
                "  - vault",
                "  - secrets",
                "  - credentials",
                "  - private",
                "  - .git",
                "  - node_modules",
                "  - dist",
                "  - build",
                "  - target",
                "  - .venv",
                "  - __pycache__",
                "  - .pytest_cache",
                "  - memory/chroma",
                "  - data/conversations",
                "  - data/artifacts",
                "  - data/file_ingest/raw",
                "  - data/file_ingest/extracted",
                "",
                "denied_file_names:",
                "  - .env",
                "  - .env.local",
                "  - id_rsa",
                "  - id_ed25519",
                "  - known_hosts",
                "  - authorized_keys",
                "",
                "denied_file_suffixes:",
                "  - .pem",
                "  - .key",
                "  - .sqlite",
                "  - .db",
                "  - .pyc",
                "  - .so",
                "  - .exe",
                "  - .bin",
                "",
                "secret_name_fragments:",
                "  - token",
                "  - secret",
                "  - credential",
                "  - password",
                "  - passwd",
                "  - apikey",
                "  - api_key",
                "  - private_key",
                "",
                "trace:",
                "  log_worker_request: true",
                "  log_worker_result: true",
                "  include_files_considered: true",
                "  include_boundary_flags: true",
                "  include_refusal_reasons: true",
                "  never_log_raw_secrets: true",
                "  never_log_vault_contents: true",
                "",
                "ui_truth:",
                "  state_label: skeleton",
                "  locality: Local",
                "  read_only: true",
                "  draft_only: true",
                "  sandboxed: true",
                "  mutation_label: not_live",
                "  shell_label: blocked",
                "  network_label: blocked",
                "  cloud_model_label: not_used",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_approved_repos_config(path: Path, repo_root: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "default_repo_key: demo",
                "",
                "inspection_defaults:",
                "  shell_allowed: false",
                "  network_allowed: false",
                "  file_mutation_allowed: false",
                "",
                "repos:",
                "  demo:",
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


def make_request(**overrides) -> AiderWorkerRequest:
    values = {
        "request_id": "req-test",
        "worker_key": "aider_worker",
        "repo_key": "demo",
        "repo_root": "",
        "trust_zone": "project_local",
        "user_goal": "Prepare a dry-run patch proposal.",
        "mode": "dry_run",
        "selected_files": ["core/runtime.py", "tests/test_runtime.py"],
        "dry_run_only": True,
        "network_allowed": False,
        "shell_allowed": False,
        "test_execution_allowed": False,
        "mutation_allowed": False,
        "git_mutation_allowed": False,
        "package_install_allowed": False,
        "credentials_allowed": False,
        "vault_allowed": False,
        "home_access_allowed": False,
        "cloud_model_allowed": False,
        "model_provider_policy": "local_only",
    }
    values.update(overrides)
    return AiderWorkerRequest(**values)


def make_configs(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    write_file(repo / "core" / "runtime.py", "print('safe')\n")
    write_file(repo / "tests" / "test_runtime.py", "def test_demo(): assert True\n")
    aider_config = write_aider_config(tmp_path / "config" / "workers" / "aider_worker.yaml")
    approved_config = write_approved_repos_config(
        tmp_path / "config" / "coder" / "approved_repos.yaml",
        repo,
    )
    return aider_config, approved_config


def run_request(tmp_path: Path, request: AiderWorkerRequest):
    aider_config, approved_config = make_configs(tmp_path)
    return run_aider_worker_dry_run(
        request,
        config_path=aider_config,
        approved_repos_config_path=approved_config,
    )


def assert_no_execution_or_mutation(result) -> None:
    assert result.worker_used is False
    assert result.aider_invoked is False
    assert result.mutated_files is False
    assert result.shell_used is False
    assert result.network_used is False
    assert result.test_execution_used is False
    assert result.git_mutation_used is False
    assert result.package_install_used is False
    assert result.external_model_used is False


def assert_blocked(result) -> None:
    assert result.status == AiderWorkerStatus.BLOCKED
    assert_no_execution_or_mutation(result)
    assert result.refusal_reasons


def test_loads_aider_worker_config_with_safe_defaults(tmp_path):
    config_path, _approved_config = make_configs(tmp_path)

    config = load_aider_worker_config(config_path)

    assert config.worker_key == "aider_worker"
    assert config.worker_kind == "governed_coding_worker"
    assert config.state == "skeleton"
    assert config.posture["dry_run_only"] is True
    assert config.posture["mutation_allowed"] is False
    assert config.posture["shell_allowed"] is False
    assert config.posture["test_execution_allowed"] is False
    assert config.posture["network_allowed"] is False
    assert config.posture["git_mutation_allowed"] is False
    assert config.posture["package_install_allowed"] is False
    assert config.posture["credentials_allowed"] is False
    assert config.posture["vault_allowed"] is False
    assert config.posture["home_access_allowed"] is False
    assert config.posture["cloud_model_allowed"] is False
    assert config.posture["external_worker_invocation_allowed"] is False
    assert ".git" in config.denied_path_fragments
    assert ".env" in config.denied_file_names
    assert ".key" in config.denied_file_suffixes
    assert "token" in config.secret_name_fragments


def test_safe_dry_run_request_returns_dry_run_ready(tmp_path):
    result = run_request(tmp_path, make_request())

    assert result.status == AiderWorkerStatus.DRY_RUN_READY
    assert_no_execution_or_mutation(result)
    assert result.approval_required is True
    assert result.files_considered == ["core/runtime.py", "tests/test_runtime.py"]
    assert result.files_proposed == ["core/runtime.py", "tests/test_runtime.py"]
    assert "Aider subprocess invocation is not live." in result.warnings


def test_unknown_repo_key_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(repo_key="unknown"))

    assert_blocked(result)
    assert any("not approved" in reason for reason in result.refusal_reasons)


def test_absolute_paths_are_blocked(tmp_path):
    result = run_request(tmp_path, make_request(selected_files=["/etc/passwd"]))

    assert_blocked(result)
    assert any("relative to an approved repo" in reason for reason in result.refusal_reasons)


def test_home_paths_are_blocked(tmp_path):
    result = run_request(tmp_path, make_request(selected_files=["~/secrets.txt"]))

    assert_blocked(result)
    assert any("relative to an approved repo" in reason for reason in result.refusal_reasons)


def test_path_traversal_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(selected_files=["../outside.py"]))

    assert_blocked(result)
    assert any("must not traverse" in reason for reason in result.refusal_reasons)


def test_vault_paths_are_blocked(tmp_path):
    result = run_request(tmp_path, make_request(selected_files=["vault/foo.md"]))

    assert_blocked(result)
    assert any("denied or generated" in reason for reason in result.refusal_reasons)


def test_secret_and_credential_paths_are_blocked(tmp_path):
    for unsafe_path in [
        "secrets/key.txt",
        "credentials/token.json",
        "private/journal.md",
        ".env",
        ".env.local",
        "id_rsa",
        "id_ed25519",
        "api_key.txt",
        "token.json",
        "deploy.pem",
    ]:
        result = run_request(tmp_path, make_request(selected_files=[unsafe_path]))

        assert_blocked(result)


def test_generated_and_dependency_paths_are_blocked(tmp_path):
    for unsafe_path in [
        "node_modules/pkg/index.js",
        ".git/config",
        ".venv/bin/python",
        "dist/bundle.js",
        "build/output.js",
        "target/debug/app",
        "__pycache__/x.pyc",
        ".pytest_cache/v/cache/nodeids",
        "memory/chroma/index",
        "data/conversations/conv_x.json",
        "data/artifacts/artifact_x.json",
        "data/file_ingest/raw/file.txt",
        "data/file_ingest/extracted/file.txt",
    ]:
        result = run_request(tmp_path, make_request(selected_files=[unsafe_path]))

        assert_blocked(result)


def test_mutation_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(mutation_allowed=True))

    assert_blocked(result)
    assert any("Mutation is not live" in reason for reason in result.refusal_reasons)


def test_shell_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(shell_allowed=True))

    assert_blocked(result)
    assert any("Shell execution is not live" in reason for reason in result.refusal_reasons)


def test_test_execution_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(test_execution_allowed=True))

    assert_blocked(result)
    assert any("Test execution is not live" in reason for reason in result.refusal_reasons)


def test_network_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(network_allowed=True))

    assert_blocked(result)
    assert any("Network access is not live" in reason for reason in result.refusal_reasons)


def test_git_mutation_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(git_mutation_allowed=True))

    assert_blocked(result)
    assert any("Git mutation is not live" in reason for reason in result.refusal_reasons)


def test_package_install_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(package_install_allowed=True))

    assert_blocked(result)
    assert any("Package installation is not live" in reason for reason in result.refusal_reasons)


def test_credentials_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(credentials_allowed=True))

    assert_blocked(result)
    assert any("Credential access is not allowed" in reason for reason in result.refusal_reasons)


def test_vault_access_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(vault_allowed=True))

    assert_blocked(result)
    assert any("Vault access is not allowed" in reason for reason in result.refusal_reasons)


def test_broad_home_access_request_is_blocked(tmp_path):
    result = run_request(tmp_path, make_request(home_access_allowed=True))

    assert_blocked(result)
    assert any("Home directory access is not allowed" in reason for reason in result.refusal_reasons)


def test_cloud_model_request_is_blocked(tmp_path):
    result = run_request(
        tmp_path,
        make_request(cloud_model_allowed=True, model_provider_policy="cloud_allowed"),
    )

    assert_blocked(result)
    assert any("Cloud model use is not live" in reason for reason in result.refusal_reasons)
    assert any("cloud or external models" in reason for reason in result.refusal_reasons)


def test_blocked_result_never_claims_execution_or_mutation(tmp_path):
    result = run_request(
        tmp_path,
        make_request(
            mutation_allowed=True,
            shell_allowed=True,
            network_allowed=True,
            test_execution_allowed=True,
            git_mutation_allowed=True,
            package_install_allowed=True,
            cloud_model_allowed=True,
            user_goal="I applied the patch and ran the tests.",
        ),
    )

    assert_blocked(result)
    assert result.commands_run == []
    assert result.tests_run == []
    assert result.files_proposed == []
    assert any(
        "must not claim" in reason
        for reason in result.refusal_reasons
    )
