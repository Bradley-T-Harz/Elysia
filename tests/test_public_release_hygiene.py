from __future__ import annotations

from pathlib import Path, PurePosixPath
import fnmatch
import json
import re
import subprocess
import sys
import tarfile
from urllib.parse import urlparse

import yaml

from app.api import media_worker_registry_service
from app.api.worker_runtime_path_service import resolve_worker_python
from app.install.profile_service import load_local_model_override_values


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "packaging" / "public_manifest.yaml"


def _dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator == "=", f"Malformed environment entry for {key or '<empty>'}"
        values[key] = value
    return values


def _tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]


def _tracked_text() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for relative in _tracked_files():
        path = ROOT / relative
        try:
            entries.append((relative, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return entries


def test_public_manifest_and_classification_contract_exist_and_parse() -> None:
    payload = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["publication"] == {
        "release_role": "qualified_public_release_payload",
        "live_state_source": "canonical_external_release_surfaces",
        "mutable_external_state_not_embedded": True,
        "owner_authorization_required_for_external_mutation": True,
        "canonical_release_url": "https://github.com/Bradley-T-Harz/Elysia/releases/tag/v1.0.0",
        "canonical_archive_url": "https://elysiaecobotics.com/archive",
    }
    for relative in payload["reviewed_source"]["required_root_files"]:
        assert (ROOT / relative).is_file()
    for relative in payload["core_payload"]["required_files"]:
        assert (ROOT / relative).is_file()
    assert (ROOT / "docs/release/PUBLIC_CANON_CLASSIFICATION.md").is_file()
    assert (ROOT / "docs/release/PUBLIC_RELEASE_RISK_INVENTORY.md").is_file()


def test_stable_marketplace_build_configuration_is_public_bounded_and_canonical() -> None:
    values = _dotenv_values(ROOT / "apps/elysia-desktop/.env.production")
    assert set(values) == {
        "VITE_ELYSIA_MARKETPLACE_URL",
        "VITE_MARKETPLACE_SUPABASE_URL",
        "VITE_MARKETPLACE_SUPABASE_ANON_KEY",
    }

    release_identity = json.loads(
        (ROOT / "config/release/release_identity.json").read_text(encoding="utf-8")
    )
    marketplace_url = values["VITE_ELYSIA_MARKETPLACE_URL"]
    assert marketplace_url == release_identity["official_codev"]["canonical_marketplace_url"]
    marketplace = urlparse(marketplace_url)
    assert marketplace.scheme == "https"
    assert marketplace.hostname == "elysiaecobotics.com"

    supabase = urlparse(values["VITE_MARKETPLACE_SUPABASE_URL"])
    assert supabase.scheme == "https"
    assert supabase.hostname is not None
    assert supabase.hostname.endswith(".supabase.co")

    publishable_key = values["VITE_MARKETPLACE_SUPABASE_ANON_KEY"]
    assert publishable_key.startswith("sb_publishable_")
    assert "service_role" not in publishable_key.lower()

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env.*" in gitignore
    assert "!apps/elysia-desktop/.env.production" in gitignore

    addons_source = (ROOT / "apps/elysia-desktop/src/AddonsPage.tsx").read_text(
        encoding="utf-8"
    )
    assert "https://elysia-marketplace.pages.dev" not in addons_source
    assert marketplace_url in addons_source


def test_public_core_prompts_are_neutral_and_mapped_into_runtime() -> None:
    payload = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    prompt_root = ROOT / "packaging/core_runtime_prompts"
    expected = {
        "elysia_code_system.txt",
        "elysia_general_system.txt",
        "elysia_light_system.txt",
        "elysia_runtime_synthesis.txt",
        "elysia_utility_system.txt",
    }
    assert {path.name for path in prompt_root.glob("*.txt")} == expected
    for path in prompt_root.glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        assert "the operator" not in text
        assert ("ojiji" + "-chhaya") not in text
        assert ("MAIN" + "_Projects") not in text
    assert payload["core_payload"]["source_mappings"] == {
        "packaging/core_runtime_prompts": "derived/runtime"
    }


def test_tracked_source_respects_public_denylist() -> None:
    payload = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    exceptions = set(payload["tracked_template_exceptions"])
    forbidden: list[str] = []
    for relative in _tracked_files():
        if relative in exceptions:
            continue
        if any(
            fnmatch.fnmatchcase(relative, pattern)
            for pattern in payload["tracked_source_deny_globs"]
        ):
            forbidden.append(relative)
    assert forbidden == []


def test_tracked_text_has_no_operator_machine_markers_or_credential_values() -> None:
    operator_markers = (
        "private" + "-operator-home",
        "private" + "-workstation-host",
        "private" + "-external-drive",
    )
    secret_patterns = (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
        re.compile(r"sk-[A-Za-z0-9]{24,}"),
    )
    marker_hits: list[str] = []
    secret_hits: list[str] = []
    for relative, text in _tracked_text():
        if any(marker in text for marker in operator_markers):
            marker_hits.append(relative)
        if any(pattern.search(text) for pattern in secret_patterns):
            secret_hits.append(relative)
    assert marker_hits == []
    assert secret_hits == []


def test_tracked_machine_model_and_worker_defaults_are_portable() -> None:
    machine = yaml.safe_load((ROOT / "config/system/machine_profile.yaml").read_text(encoding="utf-8"))
    assert machine["profile_kind"] == "portable_public_default"
    assert machine["machine_identity"] == {"hostname": None, "user": None, "device_model": None}
    assert machine["paths"]["approved_projects_root"] is None
    assert machine["paths"]["backup_root_hint"] is None

    for relative in (
        "config/models/imageforge_models.yaml",
        "config/models/speechforge_models.yaml",
        "config/models/videoforge_models.yaml",
    ):
        payload = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
        for model in payload["models"]:
            assert "local_path" not in model
            assert "voices_path" not in model
            if model.get("relative_path"):
                path = PurePosixPath(model["relative_path"])
                assert not path.is_absolute()
                assert ".." not in path.parts

    for path in sorted((ROOT / "config/workers").glob("*forge_worker.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else payload
        assert runtime.get("python_path") is None


def test_xdg_override_values_are_internal_path_inputs_not_public_truth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault = tmp_path / "vault"
    image_model = vault / "huggingface/common-canvas/CommonCanvas-XL-C"
    image_model.mkdir(parents=True)
    python_path = tmp_path / "env/bin/python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    override_path = tmp_path / "local_overrides.yaml"
    override_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "contract_version": "elysia-local-model-overrides-1.0",
                "local_only": True,
                "provider_overrides": {"ollama": {"base_url": None, "role_runtime_tags": {}}},
                "model_vault": {
                    "root": str(vault),
                    "permit_authenticated_download_state": False,
                    "provenance_manifest": None,
                },
                "worker_overrides": {
                    "imageforge": {"python_path": str(python_path), "model_root": None}
                },
                "policy": {
                    "allow_network_for_model_acquisition": False,
                    "allow_runtime_network": False,
                    "allow_private_memory_mounts": False,
                    "allow_host_docker_socket": False,
                    "allow_physical_hardware": False,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loaded = load_local_model_override_values(override_path)
    monkeypatch.setattr(media_worker_registry_service, "load_local_model_override_values", lambda: loaded)

    private_paths = media_worker_registry_service.resolved_media_runtime_paths(
        "imageforge_worker",
        "commoncanvas-xl-c",
    )
    assert private_paths["python_path"] == python_path
    assert private_paths["model_path"] == image_model

    public_entry = next(
        item
        for item in media_worker_registry_service.model_registry("imageforge")
        if item["id"] == "commoncanvas-xl-c"
    )
    assert public_entry["local_assets_present"] is True
    assert str(tmp_path) not in repr(public_entry)
    assert "relative_path" not in public_entry


def test_worker_environment_root_resolution_is_portable_and_internal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ELYSIA_BINARYFORGE_PYTHON", raising=False)
    environments = tmp_path / "environments"
    python_path = environments / "elysia_binaryforge/bin/python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o700)
    monkeypatch.setenv("ELYSIA_WORKER_ENVS_ROOT", str(environments))
    resolved = resolve_worker_python(
        {"environment": "elysia_binaryforge", "python_path": None},
        override_env="ELYSIA_BINARYFORGE_PYTHON",
        allow_current_interpreter=False,
    )
    assert resolved == python_path
    assert resolve_worker_python(
        {"environment": "../escape", "python_path": None},
        override_env="ELYSIA_ESCAPE_PYTHON",
        allow_current_interpreter=False,
    ) is None


def test_installer_copies_manifest_and_excludes_optional_machine_contracts() -> None:
    installer = (ROOT / "scripts/install_core.sh").read_text(encoding="utf-8")
    assert "packaging/public_manifest.yaml" in installer
    assert "--exclude='derived/runtime'" in installer
    assert "packaging/core_runtime_prompts/*.txt" in installer
    for relative in yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))["core_payload"][
        "excluded_optional_contracts"
    ]:
        assert f"--exclude='{relative}'" in installer


def test_public_source_archive_honors_reviewed_export_boundary(tmp_path: Path) -> None:
    output = tmp_path / "elysia-public-source.tar.gz"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_public_source_archive.py"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    with tarfile.open(output, mode="r:gz") as archive:
        names = archive.getnames()
        assert any(name.endswith("/packaging/core_runtime_prompts/elysia_general_system.txt") for name in names)
        assert any(name.endswith("/derived/runtime/elysia_general_system.txt") for name in names)
        assert any(name.endswith("/apps/elysia-desktop/package.json") for name in names)
        assert any(name.endswith("/apps/elysia-desktop/package-lock.json") for name in names)
        assert any(name.endswith("/apps/elysia-desktop/.env.production") for name in names)
        assert any(name.endswith("/apps/elysia-desktop/src/ElysiaSetupPage.tsx") for name in names)
        assert any(name.endswith("/apps/elysia-desktop/src-tauri/Cargo.toml") for name in names)
        assert any(name.endswith("/apps/elysia-desktop/src-tauri/Cargo.lock") for name in names)
        assert not any("/docs/reports/" in name for name in names)
        assert any(name.endswith("/docs/SYSTEM_PROMPT.txt") for name in names)
