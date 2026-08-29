from __future__ import annotations

from pathlib import Path
import asyncio
import subprocess
from types import SimpleNamespace

import httpx

from app.api import coding_git_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.codev_profile_service import build_codev_developer_profile_status
from app.api.coding_command_allowlist_service import public_command_catalog
from app.api.coding_process_service import sanitize_command_output
from app.api.coding_repo_approval_service import (
    apply_repo_approval,
    clear_repo_approval_plans_for_tests,
    plan_repo_approval,
    repo_approval_status,
    revoke_repo,
)
from app.api.coding_path_guard_service import guard_workspace_path
from app.api.coding_repo_registry import list_approved_repo_roots
from app.api.coding_task_service import (
    advance_coding_task,
    approve_coding_task,
    clear_task_state_for_tests,
    plan_coding_task,
    stop_coding_task,
)
from app.api.schemas.coding import (
    CodingRepoApprovalApplyRequest,
    CodingRepoApprovalPlanRequest,
    CodingRepoApprovalStatusRequest,
    CodingRepoRevokeRequest,
)
from app.api.schemas.coding_git import CodingGitPreviewRequest
from app.api.schemas.coding_tasks import (
    CodingTaskApproveRequest,
    CodingTaskCheckpointRequest,
    CodingTaskPlanRequest,
    CodingTaskStopRequest,
)
from app.api.schemas.account import AccountCreateRequest
from app.install.codev_service import read_codev_install_status
from app.install.local_auth import LocalApiAuthPolicy
from app.install.paths import RuntimeMode, resolve_elysia_paths
from app.api.main import create_app


def _xdg(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))


def test_repo_approval_is_exact_xdg_local_and_revocable(tmp_path, monkeypatch):
    _xdg(monkeypatch, tmp_path)
    monkeypatch.setenv("ELYSIA_CODING_APPROVED_ROOTS", "")
    repo = tmp_path / "workspace"
    repo.mkdir()
    clear_repo_approval_plans_for_tests()

    before = repo_approval_status(CodingRepoApprovalStatusRequest(workspace_root=str(repo)))
    assert before.status == "approval_required"
    assert before.approved is False
    assert str(repo) not in before.model_dump_json()

    plan = plan_repo_approval(CodingRepoApprovalPlanRequest(workspace_root=str(repo)))
    result = apply_repo_approval(
        CodingRepoApprovalApplyRequest(
            plan_id=plan.plan_id or "",
            plan_hash=plan.plan_hash or "",
            operator_approved=True,
            confirmation_phrase="Approve exact repository",
        )
    )
    assert result.status == "approved"
    assert repo_approval_status(CodingRepoApprovalStatusRequest(workspace_root=str(repo))).approved is True
    nested = repo / "nested"
    nested.mkdir()
    nested_guard = guard_workspace_path(
        workspace_root=str(nested),
        target_path=".",
        require_existing=True,
        allow_directory=True,
    )
    assert nested_guard.allowed is False
    assert nested_guard.reason == "workspace_root_not_approved"

    revoked = revoke_repo(
        CodingRepoRevokeRequest(
            workspace_root=str(repo),
            operator_approved=True,
            confirmation_phrase="Revoke repository approval",
        )
    )
    assert revoked.status == "revoked"
    assert repo_approval_status(CodingRepoApprovalStatusRequest(workspace_root=str(repo))).approved is False


def test_repo_registry_ignores_tampered_root_hash(tmp_path, monkeypatch):
    _xdg(monkeypatch, tmp_path)
    repo = tmp_path / "workspace"
    repo.mkdir()
    registry = tmp_path / "config" / "elysia" / "coding" / "approved-repos.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        '{"version":1,"repos":{"wrong-hash":{"root":"'
        + str(repo)
        + '","approved":true,"revoked":false}}}\n',
        encoding="utf-8",
    )
    assert list_approved_repo_roots(registry) == []


def test_repo_approval_refuses_broad_roots(monkeypatch, tmp_path):
    _xdg(monkeypatch, tmp_path)
    plan = plan_repo_approval(CodingRepoApprovalPlanRequest(workspace_root="/tmp"))
    assert plan.status == "blocked"
    assert plan.blocked_reason == "workspace_root_too_broad"


