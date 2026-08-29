"""Fixed local STT/Kokoro worker entrypoint. Heavy imports stay outside Elysia core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


ALLOWED_VOICES = {"af_sarah", "am_adam", "bf_emma", "bm_george", "ff_siwis", "zf_xiaoxiao"}
MAX_STT_BYTES = 512 * 1024 * 1024
MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
MAX_TTS_CHARS = 4000
MAX_TTS_BYTES = 16 * 1024 * 1024


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _run(argv: list[str], timeout: float = 240) -> tuple[int, bytes, bytes, str | None]:
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, close_fds=True)
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": 65_536, "stderr": 131_072}
    deadline = time.monotonic() + timeout
    failure = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "speech_subprocess_timeout"
                break
            for key, _ in selector.select(timeout=min(remaining, 0.2)):
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                stream = str(key.data)
                buffers[stream].extend(chunk)
                if len(buffers[stream]) > limits[stream]:
                    failure = f"speech_subprocess_{stream}_limit"
                    break
            if failure:
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
    return process.returncode or 0, bytes(buffers["stdout"]), bytes(buffers["stderr"]), failure


def _redact(text: str) -> str:
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", text)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)", "[REDACTED_PHONE]", text)
    return text


def _redact_json(value: Any) -> Any:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_json(item) for key, item in value.items()}
    return value


def _stt(job: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    source = Path(str(job.get("source_path") or ""))
    output = Path(str(job.get("output_path") or ""))
    root = Path(str(job.get("job_root") or ""))
    whisper_cli = Path(str(job.get("stt_executable") or ""))
    whisper_model = Path(str(job.get("stt_model") or ""))
    output_format = str(job.get("output_format") or "txt")
    if output_format not in {"txt", "json", "srt", "vtt"}:
        return {"status": "blocked", "blocked_reason": "unsupported_transcript_format"}
    if not source.is_file() or source.is_symlink() or source.stat().st_size > MAX_STT_BYTES:
        return {"status": "blocked", "blocked_reason": "invalid_or_oversized_source"}
    if (
        not _inside(output, root)
        or not whisper_cli.is_absolute()
        or not whisper_model.is_absolute()
        or not whisper_cli.is_file()
        or not whisper_model.is_file()
    ):
        return {"status": "blocked", "blocked_reason": "speech_worker_boundary_failed"}
    prefix = root / "whisper-output"
    with tempfile.TemporaryDirectory(prefix="speechforge-decode-", dir=root) as decode_dir:
        wav = Path(decode_dir) / "input.wav"
        code, _, _, failure = _run([
            "/usr/bin/ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe",
            "-i", str(source), "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(wav),
        ], timeout=30)
        if failure or code != 0 or not wav.is_file():
            return {"status": "failed", "blocked_reason": failure or "audio_decode_failed"}
        format_flag = {"txt": "-otxt", "json": "-ojf", "srt": "-osrt", "vtt": "-ovtt"}[output_format]
        argv = [
            str(whisper_cli), "-m", str(whisper_model), "-f", str(wav), "-t", "4", "-l", "en",
            "-np", "-ojf", "-of", str(prefix),
        ]
        if format_flag != "-ojf":
            argv.insert(-2, format_flag)
        code, _, _, failure = _run(argv)
        if failure or code != 0:
            return {"status": "failed", "blocked_reason": failure or "whisper_cpp_failed"}
    selected = prefix.with_suffix(f".{output_format}")
    metadata_path = prefix.with_suffix(".json")
    if not selected.is_file() or not metadata_path.is_file():
        return {"status": "failed", "blocked_reason": "transcript_output_missing"}
    if selected.stat().st_size > MAX_TRANSCRIPT_BYTES:
        return {"status": "blocked", "blocked_reason": "transcript_output_too_large"}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        metadata = {}
    if job.get("redact_sensitive_text") is True:
        if output_format == "json":
            payload = json.loads(selected.read_text(encoding="utf-8"))
            selected.write_text(json.dumps(_redact_json(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            selected.write_text(_redact(selected.read_text(encoding="utf-8")), encoding="utf-8")
    os.replace(selected, output)
    transcription = metadata.get("transcription") if isinstance(metadata, dict) else None
    segments = transcription if isinstance(transcription, list) else metadata.get("segments", []) if isinstance(metadata, dict) else []
    result_info = metadata.get("result") if isinstance(metadata.get("result"), dict) else {}
    return {
        "status": "completed",
        "worker_key": "speechforge_worker",
        "model_id": "whisper-cpp-base-en",
        "engine": "whisper_cpp",
        "output_path": str(output),
        "output_sha256": _sha(output),
        "output_bytes": output.stat().st_size,
        "language": str(result_info.get("language") or "en")[:16],
        "segment_count": len(segments),
        "runtime_seconds": round(time.monotonic() - started, 3),
        "network_used": False,
        "cloud_used": False,
        "raw_transcript_returned": False,
    }


def _tts(job: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    output = Path(str(job.get("output_path") or ""))
    root = Path(str(job.get("job_root") or ""))
    kokoro_model = Path(str(job.get("tts_model") or ""))
    kokoro_voices = Path(str(job.get("tts_voices") or ""))
    text = str(job.get("text") or "")
    voice = str(job.get("voice_id") or "")
    speed = float(job.get("speed") or 1.0)
    language = str(job.get("language") or "en-us")
    if not text or len(text) > MAX_TTS_CHARS or voice not in ALLOWED_VOICES or not 0.75 <= speed <= 1.25:
        return {"status": "blocked", "blocked_reason": "invalid_tts_request"}
    if (
        not _inside(output, root)
        or not kokoro_model.is_absolute()
        or not kokoro_voices.is_absolute()
        or not kokoro_model.is_file()
        or not kokoro_voices.is_file()
    ):
        return {"status": "blocked", "blocked_reason": "speech_worker_boundary_failed"}
    from kokoro_onnx import Kokoro
    import soundfile as sf

    engine = Kokoro(str(kokoro_model), str(kokoro_voices))
    samples, sample_rate = engine.create(text, voice=voice, speed=speed, lang=language)
    sf.write(str(output), samples, sample_rate, subtype="PCM_16")
    if not output.is_file() or output.stat().st_size > MAX_TTS_BYTES:
        return {"status": "blocked", "blocked_reason": "tts_output_missing_or_too_large"}
    return {
        "status": "completed",
        "worker_key": "speechforge_worker",
        "model_id": "kokoro-onnx-v1",
        "engine": "kokoro_onnx",
        "voice_id": voice,
        "language": language,
        "output_path": str(output),
        "output_sha256": _sha(output),
        "output_bytes": output.stat().st_size,
        "sample_rate_hz": int(sample_rate),
        "sample_count": int(len(samples)),
        "duration_seconds": round(len(samples) / float(sample_rate), 3),
        "runtime_seconds": round(time.monotonic() - started, 3),
        "network_used": False,
        "cloud_used": False,
        "synthetic_media": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request_path = Path(args.request)
    result_path = Path(args.result)
    try:
        job = json.loads(request_path.read_text(encoding="utf-8"))
        kind = str(job.get("kind") or "")
        result = _stt(job) if kind == "stt" else _tts(job) if kind == "tts" else {"status": "blocked", "blocked_reason": "unknown_speech_job"}
    except Exception as exc:
        result = {"status": "failed", "blocked_reason": "speech_worker_exception", "error_type": type(exc).__name__}
    result_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
