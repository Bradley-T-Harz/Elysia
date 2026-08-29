"""
Local file path guard for user-selected file ingestion.

This module does not grant filesystem authority. It only rejects obviously
sensitive or unsafe selected paths before parser work begins.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


SENSITIVE_PATH_FRAGMENTS = (
    "vault/",
    "/vault",
    ".env",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    "known_hosts",
    "authorized_keys",
    "private key",
    "secret",
    "secrets",
    "token",
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "password",
    "passwd",
    "shadow",
    "keychain",
    ".gnupg/",
    ".aws/",
    ".azure/",
    ".gcp/",
    ".kube/",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
)

SENSITIVE_HOME_DOTFILES = {
    ".bash_history",
    ".zsh_history",
    ".profile",
    ".bashrc",
    ".zshrc",
    ".gitconfig",
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".gcp",
    ".kube",
}


@dataclass(frozen=True)
class FilePathGuardResult:
    allowed: bool
    reason: str
    risk_category: str
    safe_display_name: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "risk_category": self.risk_category,
            "safe_display_name": self.safe_display_name,
        }


def _safe_display_name(path: Path) -> str:
    return path.name or "selected-file"


def guard_selected_file_path(
    source_path: str | Path,
    *,
    max_size_bytes: int | None = None,
) -> FilePathGuardResult:
    raw_text = str(source_path or "").strip()
    path = Path(raw_text).expanduser()
    safe_name = _safe_display_name(path)
    lowered = raw_text.replace("\\", "/").lower()
    lowered_name = safe_name.lower()

    for fragment in SENSITIVE_PATH_FRAGMENTS:
        if fragment.lower() in lowered:
            return FilePathGuardResult(
                allowed=False,
                reason="Selected path looks like a sensitive secret, vault, credential, or private runtime path.",
                risk_category="sensitive_path",
                safe_display_name=safe_name,
            )

    if lowered_name in SENSITIVE_HOME_DOTFILES:
        return FilePathGuardResult(
            allowed=False,
            reason="Selected file is a sensitive home dotfile.",
            risk_category="home_dotfile",
            safe_display_name=safe_name,
        )

    if path.exists():
        if path.is_symlink():
            return FilePathGuardResult(
                allowed=False,
                reason="Selected path is a symlink; symlink file ingest is blocked for now.",
                risk_category="symlink",
                safe_display_name=safe_name,
            )

        if path.is_dir():
            return FilePathGuardResult(
                allowed=False,
                reason="Selected path is a directory; directory ingest is blocked.",
                risk_category="directory",
                safe_display_name=safe_name,
            )

        if max_size_bytes is not None:
            try:
                size = path.stat().st_size
            except OSError:
                size = None
            if size is not None and size > max_size_bytes:
                return FilePathGuardResult(
                    allowed=False,
                    reason=(
                        f"Selected file exceeds the configured size limit of "
                        f"{max_size_bytes} bytes."
                    ),
                    risk_category="size_limit",
                    safe_display_name=safe_name,
                )

    return FilePathGuardResult(
        allowed=True,
        reason="Selected path passed the local file-ingest path guard.",
        risk_category="none",
        safe_display_name=safe_name,
    )


__all__ = ("FilePathGuardResult", "guard_selected_file_path")