def test_git_truth_uses_fixed_status_and_returns_real_scm_files(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    monkeypatch.setenv("ELYSIA_CODING_APPROVED_ROOTS", str(repo))
    monkeypatch.setattr(coding_git_service.shutil, "which", lambda name: "/usr/bin/git")
    calls: list[list[str]] = []

    def fake_run(_git: str, _root: Path, args: list[str]):
        calls.append(args)
        if args == ["remote"]:
            return subprocess.CompletedProcess(args, 0, "origin\n", "")
        return subprocess.CompletedProcess(
            args,
            0,
            "# branch.oid 0123456789abcdef\n# branch.head main\n# branch.upstream origin/main\n1 M. N... 100644 100644 100644 a a src/app.py\n? new.txt\n",
            "",
        )

    monkeypatch.setattr(coding_git_service, "_run_git", fake_run)
    result = coding_git_service.preview_git_state(CodingGitPreviewRequest(workspace_root=str(repo)))

    assert result.status == "read_only_status"
    assert result.branch == "main"
    assert result.dirty is True
    assert result.changed_count == 2
    assert result.staged_count == 1
    assert result.untracked_count == 1
    assert [item.relative_path for item in result.changed_files] == ["src/app.py", "new.txt"]
    assert calls == [
        ["status", "--porcelain=v2", "--branch", "--untracked-files=normal"],
        ["remote"],
    ]
    assert result.mutation_allowed is False
    assert result.shell_git_used is False


def test_command_catalog_and_output_are_bounded_and_sanitized(tmp_path):
    catalog = public_command_catalog()
    enabled = [entry for entry in catalog["entries"] if entry["execution_enabled"]]
    assert [entry["command_id"] for entry in enabled] == ["git_diff_check"]
    assert catalog["arbitrary_command_input_allowed"] is False
    assert catalog["shell_allowed"] is False

    raw = f"{tmp_path}/file.py token=secret-value\n-----BEGIN PRIVATE KEY-----\n"
    sanitized, truncated = sanitize_command_output(raw, workspace_root=tmp_path, limit=1000)
    assert str(tmp_path) not in sanitized
    assert "secret-value" not in sanitized
    assert "BEGIN PRIVATE KEY" not in sanitized
    assert truncated is False


def test_developer_lab_task_is_checkpoint_only_stoppable_and_receipted(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_CODING_APPROVED_ROOTS", str(tmp_path))
    source = tmp_path / "app.py"
    source.write_text("print('safe')\n", encoding="utf-8")
    clear_task_state_for_tests()

    plan = plan_coding_task(
        CodingTaskPlanRequest(
            objective="Prepare a reviewed change",
            workspace_label="test repo",
            workspace_root=str(tmp_path),
            allowed_files=["app.py"],
            max_steps=2,
            max_minutes=5,
        )
    )
    assert plan.status == "approval_required"
    assert plan.autonomous_loop_allowed is False
    assert plan.background_execution_allowed is False
    assert plan.mutation_allowed is False

    approval = approve_coding_task(
        CodingTaskApproveRequest(
            task_id=plan.task_id or "",
            task_hash=plan.task_hash or "",
            operator_approved=True,
            confirmation_phrase="Approve bounded Developer Lab plan",
        )
    )
    checkpoint = advance_coding_task(
        CodingTaskCheckpointRequest(
            task_id=plan.task_id or "",
            task_token=approval.task_token,
            operator_approved=True,
        )
    )
    assert checkpoint.status == "checkpoint_ready"
    assert checkpoint.execution_performed is False
    assert checkpoint.mutation_performed is False
    assert checkpoint.command_performed is False
    assert checkpoint.continuation_scheduled is False
    assert checkpoint.receipt_id

    stopped = stop_coding_task(CodingTaskStopRequest(task_id=plan.task_id or ""))
    assert stopped.status == "stopped"
    assert stopped.stopped is True
    assert stopped.continuation_scheduled is False


def test_codev_receipt_and_developer_profile_truth_are_sanitized(tmp_path, monkeypatch):
    _xdg(monkeypatch, tmp_path)
    paths = resolve_elysia_paths(mode=RuntimeMode.TEST)
    assert read_codev_install_status(paths)["state"] == "missing"
    receipt = paths.data_dir / "developer" / "codev-install.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        '{"schema_version":1,"extension_id":"ecosyneva-commons.elysia-codev","version":"1.0.0","contract_version":"vscode-coding-agent-contract-0.1","install_state":"installed_by_user"}\n',
        encoding="utf-8",
    )
    status = read_codev_install_status(paths)
    assert status["compatible"] is True
    assert str(tmp_path) not in str(status)

    profile = build_codev_developer_profile_status()
    assert profile["official_addon"] is True
    assert profile["public_distribution_supported"] is True
    assert profile["in_app_install_control_available"] is False
    assert profile["arbitrary_shell_allowed"] is False
    assert profile["raw_paths_exposed"] is False


def test_developer_profile_uses_effective_editor_and_receipt_truth(monkeypatch):
    profile = SimpleNamespace(
        available_profiles=[
            SimpleNamespace(
                profile_id="developer",
                display_name="Developer / Codev",
                readiness="unknown",
            )
        ],
        dependencies=[
            SimpleNamespace(
                dependency_id="vscode",
                status="unknown",
                required=True,
                activation_state="active_profile_truth_only",
                version=None,
            ),
            SimpleNamespace(
                dependency_id="git",
                status="present",
                required=True,
                activation_state="active_profile_truth_only",
                version=None,
            ),
            SimpleNamespace(
                dependency_id="codev_vsix",
                status="unknown",
                required=True,
                activation_state="active_profile_truth_only",
                version=None,
            ),
        ],
        resolved_profile_ids=["core", "developer"],
    )
    monkeypatch.setattr(
        "app.api.codev_profile_service.resolve_install_profile_status",
        lambda: (profile, []),
    )
    monkeypatch.setattr(
        "app.api.codev_profile_service.read_codev_install_status",
        lambda: {
            "compatible": True,
            "installed": True,
            "version": "1.0.0",
            "state": "installed",
        },
    )
    monkeypatch.setattr(
        "app.api.codev_profile_service.read_codev_repo_approval_status",
        lambda: {"approved_repo_count": 1, "raw_paths_exposed": False},
    )
    monkeypatch.setattr(
        "app.api.codev_profile_service.build_local_api_auth_policy",
        lambda initialize=False: SimpleNamespace(
            public_summary=lambda: {"required_for_mutations": True}
        ),
    )
    monkeypatch.setattr(
        "app.api.codev_profile_service.shutil.which",
        lambda command: "/usr/bin/code" if command == "code" else None,
    )

    status = build_codev_developer_profile_status()

    assert status["status"] == "ready"
    assert status["profile_readiness"] == "ready"
    assert status["dependencies"]["vscode"]["status"] == "present"
    assert status["dependencies"]["codev_vsix"]["status"] == "present"
    assert status["dependencies"]["codev_vsix"]["version"] == "1.0.0"


def test_codev_installer_is_dry_run_first_and_binds_a_bounded_local_package():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "install_codev.sh").read_text(encoding="utf-8")
    assert 'MODE="dry-run"' in script
    assert 'ENTRY_COUNT' in script
    assert 'UNCOMPRESSED_BYTES' in script
    assert 'PACKAGE_HASH="$(sha256sum' in script
    assert 'package_sha256' in script
    assert 'code|code-insiders|codium|vscodium' in script
    assert '--install-extension "$VSIX_PATH" --force' in script


