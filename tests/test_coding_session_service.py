from __future__ import annotations

from app.api.coding_session_service import clear_coding_sessions_for_tests, get_coding_session, start_coding_session
from app.api.schemas.coding import CodingSessionStartRequest


def test_start_coding_session_stores_minimal_metadata(tmp_path):
    clear_coding_sessions_for_tests()
    session = start_coding_session(
        CodingSessionStartRequest(
            workspace_label="Elysia",
            workspace_root=str(tmp_path),
            approval_mode="apply_with_approval",
        )
    )

    assert session.session_id.startswith("coding_")
    assert session.workspace_label == "Elysia"
    assert session.workspace_root_hash
    assert str(tmp_path) not in repr(session.to_payload())
    assert session.approval_mode == "apply_with_approval"
    assert session.boundaries.patch_apply_allowed is True
    assert session.boundaries.command_execution_allowed is False

    loaded = get_coding_session(session.session_id)
    assert loaded is not None
    assert loaded.session_id == session.session_id
