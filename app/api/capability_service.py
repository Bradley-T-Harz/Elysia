"""
Capability-truth service organ for the Elysia local API bridge.

This module centralizes the qualified stable v1.0 capability catalog so the route layer does
not hardcode a messy blob and the UI can read one honest local truth source for
what Elysia actually exposes right now.

This file should stay narrow:
- small implementation-truth checks
- capability entry assembly
- capability catalog assembly
- standard response-envelope wrapping

It must not:
- become a second runtime
- become governance logic
- perform health checks
- read raw logs
- infer capability truth from the UI
- blur planned and unavailable
- blur inactive and unknown
"""

from __future__ import annotations
from datetime import datetime, timezone

import importlib
import logging
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.install.paths import resolve_elysia_paths

from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.status import (
    CapabilityCatalogData,
    CapabilityCatalogState,
    CapabilityEntry,
    CapabilityGroup,
)

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"


def _utc_now_iso() -> str:
    """
    Return the current UTC timestamp in compact API-envelope style.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_request_id(prefix: str = "req") -> str:
    """
    Create a compact request identifier for envelope use.
    """
    return f"{prefix}_{uuid4().hex[:16]}"


def _import_optional(module_path: str) -> tuple[Any | None, str | None]:
    """
    Attempt to import one module without throwing.
    """
    try:
        return importlib.import_module(module_path), None
    except Exception as exc:
        return None, str(exc)


def _module_attr_is_callable(module_path: str, attr_name: str) -> bool:
    """
    Determine whether one imported module exposes a callable attribute.
    """
    module, _ = _import_optional(module_path)
    if module is None:
        return False

    candidate = getattr(module, attr_name, None)
    return callable(candidate)


def _module_attr_exists(module_path: str, attr_name: str) -> bool:
    """
    Determine whether one imported module exposes a named attribute.
    """
    module, _ = _import_optional(module_path)
    if module is None:
        return False

    return hasattr(module, attr_name)


def _chat_send_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for the governed chat-send path.
    """
    route_ready = _module_attr_exists("app.api.routes.chat", "router")
    bridge_ready = _module_attr_is_callable(
        "app.api.runtime_bridge",
        "send_chat_request",
    )

    if route_ready and bridge_ready:
        return CapabilityState.LIVE, []

    if route_ready and not bridge_ready:
        return CapabilityState.UNAVAILABLE, [
            "Chat route exists, but the runtime bridge is not currently callable.",
        ]

    return CapabilityState.PLANNED, [
        "Main governed chat-send path is not fully wired yet.",
    ]


def _conversation_metadata_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for compact conversation metadata surfaces.

    This capability is now considered live when the shared metadata schema, the
    local conversation service, and the standalone conversations serving surface
    are all present.
    """
    schema_ready = _module_attr_exists(
        "app.api.schemas.conversation",
        "ConversationMetadata",
    )
    service_ready = _module_attr_is_callable(
        "app.api.conversation_service",
        "list_conversations",
    )
    route_ready = _module_attr_exists(
        "app.api.routes.conversations",
        "router",
    )

    if schema_ready and service_ready and route_ready:
        return CapabilityState.LIVE, []

    if schema_ready and (service_ready or route_ready):
        return CapabilityState.DEGRADED, [
            "Conversation metadata foundations exist, but the local serving path is only partially wired.",
        ]

    if schema_ready:
        return CapabilityState.PLANNED, [
            "Shared conversation metadata schema exists, but the local serving surface is not yet fully wired.",
        ]

    return CapabilityState.UNKNOWN, [
        "Conversation metadata implementation truth is not yet confirmed.",
    ]


def _conversation_history_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for persisted conversation list/thread serving.

    This capability tracks read-only conversation history/list transport, distinct
    from compact metadata shape alone.
    """
    list_schema_ready = _module_attr_exists(
        "app.api.schemas.conversation_history",
        "ConversationListResponseData",
    )
    thread_schema_ready = _module_attr_exists(
        "app.api.schemas.conversation_history",
        "ConversationThreadResponseData",
    )
    list_service_ready = _module_attr_is_callable(
        "app.api.conversation_service",
        "list_conversations",
    )
    thread_service_ready = _module_attr_is_callable(
        "app.api.conversation_service",
        "get_conversation_thread",
    )
    route_ready = _module_attr_exists(
        "app.api.routes.conversations",
        "router",
    )

    if (
        list_schema_ready
        and thread_schema_ready
        and list_service_ready
        and thread_service_ready
        and route_ready
    ):
        return CapabilityState.LIVE, []

    if (
        list_schema_ready
        or thread_schema_ready
        or list_service_ready
        or thread_service_ready
        or route_ready
    ):
        return CapabilityState.DEGRADED, [
            "Conversation history/list foundations exist, but the local serving path is only partially wired.",
        ]

    return CapabilityState.PLANNED, [
        "Conversation history/list serving surface is designed but not yet wired.",
    ]


def _status_runtime_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for the runtime-status surface.
    """
    service_ready = _module_attr_is_callable(
        "app.api.status_service",
        "get_runtime_status",
    )
    if service_ready:
        return CapabilityState.LIVE, []

    return CapabilityState.UNAVAILABLE, [
        "Runtime-status service should exist, but is not currently callable.",
    ]


def _install_profile_runtime_state() -> tuple[CapabilityState, list[str]]:
    """Determine whether the read-only Pass 5 profile resolver is wired."""
    schema_ready = _module_attr_exists(
        "app.install.schemas",
        "InstallProfileStatusData",
    )
    service_ready = _module_attr_is_callable(
        "app.install.profile_service",
        "get_install_profile_status",
    )
    route_ready = _module_attr_exists("app.api.routes.status", "router")

    if schema_ready and service_ready and route_ready:
        return CapabilityState.LIVE, []
    if schema_ready or service_ready or route_ready:
        return CapabilityState.DEGRADED, [
            "Install-profile runtime truth is only partially wired.",
        ]
    return CapabilityState.PLANNED, [
        "Install-profile runtime truth is not wired.",
    ]


def _status_health_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for the health-status surface.
    """
    service_ready = _module_attr_is_callable(
        "app.api.status_service",
        "get_health_status",
    )
    if service_ready:
        return CapabilityState.LIVE, []

    return CapabilityState.UNAVAILABLE, [
        "Health-status service should exist, but is not currently callable.",
    ]


def _status_capabilities_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for the capability-catalog surface.
    """
    service_ready = _module_attr_is_callable(
        "app.api.capability_service",
        "get_capabilities_status",
    )
    if service_ready:
        return CapabilityState.LIVE, []

    return CapabilityState.UNAVAILABLE, [
        "Capability catalog service should exist, but is not currently callable.",
    ]


def _governance_state_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for the governance-state surface.
    """
    service_ready = _module_attr_is_callable(
        "app.api.governance_service",
        "get_governance_state",
    )
    if service_ready:
        return CapabilityState.LIVE, []

    return CapabilityState.UNAVAILABLE, [
        "Governance-state service should exist, but is not currently callable.",
    ]


def _governance_mutation_contract_state() -> tuple[CapabilityState, list[str]]:
    """Determine whether the exact fail-closed Governance change contract exists."""
    required = (
        "plan_governance_change",
        "apply_governance_change",
        "restore_governance_change",
    )
    if all(
        _module_attr_is_callable("app.api.governance_service", function_name)
        for function_name in required
    ):
        return CapabilityState.LIVE, [
            "Pass 3 contract is live and local; current production writable control count is zero."
        ]

    return CapabilityState.UNAVAILABLE, [
        "Exact Governance plan/apply/restore service contracts are incomplete."
    ]


def _approval_resolve_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for the approval-resolution surface.
    """
    service_ready = _module_attr_is_callable(
        "app.api.governance_service",
        "resolve_approval_request",
    )
    if service_ready:
        return CapabilityState.LIVE, []

    return CapabilityState.UNAVAILABLE, [
        "Approval-resolution service should exist, but is not currently callable.",
    ]


def _request_summary_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for the request-summary surface.
    """
    service_ready = _module_attr_is_callable(
        "app.api.request_trace_service",
        "get_request_summary",
    )
    if service_ready:
        return CapabilityState.LIVE, []

    return CapabilityState.UNAVAILABLE, [
        "Request-summary service should exist, but is not currently callable.",
    ]


def _file_ingestion_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for local file ingestion.

    This tracks explicit user-selected local file ingest. It must not imply
    cloud parsing, OCR, JavaScript execution, link fetching, memory promotion,
    outward sharing, or broad directory access.
    """
    schema_ready = _module_attr_exists(
        "app.api.schemas.files",
        "FileIngestResult",
    )
    service_ready = _module_attr_is_callable(
        "app.api.file_ingest_service",
        "attach_file",
    )
    route_ready = _module_attr_exists(
        "app.api.routes.files",
        "router",
    )

    pypdf_ready = _module_attr_exists("pypdf", "PdfReader")
    pdfplumber_ready = _module_attr_exists("pdfplumber", "open")
    pdf_ready = pypdf_ready or pdfplumber_ready
    docx_ready = _module_attr_exists("docx", "Document")
    openpyxl_ready = _module_attr_exists("openpyxl", "load_workbook")

    pdf_state = (
        "available via pypdf"
        if pypdf_ready
        else "available via pdfplumber"
        if pdfplumber_ready
        else "unavailable until pypdf or pdfplumber is installed"
    )
    docx_state = (
        "available via python-docx"
        if docx_ready
        else "unavailable until python-docx is installed"
    )
    xlsx_state = (
        "available via openpyxl"
        if openpyxl_ready
        else "unavailable until openpyxl is installed"
    )

    if schema_ready and service_ready and route_ready:
        optional_parser_warning = []
        if not pdf_ready:
            optional_parser_warning.append("PDF parser dependency is missing.")
        if not docx_ready:
            optional_parser_warning.append("DOCX parser dependency is missing.")
        if not openpyxl_ready:
            optional_parser_warning.append("XLSX parser dependency is missing.")

        state = CapabilityState.LIVE
        if optional_parser_warning:
            state = CapabilityState.DEGRADED

        return state, [
            "Local TXT/Markdown/JSON/saved HTML/PDF/DOCX text attachment plus CSV/XLSX file ingestion is wired through /files/attach.",
            "PDF text extraction is dependency-gated by pypdf or pdfplumber; current PDF parser state: "
            f"{pdf_state}.",
            "DOCX text extraction is dependency-gated by python-docx; current DOCX parser state: "
            f"{docx_state}.",
            "CSV uses local stdlib summary support. XLSX summary support is dependency-gated by openpyxl; current XLSX parser state: "
            f"{xlsx_state}.",
            "Saved HTML is parsed as local text only; scripts are not executed and links/resources are not fetched.",
            "Attached files remain request-scoped context or bounded data inputs. They are not promoted into memory and are not shared outward by default.",
            "No cloud parsing, OCR, JavaScript execution, link fetching, directory crawling, broad notebook behavior, or image/vision/OCR support is implied.",
            "Image attachment, OCR, and vision parsing remain planned/not live until a separate local vision/OCR organ is built.",
            *optional_parser_warning,
        ]

    if schema_ready and (service_ready or route_ready):
        return CapabilityState.DEGRADED, [
            "File-ingestion foundations exist, but the local attach path is only partially wired.",
            "Attached files must remain explicit user-selected inputs and must not become memory by default.",
        ]

    if schema_ready:
        return CapabilityState.PLANNED, [
            "File-ingestion schemas exist, but the local attach route is not yet live.",
        ]

    return CapabilityState.PLANNED, [
        "Local file-ingestion v0 is planned but not yet wired.",
    ]


def _file_context_retrieval_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine whether parsed attached files can be used as bounded request context.

    This is separate from file ingestion because a file can be attached without
    being usable in a governed response. This capability must never imply memory
    promotion, web research sharing, raw path disclosure, or raw full-file dumps.
    """
    context_summary_ready = _module_attr_is_callable(
        "app.api.file_ingest_service",
        "get_file_context_summary",
    )
    context_packet_ready = _module_attr_is_callable(
        "app.api.file_ingest_service",
        "build_attached_file_context_packet",
    )
    schema_ready = _module_attr_exists(
        "app.api.schemas.files",
        "FileContextSummary",
    )

    if schema_ready and context_summary_ready and context_packet_ready:
        return CapabilityState.LIVE, [
            "Parsed attached-file chunks can be selected as bounded local request context.",
            "Attached files are not memory; memory_promotion_allowed remains false by default.",
            "Attached file contents are not shared outward by default and must not be sent to SearXNG or other public research tools without a separate explicit public-safe query boundary.",
            "Context summaries expose file id, display name, kind, parser, chunk counts, and bounded excerpts, not raw absolute source paths.",
            "Large files are bounded through chunk selection rather than unbounded full-file prompt stuffing.",
        ]

    if schema_ready and (context_summary_ready or context_packet_ready):
        return CapabilityState.DEGRADED, [
            "Attached-file context foundations exist, but request-context packet support is only partially wired.",
        ]

    return CapabilityState.PLANNED, [
        "Attached-file context retrieval is planned but not yet wired.",
    ]


