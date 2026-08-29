"""
Bounded local plot artifact builder v0 for Elysia.

This module builds a simple SVG plot from an already-completed bounded local
data-execution summary. It does not read source data files, write artifacts,
run arbitrary Python, call shell commands, touch the network, use matplotlib,
use pandas, mutate files, scan folders, or promote anything into memory.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from html import escape
import math
from typing import Any


PLOT_ARTIFACT_TOOL_KIND = "plot_artifact_builder"
PLOT_OPERATION_NUMERIC_SUMMARY_BAR_SVG = "build_numeric_summary_bar_svg"
PLOT_ARTIFACT_KIND = "plot_image"
PLOT_KIND_NUMERIC_SUMMARY_BAR_SVG = "numeric_summary_bar_svg"
SVG_MIME_TYPE = "image/svg+xml"

DEFAULT_PLOT_WIDTH = 720
DEFAULT_PLOT_HEIGHT = 420
DEFAULT_MAX_PLOT_COLUMNS = 12
SUPPORTED_PLOT_METRICS = {"mean", "min", "max", "count", "missing"}


class PlotArtifactStatus(str, Enum):
    """Execution status for plot artifact building."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class PlotArtifactBuildResult:
    """Structured result for a bounded local plot build attempt."""

    ok: bool
    status: PlotArtifactStatus
    tool_kind: str = PLOT_ARTIFACT_TOOL_KIND
    operation: str = PLOT_OPERATION_NUMERIC_SUMMARY_BAR_SVG
    artifact_kind: str = PLOT_ARTIFACT_KIND
    plot_kind: str = PLOT_KIND_NUMERIC_SUMMARY_BAR_SVG
    title: str = ""
    summary: str = ""
    svg_text: str = ""
    svg_mime_type: str = SVG_MIME_TYPE
    width: int = DEFAULT_PLOT_WIDTH
    height: int = DEFAULT_PLOT_HEIGHT
    source_file_name: str | None = None
    source_file_kind: str | None = None
    row_count: int = 0
    column_count: int = 0
    plotted_columns: list[str] = field(default_factory=list)
    metric: str = "mean"
    locality: str = "local"
    memory_posture: str = "not_memory"
    network_access_used: bool = False
    mutated_files: bool = False
    arbitrary_python_used: bool = False
    shell_used: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _get_field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)

    attr = getattr(value, key, None)
    if attr is not None:
        return attr

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:
            dumped = None

        if isinstance(dumped, Mapping):
            return dumped.get(key, default)

    as_dict = getattr(value, "dict", None)
    if callable(as_dict):
        try:
            dumped = as_dict()
        except Exception:
            dumped = None

        if isinstance(dumped, Mapping):
            return dumped.get(key, default)

    return default


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:
            dumped = None

        if isinstance(dumped, Mapping):
            return dumped

    as_dict = getattr(value, "dict", None)
    if callable(as_dict):
        try:
            dumped = as_dict()
        except Exception:
            dumped = None

        if isinstance(dumped, Mapping):
            return dumped

    return {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _as_finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _clean_metric(metric: str) -> str:
    return str(metric or "").strip().lower()


def _blocked_result(
    *,
    metric: str,
    width: int,
    height: int,
    source_file_name: str | None = None,
    source_file_kind: str | None = None,
    row_count: int = 0,
    column_count: int = 0,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> PlotArtifactBuildResult:
    return PlotArtifactBuildResult(
        ok=False,
        status=PlotArtifactStatus.BLOCKED,
        title="Plot artifact blocked",
        summary="No local plot artifact was generated.",
        width=width,
        height=height,
        source_file_name=source_file_name,
        source_file_kind=source_file_kind,
        row_count=row_count,
        column_count=column_count,
        metric=metric,
        warnings=list(warnings or []),
        errors=list(errors or []),
    )


def _is_completed_data_execution(data_execution: Any) -> bool:
    status = _enum_text(_get_field(data_execution, "status", "")).lower()
    ok = _get_field(data_execution, "ok", True)

    if ok is False:
        return False

    return status == "completed"


def _ordered_numeric_stats(data_execution: Any) -> list[tuple[str, Any]]:
    numeric_stats = _as_mapping(_get_field(data_execution, "numeric_stats", {}))
    numeric_columns_raw = _get_field(data_execution, "numeric_columns", [])
    numeric_columns = [
        str(column)
        for column in numeric_columns_raw
        if str(column or "").strip()
    ] if isinstance(numeric_columns_raw, list) else []

    ordered: list[tuple[str, Any]] = []
    used: set[str] = set()

    for column in numeric_columns:
        if column in numeric_stats:
            ordered.append((column, numeric_stats[column]))
            used.add(column)

    for column, stats in numeric_stats.items():
        column_name = str(column)
        if column_name not in used:
            ordered.append((column_name, stats))

    return ordered


def _extract_metric_values(
    data_execution: Any,
    *,
    metric: str,
    max_columns: int,
) -> tuple[list[tuple[str, float]], list[str]]:
    warnings: list[str] = []
    plotted_values: list[tuple[str, float]] = []
    skipped_columns: list[str] = []

    for column, stats in _ordered_numeric_stats(data_execution):
        value = _as_finite_float(_get_field(stats, metric, None))
        if value is None:
            skipped_columns.append(column)
            continue

        plotted_values.append((column, value))

    if skipped_columns:
        warnings.append(
            "Skipped numeric columns without finite "
            f"{metric} values: {', '.join(skipped_columns)}."
        )

    if len(plotted_values) > max_columns:
        warnings.append(
            "Numeric columns were limited to "
            f"{max_columns} for v0 plot readability."
        )
        plotted_values = plotted_values[:max_columns]

    return plotted_values, warnings


def _format_number(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", " ")

    if value == int(value):
        return str(int(value))

    return f"{value:.3f}".rstrip("0").rstrip(".")


def _short_label(value: str, limit: int = 18) -> str:
    text = str(value)
    if len(text) <= limit:
        return text

    return text[: max(1, limit - 1)].rstrip() + "…"


def _map_value_to_y(
    value: float,
    *,
    minimum: float,
    maximum: float,
    plot_top: float,
    plot_bottom: float,
) -> float:
    if maximum == minimum:
        return (plot_top + plot_bottom) / 2

    ratio = (value - minimum) / (maximum - minimum)
    return plot_bottom - ratio * (plot_bottom - plot_top)


def _build_svg(
    *,
    title: str,
    description: str,
    values: list[tuple[str, float]],
    metric: str,
    width: int,
    height: int,
) -> str:
    safe_title = escape(title, quote=True)
    safe_description = escape(description, quote=True)

    plot_left = 84
    plot_right = max(plot_left + 120, width - 36)
    plot_top = 74
    plot_bottom = max(plot_top + 120, height - 78)
    plot_width = plot_right - plot_left

    raw_minimum = min(value for _, value in values)
    raw_maximum = max(value for _, value in values)
    minimum = min(0.0, raw_minimum)
    maximum = max(0.0, raw_maximum)

    if minimum == maximum:
        padding = abs(maximum) * 0.2 if maximum else 1.0
        minimum -= padding
        maximum += padding

    zero_y = _map_value_to_y(
        0.0,
        minimum=minimum,
        maximum=maximum,
        plot_top=plot_top,
        plot_bottom=plot_bottom,
    )

    slot_width = plot_width / max(1, len(values))
    bar_width = max(12, min(44, slot_width * 0.52))
    elements: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{safe_title}">'
        ),
        f"<title>{safe_title}</title>",
        f"<desc>{safe_description}</desc>",
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#0B0E12"/>',
        f'<rect x="18" y="18" width="{width - 36}" height="{height - 36}" rx="16" fill="#121925" stroke="rgba(199, 210, 218, 0.18)"/>',
        f'<text x="36" y="44" fill="#C7D2DA" font-family="system-ui, sans-serif" font-size="18" font-weight="700">{safe_title}</text>',
        f'<text x="36" y="64" fill="#B8A27B" font-family="system-ui, sans-serif" font-size="12">{escape("Metric: " + metric, quote=True)}</text>',
        f'<line x1="{plot_left}" y1="{zero_y:.2f}" x2="{plot_right}" y2="{zero_y:.2f}" stroke="#B8A27B" stroke-width="1.4"/>',
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" stroke="rgba(199, 210, 218, 0.35)" stroke-width="1"/>',
        f'<text x="34" y="{plot_top + 4}" fill="#C7D2DA" font-family="system-ui, sans-serif" font-size="11">{escape(_format_number(maximum), quote=True)}</text>',
        f'<text x="34" y="{plot_bottom}" fill="#C7D2DA" font-family="system-ui, sans-serif" font-size="11">{escape(_format_number(minimum), quote=True)}</text>',
    ]

    for index, (column, value) in enumerate(values):
        center_x = plot_left + slot_width * index + slot_width / 2
        x = center_x - bar_width / 2
        value_y = _map_value_to_y(
            value,
            minimum=minimum,
            maximum=maximum,
            plot_top=plot_top,
            plot_bottom=plot_bottom,
        )

        if value >= 0:
            y = value_y
            bar_height = max(1, zero_y - value_y)
        else:
            y = zero_y
            bar_height = max(1, value_y - zero_y)

        safe_column = escape(column, quote=True)
        safe_label = escape(_short_label(column), quote=True)
        safe_value = escape(_format_number(value), quote=True)
        value_text_y = y - 6 if value >= 0 else y + bar_height + 16

        elements.extend(
            [
                f"<title>{safe_column}: {safe_value}</title>",
                (
                    f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" '
                    f'height="{bar_height:.2f}" rx="5" fill="#7ED7D1" '
                    f'stroke="rgba(126, 215, 209, 0.42)"/>'
                ),
                (
                    f'<text x="{center_x:.2f}" y="{value_text_y:.2f}" '
                    f'fill="#C7D2DA" font-family="system-ui, sans-serif" '
                    f'font-size="11" text-anchor="middle">{safe_value}</text>'
                ),
                (
                    f'<text x="{center_x:.2f}" y="{plot_bottom + 22}" '
                    f'fill="#C7D2DA" font-family="system-ui, sans-serif" '
                    f'font-size="10" text-anchor="middle">{safe_label}</text>'
                ),
            ]
        )

    elements.append("</svg>")
    return "".join(elements)


def build_numeric_summary_bar_svg(
    data_execution: Any,
    *,
    metric: str = "mean",
    max_columns: int = DEFAULT_MAX_PLOT_COLUMNS,
    width: int = DEFAULT_PLOT_WIDTH,
    height: int = DEFAULT_PLOT_HEIGHT,
) -> PlotArtifactBuildResult:
    """
    Build a simple local SVG bar chart from completed numeric summary stats.

    This function reads only the already-surfaced data-execution summary. It
    does not read the source file or create/save an artifact record.
    """
    clean_metric = _clean_metric(metric)
    clean_width = max(320, int(width or DEFAULT_PLOT_WIDTH))
    clean_height = max(240, int(height or DEFAULT_PLOT_HEIGHT))
    clean_max_columns = max(1, int(max_columns or DEFAULT_MAX_PLOT_COLUMNS))

    source_file_name = _get_field(data_execution, "file_name", None) or _get_field(
        data_execution, "source_file_name", None
    )
    source_file_kind = _get_field(data_execution, "file_kind", None)
    row_count = _as_int(_get_field(data_execution, "row_count", 0))
    column_count = _as_int(_get_field(data_execution, "column_count", 0))
    incoming_warnings = [
        str(warning)
        for warning in (_get_field(data_execution, "warnings", []) or [])
        if str(warning or "").strip()
    ]

    if clean_metric not in SUPPORTED_PLOT_METRICS:
        return _blocked_result(
            metric=clean_metric,
            width=clean_width,
            height=clean_height,
            source_file_name=source_file_name,
            source_file_kind=source_file_kind,
            row_count=row_count,
            column_count=column_count,
            warnings=incoming_warnings,
            errors=[
                "Unsupported plot metric for v0. Supported metrics are: "
                + ", ".join(sorted(SUPPORTED_PLOT_METRICS))
                + "."
            ],
        )

    if not _is_completed_data_execution(data_execution):
        return _blocked_result(
            metric=clean_metric,
            width=clean_width,
            height=clean_height,
            source_file_name=source_file_name,
            source_file_kind=source_file_kind,
            row_count=row_count,
            column_count=column_count,
            warnings=incoming_warnings,
            errors=[
                "Completed bounded data execution is required before building a plot artifact."
            ],
        )

    numeric_stats = _as_mapping(_get_field(data_execution, "numeric_stats", {}))
    if not numeric_stats:
        return _blocked_result(
            metric=clean_metric,
            width=clean_width,
            height=clean_height,
            source_file_name=source_file_name,
            source_file_kind=source_file_kind,
            row_count=row_count,
            column_count=column_count,
            warnings=incoming_warnings,
            errors=["No numeric statistics were available for plotting."],
        )

    plotted_values, extraction_warnings = _extract_metric_values(
        data_execution,
        metric=clean_metric,
        max_columns=clean_max_columns,
    )

    if not plotted_values:
        return _blocked_result(
            metric=clean_metric,
            width=clean_width,
            height=clean_height,
            source_file_name=source_file_name,
            source_file_kind=source_file_kind,
            row_count=row_count,
            column_count=column_count,
            warnings=incoming_warnings + extraction_warnings,
            errors=[
                f"No finite numeric values were available for metric: {clean_metric}."
            ],
        )

    title_source = source_file_name or "data summary"
    title = f"Numeric summary plot: {title_source}"
    summary = (
        "Generated local SVG bar chart of "
        f"{clean_metric} values for {len(plotted_values)} numeric "
        f"column{'s' if len(plotted_values) != 1 else ''}."
    )
    description = (
        "Local SVG plot generated from bounded data execution summary. "
        "No source file read, network access, shell execution, arbitrary Python, "
        "file mutation, notebook behavior, pandas, or matplotlib was used."
    )
    svg_text = _build_svg(
        title=title,
        description=description,
        values=plotted_values,
        metric=clean_metric,
        width=clean_width,
        height=clean_height,
    )

    return PlotArtifactBuildResult(
        ok=True,
        status=PlotArtifactStatus.COMPLETED,
        title=title,
        summary=summary,
        svg_text=svg_text,
        width=clean_width,
        height=clean_height,
        source_file_name=source_file_name,
        source_file_kind=source_file_kind,
        row_count=row_count,
        column_count=column_count,
        plotted_columns=[column for column, _ in plotted_values],
        metric=clean_metric,
        warnings=incoming_warnings + extraction_warnings,
        errors=[],
    )


__all__ = (
    "DEFAULT_MAX_PLOT_COLUMNS",
    "DEFAULT_PLOT_HEIGHT",
    "DEFAULT_PLOT_WIDTH",
    "PLOT_ARTIFACT_KIND",
    "PLOT_ARTIFACT_TOOL_KIND",
    "PLOT_OPERATION_NUMERIC_SUMMARY_BAR_SVG",
    "PLOT_KIND_NUMERIC_SUMMARY_BAR_SVG",
    "PlotArtifactBuildResult",
    "PlotArtifactStatus",
    "SVG_MIME_TYPE",
    "build_numeric_summary_bar_svg",
)
