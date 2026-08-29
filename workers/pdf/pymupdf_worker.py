#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 EcoSyneva Commons LLC
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Isolated PyMuPDF worker for the optional Workstation PDF profile.

This program is a separate stdin/stdout JSON worker.  It is not imported into
the Apache-licensed Elysia Core process.  Its complete corresponding source is
this file and it is distributed under AGPL-3.0-or-later because it links to
AGPL-licensed PyMuPDF.  It receives only an explicitly approved local path and
bounded operation parameters; it has no network or shell authority.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pymupdf as fitz


def _text(value: object) -> str | None:
    return None if value is None else str(value)[:500]


def _rect(value: object) -> fitz.Rect:
    if isinstance(value, dict):
        return fitz.Rect(*(float(value.get(key, 0)) for key in ("x0", "y0", "x1", "y1")))
    if isinstance(value, list) and len(value) == 4:
        return fitz.Rect(*(float(item) for item in value))
    raise ValueError("rectangle_requires_x0_y0_x1_y1")


def _field_type_label(widget) -> str:
    if widget.field_type_string:
        return str(widget.field_type_string).lower().replace(" ", "_")
    return {
        1: "button", 2: "checkbox", 3: "combobox", 4: "listbox",
        5: "radio", 6: "signature", 7: "text",
    }.get(int(widget.field_type or 0), "unknown")


def discover(path: Path, max_fields: int) -> dict[str, Any]:
    document = fitz.open(str(path))
    fields: list[dict[str, Any]] = []
    try:
        for page_index in range(document.page_count):
            for widget in list(document[page_index].widgets() or []):
                if len(fields) >= max_fields:
                    return {"fields": fields}
                name = _text(widget.field_name)
                if not name:
                    continue
                flags = int(widget.field_flags or 0)
                try:
                    button_states, on_state = widget.button_states(), widget.on_state()
                except Exception:
                    button_states, on_state = None, None
                rect = widget.rect
                fields.append({
                    "kind": "form_field", "name": name,
                    "field_type": _field_type_label(widget), "field_type_raw": int(widget.field_type or 0),
                    "value": _text(widget.field_value), "value_present": widget.field_value is not None,
                    "required": bool(flags & 2), "read_only": bool(flags & 1),
                    "options": [str(item)[:500] for item in (widget.choice_values or [])],
                    "button_states": button_states, "on_state": _text(on_state), "page": page_index + 1,
                    "rect": {"x0": round(float(rect.x0), 3), "y0": round(float(rect.y0), 3),
                             "x1": round(float(rect.x1), 3), "y1": round(float(rect.y1), 3)},
                })
    finally:
        document.close()
    return {"fields": fields}


def _int_list(value: object, default: list[int]) -> list[int]:
    raw = value if isinstance(value, list) else str(value).split(",") if isinstance(value, str) else []
    result = []
    for item in raw:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result or default


def _requested_values(parameters: dict[str, object]) -> dict[str, object]:
    for key in ("fields", "field_values"):
        if isinstance(parameters.get(key), dict):
            return dict(parameters[key])
    name = parameters.get("field_name")
    return {str(name).strip(): parameters.get("value")} if isinstance(name, str) and name.strip() else {}


def _normalize_checkbox(value: object, on_state: str | None) -> str:
    if isinstance(value, bool):
        return (on_state or "Yes") if value else "Off"
    text = str(value).strip()
    if text.lower() in {"true", "yes", "on", "checked", "1"}:
        return on_state or "Yes"
    if text.lower() in {"false", "no", "off", "unchecked", "0"}:
        return "Off"
    if text in {"Off", on_state}:
        return text
    raise ValueError("invalid_checkbox_value")


def _fill(document, parameters: dict[str, object]) -> dict[str, object]:
    widgets_by_name: dict[str, list] = {}
    for page in document:
        for widget in list(page.widgets() or []):
            if widget.field_name:
                widgets_by_name.setdefault(str(widget.field_name), []).append(widget)
    results = []
    for field_name, value in _requested_values(parameters).items():
        widgets = widgets_by_name.get(str(field_name), [])
        if not widgets:
            results.append({"field_name": str(field_name), "status": "blocked", "reason": "unknown_field_name"})
            continue
        success, failures = False, []
        for widget in widgets:
            field_type = str(widget.field_type_string or "").lower()
            try:
                if int(widget.field_flags or 0) & 1:
                    raise ValueError("field_is_read_only")
                if "text" in field_type:
                    normalized = str(value if value is not None else "")
                elif "check" in field_type or "radio" in field_type:
                    normalized = _normalize_checkbox(value, widget.on_state())
                elif "combo" in field_type or "list" in field_type:
                    normalized = str(value if value is not None else "")
                    options = [str(item) for item in (widget.choice_values or [])]
                    if options and normalized not in options:
                        raise ValueError("invalid_option")
                else:
                    raise ValueError("unsupported_field_type")
                widget.field_value = normalized
                widget.update()
                success = True
            except ValueError as exc:
                failures.append(str(exc))
        results.append({"field_name": str(field_name), "status": "updated" if success else "blocked",
                        "field_type": str(widgets[0].field_type_string or "unknown"),
                        "reason": None if success else ", ".join(sorted(set(failures)))})
    return {"field_results": results, "updated_count": sum(x["status"] == "updated" for x in results),
            "blocked_count": sum(x["status"] != "updated" for x in results)}


