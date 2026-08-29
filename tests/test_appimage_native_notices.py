from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_appimage_native_notices.py"
SPEC = importlib.util.spec_from_file_location("generate_appimage_native_notices", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_package_fact_queries_the_exact_native_architecture(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_command(*args: str) -> str:
        calls.append(args)
        return "1.2.3-4\tlibexample\t1.2.3-4"

    monkeypatch.setattr(MODULE, "command", fake_command)

    assert MODULE.package_fact("libexample1", "amd64") == (
        "1.2.3-4",
        "libexample",
        "1.2.3-4",
    )
    assert calls[0][-1] == "libexample1:amd64"


def test_package_fact_refuses_ambiguous_or_malformed_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        MODULE,
        "command",
        lambda *args: "1.2.3\tlibexample\t1.2.3\n1.2.4\tlibexample\t1.2.4",
    )
    with pytest.raises(RuntimeError, match="expected one package fact"):
        MODULE.package_fact("libexample1", "amd64")

    monkeypatch.setattr(MODULE, "command", lambda *args: "1.2.3\tlibexample")
    with pytest.raises(RuntimeError, match="malformed package fact"):
        MODULE.package_fact("libexample1", "amd64")
