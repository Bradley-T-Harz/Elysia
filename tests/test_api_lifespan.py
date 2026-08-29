from __future__ import annotations

import asyncio

import app.api.account_service as account_service
import app.memory.canonical_repository as canonical_repository
from app.api.main import create_app
from app.memory.release_service import MemoryReleaseService


def test_api_lifespan_recovers_memory_and_cancels_maintenance(monkeypatch):
    """The supported lifespan owns recovery and leaves no background task."""

    qa_paths = object()
    qa_repository = object()
    recovered: list[object] = []
    monkeypatch.setattr(account_service, "get_active_elysia_paths", lambda: qa_paths)
    monkeypatch.setattr(
        canonical_repository,
        "MemoryRepository",
        lambda *, paths: qa_repository if paths is qa_paths else None,
    )
    monkeypatch.setattr(
        MemoryReleaseService,
        "recover_after_restart",
        lambda repository: recovered.append(repository),
    )
    app = create_app()

    async def exercise_lifespan() -> None:
        async with app.router.lifespan_context(app):
            task = app.state.part2e_maintenance_task
            assert task.get_name() == "elysia-part2e-maintenance"
            assert not task.done()
            assert recovered == [qa_repository]
        assert task.cancelled()

    asyncio.run(exercise_lifespan())
