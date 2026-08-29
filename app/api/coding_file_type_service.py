"""File-operation classification helpers for coding plans."""

from __future__ import annotations


SUPPORTED_FILE_OPERATION_KINDS = {"create", "edit", "delete", "rename", "move", "replace"}


def normalize_file_operation_kind(kind: str) -> str:
    return kind.strip().lower().replace(" ", "_")


def is_supported_file_operation(kind: str) -> bool:
    return normalize_file_operation_kind(kind) in SUPPORTED_FILE_OPERATION_KINDS


__all__ = (
    "SUPPORTED_FILE_OPERATION_KINDS",
    "is_supported_file_operation",
    "normalize_file_operation_kind",
)
