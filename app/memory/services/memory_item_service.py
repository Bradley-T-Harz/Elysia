from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.memory.schemas.memory_item import (
    MemoryActorKind,
    MemoryClass,
    MemoryItem,
    MemoryStatus,
)

LOGGER = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryItemNotFoundError(FileNotFoundError):
    """Raised when a memory item cannot be found."""


class MemoryItemAlreadyExistsError(FileExistsError):
    """Raised when attempting to create a memory item that already exists."""


class MemoryItemRevisionMismatchError(RuntimeError):
    """Raised when an expected revision does not match the stored revision."""


class LegacyMemoryWriterDisabledError(RuntimeError):
    """Legacy JSON memory is migration input, never a live fallback writer."""


class MemoryItemService:
    """Filesystem-backed item service for classed memory records.

    This service is intentionally boring in the best way:
    - class-aware storage layout
    - one JSON file per memory item
    - atomic writes
    - revision-safe replacement checks
    - archive/supersede helpers
    - no policy, classification, salience, or retrieval intelligence
    """

    CLASS_DIRECTORY_MAP: dict[MemoryClass, str] = {
        MemoryClass.working: "working",
        MemoryClass.conversation: "conversations",
        MemoryClass.project: "projects",
        MemoryClass.research: "research",
        MemoryClass.operational: "operational",
        MemoryClass.preference: "preferences",
        MemoryClass.sealed_private: "sealed_private",
        MemoryClass.audit: "audit",
    }

    def __init__(
        self,
        store_root: Optional[Path] = None,
        *,
        allow_legacy_writes: bool = False,
    ) -> None:
        memory_root = Path(__file__).resolve().parents[1]
        self._store_root = (store_root or (memory_root / "stores")).resolve()
        self._allow_legacy_writes = allow_legacy_writes
        self._memory_id_cache: dict[str, Path] = {}
        if self._allow_legacy_writes:
            self.ensure_store_layout()

    @property
    def store_root(self) -> Path:
        return self._store_root

    def ensure_store_layout(self) -> None:
        """Ensure the classed store layout exists on disk."""
        self._assert_legacy_write_allowed()
        self._store_root.mkdir(parents=True, exist_ok=True)
        for directory_name in self.CLASS_DIRECTORY_MAP.values():
            (self._store_root / directory_name).mkdir(parents=True, exist_ok=True)

    def get_store_dir(self, memory_class: MemoryClass) -> Path:
        """Return the directory for a given memory class."""
        try:
            directory_name = self.CLASS_DIRECTORY_MAP[memory_class]
        except KeyError as exc:
            raise ValueError(f"Unsupported memory class: {memory_class!r}") from exc

        directory = self._store_root / directory_name
        if self._allow_legacy_writes:
            directory.mkdir(parents=True, exist_ok=True)
        return directory

    def get_item_path(self, item: MemoryItem) -> Path:
        """Return the canonical file path for a memory item."""
        return self._build_item_path(item.memory_id, item.memory_class)

    def create_item(self, item: MemoryItem) -> Path:
        """Persist a new memory item.

        Raises:
            MemoryItemAlreadyExistsError: if the memory_id already exists.
        """
        self._assert_legacy_write_allowed()
        existing_path = self.find_item_path(item.memory_id, required=False)
        if existing_path is not None:
            raise MemoryItemAlreadyExistsError(
                f"Memory item already exists: {item.memory_id}"
            )

        item_path = self.get_item_path(item)
        self._atomic_write_json(item_path, self._serialize_item(item))
        self._memory_id_cache[item.memory_id] = item_path
        return item_path

    def get_item(self, memory_id: str) -> MemoryItem:
        """Load one memory item by id."""
        item_path = self.find_item_path(memory_id, required=True)
        return self._load_item_from_path(item_path)

    def list_items(
        self,
        *,
        memory_class: Optional[MemoryClass] = None,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        include_statuses: Optional[set[MemoryStatus]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[MemoryItem]:
        """List memory items with simple storage-level filtering.

        This is intentionally not the full retrieval engine. It provides
        class/scope/status-aware item access that later retrieval services
        can build on.
        """
        if offset < 0:
            raise ValueError("offset cannot be negative.")
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive when provided.")

        items: list[MemoryItem] = []

        for item_path in self._iter_item_paths(memory_class=memory_class):
            try:
                item = self._load_item_from_path(item_path)
            except Exception as exc:  # pragma: no cover - defensive filesystem guard
                LOGGER.warning("Skipping unreadable memory item %s: %s", item_path, exc)
                continue

            if project_id and item.context_links.project_id != project_id:
                continue

            if conversation_id and item.context_links.conversation_id != conversation_id:
                continue

            if include_statuses is not None and item.status not in include_statuses:
                continue

            items.append(item)

        items.sort(
            key=lambda value: (
                value.updated_at_utc,
                value.created_at_utc,
                value.memory_id,
            ),
            reverse=True,
        )

        if offset:
            items = items[offset:]

        if limit is not None:
            items = items[:limit]

        return items

    def replace_item(
        self,
        item: MemoryItem,
        *,
        expected_revision: Optional[int] = None,
    ) -> Path:
        """Replace an existing memory item safely.

        If the item moved classes, the old file is removed after the new file
        is successfully written.
        """
        self._assert_legacy_write_allowed()
        current_path = self.find_item_path(item.memory_id, required=True)
        current_item = self._load_item_from_path(current_path)

        self._validate_expected_revision(
            current_item=current_item,
            expected_revision=expected_revision,
        )

        updated_item = item.model_copy(deep=True)
        updated_item.updated_at_utc = utc_now()
        updated_item.updated_by = item.updated_by

        if updated_item.revision_info.revision <= current_item.revision_info.revision:
            updated_item.revision_info.revision = current_item.revision_info.revision + 1

        new_path = self.get_item_path(updated_item)
        self._atomic_write_json(new_path, self._serialize_item(updated_item))

        if new_path != current_path and current_path.exists():
            current_path.unlink()

        self._memory_id_cache[updated_item.memory_id] = new_path
        return new_path

    def archive_item(
        self,
        memory_id: str,
        *,
        reason: Optional[str] = None,
        updated_by: MemoryActorKind = MemoryActorKind.system,
        expected_revision: Optional[int] = None,
    ) -> MemoryItem:
        """Archive an item by changing its lifecycle state."""
        self._assert_legacy_write_allowed()
        item = self.get_item(memory_id)
        self._validate_expected_revision(
            current_item=item,
            expected_revision=expected_revision,
        )

        archived_item = item.model_copy(deep=True)
        archived_item.status = MemoryStatus.archived
        archived_item.updated_at_utc = utc_now()
        archived_item.updated_by = updated_by
        archived_item.revision_info.revision += 1
        archived_item.revision_info.last_mutation_reason = (
            reason or "Archived by memory item service."
        )

        self.replace_item(archived_item, expected_revision=item.revision_info.revision)
        return self.get_item(memory_id)

    def supersede_item(
        self,
        memory_id: str,
        *,
        successor_memory_id: str,
        reason: str,
        updated_by: MemoryActorKind = MemoryActorKind.system,
        expected_revision: Optional[int] = None,
    ) -> MemoryItem:
        """Mark an item as superseded and link it to a successor memory id."""
        self._assert_legacy_write_allowed()
        if not successor_memory_id.strip():
            raise ValueError("successor_memory_id cannot be empty.")
        if not reason.strip():
            raise ValueError("reason cannot be empty for supersede_item.")

        item = self.get_item(memory_id)
        self._validate_expected_revision(
            current_item=item,
            expected_revision=expected_revision,
        )

        superseded_item = item.model_copy(deep=True)
        superseded_item.status = MemoryStatus.superseded
        superseded_item.updated_at_utc = utc_now()
        superseded_item.updated_by = updated_by
        superseded_item.revision_info.revision += 1
        superseded_item.revision_info.superseded_by_memory_id = successor_memory_id.strip()
        superseded_item.revision_info.last_mutation_reason = reason.strip()

        self.replace_item(
            superseded_item,
            expected_revision=item.revision_info.revision,
        )
        return self.get_item(memory_id)

    def find_item_path(
        self,
        memory_id: str,
        *,
        required: bool = True,
    ) -> Optional[Path]:
        """Find the stored path for a memory item id."""
        safe_memory_id = self._normalize_memory_id(memory_id)

        cached = self._memory_id_cache.get(safe_memory_id)
        if cached and cached.exists():
            return cached

        for item_path in self._iter_item_paths():
            if item_path.stem == safe_memory_id:
                self._memory_id_cache[safe_memory_id] = item_path
                return item_path

        if required:
            raise MemoryItemNotFoundError(f"Memory item not found: {safe_memory_id}")

        return None

    def validate_store_item(self, memory_id: str) -> MemoryItem:
        """Load and validate one stored item by id."""
        return self.get_item(memory_id)

    def rebuild_index(self) -> dict[str, Path]:
        """Rebuild the in-memory id-to-path cache from disk."""
        rebuilt: dict[str, Path] = {}
        for item_path in self._iter_item_paths():
            rebuilt[item_path.stem] = item_path
        self._memory_id_cache = rebuilt
        return dict(self._memory_id_cache)

    def _build_item_path(self, memory_id: str, memory_class: MemoryClass) -> Path:
        safe_memory_id = self._normalize_memory_id(memory_id)
        return self.get_store_dir(memory_class) / f"{safe_memory_id}.json"

    def _normalize_memory_id(self, memory_id: str) -> str:
        value = memory_id.strip()
        if not value:
            raise ValueError("memory_id cannot be empty.")

        if any(char in value for char in ("/", "\\", "..", os.sep)):
            raise ValueError("memory_id contains unsafe path characters.")

        return value

    def _iter_item_paths(
        self,
        *,
        memory_class: Optional[MemoryClass] = None,
    ):
        directories: list[Path]
        if memory_class is None:
            directories = [self.get_store_dir(value) for value in self.CLASS_DIRECTORY_MAP]
        else:
            directories = [self.get_store_dir(memory_class)]

        for directory in directories:
            for item_path in sorted(directory.glob("*.json")):
                if item_path.is_file():
                    yield item_path

    def _load_item_from_path(self, item_path: Path) -> MemoryItem:
        data = json.loads(item_path.read_text(encoding="utf-8"))
        item = MemoryItem.model_validate(data)

        expected_dir = self.get_store_dir(item.memory_class)
        if item_path.parent != expected_dir:
            LOGGER.warning(
                "Memory item %s is stored in %s but claims class directory %s.",
                item.memory_id,
                item_path.parent,
                expected_dir,
            )

        self._memory_id_cache[item.memory_id] = item_path
        return item

    def _serialize_item(self, item: MemoryItem) -> dict:
        return item.model_dump(mode="json")

    def _atomic_write_json(self, destination: Path, payload: dict) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.stem}_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

        os.replace(temp_path, destination)

    def _validate_expected_revision(
        self,
        *,
        current_item: MemoryItem,
        expected_revision: Optional[int],
    ) -> None:
        if expected_revision is None:
            return

        current_revision = current_item.revision_info.revision
        if current_revision != expected_revision:
            raise MemoryItemRevisionMismatchError(
                f"Expected revision {expected_revision} but found {current_revision} "
                f"for memory_id={current_item.memory_id}."
            )

    def _assert_legacy_write_allowed(self) -> None:
        if not self._allow_legacy_writes:
            raise LegacyMemoryWriterDisabledError(
                "Legacy JSON memory is read-only migration input; canonical writes use the XDG SQLite Memory Fabric."
            )
