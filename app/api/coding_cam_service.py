"""Bounded CAMForge analysis for dangerous machine-instruction text."""

from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import re
from typing import Any

from app.api.coding_engineering_static import EngineeringInspectionError, bounds_payload, risk, update_bounds


_WORD_RE = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))")
_PAREN_COMMENT_RE = re.compile(r"\([^)]*\)")
_KNOWN_G = {
    0, 1, 2, 3, 4, 10, 17, 18, 19, 20, 21, 28, 29, 30, 31, 32,
    38, 40, 41, 42, 43, 49, 53, 54, 55, 56, 57, 58, 59, 80, 81, 82,
    83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95,
}
_KNOWN_M = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 17, 18, 30, 42, 73, 82, 83, 84,
    104, 105, 106, 107, 109, 110, 112, 114, 115, 116, 117, 118, 119,
    140, 141, 190, 191, 200, 201, 203, 204, 205, 206, 207, 208, 209,
    220, 221, 226, 300, 301, 302, 303, 400, 401, 402, 500, 501, 502,
    503, 600, 601, 702, 851, 999,
}


def _strip_comments(line: str) -> tuple[str, bool]:
    comment = ";" in line or bool(_PAREN_COMMENT_RE.search(line))
    without_semicolon = line.split(";", 1)[0]
    return _PAREN_COMMENT_RE.sub("", without_semicolon), comment


