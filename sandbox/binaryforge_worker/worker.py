"""Bounded static binary parsers. No execution, loading, linking, or mutation."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import math
import os
from pathlib import Path
import struct
from typing import Any


class BinaryWorkerError(RuntimeError):
    """Raised when a static inspection cannot safely complete."""


def _source(path: Path, max_input_bytes: int) -> Path:
    if path.is_symlink():
        raise BinaryWorkerError("source_must_be_regular_non_symlink_file")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise BinaryWorkerError("source_must_be_regular_non_symlink_file")
    if resolved.stat().st_size > max_input_bytes:
        raise BinaryWorkerError("binary_input_limit_exceeded")
    return resolved


def _hashes_and_entropy(path: Path) -> tuple[str, str | None, float]:
    sha = sha256()
    try:
        import blake3

        b3: Any = blake3.blake3()
    except Exception:
        b3 = None
    frequencies = [0] * 256
    total = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
            if b3 is not None:
                b3.update(chunk)
            total += len(chunk)
            for value, count in Counter(chunk).items():
                frequencies[value] += count
    entropy = 0.0
    if total:
        for count in frequencies:
            if count:
                probability = count / total
                entropy -= probability * math.log2(probability)
    return sha.hexdigest(), b3.hexdigest() if b3 is not None else None, round(entropy, 4)


def _magic(path: Path) -> str:
    try:
        import magic

        return str(magic.from_file(str(path)))[:240]
    except Exception:
        return "magic_unavailable"


def _strings(path: Path, *, scan_limit: int, count_limit: int, char_limit: int) -> list[str]:
    output: list[str] = []
    current = bytearray()
    scanned = 0
    with path.open("rb") as stream:
        while scanned < scan_limit and len(output) < count_limit:
            chunk = stream.read(min(65536, scan_limit - scanned))
            if not chunk:
                break
            scanned += len(chunk)
            for value in chunk:
                if 32 <= value <= 126:
                    if len(current) < char_limit:
                        current.append(value)
                else:
                    if len(current) >= 4:
                        output.append(current.decode("ascii", errors="replace"))
                        if len(output) >= count_limit:
                            break
                    current.clear()
    if len(current) >= 4 and len(output) < count_limit:
        output.append(current.decode("ascii", errors="replace"))
    return output


def _risk(code: str, severity: str, summary: str, count: int = 1) -> dict[str, Any]:
    return {"code": code, "severity": severity, "summary": summary, "count": max(1, count)}


def _name_risks(names: list[str]) -> list[dict[str, Any]]:
    lowered = [name.lower() for name in names]
    groups = {
        "imports_networking": ("warning", "Static references include networking APIs.", ("socket", "connect", "winhttp", "wininet", "urlmon", "ws2_32")),
        "imports_process_creation": ("high", "Static references include process-creation APIs.", ("createprocess", "shellexecute", "winexec", "system", "execve", "processbuilder", "java/lang/runtime")),
        "imports_dynamic_loading": ("warning", "Static references include dynamic-loading APIs.", ("loadlibrary", "getprocaddress", "dlopen", "dlsym", "system.loadlibrary")),
        "imports_crypto": ("info", "Static references include cryptographic APIs.", ("bcrypt", "crypt", "openssl", "evp_", "javax/crypto")),
    }
    flags: list[dict[str, Any]] = []
    joined = "\n".join(lowered)
    for code, (severity, summary, markers) in groups.items():
        hits = sum(joined.count(marker) for marker in markers)
        if hits:
            flags.append(_risk(code, severity, summary, hits))
    return flags


def _detect(path: Path) -> str:
    with path.open("rb") as stream:
        header = stream.read(8)
    if header.startswith(b"MZ"):
        return "pe"
    if header.startswith(b"\x7fELF"):
        return "elf"
    if header.startswith(b"\xca\xfe\xba\xbe"):
        return "class"
    if header.startswith(b"\x00asm"):
        return "wasm"
    return "unknown"


def _inspect_pe(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    try:
        import pefile
    except Exception as exc:
        raise BinaryWorkerError("pefile_dependency_unavailable") from exc
    pe = pefile.PE(str(path), fast_load=False)
    try:
        machine_map = {0x14C: "x86", 0x8664: "x86_64", 0x1C0: "arm", 0xAA64: "aarch64"}
        imports: list[dict[str, Any]] = []
        import_names: list[str] = []
        for entry in list(getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) or []):
            library = entry.dll.decode("utf-8", errors="replace") if entry.dll else "unknown"
            names: list[str] = []
            for imported in entry.imports:
                name = imported.name.decode("utf-8", errors="replace") if imported.name else f"ordinal_{imported.ordinal}"
                names.append(name)
                import_names.append(f"{library}!{name}")
                if len(import_names) >= limits["max_imports"]:
                    break
            imports.append({"library": library, "names": names})
            if len(import_names) >= limits["max_imports"]:
                break
        exports: list[str] = []
        export_directory = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
        for symbol in list(getattr(export_directory, "symbols", []) or [])[: limits["max_exports"]]:
            exports.append(symbol.name.decode("utf-8", errors="replace") if symbol.name else f"ordinal_{symbol.ordinal}")
        sections: list[dict[str, Any]] = []
        wx_sections = 0
        for section in list(pe.sections)[: limits["max_sections"]]:
            name = section.Name.rstrip(b"\x00").decode("utf-8", errors="replace")
            executable = bool(section.Characteristics & 0x20000000)
            writable = bool(section.Characteristics & 0x80000000)
            if executable and writable:
                wx_sections += 1
            sections.append({"name": name, "virtual_size": int(section.Misc_VirtualSize), "raw_size": int(section.SizeOfRawData), "executable": executable, "writable": writable, "entropy": round(float(section.get_entropy()), 4)})
        directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY
        security_size = int(directory[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]].Size)
        debug_size = int(directory[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DEBUG"]].Size)
        flags = _name_risks(import_names)
        if wx_sections:
            flags.append(_risk("write_execute_section", "high", "One or more PE sections are both writable and executable.", wx_sections))
        if security_size == 0:
            flags.append(_risk("signature_unknown_or_absent", "warning", "No embedded PE certificate table was found; this is not a trust verdict."))
        return {
            "architecture": machine_map.get(int(pe.FILE_HEADER.Machine), f"machine_0x{int(pe.FILE_HEADER.Machine):04x}"),
            "bitness": 64 if int(pe.OPTIONAL_HEADER.Magic) == 0x20B else 32,
            "endianness": "little",
            "headers": {"entry_point": int(pe.OPTIONAL_HEADER.AddressOfEntryPoint), "image_base": int(pe.OPTIONAL_HEADER.ImageBase), "subsystem": int(pe.OPTIONAL_HEADER.Subsystem), "timestamp": int(pe.FILE_HEADER.TimeDateStamp), "dll": bool(pe.FILE_HEADER.Characteristics & 0x2000), "certificate_table_present": security_size > 0},
            "sections": sections,
            "imports": imports,
            "exports": exports,
            "section_count": len(pe.sections),
            "import_count": len(import_names),
            "export_count": len(exports),
            "symbol_count": 0,
            "debug_symbols_present": debug_size > 0,
            "stripped": None,
            "risk_flags": flags,
            "toolchain": ["pefile"],
        }
    finally:
        pe.close()


def _inspect_elf(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    try:
        from elftools.elf.elffile import ELFFile
        from elftools.elf.sections import SymbolTableSection
    except Exception as exc:
        raise BinaryWorkerError("pyelftools_dependency_unavailable") from exc
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        sections: list[dict[str, Any]] = []
        symbols: list[str] = []
        imports: list[str] = []
        exports: list[str] = []
        needed: list[str] = []
        rpaths: list[str] = []
        executable_stack = False
        for segment in elf.iter_segments():
            if segment.header.p_type == "PT_GNU_STACK":
                executable_stack = bool(int(segment.header.p_flags) & 1)
        has_symtab = False
        debug_present = False
        for section in list(elf.iter_sections())[: limits["max_sections"]]:
            sections.append({"name": section.name, "type": str(section.header.sh_type), "size": int(section.header.sh_size), "flags": int(section.header.sh_flags)})
            debug_present = debug_present or section.name.startswith(".debug")
            if section.name == ".symtab":
                has_symtab = True
            if isinstance(section, SymbolTableSection):
                for symbol in section.iter_symbols():
                    name = str(symbol.name or "")
                    if not name:
                        continue
                    if len(symbols) < limits["max_symbols"]:
                        symbols.append(name)
                    bind = str(symbol.entry.st_info.bind)
                    if symbol.entry.st_shndx == "SHN_UNDEF" and len(imports) < limits["max_imports"]:
                        imports.append(name)
                    elif bind in {"STB_GLOBAL", "STB_WEAK"} and len(exports) < limits["max_exports"]:
                        exports.append(name)
            if section.header.sh_type == "SHT_DYNAMIC":
                for tag in section.iter_tags():
                    if tag.entry.d_tag == "DT_NEEDED":
                        needed.append(str(tag.needed))
                    elif tag.entry.d_tag in {"DT_RPATH", "DT_RUNPATH"}:
                        rpaths.append(str(getattr(tag, "rpath", getattr(tag, "runpath", ""))))
        flags = _name_risks(imports + needed)
        if executable_stack:
            flags.append(_risk("executable_stack", "high", "ELF GNU_STACK requests execute permission."))
        if rpaths:
            flags.append(_risk("rpath_runpath_present", "warning", "ELF contains RPATH/RUNPATH entries.", len(rpaths)))
        return {
            "architecture": str(elf.get_machine_arch()),
            "bitness": int(elf.elfclass),
            "endianness": "little" if elf.little_endian else "big",
            "headers": {"elf_type": str(elf.header.e_type), "entry_point": int(elf.header.e_entry), "needed_libraries": needed, "rpath_runpath": rpaths, "executable_stack": executable_stack},
            "sections": sections,
            "imports": imports,
            "exports": exports,
            "symbols": symbols,
            "section_count": elf.num_sections(),
            "import_count": len(imports),
            "export_count": len(exports),
            "symbol_count": len(symbols),
            "debug_symbols_present": debug_present,
            "stripped": not has_symtab,
            "risk_flags": flags,
            "toolchain": ["pyelftools"],
        }


class _ClassReader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def take(self, size: int) -> bytes:
        end = self.offset + size
        if end > len(self.data):
            raise BinaryWorkerError("truncated_class_file")
        value = self.data[self.offset:end]
        self.offset = end
        return value

    def u1(self) -> int:
        return self.take(1)[0]

    def u2(self) -> int:
        return struct.unpack(">H", self.take(2))[0]

    def u4(self) -> int:
        return struct.unpack(">I", self.take(4))[0]


def _skip_class_members(reader: _ClassReader, count: int) -> tuple[list[dict[str, int]], int]:
    members: list[dict[str, int]] = []
    native = 0
    for _ in range(count):
        access = reader.u2()
        name_index = reader.u2()
        descriptor_index = reader.u2()
        attribute_count = reader.u2()
        native += 1 if access & 0x0100 else 0
        members.append({"access_flags": access, "name_index": name_index, "descriptor_index": descriptor_index})
        for _ in range(attribute_count):
            reader.u2()
            reader.take(reader.u4())
    return members, native


def _inspect_class(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    data = path.read_bytes()
    reader = _ClassReader(data)
    if reader.take(4) != b"\xca\xfe\xba\xbe":
        raise BinaryWorkerError("invalid_class_magic")
    minor, major = reader.u2(), reader.u2()
    pool_count = reader.u2()
    pool: list[Any] = [None] * pool_count
    utf8: list[str] = []
    index = 1
    while index < pool_count:
        tag = reader.u1()
        if tag == 1:
            value = reader.take(reader.u2()).decode("utf-8", errors="replace")
            pool[index] = (tag, value)
            if len(utf8) < limits["max_symbols"]:
                utf8.append(value)
        elif tag in {3, 4}:
            reader.take(4)
        elif tag in {5, 6}:
            reader.take(8)
            index += 1
        elif tag in {7, 8, 16, 19, 20}:
            pool[index] = (tag, reader.u2())
        elif tag in {9, 10, 11, 12, 17, 18}:
            pool[index] = (tag, reader.u2(), reader.u2())
        elif tag == 15:
            pool[index] = (tag, reader.u1(), reader.u2())
        else:
            raise BinaryWorkerError(f"unsupported_class_constant_tag_{tag}")
        index += 1
    access_flags, this_class, super_class = reader.u2(), reader.u2(), reader.u2()
    interfaces_count = reader.u2()
    interfaces = [reader.u2() for _ in range(interfaces_count)]
    field_count = reader.u2()
    fields, _ = _skip_class_members(reader, field_count)
    method_count = reader.u2()
    methods, native_methods = _skip_class_members(reader, method_count)

    def class_name(pool_index: int) -> str | None:
        try:
            entry = pool[pool_index]
            name_entry = pool[entry[1]] if entry and entry[0] == 7 else None
            return str(name_entry[1]) if name_entry and name_entry[0] == 1 else None
        except (IndexError, TypeError):
            return None

    referenced = [class_name(value) for value in range(1, pool_count) if pool[value] and pool[value][0] == 7]
    references = [value for value in referenced if value][: limits["max_imports"]]
    flags = _name_risks(utf8 + references)
    joined = "\n".join(value.lower() for value in utf8)
    if "java/lang/reflect" in joined:
        flags.append(_risk("uses_reflection", "warning", "Class constants reference Java reflection APIs."))
    if "java/io/" in joined or "java/nio/file" in joined:
        flags.append(_risk("uses_file_apis", "info", "Class constants reference file APIs."))
    if native_methods:
        flags.append(_risk("native_methods_declared", "warning", "Class declares native methods.", native_methods))
    return {
        "architecture": "jvm_bytecode",
        "bitness": None,
        "endianness": "big",
        "headers": {"minor_version": minor, "major_version": major, "access_flags": access_flags, "class_name": class_name(this_class), "superclass": class_name(super_class), "interfaces": [class_name(value) for value in interfaces], "constant_pool_count": pool_count, "field_count": field_count, "method_count": method_count, "native_method_count": native_methods},
        "sections": [],
        "imports": references,
        "exports": [],
        "symbols": utf8,
        "section_count": 0,
        "import_count": len(references),
        "export_count": 0,
        "symbol_count": len(utf8),
        "debug_symbols_present": any(value in {"LineNumberTable", "LocalVariableTable", "SourceFile"} for value in utf8),
        "stripped": None,
        "risk_flags": flags,
        "toolchain": ["binaryforge_class_parser"],
        "fields": fields[: limits["max_symbols"]],
        "methods": methods[: limits["max_symbols"]],
    }


class _WasmReader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def byte(self) -> int:
        if self.offset >= len(self.data):
            raise BinaryWorkerError("truncated_wasm")
        value = self.data[self.offset]
        self.offset += 1
        return value

    def take(self, size: int) -> bytes:
        end = self.offset + size
        if end > len(self.data):
            raise BinaryWorkerError("truncated_wasm")
        value = self.data[self.offset:end]
        self.offset = end
        return value

    def leb(self) -> int:
        result = 0
        shift = 0
        for _ in range(10):
            value = self.byte()
            result |= (value & 0x7F) << shift
            if not value & 0x80:
                return result
            shift += 7
        raise BinaryWorkerError("invalid_wasm_leb")

    def name(self) -> str:
        return self.take(self.leb()).decode("utf-8", errors="replace")


def _wasm_limits(reader: _WasmReader) -> dict[str, int | None]:
    flags = reader.leb()
    minimum = reader.leb()
    maximum = reader.leb() if flags & 1 else None
    return {"minimum": minimum, "maximum": maximum}


def _inspect_wasm(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    reader = _WasmReader(path.read_bytes())
    if reader.take(4) != b"\x00asm":
        raise BinaryWorkerError("invalid_wasm_magic")
    version = struct.unpack("<I", reader.take(4))[0]
    sections: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    exports: list[dict[str, Any]] = []
    memories: list[dict[str, int | None]] = []
    start_present = False
    function_count = 0
    global_count = 0
    table_count = 0
    custom_sections: list[str] = []
    while reader.offset < len(reader.data) and len(sections) < limits["max_sections"]:
        section_id = reader.byte()
        size = reader.leb()
        payload = _WasmReader(reader.take(size))
        item: dict[str, Any] = {"id": section_id, "size": size}
        if section_id == 0:
            name = payload.name()
            custom_sections.append(name)
            item["name"] = name
        elif section_id == 2:
            count = payload.leb()
            for _ in range(min(count, limits["max_imports"])):
                module, name, kind = payload.name(), payload.name(), payload.byte()
                descriptor: Any
                if kind == 0:
                    descriptor = {"type_index": payload.leb()}
                elif kind == 1:
                    descriptor = {"element_type": payload.byte(), "limits": _wasm_limits(payload)}
                    table_count += 1
                elif kind == 2:
                    descriptor = _wasm_limits(payload)
                    memories.append(descriptor)
                elif kind == 3:
                    descriptor = {"value_type": payload.byte(), "mutable": bool(payload.byte())}
                    global_count += 1
                else:
                    raise BinaryWorkerError("unsupported_wasm_import_kind")
                imports.append({"module": module, "name": name, "kind": kind, "descriptor": descriptor})
        elif section_id == 3:
            function_count = payload.leb()
        elif section_id == 4:
            table_count += payload.leb()
        elif section_id == 5:
            count = payload.leb()
            for _ in range(count):
                memories.append(_wasm_limits(payload))
        elif section_id == 6:
            global_count = payload.leb()
        elif section_id == 7:
            count = payload.leb()
            for _ in range(min(count, limits["max_exports"])):
                exports.append({"name": payload.name(), "kind": payload.byte(), "index": payload.leb()})
        elif section_id == 8:
            start_present = True
            item["function_index"] = payload.leb()
        sections.append(item)
    import_names = [f"{value['module']}.{value['name']}" for value in imports]
    flags = _name_risks(import_names)
    if any(value["module"].startswith("wasi_") for value in imports):
        flags.append(_risk("wasi_imports", "warning", "Module imports WASI capabilities."))
    if any(value["module"] == "env" for value in imports):
        flags.append(_risk("env_imports", "warning", "Module imports from the ambient env namespace."))
    if start_present:
        flags.append(_risk("start_function_present", "warning", "Module declares a start function; it was not instantiated."))
    if any((value.get("maximum") or 0) > 65536 for value in memories):
        flags.append(_risk("large_memory_limit", "warning", "Module declares a large memory maximum."))
    return {
        "architecture": "webassembly",
        "bitness": 32,
        "endianness": "little",
        "headers": {"version": version, "function_count": function_count, "global_count": global_count, "table_count": table_count, "memories": memories, "start_section_present": start_present, "custom_sections": custom_sections},
        "sections": sections,
        "imports": imports,
        "exports": exports,
        "section_count": len(sections),
        "import_count": len(imports),
        "export_count": len(exports),
        "symbol_count": 0,
        "debug_symbols_present": "name" in custom_sections,
        "stripped": None,
        "risk_flags": flags,
        "toolchain": ["binaryforge_wasm_parser"],
    }


def inspect_binary(path: Path, *, limits: dict[str, int]) -> dict[str, Any]:
    source = _source(path, limits["max_input_bytes"])
    detected = _detect(source)
    digest, blake3_digest, entropy = _hashes_and_entropy(source)
    strings = _strings(source, scan_limit=limits["max_string_scan_bytes"], count_limit=limits["max_strings"], char_limit=limits["max_string_chars"])
    if detected == "pe":
        details = _inspect_pe(source, limits)
    elif detected == "elf":
        details = _inspect_elf(source, limits)
    elif detected == "class":
        details = _inspect_class(source, limits)
    elif detected == "wasm":
        details = _inspect_wasm(source, limits)
    else:
        details = {"architecture": None, "bitness": None, "endianness": None, "headers": {}, "sections": [], "imports": [], "exports": [], "section_count": 0, "import_count": 0, "export_count": 0, "symbol_count": 0, "debug_symbols_present": None, "stripped": None, "risk_flags": [], "toolchain": ["binaryforge_header_parser"]}
    if entropy >= 7.5:
        details["risk_flags"].append(_risk("packed_or_high_entropy", "warning", "High entropy may indicate compression, packing, encryption, or random data; it is not a malware verdict."))
    details["risk_flags"].append(_risk("static_analysis_not_verdict", "info", "Risk indicators are static observations, not antivirus certification or a malware verdict."))
    details.update({"detected_format": detected, "sha256": digest, "blake3": blake3_digest, "size_bytes": source.stat().st_size, "magic_summary": _magic(source), "entropy": entropy, "strings": strings, "string_count": len(strings), "strings_truncated": len(strings) >= limits["max_strings"], "executable_bit": bool(source.stat().st_mode & 0o111), "network_used": False, "execution_performed": False, "loading_performed": False, "mutation_performed": False})
    return details


__all__ = ("BinaryWorkerError", "inspect_binary")