def test_codev_routes_require_auth_and_return_profile_repo_git_catalog_and_task_truth(tmp_path, monkeypatch):
    _xdg(monkeypatch, tmp_path)
    elysia_paths = resolve_elysia_paths()
    identity_root = elysia_paths.identity_dir
    account_store = AccountStore(AccountPaths(
        identity_root=identity_root,
        database_path=identity_root / "elysia_identity.sqlite",
        profile_photo_dir=identity_root / "profile_photos",
        current_session_path=identity_root / "current_session.json",
        elysia_paths=elysia_paths,
    ))
    account_store.create_account(AccountCreateRequest(
        username="synthetic-codev-owner",
        password="synthetic codev owner password",
    ))
    monkeypatch.setattr(
        "app.api.user_control_service.get_authenticated_governance",
        account_store.authenticated_governance,
    )
    monkeypatch.setenv("ELYSIA_CODING_APPROVED_ROOTS", "")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (repo / "app.py").write_text("print('local')\n", encoding="utf-8")
    credential = "codev-test-credential-" + "x" * 40
    policy = LocalApiAuthPolicy(
        required=True,
        credential_path=tmp_path / "credential",
        runtime_mode=RuntimeMode.TEST,
        source="test",
        expected_credential=credential,
    )

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=create_app(auth_policy=policy))
        async with httpx.AsyncClient(transport=transport, base_url="http://testclient") as client:
            profile_response = await client.get("/coding/developer-profile")
            assert profile_response.status_code == 200
            assert profile_response.json()["data"]["developer_profile"]["official_addon"] is True

            unauthenticated = await client.post("/coding/repo/approval-status", json={"workspace_root": str(repo)})
            assert unauthenticated.status_code == 401
            assert unauthenticated.json()["data"]["credential_exposed"] is False

            headers = {"Authorization": f"Bearer {credential}", "X-Elysia-Client": "codev-test"}
            planned = await client.post("/coding/repo/approval-plan", headers=headers, json={"workspace_root": str(repo)})
            plan = planned.json()["data"]["repo_approval_plan"]
            applied = await client.post(
                "/coding/repo/approval-apply",
                headers=headers,
                json={"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"], "operator_approved": True, "confirmation_phrase": "Approve exact repository"},
            )
            assert applied.json()["data"]["repo_approval_result"]["approved"] is True

            git_response = await client.post("/coding/git/preview", headers=headers, json={"workspace_root": str(repo)})
            git_truth = git_response.json()["data"]["git_preview"]
            assert git_truth["approved_repo"] is True
            assert git_truth["shell_git_used"] is False
            assert str(repo) not in str(git_truth)

            catalog_response = (await client.get("/coding/command/catalog")).json()
            assert catalog_response["capability_state"] == "live"
            assert catalog_response["approval_state"] == "not_needed"
            catalog = catalog_response["data"]["command_catalog"]
            assert catalog["arbitrary_command_input_allowed"] is False

            task = await client.post(
                "/coding/task/plan",
                headers=headers,
                json={"objective": "Prepare one bounded plan", "workspace_root": str(repo), "allowed_files": ["app.py"], "max_steps": 2, "max_minutes": 5},
            )
            task_plan = task.json()["data"]["task_plan"]
            assert task_plan["status"] == "approval_required"
            assert task_plan["autonomous_loop_allowed"] is False
            assert task_plan["background_execution_allowed"] is False

    asyncio.run(exercise())
