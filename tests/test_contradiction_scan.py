from __future__ import annotations

from core.contradiction_scan import scan_contradictions


def test_scan_detects_likely_negation_conflict_without_notes():
    result = scan_contradictions(
        [
            {
                "claim": "The river restoration plan reduces nitrate levels.",
                "contradiction_notes": [],
            },
            {
                "claim": "The river restoration plan does not reduce nitrate levels.",
                "contradiction_notes": [],
            },
        ]
    )

    assert result["ok"] is False
    assert result["conflicts"][0]["conflict_type"] == "negation"
    assert "likely negation conflict lacks contradiction_notes" in result["issues"]
    assert "resolve truth" in result["note"]


def test_scan_detects_likely_numeric_conflict_without_notes():
    result = scan_contradictions(
        [
            {
                "claim": "The field trial measured 42 wetland acres restored.",
                "contradiction_notes": [],
            },
            {
                "claim": "The field trial measured 35 wetland acres restored.",
                "contradiction_notes": [],
            },
        ]
    )

    assert result["ok"] is False
    assert result["conflicts"][0]["conflict_type"] == "numeric_or_date"
    assert "likely numeric/date conflict lacks contradiction_notes" in result["issues"]


def test_scan_accepts_conflict_when_contradiction_notes_are_present():
    result = scan_contradictions(
        [
            {
                "claim": "The program began on 2025-01-10 after approval.",
                "contradiction_notes": [
                    "Another packet gives a different date; source timing needs review."
                ],
            },
            {
                "claim": "The program began on 2025-02-10 after approval.",
                "contradiction_notes": [],
            },
        ]
    )

    assert result["ok"] is True
    assert result["conflicts"][0]["conflict_type"] == "numeric_or_date"
    assert "contradiction_notes_present_for_possible_conflicts" in result[
        "checks_passed"
    ]


def test_scan_does_not_flag_unrelated_claims():
    result = scan_contradictions(
        [
            {
                "claim": "The ticket stores structured evidence packets.",
                "contradiction_notes": [],
            },
            {
                "claim": "The file parser supports local CSV inspection.",
                "contradiction_notes": [],
            },
        ]
    )

    assert result["ok"] is True
    assert result["conflicts"] == []
    assert "contradiction_scan_completed_without_conflicts" in result["checks_passed"]


def test_scan_warns_on_absolute_language_with_low_confidence():
    result = scan_contradictions(
        [
            {
                "claim": "This local packet definitely proves the final answer.",
                "confidence": "low",
                "contradiction_notes": [],
            }
        ]
    )

    assert result["ok"] is True
    assert result["issues"] == []
    assert result["warnings"] == [
        "packet 0 uses absolute language with low or unknown confidence"
    ]
    assert "resolve truth" in result["note"]
    assert "fetch sources" in result["note"]
    assert "browse the web" in result["note"]
    assert "use the network" in result["note"]
    assert "call an AI model" in result["note"]