def _media_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine truthful metadata-only audio/video stewardship readiness."""
    registry_ready = _module_attr_is_callable(
        "app.api.coding_media_type_registry", "media_registry_payload"
    )
    inspect_ready = _module_attr_is_callable(
        "app.api.coding_media_service", "inspect_governed_media"
    )
    thumbnail_ready = _module_attr_is_callable(
        "app.api.coding_media_service", "thumbnail_governed_media"
    )
    route_ready = _module_attr_exists("app.api.routes.coding_media", "router")
    ffprobe_ready = _module_attr_is_callable(
        "app.api.coding_media_adapter_service", "inspect_media_path"
    )
    notes = [
        "WAV, MP3, FLAC, OGG, M4A, MP4, MOV, MKV, and WebM are recognized for bounded local metadata inspection.",
        "Video thumbnails use one fixed local ffmpeg operation; raw media and full ffprobe JSON are never written to central trace.",
        "The base media lane remains read-only. Governed STT and non-cloning TTS are separate exact-approved local worker routes.",
        "Transcoding, media mutation, voice cloning, and production image/video generation remain unavailable.",
    ]
    if registry_ready and inspect_ready and thumbnail_ready and route_ready and ffprobe_ready:
        from app.api.coding_media_adapter_service import media_dependency_health

        health = media_dependency_health()
        if health["ffprobe"]["available"] and health["ffmpeg"]["available"]:
            return CapabilityState.LIVE, notes
        return CapabilityState.DEGRADED, notes + [
            "The governed source path is present, but ffprobe and/or ffmpeg is unavailable in the active runtime environment.",
        ]
    if registry_ready or inspect_ready or thumbnail_ready or route_ready:
        return CapabilityState.DEGRADED, notes + [
            "Media stewardship foundations are only partially wired.",
        ]
    return CapabilityState.PLANNED, [
        "Metadata-only audio/video stewardship is planned but not wired.",
    ]


def _coding_file_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine governed Chunk 1 file stewardship source truth."""
    registry_ready = _module_attr_is_callable("app.api.coding_file_type_registry", "registry_payload")
    preview_ready = _module_attr_is_callable("app.api.coding_file_service", "read_selected_file_preview")
    plan_ready = _module_attr_is_callable("app.api.coding_file_operation_service", "plan_file_operation")
    apply_ready = _module_attr_is_callable("app.api.coding_file_operation_service", "execute_file_operation")
    route_ready = all(
        _module_attr_exists(module, "router")
        for module in (
            "app.api.routes.coding_file_types",
            "app.api.routes.coding_files",
            "app.api.routes.coding_file_operations",
        )
    )
    notes = [
        "Registered text, code, config, manifest, Markdown, markup, and delimited files receive bounded local type and preview truth.",
        "Real .env files, keys, secret-looking paths, private runtime paths, binary content, and escaping symlinks are blocked before preview or mutation.",
        "Writes require a server-issued exact, expiring, one-time approval bound to workspace, files, source hash, plan hash, and mutation class.",
        "File stewardship does not grant shell, package-manager, Docker, SQL-execution, Git-mutation, cloud-upload, or autonomous-loop authority.",
    ]
    checks = (registry_ready, preview_ready, plan_ready, apply_ready, route_ready)
    if all(checks):
        return CapabilityState.LIVE, notes
    if any(checks):
        return CapabilityState.DEGRADED, notes + ["Chunk 1 file stewardship foundations are only partially wired."]
    return CapabilityState.PLANNED, ["Governed coding file stewardship is planned but not wired."]


def _document_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine governed Chunk 2 document stewardship source truth."""
    registry_ready = _module_attr_is_callable("app.api.coding_document_type_registry", "document_registry_payload")
    inspect_ready = _module_attr_is_callable("app.api.coding_document_adapter_service", "inspect_document")
    extract_ready = _module_attr_is_callable("app.api.coding_document_adapter_service", "extract_document_preview")
    edit_ready = _module_attr_is_callable("app.api.coding_document_edit_service", "plan_document_edit")
    export_ready = _module_attr_is_callable("app.api.coding_document_export_service", "plan_document_export")
    route_ready = _module_attr_exists("app.api.routes.coding_documents", "router")
    notes = [
        "PDF, DOCX, XLSX, PPTX, ODT, ODS, and ODP use format-specific bounded local inspection and extraction with per-adapter dependency truth.",
        "Macro-enabled and legacy Office formats are blocked; macros, formulas, embedded scripts/media, and external relationships are never executed or fetched.",
        "Stable edits and exports require exact approval and source/plan hash validation; PDF and unstable operations prefer derived local copies.",
        "Full extracted document text and private absolute paths are excluded from central audit records.",
    ]
    checks = (registry_ready, inspect_ready, extract_ready, edit_ready, export_ready, route_ready)
    if all(checks):
        return CapabilityState.LIVE, notes
    if any(checks):
        return CapabilityState.DEGRADED, notes + ["Chunk 2 document stewardship foundations are only partially wired."]
    return CapabilityState.PLANNED, ["Governed document stewardship is planned but not wired."]


def _science_data_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine governed Chunk 3 science/data stewardship source truth."""
    registry_ready = _module_attr_is_callable("app.api.coding_data_type_registry", "data_registry_payload")
    inspect_ready = _module_attr_is_callable("app.api.coding_data_adapter_service", "inspect_data_path")
    preview_ready = _module_attr_is_callable("app.api.coding_data_adapter_service", "preview_data_path")
    edit_ready = _module_attr_is_callable("app.api.coding_data_edit_service", "plan_data_edit")
    export_ready = _module_attr_is_callable("app.api.coding_data_export_service", "plan_data_export")
    route_ready = _module_attr_exists("app.api.routes.coding_data", "router")
    notes = [
        "CSV/TSV, JSONL, columnar, geospatial, raster, multidimensional, and Zarr formats receive bounded adapter-specific metadata and preview truth.",
        "Stable data mutations and derived exports are advertised only where a format-correct adapter exists and remain exact-approved, backed up or transactional, and audited.",
        "SQLite, DuckDB, and ambiguous .db files are handed to DatabaseForge; row preview, arbitrary SQL, export, repair, and mutation are unavailable by design.",
        "Remote stores, external links, unbounded full loads, cloud upload, and private geolocation disclosure are not authorized by this capability.",
    ]
    checks = (registry_ready, inspect_ready, preview_ready, edit_ready, export_ready, route_ready)
    if all(checks):
        return CapabilityState.LIVE, notes
    if any(checks):
        return CapabilityState.DEGRADED, notes + ["Chunk 3 science/data stewardship foundations are only partially wired."]
    return CapabilityState.PLANNED, ["Governed science/data stewardship is planned but not wired."]


def _visual_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine governed Chunk 4 visual stewardship source truth."""
    registry_ready = _module_attr_is_callable("app.api.coding_visual_type_registry", "visual_registry_payload")
    inspect_ready = _module_attr_is_callable("app.api.coding_visual_adapter_service", "inspect_visual_path")
    preview_ready = _module_attr_is_callable("app.api.coding_visual_adapter_service", "preview_visual_path")
    edit_ready = _module_attr_is_callable("app.api.coding_image_edit_service", "plan_visual_edit")
    export_ready = _module_attr_is_callable("app.api.coding_visual_export_service", "plan_visual_export")
    route_ready = _module_attr_exists("app.api.routes.coding_visual", "router")
    notes = [
        "PNG, JPEG, WebP, GIF, BMP, TIFF, and SVG receive bounded local metadata/preview truth with EXIF privacy and parser limits.",
        "OCR and semantic analysis are explicit-approval local actions; precise GPS, raw pixels, and full OCR text are excluded from central audit.",
        "SVG scripts, event handlers, entities, and external references are removed or blocked before any local render path.",
        "Visual edits and exports preserve the source and write only exact-approved derived local copies; cloud vision/upload is disabled.",
    ]
    checks = (registry_ready, inspect_ready, preview_ready, edit_ready, export_ready, route_ready)
    if all(checks):
        return CapabilityState.LIVE, notes
    if any(checks):
        return CapabilityState.DEGRADED, notes + ["Chunk 4 visual stewardship foundations are only partially wired."]
    return CapabilityState.PLANNED, ["Governed visual stewardship is planned but not wired."]


def _archive_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine ArchiveForge source truth without treating tool presence as authority."""
    registry_ready = _module_attr_is_callable("app.api.coding_archive_type_registry", "archive_registry_payload")
    inspect_ready = _module_attr_is_callable("app.api.coding_archive_service", "inspect_archive")
    plan_ready = _module_attr_is_callable("app.api.coding_archive_service", "plan_archive_extraction")
    apply_ready = _module_attr_is_callable("app.api.coding_archive_service", "apply_archive_extraction")
    route_ready = _module_attr_exists("app.api.routes.coding_archive", "router")
    notes = [
        "ZIP, TAR, and TAR.GZ support static listing, risk reports, and exact-approved selected-file extraction into a disposable sandbox.",
        "7Z is fixed-argument list/risk only; RAR extraction remains license-sensitive lab-only.",
        "WHL, JAR, VSIX, AppImage, and DEB are code-bearing inspect-only containers; installation and execution are unavailable by design.",
        "Archive contents are never trusted, auto-opened, imported, installed, executed, merged, or written into project roots.",
    ]
    if registry_ready and inspect_ready and plan_ready and apply_ready and route_ready:
        return CapabilityState.LIVE, notes
    if registry_ready or inspect_ready or plan_ready or apply_ready or route_ready:
        return CapabilityState.DEGRADED, notes + ["ArchiveForge foundations are only partially wired."]
    return CapabilityState.PLANNED, ["Archive/container stewardship is planned but not wired."]


def _database_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine DatabaseForge source truth without granting SQL or mutation."""
    registry_ready = _module_attr_is_callable("app.api.coding_database_type_registry", "database_registry_payload")
    inspect_ready = _module_attr_is_callable("app.api.coding_database_service", "inspect_database")
    schema_ready = _module_attr_is_callable("app.api.coding_database_service", "preview_database_schema")
    route_ready = _module_attr_exists("app.api.routes.coding_database", "router")
    notes = [
        "SQLite, DuckDB, and ambiguous .db files receive local metadata and hashes without trusting extensions.",
        "SQLite/DuckDB schema preview is snapshot-first and consumes an exact, expiring, one-time approval bound to source and plan hashes.",
        "Unknown .db files are metadata-only. Rows, arbitrary SQL, export, mutation, extension loading, and external access are unavailable by design.",
        "Detailed schema names remain in private local artifacts; central audit/request trace stores only hashes, counts, policy versions, IDs, and outcomes.",
    ]
    if registry_ready and inspect_ready and schema_ready and route_ready:
        return CapabilityState.LIVE, notes
    if registry_ready or inspect_ready or schema_ready or route_ready:
        return CapabilityState.DEGRADED, notes + ["DatabaseForge foundations are only partially wired."]
    return CapabilityState.PLANNED, ["Database stewardship is planned but not wired."]


def _binary_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine BinaryForge source truth without granting active-code authority."""
    registry_ready = _module_attr_is_callable("app.api.coding_binary_type_registry", "binary_registry_payload")
    inspect_ready = _module_attr_is_callable("app.api.coding_binary_service", "inspect_binary")
    route_ready = _module_attr_exists("app.api.routes.coding_binary", "router")
    notes = [
        "PE/EXE/DLL, ELF/SO/O, Java CLASS, WASM, and unknown BIN receive bounded local static inspection.",
        "Detailed headers, sections, imports, exports, symbols, and strings remain in private local artifacts.",
        "Risk indicators are static observations, not legal clearance, antivirus certification, or malware verdicts.",
        "Execution, loading, import, install, linking, mutation, patching, and trust are unavailable; disassembly/decompilation require a future sandbox gate.",
    ]
    if registry_ready and inspect_ready and route_ready:
        return CapabilityState.LIVE, notes
    if registry_ready or inspect_ready or route_ready:
        return CapabilityState.DEGRADED, notes + ["BinaryForge foundations are only partially wired."]
    return CapabilityState.PLANNED, ["Binary stewardship is planned but not wired."]


