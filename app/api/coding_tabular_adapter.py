"""Tabular data adapter entrypoint.

Decision logic is centralized in ``coding_data_adapter_service``.
"""

from app.api.coding_data_adapter_service import inspect_data_path, preview_data_path

__all__ = ("inspect_data_path", "preview_data_path")
