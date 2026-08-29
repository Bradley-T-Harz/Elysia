"""Bounded ffprobe/ffmpeg adapter for local audio/video metadata and thumbnails."""

from __future__ import annotations

import base64
import json
import os
import selectors
import shutil
import subprocess
import tempfile
import time
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.api.coding_media_type_registry import CodingMediaTypeDescriptor, detect_media_type


MAX_MEDIA_BYTES = 512 * 1024 * 1024
MAX_THUMBNAIL_SOURCE_BYTES = 256 * 1024 * 1024
MAX_DURATION_SECONDS = 6 * 60 * 60
MAX_STREAMS = 24
MAX_VIDEO_PIXELS = 33_177_600
MAX_PROBE_OUTPUT_BYTES = 512 * 1024
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
MEDIA_PROCESS_TIMEOUT_SECONDS = 12.0

_PRIVACY_TAG_GROUPS: dict[str, tuple[str, ...]] = {
    "title_present": ("title",),
    "artist_present": ("artist", "album_artist"),
    "comment_present": ("comment", "description", "synopsis"),
    "date_present": ("date", "creation_time", "year"),
    "device_present": ("make", "model", "device", "com.apple.quicktime.make", "com.apple.quicktime.model"),
    "location_present": ("location", "location-eng", "com.apple.quicktime.location.iso6709"),
    "gps_present": ("gps", "gps_latitude", "gps_longitude", "com.apple.quicktime.location.iso6709"),
}


def media_dependency_health() -> dict[str, Any]:
    from app.api.media_worker_registry_service import media_worker_truth

    worker_truth = media_worker_truth()
    speech = worker_truth.get("speechforge", {})
    image = worker_truth.get("imageforge", {})
    video = worker_truth.get("videoforge", {})
    return {
        "ffprobe": {"available": shutil.which("ffprobe") is not None, "purpose": "bounded media metadata"},
        "ffmpeg": {"available": shutil.which("ffmpeg") is not None, "purpose": "fixed-argument video thumbnail"},
        "network_allowed": False,
        "transcription_live": bool(speech.get("enabled") and speech.get("stt_enabled") and speech.get("stt_executable_present") and speech.get("stt_model_present")),
        "tts_live": bool(speech.get("enabled") and speech.get("tts_enabled") and speech.get("tts_model_present") and speech.get("tts_voices_present")),
        "image_generation_state": image.get("state", "unavailable"),
        "video_generation_state": video.get("state", "unavailable"),
        "generation_live": False,
        "voice_cloning_live": False,
    }


def _run_bounded(argv: list[str], *, stdout_limit: int, stderr_limit: int) -> tuple[int, bytes, bytes, str | None]:
    """Run one fixed argv command with a timeout and bounded captured output."""
    process = subprocess.Popen(  # noqa: S603 - argv is fixed by this module; shell is never used.
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        close_fds=True,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    output = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": stderr_limit}
    deadline = time.monotonic() + MEDIA_PROCESS_TIMEOUT_SECONDS
    failure: str | None = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "media_tool_timeout"
                break
            for key, _ in selector.select(timeout=min(remaining, 0.2)):
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                stream = str(key.data)
                output[stream].extend(chunk)
                if len(output[stream]) > limits[stream]:
                    del output[stream][limits[stream]:]
                    failure = f"media_tool_{stream}_limit"
                    break
            if failure:
                break
            if process.poll() is not None and not selector.get_map():
                break
    finally:
        selector.close()
        if failure and process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    return process.returncode or 0, bytes(output["stdout"]), bytes(output["stderr"]), failure


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 3) if number >= 0 else None


def _safe_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _frame_rate(value: Any) -> float | None:
    try:
        rate = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None
    return round(rate, 3) if 0 < rate <= 1000 else None


def _rotation(value: Any) -> int | None:
    try:
        rotation = int(value)
    except (TypeError, ValueError):
        return None
    return rotation if -360 <= rotation <= 360 else None


