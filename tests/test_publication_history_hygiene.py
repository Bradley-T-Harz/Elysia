from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_publication_history.py"


def _module():
    spec = importlib.util.spec_from_file_location("publication_history", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publication_history_verifier_never_returns_matching_content() -> None:
    module = _module()
    marker = b"private" + b"-operator-marker"
    findings = module.content_findings(marker + b" sensitive body", {"docs/example.md"}, [marker])
    assert findings == ["private_marker"]


def test_publication_history_verifier_catches_paths_and_allows_synthetic_fixtures() -> None:
    module = _module()
    assert module.path_findings("data/private.sqlite") == ["sensitive_filename"]
    assert module.path_findings("apps/elysia-desktop/.env.production") == ["denied_path"]
    assert module.path_findings(
        "apps/elysia-desktop/.env.production",
        {"apps/elysia-desktop/.env.production"},
    ) == []
    assert module.path_findings(
        "apps/elysia-desktop/.env.local",
        {"apps/elysia-desktop/.env.production"},
    ) == ["denied_path"]
    assert module.content_findings(b"/home/example/private", {"docs/example.md"}, []) == [
        "absolute_machine_path"
    ]
    assert module.content_findings(b"/home/example/private", {"tests/example.py"}, []) == []


def test_publication_history_verifier_accepts_github_noreply_but_rejects_private_email() -> None:
    module = _module()
    marker = b"private-person"
    assert not module.private_author_email(
        b"12345-private-person@users.noreply.github.com", [marker]
    )
    assert module.private_author_email(b"private-person@example.edu", [marker])


def test_upstream_license_author_with_shared_given_name_is_not_private_content() -> None:
    module = _module()
    notices = b"Copyright (c) 2009 Bradley Smith"
    assert module.content_findings(notices, {"THIRD_PARTY_NOTICES.txt"}, module.built_in_private_markers()) == []


def test_reviewed_publication_artifact_passes_hygiene_gate() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--scope", "public"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_strict_internal_tree_scan_still_reports_excluded_historical_evidence() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--scope", "tree"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["status"] == "failed"
    assert payload["finding_count"] >= 1
    assert all(
        str(item.get("path", "")).startswith("docs/reports/")
        for item in payload["findings"]
    )


def test_publication_artifact_uses_manifest_and_excludes_internal_reports() -> None:
    files = _module().publication_files()
    assert "packaging/public_manifest.yaml" in files
    assert not any(path.startswith("docs/reports/") for path in files)


def test_publication_boundary_contract_names_repo_roles_and_preservation_law() -> None:
    contract = (ROOT / "docs/release/PUBLICATION_BOUND_HISTORY_CONTRACT.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(contract.split())
    assert "Elysia and individually approved Add-ons" in normalized
    assert "Website, Artisan, and company repositories remain private" in normalized
    assert "repair, harden, and test" in normalized
    assert "must never be used to justify removing an established product surface" in normalized