def _engineering_stewardship_state() -> tuple[CapabilityState, list[str]]:
    """Determine EngineeringForge source truth without granting physical authority."""
    registry_ready = _module_attr_is_callable("app.api.coding_engineering_type_registry", "engineering_registry_payload")
    inspect_ready = _module_attr_is_callable("app.api.coding_engineering_service", "inspect_engineering")
    plan_ready = _module_attr_is_callable("app.api.coding_engineering_service", "plan_engineering_preview")
    apply_ready = _module_attr_is_callable("app.api.coding_engineering_service", "apply_engineering_preview")
    route_ready = _module_attr_exists("app.api.routes.coding_engineering", "router")
    notes = [
        "STL, OBJ, DAE, STEP/STP, IGES/IGS, DXF, URDF, SDF, G-code, BLEND, F3D, and F3Z receive bounded local identification and static descriptive reports.",
        "Only STL, OBJ, DXF, and G-code expose exact-approved sandbox-only SVG projections; source and project files remain unchanged.",
        "Heavy worker handoffs remain disabled because this host cannot enforce the required unprivileged namespace sandbox; ParametricForge remains experimental.",
        "Machine send, printing, CNC/serial/controller access, robot actuation, ROS/Gazebo launch, scripts/plugins, conversion/repair apply, cloud/Fusion upload, and safety certification are unavailable by design.",
    ]
    checks = (registry_ready, inspect_ready, plan_ready, apply_ready, route_ready)
    if all(checks):
        return CapabilityState.LIVE, notes
    if any(checks):
        return CapabilityState.DEGRADED, notes + ["EngineeringForge stewardship foundations are only partially wired."]
    return CapabilityState.PLANNED, ["EngineeringForge stewardship is planned but not wired."]


def _governed_media_worker_states() -> dict[str, tuple[CapabilityState, list[str]]]:
    """Return compact source-and-local-asset truth for governed media workers."""
    try:
        from app.api.media_worker_registry_service import media_worker_truth

        truth = media_worker_truth()
    except Exception as exc:
        unavailable = (CapabilityState.UNAVAILABLE, [f"Media worker truth could not be loaded: {type(exc).__name__}."])
        return {"stt": unavailable, "tts": unavailable, "image": unavailable, "video": unavailable, "voice_clone": unavailable}

    speech = truth.get("speechforge", {})
    stt_live = all(bool(speech.get(key)) for key in ("enabled", "worker_python_present", "worker_script_present", "stt_enabled", "stt_executable_present", "stt_model_present"))
    tts_live = all(bool(speech.get(key)) for key in ("enabled", "worker_python_present", "worker_script_present", "tts_enabled", "tts_model_present", "tts_voices_present"))
    image = truth.get("imageforge", {})
    video = truth.get("videoforge", {})
    image_models = list(image.get("models") or [])
    image_available = any(
        model.get("enabled_state") == "profile_gated" and model.get("local_assets_present")
        for model in image_models
    )
    video_models = list(video.get("models") or [])
    return {
        "stt": (
            CapabilityState.LIVE if stt_live else CapabilityState.DEGRADED,
            [
                "Speech-to-text runs through an isolated local Whisper.cpp worker after consent attestation and exact one-time approval.",
                "Saved transcripts are machine-generated local artifacts; raw transcript text and raw media are excluded from central audit/request trace.",
                "Only local selected files are accepted; microphone capture, URLs, cloud transcription, and automatic memory promotion are unavailable.",
            ],
        ),
        "tts": (
            CapabilityState.LIVE if tts_live else CapabilityState.DEGRADED,
            [
                "Kokoro produces local synthetic reading-voice WAV artifacts through an isolated exact-approved worker.",
                "Only catalog voices are accepted; reference-voice input and voice cloning are unavailable by design.",
                "Model/license provenance remains externally unverified, so this is local governed use rather than a production provenance claim.",
            ],
        ),
        "image": (
            CapabilityState.LIVE if image_available else CapabilityState.DEGRADED if image_models else CapabilityState.UNAVAILABLE,
            [
                "ImageForge offers one governed Creator-profile path: FLUX.1-schnell at 256×256, one step, sequential CPU offload, and one cancellable local job.",
                "The FLUX.1-schnell Apache-2.0 license was verified against official publisher sources; local safetensors remain operator-selected optional assets.",
                "Mitsua is blocked by unsafe-pickle fallback and CommonCanvas is blocked by conflicting local license metadata.",
                "Every saved image requires prompt policy, exact one-time approval, synthetic provenance, offline execution, and a profile doctor pass.",
            ],
        ),
        "video": (
            CapabilityState.DEGRADED if video_models and video.get("routes_live") is True and video.get("cancellation_supported") is True else CapabilityState.PLANNED,
            [
                "Wan 2.1 T2V 1.3B has an exact-approved, cancellable lab-only route using one fixed bounded resource profile.",
                "The lab worker is disabled by default and requires an explicit environment enablement plus lab acknowledgement.",
                "Video outputs are labeled synthetic and retain compact provenance; external license/provenance verification and sustained resource testing block production.",
            ],
        ),
        "voice_clone": (
            CapabilityState.UNAVAILABLE,
            [
                "Voice cloning, reference-voice input, and deceptive impersonation workflows are deliberately unavailable.",
            ],
        ),
    }


def _math_execution_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for bounded local math execution v0.

    This tracks only the narrow backend math execution lane:
    core math executor + execution schema + execution service + SymPy engine
    availability. It must not imply arbitrary Python, shell execution, web
    access, file mutation, notebook behavior, or mature runtime/UI routing.
    """
    executor_ready = _module_attr_is_callable(
        "core.math_executor",
        "run_math_operation",
    )
    sympy_checker_ready = _module_attr_is_callable(
        "core.math_executor",
        "is_sympy_available",
    )
    schema_ready = _module_attr_exists(
        "app.api.schemas.execution",
        "MathExecutionResult",
    )
    service_ready = _module_attr_is_callable(
        "app.api.execution_service",
        "run_math_execution",
    )

    if executor_ready and sympy_checker_ready and schema_ready and service_ready:
        math_executor_module, import_error = _import_optional("core.math_executor")

        if math_executor_module is None:
            return CapabilityState.DEGRADED, [
                "Math execution schema, service, and executor checks mostly exist, but core.math_executor could not be imported.",
                f"Import error: {import_error}",
                "This is not arbitrary Python, shell execution, web access, or file mutation.",
            ]

        try:
            sympy_available = bool(math_executor_module.is_sympy_available())
        except Exception as exc:
            return CapabilityState.DEGRADED, [
                "Math execution schema, service, and executor exist, but SymPy readiness could not be checked.",
                f"SymPy readiness check failed: {exc}",
                "This is not arbitrary Python, shell execution, web access, or file mutation.",
            ]

        if sympy_available:
            return CapabilityState.LIVE, [
                "Local SymPy-backed math execution v0 is available through the backend execution service.",
                "This is bounded local math execution only; it is not arbitrary Python, shell execution, web access, or file mutation.",
                "Runtime routing and UI trace surfacing may still be maturing.",
            ]

        return CapabilityState.DEGRADED, [
            "Math execution schema, service, and executor exist, but SymPy is not installed in the active Python environment.",
            "Install SymPy in the Elysia environment before treating math execution as fully live.",
            "This is not arbitrary Python, shell execution, web access, or file mutation.",
        ]

    if executor_ready or sympy_checker_ready or schema_ready or service_ready:
        return CapabilityState.DEGRADED, [
            "Math execution foundations exist, but the backend execution lane is only partially wired.",
            "Required pieces are core.math_executor, app.api.schemas.execution, and app.api.execution_service.",
            "This is not arbitrary Python, shell execution, web access, or file mutation.",
        ]

    return CapabilityState.PLANNED, [
        "Bounded local math execution v0 is planned but not yet wired.",
    ]



def _data_execution_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine the current truth state for bounded local data execution v0.

    This tracks the narrow read-only local table-summary lane. CSV support is
    stdlib-backed. XLSX support is local and optional, depending on openpyxl.
    It must not imply plotting, artifact rendering, arbitrary Python, shell
    execution, notebook execution, web access, file mutation, folder scanning,
    or memory promotion.
    """
    core_ready = _module_attr_is_callable(
        "core.data_executor",
        "summarize_data_file",
    )
    schema_ready = _module_attr_exists(
        "app.api.schemas.data_execution",
        "DataExecutionResult",
    )
    service_ready = _module_attr_is_callable(
        "app.api.data_execution_service",
        "run_data_execution",
    )
    context_block_ready = _module_attr_is_callable(
        "app.api.data_execution_service",
        "build_data_execution_context_block",
    )

    xlsx_module, xlsx_import_error = _import_optional("openpyxl")
    if xlsx_module is None:
        xlsx_note = (
            "XLSX inspection is dependency-gated: install openpyxl locally in the active Elysia Python environment before treating XLSX summary as available. "
            f"Current openpyxl import error: {xlsx_import_error}"
        )
    else:
        xlsx_note = (
            "Optional local openpyxl is importable, so bounded read-only XLSX first-worksheet summaries can run locally."
        )

    if core_ready and schema_ready and service_ready and context_block_ready:
        if xlsx_module is None:
            return CapabilityState.DEGRADED, [
                "Bounded local CSV data execution v0 is live through core.data_executor and app.api.data_execution_service.",
                xlsx_note,
                "Data execution is marked degraded because XLSX support is not available until openpyxl is installed locally.",
                "CSV still works. This is read-only local table summary only; it does not mean plotting, artifact rendering, arbitrary Python, shell execution, notebook execution, web access, file mutation, folder scanning, or memory promotion is live.",
            ]

        return CapabilityState.LIVE, [
            "Bounded local CSV data execution v0 is live through core.data_executor and app.api.data_execution_service.",
            xlsx_note,
            "This is read-only CSV/XLSX table summary only when dependencies allow; it does not mean plotting, artifact rendering, arbitrary Python, shell execution, notebook execution, web access, file mutation, folder scanning, or memory promotion is live.",
        ]

    if core_ready and (schema_ready or service_ready):
        return CapabilityState.DEGRADED, [
            "Data-execution foundations exist, but the API-safe service/schema path is only partially wired.",
            "Keep capability truth narrow: local table inspection is not general Python, plotting, notebook, or artifact execution.",
        ]

    if core_ready:
        return CapabilityState.PLANNED, [
            "The core data executor exists, but the API-safe data execution service is not yet live.",
        ]

    return CapabilityState.PLANNED, [
        "Bounded local data execution v0 is planned but not yet wired.",
    ]


