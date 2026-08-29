"""Test-command posture helpers for coding bridge truth surfaces."""

from __future__ import annotations


def test_execution_posture() -> dict[str, object]:
    return {
        "test_execution_allowed": False,
        "approval_required": True,
        "execution_not_implemented": True,
        "notes": [
            "Focused test execution is represented as command planning only in this pass.",
            "No test process is launched by the coding bridge.",
        ],
    }


__all__ = ("test_execution_posture",)
