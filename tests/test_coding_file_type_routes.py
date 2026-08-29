from __future__ import annotations

import asyncio

from app.api.routes import coding_file_types
from app.api.schemas.coding_file_types import CodingFileTypeInspectRequest


async def _await_payload(coro):
    return await coro


def test_file_type_routes_are_registered_on_local_bridge():
    from app.api.main import create_app

    app = create_app()
    paths = set(app.openapi()["paths"])

    assert "/coding/file-types" in paths
    assert "/coding/file/inspect-type" in paths


def test_inspect_type_returns_descriptor_without_reading_contents(tmp_path):
    source = tmp_path / ".env.example"
    source.write_text("TOKEN=example\n", encoding="utf-8")

    payload = asyncio.run(
        _await_payload(
            coding_file_types.post_file_inspect_type(
                CodingFileTypeInspectRequest(workspace_root=str(tmp_path), file_path=str(source))
            )
        )
    )
    inspection = payload["data"]["file_type_inspection"]

    assert inspection["status"] == "completed"
    assert inspection["descriptor"]["type_id"] == "env_example"
    assert inspection["descriptor"]["risk_flags"]["secret_sensitive"] is True
    assert "TOKEN=example" not in repr(payload)
