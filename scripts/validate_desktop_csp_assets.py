#!/usr/bin/env python3
"""Prove deterministic Tauri CSP handling remains fail-closed for built assets."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self._inline_script_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if any(name.startswith("on") for name in values):
            self.errors.append(f"inline event handler on <{tag}>")
        if any(value.lstrip().lower().startswith("javascript:") for value in values.values()):
            self.errors.append(f"javascript URL on <{tag}>")
        if tag.lower() == "style":
            self.errors.append("inline <style> element")
        if tag.lower() == "script" and not values.get("src"):
            self._inline_script_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._inline_script_depth:
            self._inline_script_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._inline_script_depth and data.strip():
            self.errors.append("inline executable script")


def validate(config_path: Path, dist: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    security = config["app"]["security"]
    disabled = security.get("dangerousDisableAssetCspModification")
    if disabled != ["script-src", "style-src"]:
        raise ValueError("Tauri CSP modification exception must be limited to script-src and style-src")
    directives = {
        item.strip().split(None, 1)[0]: item.strip()
        for item in str(security.get("csp") or "").split(";")
        if item.strip()
    }
    required = {
        "default-src": "'self'",
        "script-src": "'self'",
        "object-src": "'none'",
        "base-uri": "'self'",
        "frame-ancestors": "'none'",
        "form-action": "'self'",
    }
    for directive, value in required.items():
        if value not in directives.get(directive, "").split()[1:]:
            raise ValueError(f"desktop CSP is missing {directive} {value}")
    html_paths = sorted(dist.rglob("*.html"))
    if not html_paths:
        raise ValueError("desktop production build contains no HTML")
    errors: list[str] = []
    for path in html_paths:
        parser = AssetParser()
        parser.feed(path.read_text(encoding="utf-8"))
        errors.extend(f"{path.relative_to(dist)}: {error}" for error in parser.errors)
    if errors:
        raise ValueError("unsafe inline desktop asset content: " + "; ".join(errors))
    return {
        "contract_version": "elysia-desktop-csp-assets-1.0",
        "html_files": len(html_paths),
        "inline_executable_scripts": 0,
        "inline_style_elements": 0,
        "inline_event_handlers": 0,
        "javascript_urls": 0,
        "tauri_csp_modification_exception": disabled,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.config, args.dist), sort_keys=True))


if __name__ == "__main__":
    main()
