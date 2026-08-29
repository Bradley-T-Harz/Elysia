"""Strict public Python lock parsing and installed-environment verification."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
import re
from packaging.utils import canonicalize_name


PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")


class PythonLockError(RuntimeError):
    """A Python lock or environment differs from release truth."""


def parse_hash_lock(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise PythonLockError("The exact Python lock is unavailable or unsafe.")
    text = path.read_text(encoding="utf-8")
    pins: dict[str, str] = {}
    active_pin: str | None = None
    active_pin_has_hash = False
    for line in text.splitlines():
        stripped = line.strip()
        match = PIN_PATTERN.match(stripped)
        if not match:
            if stripped.startswith("--hash=sha256:"):
                if active_pin is None:
                    raise PythonLockError(
                        "The Python lock contains an orphan artifact hash without a package pin."
                    )
                active_pin_has_hash = True
            continue
        if active_pin is not None and not active_pin_has_hash:
            raise PythonLockError(
                f"The Python lock pin {active_pin} has no artifact hash."
            )
        name = canonicalize_name(match.group(1))
        version = match.group(2)
        if name in pins and pins[name] != version:
            raise PythonLockError("The Python lock contains conflicting exact versions.")
        pins[name] = version
        active_pin = name
        active_pin_has_hash = "--hash=sha256:" in stripped
    if active_pin is not None and not active_pin_has_hash:
        raise PythonLockError(f"The Python lock pin {active_pin} has no artifact hash.")
    if not pins:
        raise PythonLockError("The Python lock contains no exact package pins.")
    if "--hash=sha256:" not in text:
        raise PythonLockError("The Python lock does not contain artifact hashes.")
    return pins


def installed_versions() -> dict[str, str]:
    return {
        canonicalize_name(distribution.metadata["Name"]): distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }


def compare_environment_to_lock(
    path: Path,
    *,
    installed: dict[str, str] | None = None,
) -> dict[str, object]:
    pins = parse_hash_lock(path)
    observed = installed if installed is not None else installed_versions()
    missing = sorted(name for name in pins if name not in observed)
    mismatched = sorted([
        {"name": name, "expected": version, "actual": observed[name]}
        for name, version in pins.items()
        if name in observed and observed[name] != version
    ], key=lambda item: str(item["name"]))
    return {
        "expected_count": len(pins),
        "missing": missing,
        "mismatched": mismatched,
        "matches": not missing and not mismatched,
        "additional_packages_ignored": True,
    }


def merge_hash_locks(paths: list[Path] | tuple[Path, ...]) -> dict[str, str]:
    """Merge exact hash locks, rejecting conflicting component definitions."""

    merged: dict[str, str] = {}
    for path in paths:
        for name, version in parse_hash_lock(path).items():
            if name in merged and merged[name] != version:
                raise PythonLockError(
                    f"The selected Python locks conflict for {name}."
                )
            merged[name] = version
    if not merged:
        raise PythonLockError("No Python locks were selected.")
    return merged


def compare_environment_to_locks_exact(
    paths: list[Path] | tuple[Path, ...],
    *,
    installed: dict[str, str] | None = None,
    allowed_additional: set[str] | frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Verify an exact compositional build universe, including absence of extras."""

    pins = merge_hash_locks(paths)
    observed = installed if installed is not None else installed_versions()
    allowed = {canonicalize_name(name) for name in allowed_additional}
    missing = sorted(name for name in pins if name not in observed)
    mismatched = sorted([
        {"name": name, "expected": version, "actual": observed[name]}
        for name, version in pins.items()
        if name in observed and observed[name] != version
    ], key=lambda item: str(item["name"]))
    unexpected = sorted(set(observed).difference(pins).difference(allowed))
    return {
        "expected_count": len(pins),
        "missing": missing,
        "mismatched": mismatched,
        "unexpected": unexpected,
        "allowed_additional": sorted(allowed),
        "matches": not missing and not mismatched and not unexpected,
        "additional_packages_ignored": False,
    }


def assert_environment_matches_lock(path: Path) -> None:
    comparison = compare_environment_to_lock(path)
    if not comparison["matches"]:
        raise PythonLockError(
            f"The selected Python environment differs from the exact release lock "
            f"(missing={comparison['missing']}, mismatched={comparison['mismatched']})."
        )


def assert_environment_matches_locks_exact(
    paths: list[Path] | tuple[Path, ...],
    *,
    allowed_additional: set[str] | frozenset[str] = frozenset(),
) -> None:
    comparison = compare_environment_to_locks_exact(
        paths,
        allowed_additional=allowed_additional,
    )
    if not comparison["matches"]:
        raise PythonLockError(
            "The selected Python build environment differs from the exact composed "
            f"release locks (missing={comparison['missing']}, "
            f"mismatched={comparison['mismatched']}, "
            f"unexpected={comparison['unexpected']})."
        )


__all__ = (
    "PythonLockError",
    "assert_environment_matches_lock",
    "assert_environment_matches_locks_exact",
    "compare_environment_to_lock",
    "compare_environment_to_locks_exact",
    "installed_versions",
    "merge_hash_locks",
    "parse_hash_lock",
)
