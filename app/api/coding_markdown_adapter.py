"""Markdown/document metadata extraction for Codev previews."""

from __future__ import annotations

import re


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def summarize_markdown(text: str) -> dict[str, object]:
    headings: list[dict[str, object]] = []
    fence_count = 0
    task_count = 0
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            headings.append({"level": len(match.group(1)), "title": match.group(2)[:160]})
        if line.strip().startswith("```"):
            fence_count += 1
        if re.match(r"\s*-\s+\[[ xX]\]\s+", line):
            task_count += 1
    return {
        "parse_status": "valid",
        "document_title": headings[0]["title"] if headings else None,
        "headings": headings[:40],
        "code_fence_count": fence_count // 2,
        "task_list_item_count": task_count,
        "link_count": len(LINK_RE.findall(text)),
    }


__all__ = ("summarize_markdown",)
