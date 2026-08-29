from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_desktop_csp_assets.py"
SPEC = importlib.util.spec_from_file_location("validate_desktop_csp_assets", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "app": {
                    "security": {
                        "csp": "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
                        "dangerousDisableAssetCspModification": ["script-src", "style-src"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_external_self_hosted_assets_need_no_nondeterministic_hash_injection(tmp_path: Path) -> None:
    config = tmp_path / "tauri.json"
    dist = tmp_path / "dist"
    dist.mkdir()
    write_config(config)
    (dist / "index.html").write_text(
        '<script type="module" src="/assets/app.js"></script><link rel="stylesheet" href="/assets/app.css">',
        encoding="utf-8",
    )

    result = MODULE.validate(config, dist)

    assert result["inline_executable_scripts"] == 0
    assert result["tauri_csp_modification_exception"] == ["script-src", "style-src"]


@pytest.mark.parametrize(
    "html",
    [
        "<script>alert(1)</script>",
        "<style>body { color: red }</style>",
        '<button onclick="alert(1)">unsafe</button>',
        '<a href="javascript:alert(1)">unsafe</a>',
    ],
)
def test_inline_or_javascript_asset_content_is_rejected(tmp_path: Path, html: str) -> None:
    config = tmp_path / "tauri.json"
    dist = tmp_path / "dist"
    dist.mkdir()
    write_config(config)
    (dist / "index.html").write_text(html, encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe inline desktop asset content"):
        MODULE.validate(config, dist)
