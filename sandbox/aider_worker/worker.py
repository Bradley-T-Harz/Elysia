from __future__ import annotations

from pathlib import Path
from typing import Any

from core.repo_context_gatherer import load_approved_repos_config

from .config import DEFAULT_AIDER_WORKER_CONFIG_PATH, AiderWorkerConfig, load_aider_worker_config
from .contract import AiderWorkerRequest, AiderWorkerResult, AiderWorkerStatus
from .path_guard import validate_selected_files


APPROVED_REPOS_CONFIG_PATH = Path("config/coder/approved_repos.yaml")
APPROVAL_REASON = "Approval is required before any future mutation."
NO_MUTATION_WARNING = "No files were changed."
DRY_RUN_WARNING = "Aider subprocess invocation is not live."

DANGEROUS_REQUEST_FLAGS = {
    "mutation_allowed": "Mutation is not live for the Aider worker skeleton.",
    "shell_allowed": "Shell execution is not live for the Aider worker skeleton.",
    "test_execution_allowed": "Test execution is not live for the Aider worker skeleton.",
    "network_allowed": "Network access is not live for the Aider worker skeleton.",
    "git_mutation_allowed": "Git mutation is not live for the Aider worker skeleton.",
    "package_install_allowed": "Package installation is not live for the Aider worker skeleton.",
    "credentials_allowed": "Credential access is not allowed for the Aider worker skeleton.",
    "vault_allowed": "Vault access is not allowed for the Aider worker skeleton.",
    "home_access_allowed": "Home directory access is not allowed for the Aider worker skeleton.",
    "cloud_model_allowed": "Cloud model use is not live for the Aider worker skeleton.",
}

REQUIRED_FALSE_POSTURE_FLAGS = {
    "mutation_allowed",
    "shell_allowed",
    "test_execution_allowed",
    "network_allowed",
    "git_mutation_allowed",
    "package_install_allowed",
    "credentials_allowed",
    "vault_allowed",
    "home_access_allowed",
    "cloud_model_allowed",
    "external_worker_invocation_allowed",
}

REQUIRED_TRUE_POSTURE_FLAGS = {
    "dry_run_only",
    "approval_required_before_mutation",
    "human_review_required",
}

FALSE_EXECUTION_CLAIMS = {
    "aider ran",
    "aider invoked",
    "i invoked aider",
    "i applied",
    "applied the patch",
    "already applied",
    "i changed",
    "changed the file",
    "i wrote the file",
    "wrote the file",
    "i ran the tests",
    "ran the tests",
    "tests passed",
    "i committed",
    "committed the change",
    "git commit",
    "git push",
}


def _blocked_result(
    *,
    request: AiderWorkerRequest,
    refusal_reasons: list[str],
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    files_considered: list[str] | None = None,
) -> AiderWorkerResult:
    return AiderWorkerResult(
        status=AiderWorkerStatus.BLOCKED,
        worker_key=request.worker_key,
        worker_used=False,
        aider_invoked=False,
        repo_key=request.repo_key,
        repo_root=request.repo_root,
        trust_zone=request.trust_zone,
        files_considered=list(files_considered or []),
        files_proposed=[],
        mutated_files=False,
        network_used=False,
        shell_used=False,
        test_execution_used=False,
        git_mutation_used=False,
        package_install_used=False,
        external_model_used=False,
        approval_required=True,
        approval_reason=APPROVAL_REASON,
        refusal_reasons=list(refusal_reasons),
        warnings=list(warnings or [NO_MUTATION_WARNING]),
        errors=list(errors or []),
        trace_summary=_trace_summary(request, status=AiderWorkerStatus.BLOCKED),
    )


def _trace_summary(
    request: AiderWorkerRequest,
    *,
    status: AiderWorkerStatus,
    files_considered: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "trace_parent_id": request.trace_parent_id,
        "status": status.value,
        "worker_key": request.worker_key,
        "repo_key": request.repo_key,
        "dry_run_only": request.dry_run_only,
        "files_considered_count": len(files_considered or []),
        "aider_invoked": False,
        "mutation_used": False,
        "shell_used": False,
        "network_used": False,
    }


