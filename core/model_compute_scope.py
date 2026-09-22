"""Server-owned per-attempt compute admission, never supplied by request JSON.

The invoker still selects only policy-permitted role candidates. This scope
lets the owning runtime reserve the concrete candidate before provider access
without removing legacy configured fallback or changing adapter signatures.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable


class ModelComputeAdmissionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelAttemptControls:
    num_gpu: int | None
    owned_profile: object


_PREPARE: ContextVar[Callable[[str], int | None | ModelAttemptControls] | None] = ContextVar(
    "model_compute_prepare", default=None
)


def current_admission():
    return _PREPARE.get()


@contextmanager
def model_compute_scope(prepare: Callable[[str], int | None | ModelAttemptControls]):
    token = _PREPARE.set(prepare)
    try:
        yield
    finally:
        _PREPARE.reset(token)
