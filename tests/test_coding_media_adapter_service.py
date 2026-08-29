from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from app.api import coding_media_adapter_service as media_adapter
from app.api.coding_file_adapter_service import build_adapter_preview


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\x00\x00" * 800)


def test_probe_metadata_is_bounded_and_tag_values_are_not_exposed(tmp_path: Path, monkeypatch):
    source = tmp_path / "sample.mp3"
    source.write_bytes(b"ID3")
    probe = {
        "format": {
            "format_name": "mp3",
            "duration": "2.5",
            "bit_rate": "128000",
            "tags": {
                "title": "private-title-value",
                "artist": "private-artist-value",
                "location": "+40.0-105.0/",
            },
        },
        "streams": [{
            "index": 0,
            "codec_type": "audio",
            "codec_name": "mp3",
            "sample_rate": "44100",
            "channels": 2,
            "channel_layout": "stereo",
        }],
    }
    monkeypatch.setattr(media_adapter.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        media_adapter,
        "_run_bounded",
        lambda argv, stdout_limit, stderr_limit: (0, json.dumps(probe).encode(), b"", None),
    )

    result = media_adapter.inspect_media_path(source)

    assert result["status"] == "completed"
    assert result["audio"]["codec"] == "mp3"
    assert result["audio"]["sample_rate_hz"] == 44100
    assert result["privacy_flags"]["title_present"] is True
    assert result["privacy_flags"]["artist_present"] is True
    assert result["privacy_flags"]["location_present"] is True
    assert result["privacy_flags"]["gps_present"] is False
    assert "private-title-value" not in repr(result)
    assert "+40.0-105.0/" not in repr(result)


def test_extension_content_mismatch_is_refused(tmp_path: Path, monkeypatch):
    source = tmp_path / "pretend.mp3"
    source.write_bytes(b"not-media")
    probe = {
        "format": {"format_name": "wav", "duration": "0.1"},
        "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le"}],
    }
    monkeypatch.setattr(media_adapter.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(media_adapter, "_run_bounded", lambda *args, **kwargs: (0, json.dumps(probe).encode(), b"", None))

    result = media_adapter.inspect_media_path(source)

    assert result["status"] == "blocked"
    assert result["blocked_reason"] == "media_content_type_mismatch"
    assert result["safety_flags"]["content_type_matches_extension"] is False


def test_duration_limit_is_refused_before_hashing(tmp_path: Path, monkeypatch):
    source = tmp_path / "too-long.mp3"
    source.write_bytes(b"ID3")
    probe = {
        "format": {
            "format_name": "mp3",
            "duration": str(media_adapter.MAX_DURATION_SECONDS + 1),
        },
        "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
    }
    monkeypatch.setattr(media_adapter.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(media_adapter, "_run_bounded", lambda *args, **kwargs: (0, json.dumps(probe).encode(), b"", None))
    monkeypatch.setattr(media_adapter, "_hash_file", lambda path: pytest.fail("blocked media must not be hashed"))

    result = media_adapter.inspect_media_path(source)

    assert result["status"] == "blocked"
    assert result["blocked_reason"] == "media_duration_exceeded"
    assert result["safety_flags"]["within_duration_limit"] is False


def test_oversized_video_dimensions_block_thumbnail_decode(tmp_path: Path, monkeypatch):
    source = tmp_path / "oversized.mp4"
    source.write_bytes(b"media")
    probe = {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "1.0",
        },
        "streams": [{
            "codec_type": "video",
            "codec_name": "h264",
            "width": 8192,
            "height": 8192,
            "avg_frame_rate": "24/1",
        }],
    }
    monkeypatch.setattr(media_adapter.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(media_adapter, "_run_bounded", lambda *args, **kwargs: (0, json.dumps(probe).encode(), b"", None))

    result = media_adapter.thumbnail_media_path(source)

    assert result["status"] == "completed"
    assert result["thumbnail_status"] == "blocked"
    assert result["blocked_reason"] == "thumbnail_dimensions_exceeded"
    assert result["safety_flags"]["video_dimensions_bounded"] is False


def test_oversized_media_is_refused_before_probe(tmp_path: Path, monkeypatch):
    source = tmp_path / "large.wav"
    source.write_bytes(b"RIFF")
    monkeypatch.setattr(media_adapter, "MAX_MEDIA_BYTES", 1)
    monkeypatch.setattr(media_adapter, "_run_bounded", lambda *args, **kwargs: pytest.fail("ffprobe must not run"))

    result = media_adapter.inspect_media_path(source)

    assert result["blocked_reason"] == "media_file_too_large"
    assert result["safety_flags"]["within_size_limit"] is False


def test_real_wav_metadata_and_unified_preview_are_read_only(tmp_path: Path):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is not available")
    source = tmp_path / "tone.wav"
    _write_wav(source)

    result = media_adapter.inspect_media_path(source)
    preview = build_adapter_preview(source, max_bytes=4096, max_lines=20)

    assert result["status"] == "completed"
    assert result["media_family"] == "audio"
    assert result["audio"]["sample_rate_hz"] == 8000
    assert preview.descriptor.adapter == "media"
    assert preview.text_preview is None
    assert "Media file" in (preview.content_preview or "")
    assert preview.parse_summary["thumbnail_data_url"] is None


def test_corrupt_media_and_audio_thumbnail_are_honestly_refused(tmp_path: Path):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is not available")
    corrupt = tmp_path / "corrupt.mp3"
    corrupt.write_bytes(b"not an mp3")
    result = media_adapter.inspect_media_path(corrupt)
    assert result["status"] == "blocked"
    assert result["blocked_reason"] == "media_probe_failed"

    audio = tmp_path / "tone.wav"
    _write_wav(audio)
    thumbnail = media_adapter.thumbnail_media_path(audio)
    assert thumbnail["status"] == "completed"
    assert thumbnail["thumbnail_status"] == "not_applicable"
    assert thumbnail["blocked_reason"] == "audio_thumbnail_not_supported"


def test_fixed_thumbnail_generation_uses_disposable_video(tmp_path: Path):
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe is not available")
    source = tmp_path / "safe.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=green:s=64x48:d=0.2",
            "-an", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", "-y", str(source),
        ],
        check=True,
        timeout=15,
    )

    result = media_adapter.thumbnail_media_path(source)

    assert result["status"] == "completed"
    assert result["thumbnail_status"] == "completed"
    assert result["thumbnail_data_url"].startswith("data:image/png;base64,")
    assert result["thumbnail_path"] is None
