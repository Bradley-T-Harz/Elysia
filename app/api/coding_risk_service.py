"""Shared non-mutating risk labels for coding bridge plans."""

from __future__ import annotations

from app.api.coding_file_type_registry import detect_file_type


def summarize_file_risk(relative_path: str) -> list[str]:
    descriptor = detect_file_type(relative_path)
    risks: list[str] = []
    if descriptor.category in {"code", "style", "database_script", "shell_script"}:
        risks.append("source_code_change")
    if descriptor.category in {"config", "structured_data", "project_metadata", "lockfile"}:
        risks.append("configuration_change")
    if descriptor.lockfile:
        risks.append("lockfile_change")
    if descriptor.secret_sensitive:
        risks.append("secret_sensitive_change")
    if descriptor.executable_sensitive:
        risks.append("executable_sensitive_change")
    lowered = relative_path.lower()
    if "tests/" in lowered or lowered.startswith("test_"):
        risks.append("test_change")
    return risks or ["ordinary_file_change"]


def command_risk_labels(command: list[str]) -> list[str]:
    joined = " ".join(command).lower()
    labels: list[str] = []
    if any(term in joined for term in ["install", "uninstall", "remove", "delete", "clean"]):
        labels.append("mutation_or_package_risk")
    if any(term in joined for term in ["git push", "git reset", "git clean"]):
        labels.append("git_mutation_risk")
    if not labels:
        labels.append("read_or_check_intent")
    return labels


__all__ = ("command_risk_labels", "summarize_file_risk")
