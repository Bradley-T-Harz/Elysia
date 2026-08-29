from __future__ import annotations

from app.api.coding_state_machine import can_transition, initial_task_state
from app.api.coding_task_service import plan_coding_task
from app.api.schemas.coding_tasks import CodingTaskPlanRequest


def test_task_state_machine_is_small_and_non_autonomous():
    assert initial_task_state() == "planned"
    assert can_transition("planned", "waiting_for_user") is True
    assert can_transition("complete", "planned") is False


def test_task_plan_is_plan_only():
    result = plan_coding_task(CodingTaskPlanRequest(objective="Fix a bug", workspace_label="Elysia"))

    assert result.status == "plan_only"
    assert result.autonomous_loop_allowed is False
    assert result.mutation_allowed is False
    assert result.human_approval_required is True