def inspect_gcode(path: Path, *, limits: dict[str, int], feedrate_warning: float = 20_000.0, temperature_warning: float = 300.0) -> dict[str, Any]:
    if path.stat().st_size > limits["max_text_bytes"]:
        raise EngineeringInspectionError("engineering_text_limit_exceeded")
    commands: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    line_count = 0
    comment_count = 0
    units_mode: str | None = None
    coordinate_mode: str | None = None
    extruder_mode: str | None = None
    unit_modes_seen: set[str] = set()
    coordinate_modes_seen: set[str] = set()
    extruder_modes_seen: set[str] = set()
    position = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0}
    bounds: list[list[float]] | None = None
    feedrates: list[float] = []
    temperatures: list[dict[str, Any]] = []
    spindle_commands = 0
    tool_changes = 0
    homing_commands = 0
    probe_commands = 0
    pause_stop_commands = 0
    work_offset_changes = 0
    negative_z_moves = 0
    rapid_before_homing = 0
    suspicious_arcs = 0
    high_feedrates = 0
    homed = False
    preview_segments: list[list[list[float]]] = []
    firmware_markers: Counter[str] = Counter()
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for raw_line in stream:
            line_count += 1
            if line_count > limits["max_lines"]:
                raise EngineeringInspectionError("engineering_line_limit_exceeded")
            code, had_comment = _strip_comments(raw_line)
            comment_count += int(had_comment)
            stripped = code.strip().upper()
            if not stripped or stripped == "%":
                continue
            if stripped.startswith("$"):
                firmware_markers["grbl_dollar_command"] += 1
            words = [(letter.upper(), float(value)) for letter, value in _WORD_RE.findall(stripped)]
            values: dict[str, float] = {}
            g_codes: list[float] = []
            m_codes: list[int] = []
            for letter, value in words:
                values[letter] = value
                normalized_number = int(value) if value.is_integer() else value
                commands[f"{letter}{normalized_number}"] += 1
                if letter == "G":
                    g_codes.append(value)
                    if int(value) not in _KNOWN_G:
                        unknown[f"G{normalized_number}"] += 1
                elif letter == "M":
                    m_codes.append(int(value))
                    if int(value) not in _KNOWN_M:
                        unknown[f"M{normalized_number}"] += 1
                elif letter == "T":
                    tool_changes += 1
            for g_value in g_codes:
                g = int(g_value)
                if g == 20:
                    units_mode = "inches"
                    unit_modes_seen.add(units_mode)
                elif g == 21:
                    units_mode = "millimetres"
                    unit_modes_seen.add(units_mode)
                elif g == 90:
                    coordinate_mode = "absolute"
                    coordinate_modes_seen.add(coordinate_mode)
                elif g == 91:
                    coordinate_mode = "relative"
                    coordinate_modes_seen.add(coordinate_mode)
                elif g == 28:
                    homed = True
                    homing_commands += 1
                elif g in {29, 30, 31, 32, 38}:
                    probe_commands += 1
                elif 54 <= g <= 59 or g in {10, 92}:
                    work_offset_changes += 1
            if 82 in m_codes:
                extruder_mode = "absolute"
                extruder_modes_seen.add(extruder_mode)
            if 83 in m_codes:
                extruder_mode = "relative"
                extruder_modes_seen.add(extruder_mode)
            if any(code_value in {3, 4} for code_value in m_codes):
                spindle_commands += 1
            if any(code_value in {0, 1, 2, 30, 112, 600, 601} for code_value in m_codes):
                pause_stop_commands += 1
            if 6 in m_codes:
                tool_changes += 1
            for m in m_codes:
                if m in {104, 109, 140, 190}:
                    temperatures.append({"command": f"M{m}", "target": values.get("S")})
                    firmware_markers["marlin_temperature_command"] += 1
            if "F" in values:
                feedrates.append(values["F"])
                if abs(values["F"]) > feedrate_warning:
                    high_feedrates += 1
            motion = next((int(value) for value in g_codes if int(value) in {0, 1, 2, 3}), None)
            if motion is not None:
                if motion == 0 and not homed:
                    rapid_before_homing += 1
                old = dict(position)
                for axis in ("X", "Y", "Z"):
                    if axis in values:
                        position[axis] = values[axis] if coordinate_mode != "relative" else position[axis] + values[axis]
                if "E" in values:
                    position["E"] = values["E"] if extruder_mode != "relative" else position["E"] + values["E"]
                if not all(math.isfinite(position[axis]) for axis in ("X", "Y", "Z")):
                    raise EngineeringInspectionError("non_finite_gcode_coordinate")
                bounds = update_bounds(bounds, (position["X"], position["Y"], position["Z"]))
                if position["Z"] < 0 and position["Z"] != old["Z"]:
                    negative_z_moves += 1
                if motion in {2, 3} and not any(axis in values for axis in ("I", "J", "K", "R")):
                    suspicious_arcs += 1
                if (position["X"], position["Y"]) != (old["X"], old["Y"]) and len(preview_segments) < limits["max_preview_segments"]:
                    preview_segments.append([[old["X"], old["Y"]], [position["X"], position["Y"]]])
    if not line_count:
        raise EngineeringInspectionError("empty_gcode")
    flags = [risk("machine_profile_unverified", "warning", "No trusted machine-profile compatibility verdict is available; commands must not be sent to hardware.")]
    if units_mode is None:
        flags.append(risk("missing_units", "high", "No G20/G21 units mode was detected."))
    if coordinate_mode is None:
        flags.append(risk("missing_coordinate_mode", "high", "No G90/G91 coordinate mode was detected."))
    if negative_z_moves:
        flags.append(risk("negative_z_moves", "high", "Negative Z motion was detected.", negative_z_moves))
    if rapid_before_homing:
        flags.append(risk("rapid_moves_before_homing", "high", "Rapid moves were detected before a homing command.", rapid_before_homing))
    if spindle_commands:
        flags.append(risk("spindle_start", "high", "Spindle start commands were detected.", spindle_commands))
    high_temperatures = sum(1 for item in temperatures if isinstance(item.get("target"), float) and item["target"] > temperature_warning)
    if high_temperatures:
        flags.append(risk("heater_high_temperature", "high", "Heater targets exceeded the configured warning threshold.", high_temperatures))
    if tool_changes:
        flags.append(risk("tool_change", "warning", "Tool-selection or tool-change commands were detected.", tool_changes))
    if probe_commands:
        flags.append(risk("probe_commands", "high", "Probe or bed-level commands were detected.", probe_commands))
    unknown_m = sum(value for key, value in unknown.items() if key.startswith("M"))
    if unknown_m:
        flags.append(risk("unknown_mcode", "high", "Unknown M-codes were detected and were not executed.", unknown_m))
    if high_feedrates:
        flags.append(risk("large_feedrate", "high", "Feedrates exceeded the configured analysis threshold.", high_feedrates))
    if suspicious_arcs:
        flags.append(risk("suspicious_arcs", "warning", "Arc commands without I/J/K/R geometry were detected.", suspicious_arcs))
    if len(coordinate_modes_seen) > 1 or len(extruder_modes_seen) > 1:
        flags.append(risk("relative_absolute_mode_changes", "warning", "Relative/absolute coordinate or extrusion modes changed within the file."))
    if work_offset_changes:
        flags.append(risk("work_offset_changes", "warning", "Work-offset or coordinate-set commands were detected.", work_offset_changes))
    if unknown:
        flags.append(risk("unknown_commands", "warning", "Unknown commands require dialect and machine-profile review.", sum(unknown.values())))
    dialect = "generic"
    if firmware_markers["marlin_temperature_command"]:
        dialect = "marlin_or_reprap_hint"
    elif firmware_markers["grbl_dollar_command"] or spindle_commands:
        dialect = "grbl_or_cnc_hint"
    return {
        "dialect_hint": dialect,
        "line_count": line_count,
        "comment_line_count": comment_count,
        "command_counts": dict(commands.most_common(200)),
        "unknown_command_counts": dict(unknown.most_common(100)),
        "units_mode": units_mode or "not_detected",
        "coordinate_mode": coordinate_mode or "not_detected",
        "extruder_mode": extruder_mode or "not_detected",
        "coordinate_extents": bounds_payload(bounds),
        "feedrate_min": min(feedrates) if feedrates else None,
        "feedrate_max": max(feedrates) if feedrates else None,
        "spindle_command_count": spindle_commands,
        "temperature_commands": temperatures[:200],
        "tool_change_count": tool_changes,
        "homing_command_count": homing_commands,
        "probe_command_count": probe_commands,
        "pause_stop_command_count": pause_stop_commands,
        "work_offset_change_count": work_offset_changes,
        "machine_profile_compatibility": "unverified_warning",
        "physical_send_state": "unavailable_by_design",
        "_preview_segments": preview_segments,
        "risk_flags": flags,
        "external_references": [],
        "magic_summary": "G-code machine instruction text",
    }


__all__ = ("inspect_gcode",)
