"""Tiny planning-only task state machine for coding requests."""

from __future__ import annotations


ALLOWED_TASK_STATES = ("planned", "waiting_for_user", "blocked", "complete")


def initial_task_state() -> str:
    return "planned"


def can_transition(from_state: str, to_state: str) -> bool:
    if from_state not in ALLOWED_TASK_STATES or to_state not in ALLOWED_TASK_STATES:
        return False
    if from_state == "complete":
        return False
    return True


__all__ = ("ALLOWED_TASK_STATES", "can_transition", "initial_task_state")
