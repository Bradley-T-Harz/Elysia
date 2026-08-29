"""
Deterministic contradiction scan for research evidence packets.

Sprint 8C keeps this deliberately local and lexical. It does not call an AI
model, browse the web, fetch sources, use the network, or resolve final truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_NEGATION_PATTERNS = (
    "not",
    "no",
    "never",
    "false",
    "incorrect",
    "cannot",
    "can't",
    "does not",
    "do not",
    "did not",
    "is not",
    "are not",
    "was not",
    "were not",
)

_ABSOLUTE_LANGUAGE_PATTERNS = (
    "proves",
    "always",
    "never",
    "definitely",
    "certainly",
    "impossible",
    "guaranteed",
)

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}

_NUMBER_OR_DATE_RE = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d+(?:\.\d+)?%?\b"
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class ContradictionConflict:
    """One possible contradiction found by lexical scanning."""

    conflict_type: str
    left_index: int
    right_index: int
    reason: str
    shared_terms: list[str] = field(default_factory=list)


def _text_from_packet(packet: Any, field_name: str) -> str:
    if isinstance(packet, dict):
        return str(packet.get(field_name) or "")

    return str(getattr(packet, field_name, "") or "")


def _notes_from_packet(packet: Any) -> list[str]:
    notes = packet.get("contradiction_notes") if isinstance(packet, dict) else getattr(
        packet,
        "contradiction_notes",
        [],
    )
    if not isinstance(notes, list):
        return []

    return [str(note).strip() for note in notes if str(note).strip()]


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _terms(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(text.lower())
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def _has_negation(text: str) -> bool:
    normalized = f" {_normalize_text(text)} "
    return any(f" {pattern} " in normalized for pattern in _NEGATION_PATTERNS)


def _has_absolute_language(text: str) -> bool:
    normalized = f" {_normalize_text(text)} "
    return any(
        f" {pattern} " in normalized
        for pattern in _ABSOLUTE_LANGUAGE_PATTERNS
    )


def _confidence_from_packet(packet: Any) -> str:
    value = packet.get("confidence") if isinstance(packet, dict) else getattr(
        packet,
        "confidence",
        "",
    )
    return str(getattr(value, "value", value) or "").lower()


def _numbers_or_dates(text: str) -> set[str]:
    return set(_NUMBER_OR_DATE_RE.findall(text))


def _shared_terms(left: str, right: str) -> list[str]:
    return sorted(_terms(left) & _terms(right))


def _has_notes(left: Any, right: Any) -> bool:
    return bool(_notes_from_packet(left) or _notes_from_packet(right))


def scan_contradictions(evidence_packets: list[Any]) -> dict[str, Any]:
    """
    Scan evidence claims for likely contradictions.

    This is a deterministic contract check. It finds possible conflicts and
    requires contradiction notes; it never decides which claim is true.
    """
    conflicts: list[ContradictionConflict] = []
    issues: list[str] = []
    warnings: list[str] = []
    checks_passed: list[str] = []

    packets = list(evidence_packets or [])

    for left_index, left in enumerate(packets):
        left_claim = _text_from_packet(left, "claim")
        left_values = _numbers_or_dates(left_claim)
        left_confidence = _confidence_from_packet(left)

        if left_confidence in {"", "unknown", "low"} and _has_absolute_language(
            left_claim
        ):
            warnings.append(
                f"packet {left_index} uses absolute language with low or unknown confidence"
            )

        for right_index in range(left_index + 1, len(packets)):
            right = packets[right_index]
            right_claim = _text_from_packet(right, "claim")
            shared = _shared_terms(left_claim, right_claim)

            if len(shared) < 3:
                continue

            left_negated = _has_negation(left_claim)
            right_negated = _has_negation(right_claim)

            if left_negated != right_negated:
                conflicts.append(
                    ContradictionConflict(
                        conflict_type="negation",
                        left_index=left_index,
                        right_index=right_index,
                        reason=(
                            "Claims share terms but differ in negation posture; "
                            "manual review is required."
                        ),
                        shared_terms=shared,
                    )
                )
                if not _has_notes(left, right):
                    issues.append(
                        "likely negation conflict lacks contradiction_notes"
                    )

            right_values = _numbers_or_dates(right_claim)
            if left_values and right_values and left_values != right_values:
                conflicts.append(
                    ContradictionConflict(
                        conflict_type="numeric_or_date",
                        left_index=left_index,
                        right_index=right_index,
                        reason=(
                            "Claims share terms but contain different numeric or "
                            "date values; manual review is required."
                        ),
                        shared_terms=shared,
                    )
                )
                if not _has_notes(left, right):
                    issues.append(
                        "likely numeric/date conflict lacks contradiction_notes"
                    )

    if conflicts:
        checks_passed.append("contradiction_scan_completed_with_possible_conflicts")
        if not issues:
            checks_passed.append("contradiction_notes_present_for_possible_conflicts")
    else:
        checks_passed.append("contradiction_scan_completed_without_conflicts")

    return {
        "ok": not issues,
        "checks_passed": checks_passed,
        "issues": issues,
        "warnings": warnings,
        "conflicts": [
            {
                "conflict_type": conflict.conflict_type,
                "left_index": conflict.left_index,
                "right_index": conflict.right_index,
                "reason": conflict.reason,
                "shared_terms": conflict.shared_terms,
            }
            for conflict in conflicts
        ],
        "note": (
            "Deterministic contradiction scan only. This does not resolve truth, "
            "fetch sources, browse the web, use the network, or call an AI model."
        ),
    }


__all__ = ("scan_contradictions",)
