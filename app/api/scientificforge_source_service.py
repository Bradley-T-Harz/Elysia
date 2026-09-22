"""Verified local input authority for ScientificForge.

ScientificForge never trusts a caller-supplied filesystem path for attached
data. It resolves Elysia's private ingest copy from a stable file id and
re-verifies that copy immediately before scientific execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
from typing import Callable

from app.api.file_ingest_service import (
    DEFAULT_INGEST_ROOT,
    get_file_status,
)

from app.api.conversation_service import (
    ConversationServiceError,
    get_conversation_metadata,
)
from app.api.project_service import (
    ProjectServiceError,
    get_project_metadata,
)
from app.ownership import current_user_id


SCIENTIFIC_SOURCE_CONTRACT_VERSION = "scientific-source-v0.1"

MAX_SCIENTIFIC_SOURCE_BYTES = 25 * 1024 * 1024

_ALLOWED_FILE_KINDS = {
    "csv",
    "xlsx",
}

_FILE_ID = re.compile(
    r"^file_[0-9a-f]{16}$"
)

_SHA256 = re.compile(
    r"^[0-9a-f]{64}$"
)


class ScientificSourceError(RuntimeError):
    """A ScientificForge source failed its authority boundary."""


@dataclass(frozen=True)
class VerifiedScientificSource:
    """Internal-only verified local source reference."""

    file_id: str
    display_name: str
    file_kind: str
    source_path: Path
    sha256: str
    size_bytes: int


def _hash_file(
    path: Path,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> str:
    digest = sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            if cancel_check is not None and cancel_check():
                raise ScientificSourceError(
                    "source_verification_cancelled"
                )

            digest.update(block)

    if cancel_check is not None and cancel_check():
        raise ScientificSourceError(
            "source_verification_cancelled"
        )

    return digest.hexdigest()


def _contains_symlink(path: Path) -> bool:
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


def resolve_attached_scientific_source(
    file_id: str,
    *,
    ingest_root: str | Path | None = None,
    max_source_bytes: int = MAX_SCIENTIFIC_SOURCE_BYTES,
    cancel_check: Callable[[], bool] | None = None,
) -> VerifiedScientificSource:
    """Resolve and cryptographically verify one private ingest copy."""

    normalized_id = str(file_id or "").strip()

    if cancel_check is not None and cancel_check():
        raise ScientificSourceError(
            "source_verification_cancelled"
        )

    if not _FILE_ID.fullmatch(normalized_id):
        raise ScientificSourceError(
            "invalid_source_file_id"
        )

    root = (
        Path(ingest_root)
        if ingest_root is not None
        else DEFAULT_INGEST_ROOT
    ).expanduser()

    if _contains_symlink(root):
        raise ScientificSourceError(
            "ingest_root_symlink_not_allowed"
        )

    status = get_file_status(
        normalized_id,
        ingest_root=root,
    )

    if status is None:
        raise ScientificSourceError(
            "source_ingest_record_not_found"
        )

    if (
        not status.accepted
        or status.blocked
        or not status.ready
        or status.file is None
    ):
        raise ScientificSourceError(
            "source_not_ready_for_scientific_execution"
        )

    attached = status.file

    file_kind = str(
        getattr(
            attached.file_kind,
            "value",
            attached.file_kind,
        )
        or ""
    ).strip().lower()

    if file_kind not in _ALLOWED_FILE_KINDS:
        raise ScientificSourceError(
            "source_file_kind_not_supported_by_scientificforge_v0"
        )

    display_name = str(
        attached.display_name
        or ""
    ).strip()

    if (
        not display_name
        or Path(display_name).name != display_name
        or display_name in {".", ".."}
    ):
        raise ScientificSourceError(
            "unsafe_source_display_name"
        )

    expected_sha256 = str(
        attached.sha256
        or ""
    ).strip().lower()

    if not _SHA256.fullmatch(expected_sha256):
        raise ScientificSourceError(
            "source_ingest_digest_missing_or_invalid"
        )

    if normalized_id != f"file_{expected_sha256[:16]}":
        raise ScientificSourceError(
            "source_file_id_digest_mismatch"
        )

    raw_directory = root / "raw" / normalized_id
    source = raw_directory / display_name

    if (
        _contains_symlink(raw_directory)
        or _contains_symlink(source)
    ):
        raise ScientificSourceError(
            "source_symlink_not_allowed"
        )

    resolved_directory = raw_directory.resolve(
        strict=False
    )
    resolved_source = source.resolve(
        strict=False
    )

    try:
        resolved_source.relative_to(
            resolved_directory
        )
    except ValueError as exc:
        raise ScientificSourceError(
            "source_escaped_ingest_directory"
        ) from exc

    try:
        info = resolved_source.stat()
    except OSError as exc:
        raise ScientificSourceError(
            "source_private_copy_unavailable"
        ) from exc

    if not stat.S_ISREG(info.st_mode):
        raise ScientificSourceError(
            "source_regular_file_required"
        )

    if info.st_nlink != 1:
        raise ScientificSourceError(
            "source_hardlink_not_allowed"
        )

    actual_size = int(info.st_size)

    if (
        actual_size < 0
        or actual_size > max(
            1,
            int(max_source_bytes),
        )
    ):
        raise ScientificSourceError(
            "source_size_limit_exceeded"
        )

    recorded_size = getattr(
        attached,
        "size_bytes",
        None,
    )

    if (
        recorded_size is not None
        and int(recorded_size) != actual_size
    ):
        raise ScientificSourceError(
            "source_size_changed_after_ingest"
        )

    actual_sha256 = _hash_file(
        resolved_source,
        cancel_check=cancel_check,
    )

    if actual_sha256 != expected_sha256:
        raise ScientificSourceError(
            "source_digest_changed_after_ingest"
        )

    return VerifiedScientificSource(
        file_id=normalized_id,
        display_name=display_name,
        file_kind=file_kind,
        source_path=resolved_source,
        sha256=actual_sha256,
        size_bytes=actual_size,
    )


def _scope_identifier(
    value: object,
) -> str | None:
    """Normalize one optional ownership-bearing local scope id."""

    compact = str(
        value or ""
    ).strip()

    return compact or None


def _require_scope_owner(
    *,
    observed_owner: object,
    active_owner: str,
) -> None:
    """Require explicit ownership equality even after owner-scoped lookup."""

    compact = str(
        observed_owner or ""
    ).strip()

    if (
        not compact
        or compact != active_owner
    ):
        raise ScientificSourceError(
            "source_owner_context_mismatch"
        )


def resolve_owned_attached_scientific_source(
    file_id: str,
    *,
    ingest_root: str | Path | None = None,
    max_source_bytes: int = MAX_SCIENTIFIC_SOURCE_BYTES,
    cancel_check: Callable[[], bool] | None = None,
) -> VerifiedScientificSource:
    """Resolve a scientific attachment only through authenticated local scope.

    ``file_id`` is content-derived and installation-wide, so possession of the
    identifier is never authority. ScientificForge requires at least one
    ownership-bearing project/conversation context and validates every supplied
    context against the authenticated local account before reading or hashing
    the private ingest bytes.
    """

    active_owner = str(
        current_user_id() or ""
    ).strip()

    if not active_owner:
        raise ScientificSourceError(
            "source_owner_authentication_required"
        )

    if (
        cancel_check is not None
        and cancel_check()
    ):
        raise ScientificSourceError(
            "source_verification_cancelled"
        )

    normalized_id = str(
        file_id or ""
    ).strip()

    if not _FILE_ID.fullmatch(
        normalized_id
    ):
        raise ScientificSourceError(
            "invalid_source_file_id"
        )

    root = (
        Path(ingest_root)
        if ingest_root is not None
        else DEFAULT_INGEST_ROOT
    ).expanduser()

    status = get_file_status(
        normalized_id,
        ingest_root=root,
    )

    if status is None:
        raise ScientificSourceError(
            "source_ingest_record_not_found"
        )

    if status.file is None:
        raise ScientificSourceError(
            "source_not_ready_for_scientific_execution"
        )

    attached = status.file

    project_id = _scope_identifier(
        attached.source_project_id
    )

    conversation_id = _scope_identifier(
        attached.source_conversation_id
    )

    if (
        project_id is None
        and conversation_id is None
    ):
        raise ScientificSourceError(
            "source_owner_context_required"
        )

    if project_id is not None:
        try:
            project = get_project_metadata(
                project_id
            )
        except ProjectServiceError as exc:
            raise ScientificSourceError(
                "source_project_context_unavailable"
            ) from exc

        _require_scope_owner(
            observed_owner=project.get(
                "owner_user_id"
            ),
            active_owner=active_owner,
        )

    conversation_project_id: str | None = None

    if conversation_id is not None:
        try:
            conversation = (
                get_conversation_metadata(
                    conversation_id
                )
            )
        except ConversationServiceError as exc:
            raise ScientificSourceError(
                "source_conversation_context_unavailable"
            ) from exc

        _require_scope_owner(
            observed_owner=getattr(
                conversation,
                "owner_user_id",
                None,
            ),
            active_owner=active_owner,
        )

        conversation_project_id = (
            _scope_identifier(
                getattr(
                    conversation,
                    "project_id",
                    None,
                )
            )
        )

    if (
        project_id is not None
        and conversation_project_id is not None
        and project_id != conversation_project_id
    ):
        raise ScientificSourceError(
            "source_scope_relationship_mismatch"
        )

    # If only the conversation carried a project relationship, validate that
    # linked project as well. This closes stale/mismatched ownership chains.
    if (
        project_id is None
        and conversation_project_id is not None
    ):
        try:
            linked_project = (
                get_project_metadata(
                    conversation_project_id
                )
            )
        except ProjectServiceError as exc:
            raise ScientificSourceError(
                "source_project_context_unavailable"
            ) from exc

        _require_scope_owner(
            observed_owner=linked_project.get(
                "owner_user_id"
            ),
            active_owner=active_owner,
        )

    if (
        cancel_check is not None
        and cancel_check()
    ):
        raise ScientificSourceError(
            "source_verification_cancelled"
        )

    return resolve_attached_scientific_source(
        normalized_id,
        ingest_root=root,
        max_source_bytes=max_source_bytes,
        cancel_check=cancel_check,
    )


__all__ = (
    "MAX_SCIENTIFIC_SOURCE_BYTES",
    "SCIENTIFIC_SOURCE_CONTRACT_VERSION",
    "ScientificSourceError",
    "VerifiedScientificSource",
    "resolve_attached_scientific_source",
    "resolve_owned_attached_scientific_source",
)