def apply(source: Path, target: Path, operation: str, parameters: dict[str, object]) -> dict[str, Any]:
    document = fitz.open(str(source))
    details: dict[str, object] = {}
    try:
        if operation == "extract_pages":
            pages = _int_list(parameters.get("pages"), [1])
            selected = fitz.open()
            try:
                for number in pages:
                    if number < 1 or number > document.page_count:
                        raise ValueError("page_out_of_range")
                    selected.insert_pdf(document, from_page=number - 1, to_page=number - 1)
                selected.save(str(target), garbage=4, deflate=True)
            finally:
                selected.close()
        elif operation == "rotate_pages":
            pages = _int_list(parameters.get("pages"), list(range(1, document.page_count + 1)))
            degrees = int(parameters.get("degrees") or 90)
            if degrees % 90:
                raise ValueError("rotation_must_be_multiple_of_90")
            for number in pages:
                if number < 1 or number > document.page_count:
                    raise ValueError("page_out_of_range")
                page = document[number - 1]
                page.set_rotation((page.rotation + degrees) % 360)
            document.save(str(target), garbage=4, deflate=True)
        elif operation == "reorder_pages":
            pages = _int_list(parameters.get("pages"), list(range(1, document.page_count + 1)))
            if sorted(pages) != list(range(1, document.page_count + 1)):
                raise ValueError("reorder_pages_must_include_each_page_once")
            document.select([number - 1 for number in pages])
            document.save(str(target), garbage=4, deflate=True)
        elif operation == "merge_pdf":
            other = Path(str(parameters.get("other_pdf_path") or ""))
            if not other.is_file() or other.suffix.lower() != ".pdf":
                raise ValueError("other_pdf_path_required")
            other_document = fitz.open(str(other))
            try:
                document.insert_pdf(other_document)
            finally:
                other_document.close()
            document.save(str(target), garbage=4, deflate=True)
        elif operation == "update_metadata":
            metadata = document.metadata or {}
            for key in ("title", "author", "subject", "keywords", "creator", "producer"):
                if isinstance(parameters.get(key), str):
                    metadata[key] = str(parameters[key])[:500]
            document.set_metadata(metadata)
            document.save(str(target), garbage=4, deflate=True)
        elif operation == "add_text_stamp":
            page_number = int(parameters.get("page") or 1)
            if page_number < 1 or page_number > document.page_count:
                raise ValueError("page_out_of_range")
            document[page_number - 1].insert_text((float(parameters.get("x") or 72), float(parameters.get("y") or 72)),
                                                  str(parameters.get("text") or "Approved Elysia note")[:500],
                                                  fontsize=float(parameters.get("font_size") or 10), color=(0.8, 0.1, 0.1))
            document.save(str(target), garbage=4, deflate=True)
        elif operation == "add_highlight":
            page_number = int(parameters.get("page") or 1)
            if page_number < 1 or page_number > document.page_count:
                raise ValueError("page_out_of_range")
            annotation = document[page_number - 1].add_highlight_annot(_rect(parameters.get("rect")))
            if isinstance(parameters.get("comment"), str) and str(parameters["comment"]).strip():
                annotation.set_info(content=str(parameters["comment"])[:500]); annotation.update()
            document.save(str(target), garbage=4, deflate=True)
        elif operation == "redact_rectangles":
            rectangles = parameters.get("rectangles")
            if not isinstance(rectangles, list) or not rectangles:
                raise ValueError("rectangles_required")
            page_number = int(parameters.get("page") or 1)
            if page_number < 1 or page_number > document.page_count:
                raise ValueError("page_out_of_range")
            page = document[page_number - 1]
            for item in rectangles:
                page.add_redact_annot(_rect(item), text=str(parameters.get("replacement_text") or "")[:200], fill=(1, 1, 1))
            page.apply_redactions()
            document.save(str(target), garbage=4, deflate=True)
        elif operation == "fill_form_fields":
            details = _fill(document, parameters)
            if not details["field_results"]:
                raise ValueError("no_form_fields_requested")
            if details["blocked_count"]:
                raise ValueError("pdf_form_field_validation_failed")
            document.save(str(target), garbage=4, deflate=True)
        else:
            raise ValueError("unsupported_pdf_operation")
    finally:
        document.close()
    return {"operation_details": details}


def main() -> int:
    try:
        request = json.load(sys.stdin)
        action = request.get("action")
        if action == "discover_form_fields":
            response = discover(Path(request["source_path"]), min(int(request.get("max_fields", 100)), 500))
        elif action == "apply_derived_operation":
            response = apply(Path(request["source_path"]), Path(request["target_path"]),
                             str(request["operation"]), dict(request.get("parameters") or {}))
        else:
            raise ValueError("unsupported_worker_action")
        print(json.dumps({"status": "completed", **response}, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)[:500]}, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
