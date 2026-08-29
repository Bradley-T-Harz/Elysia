"""Structured-data parse summaries for Codev file previews."""

from __future__ import annotations

import configparser
import json
import tomllib
from typing import Any

import yaml

from app.api.coding_file_type_registry import CodingFileTypeDescriptor


def _shape_summary(payload: Any) -> dict[str, object]:
    if isinstance(payload, dict):
        return {
            "root_type": "object",
            "top_level_keys": [str(key) for key in list(payload.keys())[:40]],
            "top_level_key_count": len(payload),
        }
    if isinstance(payload, list):
        return {"root_type": "array", "item_count": len(payload)}
    return {"root_type": type(payload).__name__}


def summarize_structured_data(descriptor: CodingFileTypeDescriptor, text: str) -> dict[str, object]:
    try:
        if descriptor.language_id == "json":
            return {"parse_status": "valid", **_shape_summary(json.loads(text))}
        if descriptor.language_id == "yaml":
            return {"parse_status": "valid", **_shape_summary(yaml.safe_load(text))}
        if descriptor.language_id == "toml":
            return {"parse_status": "valid", **_shape_summary(tomllib.loads(text))}
        if descriptor.language_id == "ini":
            parser = configparser.ConfigParser()
            parser.read_string(text)
            return {"parse_status": "valid", "sections": parser.sections()}
    except Exception as exc:
        return {"parse_status": "invalid", "parser_error": f"{type(exc).__name__}: {exc}"}
    return {"parse_status": "not_applicable"}


def validate_structured_text(descriptor: CodingFileTypeDescriptor, text: str) -> tuple[bool, str | None]:
    summary = summarize_structured_data(descriptor, text)
    if summary.get("parse_status") == "invalid":
        return False, str(summary.get("parser_error") or "structured_parse_failed")
    return True, None


__all__ = ("summarize_structured_data", "validate_structured_text")
