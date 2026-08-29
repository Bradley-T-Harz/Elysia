"""Metadata-only resolution of exact install artifacts from a hash lock.

Resolution reads public package metadata and performs HEAD requests; it never
downloads artifact bodies. The resulting immutable plan supplies exact transfer
sizes, filenames, URLs, and SHA-256 identities before acquisition approval.
An explicitly allow-listed sdist may be selected only when upstream publishes
no compatible wheel and the deterministic source-to-wheel policy is exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen
import yaml

from packaging.specifiers import SpecifierSet
from packaging.tags import Tag, sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")
HASH = re.compile(r"--hash=sha256:([a-f0-9]{64})")
INDEX = re.compile(r"^--(?:extra-)?index-url\s+(https://[^\s]+)$")


class PythonArtifactResolutionError(RuntimeError):
    """A lock cannot be mapped to one exact compatible wheel per package."""


ROOT = Path(__file__).resolve().parents[2]
SOURCE_BUILD_POLICY = ROOT / "config" / "install" / "python_source_builds.yaml"


@dataclass(frozen=True)
class LockedRequirement:
    name: str
    version: str
    hashes: frozenset[str]


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def parse_locked_requirements(path: Path) -> tuple[list[str], list[LockedRequirement]]:
    if not path.is_file() or path.is_symlink():
        raise PythonArtifactResolutionError("The exact Python lock is unavailable or unsafe.")
    indexes: list[str] = []
    rows: list[LockedRequirement] = []
    active_name: str | None = None
    active_version: str | None = None
    active_hashes: set[str] = set()

    def flush() -> None:
        nonlocal active_name, active_version, active_hashes
        if active_name is None:
            return
        if not active_hashes:
            raise PythonArtifactResolutionError(
                f"The Python lock pin {active_name} has no artifact hash."
            )
        rows.append(LockedRequirement(active_name, str(active_version), frozenset(active_hashes)))
        active_name = None
        active_version = None
        active_hashes = set()

    for source_line in path.read_text(encoding="utf-8").splitlines():
        stripped = source_line.strip()
        index_match = INDEX.match(stripped)
        if index_match and index_match.group(1) not in indexes:
            indexes.append(index_match.group(1).rstrip("/"))
        pin_match = PIN.match(stripped)
        if pin_match:
            flush()
            active_name = canonicalize_name(pin_match.group(1))
            active_version = pin_match.group(2)
        for digest in HASH.findall(stripped):
            if active_name is None:
                raise PythonArtifactResolutionError("The lock contains an orphan artifact hash.")
            active_hashes.add(digest)
    flush()
    if not rows:
        raise PythonArtifactResolutionError("The lock contains no exact package pins.")
    if not indexes:
        indexes = ["https://pypi.org/simple"]
    return indexes, rows


def _compatible(filename: str, supported: dict[Tag, int]) -> int | None:
    try:
        _, _, _, tags = parse_wheel_filename(filename)
    except Exception:
        return None
    ranks = [supported[tag] for tag in tags if tag in supported]
    return min(ranks) if ranks else None


def _python_allows(specifier: str | None, python_version: str) -> bool:
    if not specifier:
        return True
    try:
        return Version(python_version) in SpecifierSet(specifier)
    except Exception:
        return False


def _json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Elysia-Setup/1.0"})
    with urlopen(request, timeout=timeout) as response:
        if int(getattr(response, "status", 200)) != 200:
            raise PythonArtifactResolutionError("A package metadata authority did not return success.")
        payload = json.loads(response.read(16 * 1024 * 1024))
    if not isinstance(payload, dict):
        raise PythonArtifactResolutionError("A package metadata response was invalid.")
    return payload


def _content_length(url: str, timeout: float) -> int:
    request = Request(url, method="HEAD", headers={"User-Agent": "Elysia-Setup/1.0"})
    with urlopen(request, timeout=timeout) as response:
        value = response.headers.get("Content-Length")
    try:
        size = int(value or "")
    except ValueError as exc:
        raise PythonArtifactResolutionError("An exact wheel transfer size was unavailable.") from exc
    if size <= 0:
        raise PythonArtifactResolutionError("An exact wheel transfer size was unavailable.")
    return size


def _pypi_candidates(
    requirement: LockedRequirement,
    *,
    supported: dict[Tag, int],
    python_version: str,
    timeout: float,
) -> list[dict[str, Any]]:
    try:
        payload = _json(
            f"https://pypi.org/pypi/{requirement.name}/{requirement.version}/json",
            timeout,
        )
    except Exception:
        return []
    candidates: list[dict[str, Any]] = []
    for item in payload.get("urls") or []:
        if not isinstance(item, dict) or item.get("packagetype") != "bdist_wheel" or item.get("yanked"):
            continue
        digest = str((item.get("digests") or {}).get("sha256") or "")
        filename = str(item.get("filename") or "")
        rank = _compatible(filename, supported)
        if digest not in requirement.hashes or rank is None:
            continue
        if not _python_allows(item.get("requires_python"), python_version):
            continue
        size = int(item.get("size") or 0)
        url = str(item.get("url") or "")
        if size <= 0 or not url.startswith("https://"):
            continue
        candidates.append({
            "artifact_type": "wheel",
            "filename": filename,
            "sha256": digest,
            "size_bytes": size,
            "url": url,
            "source_authority": "pypi_json",
            "compatibility_rank": rank,
        })
    return candidates


def _source_build_policy(requirement: LockedRequirement) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    try:
        payload = yaml.safe_load(SOURCE_BUILD_POLICY.read_text(encoding="utf-8"))
        record = payload["source_builds"][requirement.name]
        tools = payload["build_tools"]
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return None
    if (
        payload.get("contract_version") != "elysia-python-source-builds-1.0"
        or payload.get("rules", {}).get("unlisted_source_builds_allowed") is not False
        or str(record.get("version")) != requirement.version
        or not isinstance(tools, list)
        or not tools
    ):
        raise PythonArtifactResolutionError(
            f"The approved source-build policy for {requirement.name} is invalid."
        )
    source = record.get("source") or {}
    output = record.get("output") or {}
    build = record.get("build") or {}
    if (
        str(source.get("sha256")) not in requirement.hashes
        or str(output.get("sha256")) not in requirement.hashes
        or int(source.get("size_bytes") or 0) <= 0
        or not str(source.get("url") or "").startswith("https://files.pythonhosted.org/")
        or not str(source.get("filename") or "").endswith((".tar.gz", ".zip"))
        or not str(output.get("filename") or "").endswith(".whl")
        or build.get("backend") != "setuptools_legacy"
        or int(build.get("source_date_epoch") or 0) <= 0
        or not re.fullmatch(r"0[0-7]{3}", str(build.get("umask") or ""))
    ):
        raise PythonArtifactResolutionError(
            f"The approved source-build identities for {requirement.name} are invalid."
        )
    normalized_tools: list[dict[str, Any]] = []
    for tool in tools:
        if (
            not isinstance(tool, dict)
            or int(tool.get("size_bytes") or 0) <= 0
            or len(str(tool.get("sha256") or "")) != 64
            or not str(tool.get("filename") or "").endswith(".whl")
            or not str(tool.get("url") or "").startswith("https://files.pythonhosted.org/")
        ):
            raise PythonArtifactResolutionError("The exact source-build toolchain is invalid.")
        normalized_tools.append(dict(tool))
    return dict(record), normalized_tools


def _pypi_sdist_candidate(
    requirement: LockedRequirement,
    policy: dict[str, Any],
    *,
    python_version: str,
    timeout: float,
) -> dict[str, Any] | None:
    try:
        payload = _json(
            f"https://pypi.org/pypi/{requirement.name}/{requirement.version}/json",
            timeout,
        )
    except Exception:
        return None
    source = policy["source"]
    for item in payload.get("urls") or []:
        if not isinstance(item, dict) or item.get("packagetype") != "sdist" or item.get("yanked"):
            continue
        digest = str((item.get("digests") or {}).get("sha256") or "")
        candidate = {
            "artifact_type": "sdist",
            "filename": str(item.get("filename") or ""),
            "sha256": digest,
            "size_bytes": int(item.get("size") or 0),
            "url": str(item.get("url") or ""),
        }
        expected = {
            "artifact_type": "sdist",
            "filename": str(source["filename"]),
            "sha256": str(source["sha256"]),
            "size_bytes": int(source["size_bytes"]),
            "url": str(source["url"]),
        }
        if candidate != expected or digest not in requirement.hashes:
            continue
        if not _python_allows(item.get("requires_python"), python_version):
            continue
        return {
            **candidate,
            "source_authority": "pypi_json",
            "build_policy": {
                "output": dict(policy["output"]),
                "build": dict(policy["build"]),
                "license": str(policy["license"]),
                "redistribution": str(policy["redistribution"]),
            },
        }
    return None


def _simple_candidates(
    requirement: LockedRequirement,
    indexes: list[str],
    *,
    supported: dict[Tag, int],
    timeout: float,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index in indexes:
        project_url = f"{index.rstrip('/')}/{requirement.name}/"
        try:
            request = Request(project_url, headers={"Accept": "text/html", "User-Agent": "Elysia-Setup/1.0"})
            with urlopen(request, timeout=timeout) as response:
                body = response.read(16 * 1024 * 1024).decode("utf-8", errors="replace")
        except Exception:
            continue
        parser = _Links()
        parser.feed(body)
        for href in parser.hrefs:
            url = urljoin(project_url, href)
            parsed = urlparse(url)
            fragment = parsed.fragment
            digest = fragment.split("sha256=", 1)[1].split("&", 1)[0] if "sha256=" in fragment else ""
            filename = unquote(Path(parsed.path).name)
            if digest not in requirement.hashes or not filename.endswith(".whl"):
                continue
            rank = _compatible(filename, supported)
            if rank is None:
                continue
            clean_url = parsed._replace(fragment="").geturl()
            try:
                size = _content_length(clean_url, timeout)
            except Exception:
                continue
            candidates.append({
                "artifact_type": "wheel",
                "filename": filename,
                "sha256": digest,
                "size_bytes": size,
                "url": clean_url,
                "source_authority": "approved_simple_index",
                "compatibility_rank": rank,
            })
    return candidates


def resolve_hash_locked_wheels(
    lock_path: Path,
    *,
    python_version: str = "3.12",
    timeout: float = 20.0,
) -> dict[str, Any]:
    indexes, requirements = parse_locked_requirements(lock_path)
    supported = {tag: index for index, tag in enumerate(sys_tags())}
    artifacts: list[dict[str, Any]] = []
    build_tools: list[dict[str, Any]] = []
    for requirement in requirements:
        candidates = _pypi_candidates(
            requirement, supported=supported, python_version=python_version, timeout=timeout
        )
        if not candidates:
            candidates = _simple_candidates(
                requirement, indexes, supported=supported, timeout=timeout
            )
        if not candidates:
            policy_result = _source_build_policy(requirement)
            selected = None
            if policy_result is not None:
                policy, tools = policy_result
                selected = _pypi_sdist_candidate(
                    requirement, policy, python_version=python_version, timeout=timeout
                )
                if selected is not None:
                    for tool in tools:
                        if tool not in build_tools:
                            build_tools.append(tool)
            if selected is None:
                raise PythonArtifactResolutionError(
                    f"No approved exact compatible wheel or bounded source build could be resolved for {requirement.name}=={requirement.version}."
                )
        else:
            selected = sorted(candidates, key=lambda item: (int(item["compatibility_rank"]), str(item["filename"])))[0]
        artifacts.append({
            "package": requirement.name,
            "version": requirement.version,
            **selected,
        })
    unique_downloads = {
        str(item["sha256"]): item
        for item in [*artifacts, *build_tools]
    }
    return {
        "contract_version": "elysia-python-artifact-plan-1.0",
        "python": python_version,
        "artifact_count": len(unique_downloads),
        "exact_download_bytes": sum(
            int(item["size_bytes"]) for item in unique_downloads.values()
        ),
        "artifacts": artifacts,
        "build_tools": build_tools,
        "source_build_count": sum(item["artifact_type"] == "sdist" for item in artifacts),
        "wheel_bodies_downloaded": False,
        "artifact_bodies_downloaded": False,
        "metadata_network_used": True,
    }


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Resolve one exact metadata-only Elysia wheel plan.")
    parser.add_argument("lock", type=Path)
    arguments = parser.parse_args()
    plan = resolve_hash_locked_wheels(arguments.lock.resolve(strict=True))
    print(json.dumps({
        "contract_version": plan["contract_version"],
        "python": plan["python"],
        "artifact_count": plan["artifact_count"],
        "exact_download_bytes": plan["exact_download_bytes"],
        "wheel_bodies_downloaded": plan["wheel_bodies_downloaded"],
        "metadata_network_used": plan["metadata_network_used"],
    }, sort_keys=True))
    return 0


__all__ = (
    "LockedRequirement",
    "PythonArtifactResolutionError",
    "parse_locked_requirements",
    "resolve_hash_locked_wheels",
)


if __name__ == "__main__":
    raise SystemExit(_main())
