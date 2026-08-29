"""Shared safe text adapter for governed file previews."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


DEFAULT_MAX_TEXT_FILE_BYTES = 1024 * 1024


class TextFileTooLargeError(ValueError):
    def __init__(self, *, size_bytes: int, max_file_bytes: int) -> None:
        super().__init__(f"Text file is {size_bytes} bytes; hard limit is {max_file_bytes} bytes.")
        self.size_bytes = size_bytes
        self.max_file_bytes = max_file_bytes


@dataclass(frozen=True)
class TextPreview:
    preview_text: str
    raw_byte_hash: str
    decoded_text_hash: str
    encoding: str
    line_ending: str
    line_count: int
    byte_count: int
    bytes_returned: int
    lines_returned: int
    truncated: bool
    binary_detected: bool
    bom: str | None = None
    redaction_notes: tuple[str, ...] = ()


def detect_line_ending(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    if crlf and not lf and not cr:
        return "crlf"
    if lf and not crlf and not cr:
        return "lf"
    if cr and not crlf and not lf:
        return "cr"
    if crlf or lf or cr:
        return "mixed"
    return "none"


def decode_text(raw: bytes) -> tuple[str, str, str | None, bool]:
    if b"\x00" in raw:
        return "", "binary", None, True
    try:
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig"), "utf-8-sig", "utf-8-bom", False
        if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
            return raw.decode("utf-16"), "utf-16", "utf-16-bom", False
        return raw.decode("utf-8"), "utf-8", None, False
    except UnicodeDecodeError:
        return "", "binary", None, True


def build_text_preview(
    path: Path,
    *,
    max_bytes: int,
    max_lines: int,
    max_file_bytes: int = DEFAULT_MAX_TEXT_FILE_BYTES,
) -> TextPreview:
    size_bytes = path.stat().st_size
    if size_bytes > max_file_bytes:
        raise TextFileTooLargeError(size_bytes=size_bytes, max_file_bytes=max_file_bytes)
    raw = path.read_bytes()
    raw_byte_hash = sha256(raw).hexdigest()
    text, encoding, bom, binary = decode_text(raw)
    if binary:
        return TextPreview(
            preview_text="",
            raw_byte_hash=raw_byte_hash,
            decoded_text_hash="",
            encoding=encoding,
            line_ending="none",
            line_count=0,
            byte_count=len(raw),
            bytes_returned=0,
            lines_returned=0,
            truncated=False,
            binary_detected=True,
            bom=bom,
        )

    full_lines = text.splitlines()
    preview_raw = raw[: max(1, max_bytes)]
    preview_text, _, _, _ = decode_text(preview_raw)
    truncated = len(raw) > max_bytes
    preview_lines = preview_text.splitlines(keepends=True)
    if len(preview_lines) > max_lines:
        preview_text = "".join(preview_lines[:max_lines])
        truncated = True

    return TextPreview(
        preview_text=preview_text,
        raw_byte_hash=raw_byte_hash,
        decoded_text_hash=sha256(text.encode("utf-8")).hexdigest(),
        encoding=encoding,
        line_ending=detect_line_ending(text),
        line_count=len(full_lines),
        byte_count=len(raw),
        bytes_returned=len(preview_text.encode("utf-8")),
        lines_returned=len(preview_text.splitlines()),
        truncated=truncated,
        binary_detected=False,
        bom=bom,
    )


__all__ = (
    "DEFAULT_MAX_TEXT_FILE_BYTES",
    "TextFileTooLargeError",
    "TextPreview",
    "build_text_preview",
    "decode_text",
    "detect_line_ending",
)
