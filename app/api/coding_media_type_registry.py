"""Canonical registry for governed, read-only audio/video stewardship."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingMediaTypeDescriptor:
    type_id: str
    label: str
    extensions: tuple[str, ...]
    mime_types: tuple[str, ...]
    media_family: str
    expected_formats: tuple[str, ...]
    readable: bool = True
    metadata_inspectable: bool = True
    thumbnail_capable: bool = False
    transcribable: bool = False
    mutable: bool = False
    risk: str = "medium"
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["capabilities"] = {
            "readable": self.readable,
            "metadata_inspectable": self.metadata_inspectable,
            "thumbnail_capable": self.thumbnail_capable,
            "transcribable": self.transcribable,
            "mutable": self.mutable,
        }
        return payload


SUPPORTED_MEDIA_TYPES: tuple[CodingMediaTypeDescriptor, ...] = (
    CodingMediaTypeDescriptor("wav_audio", "WAV audio", (".wav",), ("audio/wav", "audio/x-wav"), "audio", ("wav",), transcribable=True),
    CodingMediaTypeDescriptor("mp3_audio", "MP3 audio", (".mp3",), ("audio/mpeg",), "audio", ("mp3",), transcribable=True),
    CodingMediaTypeDescriptor("flac_audio", "FLAC audio", (".flac",), ("audio/flac", "audio/x-flac"), "audio", ("flac",), transcribable=True),
    CodingMediaTypeDescriptor("ogg_audio", "Ogg audio", (".ogg",), ("audio/ogg", "application/ogg"), "audio", ("ogg",), transcribable=True),
    CodingMediaTypeDescriptor("m4a_audio", "M4A audio", (".m4a",), ("audio/mp4", "audio/x-m4a"), "audio", ("mov,mp4,m4a,3gp,3g2,mj2", "m4a", "mp4"), transcribable=True),
    CodingMediaTypeDescriptor("mp4_video", "MP4 video", (".mp4",), ("video/mp4",), "video", ("mov,mp4,m4a,3gp,3g2,mj2", "mp4"), thumbnail_capable=True, transcribable=True),
    CodingMediaTypeDescriptor("mov_video", "QuickTime video", (".mov",), ("video/quicktime",), "video", ("mov,mp4,m4a,3gp,3g2,mj2", "mov"), thumbnail_capable=True, transcribable=True),
    CodingMediaTypeDescriptor("mkv_video", "Matroska video", (".mkv",), ("video/x-matroska",), "video", ("matroska,webm", "matroska"), thumbnail_capable=True, transcribable=True),
    CodingMediaTypeDescriptor("webm_video", "WebM video", (".webm",), ("video/webm",), "video", ("matroska,webm", "webm"), thumbnail_capable=True, transcribable=True),
)

SUPPORTED_MEDIA_EXTENSIONS = tuple(
    sorted({extension for descriptor in SUPPORTED_MEDIA_TYPES for extension in descriptor.extensions})
)

UNKNOWN_MEDIA = CodingMediaTypeDescriptor(
    "media_unsupported",
    "Unsupported media file",
    (),
    ("application/octet-stream",),
    "unknown",
    (),
    readable=False,
    metadata_inspectable=False,
    risk="blocked",
    notes=("Only explicitly registered local audio/video formats are inspected.",),
)


def detect_media_type(path: Path | str) -> CodingMediaTypeDescriptor:
    suffix = Path(str(path)).suffix.lower()
    for descriptor in SUPPORTED_MEDIA_TYPES:
        if suffix in descriptor.extensions:
            return descriptor
    return UNKNOWN_MEDIA


def is_supported_media_path(path: Path | str) -> bool:
    return detect_media_type(path).metadata_inspectable


def media_registry_payload() -> list[dict[str, object]]:
    return [descriptor.to_payload() for descriptor in SUPPORTED_MEDIA_TYPES]


__all__ = (
    "CodingMediaTypeDescriptor",
    "SUPPORTED_MEDIA_EXTENSIONS",
    "SUPPORTED_MEDIA_TYPES",
    "UNKNOWN_MEDIA",
    "detect_media_type",
    "is_supported_media_path",
    "media_registry_payload",
)
