"""Non-repairing install doctor and first-run readiness truth."""

from __future__ import annotations

from collections import Counter
import ctypes.util
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from packaging.utils import canonicalize_name

from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope

from .local_auth import LocalApiAuthPolicy, build_local_api_auth_policy
from .paths import ElysiaPaths, resolve_elysia_paths
from .profile_service import resolve_install_profile_status
from .model_acquisition_service import CREATOR_MODEL_IDS, MANIFEST_PATH
from .codev_service import read_codev_install_status, read_codev_repo_approval_status
from .component_graph_service import load_component_graph, resolve_profile_components
from .install_root_service import install_root_hash, resolve_component_runtime_root
from .python_lock_service import compare_environment_to_lock
from .release_trust import public_trust_state
from .schemas import DependencyStatus, DoctorCheck, DoctorStatusData


API_VERSION = "1.0.0"
DESKTOP_VERSION = "1.0.0"
CONTRACT_VERSION = "elysia-install-doctor-1.0"
DOCTOR_VERSION = "1"
LAST_RUN_FILENAME = "last-run.json"
ROOT = Path(__file__).resolve().parents[2]


def _safe_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _isolated_python_executable(component_root: Path, environment_id: str) -> Path | None:
    """Resolve a venv interpreter without rejecting Python's normal symlinks."""

    environment = component_root / environment_id
    candidate = environment / "bin" / "python"
    if environment.parent != component_root:
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return None
    return candidate


def _canonical_installed_versions(installed: dict[str, Any]) -> dict[str, str]:
    return {
        canonicalize_name(str(name)): str(version)
        for name, version in installed.items()
    }


