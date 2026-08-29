"""Lightweight XML/HTML markup summaries without rendering or execution."""

from __future__ import annotations

from html.parser import HTMLParser
from xml.etree import ElementTree


class _TagCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        self.tags[tag.lower()] = self.tags.get(tag.lower(), 0) + 1


def summarize_markup(text: str, *, language_id: str | None) -> dict[str, object]:
    if language_id == "xml":
        try:
            root = ElementTree.fromstring(text)
            return {"parse_status": "valid", "root_element": root.tag}
        except Exception as exc:
            return {"parse_status": "invalid", "parser_error": f"{type(exc).__name__}: {exc}"}
    parser = _TagCounter()
    parser.feed(text)
    return {
        "parse_status": "valid",
        "tag_summary": dict(sorted(parser.tags.items())[:40]),
        "script_or_style_present": bool(parser.tags.get("script") or parser.tags.get("style")),
    }


__all__ = ("summarize_markup",)
