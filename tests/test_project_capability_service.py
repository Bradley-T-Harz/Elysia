from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import project_capability_service as service


@pytest.fixture()
def project_workbench(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "_store_root", lambda: tmp_path / "project-capabilities")
    monkeypatch.setattr(service, "_owner", lambda: "owner-a")
    monkeypatch.setattr(
        service.project_service,
        "get_project_metadata",
        lambda project_id: {"project_id": project_id, "owner_user_id": "owner-a"},
    )
    monkeypatch.setattr(service.project_service, "update_project_metadata", lambda *_args, **_kwargs: None)
    return tmp_path


def test_study_quiz_goal_and_canvas_are_owner_scoped_and_persisted(project_workbench):
    source = "Photosynthesis: plants convert light energy into chemical energy."
    plan = service.create_study_plan(
        "project-a",
        service.StudyPlanRequest(topic="Photosynthesis", source_material=source),
    )
    assert plan["study_plan"]["grounding_state"] == "user_supplied_source"
    assert plan["study_plan"]["modules"]
    assert "source_material" not in plan["study_plan"]
    module = plan["study_plan"]["modules"][0]
    reviewed = service.review_study_module(
        "project-a",
        plan["study_plan"]["study_plan_id"],
        module["module_id"],
        service.StudyModuleReviewRequest(action="complete", reflection="I can explain this.", confidence=4),
    )
    assert reviewed["study_module"]["review_state"] == "completed"
    assert reviewed["study_plan"]["progress"]["percent"] == 50

    quiz = service.generate_quiz(
        "project-a",
        service.QuizGenerateRequest(source_material=source, question_count=1),
    )["quiz"]
    question = quiz["questions"][0]
    assert "expected_answer" not in question
    answer = service.answer_quiz(
        "project-a",
        quiz["quiz_id"],
        service.QuizAnswerRequest(
            question_id=question["question_id"],
            answer="Plants convert light energy into chemical energy.",
        ),
    )
    assert answer["correct"] is True
    assert answer["score"] == 1
    retry = service.answer_quiz(
        "project-a",
        quiz["quiz_id"],
        service.QuizAnswerRequest(question_id=question["question_id"], answer="needs review"),
    )
    assert retry["attempt_count"] == 2
    assert retry["explanation"].startswith("Grounded source statement")

    investigation = service.record_research_iteration(
        "project-a",
        service.ResearchIterationRequest(
            question="How do plants store light energy?",
            query="photosynthesis primary source",
            evidence_packets=[{
                "evidence_id": "evidence-a",
                "source_url": "https://example.org/source",
                "title": "Primary source",
                "snippet": "Plants convert light energy.",
                "claim": "Plants store converted light energy.",
                "supports_claim": True,
                "private_context_sent": False,
            }],
            evidence_verified=True,
        ),
    )["research_investigation"]
    assert investigation["source_count"] == 1
    assert investigation["comparison"]["status"] == "none_recorded"
    paused = service.transition_research(
        "project-a",
        investigation["investigation_id"],
        service.ResearchTransitionRequest(action="pause"),
    )["research_investigation"]
    assert paused["status"] == "paused"
    assert service.transition_research(
        "project-a",
        investigation["investigation_id"],
        service.ResearchTransitionRequest(action="cancel"),
    )["research_investigation"]["status"] == "cancelled"

    goal = service.create_goal(
        "project-a",
        service.GoalCreateRequest(goal="Prepare a grounded summary", budget_steps=3),
        autonomy_level=2,
    )["goal"]
    assert goal["policy"]["operator_stop_always_available"] is True
    assert goal["policy"]["shell_allowed"] is False
    started = service.transition_goal(
        "project-a",
        goal["goal_id"],
        service.GoalTransitionRequest(action="start"),
    )["goal"]
    assert started["status"] == "active"
    stopped = service.transition_goal(
        "project-a",
        goal["goal_id"],
        service.GoalTransitionRequest(action="emergency_stop"),
    )["goal"]
    assert stopped["status"] == "emergency_stopped"

    canvas = service.update_canvas(
        "project-a",
        service.CanvasUpdateRequest(
            title="Evidence map",
            elements=[service.CanvasElement(kind="note", content="Review the supplied source.")],
        ),
    )["canvas"]
    assert canvas["title"] == "Evidence map"
    assert canvas["elements"][0]["kind"] == "note"

    workbench = service.get_workbench("project-a")
    assert len(workbench["study_plans"]) == 1
    assert len(workbench["quizzes"]) == 1
    assert len(workbench["research_investigations"]) == 1
    assert len(workbench["goals"]) == 1
    assert workbench["canvas"]["title"] == "Evidence map"
    assert "owner_user_id" not in workbench

    state_files = list((project_workbench / "project-capabilities").rglob("*.json"))
    assert len(state_files) == 1
    assert state_files[0].stat().st_mode & 0o777 == 0o600


