"""CSV/TSV adapter summaries for governed file previews."""

from __future__ import annotations

import csv
from io import StringIO


def summarize_delimited_data(text: str, *, delimiter: str) -> dict[str, object]:
    sample = text[:20_000]
    reader = csv.reader(StringIO(sample), delimiter=delimiter)
    rows = list(reader)
    headers = rows[0] if rows else []
    return {
        "parse_status": "valid",
        "delimiter": "\\t" if delimiter == "\t" else delimiter,
        "has_header": bool(headers),
        "column_count": len(headers),
        "column_names": headers[:40],
        "sample_row_count": max(0, len(rows) - 1),
    }


__all__ = ("summarize_delimited_data",)
