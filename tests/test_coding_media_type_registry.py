from __future__ import annotations

from app.api.coding_file_type_registry import detect_file_type
from app.api.coding_media_type_registry import detect_media_type, media_registry_payload


def test_media_registry_has_exact_chunk5_governed_slice():
    payload = media_registry_payload()
    by_extension = {
        extension: item
        for item in payload
        for extension in item["extensions"]
    }

    assert set(by_extension) == {
        ".wav", ".mp3", ".flac", ".ogg", ".m4a",
        ".mp4", ".mov", ".mkv", ".webm",
    }
    for extension in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
        assert by_extension[extension]["media_family"] == "audio"
        assert by_extension[extension]["capabilities"]["thumbnail_capable"] is False
        assert by_extension[extension]["capabilities"]["transcribable"] is True
        assert by_extension[extension]["capabilities"]["mutable"] is False
    for extension in (".mp4", ".mov", ".mkv", ".webm"):
        assert by_extension[extension]["media_family"] == "video"
        assert by_extension[extension]["capabilities"]["thumbnail_capable"] is True
        assert by_extension[extension]["capabilities"]["transcribable"] is True
        assert by_extension[extension]["capabilities"]["mutable"] is False


def test_media_types_are_read_only_in_unified_file_registry():
    descriptor = detect_file_type("recording.mp3", b"ID3")
    assert descriptor.adapter == "media"
    assert descriptor.readable is True
    assert descriptor.writable is False
    assert descriptor.patchable is False
    assert descriptor.creatable is False
    assert descriptor.deletable is False
    assert descriptor.renameable is False
    assert detect_media_type("unknown.avi").metadata_inspectable is False
