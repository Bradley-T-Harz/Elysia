from __future__ import annotations

from app.api import user_control_service
from app.memory.canonical_models import MemorySettings


def test_user_controls_come_from_authoritative_memory_settings(monkeypatch):
    settings = MemorySettings(
        memory_recording_enabled=False, autonomy_level=3,
        internet_master_enabled=True,
    )
    class Fabric:
        @staticmethod
        def current_principal():
            return object()

        @staticmethod
        def settings(_principal):
            return settings

    fabric = Fabric()
    monkeypatch.setattr(user_control_service, "MemoryFabricService", lambda repository: fabric)
    monkeypatch.setattr(user_control_service, "MemoryRepository", lambda paths: object())
    monkeypatch.setattr(user_control_service, "get_active_elysia_paths", lambda: object())
    monkeypatch.setattr(
        user_control_service,
        "get_authenticated_governance",
        lambda: {"managed": False, "managed_policy": None, "policy_version": 1},
    )

    snapshot = user_control_service.current_user_controls()
    assert snapshot.memory_recording_enabled is False
    assert snapshot.autonomy_level == 3
    assert snapshot.internet_master_enabled is True
    assert snapshot.addons_allowed is True
    assert snapshot.connectors_allowed is True
    assert snapshot.coding_execution_allowed is True
    assert user_control_service.internet_master_enabled() is True
    assert user_control_service.autonomy_level() == 3


def test_internet_switch_fails_closed_and_autonomy_has_bounded_fallback(monkeypatch):
    def unavailable():
        raise RuntimeError("no active account")

    monkeypatch.setattr(user_control_service, "current_user_controls", unavailable)
    assert user_control_service.internet_master_enabled() is False
    assert user_control_service.autonomy_level(default=1) == 1