def _approved_repo_entries(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    repos = config.get("repos", {})
    if not isinstance(repos, dict):
        return {}

    return {
        str(key): value
        for key, value in repos.items()
        if isinstance(value, dict)
    }


def _validate_repo_key(
    *,
    request: AiderWorkerRequest,
    approved_repos_config_path: str | Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        approved_config = load_approved_repos_config(approved_repos_config_path)
    except Exception as exc:
        return None, [f"Approved repo config could not be loaded: {exc}"]

    repo_key = str(request.repo_key or "").strip()
    if not repo_key:
        return None, ["Repo key is required for Aider worker dry-run validation."]

    repos = _approved_repo_entries(approved_config)
    repo = repos.get(repo_key)
    if repo is None:
        return None, [f"Repo key is not approved for Aider worker use: {repo_key}"]

    if repo.get("allowed") is not True:
        return repo, [f"Repo key is configured but not allowed: {repo_key}"]

    return repo, []


def _validate_posture_config(config: AiderWorkerConfig) -> list[str]:
    reasons: list[str] = []

    for flag in sorted(REQUIRED_TRUE_POSTURE_FLAGS):
        if config.posture.get(flag) is not True:
            reasons.append(f"Aider worker config must keep {flag} true.")

    for flag in sorted(REQUIRED_FALSE_POSTURE_FLAGS):
        if config.posture.get(flag) is not False:
            reasons.append(f"Aider worker config must keep {flag} false.")

    if config.state != "skeleton":
        reasons.append("Aider worker config state must remain skeleton for Sprint 7B-7D.")

    return reasons


def _validate_request_flags(request: AiderWorkerRequest) -> list[str]:
    reasons: list[str] = []

    if request.worker_key != "aider_worker":
        reasons.append(f"Unexpected worker key for Aider worker skeleton: {request.worker_key}")

    if request.dry_run_only is not True:
        reasons.append("Aider worker requests must be dry_run_only in the skeleton.")

    for flag, reason in DANGEROUS_REQUEST_FLAGS.items():
        if getattr(request, flag) is True:
            reasons.append(reason)

    provider_policy = str(request.model_provider_policy or "").lower()
    if "cloud" in provider_policy or "external" in provider_policy:
        reasons.append("Model provider policy must not request cloud or external models.")

    return reasons


def _validate_truthful_language(request: AiderWorkerRequest) -> list[str]:
    text = " ".join(
        [
            str(request.user_goal or ""),
            str(request.privacy_notice or ""),
            str(request.mode or ""),
        ]
    ).lower()

    if any(phrase in text for phrase in FALSE_EXECUTION_CLAIMS):
        return [
            "Aider worker dry-run requests must not claim Aider, shell, tests, git, or file mutation already happened."
        ]

    return []


def run_aider_worker_dry_run(
    request: AiderWorkerRequest,
    *,
    config_path: str | Path = DEFAULT_AIDER_WORKER_CONFIG_PATH,
    approved_repos_config_path: str | Path = APPROVED_REPOS_CONFIG_PATH,
) -> AiderWorkerResult:
    """
    Validate a future Aider worker request without invoking Aider or mutating files.

    This skeleton is a boundary checkpoint only. It does not inspect file
    contents, run shell commands, call git, run tests, use network, or call
    external models.
    """
    try:
        config = load_aider_worker_config(config_path)
    except Exception as exc:
        return _blocked_result(
            request=request,
            refusal_reasons=[f"Aider worker config could not be loaded: {exc}"],
            errors=[str(exc)],
        )

    repo, repo_reasons = _validate_repo_key(
        request=request,
        approved_repos_config_path=approved_repos_config_path,
    )

    path_result = validate_selected_files(request.selected_files, config)

    refusal_reasons = (
        _validate_posture_config(config)
        + repo_reasons
        + path_result.refusal_reasons
        + _validate_request_flags(request)
        + _validate_truthful_language(request)
    )

    trust_zone = str(repo.get("trust_zone") or request.trust_zone) if repo else request.trust_zone
    repo_root = str(repo.get("root") or request.repo_root) if repo else request.repo_root

    if refusal_reasons:
        blocked_request = AiderWorkerRequest(
            request_id=request.request_id,
            worker_key=request.worker_key,
            repo_key=request.repo_key,
            repo_root=repo_root,
            trust_zone=trust_zone,
            user_goal=request.user_goal,
            mode=request.mode,
            selected_files=request.selected_files,
            dry_run_only=request.dry_run_only,
            network_allowed=request.network_allowed,
            shell_allowed=request.shell_allowed,
            test_execution_allowed=request.test_execution_allowed,
            mutation_allowed=request.mutation_allowed,
            git_mutation_allowed=request.git_mutation_allowed,
            package_install_allowed=request.package_install_allowed,
            credentials_allowed=request.credentials_allowed,
            vault_allowed=request.vault_allowed,
            home_access_allowed=request.home_access_allowed,
            cloud_model_allowed=request.cloud_model_allowed,
            approval_token=request.approval_token,
            model_provider_policy=request.model_provider_policy,
            privacy_notice=request.privacy_notice,
            trace_parent_id=request.trace_parent_id,
        )
        return _blocked_result(
            request=blocked_request,
            refusal_reasons=refusal_reasons,
            files_considered=path_result.accepted_paths,
        )

    return AiderWorkerResult(
        status=AiderWorkerStatus.DRY_RUN_READY,
        worker_key=request.worker_key,
        worker_used=False,
        aider_invoked=False,
        repo_key=request.repo_key,
        repo_root=repo_root,
        trust_zone=trust_zone,
        files_considered=list(path_result.accepted_paths),
        files_proposed=list(path_result.accepted_paths),
        diff_preview="",
        diff_preview_hash="",
        commands_requested=[],
        commands_run=[],
        tests_requested=[],
        tests_run=[],
        mutated_files=False,
        network_used=False,
        shell_used=False,
        test_execution_used=False,
        git_mutation_used=False,
        package_install_used=False,
        external_model_used=False,
        approval_required=True,
        approval_reason=APPROVAL_REASON,
        refusal_reasons=[],
        warnings=[
            DRY_RUN_WARNING,
            NO_MUTATION_WARNING,
            "Runtime and UI integration are deferred.",
        ],
        errors=[],
        trace_summary=_trace_summary(
            request,
            status=AiderWorkerStatus.DRY_RUN_READY,
            files_considered=path_result.accepted_paths,
        ),
    )
