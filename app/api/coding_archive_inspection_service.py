"""Static archive inspection, manifest building, and risk analysis."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.parser import BytesParser
from hashlib import sha256
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
from typing import Any, BinaryIO
import unicodedata
import zipfile

from app.api.coding_archive_policy_service import load_archive_limits
from app.api.coding_archive_type_registry import (
    archive_type_from_extension,
    descriptor_for_type,
)
from app.api.coding_archive_worker_service import list_with_archiveforge_worker
from app.api.schemas.archive import ArchiveMemberRecord, ArchivePackageMetadata, ArchiveRiskFlag


NESTED_ARCHIVE_SUFFIXES = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".7z",
    ".rar",
    ".whl",
    ".jar",
    ".vsix",
    ".appimage",
    ".deb",
)
NATIVE_SUFFIXES = (".so", ".pyd", ".dll", ".dylib", ".node", ".exe", ".bin")
SCRIPT_NAMES = {"preinst", "postinst", "prerm", "postrm", "config", "triggers"}
WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


class ArchiveInspectionError(ValueError):
    """Raised for malformed containers that cannot be inspected safely."""


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return sha256(raw).hexdigest()


def _path_hash(value: str) -> str:
    return sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()[:24]


def _iso_timestamp(value: float | int | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _zip_timestamp(value: tuple[int, int, int, int, int, int]) -> str | None:
    try:
        return datetime(*value, tzinfo=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        return None


def _normalize_member_path(raw_path: str, max_chars: int) -> tuple[str | None, str | None, list[str]]:
    risks: list[str] = []
    if not raw_path or "\x00" in raw_path:
        return None, "empty_or_nul_path", ["invalid_path"]
    if len(raw_path) > max_chars:
        risks.append("path_too_long")
    if raw_path.startswith(("/", "\\")):
        risks.append("absolute_path")
    if raw_path.startswith("~"):
        risks.append("home_relative_path")
    if WINDOWS_DRIVE_RE.match(raw_path) or raw_path.startswith(("\\\\", "//")):
        risks.append("windows_unc_or_drive_path")
    replaced = raw_path.replace("\\", "/")
    parts = replaced.split("/")
    if any(part == ".." for part in parts):
        risks.append("path_traversal")
    cleaned = [part for part in parts if part not in {"", "."}]
    if not cleaned:
        risks.append("empty_normalized_path")
    normalized = PurePosixPath(*cleaned).as_posix() if cleaned else None
    blocking = {
        "invalid_path",
        "path_too_long",
        "absolute_path",
        "home_relative_path",
        "windows_unc_or_drive_path",
        "path_traversal",
        "empty_normalized_path",
    }
    reason = next((risk for risk in risks if risk in blocking), None)
    return normalized, reason, risks


def _member_from_values(
    *,
    index: int,
    raw_path: str,
    kind: str,
    compressed_size: int,
    uncompressed_size: int,
    mode: int | None,
    mtime: str | None,
    is_directory: bool,
    is_regular_file: bool,
    is_symlink: bool = False,
    is_hardlink: bool = False,
    is_device: bool = False,
    is_fifo: bool = False,
    is_socket: bool = False,
    is_encrypted: bool = False,
    extraction_supported: bool,
    max_path_chars: int,
) -> ArchiveMemberRecord:
    normalized, blocked_reason, risks = _normalize_member_path(raw_path, max_path_chars)
    executable = bool(mode is not None and mode & 0o111)
    if is_symlink:
        risks.append("symlink")
        blocked_reason = blocked_reason or "symlink"
    if is_hardlink:
        risks.append("hardlink")
        blocked_reason = blocked_reason or "hardlink"
    if is_device:
        risks.append("device")
        blocked_reason = blocked_reason or "device"
    if is_fifo:
        risks.append("fifo")
        blocked_reason = blocked_reason or "fifo"
    if is_socket:
        risks.append("socket")
        blocked_reason = blocked_reason or "socket"
    if is_encrypted:
        risks.append("encrypted")
        blocked_reason = blocked_reason or "encrypted"
    if mode is not None and mode & (stat.S_ISUID | stat.S_ISGID):
        risks.append("setid_permission")
        blocked_reason = blocked_reason or "setid_permission"
    if executable and not is_directory:
        risks.append("executable_permission")
    lower_name = (normalized or raw_path).casefold()
    nested = any(lower_name.endswith(suffix) for suffix in NESTED_ARCHIVE_SUFFIXES)
    if nested:
        risks.append("nested_archive")
        blocked_reason = blocked_reason or "nested_archive_inspect_only"
    if any(lower_name.endswith(suffix) for suffix in NATIVE_SUFFIXES):
        risks.append("native_binary")
    collision_key = unicodedata.normalize("NFC", normalized or raw_path).casefold()
    extractable = bool(
        extraction_supported
        and blocked_reason is None
        and (is_regular_file or is_directory)
        and not is_symlink
        and not is_hardlink
        and not is_device
        and not is_fifo
        and not is_socket
    )
    return ArchiveMemberRecord(
        index=index,
        display_path=raw_path,
        path_hash=_path_hash(raw_path),
        normalized_relative_path=normalized,
        collision_key_hash=_path_hash(collision_key),
        kind=kind,
        compressed_size=max(0, compressed_size),
        uncompressed_size=max(0, uncompressed_size),
        mode=mode,
        mtime=mtime,
        is_directory=is_directory,
        is_regular_file=is_regular_file,
        is_symlink=is_symlink,
        is_hardlink=is_hardlink,
        is_device=is_device,
        is_fifo=is_fifo,
        is_socket=is_socket,
        is_executable=executable,
        is_encrypted=is_encrypted,
        is_nested_archive_candidate=nested,
        extractable=extractable,
        blocked_reason=blocked_reason,
        risk_flags=sorted(set(risks)),
    )


def _detect_zip_semantics(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [item.filename.replace("\\", "/") for item in archive.infolist()[:10001]]
    except (OSError, zipfile.BadZipFile):
        return "zip"
    lowered = [name.casefold() for name in names]
    if any(".dist-info/wheel" in name for name in lowered):
        return "whl"
    if any(name == "extension.vsixmanifest" or name.endswith("/extension.vsixmanifest") for name in lowered) and any(
        name == "extension/package.json" or name.endswith("/extension/package.json") for name in lowered
    ):
        return "vsix"
    if any(name == "meta-inf/manifest.mf" for name in lowered) or any(name.endswith(".class") for name in lowered):
        return "jar"
    return "zip"


def _read_ar_members(path: Path, *, max_members: int = 10_000) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        if stream.read(8) != b"!<arch>\n":
            raise ArchiveInspectionError("invalid_ar_container")
        index = 0
        while True:
            if index > max_members:
                break
            header = stream.read(60)
            if not header:
                break
            if len(header) != 60 or header[58:60] != b"`\n":
                raise ArchiveInspectionError("malformed_ar_header")
            name = header[:16].decode("utf-8", errors="replace").strip().rstrip("/")
            try:
                size = int(header[48:58].decode("ascii", errors="strict").strip() or "0")
            except ValueError as exc:
                raise ArchiveInspectionError("malformed_ar_member_size") from exc
            offset = stream.tell()
            members.append({"index": index, "name": name, "offset": offset, "size": max(0, size)})
            stream.seek(size + (size % 2), io.SEEK_CUR)
            index += 1
    return members


def _detect_content_type(path: Path, head: bytes, *, header_only: bool = False) -> str:
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06") or head.startswith(b"PK\x07\x08"):
        return "zip" if header_only else _detect_zip_semantics(path)
    if head.startswith(b"7z\xbc\xaf'\x1c"):
        return "7z"
    if head.startswith(b"Rar!\x1a\x07"):
        return "rar"
    if head.startswith(b"!<arch>\n"):
        if header_only:
            return "unknown"
        try:
            ar_members = _read_ar_members(path)
            debian = next((member for member in ar_members if member["name"] == "debian-binary"), None)
            if debian:
                with path.open("rb") as stream:
                    stream.seek(int(debian["offset"]))
                    if stream.read(min(16, int(debian["size"]))).startswith(b"2.0"):
                        return "deb"
        except (OSError, ArchiveInspectionError):
            pass
    if head.startswith(b"\x7fELF") and (path.name.lower().endswith(".appimage") or head[8:11] in {b"AI\x01", b"AI\x02"}):
        return "appimage"
    if header_only:
        return "tar_gz" if head.startswith(b"\x1f\x8b") and path.name.lower().endswith((".tar.gz", ".tgz")) else "unknown"
    try:
        if tarfile.is_tarfile(path):
            if head.startswith(b"\x1f\x8b"):
                return "tar_gz"
            if head.startswith((b"BZh", b"\xfd7zXZ\x00")):
                return "unknown"
            return "tar"
    except OSError:
        pass
    return "unknown"


def _zip_members(
    path: Path,
    *,
    archive_type: str,
    max_path_chars: int,
    max_members: int,
) -> list[ArchiveMemberRecord]:
    extraction_supported = archive_type == "zip"
    members: list[ArchiveMemberRecord] = []
    with zipfile.ZipFile(path) as archive:
        for index, info in enumerate(archive.infolist()[: max_members + 1]):
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode) if mode else 0
            is_directory = info.is_dir() or file_type == stat.S_IFDIR
            is_symlink = file_type == stat.S_IFLNK
            is_device = file_type in {stat.S_IFBLK, stat.S_IFCHR}
            is_fifo = file_type == stat.S_IFIFO
            is_socket = file_type == stat.S_IFSOCK
            regular = not (is_directory or is_symlink or is_device or is_fifo or is_socket)
            members.append(
                _member_from_values(
                    index=index,
                    raw_path=info.filename,
                    kind="directory" if is_directory else "symlink" if is_symlink else "device" if is_device else "fifo" if is_fifo else "socket" if is_socket else "file",
                    compressed_size=info.compress_size,
                    uncompressed_size=info.file_size,
                    mode=mode or None,
                    mtime=_zip_timestamp(info.date_time),
                    is_directory=is_directory,
                    is_regular_file=regular,
                    is_symlink=is_symlink,
                    is_device=is_device,
                    is_fifo=is_fifo,
                    is_socket=is_socket,
                    is_encrypted=bool(info.flag_bits & 0x1),
                    extraction_supported=extraction_supported,
                    max_path_chars=max_path_chars,
                )
            )
    return members


def _tar_members(
    source: Path | None = None,
    *,
    fileobj: BinaryIO | None = None,
    prefix: str = "",
    extraction_supported: bool,
    max_path_chars: int,
    max_members: int,
) -> list[ArchiveMemberRecord]:
    members: list[ArchiveMemberRecord] = []
    with tarfile.open(name=str(source) if source else None, fileobj=fileobj, mode="r:*") as archive:
        for index, info in enumerate(archive):
            if index > max_members:
                break
            raw_name = f"{prefix}{info.name}" if prefix else info.name
            is_device = info.ischr() or info.isblk()
            is_socket = False
            members.append(
                _member_from_values(
                    index=index,
                    raw_path=raw_name,
                    kind=(
                        "directory" if info.isdir() else "symlink" if info.issym() else "hardlink" if info.islnk()
                        else "device" if is_device else "fifo" if info.isfifo() else "file" if info.isfile() else "special"
                    ),
                    compressed_size=0,
                    uncompressed_size=info.size if info.isfile() else 0,
                    mode=info.mode,
                    mtime=_iso_timestamp(info.mtime),
                    is_directory=info.isdir(),
                    is_regular_file=info.isfile(),
                    is_symlink=info.issym(),
                    is_hardlink=info.islnk(),
                    is_device=is_device,
                    is_fifo=info.isfifo(),
                    is_socket=is_socket,
                    extraction_supported=extraction_supported,
                    max_path_chars=max_path_chars,
                )
            )
    return members


class _ArMemberReader(io.RawIOBase):
    def __init__(self, source: BinaryIO, offset: int, size: int) -> None:
        self._source = source
        self._offset = offset
        self._size = size
        self._position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self._position + offset
        elif whence == io.SEEK_END:
            position = self._size + offset
        else:
            raise ValueError("invalid_whence")
        self._position = max(0, min(self._size, position))
        return self._position

    def read(self, size: int = -1) -> bytes:
        remaining = self._size - self._position
        count = remaining if size is None or size < 0 else min(size, remaining)
        if count <= 0:
            return b""
        self._source.seek(self._offset + self._position)
        data = self._source.read(count)
        self._position += len(data)
        return data


def _deb_members(
    path: Path,
    *,
    max_path_chars: int,
    max_members: int,
) -> tuple[list[ArchiveMemberRecord], list[dict[str, Any]]]:
    ar_members = _read_ar_members(path, max_members=max_members)
    records: list[ArchiveMemberRecord] = []
    with path.open("rb") as stream:
        for member in ar_members:
            name = str(member["name"])
            if name.startswith("control.tar") or name.startswith("data.tar"):
                prefix = "control/" if name.startswith("control.tar") else "data/"
                reader = _ArMemberReader(stream, int(member["offset"]), int(member["size"]))
                try:
                    nested = _tar_members(
                        fileobj=reader,
                        prefix=prefix,
                        extraction_supported=False,
                        max_path_chars=max_path_chars,
                        max_members=max_members,
                    )
                except (tarfile.TarError, OSError):
                    nested = []
                for record in nested:
                    if len(records) > max_members:
                        break
                    record.index = len(records)
                    records.append(record)
            else:
                records.append(
                    _member_from_values(
                        index=len(records),
                        raw_path=f"container/{name}",
                        kind="file",
                        compressed_size=int(member["size"]),
                        uncompressed_size=int(member["size"]),
                        mode=None,
                        mtime=None,
                        is_directory=False,
                        is_regular_file=True,
                        extraction_supported=False,
                        max_path_chars=max_path_chars,
                    )
                )
            if len(records) > max_members:
                break
    return records, ar_members


def _bounded_zip_read(archive: zipfile.ZipFile, name: str, limit: int) -> tuple[bytes, bool]:
    try:
        with archive.open(name) as stream:
            raw = stream.read(limit + 1)
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile):
        return b"", False
    return raw[:limit], len(raw) > limit


def _metadata_lines(raw: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().casefold()
        if normalized in {"name", "version", "requires-python", "wheel-version", "tag", "main-class", "class-path", "implementation-title", "implementation-version"}:
            result[key.strip()] = value.strip()[:500]
    return result


def _inspect_zip_package(
    path: Path,
    archive_type: str,
    limit: int,
    max_members: int,
) -> ArchivePackageMetadata | None:
    if archive_type not in {"whl", "jar", "vsix"}:
        return None
    scripts: list[str] = []
    summary: dict[str, Any] = {}
    native_count = 0
    entrypoint_count = 0
    truncated = False
    warnings: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = [info.filename for info in archive.infolist()[: max_members + 1]]
        lowered = {name.casefold(): name for name in names}
        native_count = sum(1 for name in names if name.casefold().endswith(NATIVE_SUFFIXES))
        if archive_type == "whl":
            metadata_name = next((name for name in names if name.casefold().endswith(".dist-info/metadata")), None)
            wheel_name = next((name for name in names if name.casefold().endswith(".dist-info/wheel")), None)
            entry_name = next((name for name in names if name.casefold().endswith(".dist-info/entry_points.txt")), None)
            record_name = next((name for name in names if name.casefold().endswith(".dist-info/record")), None)
            if metadata_name:
                raw, cut = _bounded_zip_read(archive, metadata_name, limit)
                truncated = truncated or cut
                parsed = BytesParser().parsebytes(raw)
                summary.update({
                    "name": str(parsed.get("Name") or "")[:300],
                    "version": str(parsed.get("Version") or "")[:120],
                    "requires_python": str(parsed.get("Requires-Python") or "")[:300],
                    "dependency_count": len(parsed.get_all("Requires-Dist") or []),
                })
            if wheel_name:
                raw, cut = _bounded_zip_read(archive, wheel_name, limit)
                truncated = truncated or cut
                wheel_fields = _metadata_lines(raw)
                summary["wheel_version"] = wheel_fields.get("Wheel-Version")
                summary["tags"] = [line.split(":", 1)[1].strip()[:200] for line in raw.decode("utf-8", errors="replace").splitlines() if line.casefold().startswith("tag:")][:20]
            if entry_name:
                raw, cut = _bounded_zip_read(archive, entry_name, limit)
                truncated = truncated or cut
                sections = [line.strip()[1:-1] for line in raw.decode("utf-8", errors="replace").splitlines() if line.strip().startswith("[") and line.strip().endswith("]")]
                scripts = sections[:50]
                entrypoint_count = sum(1 for line in raw.decode("utf-8", errors="replace").splitlines() if "=" in line and not line.lstrip().startswith(("#", "[")))
            summary["record_present"] = bool(record_name)
            if not record_name:
                warnings.append("Wheel RECORD metadata is missing.")
        elif archive_type == "jar":
            manifest_name = lowered.get("meta-inf/manifest.mf")
            if manifest_name:
                raw, cut = _bounded_zip_read(archive, manifest_name, limit)
                truncated = truncated or cut
                summary.update(_metadata_lines(raw))
            summary.update(
                class_count=sum(1 for name in names if name.casefold().endswith(".class")),
                signature_file_count=sum(1 for name in names if name.casefold().startswith("meta-inf/") and name.casefold().endswith((".sf", ".rsa", ".dsa", ".ec"))),
                service_provider_count=sum(1 for name in names if name.casefold().startswith("meta-inf/services/")),
            )
            if summary.get("Main-Class"):
                scripts.append("Main-Class")
                entrypoint_count += 1
            if summary.get("Class-Path"):
                scripts.append("Class-Path")
        else:
            package_name = lowered.get("extension/package.json") or next((name for name in names if name.casefold().endswith("/package.json")), None)
            manifest_name = lowered.get("extension.vsixmanifest") or next((name for name in names if name.casefold().endswith("/extension.vsixmanifest")), None)
            if package_name:
                raw, cut = _bounded_zip_read(archive, package_name, limit)
                truncated = truncated or cut
                try:
                    package = json.loads(raw.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    package = {}
                if isinstance(package, dict):
                    activation = list(package.get("activationEvents") or []) if isinstance(package.get("activationEvents"), list) else []
                    commands = ((package.get("contributes") or {}).get("commands") or []) if isinstance(package.get("contributes"), dict) else []
                    package_scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
                    scripts = [str(key)[:100] for key in package_scripts][:50]
                    entrypoint_count = len(activation)
                    summary.update(
                        name=str(package.get("name") or "")[:200],
                        publisher=str(package.get("publisher") or "")[:200],
                        version=str(package.get("version") or "")[:100],
                        activation_event_count=len(activation),
                        broad_activation=any(str(item) in {"*", "onStartupFinished"} for item in activation),
                        command_count=len(commands) if isinstance(commands, list) else 0,
                        extension_kind=list(package.get("extensionKind") or [])[:10] if isinstance(package.get("extensionKind"), list) else package.get("extensionKind"),
                        dependency_count=len(package.get("extensionDependencies") or []) if isinstance(package.get("extensionDependencies"), list) else 0,
                        proposed_api=bool(package.get("enabledApiProposals")),
                    )
            summary["vsix_manifest_present"] = bool(manifest_name)
    return ArchivePackageMetadata(
        container_kind=archive_type,
        summary=summary,
        scripts_present=scripts,
        native_binary_count=native_count,
        executable_entrypoint_count=entrypoint_count,
        metadata_truncated=truncated,
        install_supported=False,
        execute_supported=False,
        warnings=warnings,
    )


def _inspect_deb_package(members: list[ArchiveMemberRecord]) -> ArchivePackageMetadata:
    scripts = sorted(
        {
            PurePosixPath(member.normalized_relative_path or "").name
            for member in members
            if (member.normalized_relative_path or "").startswith("control/")
            and PurePosixPath(member.normalized_relative_path or "").name in SCRIPT_NAMES
        }
    )
    names = [member.normalized_relative_path or "" for member in members]
    summary = {
        "control_member_count": sum(1 for name in names if name.startswith("control/")),
        "data_member_count": sum(1 for name in names if name.startswith("data/")),
        "maintainer_script_count": len(scripts),
        "systemd_unit_count": sum(1 for name in names if "/systemd/" in name or name.endswith((".service", ".socket", ".timer"))),
        "udev_rule_count": sum(1 for name in names if "/udev/" in name or name.endswith(".rules")),
        "cron_entry_count": sum(1 for name in names if "/cron." in name or "/cron/" in name),
        "desktop_file_count": sum(1 for name in names if name.endswith(".desktop")),
        "system_binary_count": sum(1 for name in names if name.startswith(("data/usr/bin/", "data/usr/sbin/", "data/bin/", "data/sbin/"))),
        "library_count": sum(1 for name in names if "/lib/" in name or name.endswith((".so", ".a"))),
    }
    return ArchivePackageMetadata(
        container_kind="deb",
        summary=summary,
        scripts_present=scripts,
        native_binary_count=sum(1 for member in members if "native_binary" in member.risk_flags),
        executable_entrypoint_count=summary["system_binary_count"],
        install_supported=False,
        execute_supported=False,
    )


def _apply_collision_analysis(members: list[ArchiveMemberRecord]) -> None:
    exact: dict[str, list[ArchiveMemberRecord]] = defaultdict(list)
    normalized: dict[str, list[ArchiveMemberRecord]] = defaultdict(list)
    for member in members:
        exact[member.display_path].append(member)
        key = unicodedata.normalize("NFC", member.normalized_relative_path or member.display_path).casefold()
        normalized[key].append(member)
    for group in exact.values():
        if len(group) > 1:
            for member in group:
                member.risk_flags = sorted(set(member.risk_flags + ["duplicate_path"]))
                member.blocked_reason = member.blocked_reason or "duplicate_path"
                member.extractable = False
    for group in normalized.values():
        distinct = {member.display_path for member in group}
        if len(group) > 1 and len(distinct) > 1:
            for member in group:
                member.risk_flags = sorted(set(member.risk_flags + ["unicode_or_case_collision"]))
                member.blocked_reason = member.blocked_reason or "unicode_or_case_collision"
                member.extractable = False


def _risk_flags(
    *,
    members: list[ArchiveMemberRecord],
    archive_size: int,
    projected_size: int,
    directory_count: int,
    package_metadata: ArchivePackageMetadata | None,
    extension_type: str,
    detected_type: str,
    limits: dict[str, int],
) -> list[ArchiveRiskFlag]:
    counts = Counter(flag for member in members for flag in member.risk_flags)
    risks: list[ArchiveRiskFlag] = []
    blocking_member_flags = {
        "invalid_path",
        "path_too_long",
        "absolute_path",
        "home_relative_path",
        "windows_unc_or_drive_path",
        "path_traversal",
        "empty_normalized_path",
        "symlink",
        "hardlink",
        "device",
        "fifo",
        "socket",
        "encrypted",
        "setid_permission",
        "duplicate_path",
        "unicode_or_case_collision",
    }
    for code, count in sorted(counts.items()):
        blocked = code in blocking_member_flags
        severity = "blocked" if blocked else "high" if code in {"native_binary", "nested_archive", "executable_permission"} else "warning"
        risks.append(
            ArchiveRiskFlag(
                code=code,
                severity=severity,  # type: ignore[arg-type]
                count=count,
                blocks_extraction=blocked,
                summary=f"{count} archive member(s) triggered {code.replace('_', ' ')}.",
            )
        )
    if extension_type != detected_type:
        risks.append(ArchiveRiskFlag(code="extension_content_mismatch", severity="blocked", blocks_extraction=True, summary="Filename extension and inspected content type do not match."))
    ratio = projected_size / max(1, archive_size)
    if ratio >= limits["compression_ratio_block"]:
        risks.append(ArchiveRiskFlag(code="extreme_compression_ratio", severity="blocked", blocks_extraction=True, summary="Projected compression ratio exceeds the extraction block threshold."))
    elif ratio >= limits["compression_ratio_warn"]:
        risks.append(ArchiveRiskFlag(code="high_compression_ratio", severity="high", blocks_extraction=False, summary="Projected compression ratio is bomb-like and requires caution."))
    hard_limits = (
        (len(members) > limits["max_members"], "member_count_limit", "Archive member count exceeds policy."),
        (directory_count > limits["max_directories"], "directory_count_limit", "Archive directory count exceeds policy."),
        (projected_size > limits["max_projected_uncompressed_bytes"], "projected_size_limit", "Projected uncompressed size exceeds policy."),
        (any(member.uncompressed_size > limits["max_single_file_bytes"] for member in members), "single_file_size_limit", "At least one member exceeds the single-file limit."),
    )
    for triggered, code, summary in hard_limits:
        if triggered:
            risks.append(ArchiveRiskFlag(code=code, severity="blocked", blocks_extraction=True, summary=summary))
    if package_metadata:
        if package_metadata.scripts_present:
            risks.append(ArchiveRiskFlag(code="package_scripts", severity="high", count=len(package_metadata.scripts_present), summary="Package scripts or executable entrypoint metadata are present."))
        if package_metadata.native_binary_count:
            risks.append(ArchiveRiskFlag(code="package_native_binaries", severity="high", count=package_metadata.native_binary_count, summary="Package contains native binaries."))
        if package_metadata.executable_entrypoint_count:
            risks.append(ArchiveRiskFlag(code="package_entrypoints", severity="high", count=package_metadata.executable_entrypoint_count, summary="Package declares executable or activation entrypoints."))
    return risks


def inspect_archive_path(path: Path) -> dict[str, Any]:
    policy = load_archive_limits()
    limits = policy["limits"]
    archive_size = path.stat().st_size
    extension_type = archive_type_from_extension(path)
    with path.open("rb") as stream:
        head = stream.read(8192)
    input_size_blocked = archive_size > limits["max_archive_input_bytes"]
    archive_sha256 = None if input_size_blocked else hash_file(path)
    detected_type = _detect_content_type(path, head, header_only=input_size_blocked)
    descriptor = descriptor_for_type(detected_type)
    members: list[ArchiveMemberRecord] = []
    package_metadata: ArchivePackageMetadata | None = None
    tool_used = "python_stdlib"
    inspect_error: str | None = None
    if input_size_blocked:
        inspect_error = "archive_input_size_limit"
    elif detected_type in {"zip", "whl", "jar", "vsix"}:
        try:
            members = _zip_members(
                path,
                archive_type=detected_type,
                max_path_chars=limits["max_output_path_chars"],
                max_members=limits["max_members"],
            )
            package_metadata = _inspect_zip_package(
                path,
                detected_type,
                limits["max_metadata_member_bytes"],
                limits["max_members"],
            )
        except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
            inspect_error = "malformed_or_unreadable_zip_container"
    elif detected_type in {"tar", "tar_gz"}:
        try:
            members = _tar_members(
                path,
                extraction_supported=True,
                max_path_chars=limits["max_output_path_chars"],
                max_members=limits["max_members"],
            )
        except (OSError, tarfile.TarError):
            inspect_error = "malformed_or_unreadable_tar_container"
    elif detected_type in {"7z", "rar"}:
        external = list_with_archiveforge_worker(
            path,
            archive_type=detected_type,
            timeout_seconds=min(20, limits["max_extraction_runtime_seconds"]),
            max_stdout_bytes=limits["max_worker_stdout_bytes"],
            max_stderr_bytes=limits["max_worker_stderr_bytes"],
        )
        tool_used = str(external.get("tool") or "archiveforge_worker")
        if external.get("status") != "completed":
            inspect_error = str(external.get("reason") or "external_archive_listing_failed")
        for index, raw in enumerate((external.get("members") or [])[: limits["max_members"] + 1]):
            if not isinstance(raw, dict):
                continue
            members.append(
                _member_from_values(
                    index=index,
                    raw_path=str(raw.get("display_path") or ""),
                    kind=str(raw.get("kind") or "file"),
                    compressed_size=int(raw.get("compressed_size") or 0),
                    uncompressed_size=int(raw.get("uncompressed_size") or 0),
                    mode=None,
                    mtime=None,
                    is_directory=bool(raw.get("is_directory")),
                    is_regular_file=bool(raw.get("is_regular_file", True)),
                    is_encrypted=bool(raw.get("is_encrypted")),
                    extraction_supported=False,
                    max_path_chars=limits["max_output_path_chars"],
                )
            )
    elif detected_type == "deb":
        try:
            members, _ = _deb_members(
                path,
                max_path_chars=limits["max_output_path_chars"],
                max_members=limits["max_members"],
            )
            package_metadata = _inspect_deb_package(members)
        except (OSError, ArchiveInspectionError):
            inspect_error = "malformed_or_unreadable_deb_container"
    elif detected_type == "appimage":
        tool_used = "static_elf_header"
        package_metadata = ArchivePackageMetadata(
            container_kind="appimage",
            summary={
                "elf_header_present": head.startswith(b"\x7fELF"),
                "appimage_marker_present": head[8:11] in {b"AI\x01", b"AI\x02"},
                "payload_listing_state": "unavailable_by_design_without_proven_nonexecuting_offset",
            },
            native_binary_count=1,
            executable_entrypoint_count=1,
            warnings=["AppImage payload was not mounted or extracted; the container was never executed."],
        )
    else:
        inspect_error = "unsupported_or_unrecognized_container"

    _apply_collision_analysis(members)
    manifest_truncated = len(members) > limits["max_members"]
    projected = sum(member.uncompressed_size for member in members if member.is_regular_file)
    directory_count = sum(1 for member in members if member.is_directory)
    largest = max((member.uncompressed_size for member in members), default=0)
    nested_count = sum(1 for member in members if member.is_nested_archive_candidate)
    risks = _risk_flags(
        members=members,
        archive_size=archive_size,
        projected_size=projected,
        directory_count=directory_count,
        package_metadata=package_metadata,
        extension_type=extension_type,
        detected_type=detected_type,
        limits=limits,
    )
    if inspect_error:
        risks.append(ArchiveRiskFlag(code=inspect_error, severity="blocked", blocks_extraction=True, summary="Archive inspection could not complete safely."))
    risk_counts = Counter(risk.code for risk in risks for _ in range(risk.count))
    manifest_payload = {
        "archive_sha256": archive_sha256,
        "archive_size_bytes": archive_size,
        "extension_type": extension_type,
        "detected_type": detected_type,
        "policy_version": policy["version"],
        "manifest_truncated_by_member_limit": manifest_truncated,
        "members": [member.to_payload() for member in members],
        "package_metadata": package_metadata.to_payload() if package_metadata else None,
        "risk_flags": [risk.to_payload() for risk in risks],
    }
    manifest_digest = canonical_digest(manifest_payload)
    return {
        "status": "completed" if not inspect_error else "blocked",
        "archive_sha256": archive_sha256,
        "archive_size_bytes": archive_size,
        "extension_type": extension_type,
        "detected_type": detected_type,
        "extension_content_match": extension_type == detected_type,
        "descriptor": descriptor,
        "members": members,
        "member_count": len(members),
        "manifest_truncated": manifest_truncated,
        "directory_count": directory_count,
        "projected_uncompressed_bytes": projected,
        "largest_member_bytes": largest,
        "nested_archive_count": nested_count,
        "compression_ratio": round(projected / max(1, archive_size), 3),
        "encrypted": any(member.is_encrypted for member in members),
        "risk_flags": risks,
        "risk_counts": dict(sorted(risk_counts.items())),
        "package_metadata": package_metadata,
        "manifest_digest": manifest_digest,
        "manifest_payload": manifest_payload,
        "policy_version": policy["version"],
        "tool_used": tool_used,
        "blocked_reason": inspect_error,
        "warnings": list(descriptor.notes)
        + (["Manifest scanning stopped after the configured member-count boundary was proven exceeded."] if manifest_truncated else []),
    }


__all__ = (
    "ArchiveInspectionError",
    "canonical_digest",
    "hash_file",
    "inspect_archive_path",
)
