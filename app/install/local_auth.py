"""Local-client credential contract for the loopback Elysia API.

Packaged mode requires a bearer credential for every mutating HTTP method.
Source mode remains explicitly development-compatible unless the operator sets
``ELYSIA_API_AUTH_MODE=required``.  Credential values are never included in
status payloads, receipts, exceptions, or logs.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import stat
import tempfile
from typing import Mapping

from .paths import ElysiaPaths, RuntimeMode, ensure_elysia_directories, resolve_elysia_paths


AUTH_MODE_ENV = "ELYSIA_API_AUTH_MODE"
CREDENTIAL_FILENAME = "local-api.credential"
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class LocalAuthError(RuntimeError):
    """Raised when the local credential contract cannot be initialized."""


@dataclass(frozen=True)
class LocalApiAuthPolicy:
    required: bool
    credential_path: Path
    runtime_mode: RuntimeMode
    source: str
    expected_credential: str | None = None

    def public_summary(self) -> dict[str, object]:
        return {
            "required_for_mutations": self.required,
            "initialized": self.expected_credential is not None or self.credential_path.is_file(),
            "storage": "XDG private runtime credential",
            "credential_exposed": False,
            "source": self.source,
        }


def _credential_path(paths: ElysiaPaths) -> Path:
    return paths.auth_dir / CREDENTIAL_FILENAME


def _read_credential(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value if len(value) >= 32 else None


def ensure_local_api_credential(paths: ElysiaPaths) -> str:
    """Return a private local credential, creating it atomically when absent."""
    ensure_elysia_directories(paths)
    paths.auth_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        paths.auth_dir.chmod(stat.S_IRWXU)
    except OSError:
        pass
    path = _credential_path(paths)
    current = _read_credential(path)
    if current is not None:
        return current

    value = secrets.token_urlsafe(48)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        current = _read_credential(path)
        if current is None:
            raise LocalAuthError("The local API credential exists but is invalid.")
        return current
    except OSError as exc:
        raise LocalAuthError("The local API credential could not be created.") from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return value


def rotate_local_api_credential(paths: ElysiaPaths) -> str:
    """Replace the local credential atomically, invalidating the prior value."""
    ensure_elysia_directories(paths)
    paths.auth_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=paths.auth_dir,
            prefix=".credential-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(value + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.chmod(0o600)
        temporary.replace(_credential_path(paths))
    except OSError as exc:
        raise LocalAuthError("The local API credential could not be rotated.") from exc
    return value


def build_local_api_auth_policy(
    *,
    paths: ElysiaPaths | None = None,
    environ: Mapping[str, str] | None = None,
    initialize: bool | None = None,
) -> LocalApiAuthPolicy:
    values = os.environ if environ is None else environ
    resolved_paths = paths or resolve_elysia_paths(values)
    configured = str(values.get(AUTH_MODE_ENV, "")).strip().lower()
    if configured not in {"", "required", "development-disabled"}:
        raise LocalAuthError(
            "ELYSIA_API_AUTH_MODE must be required or development-disabled."
        )
    if configured == "required":
        required = True
        source = "explicit_required"
    elif configured == "development-disabled":
        if resolved_paths.mode == RuntimeMode.PACKAGED:
            raise LocalAuthError("Packaged mode cannot disable local API authentication.")
        required = False
        source = "explicit_source_development"
    else:
        required = resolved_paths.mode == RuntimeMode.PACKAGED
        source = "packaged_default" if required else "source_development_default"

    should_initialize = required if initialize is None else initialize
    credential = ensure_local_api_credential(resolved_paths) if should_initialize else None
    return LocalApiAuthPolicy(
        required=required,
        credential_path=_credential_path(resolved_paths),
        runtime_mode=resolved_paths.mode,
        source=source,
        expected_credential=credential,
    )


def supplied_bearer_credential(headers: Mapping[str, str]) -> str | None:
    value = str(headers.get("authorization", "")).strip()
    scheme, separator, credential = value.partition(" ")
    if not separator or scheme.lower() != "bearer" or not credential.strip():
        return None
    return credential.strip()


def validate_local_api_credential(
    policy: LocalApiAuthPolicy,
    headers: Mapping[str, str],
) -> bool:
    if not policy.required:
        return True
    supplied = supplied_bearer_credential(headers)
    expected = policy.expected_credential or _read_credential(policy.credential_path)
    if supplied is None or expected is None:
        return False
    return secrets.compare_digest(supplied, expected)


__all__ = (
    "AUTH_MODE_ENV",
    "CREDENTIAL_FILENAME",
    "LocalApiAuthPolicy",
    "LocalAuthError",
    "MUTATING_METHODS",
    "build_local_api_auth_policy",
    "ensure_local_api_credential",
    "rotate_local_api_credential",
    "supplied_bearer_credential",
    "validate_local_api_credential",
)
