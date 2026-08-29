from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_embedded_python_license_payloads_are_reuse_isolated_and_complete() -> None:
    notice = (
        ROOT / "requirements" / "THIRD_PARTY_NOTICES.txt"
    ).read_text(encoding="utf-8")
    lines = notice.splitlines()

    begins = [index for index, line in enumerate(lines) if "--- BEGIN UPSTREAM " in line]
    ends = [index for index, line in enumerate(lines) if "--- END UPSTREAM " in line]

    assert begins
    assert len(begins) == len(ends)
    assert notice.count("REUSE-IgnoreStart") == len(begins)
    assert notice.count("REUSE-IgnoreEnd") == len(ends)
    assert all(index > 0 and lines[index - 1] == "REUSE-IgnoreStart" for index in begins)
    assert all(
        index + 1 < len(lines) and lines[index + 1] == "REUSE-IgnoreEnd"
        for index in ends
    )

    # Removing a redundant root-level license payload must not remove the exact
    # upstream notice carried for the dependency that needs it.
    assert "pyelftools 0.33" in notice
    assert "License: Unlicense" in notice
    assert "This is free and unencumbered software released into the public domain." in notice


def test_dependency_notices_retain_exact_mit_payload_without_redundant_root_copy() -> None:
    desktop_notice = (
        ROOT / "apps" / "elysia-desktop" / "THIRD_PARTY_NOTICES.txt"
    ).read_text(encoding="utf-8")

    assert "MIT License" in desktop_notice
    assert "Permission is hereby granted, free of charge" in desktop_notice
