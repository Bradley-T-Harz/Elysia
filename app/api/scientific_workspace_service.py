"""Private project-bound authority for scientific workspace roots.

Scientific workspace approval is intentionally independent from Codev repository
approval. A grant authorizes only later governed scientific inspection/compute
inside one exact local folder for one authenticated owner and one owned project.

It does not grant shell, Git, package installation, network, publication,
arbitrary Python, source mutation, or broad filesystem authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
import tempfile
from typing import Any
from uuid import uuid4

from app.api.coding_data_type_registry import (
    DATA_DIRECTORY_EXTENSIONS,
    SUPPORTED_DATA_TYPES,
    UNKNOWN_DATA,
)
from app.api.project_service import (
    ProjectServiceError,
    get_project_metadata,
)
from app.api.schemas.scientific_workspace import (
    ScientificWorkspaceApplyRequest,
    ScientificWorkspaceApprovalPlan,
    ScientificWorkspaceApprovalResult,
    ScientificWorkspaceManifest,
    ScientificWorkspaceManifestEntry,
    ScientificWorkspaceManifestRequest,
    ScientificWorkspacePlanRequest,
    ScientificWorkspaceRevokeRequest,
    ScientificWorkspaceStatus,
    ScientificWorkspaceStatusRequest,
)
from app.install.paths import resolve_elysia_paths
from app.ownership import current_user_id


REGISTRY_VERSION = 1
PLAN_TTL_SECONDS = 300

_REGISTRY_LOCK = RLock()
_PLAN_LOCK = RLock()


class ScientificWorkspaceError(RuntimeError):
    """Scientific workspace authority failed closed."""


@dataclass
class _PlanRecord:
    plan: ScientificWorkspaceApprovalPlan
    root: Path
    owner_user_id: str
    project_id: str
    expires_at: datetime
    used: bool = False


_PLANS: dict[str, _PlanRecord] = {}


def _serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _REGISTRY_LOCK:
            return function(*args, **kwargs)

    return wrapped


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    )


def _iso(value: datetime) -> str:
    return value.isoformat().replace(
        "+00:00",
        "Z",
    )


def scientific_workspace_registry_path() -> Path:
    return (
        resolve_elysia_paths().config_dir
        / "scientific"
        / "approved-workspaces.json"
    )


def _empty_registry() -> dict[str, Any]:
    return {
        "version": REGISTRY_VERSION,
        "workspaces": {},
    }


def _root_hash(root: Path) -> str:
    return sha256(
        str(root).encode("utf-8")
    ).hexdigest()[:24]


def _authority_key(
    *,
    owner_user_id: str,
    project_id: str,
    root: Path,
) -> str:
    return sha256(
        (
            owner_user_id
            + "\n"
            + project_id
            + "\n"
            + str(root)
        ).encode("utf-8")
    ).hexdigest()[:32]


def _path_contains_symlink(path: Path) -> bool:
    absolute = Path(
        os.path.abspath(
            str(path)
        )
    )

    current = Path(absolute.anchor)

    for part in absolute.parts[1:]:
        current = current / part

        if current.is_symlink():
            return True

    return False


def _candidate_root(
    workspace_root: str,
) -> tuple[Path, str, str | None]:
    root = Path(
        os.path.abspath(
            str(
                Path(workspace_root).expanduser()
            )
        )
    )

    label = root.name or "scientific-workspace"

    if not root.exists() or not root.is_dir():
        return (
            root,
            label,
            "workspace_root_not_directory",
        )

    broad_roots = {
        Path(root.anchor),
        Path.home().resolve(),
        Path("/home"),
        Path("/tmp"),
    }

    if root in broad_roots:
        return (
            root,
            label,
            "workspace_root_too_broad",
        )

    if _path_contains_symlink(root):
        return (
            root,
            label,
            "workspace_root_symlink",
        )

    return root, label, None


def _require_owner_project(
    project_id: str,
) -> tuple[str, dict[str, Any]]:
    owner = str(
        current_user_id() or ""
    ).strip()

    if not owner:
        raise ScientificWorkspaceError(
            "scientific_workspace_authentication_required"
        )

    try:
        metadata = get_project_metadata(
            project_id
        )
    except ProjectServiceError as exc:
        raise ScientificWorkspaceError(
            "scientific_workspace_project_unavailable"
        ) from exc

    observed_owner = str(
        metadata.get("owner_user_id")
        or ""
    ).strip()

    if (
        not observed_owner
        or observed_owner != owner
    ):
        raise ScientificWorkspaceError(
            "scientific_workspace_project_owner_mismatch"
        )

    return owner, metadata


def load_scientific_workspace_registry(
    path: Path | None = None,
) -> dict[str, Any]:
    target = (
        path
        or scientific_workspace_registry_path()
    )

    try:
        payload = json.loads(
            target.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError:
        return _empty_registry()
    except (OSError, ValueError):
        return {
            **_empty_registry(),
            "invalid": True,
        }

    if (
        not isinstance(payload, dict)
        or payload.get("version")
        != REGISTRY_VERSION
        or not isinstance(
            payload.get("workspaces"),
            dict,
        )
    ):
        return {
            **_empty_registry(),
            "invalid": True,
        }

    return {
        "version": REGISTRY_VERSION,
        "workspaces": payload["workspaces"],
    }


def _save_registry(
    payload: dict[str, Any],
    path: Path | None = None,
) -> None:
    target = (
        path
        or scientific_workspace_registry_path()
    )

    target.parent.mkdir(
        mode=0o700,
        parents=True,
        exist_ok=True,
    )

    try:
        target.parent.chmod(0o700)
    except OSError:
        pass

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=".approved-scientific-workspaces-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(
            payload,
            handle,
            sort_keys=True,
            indent=2,
        )
        handle.write("\n")
        temporary = Path(handle.name)

    temporary.chmod(0o600)
    os.replace(
        temporary,
        target,
    )

    target.chmod(0o600)


def _matching_entry(
    *,
    owner_user_id: str,
    project_id: str,
    root: Path,
    registry: dict[str, Any],
) -> dict[str, Any] | None:
    key = _authority_key(
        owner_user_id=owner_user_id,
        project_id=project_id,
        root=root,
    )

    raw = registry["workspaces"].get(
        key
    )

    if not isinstance(raw, dict):
        return None

    if (
        raw.get("owner_user_id")
        != owner_user_id
        or raw.get("project_id")
        != project_id
        or raw.get("root")
        != str(root)
        or raw.get("root_hash")
        != _root_hash(root)
    ):
        return None

    return raw


def scientific_workspace_status(
    payload: ScientificWorkspaceStatusRequest,
) -> ScientificWorkspaceStatus:
    root, label, root_error = _candidate_root(
        payload.workspace_root
    )

    try:
        owner, _ = _require_owner_project(
            payload.project_id
        )
    except ScientificWorkspaceError as exc:
        return ScientificWorkspaceStatus(
            status="blocked",
            project_id=payload.project_id,
            workspace_label=label,
            workspace_root_hash=_root_hash(root),
            blocked_reason=str(exc),
            warnings=[
                "Scientific workspace authority failed closed."
            ],
        )

    registry = (
        load_scientific_workspace_registry()
    )

    if registry.get("invalid"):
        return ScientificWorkspaceStatus(
            status="blocked",
            project_id=payload.project_id,
            workspace_label=label,
            workspace_root_hash=_root_hash(root),
            blocked_reason=(
                "scientific_workspace_registry_requires_recovery"
            ),
        )

    entry = _matching_entry(
        owner_user_id=owner,
        project_id=payload.project_id,
        root=root,
        registry=registry,
    )

    revoked = bool(
        entry
        and entry.get("revoked") is True
    )

    approved = bool(
        entry
        and entry.get("approved") is True
        and not revoked
        and root_error is None
    )

    return ScientificWorkspaceStatus(
        status=(
            "approved"
            if approved
            else "blocked"
            if root_error or revoked
            else "approval_required"
        ),
        project_id=payload.project_id,
        workspace_label=label,
        workspace_root_hash=_root_hash(root),
        approved=approved,
        revoked=revoked,
        approval_source=(
            "XDG private scientific workspace registry"
            if approved
            else None
        ),
        blocked_reason=(
            root_error
            or (
                "scientific_workspace_revoked"
                if revoked
                else None
            )
        ),
        warnings=[
            (
                "Scientific workspace approval grants only "
                "separately governed local scientific "
                "inspection and computation."
            )
        ],
    )


def plan_scientific_workspace_approval(
    payload: ScientificWorkspacePlanRequest,
) -> ScientificWorkspaceApprovalPlan:
    root, label, error = _candidate_root(
        payload.workspace_root
    )

    try:
        owner, _ = _require_owner_project(
            payload.project_id
        )
    except ScientificWorkspaceError as exc:
        return ScientificWorkspaceApprovalPlan(
            status="blocked",
            project_id=payload.project_id,
            workspace_label=label,
            workspace_root_hash=_root_hash(root),
            blocked_reason=str(exc),
            warnings=[
                "No scientific workspace approval plan was issued."
            ],
        )

    if error:
        return ScientificWorkspaceApprovalPlan(
            status="blocked",
            project_id=payload.project_id,
            workspace_label=label,
            workspace_root_hash=_root_hash(root),
            blocked_reason=error,
            warnings=[
                "No scientific workspace approval plan was issued."
            ],
        )

    plan_id = (
        "scientific_workspace_plan_"
        + uuid4().hex[:16]
    )

    expires = (
        _now()
        + timedelta(
            seconds=PLAN_TTL_SECONDS
        )
    )

    root_hash = _root_hash(root)

    plan_hash = sha256(
        (
            "scientific_workspace_approval\n"
            + owner
            + "\n"
            + payload.project_id
            + "\n"
            + root_hash
            + "\n"
            + plan_id
        ).encode("utf-8")
    ).hexdigest()[:32]

    plan = ScientificWorkspaceApprovalPlan(
        status="approval_required",
        plan_id=plan_id,
        plan_hash=plan_hash,
        project_id=payload.project_id,
        workspace_label=label,
        workspace_root_hash=root_hash,
        expires_at_utc=_iso(expires),
        consequences=[
            (
                "Allow bounded inventory and separately governed "
                "scientific operations inside this exact folder "
                "for this project and account."
            ),
            (
                "Do not grant shell, arbitrary Python, Git mutation, "
                "package installation, network, publication, source "
                "mutation, or broad filesystem authority."
            ),
        ],
        warnings=[
            (
                "Review the project, exact workspace label, "
                "and root hash before approval."
            )
        ],
    )

    with _PLAN_LOCK:
        _PLANS[plan_id] = _PlanRecord(
            plan=plan,
            root=root,
            owner_user_id=owner,
            project_id=payload.project_id,
            expires_at=expires,
        )

    return plan


@_serialized
def _record_workspace_approval(
    *,
    owner_user_id: str,
    project_id: str,
    root: Path,
    label: str,
) -> None:
    registry = (
        load_scientific_workspace_registry()
    )

    if registry.get("invalid"):
        raise ScientificWorkspaceError(
            "scientific_workspace_registry_requires_recovery"
        )

    key = _authority_key(
        owner_user_id=owner_user_id,
        project_id=project_id,
        root=root,
    )

    now = _iso(_now())

    registry["workspaces"][key] = {
        "owner_user_id": owner_user_id,
        "project_id": project_id,
        "root": str(root),
        "root_hash": _root_hash(root),
        "label": label,
        "approved": True,
        "revoked": False,
        "approved_at_utc": now,
        "updated_at_utc": now,
    }

    _save_registry(registry)


def apply_scientific_workspace_approval(
    payload: ScientificWorkspaceApplyRequest,
) -> ScientificWorkspaceApprovalResult:
    try:
        owner, _ = _require_owner_project(
            payload.project_id
        )
    except ScientificWorkspaceError as exc:
        return ScientificWorkspaceApprovalResult(
            status="blocked",
            project_id=payload.project_id,
            workspace_label="scientific-workspace",
            workspace_root_hash="unknown",
            blocked_reason=str(exc),
        )

    with _PLAN_LOCK:
        record = _PLANS.get(
            payload.plan_id
        )

        if record is None:
            return ScientificWorkspaceApprovalResult(
                status="blocked",
                project_id=payload.project_id,
                workspace_label="scientific-workspace",
                workspace_root_hash="unknown",
                blocked_reason="unknown_plan",
            )

        if record.used:
            return ScientificWorkspaceApprovalResult(
                status="blocked",
                project_id=payload.project_id,
                workspace_label=record.plan.workspace_label,
                workspace_root_hash=record.plan.workspace_root_hash,
                blocked_reason="plan_already_used",
            )

        if (
            record.owner_user_id != owner
            or record.project_id
            != payload.project_id
        ):
            return ScientificWorkspaceApprovalResult(
                status="blocked",
                project_id=payload.project_id,
                workspace_label=record.plan.workspace_label,
                workspace_root_hash=record.plan.workspace_root_hash,
                blocked_reason="plan_authority_mismatch",
            )

        if _now() >= record.expires_at:
            return ScientificWorkspaceApprovalResult(
                status="blocked",
                project_id=payload.project_id,
                workspace_label=record.plan.workspace_label,
                workspace_root_hash=record.plan.workspace_root_hash,
                blocked_reason="plan_expired",
            )

        if (
            payload.plan_hash
            != record.plan.plan_hash
        ):
            return ScientificWorkspaceApprovalResult(
                status="blocked",
                project_id=payload.project_id,
                workspace_label=record.plan.workspace_label,
                workspace_root_hash=record.plan.workspace_root_hash,
                blocked_reason="plan_hash_mismatch",
            )

        if (
            not payload.operator_approved
            or payload.confirmation_phrase
            != "Approve exact scientific workspace"
        ):
            return ScientificWorkspaceApprovalResult(
                status="approval_required",
                project_id=payload.project_id,
                workspace_label=record.plan.workspace_label,
                workspace_root_hash=record.plan.workspace_root_hash,
                blocked_reason="explicit_confirmation_required",
            )

        root, label, error = _candidate_root(
            str(record.root)
        )

        if (
            error
            or _root_hash(root)
            != record.plan.workspace_root_hash
        ):
            return ScientificWorkspaceApprovalResult(
                status="blocked",
                project_id=payload.project_id,
                workspace_label=label,
                workspace_root_hash=_root_hash(root),
                blocked_reason=(
                    error
                    or "workspace_root_changed"
                ),
            )

        try:
            _record_workspace_approval(
                owner_user_id=owner,
                project_id=payload.project_id,
                root=root,
                label=label,
            )
        except ScientificWorkspaceError as exc:
            return ScientificWorkspaceApprovalResult(
                status="blocked",
                project_id=payload.project_id,
                workspace_label=label,
                workspace_root_hash=_root_hash(root),
                blocked_reason=str(exc),
            )

        record.used = True

    return ScientificWorkspaceApprovalResult(
        status="approved",
        project_id=payload.project_id,
        workspace_label=label,
        workspace_root_hash=_root_hash(root),
        approved=True,
        operation_id=(
            "scientific_workspace_approval_"
            + uuid4().hex[:16]
        ),
        warnings=[
            (
                "Approval is exact to this account, "
                "project, and folder root."
            ),
            (
                "Every scientific read, compute operation, "
                "artifact write, and outward action remains "
                "independently governed."
            ),
        ],
    )


@_serialized
def _record_workspace_revocation(
    *,
    owner_user_id: str,
    project_id: str,
    root: Path,
    label: str,
) -> bool:
    registry = (
        load_scientific_workspace_registry()
    )

    if registry.get("invalid"):
        raise ScientificWorkspaceError(
            "scientific_workspace_registry_requires_recovery"
        )

    key = _authority_key(
        owner_user_id=owner_user_id,
        project_id=project_id,
        root=root,
    )

    entry = registry["workspaces"].get(
        key
    )

    existed = isinstance(entry, dict)

    if not existed:
        entry = {
            "owner_user_id": owner_user_id,
            "project_id": project_id,
            "root": str(root),
            "root_hash": _root_hash(root),
            "label": label,
        }

        registry["workspaces"][key] = entry

    entry["approved"] = False
    entry["revoked"] = True
    entry["updated_at_utc"] = _iso(
        _now()
    )

    _save_registry(registry)

    return existed


def revoke_scientific_workspace(
    payload: ScientificWorkspaceRevokeRequest,
) -> ScientificWorkspaceApprovalResult:
    try:
        owner, _ = _require_owner_project(
            payload.project_id
        )
    except ScientificWorkspaceError as exc:
        root = Path(
            os.path.abspath(
                str(
                    Path(
                        payload.workspace_root
                    ).expanduser()
                )
            )
        )

        return ScientificWorkspaceApprovalResult(
            status="blocked",
            project_id=payload.project_id,
            workspace_label=(
                root.name
                or "scientific-workspace"
            ),
            workspace_root_hash=_root_hash(
                root
            ),
            blocked_reason=str(exc),
        )

    root = Path(
        os.path.abspath(
            str(
                Path(
                    payload.workspace_root
                ).expanduser()
            )
        )
    )

    label = (
        root.name
        or "scientific-workspace"
    )

    if (
        not payload.operator_approved
        or payload.confirmation_phrase
        != "Revoke scientific workspace approval"
    ):
        return ScientificWorkspaceApprovalResult(
            status="approval_required",
            project_id=payload.project_id,
            workspace_label=label,
            workspace_root_hash=_root_hash(root),
            blocked_reason=(
                "explicit_confirmation_required"
            ),
        )

    try:
        existed = _record_workspace_revocation(
            owner_user_id=owner,
            project_id=payload.project_id,
            root=root,
            label=label,
        )
    except ScientificWorkspaceError as exc:
        return ScientificWorkspaceApprovalResult(
            status="blocked",
            project_id=payload.project_id,
            workspace_label=label,
            workspace_root_hash=_root_hash(root),
            blocked_reason=str(exc),
        )

    return ScientificWorkspaceApprovalResult(
        status=(
            "revoked"
            if existed
            else "not_previously_approved_revocation_recorded"
        ),
        project_id=payload.project_id,
        workspace_label=label,
        workspace_root_hash=_root_hash(root),
        approved=False,
        revoked=True,
        operation_id=(
            "scientific_workspace_revoke_"
            + uuid4().hex[:16]
        ),
        warnings=[
            (
                "Scientific authority for this exact "
                "account/project/root tuple is revoked."
            )
        ],
    )


@dataclass(frozen=True)
class VerifiedScientificWorkspaceSource:
    """Internal-only verified source inside one approved scientific workspace."""

    project_id: str
    workspace_root_hash: str
    relative_path: str
    source_path: Path
    type_id: str
    category: str
    adapter: str
    size_bytes: int


def resolve_scientific_workspace_source(
    *,
    project_id: str,
    workspace_root: str,
    relative_path: str,
) -> VerifiedScientificWorkspaceSource:
    """Resolve one exact regular scientific file under current workspace authority.

    This is path authority only. It does not parse, hash, ingest, compute,
    mutate, publish, or expose the absolute source path to public contracts.
    """

    root, _label, root_hash, error = (
        _approved_manifest_root(
            project_id=project_id,
            workspace_root=workspace_root,
        )
    )

    if root is None:
        raise ScientificWorkspaceError(
            error
            or "scientific_workspace_unavailable"
        )

    requested = str(
        relative_path or ""
    ).strip()

    if (
        not requested
        or Path(requested).is_absolute()
    ):
        raise ScientificWorkspaceError(
            "scientific_workspace_relative_path_required"
        )

    lexical = Path(requested)

    if any(
        part in {"", ".", ".."}
        for part in lexical.parts
    ):
        raise ScientificWorkspaceError(
            "scientific_workspace_relative_path_invalid"
        )

    normalized_relative = (
        lexical.as_posix()
    )

    if not _inventory_path_allowed(
        normalized_relative
    ):
        raise ScientificWorkspaceError(
            "scientific_workspace_source_blocked"
        )

    candidate = Path(
        os.path.abspath(
            str(root / lexical)
        )
    )

    try:
        resolved_relative = (
            candidate
            .relative_to(root)
            .as_posix()
        )
    except ValueError as exc:
        raise ScientificWorkspaceError(
            "scientific_workspace_source_escape"
        ) from exc

    if (
        resolved_relative
        != normalized_relative
    ):
        raise ScientificWorkspaceError(
            "scientific_workspace_source_path_changed"
        )

    if _path_contains_symlink(
        candidate
    ):
        raise ScientificWorkspaceError(
            "scientific_workspace_source_symlink"
        )

    if (
        not candidate.exists()
        or not candidate.is_file()
    ):
        raise ScientificWorkspaceError(
            "scientific_workspace_regular_file_required"
        )

    try:
        info = candidate.stat()
    except OSError as exc:
        raise ScientificWorkspaceError(
            "scientific_workspace_source_stat_failed"
        ) from exc

    if info.st_nlink != 1:
        raise ScientificWorkspaceError(
            "scientific_workspace_source_hardlink"
        )

    descriptor = _inventory_descriptor(
        candidate
    )

    if descriptor.adapter == "blocked":
        raise ScientificWorkspaceError(
            "scientific_workspace_source_type_unsupported"
        )

    return VerifiedScientificWorkspaceSource(
        project_id=project_id,
        workspace_root_hash=root_hash,
        relative_path=normalized_relative,
        source_path=candidate,
        type_id=descriptor.type_id,
        category=descriptor.category,
        adapter=descriptor.adapter,
        size_bytes=max(
            0,
            int(info.st_size),
        ),
    )


_BLOCKED_INVENTORY_PARTS = {
    ".git",
    ".ssh",
    ".gnupg",
    ".elysia_backups",
    "vault",
}

_BLOCKED_INVENTORY_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
    "authorized_keys",
}

_MAX_DIRECTORY_STORE_NODES = 20_000


def _inventory_path_allowed(
    relative_path: str,
) -> bool:
    parts = [
        part.casefold()
        for part in Path(relative_path).parts
        if part not in {"", "."}
    ]

    if any(
        part in _BLOCKED_INVENTORY_PARTS
        for part in parts
    ):
        return False

    if (
        parts
        and parts[-1]
        in _BLOCKED_INVENTORY_NAMES
    ):
        return False

    return True


def _inventory_descriptor(
    path: Path,
):
    """Classify by registered scientific-data filename only.

    The manifest phase deliberately does not call the full data adapters and
    does not inspect source bytes.
    """

    suffix = path.suffix.casefold()

    for descriptor in SUPPORTED_DATA_TYPES:
        if suffix in descriptor.extensions:
            return descriptor

    return UNKNOWN_DATA


def _directory_store_metadata(
    root: Path,
) -> tuple[int, bool]:
    """Return bounded metadata-only size and boundary truth for a directory store."""

    total_size = 0
    visited = 0
    stack = [root]

    while stack:
        current = stack.pop()

        try:
            children = list(
                os.scandir(current)
            )
        except OSError:
            return total_size, False

        for child in children:
            visited += 1

            if visited > _MAX_DIRECTORY_STORE_NODES:
                return total_size, False

            try:
                if child.is_symlink():
                    return total_size, False

                if child.is_dir(
                    follow_symlinks=False
                ):
                    stack.append(
                        Path(child.path)
                    )
                    continue

                if not child.is_file(
                    follow_symlinks=False
                ):
                    return total_size, False

                info = child.stat(
                    follow_symlinks=False
                )

                if info.st_nlink != 1:
                    return total_size, False

                total_size += max(
                    0,
                    int(info.st_size),
                )

            except OSError:
                return total_size, False

    return total_size, True


def _approved_manifest_root(
    *,
    project_id: str,
    workspace_root: str,
) -> tuple[
    Path | None,
    str,
    str,
    str | None,
]:
    root, label, root_error = (
        _candidate_root(
            workspace_root
        )
    )

    root_hash = _root_hash(root)

    if root_error:
        return (
            None,
            label,
            root_hash,
            root_error,
        )

    try:
        owner, _ = _require_owner_project(
            project_id
        )
    except ScientificWorkspaceError as exc:
        return (
            None,
            label,
            root_hash,
            str(exc),
        )

    registry = (
        load_scientific_workspace_registry()
    )

    if registry.get("invalid"):
        return (
            None,
            label,
            root_hash,
            "scientific_workspace_registry_requires_recovery",
        )

    entry = _matching_entry(
        owner_user_id=owner,
        project_id=project_id,
        root=root,
        registry=registry,
    )

    if not entry:
        return (
            None,
            label,
            root_hash,
            "scientific_workspace_not_approved",
        )

    if entry.get("revoked") is True:
        return (
            None,
            label,
            root_hash,
            "scientific_workspace_revoked",
        )

    if entry.get("approved") is not True:
        return (
            None,
            label,
            root_hash,
            "scientific_workspace_not_approved",
        )

    return (
        root,
        label,
        root_hash,
        None,
    )


def build_scientific_workspace_manifest(
    payload: ScientificWorkspaceManifestRequest,
) -> ScientificWorkspaceManifest:
    """Inventory one approved scientific folder without parsing source content."""

    root, label, root_hash, error = (
        _approved_manifest_root(
            project_id=payload.project_id,
            workspace_root=payload.workspace_root,
        )
    )

    if root is None:
        return ScientificWorkspaceManifest(
            status="blocked",
            project_id=payload.project_id,
            workspace_label=label,
            workspace_root_hash=root_hash,
            warnings=[
                error
                or "scientific_workspace_unavailable"
            ],
        )

    entries: list[
        ScientificWorkspaceManifestEntry
    ] = []

    discovered_count = 0
    supported_count = 0
    unsupported_count = 0
    skipped_count = 0
    total_size_bytes = 0
    truncated = False

    stack = [root]

    while stack and not truncated:
        current = stack.pop()

        try:
            children = sorted(
                os.scandir(current),
                key=lambda item: (
                    item.name.casefold()
                ),
                reverse=True,
            )
        except OSError:
            skipped_count += 1
            continue

        for child in children:
            child_path = Path(
                child.path
            )

            try:
                relative = (
                    child_path
                    .relative_to(root)
                    .as_posix()
                )
            except ValueError:
                skipped_count += 1
                continue

            if not _inventory_path_allowed(
                relative
            ):
                skipped_count += 1
                continue

            try:
                if child.is_symlink():
                    skipped_count += 1
                    continue

                if child.is_dir(
                    follow_symlinks=False
                ):
                    if (
                        child_path.suffix.casefold()
                        in DATA_DIRECTORY_EXTENSIONS
                    ):
                        discovered_count += 1

                        size_bytes, safe = (
                            _directory_store_metadata(
                                child_path
                            )
                        )

                        if not safe:
                            skipped_count += 1
                            continue

                        descriptor = (
                            _inventory_descriptor(
                                child_path
                            )
                        )

                        supported = (
                            descriptor.adapter
                            != "blocked"
                        )

                        entries.append(
                            ScientificWorkspaceManifestEntry(
                                relative_path=relative,
                                entry_kind="directory_store",
                                size_bytes=size_bytes,
                                type_id=descriptor.type_id,
                                family=descriptor.category,
                                adapter=descriptor.adapter,
                                supported_scientific_data=supported,
                            )
                        )

                        total_size_bytes += (
                            size_bytes
                        )

                        if supported:
                            supported_count += 1
                        else:
                            unsupported_count += 1

                    else:
                        stack.append(
                            child_path
                        )

                    if (
                        len(entries)
                        >= payload.max_entries
                    ):
                        truncated = True
                        break

                    continue

                if not child.is_file(
                    follow_symlinks=False
                ):
                    skipped_count += 1
                    continue

                info = child.stat(
                    follow_symlinks=False
                )

                discovered_count += 1

                if info.st_nlink != 1:
                    skipped_count += 1
                    continue

                descriptor = (
                    _inventory_descriptor(
                        child_path
                    )
                )

                supported = (
                    descriptor.adapter
                    != "blocked"
                )

                size_bytes = max(
                    0,
                    int(info.st_size),
                )

                entries.append(
                    ScientificWorkspaceManifestEntry(
                        relative_path=relative,
                        entry_kind="regular_file",
                        size_bytes=size_bytes,
                        type_id=descriptor.type_id,
                        family=descriptor.category,
                        adapter=descriptor.adapter,
                        supported_scientific_data=supported,
                    )
                )

                total_size_bytes += (
                    size_bytes
                )

                if supported:
                    supported_count += 1
                else:
                    unsupported_count += 1

                if (
                    len(entries)
                    >= payload.max_entries
                ):
                    truncated = True
                    break

            except OSError:
                skipped_count += 1
                continue

    entries.sort(
        key=lambda item: (
            item.relative_path.casefold()
        )
    )

    return ScientificWorkspaceManifest(
        status="completed",
        project_id=payload.project_id,
        workspace_label=label,
        workspace_root_hash=root_hash,
        entries=entries,
        discovered_count=discovered_count,
        supported_count=supported_count,
        unsupported_count=unsupported_count,
        skipped_count=skipped_count,
        total_size_bytes=total_size_bytes,
        truncated=truncated,
        raw_paths_exposed=False,
        source_mutated=False,
        network_used=False,
        warnings=[
            (
                "Manifest inventory used directory metadata and registered "
                "filename/type contracts only; scientific source contents "
                "were not parsed by this phase."
            ),
            (
                "Symlinks, hardlinked regular files, blocked private paths, "
                "and unsafe directory stores are excluded."
            ),
        ],
    )


def clear_scientific_workspace_plans_for_tests() -> None:
    with _PLAN_LOCK:
        _PLANS.clear()


__all__ = (
    "ScientificWorkspaceError",
    "VerifiedScientificWorkspaceSource",
    "apply_scientific_workspace_approval",
    "build_scientific_workspace_manifest",
    "clear_scientific_workspace_plans_for_tests",
    "load_scientific_workspace_registry",
    "plan_scientific_workspace_approval",
    "resolve_scientific_workspace_source",
    "revoke_scientific_workspace",
    "scientific_workspace_registry_path",
    "scientific_workspace_status",
)
