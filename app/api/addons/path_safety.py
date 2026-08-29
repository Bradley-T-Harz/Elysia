"""Path and package-entry guards for local add-on packages."""

from __future__ import annotations

import posixpath
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipInfo

from app.api.project_paths import data_path


MAX_PACKAGE_BYTES = 25 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILE_COUNT = 500
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
BINARY_EXTENSIONS = {
    ".bin",
    ".dll",
    ".dylib",
    ".exe",
    ".msi",
    ".o",
    ".pyc",
    ".pyd",
    ".sh",
    ".so",
}
ARCHIVE_EXTENSIONS = {
    ".7z",
    ".appimage",
    ".deb",
    ".elysia-addon",
    ".gz",
    ".jar",
    ".rar",
    ".tar",
    ".tgz",
    ".vsix",
    ".whl",
    ".zip",
}
FORBIDDEN_HIDDEN_PARTS = {".aws", ".env", ".git", ".gnupg", ".ssh"}
FORBIDDEN_CREDENTIAL_NAMES = {
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
    "known_hosts",
    "netrc",
    "secrets.json",
}


def addons_root() -> Path:
    """Return the user-local add-on data root without creating it."""
    return data_path("addons")


def ensure_addons_tree() -> dict[str, Path]:
    root = addons_root()
    paths = {
        "root": root,
        "installed": root / "installed",
        "staged": root / "staged",
        "disabled": root / "disabled",
        "removed": root / "removed",
        "cache": root / "cache",
        "rollback": root / "rollback",
        "manifests": root / "manifests",
        "audit": root / "audit",
        "quarantine": root / "quarantine",
        "samples": root / "samples",
    }
    for path in paths.values():
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return paths


def is_zip_symlink(info: ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def is_zip_special_file(info: ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return bool(mode) and mode not in {stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}


def normalize_package_entry(name: str) -> str:
    cleaned = name.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return posixpath.normpath(cleaned)


def validate_package_entry(name: str) -> list[str]:
    errors: list[str] = []
    if not name or name.endswith("/"):
        return errors
    normalized = normalize_package_entry(name)
    path = PurePosixPath(normalized)
    if normalized.startswith("../") or "/../" in normalized or normalized == "..":
        errors.append(f"Path traversal is not allowed: {name}")
    if path.is_absolute() or name.startswith("/") or name.startswith("\\"):
        errors.append(f"Absolute paths are not allowed: {name}")
    if any(part in {"", ".", ".."} for part in path.parts):
        errors.append(f"Unsafe package path segment: {name}")
    lowered = [part.lower() for part in path.parts]
    if ".env" in lowered or any(part.startswith(".env.") for part in lowered):
        errors.append(f"Hidden environment files are not allowed: {name}")
    if any(part in FORBIDDEN_HIDDEN_PARTS for part in lowered):
        errors.append(f"Hidden credential/source-control directories are not allowed: {name}")
    if any(part.startswith(".") and part not in {".", ".."} for part in path.parts):
        errors.append(f"Hidden package entries require removal before packaging: {name}")
    if path.name.lower() in FORBIDDEN_CREDENTIAL_NAMES or path.suffix.lower() in {".key", ".pem", ".p12", ".pfx"}:
        errors.append(f"Credential-like package entries are not allowed: {name}")
    return errors


def is_binary_entry(name: str) -> bool:
    return PurePosixPath(normalize_package_entry(name)).suffix.lower() in BINARY_EXTENSIONS


def safe_install_leaf(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value).strip(".-")[:80] or "addon"


def ensure_within_directory(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_root != resolved_path and resolved_root not in resolved_path.parents:
        raise ValueError(f"Path escapes allowed add-on directory: {path}")


__all__ = (
    "ARCHIVE_EXTENSIONS",
    "BINARY_EXTENSIONS",
    "MAX_COMPRESSION_RATIO",
    "MAX_FILE_COUNT",
    "MAX_FILE_BYTES",
    "MAX_PACKAGE_BYTES",
    "MAX_UNCOMPRESSED_BYTES",
    "addons_root",
    "ensure_addons_tree",
    "ensure_within_directory",
    "is_binary_entry",
    "is_zip_special_file",
    "is_zip_symlink",
    "normalize_package_entry",
    "safe_install_leaf",
    "validate_package_entry",
)
