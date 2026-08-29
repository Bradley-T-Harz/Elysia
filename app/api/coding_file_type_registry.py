"""Canonical file type registry for governed Codev file stewardship."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingFileTypeDescriptor:
    type_id: str
    label: str
    category: str
    adapter: str
    language_id: str | None
    extensions: tuple[str, ...] = ()
    exact_names: tuple[str, ...] = ()
    compound_names: tuple[str, ...] = ()
    readable: bool = True
    writable: bool = True
    patchable: bool = True
    creatable: bool = True
    deletable: bool = True
    renameable: bool = True
    secret_sensitive: bool = False
    generated_sensitive: bool = False
    lockfile: bool = False
    executable_sensitive: bool = False
    max_preview_bytes: int = 65_536
    max_patch_bytes: int = 131_072
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_PREVIEW_BYTES = 65_536
DEFAULT_PATCH_BYTES = 131_072


def _descriptor(
    type_id: str,
    label: str,
    category: str,
    adapter: str,
    language_id: str | None = None,
    *,
    extensions: tuple[str, ...] = (),
    exact_names: tuple[str, ...] = (),
    compound_names: tuple[str, ...] = (),
    readable: bool = True,
    writable: bool = True,
    patchable: bool = True,
    creatable: bool = True,
    deletable: bool = True,
    renameable: bool = True,
    secret_sensitive: bool = False,
    generated_sensitive: bool = False,
    lockfile: bool = False,
    executable_sensitive: bool = False,
    max_preview_bytes: int = DEFAULT_PREVIEW_BYTES,
    max_patch_bytes: int = DEFAULT_PATCH_BYTES,
    notes: tuple[str, ...] = (),
) -> CodingFileTypeDescriptor:
    return CodingFileTypeDescriptor(
        type_id=type_id,
        label=label,
        category=category,
        adapter=adapter,
        language_id=language_id,
        extensions=extensions,
        exact_names=exact_names,
        compound_names=compound_names,
        readable=readable,
        writable=writable,
        patchable=patchable,
        creatable=creatable,
        deletable=deletable,
        renameable=renameable,
        secret_sensitive=secret_sensitive,
        generated_sensitive=generated_sensitive,
        lockfile=lockfile,
        executable_sensitive=executable_sensitive,
        max_preview_bytes=max_preview_bytes,
        max_patch_bytes=max_patch_bytes,
        notes=notes,
    )


SUPPORTED_FILE_TYPES: tuple[CodingFileTypeDescriptor, ...] = (
    _descriptor("python_code", "Python code", "code", "code", "python", extensions=(".py",)),
    _descriptor("typescript_code", "TypeScript code", "code", "code", "typescript", extensions=(".ts",)),
    _descriptor("typescript_react_code", "TypeScript React code", "code", "code", "typescriptreact", extensions=(".tsx",)),
    _descriptor("vite_config_ts", "Vite TypeScript config", "project_metadata", "code", "typescript", exact_names=("vite.config.ts",), notes=("Vite config changes can alter frontend build behavior.",)),
    _descriptor("javascript_code", "JavaScript code", "code", "code", "javascript", extensions=(".js",)),
    _descriptor("javascript_react_code", "JavaScript React code", "code", "code", "javascriptreact", extensions=(".jsx",)),
    _descriptor("css_style", "CSS stylesheet", "style", "code", "css", extensions=(".css",)),
    _descriptor("sql_script", "SQL script", "database_script", "code", "sql", extensions=(".sql",), notes=("SQL execution is not implied by read or patch support.",)),
    _descriptor("shell_script", "Shell script", "shell_script", "code", "shellscript", extensions=(".sh",), executable_sensitive=True, notes=("Shell files are executable-sensitive; reading/patching never authorizes execution.",)),
    _descriptor("dockerfile", "Dockerfile", "config", "code", "dockerfile", exact_names=("dockerfile",), notes=("Docker build/run is not enabled by this descriptor.",)),
    _descriptor("requirements_txt", "Python requirements file", "project_metadata", "code", "pip-requirements", exact_names=("requirements.txt",)),
    _descriptor("json_data", "JSON data", "structured_data", "structured_data", "json", extensions=(".json",)),
    _descriptor("package_json", "npm package manifest", "project_metadata", "structured_data", "json", exact_names=("package.json",)),
    _descriptor("tsconfig_json", "TypeScript config", "project_metadata", "structured_data", "json", exact_names=("tsconfig.json",)),
    _descriptor("package_lock_json", "npm package lockfile", "lockfile", "structured_data", "json", exact_names=("package-lock.json",), lockfile=True, creatable=False, deletable=False, notes=("Lockfiles are patchable only with explicit caution; package-manager regeneration is not enabled.",)),
    _descriptor("yaml_data", "YAML data", "structured_data", "structured_data", "yaml", extensions=(".yaml", ".yml")),
    _descriptor("docker_compose_yaml", "Docker Compose YAML", "config", "structured_data", "yaml", exact_names=("docker-compose.yml", "docker-compose.yaml"), notes=("Docker compose execution is not enabled.",)),
    _descriptor("toml_data", "TOML data", "structured_data", "structured_data", "toml", extensions=(".toml",)),
    _descriptor("cargo_toml", "Cargo manifest", "project_metadata", "structured_data", "toml", exact_names=("Cargo.toml",)),
    _descriptor("pyproject_toml", "Python project config", "project_metadata", "structured_data", "toml", exact_names=("pyproject.toml",)),
    _descriptor("cargo_lock", "Cargo lockfile", "lockfile", "structured_data", "toml", exact_names=("Cargo.lock",), lockfile=True, creatable=False, deletable=False, notes=("Cargo lockfiles are read/analyze/diff capable; package-manager regeneration is not enabled.",)),
    _descriptor("ini_config", "INI/CFG config", "config", "structured_data", "ini", extensions=(".ini", ".cfg")),
    _descriptor("markdown_doc", "Markdown document", "markdown", "markdown", "markdown", extensions=(".md",)),
    _descriptor("project_readme", "Project README", "project_metadata", "markdown", "markdown", exact_names=("readme", "readme.md")),
    _descriptor("license_doc", "License document", "project_metadata", "markdown", "text", exact_names=("license", "license.md"), notes=("License edits are high-risk and should be narrow and explicit.",)),
    _descriptor("changelog_doc", "Changelog document", "project_metadata", "markdown", "markdown", exact_names=("changelog", "changelog.md")),
    _descriptor("plain_text", "Plain text", "plain_text", "text", "plaintext", extensions=(".txt", ".rst")),
    _descriptor("stl_engineering", "STL triangle mesh", "engineering", "engineering", None, extensions=(".stl",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("GeometryForge performs bounded static inspection; source mutation, print, repair, and machine send are separate or unavailable actions.",)),
    _descriptor("obj_engineering", "Wavefront OBJ mesh", "engineering", "engineering", None, extensions=(".obj",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("GeometryForge reports MTL/texture references without fetching or following unsafe paths.",)),
    _descriptor("dae_engineering", "COLLADA scene/mesh", "engineering", "engineering", None, extensions=(".dae",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("COLLADA is parsed as defused XML; external references are never fetched.",)),
    _descriptor("step_engineering", "STEP product model", "engineering", "engineering", None, extensions=(".step", ".stp"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("CADForge static exchange inspection only; macros, source overwrite, and manufacturing claims are unavailable.",)),
    _descriptor("iges_engineering", "IGES exchange model", "engineering", "engineering", None, extensions=(".iges", ".igs"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("CADForge does not assume watertightness or unit correctness.",)),
    _descriptor("dxf_engineering", "DXF drawing/model", "engineering", "engineering", None, extensions=(".dxf",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("CADForge reports drawing structure and XREF risk without generating toolpaths or cut-ready claims.",)),
    _descriptor("urdf_engineering", "URDF robot model", "engineering", "engineering", None, extensions=(".urdf",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("RobotModelForge never expands xacro by default or launches ROS, RViz, Gazebo, controllers, or hardware.",)),
    _descriptor("sdf_engineering", "SDF simulation description", "engineering", "engineering", None, extensions=(".sdf",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("Plugins and external resources are reported but never loaded or fetched.",)),
    _descriptor("gcode_engineering", "G-code machine instructions", "engineering", "engineering", None, extensions=(".gcode", ".nc", ".tap", ".cnc"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("CAMForge treats G-code as dangerous inert text; serial/controller send and physical output are unavailable by design.",)),
    _descriptor("blend_engineering", "Blender scene", "engineering", "engineering", None, extensions=(".blend",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("BlendForge static metadata only; embedded scripts, drivers, linked data, and add-ons are never executed or loaded.",)),
    _descriptor("f3d_engineering", "Fusion 360 design", "engineering", "engineering", None, extensions=(".f3d",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Limited local metadata only; Autodesk cloud translation and upload are unavailable by design.",)),
    _descriptor("f3z_engineering", "Fusion 360 distributed design", "engineering", "engineering", None, extensions=(".f3z",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Container recognition only; export a neutral derivative for local-first CAD inspection.",)),
    _descriptor("csv_data", "CSV data", "delimited_data", "delimited_data", "csv", extensions=(".csv",)),
    _descriptor("tsv_data", "TSV data", "delimited_data", "delimited_data", "tsv", extensions=(".tsv",)),
    _descriptor("xml_markup", "XML markup", "markup", "markup", "xml", extensions=(".xml",)),
    _descriptor("html_markup", "HTML markup", "markup", "markup", "html", extensions=(".html", ".htm"), notes=("HTML is previewed as text; scripts and external references are never executed.",)),
    _descriptor("env_example", "Environment example file", "config", "text", "dotenv", exact_names=(".env.example",), compound_names=(".env.example",), secret_sensitive=True, notes=("Allowed with caution; secret scanning always runs.",)),
    _descriptor("gitignore", "Git ignore file", "config", "text", "gitignore", exact_names=(".gitignore",)),
    _descriptor("blocked_secret_env", "Secret environment file", "blocked_secret", "blocked", "dotenv", exact_names=(".env", ".env.local"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, secret_sensitive=True, notes=("Real environment files are blocked before preview or mutation.",)),
    _descriptor("pdf_document", "PDF document", "document", "document", "pdf", extensions=(".pdf",), writable=False, patchable=False, creatable=False, secret_sensitive=False, notes=("PDF support is extraction/export oriented; arbitrary inline PDF editing is refused.",)),
    _descriptor("docx_document", "Word document", "document", "document", "docx", extensions=(".docx",), patchable=False, notes=("DOCX support uses document adapters and stable approved edit operations; unified text patches are refused.",)),
    _descriptor("xlsx_workbook", "Excel workbook", "document", "document", "xlsx", extensions=(".xlsx",), patchable=False, notes=("XLSX formulas are inspected as inert text and never executed; unified text patches are refused.",)),
    _descriptor("pptx_presentation", "PowerPoint presentation", "document", "document", "pptx", extensions=(".pptx",), patchable=False, notes=("PPTX support uses document adapters and stable approved edit operations; unified text patches are refused.",)),
    _descriptor("odt_document", "OpenDocument text", "document", "document", "odt", extensions=(".odt",), patchable=False, notes=("ODT support is extraction/export oriented in this pass.",)),
    _descriptor("ods_spreadsheet", "OpenDocument spreadsheet", "document", "document", "ods", extensions=(".ods",), patchable=False, notes=("ODS support is extraction/export oriented; formulas are never executed.",)),
    _descriptor("odp_presentation", "OpenDocument presentation", "document", "document", "odp", extensions=(".odp",), patchable=False, notes=("ODP support is extraction/export oriented in this pass.",)),
    _descriptor("jsonl_data", "JSON Lines data", "science_data", "data", "jsonl", extensions=(".jsonl",), patchable=False, notes=("JSONL uses governed data stewardship for bounded preview and approved record operations.",)),
    _descriptor("parquet_data", "Parquet table", "science_data", "data", "parquet", extensions=(".parquet",), writable=False, patchable=False, notes=("Parquet uses PyArrow-backed governed data stewardship for schema, row-group, and bounded preview support.",)),
    _descriptor("sqlite_database", "SQLite database", "database", "database", None, extensions=(".sqlite", ".sqlite3"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("Static metadata only; exact-approved snapshot-first schema preview is separate. Rows, SQL, export, and mutation are unavailable.",)),
    _descriptor("duckdb_database", "DuckDB database", "database", "database", None, extensions=(".duckdb",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("Static metadata only; exact-approved fixed schema introspection is separate. Extensions, external access, SQL, export, and mutation are unavailable.",)),
    _descriptor("ambiguous_database", "Ambiguous .db database file", "database", "database", None, extensions=(".db",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("The .db extension is not trusted. DatabaseForge identifies content; unknown files remain metadata-only.",)),
    _descriptor("geojson_data", "GeoJSON vector data", "science_data", "data", "geojson", extensions=(".geojson",), patchable=False, notes=("GeoJSON uses governed data stewardship for bounded feature preview and approved feature/property operations.",)),
    _descriptor("geopackage_data", "GeoPackage", "science_data", "data", "gpkg", extensions=(".gpkg",), writable=False, patchable=False, notes=("GeoPackage uses GDAL-backed stewardship for layers, CRS, bounds, schema, and bounded feature previews.",)),
    _descriptor("shapefile_data", "Shapefile sidecar set", "science_data", "data", "shp", extensions=(".shp",), writable=False, patchable=False, notes=("Shapefile support validates required sidecars and uses GDAL-backed bounded feature previews.",)),
    _descriptor("kml_data", "KML vector data", "science_data", "data", "kml", extensions=(".kml",), patchable=False, notes=("KML external network links are reported but never fetched.",)),
    _descriptor("kmz_data", "KMZ vector archive", "science_data", "data", "kmz", extensions=(".kmz",), writable=False, patchable=False, notes=("KMZ inspection uses zip-slip protection and never fetches external links.",)),
    _descriptor("tiff_image", "TIFF image", "visual", "visual", "tiff", extensions=(".tif", ".tiff"), writable=False, patchable=False, notes=("Ordinary TIFF uses visual stewardship; geospatial TIFF hints are surfaced and data routes remain available for raster science workflows.",)),
    _descriptor("geotiff_data", "GeoTIFF/TIFF raster", "science_data", "data", "raster", extensions=(".tif", ".tiff"), writable=False, patchable=False, notes=("Rasterio-backed support is bounded to metadata, CRS, bounds, band summaries, and sample-window statistics.",)),
    _descriptor("netcdf_data", "NetCDF dataset", "science_data", "data", "netcdf", extensions=(".nc", ".netcdf"), writable=False, patchable=False, notes=("NetCDF uses xarray with h5netcdf in-process; netCDF4 is isolated behind a timeout worker fallback.",)),
    _descriptor("hdf5_data", "HDF5 dataset", "science_data", "data", "hdf5", extensions=(".h5", ".hdf5"), writable=False, patchable=False, notes=("HDF5 uses h5py-backed group, dataset, attr, chunk, compression, and bounded sample access.",)),
    _descriptor("zarr_data", "Zarr directory store", "science_data", "data", "zarr", extensions=(".zarr",), writable=False, patchable=False, notes=("Zarr is a workspace-contained directory store with metadata, attrs, chunk, and bounded local-store sample stewardship.",)),
    _descriptor("png_image", "PNG image", "visual", "visual", "png", extensions=(".png",), writable=False, patchable=False, notes=("Visual stewardship supports metadata, privacy report, safe thumbnail, OCR, analysis, and approval-gated derived-copy edits." ,)),
    _descriptor("jpeg_image", "JPEG image", "visual", "visual", "jpeg", extensions=(".jpg", ".jpeg"), writable=False, patchable=False, secret_sensitive=False, notes=("EXIF/GPS metadata is summarized without exposing precise GPS; strip/derived-copy workflows are approval-gated.",)),
    _descriptor("webp_image", "WebP image", "visual", "visual", "webp", extensions=(".webp",), writable=False, patchable=False, notes=("Animated WebP is bounded; previews do not audit raw pixels.",)),
    _descriptor("gif_image", "GIF image", "visual", "visual", "gif", extensions=(".gif",), writable=False, patchable=False, notes=("Animated GIF frame inspection is bounded by visual policy.",)),
    _descriptor("bmp_image", "BMP image", "visual", "visual", "bmp", extensions=(".bmp",), writable=False, patchable=False, notes=("BMP support is local metadata/preview/export/edit-copy stewardship.",)),
    _descriptor("svg_vector_image", "SVG image", "visual", "visual", "svg", extensions=(".svg",), writable=False, patchable=False, executable_sensitive=True, notes=("SVG is parsed with defused XML and rendered only after sanitization; scripts/external references are removed for previews.",)),
    _descriptor("wav_audio", "WAV audio", "media", "media", "audio", extensions=(".wav",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection; exact-approved local transcription is separate; mutation is unavailable.",)),
    _descriptor("mp3_audio", "MP3 audio", "media", "media", "audio", extensions=(".mp3",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection; embedded tag values are not exposed.",)),
    _descriptor("flac_audio", "FLAC audio", "media", "media", "audio", extensions=(".flac",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection; exact-approved local transcription is separate; mutation is unavailable.",)),
    _descriptor("ogg_audio", "Ogg audio", "media", "media", "audio", extensions=(".ogg",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection; exact-approved local transcription is separate; mutation is unavailable.",)),
    _descriptor("m4a_audio", "M4A audio", "media", "media", "audio", extensions=(".m4a",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection; embedded tag values are not exposed.",)),
    _descriptor("mp4_video", "MP4 video", "media", "media", "video", extensions=(".mp4",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection and fixed-argument derived thumbnail only.",)),
    _descriptor("mov_video", "QuickTime video", "media", "media", "video", extensions=(".mov",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection and fixed-argument derived thumbnail only.",)),
    _descriptor("mkv_video", "Matroska video", "media", "media", "video", extensions=(".mkv",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection and fixed-argument derived thumbnail only.",)),
    _descriptor("webm_video", "WebM video", "media", "media", "video", extensions=(".webm",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Read-only metadata inspection and fixed-argument derived thumbnail only.",)),
    _descriptor("zip_archive", "ZIP archive", "archive", "archive", None, extensions=(".zip",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("ArchiveForge inspection and selected sandbox extraction are separate governed actions; contents are never trusted automatically.",)),
    _descriptor("tar_archive", "TAR archive", "archive", "archive", None, extensions=(".tar",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("ArchiveForge blocks traversal, links, devices, FIFOs, sockets, ownership, and dangerous permissions.",)),
    _descriptor("tar_gz_archive", "Compressed TAR archive", "archive", "archive", None, extensions=(".tgz",), compound_names=(".tar.gz",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Selected regular files may be extracted only after exact approval into a disposable sandbox.",)),
    _descriptor("seven_zip_archive", "7-Zip archive", "archive", "archive", None, extensions=(".7z",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("7Z is list/risk only in the proven Chunk 6 slice; extraction is not enabled.",)),
    _descriptor("rar_archive", "RAR archive", "archive", "archive", None, extensions=(".rar",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("RAR tooling is available locally but license-sensitive; extraction remains lab-only.",)),
    _descriptor("python_wheel_container", "Python wheel", "archive", "archive", None, extensions=(".whl",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("Wheel metadata is inspected as inert data; pip install and import are unavailable by design.",)),
    _descriptor("java_archive_container", "Java archive", "archive", "archive", None, extensions=(".jar",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("JAR inspection is static; java -jar and class loading are unavailable by design.",)),
    _descriptor("vsix_extension_container", "VS Code extension package", "archive", "archive", None, extensions=(".vsix",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("VSIX inspection is static; extension installation and activation are unavailable by design.",)),
    _descriptor("appimage_container", "AppImage executable container", "archive", "archive", None, extensions=(".appimage",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("AppImage inspection never executes, mounts, or invokes --appimage-extract.",)),
    _descriptor("debian_package_container", "Debian package", "archive", "archive", None, extensions=(".deb",), writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("DEB inspection is static; dpkg/apt installation and maintainer-script execution are unavailable by design.",)),
    _descriptor("windows_pe_binary", "Windows PE executable/library", "binary", "binary", None, extensions=(".exe", ".dll"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("BinaryForge static metadata only; never run, load, install, patch, or trust automatically.",)),
    _descriptor("elf_binary", "ELF binary/shared object/object", "binary", "binary", None, extensions=(".so", ".o"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("BinaryForge static metadata only; never execute, dlopen, link, patch, or install.",)),
    _descriptor("java_class_binary", "Java class bytecode", "binary", "binary", None, extensions=(".class",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("Static class metadata only; never load, initialize, execute, or decompile.",)),
    _descriptor("wasm_binary", "WebAssembly module", "binary", "binary", None, extensions=(".wasm",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("Static WASM metadata only; never instantiate or call exports.",)),
    _descriptor("binary", "Unknown binary data", "binary", "binary", None, extensions=(".bin",), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("BinaryForge metadata-only handling; no extraction, execution, loading, mutation, or patching.",)),
    _descriptor("macro_enabled_document", "Macro-enabled document", "blocked_document", "blocked", None, extensions=(".docm", ".xlsm", ".pptm", ".dotm", ".xltm", ".potm"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, executable_sensitive=True, notes=("Macro-enabled document variants are blocked; macros are never inspected or executed.",)),
    _descriptor("legacy_office_document", "Legacy Office document", "blocked_document", "blocked", None, extensions=(".doc", ".xls", ".ppt"), readable=False, writable=False, patchable=False, creatable=False, deletable=False, renameable=False, notes=("Legacy Office formats are unsupported except for refusal metadata.",)),
)


UNKNOWN_TEXT = _descriptor(
    "unknown_text",
    "Unknown text file",
    "unknown_text",
    "text",
    None,
    writable=False,
    patchable=False,
    creatable=False,
    deletable=False,
    renameable=False,
    notes=("Unknown text files are preview-only until a governed semantic adapter recognizes them.",),
)
BINARY_UNSUPPORTED = _descriptor(
    "binary",
    "Binary or unsupported file",
    "binary",
    "blocked",
    None,
    readable=False,
    writable=False,
    patchable=False,
    creatable=False,
    deletable=False,
    renameable=False,
    notes=("Binary files are outside Chunk 1 file stewardship.",),
)


def _normalized_name(path: Path | str) -> str:
    return Path(str(path)).name


def _looks_binary(raw_bytes: bytes | None) -> bool:
    if not raw_bytes:
        return False
    if b"\x00" in raw_bytes:
        return True
    try:
        raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def detect_file_type(path: Path | str, raw_bytes: bytes | None = None) -> CodingFileTypeDescriptor:
    candidate = Path(str(path))
    name = _normalized_name(candidate)
    lower_name = name.lower()
    suffix = candidate.suffix.lower()

    for descriptor in SUPPORTED_FILE_TYPES:
        exact_names = {item.lower() for item in descriptor.exact_names}
        compound_names = {item.lower() for item in descriptor.compound_names}
        if lower_name in exact_names or lower_name in compound_names:
            return descriptor
        if any(lower_name.endswith(item) for item in compound_names):
            return descriptor

    for descriptor in SUPPORTED_FILE_TYPES:
        if suffix and suffix in descriptor.extensions:
            return descriptor

    if _looks_binary(raw_bytes):
        return BINARY_UNSUPPORTED

    return UNKNOWN_TEXT


def registry_payload() -> list[dict[str, object]]:
    return [descriptor.to_payload() for descriptor in SUPPORTED_FILE_TYPES]


__all__ = (
    "BINARY_UNSUPPORTED",
    "CodingFileTypeDescriptor",
    "SUPPORTED_FILE_TYPES",
    "UNKNOWN_TEXT",
    "detect_file_type",
    "registry_payload",
)