def test_project_source_attachment_uses_governed_ingest_and_redacts_path(
    project_workbench, monkeypatch
):
    selected = project_workbench / "source.md"
    selected.write_text("A safe local source.\n", encoding="utf-8")
    attached = SimpleNamespace(
        display_name="source.md",
        file_kind=SimpleNamespace(value="markdown"),
        sha256="a" * 64,
        size_bytes=21,
        parser_used="markdown",
        blocked_reason=None,
    )
    monkeypatch.setattr(
        service.file_ingest_service,
        "attach_file",
        lambda source_path, project_id: SimpleNamespace(
            ready=True,
            accepted=True,
            file=attached,
            file_id="file-source-a",
            errors=[],
        ),
    )

    result = service.attach_project_source(
        "project-a", service.ProjectSourceAttachRequest(source_path=str(selected))
    )
    assert result["source"]["display_name"] == "source.md"
    assert result["source"]["local_only"] is True
    assert "source_path" not in result["source"]
    assert "source_path" not in service.get_workbench("project-a")["sources"][0]


def test_project_ownership_mismatch_is_blocked(project_workbench, monkeypatch):
    monkeypatch.setattr(
        service.project_service,
        "get_project_metadata",
        lambda project_id: {"project_id": project_id, "owner_user_id": "owner-b"},
    )
    with pytest.raises(service.ProjectCapabilityError, match="another local account"):
        service.get_workbench("project-a")


def test_quiz_requires_grounding_and_goal_transition_is_bounded(project_workbench):
    with pytest.raises(service.ProjectCapabilityError, match="Provide source statements"):
        service.generate_quiz(
            "project-a", service.QuizGenerateRequest(source_material="no"),
        )

    goal = service.create_goal(
        "project-a",
        service.GoalCreateRequest(goal="Do bounded work", steps=["First"], budget_steps=1),
        autonomy_level=1,
    )["goal"]
    with pytest.raises(service.ProjectCapabilityError, match="not allowed"):
        service.transition_goal(
            "project-a",
            goal["goal_id"],
            service.GoalTransitionRequest(action="complete_step", step_id=goal["steps"][0]["step_id"]),
        )

    with pytest.raises(service.ProjectCapabilityError, match="Project/Agent ceiling"):
        service.create_goal(
            "project-a",
            service.GoalCreateRequest(goal="Must remain blocked by managed ceiling"),
            autonomy_level=1,
            project_agent_limit=0,
        )


def test_sustained_goal_has_scope_deadline_budgets_restart_pause_and_emergency_revocation(
    project_workbench, monkeypatch
):
    goal = service.create_goal(
        "project-a",
        service.GoalCreateRequest(
            goal="Synthetic sustained objective",
            exact_scope="Only prepare a local, reversible draft.",
            steps=["Draft", "Verify"],
            budget_steps=2,
            budget_minutes=15,
            max_tool_calls=3,
            max_network_requests=0,
            checkpoint_interval_steps=1,
        ),
        autonomy_level=5,
    )["goal"]
    assert goal["exact_scope"] == "Only prepare a local, reversible draft."
    assert goal["deadline_at_utc"].endswith("Z")
    assert goal["policy"]["external_mutation_requires_exact_approval"] is True
    assert goal["policy"]["authority_self_increase_allowed"] is False
    active = service.transition_goal(
        "project-a", goal["goal_id"], service.GoalTransitionRequest(action="start")
    )["goal"]
    assert active["status"] == "active"

    # A new process identity must never silently resume sustained work.
    monkeypatch.setattr(service, "_RUNTIME_INSTANCE_ID", "runtimeinstance_after_restart")
    recovered = service.get_workbench("project-a")["goals"][0]
    assert recovered["status"] == "paused"
    assert recovered["restart_resume_required"] is True
    assert recovered["receipts"][-1]["action"] == "restart_recovery_pause"

    assert service.emergency_stop_all_goals() == 1
    stopped = service.get_workbench("project-a")["goals"][0]
    assert stopped["status"] == "emergency_stopped"
    assert stopped["receipts"][-1]["action"] == "system_emergency_stop"
