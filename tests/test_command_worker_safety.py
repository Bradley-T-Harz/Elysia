from __future__ import annotations

from sandbox.command_worker import CommandWorkerRequest, CommandWorkerStatus, run_command_worker
from sandbox.command_worker.command_guard import command_key_for_argv


def test_command_guard_allows_exact_frontend_typecheck_command():
    argv = ["npm", "--prefix", "apps/elysia-desktop", "run", "typecheck"]

    assert command_key_for_argv(argv) == ("frontend_typecheck", None)


def test_command_guard_blocks_arbitrary_npm_install():
    argv = ["npm", "install"]

    key, error = command_key_for_argv(argv)
    assert key is None
    assert error


def test_command_worker_requires_approval_before_execution(tmp_path):
    request = CommandWorkerRequest(
        request_id="req_cmd_test",
        repo_key="tmp",
        cwd=str(tmp_path),
        command_key="py_compile_file",
        argv=["python", "-m", "py_compile", "sample.py"],
        approval_reference="approval",
        approved_by_user=False,
    )

    result = run_command_worker(request, repo_root=str(tmp_path))

    assert result.status == CommandWorkerStatus.BLOCKED
    assert result.shell_used is False
    assert result.mutated_files is False
    assert result.git_mutation_used is False


def test_command_worker_runs_allowlisted_command_with_shell_false(tmp_path):
    (tmp_path / "sample.py").write_text("x = 1\n", encoding="utf-8")
    request = CommandWorkerRequest(
        request_id="req_cmd_test",
        repo_key="tmp",
        cwd=str(tmp_path),
        command_key="py_compile_file",
        argv=["python", "-m", "py_compile", "sample.py"],
        approval_reference="approval",
        approved_by_user=True,
    )

    result = run_command_worker(request, repo_root=str(tmp_path))

    assert result.status == CommandWorkerStatus.COMPLETED
    assert result.exit_code == 0
    assert result.allowlist_matched is True
    assert result.shell_used is False
    assert result.mutated_files is False
    assert result.git_mutation_used is False
