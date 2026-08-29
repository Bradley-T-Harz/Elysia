from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from app.api.addons.deep_link import parse_marketplace_install_link
from app.api.addons.manifest_validator import inspect_addon_package


def _package(tmp_path: Path, manifest: dict, files: dict[str, str], name: str = "sample.elysia-addon") -> Path:
    path = tmp_path / name
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for file_name, content in files.items():
            archive.writestr(file_name, content)
    return path


def _manifest(files: dict[str, str], **overrides):
    checksums = {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in files.items()}
    manifest = {
        "schema_version": "1.0",
        "addon_id": "org.ecosyneva.test-addon",
        "name": "Test Add-on",
        "version": "0.1.0",
        "publisher": {"name": "Tester"},
        "compatibility": {"min_elysia_version": "0.1.0", "addon_api_version": "1"},
        "entrypoints": {"tool": "files/tool.py"},
        "permissions": [{"key": "model.invoke.local", "required": False, "reason": "Local summary only."}],
        "sandbox": {"required": True, "network": "deny_by_default", "filesystem": "temporary_only"},
        "checksums": {"files": checksums},
        "binaries": [],
    }
    manifest.update(overrides)
    return manifest


def test_valid_addon_package_passes(tmp_path: Path):
    files = {"files/tool.py": "def run():\n    return 'ok'\n"}
    package = _package(tmp_path, _manifest(files), files)

    inspection = inspect_addon_package(package)

    assert inspection.valid is True
    assert inspection.installable is True
    assert inspection.manifest is not None
    assert inspection.manifest.addon_id == "org.ecosyneva.test-addon"


def test_missing_manifest_fails(tmp_path: Path):
    package = tmp_path / "missing.elysia-addon"
    with ZipFile(package, "w") as archive:
        archive.writestr("README.md", "No manifest.")

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("missing manifest.json" in error for error in inspection.errors)


def test_path_traversal_fails(tmp_path: Path):
    files = {"files/tool.py": "ok"}
    package = _package(tmp_path, _manifest(files), {**files, "../escape.txt": "bad"})

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("Path traversal" in error for error in inspection.errors)


def test_absolute_path_fails(tmp_path: Path):
    files = {"files/tool.py": "ok"}
    package = _package(tmp_path, _manifest(files), {**files, "/tmp/escape.txt": "bad"})

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("Absolute paths" in error for error in inspection.errors)


def test_hidden_env_fails(tmp_path: Path):
    files = {"files/tool.py": "ok"}
    package = _package(tmp_path, _manifest(files), {**files, ".env": "SECRET=value"})

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("environment files" in error for error in inspection.errors)


def test_hash_mismatch_fails(tmp_path: Path):
    files = {"files/tool.py": "ok"}
    manifest = _manifest(files)
    manifest["checksums"]["files"]["files/tool.py"] = "0" * 64
    package = _package(tmp_path, manifest, files)

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("Checksum mismatch" in error for error in inspection.errors)


def test_undeclared_permission_fails(tmp_path: Path):
    files = {"files/tool.py": "ok"}
    manifest = _manifest(files, permissions=[{"key": "vault.read_everything", "required": True, "reason": "bad"}])
    package = _package(tmp_path, manifest, files)

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("not in vocabulary" in error for error in inspection.errors)


def test_undeclared_binary_fails(tmp_path: Path):
    files = {"files/tool.py": "ok"}
    package = _package(tmp_path, _manifest(files), {**files, "files/run.sh": "#!/bin/sh\necho no\n"})

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("Binary/script-like" in error for error in inspection.errors)


def test_disguised_executable_signature_fails(tmp_path: Path):
    files = {
        "files/tool.py": "ok",
        "files/payload.dat": "\x7fELF-disguised",
    }
    package = _package(tmp_path, _manifest(files), files)

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("payload signature is undeclared" in error for error in inspection.errors)


def test_symlink_entry_fails(tmp_path: Path):
    files = {"files/tool.py": "ok"}
    package = tmp_path / "symlink.elysia-addon"
    with ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(_manifest(files)))
        archive.writestr("files/tool.py", files["files/tool.py"])
        info = ZipInfo("files/link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "target")

    inspection = inspect_addon_package(package)

    assert inspection.valid is False
    assert any("Symlink" in error for error in inspection.errors)


def test_symlink_package_file_fails(tmp_path: Path):
    files = {"files/tool.py": "ok"}
    package = _package(tmp_path, _manifest(files), files)
    link = tmp_path / "linked.elysia-addon"
    link.symlink_to(package)

    inspection = inspect_addon_package(link)

    assert inspection.valid is False
    assert inspection.installable is False
    assert any("Symlink package" in error for error in inspection.errors)


def test_deep_link_parser_treats_link_as_invitation_only():
    intent, errors = parse_marketplace_install_link("elysia://marketplace/install?intent_id=abc-123&nonce=safe_nonce")

    assert errors == []
    assert intent is not None
    assert intent.intent_id == "abc-123"


def test_deep_link_parser_rejects_wrong_route():
    intent, errors = parse_marketplace_install_link("elysia://marketplace/enable?intent_id=abc&nonce=n")

    assert intent is None
    assert errors
