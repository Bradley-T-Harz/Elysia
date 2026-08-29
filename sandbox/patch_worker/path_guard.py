"""Path guard for the governed patch worker."""

from __future__ import annotations

from pathlib import Path


BLOCKED_PARTS = {
    ".git",
    "vault",
    "secrets",
    "credentials",
    "node_modules",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
}

BLOCKED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "known_hosts",
    "authorized_keys",
}

BLOCKED_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".der",
    ".sqlite",
    ".db",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
}


def normalize_patch_path(repo_root: str | Path, file_path: str) -> tuple[Path | None, str | None]:
    """Return a safe absolute path for a repo-relative patch target."""
    raw = str(file_path or "").strip()
    if not raw:
        return None, "Patch file path is required."
    if raw.startswith("~"):
        return None, "Patch file path must not target a home directory shortcut."

    candidate = Path(raw)
    if candidate.is_absolute():
        return None, "Patch file path must be relative to the approved repo."

    normalized_parts = candidate.parts
    if any(part in {"", "."} for part in normalized_parts):
        candidate = Path(*[part for part in normalized_parts if part not in {"", "."}])

    if any(part == ".." for part in candidate.parts):
        return None, "Patch file path must not traverse outside the approved repo."

    lowered_parts = {part.lower() for part in candidate.parts}
    if lowered_parts & BLOCKED_PARTS:
        return None, "Patch file path targets a sealed, generated, dependency, or private area."
    if candidate.name.lower() in BLOCKED_NAMES:
        return None, "Patch file path targets a secret-looking file name."
    if candidate.suffix.lower() in BLOCKED_SUFFIXES:
        return None, "Patch file path targets an unsupported binary or secret-like suffix."

    root = Path(repo_root).expanduser().resolve(strict=False)
    target = (root / candidate).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        return None, "Patch file path escaped the approved repo root."

    if target.exists() and target.is_symlink():
        return None, "Patch worker refuses symlink targets."

    return target, None


__all__ = ("normalize_patch_path",)
