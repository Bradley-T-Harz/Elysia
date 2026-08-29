"""Safety checks for governed document containers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from zipfile import BadZipFile, ZipFile, is_zipfile

from app.api.coding_document_type_registry import CodingDocumentTypeDescriptor


DEFAULT_MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_CONTAINER_ENTRIES = 4000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
ZIP_CONTAINER_ADAPTERS = {"docx", "xlsx", "pptx", "odf"}


@dataclass(frozen=True)
class CodingDocumentSafetyResult:
    allowed: bool
    status: str
    size_bytes: int = 0
    byte_hash: str | None = None
    blocked_reason: str | None = None
    warnings: tuple[str, ...] = ()
    container_entry_count: int = 0
    uncompressed_bytes: int = 0
    encrypted: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "byte_hash": self.byte_hash,
            "blocked_reason": self.blocked_reason,
            "warnings": list(self.warnings),
            "container_entry_count": self.container_entry_count,
            "uncompressed_bytes": self.uncompressed_bytes,
            "encrypted": self.encrypted,
        }


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unsafe_zip_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return (
        normalized.startswith("/")
        or normalized.startswith("../")
        or "/../" in normalized
        or normalized == ".."
        or ":" in normalized.split("/", 1)[0]
    )


def _pdf_encrypted(path: Path) -> bool:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return bool(getattr(reader, "is_encrypted", False))
    except Exception:
        return False


def check_document_safety(
    path: Path,
    descriptor: CodingDocumentTypeDescriptor,
    *,
    max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    max_container_entries: int = DEFAULT_MAX_CONTAINER_ENTRIES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> CodingDocumentSafetyResult:
    if not descriptor.readable:
        return CodingDocumentSafetyResult(
            allowed=False,
            status="blocked",
            blocked_reason=descriptor.type_id,
            warnings=descriptor.notes,
        )
    if not path.exists() or not path.is_file():
        return CodingDocumentSafetyResult(False, "blocked", blocked_reason="missing_path")

    size = path.stat().st_size
    byte_hash = _hash_file(path)
    if size > max_document_bytes:
        return CodingDocumentSafetyResult(
            False,
            "blocked",
            size_bytes=size,
            byte_hash=byte_hash,
            blocked_reason="document_too_large",
            warnings=(f"Document exceeds configured limit of {max_document_bytes} bytes.",),
        )

    if descriptor.adapter == "pdf":
        encrypted = _pdf_encrypted(path)
        if encrypted:
            return CodingDocumentSafetyResult(
                False,
                "blocked",
                size_bytes=size,
                byte_hash=byte_hash,
                blocked_reason="encrypted_document",
                encrypted=True,
            )
        return CodingDocumentSafetyResult(True, "allowed", size_bytes=size, byte_hash=byte_hash)

    if descriptor.adapter in ZIP_CONTAINER_ADAPTERS:
        if not is_zipfile(path):
            return CodingDocumentSafetyResult(
                False,
                "blocked",
                size_bytes=size,
                byte_hash=byte_hash,
                blocked_reason="corrupted_or_invalid_container",
            )
        try:
            with ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > max_container_entries:
                    return CodingDocumentSafetyResult(
                        False,
                        "blocked",
                        size_bytes=size,
                        byte_hash=byte_hash,
                        blocked_reason="too_many_container_entries",
                        container_entry_count=len(infos),
                    )
                total_uncompressed = 0
                for info in infos:
                    if _unsafe_zip_name(info.filename):
                        return CodingDocumentSafetyResult(
                            False,
                            "blocked",
                            size_bytes=size,
                            byte_hash=byte_hash,
                            blocked_reason="zip_slip_path_traversal",
                            container_entry_count=len(infos),
                        )
                    total_uncompressed += int(info.file_size)
                if total_uncompressed > max_uncompressed_bytes:
                    return CodingDocumentSafetyResult(
                        False,
                        "blocked",
                        size_bytes=size,
                        byte_hash=byte_hash,
                        blocked_reason="container_uncompressed_size_too_large",
                        container_entry_count=len(infos),
                        uncompressed_bytes=total_uncompressed,
                    )
                return CodingDocumentSafetyResult(
                    True,
                    "allowed",
                    size_bytes=size,
                    byte_hash=byte_hash,
                    container_entry_count=len(infos),
                    uncompressed_bytes=total_uncompressed,
                )
        except BadZipFile:
            return CodingDocumentSafetyResult(
                False,
                "blocked",
                size_bytes=size,
                byte_hash=byte_hash,
                blocked_reason="corrupted_or_invalid_container",
            )

    return CodingDocumentSafetyResult(False, "blocked", size_bytes=size, byte_hash=byte_hash, blocked_reason="unsupported_document_adapter")


__all__ = ("CodingDocumentSafetyResult", "check_document_safety")
