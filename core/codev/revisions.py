"""Canonical content identity shared with browser workspaces (UTF-8 JSON)."""
from hashlib import sha256
import json
import re
import unicodedata

from core.codev.contracts import WorkspaceFile


def relative_path(value: str) -> str:
    if not value or len(value) > 512 or value != unicodedata.normalize("NFC", value):
        raise ValueError("noncanonical_workspace_path")
    if value.startswith("/") or "\\" in value or ":" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("unsafe_workspace_path")
    for part in value.split("/"):
        if part in {"", ".", ".."} or part.endswith((".", " ")):
            raise ValueError("unsafe_workspace_path")
        if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part):
            raise ValueError("reserved_workspace_path")
    value.encode("utf-8", errors="strict")
    return value


def denied_path(value: str) -> bool:
    parts = relative_path(value).casefold().split("/")
    return any(part in {".git", ".ssh", ".gnupg", ".aws", ".azure", ".local_secrets", "vault", "sealed", ".elysia_backups", "node_modules", ".venv", "__pycache__"}
               or part == ".env" or part.startswith(".env.")
               or part.endswith((".pem", ".key", ".p12", ".pfx")) for part in parts)


def workspace_hash(files: list[WorkspaceFile]) -> str:
    """Availability/provenance never changes the identity of unchanged bytes."""
    seen: set[str] = set()
    rows = []
    for item in files:
        path = relative_path(item.path)
        collision = path.upper()
        if collision in seen:
            raise ValueError("workspace_path_collision")
        seen.add(collision)
        if item.text is not None:
            raw = item.text.encode("utf-8")
            if item.availability != "text" or sha256(raw).hexdigest() != item.content_hash or len(raw) != item.size_bytes:
                raise ValueError("workspace_file_hash_mismatch")
        rows.append([path, item.content_hash, item.size_bytes])
    rows.sort(key=lambda row: row[0].encode("utf-16-be"))
    return sha256(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
