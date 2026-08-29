"""Adapter router for governed Codev file stewardship."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.api.coding_code_language_adapter import summarize_code_file
from app.api.coding_data_adapter_service import inspect_data_path
from app.api.coding_document_adapter_service import extract_document_preview
from app.api.coding_delimited_data_adapter import summarize_delimited_data
from app.api.coding_file_type_registry import CodingFileTypeDescriptor, detect_file_type
from app.api.coding_media_adapter_service import inspect_media_path
from app.api.coding_archive_inspection_service import inspect_archive_path
from app.api.coding_visual_adapter_service import inspect_visual_path
from app.api.coding_markdown_adapter import summarize_markdown
from app.api.coding_markup_adapter import summarize_markup
from app.api.coding_secret_scan_service import redact_secret_lines, scan_preview_for_secrets
from app.api.coding_structured_data_adapter import summarize_structured_data, validate_structured_text
from app.api.coding_text_file_adapter import TextFileTooLargeError, TextPreview, build_text_preview


BIDI_OR_CONTROL_MARKERS = {
    "\u202a": "left-to-right embedding",
    "\u202b": "right-to-left embedding",
    "\u202c": "pop directional formatting",
    "\u202d": "left-to-right override",
    "\u202e": "right-to-left override",
    "\u2066": "left-to-right isolate",
    "\u2067": "right-to-left isolate",
    "\u2068": "first strong isolate",
    "\u2069": "pop directional isolate",
}


@dataclass(frozen=True)
class CodingFileAdapterPreview:
    descriptor: CodingFileTypeDescriptor
    text_preview: TextPreview | None
    parse_status: str
    parse_summary: dict[str, Any]
    content_preview: str | None
    secret_scan_findings: list[str]
    redactions: list[str]
    blocked_reason: str | None = None


def build_adapter_preview(
    path: Path,
    *,
    max_bytes: int,
    max_lines: int,
    max_file_bytes: int = 1024 * 1024,
) -> CodingFileAdapterPreview:
    raw_sample: bytes | None = None
    if path.exists() and path.is_file():
        with path.open("rb") as stream:
            raw_sample = stream.read(4096)
    descriptor = detect_file_type(path, raw_sample)
    if not descriptor.readable:
        blocked_reason = (
            "binary_or_unsupported_file"
            if descriptor.type_id == "binary"
            else "file_type_not_readable"
        )
        return CodingFileAdapterPreview(
            descriptor=descriptor,
            text_preview=None,
            parse_status="blocked",
            parse_summary={},
            content_preview=None,
            secret_scan_findings=[],
            redactions=[],
            blocked_reason=blocked_reason,
        )

    if descriptor.adapter == "document":
        document_preview = extract_document_preview(
            path,
            max_chars=min(max_bytes, descriptor.max_preview_bytes),
            max_tables=8,
            max_rows=20,
        )
        if document_preview.blocked_reason:
            return CodingFileAdapterPreview(
                descriptor=descriptor,
                text_preview=None,
                parse_status="blocked",
                parse_summary=document_preview.summary(),
                content_preview=None,
                secret_scan_findings=[],
                redactions=document_preview.redactions,
                blocked_reason=document_preview.blocked_reason,
            )
        return CodingFileAdapterPreview(
            descriptor=descriptor,
            text_preview=None,
            parse_status=document_preview.status,
            parse_summary=document_preview.summary(),
            content_preview=document_preview.text_preview,
            secret_scan_findings=document_preview.secret_scan_findings,
            redactions=document_preview.redactions,
        )

    if descriptor.adapter == "data":
        data_preview = inspect_data_path(path)
        if data_preview.blocked_reason:
            return CodingFileAdapterPreview(
                descriptor=descriptor,
                text_preview=None,
                parse_status="blocked",
                parse_summary=data_preview.to_payload(file_label=path.name, relative_path=path.name, path_hash=None),
                content_preview=None,
                secret_scan_findings=[],
                redactions=[],
                blocked_reason=data_preview.blocked_reason,
            )
        summary = data_preview.to_payload(file_label=path.name, relative_path=path.name, path_hash=None)
        return CodingFileAdapterPreview(
            descriptor=descriptor,
            text_preview=None,
            parse_status=data_preview.status,
            parse_summary=summary,
            content_preview=str(summary.get("preview") or summary.get("schema_summary") or summary.get("metadata") or "")[:4000],
            secret_scan_findings=[],
            redactions=[f"{data_preview.redaction_count} secret-like sample values redacted."] if data_preview.redaction_count else [],
        )

    if descriptor.adapter == "visual":
        visual_preview = inspect_visual_path(path)
        if visual_preview.get("blocked_reason"):
            return CodingFileAdapterPreview(
                descriptor=descriptor,
                text_preview=None,
                parse_status="blocked",
                parse_summary=visual_preview,
                content_preview=None,
                secret_scan_findings=[],
                redactions=[],
                blocked_reason=str(visual_preview.get("blocked_reason")),
            )
        metadata = visual_preview.get("metadata") or {}
        privacy = visual_preview.get("exif_privacy") or {}
        summary_parts = [
            f"Visual file: {descriptor.label}.",
            f"Status: {visual_preview.get('status')}.",
        ]
        width = metadata.get("width")
        height = metadata.get("height")
        if width and height:
            summary_parts.append(f"Dimensions: {width} x {height}.")
        if privacy.get("exif_present"):
            summary_parts.append("EXIF metadata is present; precise GPS is not exposed.")
        if visual_preview.get("svg_safety"):
            summary_parts.append("SVG preview is sanitized before rendering.")
        if visual_preview.get("warnings"):
            summary_parts.append("Warnings: " + "; ".join(str(item) for item in visual_preview.get("warnings", [])[:4]))
        return CodingFileAdapterPreview(
            descriptor=descriptor,
            text_preview=None,
            parse_status=str(visual_preview.get("status") or "metadata_only"),
            parse_summary=visual_preview,
            content_preview=" ".join(summary_parts)[:4000],
            secret_scan_findings=[],
            redactions=[],
        )

    if descriptor.adapter == "media":
        media_preview = inspect_media_path(path)
        if media_preview.get("blocked_reason"):
            return CodingFileAdapterPreview(
                descriptor=descriptor,
                text_preview=None,
                parse_status="blocked",
                parse_summary=media_preview,
                content_preview=None,
                secret_scan_findings=[],
                redactions=[],
                blocked_reason=str(media_preview.get("blocked_reason")),
            )
        audio = media_preview.get("audio") or {}
        video = media_preview.get("video") or {}
        parts = [
            f"Media file: {descriptor.label}.",
            f"Duration: {media_preview.get('duration_seconds')} seconds.",
            f"Container: {media_preview.get('container') or 'unknown'}.",
        ]
        if audio.get("codec"):
            parts.append(f"Audio codec: {audio['codec']}.")
        if video.get("codec"):
            parts.append(f"Video codec: {video['codec']}.")
        if any(bool(value) for value in (media_preview.get("privacy_flags") or {}).values()):
            parts.append("Privacy-sensitive embedded tags are present; their values are not exposed.")
        return CodingFileAdapterPreview(
            descriptor=descriptor,
            text_preview=None,
            parse_status=str(media_preview.get("status") or "metadata_only"),
            parse_summary=media_preview,
            content_preview=" ".join(parts)[:4000],
            secret_scan_findings=[],
            redactions=[],
        )

    if descriptor.adapter == "archive":
        archive_preview = inspect_archive_path(path)
        summary = {
            key: value
            for key, value in archive_preview.items()
            if key not in {"manifest_payload"}
        }
        summary["descriptor"] = archive_preview["descriptor"].to_payload()
        summary["members"] = [member.to_payload() for member in archive_preview["members"][:200]]
        summary["risk_flags"] = [risk.to_payload() for risk in archive_preview["risk_flags"]]
        if archive_preview["package_metadata"]:
            summary["package_metadata"] = archive_preview["package_metadata"].to_payload()
        parts = [
            f"Archive/container: {archive_preview['detected_type']}.",
            f"Members: {archive_preview['member_count']}.",
            f"Projected bytes: {archive_preview['projected_uncompressed_bytes']}.",
            f"Risk flags: {sum(archive_preview['risk_counts'].values())}.",
            "Contents were not extracted, opened, executed, imported, installed, or trusted.",
        ]
        return CodingFileAdapterPreview(
            descriptor=descriptor,
            text_preview=None,
            parse_status=str(archive_preview["status"]),
            parse_summary=summary,
            content_preview=" ".join(parts),
            secret_scan_findings=[],
            redactions=[],
            blocked_reason=archive_preview["blocked_reason"] if archive_preview["status"] == "blocked" else None,
        )

    try:
        preview = build_text_preview(
            path,
            max_bytes=min(max_bytes, descriptor.max_preview_bytes),
            max_lines=max_lines,
            max_file_bytes=max_file_bytes,
        )
    except TextFileTooLargeError as exc:
        return CodingFileAdapterPreview(
            descriptor=descriptor,
            text_preview=None,
            parse_status="blocked",
            parse_summary={"size_bytes": exc.size_bytes, "max_file_bytes": exc.max_file_bytes},
            content_preview=None,
            secret_scan_findings=[],
            redactions=[],
            blocked_reason="text_file_too_large",
        )
    if preview.binary_detected:
        return CodingFileAdapterPreview(
            descriptor=detect_file_type(path, raw_sample),
            text_preview=preview,
            parse_status="blocked",
            parse_summary={},
            content_preview=None,
            secret_scan_findings=[],
            redactions=[],
            blocked_reason="binary_or_unsupported_file",
        )

    content = preview.preview_text
    findings = scan_preview_for_secrets(content)
    redactions: list[str] = []
    if findings:
        content = redact_secret_lines(content)
        redactions.append("Potential secret lines were redacted from preview.")
    bidi_markers = sorted(label for marker, label in BIDI_OR_CONTROL_MARKERS.items() if marker in content)
    if bidi_markers:
        redactions.append("Bidirectional Unicode control markers detected: " + ", ".join(bidi_markers))

    parse_summary: dict[str, Any] = {}
    if descriptor.adapter == "code":
        parse_summary = summarize_code_file(descriptor, content)
        parse_summary.setdefault("parse_status", "metadata_only")
    elif descriptor.adapter == "structured_data":
        parse_summary = summarize_structured_data(descriptor, content)
    elif descriptor.adapter == "markdown":
        parse_summary = summarize_markdown(content)
    elif descriptor.adapter == "delimited_data":
        parse_summary = summarize_delimited_data(content, delimiter="\t" if descriptor.type_id == "tsv_data" else ",")
    elif descriptor.adapter == "markup":
        parse_summary = summarize_markup(content, language_id=descriptor.language_id)
    else:
        parse_summary = {"parse_status": "metadata_only"}

    return CodingFileAdapterPreview(
        descriptor=descriptor,
        text_preview=preview,
        parse_status=str(parse_summary.get("parse_status") or "metadata_only"),
        parse_summary=parse_summary,
        content_preview=content,
        secret_scan_findings=findings,
        redactions=redactions,
    )


def validate_patch_for_descriptor(
    descriptor: CodingFileTypeDescriptor,
    *,
    new_text: str | None = None,
) -> tuple[bool, str | None]:
    if not descriptor.patchable or descriptor.adapter == "blocked":
        return False, "file_type_not_patchable"
    if descriptor.secret_sensitive and descriptor.type_id != "env_example":
        return False, "secret_sensitive_file_blocked"
    if new_text is not None and descriptor.adapter == "structured_data":
        return validate_structured_text(descriptor, new_text)
    return True, None


def capability_flags(descriptor: CodingFileTypeDescriptor) -> dict[str, bool]:
    return {
        "readable": descriptor.readable,
        "writable": descriptor.writable,
        "patchable": descriptor.patchable,
        "creatable": descriptor.creatable,
        "deletable": descriptor.deletable,
        "renameable": descriptor.renameable,
    }


def risk_flags(descriptor: CodingFileTypeDescriptor) -> dict[str, bool]:
    return {
        "secret_sensitive": descriptor.secret_sensitive,
        "generated_sensitive": descriptor.generated_sensitive,
        "lockfile": descriptor.lockfile,
        "executable_sensitive": descriptor.executable_sensitive,
    }


__all__ = (
    "BIDI_OR_CONTROL_MARKERS",
    "CodingFileAdapterPreview",
    "build_adapter_preview",
    "capability_flags",
    "risk_flags",
    "validate_patch_for_descriptor",
)
