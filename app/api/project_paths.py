"""Repository-root path helpers for local API services."""

from __future__ import annotations

from pathlib import Path

from app.install.paths import resolve_elysia_paths


def elysia_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def elysia_path(*parts: str) -> Path:
    return elysia_repo_root().joinpath(*parts)


def config_path(*parts: str) -> Path:
    return elysia_path("config", *parts)


def policy_path(*parts: str) -> Path:
    return config_path("policies", *parts)


def data_path(*parts: str) -> Path:
    """Return an Elysia-owned XDG user-data path."""
    return resolve_elysia_paths().data_dir.joinpath(*parts)


def state_path(*parts: str) -> Path:
    """Return an Elysia-owned XDG user-state path."""
    return resolve_elysia_paths().state_dir.joinpath(*parts)


__all__ = (
    "config_path",
    "data_path",
    "elysia_path",
    "elysia_repo_root",
    "policy_path",
    "state_path",
)