def _rootless_podman_ready(
    podman: str | None, *, attempts: int = 3
) -> bool:
    """Prove rootless Podman, tolerating bounded clean-VM startup pressure."""

    if not podman:
        return False
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DOCKER_HOST", "CONTAINER_HOST"}
    }
    for _attempt in range(max(1, attempts)):
        try:
            probe = subprocess.run(
                [podman, "info", "--format", "{{.Host.Security.Rootless}}"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0 and probe.stdout.strip().lower() == "true":
            return True
    return False


def _sqlite_contract_check(
    database: Path,
    *,
    check_id: str,
    label: str,
    tables: set[str],
    first_use_summary: str,
) -> DoctorCheck:
    """Validate a private SQLite authority without creating or exposing it."""
    if not database.exists():
        return _check(
            check_id, label, "identity", DependencyStatus.PRESENT, True,
            first_use_summary,
        )
    if not database.is_file() or database.is_symlink() or database.stat().st_mode & 0o077:
        return _check(
            check_id, label, "identity", DependencyStatus.BLOCKED, True,
            f"{label} is not a private safe regular file.",
            "Correct ownership/permissions or restore the authority from a verified private backup.",
        )
    try:
        with database.open("rb") as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                raise sqlite3.DatabaseError("invalid header")
        with sqlite3.connect(
            f"file:{database.as_posix()}?mode=ro", uri=True, timeout=1.0
        ) as connection:
            if str(connection.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                raise sqlite3.DatabaseError("integrity")
            observed = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        if not tables.issubset(observed):
            raise sqlite3.DatabaseError("schema")
    except (OSError, sqlite3.Error, ValueError):
        return _check(
            check_id, label, "identity", DependencyStatus.BLOCKED, True,
            f"{label} failed its read-only integrity or schema check.",
            "Restore from a verified private backup; Doctor did not mutate the authority.",
        )
    return _check(
        check_id, label, "identity", DependencyStatus.PRESENT, True,
        f"{label} passed private-file, SQLite integrity, and schema checks.",
    )


def _backup_check(paths: ElysiaPaths) -> DoctorCheck:
    root = paths.memory_backup_dir
    if not root.exists():
        return _check(
            "private_backups", "Private backup readiness", "backup",
            DependencyStatus.PRESENT, True,
            "The private backup location is ready for first use; no backup is fabricated for a blank profile.",
        )
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode & 0o077:
        return _check(
            "private_backups", "Private backup readiness", "backup",
            DependencyStatus.BLOCKED, True,
            "The private backup location is unsafe or has overly broad permissions.",
            "Correct the account-owned backup location before update or repair.",
        )
    unsafe = [
        candidate for candidate in root.iterdir()
        if candidate.is_symlink() or (candidate.is_file() and candidate.stat().st_mode & 0o077)
    ]
    return _check(
        "private_backups", "Private backup readiness", "backup",
        DependencyStatus.DEGRADED if unsafe else DependencyStatus.PRESENT, True,
        (
            "One or more managed backup entries are unsafe."
            if unsafe else
            "The private backup location and existing managed entries satisfy the account-owned permission boundary."
        ),
        "Move unsafe entries out of service and restore from verified private evidence."
        if unsafe else None,
    )


def _setup_component_selection(paths: ElysiaPaths) -> tuple[str, set[str]]:
    receipt = _safe_json(paths.state_dir / "setup" / "installation.json")
    if not receipt or receipt.get("status") != "configured":
        return "core", set(resolve_profile_components("core"))
    profile_id = str(receipt.get("profile_id") or "core")
    try:
        expected = set(resolve_profile_components(
            profile_id,
            custom_components=[str(item) for item in receipt.get("custom_components", [])]
            if profile_id == "custom" else None,
        ))
    except Exception:
        return profile_id, set()
    recorded = {str(item) for item in receipt.get("component_ids", [])}
    return profile_id, expected if recorded == expected else set()


def _component_checks(paths: ElysiaPaths) -> list[DoctorCheck]:
    """Verify selected components from exact ownership receipts and health probes."""
    graph = load_component_graph()
    profile_id, selected = _setup_component_selection(paths)
    if not selected:
        return [
            _check(
                "setup_component_receipt", "Setup component selection", "component",
                DependencyStatus.BLOCKED, True,
                "The Setup receipt does not match the authoritative component graph.",
                "Create a fresh exact Setup preview and approve that immutable component selection.",
            )
        ]
    receipts = paths.state_dir / "install" / "components"
    component_root = resolve_component_runtime_root(paths)
    python_components = {
        "workstation_adapters": ("elysia_workstation", "workstation-py312.lock.txt"),
        "creator_perception": ("elysia_creator", None),
        "scientific_engineering": ("elysia_neurofabric", None),
    }
    checks: list[DoctorCheck] = [
        _check(
            "setup_component_receipt", "Setup component selection", "component",
            DependencyStatus.PRESENT, True,
            f"The {profile_id} Setup receipt resolves exactly through the authoritative component graph.",
        )
    ]
    for component_id, component in graph["components"].items():
        required = component_id in selected
        if not required:
            checks.append(_check(
                f"component_{component_id}", str(component_id).replace("_", " ").title(),
                "component", DependencyStatus.PROFILE_GATED, False,
                "This component is not selected by the active Setup profile.",
            ))
            continue
        if component_id in {
            "core_python_runtime", "desktop_shell", "identity_memory_fabric",
            "personal_onboarding", "local_connectors",
        }:
            checks.append(_check(
                f"component_{component_id}", str(component_id).replace("_", " ").title(),
                "component", DependencyStatus.PRESENT, True,
                "This package-bound component is present in the active Elysia payload and remains governed by its dedicated Doctor checks.",
            ))
            continue
        if component_id == "local_model_provider":
            checks.append(_check(
                f"component_{component_id}", "Local Model Provider", "component",
                DependencyStatus.PRESENT if shutil.which("ollama") else DependencyStatus.MISSING,
                True,
                "The selected local provider command is present."
                if shutil.which("ollama") else
                "The selected local provider is absent; no cloud fallback or silent download occurred.",
                None if shutil.which("ollama") else "Install an approved local provider through its separately reviewed acquisition flow.",
            ))
            continue
        if component_id in python_components:
            environment_id, lock_name = python_components[component_id]
            python = _isolated_python_executable(component_root, environment_id)
            receipt = _safe_json(receipts / f"{component_id}.json")
            if lock_name is None and receipt:
                candidate = str(receipt.get("lock_name") or "")
                if candidate in {
                    "creator-cpu-py312.lock.txt",
                    "creator-cuda-py312.lock.txt",
                    "neurofabric-cpu-py312.lock.txt",
                    "neurofabric-cuda-py312.lock.txt",
                }:
                    lock_name = candidate
            status = DependencyStatus.MISSING
            summary = "The selected isolated Python component has no valid Elysia ownership receipt."
            root_matches = bool(
                receipt
                and receipt.get("component_root_sha256") in {
                    None,
                    install_root_hash(component_root),
                }
            )
            if receipt and root_matches and lock_name and python is not None:
                try:
                    result = subprocess.run(
                        [str(python), "-c", (
                            "import json;from app.install.python_lock_service import compare_environment_to_lock;"
                            f"print(json.dumps(compare_environment_to_lock('/payload/config/install/locks/{lock_name}')))"
                        )],
                        capture_output=True, text=True, timeout=30, check=False,
                        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
                    )
                    # Installed environments do not necessarily contain the Elysia payload.
                    # Fall back to package-metadata comparison below when the bounded helper is unavailable.
                    if result.returncode == 0:
                        comparison = json.loads(result.stdout.strip().splitlines()[-1])
                    else:
                        probe = subprocess.run(
                            [str(python), "-c", "import importlib.metadata,json;print(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata.get('Name')}))"],
                            capture_output=True, text=True, timeout=30, check=False,
                            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
                        )
                        installed = json.loads(probe.stdout.strip().splitlines()[-1]) if probe.returncode == 0 else {}
                        comparison = compare_environment_to_lock(
                            ROOT / "config" / "install" / "locks" / lock_name,
                            installed=_canonical_installed_versions(installed),
                        )
                    if comparison.get("matches"):
                        status = DependencyStatus.PRESENT
                        summary = "The isolated component environment matches its exact hash lock and ownership receipt."
                    else:
                        status = DependencyStatus.DEGRADED
                        summary = "The isolated component environment differs from its exact release lock."
                except Exception:
                    status = DependencyStatus.DEGRADED
                    summary = "The isolated component environment could not prove its exact lock state."
            if component_id == "creator_perception" and status == DependencyStatus.PRESENT:
                model_receipt = receipt.get("model_receipt") if receipt else None
                expected_manifest = _file_sha256(MANIFEST_PATH)
                selected_models = {
                    str(item) for item in (
                        model_receipt.get("selected_model_ids", [])
                        if isinstance(model_receipt, dict) else []
                    )
                }
                gated_models = sorted(set(CREATOR_MODEL_IDS) - selected_models)
                if not isinstance(model_receipt, dict):
                    status = DependencyStatus.DEGRADED
                    summary = "The Creator environment is exact, but it has no model-selection receipt."
                elif model_receipt.get("manifest_sha256") not in {None, expected_manifest}:
                    status = DependencyStatus.DEGRADED
                    summary = "The Creator model receipt was produced from a different acquisition manifest."
                elif receipt.get("status") == "ready_with_model_gates" or gated_models:
                    status = DependencyStatus.DEGRADED
                    summary = (
                        "The Creator environment is exact; unselected model-specific capabilities remain truthfully gated: "
                        + ", ".join(gated_models)
                        + "."
                    )
            checks.append(_check(
                f"component_{component_id}", str(component_id).replace("_", " ").title(),
                "component", status, True, summary,
                None if status == DependencyStatus.PRESENT else "Repair only this Elysia-owned environment from the exact approved lock.",
            ))
            continue
        receipt = _safe_json(receipts / f"{component_id}.json")
        checks.append(_check(
            f"component_{component_id}", str(component_id).replace("_", " ").title(),
            "component", DependencyStatus.PRESENT if receipt and receipt.get("status") == "ready" else DependencyStatus.MISSING,
            True,
            "The selected component has a private Elysia ownership/readiness receipt."
            if receipt and receipt.get("status") == "ready" else
            "The selected component has no valid ready ownership receipt.",
            None if receipt and receipt.get("status") == "ready" else "Run its separately approved component acquisition/install flow, then rerun Doctor.",
        ))
    return checks


def _system_and_resource_checks(paths: ElysiaPaths, selected: set[str]) -> list[DoctorCheck]:
    graph = load_component_graph()
    dependencies = {
        dependency
        for component_id in selected
        for dependency in graph["components"][component_id]["system_dependencies"]
    }
    tools = dependencies & {"ffmpeg", "ffprobe", "tesseract", "git", "vscode", "ollama"}
    checks: list[DoctorCheck] = []
    for tool in sorted(tools):
        command = "code" if tool == "vscode" else tool
        found = shutil.which(command) or (shutil.which("codium") if tool == "vscode" else None)
        checks.append(_check(
            f"system_tool_{tool}", f"System tool: {tool}", "system",
            DependencyStatus.PRESENT if found else DependencyStatus.MISSING, True,
            f"The selected profile's {tool} prerequisite is present."
            if found else f"The selected profile requires {tool}, which is absent.",
            None if found else "Review the exact package-manager privilege preview before installing this prerequisite.",
        ))
    if "libmagic" in dependencies:
        found = bool(ctypes.util.find_library("magic"))
        checks.append(_check(
            "system_library_libmagic", "System library: libmagic", "system",
            DependencyStatus.PRESENT if found else DependencyStatus.MISSING, True,
            "The selected profile's native file-type library is present."
            if found else "The selected profile requires libmagic, which is absent.",
            None if found else "Review the exact package-manager privilege preview before installing libmagic.",
        ))
    if dependencies & {"rootless_podman_or_bounded_docker", "rootless_sandbox"}:
        podman = shutil.which("podman")
        rootless = _rootless_podman_ready(podman)
        checks.append(_check(
            "system_rootless_container", "Rootless container/sandbox authority", "system",
            DependencyStatus.PRESENT if rootless else DependencyStatus.MISSING, True,
            "Rootless Podman is available without a host daemon socket."
            if rootless else "The selected profile requires a proven rootless container/sandbox runtime.",
            None if rootless else "Install and configure rootless Podman through the exact prerequisite preview; do not grant a host Docker socket.",
        ))
    disk_root = paths.data_dir
    while not disk_root.exists() and disk_root != disk_root.parent:
        disk_root = disk_root.parent
    available = shutil.disk_usage(disk_root).free
    minimum = 2 * 1024**3
    checks.append(_check(
        "disk_pressure", "Local storage pressure", "resource",
        DependencyStatus.PRESENT if available >= minimum else DependencyStatus.BLOCKED,
        True,
        "The active XDG data filesystem has sufficient free capacity for Core lifecycle checkpoints."
        if available >= minimum else "The active XDG data filesystem is below the safe Core checkpoint floor.",
        None if available >= minimum else "Free storage or select a smaller profile before installation/update.",
    ))
    policy_path = ROOT / "config" / "install" / "update_trust.yaml"
    trust = public_trust_state(policy_path)
    checks.append(_check(
        "updater_signature_trust", "Updater signature trust", "update",
        DependencyStatus.PRESENT if trust.get("verification_ready") else DependencyStatus.BLOCKED,
        False,
        "An approved package-owned public Ed25519 updater key is active for explicit Local Admin lifecycle approval; no private key is present."
        if trust.get("verification_ready") else
        "Updater verification fails closed because no valid package-owned production public-key policy is active.",
        None if trust.get("verification_ready") else "Complete the signing/updater key decision packet; never place private key bytes in Elysia state or evidence.",
    ))
    return checks


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path_writable(path: Path) -> bool:
    if path.exists():
        return path.is_dir() and os.access(path, os.W_OK)
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent.is_dir() and os.access(parent, os.W_OK)


def _loopback_reachable(
    url: str, *, timeout: float = 3.0, attempts: int = 3
) -> bool:
    if not (url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")):
        return False
    for _attempt in range(max(1, attempts)):
        try:
            with urlopen(url, timeout=timeout) as response:
                return 200 <= int(getattr(response, "status", 200)) < 500
        except (OSError, URLError, TimeoutError, ValueError):
            continue
    return False


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _semantic_projection_check(paths: ElysiaPaths, *, probe: bool) -> DoctorCheck:
    """Inspect the optional profile without installing, starting, or repairing."""
    from app.cognition.semantic_projection import (
        SemanticProjectionConfig,
        SemanticProjectionError,
    )

    try:
        config = SemanticProjectionConfig.load(paths)
    except SemanticProjectionError:
        return _check(
            "semantic_projection_service", "Local semantic projection", "cognition",
            DependencyStatus.DEGRADED, False,
            "The optional semantic profile configuration failed its loopback, version, or permission contract.",
            "Repair the explicit semantic profile configuration; doctor did not modify it.",
        )
    if config is None or not config.enabled:
        return _check(
            "semantic_projection_service", "Local semantic projection", "cognition",
            DependencyStatus.OPTIONAL_MISSING, False,
            "The production hybrid retrieval capability is available but its optional local profile is not installed/enabled; FTS5 remains ready.",
        )
    if not probe:
        return _check(
            "semantic_projection_service", "Local semantic projection", "cognition",
            DependencyStatus.UNKNOWN, False,
            "The optional semantic profile is configured; authenticated loopback reachability was not probed.",
        )
    try:
        key_path = config.api_key_path
        if not key_path.is_file() or key_path.is_symlink() or key_path.stat().st_mode & 0o077:
            raise OSError("unsafe API-key contract")
        request = Request(
            config.qdrant_url + "/collections",
            headers={"api-key": key_path.read_text(encoding="utf-8").strip()},
        )
        with urlopen(request, timeout=3.0) as response:
            payload = json.loads(response.read(2 * 1024 * 1024))
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise ValueError("invalid authenticated response")
        with urlopen(config.ollama_url + "/api/tags", timeout=3.0) as response:
            model_payload = json.loads(response.read(2 * 1024 * 1024))
        names = {
            str(item.get("name") or "")
            for item in (model_payload.get("models") or [])
            if isinstance(item, dict)
        }
        if config.model not in names:
            raise ValueError("promoted embedding model absent")
    except Exception:
        return _check(
            "semantic_projection_service", "Local semantic projection", "cognition",
            DependencyStatus.DEGRADED, False,
            "The configured authenticated loopback Qdrant service or pinned Qwen embedding model was unavailable; canonical Memory and FTS5 remain functional.",
            "Start/verify the Elysia-owned semantic profile and local model, then rebuild its derived projection.",
        )
    return _check(
        "semantic_projection_service", "Local semantic projection", "cognition",
        DependencyStatus.PRESENT, False,
        "Authenticated REST-only Qdrant and the pinned local Qwen embedding model responded on loopback; the normal-memory projection is derived and rebuildable.",
    )


def _neurofabric_runtime_check(
    paths: ElysiaPaths, selected_components: set[str], *, probe: bool
) -> DoctorCheck:
    if "scientific_engineering" not in selected_components:
        return _check(
            "neurofabric_runtime", "Isolated Neurofabric runtime", "compute",
            DependencyStatus.PROFILE_GATED, False,
            "The optional CPU and CUDA Neurofabric profiles are not selected; packaged Core contains no Torch runtime.",
        )
    receipt = _safe_json(paths.state_dir / "install" / "components" / "scientific_engineering.json")
    lock_name = str((receipt or {}).get("lock_name") or "")
    selected = "cuda" if "cuda" in lock_name else "cpu" if "cpu" in lock_name else None
    executable = resolve_component_runtime_root(paths) / "elysia_neurofabric" / "bin" / "python"
    if not receipt or receipt.get("status") != "ready" or selected is None or not executable.is_file():
        return _check(
            "neurofabric_runtime", "Isolated Neurofabric runtime", "compute",
            DependencyStatus.MISSING, True,
            "The selected Scientific/Engineering profile has no exact ready Neurofabric environment receipt.",
            "Install or repair the hardware-selected Elysia-owned Neurofabric environment from its exact lock.",
        )
    if not probe:
        return _check(
            "neurofabric_runtime", "Isolated Neurofabric runtime", "compute",
            DependencyStatus.UNKNOWN, True,
            f"The {selected.upper()} Neurofabric profile is selected; bounded environment/device proof was not requested.",
            "Run the local-services doctor proof before enabling Neurofabric work.",
        )
    command = [str(executable), "-c"] if os.access(executable, os.X_OK) else []
    probe_code = (
        "import importlib.metadata,json,torch;"
        "x=torch.arange(4,dtype=torch.float32);"
        "print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,"
        "'available':torch.cuda.is_available(),'devices':torch.cuda.device_count(),"
        "'cpu_ok':bool((x+x).tolist()==[0.0,2.0,4.0,6.0]),"
        "'ncps':importlib.metadata.version('ncps')}))"
    )
    if not command:
        result = None
    else:
        try:
            result = subprocess.run(
                [*command, probe_code], capture_output=True, text=True,
                timeout=180, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
    try:
        payload = json.loads((result.stdout if result else "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        payload = {}
    cpu_ready = bool(payload.get("cpu_ok") and payload.get("ncps"))
    cuda_ready = bool(payload.get("cuda") and payload.get("available") and int(payload.get("devices") or 0) > 0)
    ready = cpu_ready and (selected == "cpu" or cuda_ready)
    return _check(
        "neurofabric_runtime", "Isolated Neurofabric runtime", "compute",
        DependencyStatus.PRESENT if ready else DependencyStatus.DEGRADED,
        True,
        (
            f"The selected {selected.upper()} Neurofabric profile passed isolated Torch, NCPS, CPU"
            + (", and CUDA device" if selected == "cuda" else " fallback")
            + " proof; packaged Core remains independent."
            if ready else
            f"The selected {selected.upper()} Neurofabric profile failed its isolated runtime/device proof; Core remains available without it."
        ),
        None if ready else "Repair only the explicit elysia_neurofabric environment, then rerun doctor; do not install Torch into Core.",
    )


def _check(
    check_id: str,
    label: str,
    category: str,
    status: DependencyStatus,
    required: bool,
    summary: str,
    remediation: str | None = None,
) -> DoctorCheck:
    classification = {
        DependencyStatus.PRESENT: "ready",
        DependencyStatus.MISSING: "missing",
        DependencyStatus.OPTIONAL_MISSING: "missing",
        DependencyStatus.BLOCKED: "blocked",
        DependencyStatus.DEGRADED: "degraded",
        DependencyStatus.UNKNOWN: "degraded",
        DependencyStatus.PROFILE_GATED: "not_selected",
        DependencyStatus.LAB_GATED: "not_selected",
        DependencyStatus.NOT_APPLICABLE: "not_selected",
    }[status]
    return DoctorCheck(
        check_id=check_id,
        label=label,
        category=category,
        status=status,
        classification=classification,
        required=required,
        summary=summary,
        remediation=remediation,
    )


def _memory_fabric_check(paths: ElysiaPaths) -> DoctorCheck:
    """Inspect canonical memory without creating, repairing, or exposing its path."""
    database = paths.memory_database_path
    if not database.exists():
        return _check(
            "canonical_memory_fabric",
            "Canonical Memory Fabric",
            "memory",
            DependencyStatus.PRESENT,
            True,
            "The XDG-local Memory Fabric is ready for first-account initialization.",
        )
    if not database.is_file() or database.is_symlink():
        return _check(
            "canonical_memory_fabric",
            "Canonical Memory Fabric",
            "memory",
            DependencyStatus.MISSING,
            True,
            "The canonical memory authority is not a safe regular database file.",
            "Restore from a verified private backup; doctor will not modify memory.",
        )
    try:
        mode = database.stat().st_mode & 0o777
        with database.open("rb") as handle:
            header = handle.read(16)
        if header != b"SQLite format 3\x00":
            raise sqlite3.DatabaseError("invalid database header")
        uri = f"file:{database.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()
            version = conn.execute("SELECT MAX(schema_version) FROM schema_migrations").fetchone()
            foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        if not integrity or str(integrity[0]).lower() != "ok" or foreign_keys:
            raise sqlite3.DatabaseError("integrity check failed")
        if int((version or [0])[0] or 0) < 1:
            raise sqlite3.DatabaseError("schema version missing")
        if mode & 0o077:
            return _check(
                "canonical_memory_fabric",
                "Canonical Memory Fabric",
                "memory",
                DependencyStatus.DEGRADED,
                True,
                "The canonical memory database is healthy but its file permissions are too broad.",
                "Restrict the database to its owning user before using private memory.",
            )
        return _check(
            "canonical_memory_fabric",
            "Canonical Memory Fabric",
            "memory",
            DependencyStatus.PRESENT,
            True,
            "The single XDG-local Memory Fabric passed schema, integrity, and permission checks.",
        )
    except (OSError, sqlite3.Error, ValueError):
        # Keep recognizing the pre-Part-2E verified SQLite safety snapshots as
        # well as portable Elysia Memory Archives.  The latter supersede raw
        # snapshots for user-facing backup/restore, but an existing verified
        # snapshot remains truthful recovery evidence during an upgrade.
        backups_present = paths.memory_backup_dir.is_dir() and any(
            candidate.is_file() and not candidate.is_symlink()
            for pattern in ("*.elysia-memory-archive", "*.sqlite")
            for candidate in paths.memory_backup_dir.glob(pattern)
        )
        return _check(
            "canonical_memory_fabric",
            "Canonical Memory Fabric",
            "memory",
            DependencyStatus.MISSING,
            True,
            (
                "The canonical memory database failed a read-only integrity check; a private backup is available."
                if backups_present
                else "The canonical memory database failed a read-only integrity check and no private backup was found."
            ),
            "Enter maintenance and restore only from a verified private backup; doctor made no changes.",
        )


def _memory_release_check(paths: ElysiaPaths) -> DoctorCheck:
    """Read-only Part 2E object/archive/schema truth without private content."""

    try:
        zstd_version = importlib.metadata.version("zstandard")
    except importlib.metadata.PackageNotFoundError:
        return _check(
            "memory_release_closure", "Memory release lifecycle", "memory",
            DependencyStatus.MISSING, True,
            "The required Zstandard codec is absent from Core.",
            "Repair the pinned Core dependency profile; doctor did not install anything.",
        )
    if not paths.memory_database_path.exists():
        return _check(
            "memory_release_closure", "Memory release lifecycle", "memory",
            DependencyStatus.PRESENT, True,
            f"The Part 2E lifecycle is ready for first use with Zstandard {zstd_version}.",
        )
    try:
        uri = f"file:{paths.memory_database_path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as conn:
            conn.row_factory = sqlite3.Row
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required = {
                "memory_objects", "memory_object_refs", "memory_cold_revisions",
                "memory_graph_nodes", "memory_graph_edges", "memory_archive_registry",
                "memory_restore_plans", "memory_truth_events", "memory_tier_events",
            }
            version = int(
                conn.execute("SELECT COALESCE(MAX(schema_version),0) FROM schema_migrations").fetchone()[0]
            )
            archives = [
                dict(row)
                for row in conn.execute(
                    "SELECT path_token,size_bytes,checksum FROM memory_archive_registry"
                ).fetchall()
            ]
        if version < 3 or not required.issubset(tables):
            raise sqlite3.DatabaseError("Part 2E schema missing")
        for archive in archives:
            candidate = paths.memory_backup_dir / str(archive["path_token"])
            if (
                not candidate.is_file()
                or candidate.is_symlink()
                or candidate.stat().st_size != int(archive["size_bytes"])
                or _file_sha256(candidate) != str(archive["checksum"])
            ):
                raise sqlite3.DatabaseError("managed archive integrity failed")
        pack = paths.memory_blob_dir / "objects-v1" / "cold-pack-v1.sqlite"
        if pack.exists():
            if not pack.is_file() or pack.is_symlink() or pack.stat().st_mode & 0o077:
                raise sqlite3.DatabaseError("cold pack boundary failed")
            with sqlite3.connect(f"file:{pack.as_posix()}?mode=ro", uri=True, timeout=1.0) as conn:
                if str(conn.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                    raise sqlite3.DatabaseError("cold pack integrity failed")
        return _check(
            "memory_release_closure", "Memory release lifecycle", "memory",
            DependencyStatus.PRESENT, True,
            f"Part 2E schema v{version}, cold-pack, and {len(archives)} Elysia-held archive manifest(s) passed read-only checks with Zstandard {zstd_version}.",
        )
    except (OSError, sqlite3.Error, ValueError):
        return _check(
            "memory_release_closure", "Memory release lifecycle", "memory",
            DependencyStatus.DEGRADED, True,
            "The Part 2E schema, cold object pack, or managed archive manifest failed a read-only integrity check.",
            "Inspect Health and restore only from a verified encrypted archive; doctor made no changes.",
        )


def _sqlite_cognition_check(
    *,
    database: Path,
    check_id: str,
    label: str,
    expected_table: str,
    category: str,
    first_use_summary: str,
    healthy_summary: str,
    rebuildable: bool,
) -> DoctorCheck:
    """Inspect one Part 2C SQLite organ read-only, without creating or repairing it."""
    if not database.exists():
        return _check(
            check_id,
            label,
            category,
            DependencyStatus.PRESENT,
            True,
            first_use_summary,
        )
    if not database.is_file() or database.is_symlink():
        return _check(
            check_id,
            label,
            category,
            DependencyStatus.MISSING,
            True,
            f"{label} is not a safe regular database file.",
            "Rebuild the derived projection." if rebuildable else "Restore the XDG-local evidence authority from a verified private backup.",
        )
    try:
        mode = database.stat().st_mode & 0o777
        with database.open("rb") as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                raise sqlite3.DatabaseError("invalid database header")
        uri = f"file:{database.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
                (expected_table,),
            ).fetchone()
        if not integrity or str(integrity[0]).lower() != "ok" or table is None:
            raise sqlite3.DatabaseError("integrity or schema check failed")
        if mode & 0o077:
            return _check(
                check_id,
                label,
                category,
                DependencyStatus.DEGRADED,
                True,
                f"{label} is healthy but its file permissions are too broad.",
                "Restrict the database to its owning user.",
            )
        return _check(
            check_id,
            label,
            category,
            DependencyStatus.PRESENT,
            True,
            healthy_summary,
        )
    except (OSError, sqlite3.Error, ValueError):
        return _check(
            check_id,
            label,
            category,
            DependencyStatus.DEGRADED if rebuildable else DependencyStatus.MISSING,
            True,
            f"{label} failed its read-only integrity check.",
            "Rebuild from canonical normal memory; private and sealed content must remain excluded."
            if rebuildable
            else "Restore the XDG-local evidence authority from a verified private backup; doctor made no changes.",
        )


def _first_run_summary(paths: ElysiaPaths, auth: LocalApiAuthPolicy) -> dict[str, object]:
    required_roots = (
        paths.config_dir,
        paths.data_dir,
        paths.cache_dir,
        paths.state_dir,
        paths.runtime_dir,
    )
    roots_ready = all(path.is_dir() for path in required_roots)
    auth_ready = not auth.required or bool(auth.public_summary()["initialized"])
    doctor_recorded = (paths.doctor_state_dir / LAST_RUN_FILENAME).is_file()
    return {
        "state": "ready" if roots_ready and auth_ready else "not_ready",
        "required_directories_ready": roots_ready,
        "authentication_ready": auth_ready,
        "doctor_run_recorded": doctor_recorded,
        "profile_resolution_expected": True,
        "raw_paths_exposed": False,
    }


def run_doctor(
    *,
    paths: ElysiaPaths | None = None,
    auth_policy: LocalApiAuthPolicy | None = None,
    api_reachable: bool = True,
    probe_local_services: bool = False,
    profile_override_path: Path | None = None,
    model_override_path: Path | None = None,
    desktop_package_state: str | None = None,
) -> DoctorStatusData:
    """Inspect bounded local readiness without installing, repairing, or enabling."""
    resolved_paths = paths or resolve_elysia_paths()
    auth = auth_policy or build_local_api_auth_policy(
        paths=resolved_paths,
        initialize=False,
    )
    profile_kwargs: dict[str, Path] = {}
    if profile_override_path is not None:
        profile_kwargs["profile_override_path"] = profile_override_path
    if model_override_path is not None:
        profile_kwargs["model_override_path"] = model_override_path
    profile, _ = resolve_install_profile_status(**profile_kwargs)
    resolved_profile_ids = set(profile.resolved_profile_ids)
    codev_status = read_codev_install_status(resolved_paths)
    codev_repo_approval = read_codev_repo_approval_status(resolved_paths)
    desktop_state = (
        desktop_package_state
        if desktop_package_state is not None
        else os.environ.get("ELYSIA_DESKTOP_PACKAGE", "")
    ).strip().lower()
    desktop_present = desktop_state in {"present", "source-dev"}
    if desktop_package_state is None and not desktop_present:
        desktop_present = shutil.which("elysia-desktop") is not None
    desktop_compatible = desktop_present and API_VERSION == DESKTOP_VERSION

    checks: list[DoctorCheck] = []
    _, selected_components = _setup_component_selection(resolved_paths)
    component_checks = _component_checks(resolved_paths)
    component_check_by_id = {check.check_id: check for check in component_checks}
    for label, directory in (
        ("Config", resolved_paths.config_dir),
        ("Data", resolved_paths.data_dir),
        ("Cache", resolved_paths.cache_dir),
        ("State", resolved_paths.state_dir),
        ("Runtime", resolved_paths.runtime_dir),
    ):
        writable = _path_writable(directory)
        checks.append(
            _check(
                f"xdg_{label.lower()}",
                f"{label} location",
                "xdg",
                DependencyStatus.PRESENT if writable else DependencyStatus.MISSING,
                True,
                f"{label} uses the private XDG user location and is {'writable' if writable else 'not writable'}.",
                None if writable else "Correct user ownership or XDG environment configuration.",
            )
        )

    checks.append(
        _sqlite_contract_check(
            resolved_paths.identity_dir / "elysia_identity.sqlite",
            check_id="identity_account_db",
            label="Local Identity/account authority",
            tables={"users", "profiles", "sessions", "profile_photo_assets", "account_events"},
            first_use_summary="The private local Identity authority is ready for atomic first-account creation.",
        )
    )
    checks.append(
        _sqlite_contract_check(
            resolved_paths.identity_dir / "personal_onboarding.sqlite",
            check_id="onboarding_storage",
            label="Encrypted personal-onboarding storage",
            tables={"onboarding_state"},
            first_use_summary="Account-owned encrypted onboarding storage is ready for optional post-account use.",
        )
    )
    checks.append(
        _memory_fabric_check(resolved_paths)
    )
    checks.append(_memory_release_check(resolved_paths))
    checks.append(_backup_check(resolved_paths))
    checks.append(
        _sqlite_cognition_check(
            database=resolved_paths.memory_fts_database_path,
            check_id="memory_fts_projection",
            label="Normal-memory lexical projection",
            expected_table="memory_fts",
            category="cognition",
            first_use_summary="The rebuildable XDG-cache FTS5 projection is ready for first use.",
            healthy_summary="The normal-only FTS5 projection passed read-only integrity, schema, and permission checks.",
            rebuildable=True,
        )
    )
    semantic_check = _semantic_projection_check(
        resolved_paths, probe=probe_local_services
    )
    checks.append(semantic_check)
    neurofabric_check = _neurofabric_runtime_check(
        resolved_paths, selected_components, probe=probe_local_services
    )
    checks.append(neurofabric_check)
    checks.append(
        _sqlite_cognition_check(
            database=resolved_paths.evidence_database_path,
            check_id="research_evidence_authority",
            label="Research evidence authority",
            expected_table="evidence_records",
            category="cognition",
            first_use_summary="The XDG-local research evidence authority is ready for first use.",
            healthy_summary="The durable research evidence authority passed read-only integrity, schema, and permission checks.",
            rebuildable=False,
        )
    )
    checks.append(
        _check(
            "core_profile",
            "Core profile",
            "profile",
            DependencyStatus.PRESENT
            if not profile.missing_core_dependency_ids
            else DependencyStatus.MISSING,
            True,
            (
                "Core dependency contract is satisfied."
                if not profile.missing_core_dependency_ids
                else "One or more required Core dependencies are missing."
            ),
            None if not profile.missing_core_dependency_ids else "Review the Core dependency manifest; doctor does not install it.",
        )
    )
    searxng_required = "governed_research" in selected_components
    searxng_reachable = _loopback_reachable("http://127.0.0.1:8888/") if probe_local_services else False
    checks.append(
        _check(
            "searxng_reachability",
            "Governed SearXNG worker",
            "research",
            DependencyStatus.PRESENT if searxng_reachable
            else DependencyStatus.MISSING if probe_local_services and searxng_required
            else DependencyStatus.OPTIONAL_MISSING if probe_local_services
            else DependencyStatus.UNKNOWN if searxng_required
            else DependencyStatus.PROFILE_GATED,
            searxng_required,
            (
                "The loopback-only SearXNG endpoint responded; no public query was sent."
                if searxng_reachable
                else "The selected loopback SearXNG endpoint did not respond; no public query was sent."
                if probe_local_services and searxng_required
                else "The optional loopback SearXNG endpoint did not respond; no public query was sent."
                if probe_local_services
                else "Reachability was not probed for the selected research component."
                if searxng_required
                else "The governed research component is not selected."
            ),
            "Start the governed loopback SearXNG worker when Internet-enabled research is needed."
            if probe_local_services and not searxng_reachable
            else None,
        )
    )
    for dependency in profile.dependencies:
        dependency_status = DependencyStatus(dependency.status)
        dependency_summary = dependency.warning or dependency.purpose
        isolated_component_id = {
            "workstation": "component_workstation_adapters",
            "creator": "component_creator_perception",
        }.get(dependency.profile_id)
        isolated_component = component_check_by_id.get(isolated_component_id or "")
        isolated_environment_ready = bool(
            isolated_component
            and (
                isolated_component.status == DependencyStatus.PRESENT
                or (
                    dependency.profile_id == "creator"
                    and isolated_component.status == DependencyStatus.DEGRADED
                    and "environment is exact" in isolated_component.summary
                )
            )
        )
        if dependency.catalog_kind == "python" and isolated_environment_ready:
            dependency_status = DependencyStatus.PRESENT
            dependency_summary = (
                "The owning isolated component environment matches its exact release lock."
            )
        elif (
            dependency.profile_id == "semantic_local"
            and dependency.dependency_id
            in {"qdrant_loopback_service", "semantic_container_engine"}
            and semantic_check.status == DependencyStatus.PRESENT
            and component_check_by_id.get("component_semantic_retrieval")
            and component_check_by_id["component_semantic_retrieval"].status
            == DependencyStatus.PRESENT
        ):
            dependency_status = DependencyStatus.PRESENT
            dependency_summary = (
                "The exact managed semantic component and authenticated loopback service passed Doctor proof."
            )
        if dependency.dependency_id.startswith("neurofabric_") and dependency.profile_id in resolved_profile_ids:
            dependency_status = DependencyStatus(neurofabric_check.status)
            dependency_summary = neurofabric_check.summary
        if dependency.dependency_id == "elysia_tauri_desktop" and desktop_compatible:
            dependency_status = DependencyStatus.PRESENT
            dependency_summary = "The active Desktop/API contract versions are aligned."
        elif dependency.dependency_id == "vscode" and (
            shutil.which("code") is not None or shutil.which("codium") is not None
        ):
            dependency_status = DependencyStatus.PRESENT
            dependency_summary = "A compatible VS Code-family host command is present; no editor was launched."
        elif dependency.dependency_id == "codev_vsix":
            dependency_status = (
                DependencyStatus.PRESENT
                if codev_status["compatible"]
                else DependencyStatus.DEGRADED
                if codev_status["installed"]
                else DependencyStatus.MISSING
            )
            dependency_summary = (
                "The official Codev extension receipt matches the expected version and local API contract."
                if codev_status["compatible"]
                else "A Codev install receipt exists but its version or API contract is incompatible."
                if codev_status["installed"]
                else "The official Codev extension receipt is missing; doctor did not install it."
            )
        checks.append(
            _check(
                f"dependency_{dependency.dependency_id}",
                dependency.label,
                f"dependency_{dependency.category}",
                dependency_status,
                bool(dependency.required and dependency.profile_id in resolved_profile_ids),
                dependency_summary,
                (
                    "Review the owning profile dependency contract; doctor does not install it."
                    if dependency_status
                    in {
                        DependencyStatus.MISSING,
                        DependencyStatus.OPTIONAL_MISSING,
                        DependencyStatus.UNKNOWN,
                    }
                    else None
                ),
            )
        )
    checks.append(
        _check(
            "codev_contract",
            "Codev Developer-profile contract",
            "developer",
            DependencyStatus.PRESENT
            if codev_status["compatible"]
            else DependencyStatus.DEGRADED
            if codev_status["installed"]
            else DependencyStatus.PROFILE_GATED
            if "developer" not in resolved_profile_ids
            else DependencyStatus.MISSING,
            "developer" in resolved_profile_ids,
            (
                "Codev version and local coding API contract are aligned."
                if codev_status["compatible"]
                else "Developer profile is not selected; Codev remains optional."
                if "developer" not in resolved_profile_ids
                else "Install or reconcile the official Codev VSIX through the explicit Developer-profile installer."
            ),
            None
            if codev_status["compatible"] or "developer" not in resolved_profile_ids
            else "Run the explicit Codev installer with a reviewed local VSIX, then rerun doctor.",
        )
    )
    checks.append(
        _check(
            "codev_repo_approval",
            "Codev exact repository approval",
            "developer",
            DependencyStatus.PRESENT
            if codev_repo_approval["approved_repo_count"]
            else DependencyStatus.OPTIONAL_MISSING,
            False,
            (
                f"{codev_repo_approval['approved_repo_count']} exact repository approval(s) are active; no path is exposed."
                if codev_repo_approval["approved_repo_count"]
                else "No repository is approved; Codev remains read-only until exact local approval."
            ),
            None,
        )
    )
    checks.append(
        _check(
            "local_api",
            "Local API",
            "runtime",
            DependencyStatus.PRESENT if api_reachable else DependencyStatus.MISSING,
            True,
            "The governed loopback API is reachable." if api_reachable else "The governed loopback API is not reachable.",
            None if api_reachable else "Start the fixed Elysia API launcher and rerun verification.",
        )
    )
    auth_initialized = bool(auth.public_summary()["initialized"])
    checks.append(
        _check(
            "local_api_auth",
            "Local API authentication",
            "security",
            DependencyStatus.PRESENT
            if (not auth.required or auth_initialized)
            else DependencyStatus.MISSING,
            True,
            (
                "Mutating local API calls require a private runtime credential."
                if auth.required and auth_initialized
                else "Source development mode is explicit; packaged mode will require authentication."
                if not auth.required
                else "The required packaged-mode credential is not initialized."
            ),
            None if (not auth.required or auth_initialized) else "Initialize Elysia through the packaged API launcher.",
        )
    )
    checks.append(
        _check(
            "desktop_api_contract",
            "Desktop/API compatibility",
            "contract",
            DependencyStatus.PRESENT if desktop_compatible else DependencyStatus.UNKNOWN,
            True,
            (
                "The active Desktop and API contract versions are aligned."
                if desktop_compatible
                else "Desktop package/source-session proof is not active for this doctor run."
            ),
            None if desktop_compatible else "Run doctor from the packaged Desktop lifecycle or explicit source launcher.",
        )
    )

    provider_required = "local_model_provider" in selected_components
    provider_reachable = _loopback_reachable("http://127.0.0.1:11434/api/tags") if probe_local_services else False
    checks.append(
        _check(
            "ollama_reachability",
            "Local model provider",
            "provider",
            DependencyStatus.PRESENT if provider_reachable
            else DependencyStatus.MISSING if probe_local_services and provider_required
            else DependencyStatus.OPTIONAL_MISSING if probe_local_services
            else DependencyStatus.UNKNOWN if provider_required
            else DependencyStatus.PROFILE_GATED,
            provider_required,
            (
                "The loopback Ollama endpoint responded; no model was loaded."
                if provider_reachable
                else "The selected loopback provider did not respond; no download was attempted."
                if probe_local_services and provider_required
                else "The optional loopback provider did not respond; no download was attempted."
                if probe_local_services
                else "Reachability was not probed for the selected provider."
                if provider_required
                else "No local model provider is selected."
            ),
            "Install/configure an optional local provider, or continue with degraded model capability."
            if probe_local_services and not provider_reachable
            else None,
        )
    )
    for worker in profile.worker_summaries:
        checks.append(
            _check(
                f"worker_{worker.worker_id}",
                worker.label,
                "worker",
                DependencyStatus(worker.status),
                False,
                worker.note,
                "A later profile-specific doctor and local isolation proof are required."
                if worker.doctor_proof_required
                else None,
            )
        )

    checks.extend(component_checks)
    checks.extend(_system_and_resource_checks(resolved_paths, selected_components))

    counts = Counter(str(check.status) for check in checks)
    status_counts = {status.value: int(counts.get(status.value, 0)) for status in DependencyStatus}
    required_failed = any(
        check.required
        and check.status
        in {
            DependencyStatus.MISSING,
            DependencyStatus.BLOCKED,
            DependencyStatus.DEGRADED,
            DependencyStatus.UNKNOWN,
        }
        for check in checks
    )
    overall = DependencyStatus.DEGRADED if required_failed else DependencyStatus.PRESENT
    optional_ready = not any(
        not check.required
        and check.status
        in {
            DependencyStatus.MISSING,
            DependencyStatus.OPTIONAL_MISSING,
            DependencyStatus.UNKNOWN,
            DependencyStatus.BLOCKED,
            DependencyStatus.DEGRADED,
            DependencyStatus.PROFILE_GATED,
            DependencyStatus.LAB_GATED,
        }
        for check in checks
    )
    return DoctorStatusData(
        doctor_version=DOCTOR_VERSION,
        overall_status=overall,
        runtime_mode=resolved_paths.mode.value,
        active_profile_id=profile.active_profile_id,
        checks=checks,
        status_counts=status_counts,
        core_ready=not required_failed,
        optional_profiles_ready=optional_ready,
        local_api_reachable=api_reachable,
        local_auth=auth.public_summary(),
        path_contract=resolved_paths.public_summary(),
        first_run=_first_run_summary(resolved_paths, auth),
        desktop_api_compatible=desktop_compatible,
        worker_execution_enabled=False,
        install_authority_available=False,
        repair_authority_available=False,
        raw_paths_exposed=False,
        generated_at_utc=_utc_now_iso(),
    )


def record_doctor_result(data: DoctorStatusData, *, paths: ElysiaPaths | None = None) -> None:
    """Write a sanitized doctor receipt; it contains no paths, tokens, or host details."""
    resolved_paths = paths or resolve_elysia_paths()
    resolved_paths.doctor_state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "doctor_version": data.doctor_version,
        "overall_status": data.overall_status,
        "core_ready": data.core_ready,
        "active_profile_id": data.active_profile_id,
        "generated_at_utc": data.generated_at_utc,
        "raw_paths_exposed": False,
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=resolved_paths.doctor_state_dir,
        prefix=".doctor-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(resolved_paths.doctor_state_dir / LAST_RUN_FILENAME)


def get_doctor_status(*, probe_local_services: bool = False) -> dict[str, Any]:
    request_id = f"req_doctor_{uuid4().hex[:16]}"
    try:
        data = run_doctor(probe_local_services=probe_local_services)
        degraded = data.overall_status != DependencyStatus.PRESENT
        envelope = build_response_envelope(
            status=EnvelopeStatus.DEGRADED if degraded else EnvelopeStatus.OK,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="install_doctor_status",
            capability_state=CapabilityState.DEGRADED if degraded else CapabilityState.LIVE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            warnings=[] if not degraded else ["One or more required Core readiness checks need attention."],
            errors=[],
            trace_summary=TraceSummary(
                route_used="status.doctor",
                log_written=False,
                journal_written=False,
            ),
            data=data,
        )
        return envelope.to_payload()
    except Exception:
        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="install_doctor_status",
            capability_state=CapabilityState.UNAVAILABLE,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            warnings=[],
            errors=["Install doctor could not validate the local contracts."],
            trace_summary=TraceSummary(route_used="status.doctor", log_written=False, journal_written=False),
            data={},
        )
        return envelope.to_payload()


__all__ = (
    "CONTRACT_VERSION",
    "DOCTOR_VERSION",
    "LAST_RUN_FILENAME",
    "get_doctor_status",
    "record_doctor_result",
    "run_doctor",
)