def _bounded_public_research_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine bounded public web research truth without broad network checks.
    """
    config_path = Path("config/workers/searxng_worker.yaml")
    if not config_path.exists():
        return CapabilityState.PLANNED, [
            "SearXNG worker contract exists, but worker config is not present.",
            "No public web query path is live.",
        ]

    worker_ready = _module_attr_is_callable(
        "sandbox.searxng_worker.worker",
        "run_searxng_worker",
    )
    service_ready = _module_attr_is_callable(
        "app.api.research_service",
        "run_bounded_public_research",
    )
    route_ready = _module_attr_exists("app.api.routes.research", "router")

    try:
        from sandbox.searxng_worker.config import load_searxng_worker_config

        config = load_searxng_worker_config(config_path)
        enabled = config.service.get("enabled") is True
    except Exception as exc:
        return CapabilityState.UNAVAILABLE, [
            f"SearXNG worker config could not be loaded: {exc}",
            "No query was sent and no external boundary was crossed.",
        ]

    notes = [
        "Bounded public web research uses a local SearXNG worker, not core browsing.",
        "SearXNG service is configured for local loopback.",
        "Search boundary is the external public web for query terms.",
        "Private context is blocked; cloud search, cloud models, and page fetch are disabled.",
    ]

    if worker_ready and service_ready and route_ready and enabled:
        return CapabilityState.DEGRADED, notes + [
            "Worker, service, and route are present. Reachability is unverified until a bounded loopback search succeeds.",
        ]

    if worker_ready and service_ready and route_ready:
        return CapabilityState.INACTIVE, notes + [
            "Worker, service, and route are present, but config service.enabled is false.",
            "No query will be sent until bounded public research is explicitly enabled.",
        ]

    if worker_ready or service_ready or route_ready:
        return CapabilityState.DEGRADED, notes + [
            "Bounded public research foundations are only partially wired.",
        ]

    return CapabilityState.PLANNED, notes + [
        "Bounded public research worker is not wired yet.",
    ]


def _bounded_fetch_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine bounded public fetch truth without active network checks.
    """
    config_path = Path("config/workers/fetch_worker.yaml")
    worker_ready = _module_attr_is_callable(
        "sandbox.fetch_worker.worker",
        "run_fetch_worker",
    )
    service_ready = _module_attr_is_callable(
        "app.api.research_service",
        "run_bounded_public_fetch",
    )
    route_ready = _module_attr_exists("app.api.routes.research", "router")

    notes = [
        "Bounded fetch is explicit, approval-gated, and request-specific.",
        "It blocks private/local URLs, credentials, crawling, browser automation, login scraping, cloud models, and private context outward.",
        "Trace/UI should expose boundary truth and only bounded sanitized snippets, not raw HTML or full page text.",
    ]

    if not config_path.exists():
        return CapabilityState.PLANNED, notes + [
            "Fetch worker config is not present.",
        ]

    try:
        from sandbox.fetch_worker.config import load_fetch_worker_config

        config = load_fetch_worker_config(config_path)
        enabled = config.service.get("enabled") is True
    except Exception as exc:
        return CapabilityState.UNAVAILABLE, notes + [
            f"Fetch worker config could not be loaded: {exc}",
        ]

    if worker_ready and service_ready and route_ready and enabled:
        return CapabilityState.LIVE, notes + [
            "Worker, service, route, and config are present. Reachability is not probed by the capability service.",
        ]

    if worker_ready and service_ready and route_ready:
        return CapabilityState.INACTIVE, notes + [
            "Worker, service, and route are present, but config service.enabled is false.",
        ]

    if worker_ready or service_ready or route_ready:
        return CapabilityState.DEGRADED, notes + [
            "Bounded fetch foundations are partially wired.",
        ]

    return CapabilityState.PLANNED, notes + [
        "Bounded fetch worker is not wired yet.",
    ]


def _mode_profiles_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine whether shared mode posture config is present.

    Mode profiles are posture, not authority. They must not imply shell,
    mutation, cloud, web, private-context export, or worker power by themselves.
    """
    config_path = Path("config/modes/mode_profiles.yaml")
    if not config_path.exists():
        return CapabilityState.PLANNED, [
            "Mode profile config is planned but not present.",
            "Modes must not grant tools or bypass approval policy by themselves.",
        ]

    try:
        config_path.read_text(encoding="utf-8")
    except Exception as exc:
        return CapabilityState.UNAVAILABLE, [
            f"Mode profile config exists but could not be read: {exc}",
            "Modes must not grant tools or bypass approval policy by themselves.",
        ]

    return CapabilityState.LIVE, [
        "Mode profiles define posture, weighting, strictness, and response style.",
        "Modes do not grant tools by themselves; policy gates, autonomy, capability truth, locality truth, and model routing remain authoritative.",
    ]


def _repo_context_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine read-only selected-repo context truth.
    """
    gatherer_ready = _module_attr_is_callable(
        "core.repo_context_gatherer",
        "gather_repo_context",
    )

    if gatherer_ready:
        return CapabilityState.LIVE, [
            "Read-only selected-repo context gatherer exists for governed Coder paths.",
            "This is local selected-repo inspection only; it grants no mutation, shell, package install, git, or host-wide scanning authority.",
        ]

    return CapabilityState.PLANNED, [
        "Read-only selected-repo context gathering is planned but not callable.",
    ]


def _code_patch_plan_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine proposal-only code patch planning truth.
    """
    formatter_ready = _module_attr_is_callable(
        "core.code_patch_formatter",
        "format_code_patch_plan",
    )

    if formatter_ready:
        return CapabilityState.LIVE, [
            "Proposal-only patch planning formatter exists for governed Coder paths.",
            "Patch application is not live here; no file mutation, shell execution, git mutation, or package install authority is granted.",
        ]

    return CapabilityState.PLANNED, [
        "Proposal-only patch planning is planned but not callable.",
    ]


def _patch_application_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine approved patch application truth without mutating files.
    """
    schema_ready = _module_attr_exists("app.api.schemas.code", "PatchApplyRequest")
    service_ready = _module_attr_is_callable("app.api.code_service", "apply_approved_patch")
    worker_ready = _module_attr_is_callable("sandbox.patch_worker.worker", "run_patch_worker")
    route_ready = _module_attr_exists("app.api.routes.code", "router")

    notes = [
        "Patch application is explicit and approval-gated only.",
        "It requires exact files, exact patch hash, path guard, diff preview, rollback note, and mutation ledger truth.",
        "The worker uses Python file edits only; it does not grant shell, git, package install, or autonomous edit authority.",
    ]

    if schema_ready and service_ready and worker_ready and route_ready:
        return CapabilityState.LIVE, notes

    if schema_ready or service_ready or worker_ready or route_ready:
        return CapabilityState.DEGRADED, notes + [
            "Approved patch application foundations are partially present."
        ]

    return CapabilityState.PLANNED, [
        "Approved patch application is planned but not wired.",
    ]


def _focused_command_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine exact approved focused command execution truth.
    """
    schema_ready = _module_attr_exists(
        "app.api.schemas.code",
        "FocusedCommandRunRequest",
    )
    service_ready = _module_attr_is_callable(
        "app.api.code_service",
        "run_approved_focused_command",
    )
    worker_ready = _module_attr_is_callable(
        "sandbox.command_worker.worker",
        "run_command_worker",
    )
    route_ready = _module_attr_exists("app.api.routes.code", "router")
    notes = [
        "Focused command execution is explicit and approval-gated only.",
        "Allowed commands are narrow exact matches, currently focused tests and frontend typecheck/build.",
        "The command worker uses shell=False and records command ledger truth; broad shell remains not live.",
    ]

    if schema_ready and service_ready and worker_ready and route_ready:
        return CapabilityState.LIVE, notes

    if schema_ready or service_ready or worker_ready or route_ready:
        return CapabilityState.DEGRADED, notes + [
            "Focused command foundations are partially present."
        ]

    return CapabilityState.PLANNED, [
        "Approved focused command execution is planned but not wired.",
    ]


def _aider_worker_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine Aider worker skeleton/dry-run truth without invoking Aider.
    """
    contract_ready = Path("docs/coder/aider_worker_contract.md").exists()
    config_ready = Path("config/workers/aider_worker.yaml").exists()
    dry_run_ready = _module_attr_is_callable(
        "sandbox.aider_worker.worker",
        "run_aider_worker_dry_run",
    )

    if contract_ready and config_ready and dry_run_ready:
        return CapabilityState.DEGRADED, [
            "Aider worker contract, config, and dry-run validation skeleton exist.",
            "Aider subprocess invocation is not live in this capability state.",
            "No mutation, shell, git mutation, package install, network, or cloud model authority is granted.",
        ]

    if contract_ready or config_ready or dry_run_ready:
        return CapabilityState.DEGRADED, [
            "Aider worker foundations are partially present, but dry-run worker truth is incomplete.",
            "No mutation, shell, git mutation, package install, network, or cloud model authority is granted.",
        ]

    return CapabilityState.PLANNED, [
        "Aider worker is planned but not wired.",
        "Future use must remain selected-repo scoped, approval-gated, and never a silent autonomous editor.",
    ]


def _evidence_packets_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine evidence packet schema/verifier truth.
    """
    schema_ready = _module_attr_exists(
        "app.api.schemas.evidence",
        "ResearchEvidencePacket",
    )
    verifier_ready = _module_attr_is_callable(
        "core.evidence_verifier",
        "verify_research_ticket_payload",
    )

    if schema_ready and verifier_ready:
        return CapabilityState.LIVE, [
            "Evidence packet schemas and verifier exist for bounded research results.",
            "Evidence packets structure source evidence; Search snippets are evidence candidates, not final proof.",
        ]

    if schema_ready or verifier_ready:
        return CapabilityState.DEGRADED, [
            "Evidence packet foundations are partially present, but schema/verifier truth is incomplete.",
            "Search snippets must remain evidence candidates, not final proof.",
        ]

    return CapabilityState.PLANNED, [
        "Evidence packet schemas and verifier are planned but not present.",
    ]


def _artifact_outputs_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine local artifact output truth without broadening artifact authority.
    """
    schema_ready = _module_attr_exists(
        "app.api.schemas.artifacts",
        "ArtifactSummary",
    )
    summary_ready = _module_attr_is_callable(
        "app.api.artifact_service",
        "artifact_summary_from_record",
    )
    data_artifact_ready = _module_attr_is_callable(
        "app.api.artifact_service",
        "create_data_summary_artifact",
    )
    plot_artifact_ready = _module_attr_is_callable(
        "app.api.artifact_service",
        "create_plot_image_artifact",
    )

    if schema_ready and summary_ready and data_artifact_ready and plot_artifact_ready:
        return CapabilityState.LIVE, [
            "Local artifact summary/output schemas and service helpers exist for data summaries and plot images.",
            "Artifacts are local outputs and do not become memory by default.",
            "This does not imply a full artifact browser, raw payload exposure, shell execution, web access, or file mutation.",
        ]

    if schema_ready or summary_ready or data_artifact_ready or plot_artifact_ready:
        return CapabilityState.DEGRADED, [
            "Artifact output foundations are partially present, but the local artifact path is incomplete.",
            "Artifacts must not expose raw payloads, raw file contents, or hidden reasoning.",
        ]

    return CapabilityState.PLANNED, [
        "Artifact outputs are planned but not wired.",
    ]