def _collect_tags(probe: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    containers = [probe.get("format")]
    containers.extend(probe.get("streams") if isinstance(probe.get("streams"), list) else [])
    for container in containers:
        if not isinstance(container, dict):
            continue
        tags = container.get("tags")
        if isinstance(tags, dict):
            keys.update(str(key).strip().casefold() for key in tags if str(key).strip())
    return keys


def _privacy_flags(probe: dict[str, Any]) -> dict[str, bool]:
    keys = _collect_tags(probe)
    return {
        flag: any(marker == tag or marker in tag for tag in keys for marker in markers)
        for flag, markers in _PRIVACY_TAG_GROUPS.items()
    }


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_argv(path: Path) -> list[str]:
    return [
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-show_entries",
        "format=format_name,duration,bit_rate,nb_streams:format_tags=title,artist,album_artist,comment,description,synopsis,date,creation_time,year,make,model,device,location,location-eng,com.apple.quicktime.location.ISO6709,com.apple.quicktime.make,com.apple.quicktime.model:stream=index,codec_type,codec_name,sample_rate,channels,channel_layout,width,height,avg_frame_rate,r_frame_rate:stream_tags=title,artist,album_artist,comment,description,date,creation_time,make,model,device,location,location-eng,com.apple.quicktime.location.ISO6709:stream_side_data=rotation:stream_disposition=attached_pic",
        "-of", "json", str(path),
    ]


def _base_result(path: Path, descriptor: CodingMediaTypeDescriptor) -> dict[str, Any]:
    size = path.stat().st_size if path.exists() and path.is_file() else 0
    return {
        "status": "blocked",
        "descriptor": descriptor.to_payload(),
        "size_bytes": size,
        "media_family": descriptor.media_family,
        "container": None,
        "duration_seconds": None,
        "bitrate_bps": None,
        "stream_count": 0,
        "audio": {},
        "video": {},
        "privacy_flags": {key: False for key in _PRIVACY_TAG_GROUPS},
        "safety_flags": {
            "local_file_only": True,
            "read_only": True,
            "network_allowed": False,
            "within_size_limit": size <= MAX_MEDIA_BYTES,
            "within_duration_limit": True,
            "stream_count_bounded": True,
            "video_dimensions_bounded": True,
            "embedded_tag_values_exposed": False,
        },
        "dependencies": media_dependency_health(),
        "thumbnail_status": "not_requested",
        "thumbnail_data_url": None,
        "thumbnail_path": None,
        "blocked_reason": None,
        "warnings": list(descriptor.notes),
    }


def inspect_media_path(path: Path) -> dict[str, Any]:
    descriptor = detect_media_type(path)
    result = _base_result(path, descriptor)
    if not descriptor.metadata_inspectable:
        result["blocked_reason"] = "unsupported_media_type"
        return result
    if not path.is_file():
        result["blocked_reason"] = "media_path_not_file"
        return result
    if result["size_bytes"] > MAX_MEDIA_BYTES:
        result["blocked_reason"] = "media_file_too_large"
        return result
    if shutil.which("ffprobe") is None:
        result.update(status="unavailable", blocked_reason="ffprobe_unavailable")
        return result

    code, stdout, _stderr, failure = _run_bounded(
        _probe_argv(path), stdout_limit=MAX_PROBE_OUTPUT_BYTES, stderr_limit=MAX_DIAGNOSTIC_BYTES
    )
    if failure:
        result["blocked_reason"] = failure
        return result
    if code != 0:
        result["blocked_reason"] = "media_probe_failed"
        return result
    try:
        probe = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        result["blocked_reason"] = "media_probe_invalid_output"
        return result
    if not isinstance(probe, dict):
        result["blocked_reason"] = "media_probe_invalid_output"
        return result

    format_info = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    streams = [stream for stream in streams if isinstance(stream, dict)]
    result["stream_count"] = len(streams)
    if len(streams) > MAX_STREAMS:
        result["safety_flags"]["stream_count_bounded"] = False
        result["blocked_reason"] = "media_stream_count_exceeded"
        return result

    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    video_streams = [
        stream for stream in streams
        if stream.get("codec_type") == "video"
        and not bool((stream.get("disposition") or {}).get("attached_pic"))
    ]
    if descriptor.media_family == "audio" and not audio_streams:
        result["blocked_reason"] = "media_family_mismatch"
        return result
    if descriptor.media_family == "audio" and video_streams:
        result["blocked_reason"] = "media_family_mismatch"
        return result
    if descriptor.media_family == "video" and not video_streams:
        result["blocked_reason"] = "media_family_mismatch"
        return result

    duration = _safe_float(format_info.get("duration"))
    result["duration_seconds"] = duration
    if duration is None:
        result["safety_flags"]["within_duration_limit"] = False
        result["blocked_reason"] = "media_duration_unavailable"
        return result
    if duration is not None and duration > MAX_DURATION_SECONDS:
        result["safety_flags"]["within_duration_limit"] = False
        result["blocked_reason"] = "media_duration_exceeded"
        return result

    audio = audio_streams[0] if audio_streams else {}
    video = video_streams[0] if video_streams else {}
    side_data = video.get("side_data_list") if isinstance(video.get("side_data_list"), list) else []
    rotation = next(
        (_rotation(item.get("rotation")) for item in side_data if isinstance(item, dict) and item.get("rotation") is not None),
        None,
    )
    width = _safe_int(video.get("width"))
    height = _safe_int(video.get("height"))
    if width and height and width * height > MAX_VIDEO_PIXELS:
        result["safety_flags"]["video_dimensions_bounded"] = False
    container = str(format_info.get("format_name") or "")[:160] or None
    expected_container = any(
        expected in (container or "").casefold()
        for expected in descriptor.expected_formats
    )
    result["safety_flags"]["content_type_matches_extension"] = expected_container
    if not expected_container:
        result["blocked_reason"] = "media_content_type_mismatch"
        return result

    result.update(
        status="completed",
        blocked_reason=None,
        container=container,
        bitrate_bps=_safe_int(format_info.get("bit_rate")),
        audio={
            "codec": str(audio.get("codec_name") or "")[:80] or None,
            "sample_rate_hz": _safe_int(audio.get("sample_rate")),
            "channels": _safe_int(audio.get("channels")),
            "channel_layout": str(audio.get("channel_layout") or "")[:80] or None,
            "stream_count": len(audio_streams),
        },
        video={
            "codec": str(video.get("codec_name") or "")[:80] or None,
            "width": width,
            "height": height,
            "frame_rate_fps": _frame_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
            "rotation_degrees": rotation,
            "stream_count": len(video_streams),
        },
        privacy_flags=_privacy_flags(probe),
    )
    result["content_hash"] = _hash_file(path)
    return result


def thumbnail_media_path(path: Path) -> dict[str, Any]:
    result = inspect_media_path(path)
    if result.get("status") != "completed":
        result["thumbnail_status"] = "blocked"
        return result
    descriptor = detect_media_type(path)
    if descriptor.media_family != "video" or not descriptor.thumbnail_capable:
        result.update(thumbnail_status="not_applicable", blocked_reason="audio_thumbnail_not_supported")
        return result
    if result["size_bytes"] > MAX_THUMBNAIL_SOURCE_BYTES:
        result.update(thumbnail_status="blocked", blocked_reason="thumbnail_source_too_large")
        return result
    if result.get("safety_flags", {}).get("video_dimensions_bounded") is False:
        result.update(thumbnail_status="blocked", blocked_reason="thumbnail_dimensions_exceeded")
        return result
    if shutil.which("ffmpeg") is None:
        result.update(status="unavailable", thumbnail_status="unavailable", blocked_reason="ffmpeg_unavailable")
        return result

    duration = result.get("duration_seconds")
    seek_seconds = min(1.0, max(0.0, float(duration or 0.0) / 10.0))
    with tempfile.TemporaryDirectory(prefix="elysia-media-thumbnail-") as temporary_directory:
        output_path = Path(temporary_directory) / "thumbnail.png"
        argv = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-protocol_whitelist", "file,pipe", "-ss", f"{seek_seconds:.3f}",
            "-i", str(path), "-map", "0:v:0", "-frames:v", "1",
            "-vf", "scale=640:360:force_original_aspect_ratio=decrease",
            "-an", "-sn", "-dn", "-f", "image2", "-vcodec", "png",
            "-y", str(output_path),
        ]
        code, _stdout, _stderr, failure = _run_bounded(
            argv, stdout_limit=MAX_DIAGNOSTIC_BYTES, stderr_limit=MAX_DIAGNOSTIC_BYTES
        )
        if failure or code != 0 or not output_path.is_file():
            result.update(thumbnail_status="blocked", blocked_reason=failure or "thumbnail_generation_failed")
            return result
        if output_path.stat().st_size > MAX_THUMBNAIL_BYTES:
            result.update(thumbnail_status="blocked", blocked_reason="thumbnail_output_too_large")
            return result
        thumbnail_bytes = output_path.read_bytes()

    result.update(
        thumbnail_status="completed",
        thumbnail_data_url="data:image/png;base64," + base64.b64encode(thumbnail_bytes).decode("ascii"),
        thumbnail_path=None,
        blocked_reason=None,
    )
    return result


__all__ = (
    "MAX_DURATION_SECONDS",
    "MAX_MEDIA_BYTES",
    "MAX_STREAMS",
    "MAX_VIDEO_PIXELS",
    "MAX_THUMBNAIL_SOURCE_BYTES",
    "inspect_media_path",
    "media_dependency_health",
    "thumbnail_media_path",
)
