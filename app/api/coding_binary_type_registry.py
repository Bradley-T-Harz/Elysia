"""Canonical BinaryForge format and authority registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.api.schemas.database_binary import BinaryTypeDescriptor


BINARY_TYPES: dict[str, BinaryTypeDescriptor] = {
    "pe": BinaryTypeDescriptor(type_id="pe", label="PE/COFF executable or library", extensions=[".exe", ".dll"], inspection_state="available", notes=["Static PE headers, sections, imports, exports, resources, and signature presence only."]),
    "elf": BinaryTypeDescriptor(type_id="elf", label="ELF executable, shared object, or object", extensions=[".so", ".o", ".bin"], inspection_state="available", notes=["Static ELF headers, sections, segments, dependencies, symbols, and hardening indicators only."]),
    "class": BinaryTypeDescriptor(type_id="class", label="Java class bytecode", extensions=[".class"], inspection_state="available", notes=["Static class-file metadata and reference summaries only; no class loading or decompilation."]),
    "wasm": BinaryTypeDescriptor(type_id="wasm", label="WebAssembly module", extensions=[".wasm"], inspection_state="available", notes=["Static sections, imports, exports, memories, and start-section presence only; no instantiation."]),
    "bin_unknown": BinaryTypeDescriptor(type_id="bin_unknown", label="Unknown binary data", extensions=[".bin"], inspection_state="metadata_only", notes=["Hash, size, magic, entropy, and bounded artifact-only strings only."]),
    "binary_unknown": BinaryTypeDescriptor(type_id="binary_unknown", label="Unrecognized binary file", extensions=[], inspection_state="metadata_only", notes=["Static metadata only because the format could not be safely identified."]),
}
BINARY_EXTENSIONS = {extension for descriptor in BINARY_TYPES.values() for extension in descriptor.extensions}


def binary_type_from_extension(path: Path | str) -> str:
    suffix = Path(str(path)).suffix.lower()
    if suffix in {".exe", ".dll"}:
        return "pe"
    if suffix in {".so", ".o"}:
        return "elf"
    if suffix == ".class":
        return "class"
    if suffix == ".wasm":
        return "wasm"
    if suffix == ".bin":
        return "bin_unknown"
    return "binary_unknown"


def detect_binary_format(path: Path) -> tuple[str, str]:
    try:
        with path.open("rb") as stream:
            header = stream.read(64)
    except OSError:
        return "unknown", "unreadable"
    if header.startswith(b"MZ"):
        return "pe", "PE/COFF (MZ)"
    if header.startswith(b"\x7fELF"):
        return "elf", "ELF"
    if header.startswith(b"\xca\xfe\xba\xbe"):
        return "class", "Java class"
    if header.startswith(b"\x00asm"):
        return "wasm", "WebAssembly"
    return "unknown", "unrecognized binary data"


def descriptor_for_binary(format_id: str, *, extension_type: str | None = None) -> BinaryTypeDescriptor:
    if format_id in BINARY_TYPES:
        return BINARY_TYPES[format_id]
    if extension_type == "bin_unknown":
        return BINARY_TYPES["bin_unknown"]
    return BINARY_TYPES["binary_unknown"]


def binary_registry_payload() -> dict[str, Any]:
    return {
        "version": "binary-types-0.1",
        "formats": [BINARY_TYPES[key].to_payload() for key in ("pe", "elf", "class", "wasm", "bin_unknown")],
        "authority": {
            "static_inspection": "available",
            "disassembly": "future_sandbox_required",
            "decompilation": "future_sandbox_required",
            "execution": "unavailable_by_design",
            "loading": "unavailable_by_design",
            "installation": "unavailable_by_design",
            "linking": "unavailable_by_design",
            "mutation": "unavailable_by_design",
            "patching": "unavailable_by_design",
        },
    }


def is_registered_binary_path(path: Path | str) -> bool:
    return Path(str(path)).suffix.lower() in BINARY_EXTENSIONS


__all__ = (
    "BINARY_TYPES",
    "BINARY_EXTENSIONS",
    "binary_registry_payload",
    "binary_type_from_extension",
    "descriptor_for_binary",
    "detect_binary_format",
    "is_registered_binary_path",
)
