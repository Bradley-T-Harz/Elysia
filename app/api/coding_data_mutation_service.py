"""Compatibility wrapper for governed data mutation operations."""

from __future__ import annotations

from app.api.coding_data_edit_service import apply_data_edit, plan_data_edit

__all__ = ("apply_data_edit", "plan_data_edit")