def _tool_ledger_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine compact request tool-ledger truth.
    """
    schema_ready = _module_attr_exists(
        "app.api.schemas.tools",
        "ToolLedgerEntry",
    )
    trace_writer_ready = _module_attr_is_callable(
        "app.api.request_trace_service",
        "update_request_trace_ledger_snapshot",
    )

    if schema_ready and trace_writer_ready:
        return CapabilityState.LIVE, [
            "Compact request ledger schema and trace snapshot fields exist.",
            "Raw logs, journals, file contents, hidden reasoning, and raw internal payloads are not exposed.",
        ]

    if schema_ready or trace_writer_ready:
        return CapabilityState.DEGRADED, [
            "Tool-ledger foundations are partially present, but schema/trace writer truth is incomplete.",
            "Raw logs and private payloads must not be exposed.",
        ]

    return CapabilityState.PLANNED, [
        "Tool ledger is planned but not wired.",
    ]


def _identity_account_state() -> tuple[CapabilityState, list[str]]:
    """
    Determine sealed local account gate truth without reading private account data.
    """
    service_ready = all(
        _module_attr_is_callable("app.api.account_service", attr)
        for attr in (
            "get_account_state",
            "create_account",
            "login",
            "logout",
            "get_private_profile",
            "get_elysia_visible_profile",
            "select_profile_photo",
            "load_account_colors",
            "load_privacy_policy_view",
        )
    )
    route_ready = _module_attr_exists("app.api.routes.account", "router")
    schema_ready = _module_attr_exists(
        "app.api.schemas.account",
        "ElysiaVisibleProfile",
    )
    policy_ready = Path("config/policies/account_privacy.yaml").is_file()
    colors_ready = Path("config/ui/account_colors.yaml").is_file()

    if service_ready and route_ready and schema_ready and policy_ready and colors_ready:
        return CapabilityState.LIVE, [
            "Sealed local account service, routes, schemas, privacy contract, and account colors are present.",
            "Private profile fields are UI-authenticated only and are not normal Memory.",
            "Runtime receives only username/name, interests, Story, and identity-photo reference truth.",
            "Password hashes, session tokens, original photo paths, birthdate, emails, phone, socials, GitHub, and city/state are not exposed to runtime, tools, workers, traces, logs, or journals.",
        ]

    if service_ready or route_ready or schema_ready or policy_ready or colors_ready:
        return CapabilityState.DEGRADED, [
            "Identity account foundations are partially present, but the sealed account gate is incomplete.",
            "Private profile data must remain out of normal Memory and runtime context.",
        ]

    return CapabilityState.PLANNED, [
        "Sealed local account gate is planned but not wired.",
    ]


def _planned_part3_capability(
    *,
    capability_key: str,
    display_name: str,
    group: CapabilityGroup,
    summary: str,
    ui_surfaces: list[str],
    supporting_endpoint: str | None = None,
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED,
    read_only: bool = True,
    notes: list[str] | None = None,
) -> CapabilityEntry:
    """
    Build one honest Part 3 capability entry before the organ is live.

    These entries intentionally name planned organs without pretending they are
    currently executable. This lets the UI expose future power truthfully while
    keeping implementation authority in the backend.
    """
    return CapabilityEntry(
        capability_key=capability_key,
        display_name=display_name,
        group=group,
        state=CapabilityState.PLANNED,
        summary=summary,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        read_only=read_only,
        ui_surfaces=ui_surfaces,
        supporting_endpoint=supporting_endpoint,
        notes=notes
        or [
            "Part 3 organ is named in the capability catalog but is not live yet.",
            "The UI must not render this as executable until backend truth changes.",
        ],
    )


def _build_capability_entries() -> list[CapabilityEntry]:
    """
    Build the qualified stable v1.0 capability catalog entries from implementation truth.
    """
    entries: list[CapabilityEntry] = []

    semantic_impl = all(
        _module_attr_is_callable("app.cognition.semantic_projection", attr)
        for attr in ("semantic_projection_health",)
    ) and _module_attr_is_callable("app.cognition.hybrid_retrieval", "HybridMemoryRetriever")
    semantic_config_path = resolve_elysia_paths().memory_semantic_client_config_path
    semantic_configured = False
    semantic_config_invalid = False
    if semantic_impl and semantic_config_path.is_file():
        from app.cognition.semantic_projection import semantic_projection_health

        semantic_truth = semantic_projection_health(probe=False)
        semantic_configured = bool(semantic_truth.get("configured"))
        semantic_config_invalid = semantic_truth.get("state") == "degraded"
    entries.append(
        CapabilityEntry(
            capability_key="canonical_memory_hybrid_retrieval",
            display_name="Local semantic Memory retrieval",
            group=CapabilityGroup.MEMORY,
            state=(
                CapabilityState.DEGRADED if semantic_config_invalid
                else CapabilityState.LIVE if semantic_impl and semantic_configured
                else CapabilityState.INACTIVE if semantic_impl
                else CapabilityState.DEGRADED
            ),
            summary="FTS5 plus optional local Qwen/Qdrant semantic retrieval with hard authorization before ranking and canonical re-authorization afterward.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=True,
            ui_surfaces=["memory_room", "health_room", "capabilities_room", "right_drawer", "chamber"],
            supporting_endpoint="/memory/health",
            notes=[
                "Canonical SQLite Memory remains authoritative; Qdrant is a disposable normal-memory projection.",
                "Private Memory uses authenticated ephemeral retrieval and Sealed Memory never receives a persistent vector.",
                "The optional profile is explicit, authenticated, telemetry-disabled, REST-only, loopback-only, and never auto-started.",
                "FTS5 remains production-functional when the optional local profile is absent or degraded.",
            ],
        )
    )
    entries.append(
        CapabilityEntry(
            capability_key="memory_release_lifecycle",
            display_name="Cognitive memory lifecycle and portability",
            group=CapabilityGroup.MEMORY,
            state=(
                CapabilityState.LIVE
                if _module_attr_is_callable(
                    "app.memory.release_service", "MemoryReleaseService"
                )
                else CapabilityState.DEGRADED
            ),
            summary="Nine governed memory forms, Working/Hot/Warm/Cold/Archived metabolism, owner-reviewed consolidation, deterministic privacy-safe relations, encrypted portable restore, homeostasis, and exhaustive hard deletion over the canonical Memory Fabric.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NEEDED,
            read_only=False,
            ui_surfaces=[
                "memory_room", "settings_panel", "health_room",
                "capabilities_room", "requests_room", "governance_room",
                "admin_room", "right_drawer", "chamber",
            ],
            supporting_endpoint="/memory/health",
            notes=[
                "SQLite remains the sole canonical Memory writer; object, graph, lexical, semantic, and cold structures are governed bytes or rebuildable projections.",
                "Private and Sealed cold/archive bytes remain authenticated and encrypted; Sealed records never enter ordinary graph or vector indexes.",
                "Hard deletion uses an exact one-time plan and proves absence from Elysia-held canonical, projection, graph, object, cold, and managed-backup state; offline user copies remain outside Elysia's reach.",
                "Admin receives metadata-only installation/storage health and never gains user memory content authority.",
            ],
        )
    )
    entries.extend(
        [
            CapabilityEntry(
                capability_key="adaptive_cognition_governor",
                display_name="Adaptive Cognition Governor",
                group=CapabilityGroup.CORE_CHAT,
                state=CapabilityState.LIVE,
                summary="Six deterministic reasoning gears with policy-bounded escalation, early exit, model/context/tool budgets, and content-free receipts in the real cognition path.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "governance_room", "health_room", "capabilities_room", "right_drawer"],
                supporting_endpoint="/cognition/status",
                notes=["The Governor selects effort and resources; it cannot increase autonomy or bypass ownership, privacy, Internet, approval, or managed-profile ceilings."],
            ),
            CapabilityEntry(
                capability_key="heterogeneous_compute_governor",
                display_name="CPU/GPU Compute Governor",
                group=CapabilityGroup.EXECUTION,
                state=CapabilityState.LIVE,
                summary="Measured CPU/GPU arbitration, durable bounded GPU leases, interactive preemption, resource ceilings, semantic scheduling, cancellation, and CPU fallback.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["health_room", "capabilities_room", "requests_room", "right_drawer", "status"],
                supporting_endpoint="/cognition/status",
                notes=["GPU use is earned per workload; no embedding or Neurofabric workload receives a permanent reservation."],
            ),
            CapabilityEntry(
                capability_key="neurofabric_runtime_profiles",
                display_name="Neurofabric CPU / CUDA MEGA profiles",
                group=CapabilityGroup.EXECUTION,
                state=CapabilityState.LIVE,
                summary="Separate optional CPU and CUDA 13.0 PyTorch/NCPS environment contracts with doctor proof and no Torch dependency in packaged Core.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["health_room", "capabilities_room"],
                supporting_endpoint="/status/doctor",
                notes=["CUDA is never forced onto unsupported machines; the deterministic Governor remains authority and NCPS remains an unpromoted reference dependency."],
            ),
            CapabilityEntry(
                capability_key="system_emergency_stop",
                display_name="System-wide emergency stop and recovery",
                group=CapabilityGroup.GOVERNANCE,
                state=CapabilityState.LIVE,
                summary="Authenticated cooperative cancellation, prominent Desktop/keyboard/CLI stop, exact owned-process hard stop, restart recovery, Sealed relock, GPU lease revocation, and explicit reset.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["top_bar", "settings", "governance_room", "admin_room", "health_room", "status"],
                supporting_endpoint="/emergency/status",
                notes=["Stop deletes no canonical user data and does not rewrite the user’s durable preferred autonomy level."],
            ),
        ]
    )

    chat_send_state, chat_send_notes = _chat_send_state()
    entries.append(
        CapabilityEntry(
            capability_key="chat_send",
            display_name="Chat send",
            group=CapabilityGroup.CORE_CHAT,
            state=chat_send_state,
            summary="Main governed body-facing chat submission path.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=False,
            ui_surfaces=["conversations_room", "quick_invoke"],
            supporting_endpoint="/chat/send",
            notes=chat_send_notes,
        )
    )

    conversation_metadata_state, conversation_metadata_notes = _conversation_metadata_state()
    entries.append(
        CapabilityEntry(
            capability_key="conversation_metadata",
            display_name="Conversation metadata",
            group=CapabilityGroup.CORE_CHAT,
            state=conversation_metadata_state,
            summary="Compact conversation-container metadata shape for list and header surfaces.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=True,
            ui_surfaces=["conversations_room"],
            supporting_endpoint="/conversations",
            notes=conversation_metadata_notes,
        )
    )

    conversation_history_state, conversation_history_notes = _conversation_history_state()
    entries.append(
        CapabilityEntry(
            capability_key="conversation_history",
            display_name="Conversation history",
            group=CapabilityGroup.CORE_CHAT,
            state=conversation_history_state,
            summary="Read-only local conversation list and thread serving surface for persisted conversations.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=True,
            ui_surfaces=["conversations_room"],
            supporting_endpoint="/conversations/{conversation_id}",
            notes=conversation_history_notes,
        )
    )

    runtime_state, runtime_notes = _status_runtime_state()
    entries.append(
        CapabilityEntry(
            capability_key="status_runtime",
            display_name="Runtime status",
            group=CapabilityGroup.STATUS_SURFACES,
            state=runtime_state,
            summary="Runtime truth surface for active role, runtime, locality, and fallback state.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=True,
            ui_surfaces=["bottom_status_bar", "right_drawer", "governance_room"],
            supporting_endpoint="/status/runtime",
            notes=runtime_notes,
        )
    )

    health_state, health_notes = _status_health_state()
    entries.append(
        CapabilityEntry(
            capability_key="status_health",
            display_name="Health status",
            group=CapabilityGroup.STATUS_SURFACES,
            state=health_state,
            summary="Service and subsystem health inspection surface.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=True,
            ui_surfaces=["governance_room", "right_drawer", "startup_truth_surface"],
            supporting_endpoint="/status/health",
            notes=health_notes,
        )
    )

    capabilities_state, capabilities_notes = _status_capabilities_state()
    entries.append(
        CapabilityEntry(
            capability_key="status_capabilities",
            display_name="Capability catalog",
            group=CapabilityGroup.STATUS_SURFACES,
            state=capabilities_state,
            summary="Capability truth surface for what Elysia actually exposes right now.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=True,
            ui_surfaces=["governance_room", "right_drawer", "startup_truth_surface"],
            supporting_endpoint="/status/capabilities",
            notes=capabilities_notes,
        )
    )

    governance_state, governance_notes = _governance_state_state()
    entries.append(
        CapabilityEntry(
            capability_key="governance_state",
            display_name="Governance state",
            group=CapabilityGroup.GOVERNANCE,
            state=governance_state,
            summary="Governance-room state inspection and configuration truth surface.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=True,
            ui_surfaces=["governance_room", "right_drawer"],
            supporting_endpoint="/governance/state",
            notes=governance_notes,
        )
    )

    governance_mutation_state, governance_mutation_notes = (
        _governance_mutation_contract_state()
    )
    entries.append(
        CapabilityEntry(
            capability_key="governance_mutation_contract",
            display_name="Governance mutation contract",
            group=CapabilityGroup.GOVERNANCE,
            state=governance_mutation_state,
            summary=(
                "Exact fail-closed plan, approval, apply, and restore framework; "
                "no production control is currently live-editable."
            ),
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NEEDED,
            read_only=True,
            ui_surfaces=["governance_room"],
            supporting_endpoint="/governance/changes/plan",
            notes=governance_mutation_notes,
        )
    )

    install_profile_state, install_profile_notes = _install_profile_runtime_state()
    entries.extend(
        [
            CapabilityEntry(
                capability_key="desktop_settings_preferences",
                display_name="Desktop settings and local preferences",
                group=CapabilityGroup.STATUS_SURFACES,
                state=CapabilityState.LIVE,
                summary="Persistent low-risk Desktop presentation preferences, read-only release/runtime truth, reset, and allowlist-built diagnostics.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["settings_panel"],
                supporting_endpoint=None,
                notes=[
                    "Appearance, density, reduced-motion/system-motion posture, left-rail behavior, and startup room are local Desktop preferences.",
                    "Settings exposes no governance, autonomy, outbound, cloud, worker, hardware, memory, model, or profile mutation authority.",
                ],
            ),
            CapabilityEntry(
                capability_key="install_profile_manifests",
                display_name="Install profile runtime truth",
                group=CapabilityGroup.STATUS_SURFACES,
                state=install_profile_state,
                summary="Deterministic read-only Core, Workstation, Creator, and Developer profile, dependency, provider, override, and worker-readiness truth.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["settings_panel", "capabilities_room", "health_room"],
                supporting_endpoint="/status/profiles",
                notes=[
                    "The resolver uses module metadata and executable lookup only; it installs, downloads, starts, and enables nothing.",
                    "Model, worker, vault, sandbox, and isolation proof remain reserved for Pass 6 doctor or later Lab gates.",
                    *install_profile_notes,
                ],
            ),
            CapabilityEntry(
                capability_key="installer_doctor_readiness",
                display_name="Installer and doctor readiness",
                group=CapabilityGroup.STATUS_SURFACES,
                state=CapabilityState.LIVE,
                summary="Dry-run-first user-local Core install/verify lifecycle, XDG state contract, packaged local-client authentication, and non-repairing doctor truth are implemented.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["settings_panel", "capabilities_room", "health_room"],
                supporting_endpoint="/status/doctor",
                notes=[
                    "The installer defaults to dry-run, uses user-local XDG storage, preserves user data, and never silently downloads or enables an optional profile.",
                    "Packaged mutating API calls require a private XDG runtime credential; source development mode is explicit.",
                    "Doctor reports readiness only and has no install, repair, download, worker-start, cloud, hardware, or profile-enable authority.",
                ],
            ),
            CapabilityEntry(
                capability_key="addon_registry_management",
                display_name="Governed add-on lifecycle",
                group=CapabilityGroup.TOOLS,
                state=CapabilityState.LIVE,
                summary="Exact plan, one-time approval, XDG-local disabled staging, lifecycle, revocation, and sanitized receipt contracts are live; code execution remains off.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["addons_room", "capabilities_room"],
                supporting_endpoint="/addons/status",
                notes=[
                    "Installed does not mean enabled; enabled_limited does not execute add-on code or grant unrestricted authority.",
                    "Removed is an explicit registry state and retains staged files; revocation withdraws trust and effective grants.",
                    "Every state change is bound to package hash, current state, registry revision, exact plan, and one-time local approval.",
                ],
            ),
            CapabilityEntry(
                capability_key="addon_package_validation",
                display_name="Static add-on package validation",
                group=CapabilityGroup.TOOLS,
                state=CapabilityState.LIVE,
                summary="Untrusted .elysia-addon packages receive bounded static ZIP, manifest, permission, compatibility, checksum, path, credential, and payload inspection without import or execution.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["addons_room", "capabilities_room"],
                supporting_endpoint="/addons/inspect-package",
                notes=[
                    "Validation rejects traversal, absolute paths, links, special files, credential material, checksum mismatch, undeclared code, and unsafe archive shapes.",
                    "Signing readiness is represented honestly; unsigned packages are not presented as signed.",
                ],
            ),
            CapabilityEntry(
                capability_key="addon_permission_resolution",
                display_name="Add-on permission law",
                group=CapabilityGroup.GOVERNANCE,
                state=CapabilityState.LIVE,
                summary="Requested, approved, and effective permissions are separate; effective authority is a fail-closed intersection and cannot be widened by UI or add-on metadata.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["addons_room", "capabilities_room"],
                supporting_endpoint="/addons/status",
                notes=[
                    "Runtime, bridge, network, shell, workers, hardware, host Docker socket, private memory, vault, credential, and raw-log authority remain denied.",
                    "Doctor and local sandbox proof are required before future runtime permissions can become effective.",
                ],
            ),
            CapabilityEntry(
                capability_key="developer_addon_package_preparation",
                display_name="Developer Forge add-on preparation",
                group=CapabilityGroup.CODER,
                state=CapabilityState.DEGRADED,
                summary="Local-private manifest and source-inventory planning is live; package writing, remote push, upload, submission, publication, and execution are not live.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["addons_room", "capabilities_room"],
                supporting_endpoint="/addons/developer/package-plan",
                notes=[
                    "The preparation contract accepts sanitized inventory metadata rather than reading arbitrary project folders.",
                    "A later approved builder must preserve secret, private-path, dependency, license, provenance, and content checks.",
                ],
            ),
            CapabilityEntry(
                capability_key="marketplace_submission_review_contract",
                display_name="Marketplace submission and review contract",
                group=CapabilityGroup.TOOLS,
                state=CapabilityState.DEGRADED,
                summary="Non-uploading submission and admin-review previews bind privacy acknowledgment, exact package hash, scan results, permissions, compatibility, risks, reviewer, and decision; local Elysia does not upload or publish.",
                locality=LocalityState.CROSSED_BOUNDARY,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["addons_room", "capabilities_room"],
                supporting_endpoint="/addons/marketplace/submission-preview",
                notes=[
                    "Website upload is an external boundary and selected files leave the local computer.",
                    "Submitted does not mean approved or public; admin-reviewed does not mean guaranteed safe.",
                ],
            ),
            CapabilityEntry(
                capability_key="codev_official_addon_candidate",
                display_name="Codev official add-on",
                group=CapabilityGroup.CODER,
                state=CapabilityState.LIVE,
                summary="Codev is the official qualified stable v1.0.0 Developer-profile add-on with a reviewed local VSIX install/receipt contract and canonical Elysia Ecobotics Marketplace distribution.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["addons_room", "capabilities_room", "codev"],
                supporting_endpoint="/addons/official-candidates",
                notes=[
                    "The user-local installer validates an exact local VSIX and never downloads or publishes it.",
                    "Exact-byte Extension Host and lifecycle qualification is recorded in the Pass 10D release evidence.",
                    "No silent shell, remote push, Marketplace submission, or publication authority is granted to the add-on.",
                ],
            ),
            CapabilityEntry(
                capability_key="marketplace_catalog",
                display_name="Optional Marketplace catalog",
                group=CapabilityGroup.TOOLS,
                state=CapabilityState.INACTIVE,
                summary="An explicitly configured external catalog and saved-list surface exists behind account/link gates; it is not required by Core.",
                locality=LocalityState.CROSSED_BOUNDARY,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["addons_room", "capabilities_room"],
                supporting_endpoint=None,
                notes=[
                    "Catalog reads and saved-list updates cross an optional external boundary only after explicit Marketplace configuration and sign-in.",
                    "The website cannot install, enable, remove, execute, or inspect private local state.",
                ],
            ),
            CapabilityEntry(
                capability_key="local_sandbox_readiness",
                display_name="Local sandbox readiness",
                group=CapabilityGroup.TOOLS,
                state=CapabilityState.PLANNED,
                summary="Local-only sandbox doctrine is defined, but no general add-on or heavy-worker sandbox is enabled without later doctor and isolation proof.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["settings_panel", "capabilities_room"],
                supporting_endpoint=None,
                notes=[
                    "No cloud sandbox is required or implied.",
                    "Network, host Docker socket, private-memory mounts, and physical hardware remain denied by default.",
                    "The install doctor reports prerequisites without starting or enabling a sandbox.",
                ],
            ),
            CapabilityEntry(
                capability_key="external_boundary_governance",
                display_name="External and cloud boundary law",
                group=CapabilityGroup.GOVERNANCE,
                state=CapabilityState.LIVE,
                summary="Local-first defaults and the prohibition on silent cloud fallback are live constitutional truth.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["settings_panel", "governance_room", "status_menu", "capabilities_room"],
                supporting_endpoint="/governance/state",
                notes=[
                    "Optional external capabilities must be named, profile-gated, scoped, and auditable.",
                    "This law does not imply an external profile or outbound action is currently enabled.",
                ],
            ),
            CapabilityEntry(
                capability_key="publish_queue_profile",
                display_name="Governed publish queue",
                group=CapabilityGroup.TOOLS,
                state=CapabilityState.PLANNED,
                summary="Optional outbound Draft → Preview → Destination bind → Final approval → Receipt flow; no posting route is live.",
                locality=LocalityState.CROSSED_BOUNDARY,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["governance_room", "capabilities_room"],
                supporting_endpoint=None,
                notes=[
                    "No silent send or post is authorized.",
                    "The optional outbound profile and exact destination contract must exist before promotion.",
                ],
            ),
            CapabilityEntry(
                capability_key="codev_developer_profile",
                display_name="Codev Developer profile",
                group=CapabilityGroup.CODER,
                state=CapabilityState.DEGRADED,
                summary="The official Codev add-on has Developer-profile install/doctor truth, authenticated API integration, exact repo approval, read-only Git state, native diff review, bounded checks, receipts, and checkpoint-only Developer Lab planning.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["capabilities_room", "codev"],
                supporting_endpoint="/coding/developer-profile",
                notes=[
                    "Codev remains governed by approved repositories, exact mutation approvals, bounded command catalogs, and request receipts.",
                    "Profile readiness remains install-dependent and fresh Extension Host/manual package proof stays in the release gate.",
                    "Arbitrary shell, hidden Git mutation/push, broad ingestion, cloud upload, and unbounded autonomy remain forbidden.",
                ],
            ),
            CapabilityEntry(
                capability_key="codev_repo_and_git_truth",
                display_name="Codev exact repository approval and Git truth",
                group=CapabilityGroup.CODER,
                state=CapabilityState.LIVE,
                summary="VS Code trust and an exact XDG-local Elysia repo approval gate fixed-argv read-only branch, HEAD, remote, and changed-file truth.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["capabilities_room", "codev"],
                supporting_endpoint="/coding/git/preview",
                notes=["No Git mutation, broad root approval, raw path display, shell, push, or publish authority exists."],
            ),
            CapabilityEntry(
                capability_key="codev_bounded_command_catalog",
                display_name="Codev bounded command catalog",
                group=CapabilityGroup.CODER,
                state=CapabilityState.LIVE,
                summary="Backend-owned exact argv, cwd, timeout, output, environment, approval, and receipt contracts govern the small command/check catalog.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["capabilities_room", "codev"],
                supporting_endpoint="/coding/command/catalog",
                notes=["Arbitrary input, shell interpolation, network, package installation, and Git mutation remain unavailable."],
            ),
            CapabilityEntry(
                capability_key="codev_developer_lab_checkpoints",
                display_name="Codev Developer Lab bounded task checkpoints",
                group=CapabilityGroup.CODER,
                state=CapabilityState.DEGRADED,
                summary="Plan, exact approval, one-click checkpoint receipts, budgets, and stop/revoke are live; checkpoints intentionally execute no tools, commands, patches, or background continuation.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["capabilities_room", "codev"],
                supporting_endpoint="/coding/task/plan",
                notes=["This is a governed Lab foundation, not an autonomous loop. Each later operation retains its own exact approval."],
            ),
            CapabilityEntry(
                capability_key="parametricforge_lab",
                display_name="ParametricForge lab",
                group=CapabilityGroup.FILES,
                state=CapabilityState.INACTIVE,
                summary="Experimental engineering worker lane; static EngineeringForge reports remain separate and live where supported.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["capabilities_room", "codev"],
                supporting_endpoint="/coding/engineering/workers",
                notes=[
                    "Heavy worker handoff remains disabled until local namespace/sandbox and doctor proof exists.",
                    "No machine, controller, ROS/Gazebo launch, cloud CAD upload, or physical actuation authority is granted.",
                ],
            ),
        ]
    )

    approval_resolve_state, approval_resolve_notes = _approval_resolve_state()
    entries.append(
        CapabilityEntry(
            capability_key="approval_resolve",
            display_name="Approval resolve",
            group=CapabilityGroup.APPROVALS,
            state=approval_resolve_state,
            summary="Exact one-time approval resolution for server-held Governance change requests.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NEEDED,
            read_only=False,
            ui_surfaces=["right_drawer", "governance_room"],
            supporting_endpoint="/approval/resolve",
            notes=approval_resolve_notes,
        )
    )

    request_summary_state, request_summary_notes = _request_summary_state()
    entries.append(
        CapabilityEntry(
            capability_key="request_summary",
            display_name="Request summary",
            group=CapabilityGroup.REQUESTS,
            state=request_summary_state,
            summary="Governed request-summary inspection surface.",
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            read_only=True,
            ui_surfaces=["right_drawer", "governance_room"],
            supporting_endpoint="/requests/{request_id}/summary",
            notes=request_summary_notes,
        )
    )

    file_ingestion_state, file_ingestion_notes = _file_ingestion_state()
    file_context_retrieval_state, file_context_retrieval_notes = _file_context_retrieval_state()
    coding_file_stewardship_state, coding_file_stewardship_notes = _coding_file_stewardship_state()
    document_stewardship_state, document_stewardship_notes = _document_stewardship_state()
    science_data_stewardship_state, science_data_stewardship_notes = _science_data_stewardship_state()
    visual_stewardship_state, visual_stewardship_notes = _visual_stewardship_state()
    media_stewardship_state, media_stewardship_notes = _media_stewardship_state()
    archive_stewardship_state, archive_stewardship_notes = _archive_stewardship_state()
    database_stewardship_state, database_stewardship_notes = _database_stewardship_state()
    binary_stewardship_state, binary_stewardship_notes = _binary_stewardship_state()
    engineering_stewardship_state, engineering_stewardship_notes = _engineering_stewardship_state()
    media_worker_states = _governed_media_worker_states()
    math_execution_state, math_execution_notes = _math_execution_state()
    data_execution_state, data_execution_notes = _data_execution_state()
    bounded_research_state, bounded_research_notes = _bounded_public_research_state()
    mode_profiles_state, mode_profiles_notes = _mode_profiles_state()
    repo_context_state, repo_context_notes = _repo_context_state()
    code_patch_plan_state, code_patch_plan_notes = _code_patch_plan_state()
    patch_application_state, patch_application_notes = _patch_application_state()
    focused_command_state, focused_command_notes = _focused_command_state()
    aider_worker_state, aider_worker_notes = _aider_worker_state()
    evidence_packets_state, evidence_packets_notes = _evidence_packets_state()
    artifact_outputs_state, artifact_outputs_notes = _artifact_outputs_state()
    tool_ledger_state, tool_ledger_notes = _tool_ledger_state()
    bounded_fetch_state, bounded_fetch_notes = _bounded_fetch_state()
    identity_account_state, identity_account_notes = _identity_account_state()

    entries.extend(
        [
            CapabilityEntry(
                capability_key="identity_account",
                display_name="Identity account gate",
                group=CapabilityGroup.GOVERNANCE,
                state=identity_account_state,
                summary="Sealed local account creation, login persistence, logout, private profile, and Elysia-visible projection.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["account_gate", "user_creator", "user_profile", "capabilities_room"],
                supporting_endpoint="/account/state",
                notes=identity_account_notes,
            ),
            CapabilityEntry(
                capability_key="mode_profiles",
                display_name="Mode profiles",
                group=CapabilityGroup.GOVERNANCE,
                state=mode_profiles_state,
                summary="Shared mode posture config for Default, Tutor, Researcher, Writer, and Coder.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "capabilities_room"],
                supporting_endpoint=None,
                notes=mode_profiles_notes,
            ),
            CapabilityEntry(
                capability_key="file_ingestion",
                display_name="File ingestion",
                group=CapabilityGroup.FILES,
                state=file_ingestion_state,
                summary="Local-first TXT/Markdown/JSON/saved HTML/PDF/DOCX text attach plus CSV/XLSX data-input ingest path for explicit user-selected files.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "right_drawer", "capabilities_room"],
                supporting_endpoint="/files/attach",
                notes=file_ingestion_notes,
            ),
            CapabilityEntry(
                capability_key="file_context_retrieval",
                display_name="File context retrieval",
                group=CapabilityGroup.FILES,
                state=file_context_retrieval_state,
                summary="Use parsed attached-file chunks as bounded local request context without promoting files into memory by default.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "right_drawer", "memory_room", "requests_room"],
                supporting_endpoint="/files/{file_id}/context-summary",
                notes=file_context_retrieval_notes,
            ),
            CapabilityEntry(
                capability_key="coding_file_stewardship",
                display_name="Coding file stewardship",
                group=CapabilityGroup.FILES,
                state=coding_file_stewardship_state,
                summary="Governed type detection, bounded preview, and exact-approved local operations for registered text/code files.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/file-types",
                notes=coding_file_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="document_stewardship",
                display_name="Document stewardship",
                group=CapabilityGroup.FILES,
                state=document_stewardship_state,
                summary="Bounded local inspection, extraction, stable edits, and derivative exports for supported document formats.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/document-types",
                notes=document_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="science_data_stewardship",
                display_name="Science/data stewardship",
                group=CapabilityGroup.FILES,
                state=science_data_stewardship_state,
                summary="Bounded local metadata, previews, and adapter-specific governed derivatives for science/data formats.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/data-types",
                notes=science_data_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="visual_stewardship",
                display_name="Visual stewardship",
                group=CapabilityGroup.FILES,
                state=visual_stewardship_state,
                summary="Privacy-aware local image/SVG inspection, preview, OCR, analysis, export, and derived edits.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/visual-types",
                notes=visual_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="media_stewardship",
                display_name="Audio/video metadata stewardship",
                group=CapabilityGroup.FILES,
                state=media_stewardship_state,
                summary="Approval-gated local metadata inspection and safe derived thumbnails for selected audio/video files.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/media/inspect",
                notes=media_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="archiveforge_stewardship",
                display_name="ArchiveForge container stewardship",
                group=CapabilityGroup.FILES,
                state=archive_stewardship_state,
                summary="Static archive inspection, risk reporting, exact planning, and selected sandbox extraction without install or execution authority.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/archive/inspect",
                notes=archive_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="databaseforge_stewardship",
                display_name="DatabaseForge stewardship",
                group=CapabilityGroup.FILES,
                state=database_stewardship_state,
                summary="Static database identity/hash metadata plus exact-approved snapshot-first SQLite/DuckDB schema inspection.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/database/inspect",
                notes=database_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="binaryforge_stewardship",
                display_name="BinaryForge stewardship",
                group=CapabilityGroup.FILES,
                state=binary_stewardship_state,
                summary="Bounded static metadata and risk indicators for native, JVM, WASM, and unknown binary files.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/binary/inspect",
                notes=binary_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="engineeringforge_stewardship",
                display_name="EngineeringForge stewardship",
                group=CapabilityGroup.FILES,
                state=engineering_stewardship_state,
                summary="Bounded static engineering-file reports plus exact-approved local SVG projections for supported formats.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/engineering/types",
                notes=engineering_stewardship_notes,
            ),
            CapabilityEntry(
                capability_key="speech_transcription",
                display_name="Local speech transcription",
                group=CapabilityGroup.FILES,
                state=media_worker_states["stt"][0],
                summary="Consent-aware, exact-approved local speech-to-text saved as a governed artifact.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/media/transcribe/preview",
                notes=media_worker_states["stt"][1],
            ),
            CapabilityEntry(
                capability_key="synthetic_reading_voice",
                display_name="Synthetic reading voice",
                group=CapabilityGroup.ARTIFACTS,
                state=media_worker_states["tts"][0],
                summary="Exact-approved local Kokoro reading voice saved as a synthetic WAV artifact.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/media/tts/preview",
                notes=media_worker_states["tts"][1],
            ),
            CapabilityEntry(
                capability_key="imageforge_lab",
                display_name="ImageForge",
                group=CapabilityGroup.ARTIFACTS,
                state=media_worker_states["image"][0],
                summary="Cancellable local synthetic image generation through an optional, doctor-verified Creator profile.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "conversations_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/media/imageforge/models",
                notes=media_worker_states["image"][1],
            ),
            CapabilityEntry(
                capability_key="project_study",
                display_name="Grounded Study",
                group=CapabilityGroup.RESEARCH,
                state=CapabilityState.LIVE,
                summary="Account-scoped source-grounded study plans with difficulty, guided practice, persisted progress, and review scheduling.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "capabilities_room"],
                supporting_endpoint="/projects/{project_id}/study-plans",
                notes=["Study source text remains in the private owner-scoped workbench store and is not returned to the webview."],
            ),
            CapabilityEntry(
                capability_key="project_quizzes",
                display_name="Evidence-grounded quizzes",
                group=CapabilityGroup.RESEARCH,
                state=CapabilityState.LIVE,
                summary="Source-grounded quiz generation, grading, explanations, retries, difficulty, and persisted mastery progress.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "capabilities_room"],
                supporting_endpoint="/projects/{project_id}/quizzes",
                notes=["Expected answers remain server-side; the Desktop receives prompts, grading, and bounded explanations."],
            ),
            CapabilityEntry(
                capability_key="project_goal_pursuit",
                display_name="Bounded goal pursuit",
                group=CapabilityGroup.EXECUTION,
                state=CapabilityState.LIVE,
                summary="Explicit local goals with bounded plans, step budgets, checkpoints, receipts, pause, stop, and emergency stop.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "capabilities_room"],
                supporting_endpoint="/projects/{project_id}/goals",
                notes=["Hidden execution, unrestricted shell, push, and publication remain deterministically denied."],
            ),
            CapabilityEntry(
                capability_key="project_canvas",
                display_name="Local Project Canvas",
                group=CapabilityGroup.ARTIFACTS,
                state=CapabilityState.LIVE,
                summary="Owner-scoped internal visual-note canvas with durable local elements and no external provider.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "capabilities_room"],
                supporting_endpoint="/projects/{project_id}/canvas",
                notes=["Historical Canvas meant the internal Project action, not an external learning-management vendor."],
            ),
            CapabilityEntry(
                capability_key="local_gimp_image_editing",
                display_name="Governed local image editing",
                group=CapabilityGroup.ARTIFACTS,
                state=CapabilityState.LIVE if shutil.which("gimp") else CapabilityState.DEGRADED,
                summary="Explicitly selected images are copied into a private Project workspace and opened through fixed-argv local GIMP.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "capabilities_room"],
                supporting_endpoint="/projects/{project_id}/creative/gimp",
                notes=["GIMP is optional; the original is never mutated and arbitrary shell authority is not granted."],
            ),
            CapabilityEntry(
                capability_key="soundcloud_optional_connector",
                display_name="Optional SoundCloud connector",
                group=CapabilityGroup.ARTIFACTS,
                state=CapabilityState.LIVE,
                summary="User-configured OAuth 2.1 PKCE connector with Internet-master enforcement and local credential revocation.",
                locality=LocalityState.CROSSED_BOUNDARY,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "capabilities_room"],
                supporting_endpoint="/projects/{project_id}/connectors/soundcloud",
                notes=["A user-owned SoundCloud account and registered application are external prerequisites; no operator credential is bundled."],
            ),
            CapabilityEntry(
                capability_key="videoforge_lab",
                display_name="VideoForge lab",
                group=CapabilityGroup.ARTIFACTS,
                state=media_worker_states["video"][0],
                summary="Cancellable, disabled-by-default Wan lab route with no production-enabled video model.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "capabilities_room", "codev"],
                supporting_endpoint="/coding/media/videoforge/preview",
                notes=media_worker_states["video"][1],
            ),
            CapabilityEntry(
                capability_key="voice_cloning",
                display_name="Voice cloning",
                group=CapabilityGroup.ARTIFACTS,
                state=media_worker_states["voice_clone"][0],
                summary="Deliberately unavailable identity-bearing voice capability.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.DENIED,
                read_only=False,
                ui_surfaces=["capabilities_room", "codev"],
                supporting_endpoint=None,
                notes=media_worker_states["voice_clone"][1],
            ),
            CapabilityEntry(
                capability_key="math_execution",
                display_name="Math execution",
                group=CapabilityGroup.EXECUTION,
                state=math_execution_state,
                summary="Bounded local symbolic/numeric math execution for checking and tutoring.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint="/execution/math",
                notes=math_execution_notes,
            ),
            CapabilityEntry(
                capability_key="data_execution",
                display_name="Data execution",
                group=CapabilityGroup.EXECUTION,
                state=data_execution_state,
                summary="Bounded local CSV/XLSX data inspection and basic table summary for user-selected files.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint="/execution/data",
                notes=data_execution_notes,
            ),
            CapabilityEntry(
                capability_key="coder_mode",
                display_name="Coder mode",
                group=CapabilityGroup.CODER,
                state=mode_profiles_state,
                summary="Governed coding posture for repo-aware explanation, patch drafting, and review.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "mode_chips", "capabilities_room"],
                supporting_endpoint=None,
                notes=mode_profiles_notes + [
                    "Coder mode may prefer read-only repo context and proposal-only patch planning when governed paths are available.",
                    "Coder mode does not grant mutation, shell, git, package install, external worker, web, cloud, or private-context export authority by itself.",
                ],
            ),
            CapabilityEntry(
                capability_key="repo_context",
                display_name="Repo context",
                group=CapabilityGroup.CODER,
                state=repo_context_state,
                summary="Read-only selected-repository context gathering for coding assistance.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint="/coder/repo-context",
                notes=repo_context_notes,
            ),
            CapabilityEntry(
                capability_key="patch_review",
                display_name="Patch review",
                group=CapabilityGroup.CODER,
                state=code_patch_plan_state,
                summary="Diff/patch proposal and review path before any code change is applied.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint="/coder/patch-review",
                notes=code_patch_plan_notes,
            ),
            CapabilityEntry(
                capability_key="patch_application",
                display_name="Patch application",
                group=CapabilityGroup.CODER,
                state=patch_application_state,
                summary="Approval-gated Python-only exact patch application path for selected repositories.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint="/code/patch/apply",
                notes=patch_application_notes,
            ),
            CapabilityEntry(
                capability_key="focused_test_execution",
                display_name="Focused test execution",
                group=CapabilityGroup.CODER,
                state=focused_command_state,
                summary="Approval-gated exact focused command worker for selected tests and frontend typecheck/build.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint="/code/tests/run",
                notes=focused_command_notes,
            ),
            _planned_part3_capability(
                capability_key="shell_execution",
                display_name="Shell execution",
                group=CapabilityGroup.CODER,
                summary="Broad host shell execution for Coder mode is not live; exact approved focused commands are tracked separately.",
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint=None,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                notes=[
                    "Planned/blocked for Coder mode v0. No free host shell authority is live.",
                    "Chunk 2 focused command execution is separate, exact, approval-gated, and uses shell=False.",
                    "Future implementation must distinguish read-only inspection, sandbox commands, and host-affecting commands.",
                    "Package installs, service changes, destructive commands, and git mutation require explicit approval.",
                ],
            ),
            CapabilityEntry(
                capability_key="aider_worker",
                display_name="Aider worker",
                group=CapabilityGroup.CODER,
                state=aider_worker_state,
                summary="Selected-repo Aider worker skeleton with dry-run validation truth only.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint=None,
                notes=aider_worker_notes,
            ),
            _planned_part3_capability(
                capability_key="openhands_worker",
                display_name="OpenHands worker",
                group=CapabilityGroup.CODER,
                summary="Future sandbox-only coding worker. Not live yet.",
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint=None,
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                notes=[
                    "Planned Part 3 worker. OpenHands is not wired yet.",
                    "Future use must be Docker/sandbox-only and must not gain host-wide authority or sealed-folder access.",
                    "Host Docker socket access and unrestricted filesystem mounts must remain forbidden by default.",
                ],
            ),
            CapabilityEntry(
                capability_key="bounded_public_web_research",
                display_name="Bounded public web research",
                group=CapabilityGroup.RESEARCH,
                state=bounded_research_state,
                summary="Bounded public web search through the local SearXNG worker; query terms may cross the external public web boundary.",
                locality=(
                    LocalityState.CROSSED_BOUNDARY
                    if bounded_research_state in {CapabilityState.LIVE, CapabilityState.DEGRADED}
                    else LocalityState.LOCAL
                ),
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["requests_room", "capabilities_room"],
                supporting_endpoint="/research/search",
                notes=bounded_research_notes,
            ),
            CapabilityEntry(
                capability_key="project_researcher",
                display_name="Project Researcher",
                group=CapabilityGroup.RESEARCH,
                state=bounded_research_state,
                summary="Durable Project-linked investigations with iterative queries, evidence provenance, source comparison, contradiction awareness, and cancellation.",
                locality=(
                    LocalityState.CROSSED_BOUNDARY
                    if bounded_research_state in {CapabilityState.LIVE, CapabilityState.DEGRADED}
                    else LocalityState.LOCAL
                ),
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "capabilities_room", "right_drawer"],
                supporting_endpoint="/projects/{project_id}/research/iterations",
                notes=[
                    "Internet OFF fails closed before query or fetch egress.",
                    "Only public-safe query terms cross the boundary; private Project source is not appended automatically.",
                    "Exact public-page fetch remains separately approved and bounded.",
                ],
            ),
            CapabilityEntry(
                capability_key="searxng_research_worker",
                display_name="SearXNG research worker",
                group=CapabilityGroup.RESEARCH,
                state=bounded_research_state,
                summary="Local loopback SearXNG search worker for public query terms only.",
                locality=LocalityState.CROSSED_BOUNDARY
                if bounded_research_state in {CapabilityState.LIVE, CapabilityState.DEGRADED}
                else LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["requests_room", "capabilities_room"],
                supporting_endpoint="/research/search",
                notes=bounded_research_notes,
            ),
            CapabilityEntry(
                capability_key="bounded_public_page_fetch",
                display_name="Bounded public page fetch",
                group=CapabilityGroup.RESEARCH,
                state=bounded_fetch_state,
                summary="Approval-gated single public URL fetch worker with SSRF guards and snippet-only evidence truth.",
                locality=(
                    LocalityState.CROSSED_BOUNDARY
                    if bounded_fetch_state in {CapabilityState.LIVE, CapabilityState.DEGRADED}
                    else LocalityState.LOCAL
                ),
                approval_state=ApprovalState.NEEDED,
                read_only=False,
                ui_surfaces=["requests_room", "capabilities_room"],
                supporting_endpoint="/research/fetch",
                notes=bounded_fetch_notes,
            ),
            CapabilityEntry(
                capability_key="evidence_packets",
                display_name="Evidence packets",
                group=CapabilityGroup.RESEARCH,
                state=evidence_packets_state,
                summary="Structured source/evidence summaries for research and verification.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["requests_room", "right_drawer", "capabilities_room"],
                supporting_endpoint="/research/evidence",
                notes=evidence_packets_notes,
            ),
            CapabilityEntry(
                capability_key="artifact_outputs",
                display_name="Artifact outputs",
                group=CapabilityGroup.ARTIFACTS,
                state=artifact_outputs_state,
                summary="Governed generated outputs such as tables, plots, reports, or patches.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["conversations_room", "requests_room", "capabilities_room"],
                supporting_endpoint="/artifacts",
                notes=artifact_outputs_notes,
            ),
            CapabilityEntry(
                capability_key="artifact_registry",
                display_name="Artifact registry",
                group=CapabilityGroup.ARTIFACTS,
                state=artifact_outputs_state,
                summary="Local artifact list/detail plane with project, request, and conversation filters.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["artifacts_room", "project_detail_room", "requests_room"],
                supporting_endpoint="/artifacts",
                notes=artifact_outputs_notes
                + [
                    "Artifact summaries do not expose raw source paths or artifact paths.",
                    "Artifacts are not memory by default and are not published externally.",
                ],
            ),
            CapabilityEntry(
                capability_key="project_continuity",
                display_name="Project continuity",
                group=CapabilityGroup.PROJECTS,
                state=CapabilityState.LIVE,
                summary="Hybrid local project continuity summary with conversations, requests, artifacts, evidence counts, milestones, blockers, and next actions.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=False,
                ui_surfaces=["projects_room", "project_detail_room", "right_drawer"],
                supporting_endpoint="/projects/{project_id}/continuity",
                notes=[
                    "Project continuity is local and provenance-linked.",
                    "Manual fields are compact metadata; automatic fields are derived from local project, conversation, request trace, and artifact stores.",
                    "Sealed/private memory is not exposed raw.",
                ],
            ),
            CapabilityEntry(
                capability_key="tool_ledger",
                display_name="Tool ledger",
                group=CapabilityGroup.TOOLS,
                state=tool_ledger_state,
                summary="Inspectable record of tools, workers, apps, and side-effect boundaries used by a request.",
                locality=LocalityState.LOCAL,
                approval_state=ApprovalState.NOT_NEEDED,
                read_only=True,
                ui_surfaces=["requests_room", "right_drawer", "governance_room"],
                supporting_endpoint="/requests/{request_id}/summary",
                notes=tool_ledger_notes,
            ),
        ]
    )

    return entries


def _determine_catalog_state(entries: list[CapabilityEntry]) -> CapabilityCatalogState:
    """
    Determine the overall state of the capability catalog snapshot itself.

    The catalog can be live even when some individual entries are planned or
    unavailable, as long as the catalog surface is itself available and truthfully
    reporting those states.
    """
    if not entries:
        return CapabilityCatalogState.UNKNOWN

    states = {entry.state for entry in entries}

    if CapabilityState.UNKNOWN in states and len(states) == 1:
        return CapabilityCatalogState.UNKNOWN

    if CapabilityState.UNAVAILABLE in states and all(
        state == CapabilityState.UNAVAILABLE for state in states
    ):
        return CapabilityCatalogState.UNAVAILABLE

    if CapabilityState.DEGRADED in states:
        return CapabilityCatalogState.DEGRADED

    return CapabilityCatalogState.LIVE


def get_capabilities_status() -> dict[str, Any]:
    """
    Return a structured envelope payload for GET /status/capabilities.
    """
    request_id = _new_request_id()

    try:
        entries = _build_capability_entries()
        catalog_state = _determine_catalog_state(entries)
        groups = sorted(
            {
                str(entry.group)
                for entry in entries
                if entry.group is not None
            }
        )

        warnings: list[str] = []
        errors: list[str] = []

        unavailable_count = sum(
            1 for entry in entries if entry.state == CapabilityState.UNAVAILABLE
        )
        planned_count = sum(
            1 for entry in entries if entry.state == CapabilityState.PLANNED
        )
        unknown_count = sum(
            1 for entry in entries if entry.state == CapabilityState.UNKNOWN
        )

        if unavailable_count:
            warnings.append(
                f"{unavailable_count} capability entries should exist but are currently unreachable."
            )

        if planned_count:
            warnings.append(
                f"{planned_count} capability entries are designed but not yet live."
            )

        if unknown_count:
            warnings.append(
                f"{unknown_count} capability entries are not yet confirmed."
            )

        data = CapabilityCatalogData(
            capability_catalog_state=catalog_state,
            capability_count=len(entries),
            last_updated_utc=_utc_now_iso(),
            capability_groups=groups,
            capabilities=entries,
        )

        envelope = build_response_envelope(
            status=EnvelopeStatus.OK,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="capability_manifest",
            capability_state=CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            warnings=warnings,
            errors=errors,
            trace_summary=TraceSummary(
                route_used="status.capabilities",
                log_written=False,
                journal_written=False,
            ),
            data=data,
        )
        return envelope.to_payload()

    except Exception as exc:
        LOGGER.exception("Failed to assemble capability catalog", exc_info=exc)

        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="capability_manifest",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Capability catalog inspection failed unexpectedly: {exc}"],
            trace_summary=TraceSummary(
                route_used="status.capabilities",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()


__all__ = ("get_capabilities_status",)
