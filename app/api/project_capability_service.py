"""Owner-scoped, XDG-local state for restored Project capabilities.

This module intentionally owns only durable project workbench state. Heavy
workers (Research, ImageForge, SpeechForge, GIMP) retain their own governed
services and are never imported here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api import file_ingest_service, project_service
from app.ids import new_id
from app.install.paths import resolve_elysia_paths
from app.ownership import current_user_id


STORE_VERSION = 2
MAX_SOURCE_CHARS = 24_000
MAX_CANVAS_ELEMENTS = 200
MAX_RESEARCH_EVIDENCE = 40
_LOCK = threading.RLock()
_SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_RUNTIME_INSTANCE_ID = new_id("runtimeinstance")


class ProjectCapabilityError(RuntimeError):
    """A project capability request could not be completed safely."""


class ProjectSourceAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_path: str = Field(min_length=1, max_length=4096)


class StudyPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: str = Field(min_length=1, max_length=240)
    goals: list[str] = Field(default_factory=list, max_length=12)
    source_material: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    difficulty: Literal["foundational", "intermediate", "advanced"] = "intermediate"

    @field_validator("goals")
    @classmethod
    def validate_goals(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip()[:240] for value in values if value.strip()]
        return cleaned[:12]


class StudyModuleReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["start", "complete", "needs_review", "reset"]
    reflection: str | None = Field(default=None, max_length=2000)
    confidence: int | None = Field(default=None, ge=1, le=5)


class QuizGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="Project knowledge check", min_length=1, max_length=240)
    source_material: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    difficulty: Literal["foundational", "intermediate", "advanced"] = "intermediate"
    question_count: int = Field(default=5, ge=1, le=12)


class QuizAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question_id: str = Field(min_length=1, max_length=120)
    answer: str = Field(min_length=1, max_length=2000)


class ResearchIterationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    investigation_id: str | None = Field(default=None, max_length=120)
    question: str = Field(min_length=1, max_length=1000)
    query: str = Field(min_length=1, max_length=1000)
    evidence_packets: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_RESEARCH_EVIDENCE)
    evidence_verified: bool = False


class ResearchTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["pause", "resume", "complete", "cancel"]


class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    goal: str = Field(min_length=1, max_length=1000)
    exact_scope: str | None = Field(default=None, max_length=2000)
    steps: list[str] = Field(default_factory=list, max_length=20)
    budget_steps: int = Field(default=8, ge=1, le=50)
    budget_minutes: int = Field(default=30, ge=1, le=1440)
    max_tool_calls: int = Field(default=12, ge=0, le=200)
    max_network_requests: int = Field(default=0, ge=0, le=200)
    checkpoint_interval_steps: int = Field(default=1, ge=1, le=10)
    stop_condition: str = Field(
        default="Stop at budget, deadline, policy boundary, failed verification, or operator revocation.",
        min_length=1,
        max_length=1000,
    )

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, values: list[str]) -> list[str]:
        return [value.strip()[:500] for value in values if value.strip()][:20]


class GoalTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["start", "pause", "resume", "complete_step", "stop", "emergency_stop"]
    step_id: str | None = Field(default=None, max_length=120)
    checkpoint_note: str | None = Field(default=None, max_length=2000)


class CanvasElement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    element_id: str = Field(default_factory=lambda: new_id("canvas_element"), max_length=120)
    kind: Literal["note", "heading", "link", "image_reference"] = "note"
    content: str = Field(min_length=1, max_length=4000)
    x: float = Field(default=40, ge=0, le=4000)
    y: float = Field(default=40, ge=0, le=4000)
    width: float = Field(default=260, ge=80, le=2000)
    height: float = Field(default=140, ge=48, le=2000)
    color: str = Field(default="bronze", pattern=r"^(bronze|teal|emerald|silver|oxide)$")


class CanvasUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="Project Canvas", min_length=1, max_length=240)
    elements: list[CanvasElement] = Field(default_factory=list, max_length=MAX_CANVAS_ELEMENTS)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _owner() -> str:
    owner = current_user_id()
    if not owner:
        raise ProjectCapabilityError("An authenticated local account is required.")
    return owner


def _owner_hash(owner: str) -> str:
    return hashlib.sha256(owner.encode("utf-8")).hexdigest()[:24]


def _store_root() -> Path:
    return resolve_elysia_paths().state_dir / "project-capabilities"


def _path(project_id: str, owner: str) -> Path:
    if not _SAFE_PROJECT_ID.fullmatch(project_id):
        raise ProjectCapabilityError("Project identifier contains unsupported characters.")
    return _store_root() / _owner_hash(owner) / f"{project_id}.json"


def _empty(project_id: str, owner: str) -> dict[str, Any]:
    now = _now()
    return {
        "store_version": STORE_VERSION,
        "project_id": project_id,
        "owner_user_id": owner,
        "created_at_utc": now,
        "updated_at_utc": now,
        "sources": [],
        "study_plans": [],
        "quizzes": [],
        "research_investigations": [],
        "goals": [],
        "canvas": {"title": "Project Canvas", "elements": [], "updated_at_utc": now},
    }


def _verify_project(project_id: str, owner: str) -> None:
    metadata = project_service.get_project_metadata(project_id)
    record_owner = metadata.get("owner_user_id")
    if record_owner and record_owner != owner:
        raise ProjectCapabilityError("The project belongs to another local account.")


def _load(project_id: str, owner: str) -> dict[str, Any]:
    _verify_project(project_id, owner)
    path = _path(project_id, owner)
    if not path.exists():
        return _empty(project_id, owner)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectCapabilityError("Project capability state is unreadable.") from exc
    if payload.get("owner_user_id") != owner or payload.get("project_id") != project_id:
        raise ProjectCapabilityError("Project capability ownership could not be verified.")
    payload.setdefault("research_investigations", [])
    recovered = False
    for goal in payload.setdefault("goals", []):
        if goal.get("status") == "active" and goal.get("runtime_instance_id") != _RUNTIME_INSTANCE_ID:
            goal["status"] = "paused"
            goal["restart_resume_required"] = True
            goal["updated_at_utc"] = _now()
            goal.setdefault("receipts", []).append({
                "action": "restart_recovery_pause",
                "created_at_utc": _now(),
                "status": "paused",
                "content_free": True,
            })
            recovered = True
    if recovered:
        _write(payload)
    return payload


def _write(payload: dict[str, Any]) -> dict[str, Any]:
    payload["updated_at_utc"] = _now()
    path = _path(str(payload["project_id"]), str(payload["owner_user_id"]))
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temp_path.replace(path)
        path.chmod(0o600)
    finally:
        temp_path.unlink(missing_ok=True)
    return payload


def _public(payload: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(payload))

    def scrub(value: Any) -> None:
        if isinstance(value, dict):
            for private_key in ("owner_user_id", "source_path", "source_material", "expected_answer"):
                value.pop(private_key, None)
            for child in value.values():
                scrub(child)
        elif isinstance(value, list):
            for child in value:
                scrub(child)

    scrub(result)
    return result


def get_workbench(project_id: str) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        return _public(_load(project_id, owner))


def attach_project_source(project_id: str, request: ProjectSourceAttachRequest) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        payload = _load(project_id, owner)
        result = file_ingest_service.attach_file(request.source_path, project_id=project_id)
        if not result.ready or not result.accepted or result.file is None:
            reason = result.errors[0] if result.errors else result.file.blocked_reason if result.file else None
            raise ProjectCapabilityError(reason or "The selected source was not accepted.")
        source = {
            "source_id": result.file_id,
            "display_name": result.file.display_name,
            "file_kind": str(getattr(result.file.file_kind, "value", result.file.file_kind)),
            "sha256": result.file.sha256,
            "size_bytes": result.file.size_bytes,
            "parser_used": result.file.parser_used,
            "source_path": str(Path(request.source_path).expanduser().resolve()),
            "attached_at_utc": _now(),
            "local_only": True,
            "memory_promoted": False,
        }
        existing = {item.get("source_id"): item for item in payload["sources"]}
        existing[source["source_id"]] = source
        payload["sources"] = list(existing.values())
        _write(payload)
        project_service.update_project_metadata(project_id, source_count=len(payload["sources"]))
        return _public({"project_id": project_id, "source": source, "source_count": len(payload["sources"])})


def _study_modules(topic: str, goals: list[str], source_material: str, difficulty: str) -> list[dict[str, Any]]:
    excerpts = [line.strip() for line in source_material.splitlines() if line.strip()][:8]
    objectives = goals or [f"Explain the central ideas in {topic}", f"Apply {topic} to a new example"]
    modules: list[dict[str, Any]] = []
    for index, objective in enumerate(objectives[:8], start=1):
        grounding = excerpts[(index - 1) % len(excerpts)] if excerpts else topic
        modules.append({
            "module_id": new_id("study_module"),
            "sequence": index,
            "objective": objective,
            "grounding_excerpt": grounding[:1000],
            "practice_prompt": f"Explain this in your own words, then give one {difficulty} example: {grounding[:500]}",
            "review_state": "not_started",
        })
    return modules


def create_study_plan(project_id: str, request: StudyPlanRequest) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        payload = _load(project_id, owner)
        source_digest = hashlib.sha256(request.source_material.encode("utf-8")).hexdigest()
        plan = {
            "study_plan_id": new_id("study_plan"),
            "topic": request.topic,
            "goals": request.goals,
            "difficulty": request.difficulty,
            "source_material": request.source_material,
            "source_sha256": source_digest,
            "grounding_state": "user_supplied_source",
            "modules": _study_modules(request.topic, request.goals, request.source_material, request.difficulty),
            "created_at_utc": _now(),
            "updated_at_utc": _now(),
        }
        payload["study_plans"].append(plan)
        _write(payload)
        return _public({"project_id": project_id, "study_plan": plan})


def review_study_module(
    project_id: str,
    study_plan_id: str,
    module_id: str,
    request: StudyModuleReviewRequest,
) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        payload = _load(project_id, owner)
        plan = next((item for item in payload["study_plans"] if item["study_plan_id"] == study_plan_id), None)
        if plan is None:
            raise ProjectCapabilityError("Study plan not found.")
        module = next((item for item in plan["modules"] if item["module_id"] == module_id), None)
        if module is None:
            raise ProjectCapabilityError("Study module not found.")
        allowed = {
            "not_started": {"start", "complete", "needs_review"},
            "in_progress": {"complete", "needs_review", "reset"},
            "completed": {"needs_review", "reset"},
            "review_due": {"start", "complete", "reset"},
        }
        if request.action not in allowed.get(module.get("review_state", "not_started"), set()):
            raise ProjectCapabilityError("That study transition is not allowed in the current module state.")
        module["review_state"] = {
            "start": "in_progress",
            "complete": "completed",
            "needs_review": "review_due",
            "reset": "not_started",
        }[request.action]
        module.setdefault("review_history", []).append({
            "action": request.action,
            "reflection": request.reflection,
            "confidence": request.confidence,
            "recorded_at_utc": _now(),
        })
        completed = sum(1 for item in plan["modules"] if item["review_state"] == "completed")
        plan["progress"] = {
            "completed_modules": completed,
            "module_count": len(plan["modules"]),
            "percent": round((completed / max(1, len(plan["modules"]))) * 100),
            "review_due": sum(1 for item in plan["modules"] if item["review_state"] == "review_due"),
        }
        plan["updated_at_utc"] = _now()
        _write(payload)
        return _public({"project_id": project_id, "study_plan": plan, "study_module": module})


def _bounded_evidence(packet: dict[str, Any]) -> dict[str, Any]:
    """Keep only public evidence/provenance fields needed for local continuity."""
    allowed = {
        "evidence_id", "source_url", "title", "retrieved_at_utc", "snippet", "claim",
        "confidence", "contradiction_notes", "source_type", "retrieval_method",
        "source_rank", "source_date", "publisher", "authors", "supports_claim", "warnings",
    }
    result = {key: packet[key] for key in allowed if key in packet}
    encoded = json.dumps(result, ensure_ascii=False)
    if len(encoded) > 12_000:
        result["snippet"] = str(result.get("snippet", ""))[:2000]
        result["contradiction_notes"] = list(result.get("contradiction_notes") or [])[:8]
        result["warnings"] = list(result.get("warnings") or [])[:8]
    return result


def _contradiction_summary(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    explicit = [
        note
        for packet in evidence
        for note in list(packet.get("contradiction_notes") or [])
        if isinstance(note, str) and note.strip()
    ]
    claim_positions: dict[str, set[bool]] = {}
    for packet in evidence:
        claim = str(packet.get("claim") or "").strip().casefold()
        support = packet.get("supports_claim")
        if claim and isinstance(support, bool):
            claim_positions.setdefault(claim, set()).add(support)
    conflicts = [claim for claim, positions in claim_positions.items() if len(positions) > 1]
    return {
        "explicit_notes": explicit[:20],
        "conflicting_claims": conflicts[:20],
        "status": "contradictions_present" if explicit or conflicts else "none_recorded",
    }


def record_research_iteration(project_id: str, request: ResearchIterationRequest) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        payload = _load(project_id, owner)
        investigations = payload["research_investigations"]
        investigation = next(
            (item for item in investigations if item["investigation_id"] == request.investigation_id),
            None,
        )
        if request.investigation_id and investigation is None:
            raise ProjectCapabilityError("Research investigation not found.")
        if investigation is None:
            investigation = {
                "investigation_id": new_id("research_investigation"),
                "question": request.question,
                "status": "active",
                "iterations": [],
                "evidence": [],
                "created_at_utc": _now(),
            }
            investigations.append(investigation)
        if investigation["status"] != "active":
            raise ProjectCapabilityError("Research must be active before another investigation step is recorded.")
        evidence = [_bounded_evidence(packet) for packet in request.evidence_packets]
        investigation["iterations"].append({
            "iteration_id": new_id("research_iteration"),
            "query": request.query,
            "evidence_count": len(evidence),
            "evidence_verified": request.evidence_verified,
            "recorded_at_utc": _now(),
        })
        known_ids = {str(item.get("evidence_id") or item.get("source_url")) for item in investigation["evidence"]}
        for packet in evidence:
            identity = str(packet.get("evidence_id") or packet.get("source_url"))
            if identity not in known_ids:
                investigation["evidence"].append(packet)
                known_ids.add(identity)
        investigation["source_count"] = len({item.get("source_url") for item in investigation["evidence"] if item.get("source_url")})
        investigation["comparison"] = _contradiction_summary(investigation["evidence"])
        investigation["updated_at_utc"] = _now()
        _write(payload)
        return _public({"project_id": project_id, "research_investigation": investigation})


def transition_research(project_id: str, investigation_id: str, request: ResearchTransitionRequest) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        payload = _load(project_id, owner)
        investigation = next(
            (item for item in payload["research_investigations"] if item["investigation_id"] == investigation_id),
            None,
        )
        if investigation is None:
            raise ProjectCapabilityError("Research investigation not found.")
        allowed = {
            "active": {"pause", "complete", "cancel"},
            "paused": {"resume", "complete", "cancel"},
            "completed": set(),
            "cancelled": set(),
        }
        if request.action not in allowed.get(investigation["status"], set()):
            raise ProjectCapabilityError("That research transition is not allowed in the current state.")
        investigation["status"] = {
            "pause": "paused", "resume": "active", "complete": "completed", "cancel": "cancelled",
        }[request.action]
        investigation["updated_at_utc"] = _now()
        _write(payload)
        return _public({"project_id": project_id, "research_investigation": investigation})


def _fact_pairs(source: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in source.splitlines():
        line = " ".join(raw.strip().split())
        if len(line) < 3:
            continue
        if "::" in line:
            term, definition = line.split("::", 1)
        elif ":" in line and len(line.split(":", 1)[0]) <= 100:
            term, definition = line.split(":", 1)
        else:
            term, definition = f"Source statement {len(pairs) + 1}", line
        term, definition = term.strip(), definition.strip()
        if term and definition:
            pairs.append((term[:240], definition[:2000]))
    return pairs


def generate_quiz(project_id: str, request: QuizGenerateRequest) -> dict[str, Any]:
    owner = _owner()
    facts = _fact_pairs(request.source_material)
    if not facts:
        raise ProjectCapabilityError("Provide source statements or `term: definition` lines before generating a quiz.")
    with _LOCK:
        payload = _load(project_id, owner)
        questions = []
        for term, answer in facts[: request.question_count]:
            questions.append({
                "question_id": new_id("quiz_question"),
                "prompt": f"What does the supplied source say about {term}?",
                "expected_answer": answer,
                "answer_sha256": hashlib.sha256(answer.casefold().encode("utf-8")).hexdigest(),
                "explanation": f"Grounded source statement: {answer}",
                "attempts": [],
                "mastered": False,
            })
        quiz = {
            "quiz_id": new_id("quiz"),
            "title": request.title,
            "difficulty": request.difficulty,
            "source_material": request.source_material,
            "source_sha256": hashlib.sha256(request.source_material.encode("utf-8")).hexdigest(),
            "grounding_state": "user_supplied_source",
            "questions": questions,
            "score": 0,
            "created_at_utc": _now(),
            "updated_at_utc": _now(),
        }
        payload["quizzes"].append(quiz)
        _write(payload)
        return _public({"project_id": project_id, "quiz": quiz})


def _normalized_words(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if len(word) > 2}


def answer_quiz(project_id: str, quiz_id: str, request: QuizAnswerRequest) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        payload = _load(project_id, owner)
        quiz = next((item for item in payload["quizzes"] if item["quiz_id"] == quiz_id), None)
        if quiz is None:
            raise ProjectCapabilityError("Quiz not found.")
        question = next((item for item in quiz["questions"] if item["question_id"] == request.question_id), None)
        if question is None:
            raise ProjectCapabilityError("Quiz question not found.")
        expected_words = _normalized_words(question["expected_answer"])
        answer_words = _normalized_words(request.answer)
        overlap = len(expected_words & answer_words) / max(1, len(expected_words))
        correct = request.answer.casefold().strip() == question["expected_answer"].casefold().strip() or overlap >= 0.7
        attempt = {
            "attempted_at_utc": _now(),
            "answer": request.answer,
            "correct": correct,
            "keyword_overlap": round(overlap, 3),
        }
        question["attempts"].append(attempt)
        question["mastered"] = bool(correct)
        quiz["score"] = sum(1 for item in quiz["questions"] if item["mastered"])
        quiz["updated_at_utc"] = _now()
        _write(payload)
        return {
            "project_id": project_id,
            "quiz_id": quiz_id,
            "question_id": request.question_id,
            "correct": correct,
            "score": quiz["score"],
            "question_count": len(quiz["questions"]),
            "explanation": question["explanation"],
            "attempt_count": len(question["attempts"]),
        }


def create_goal(
    project_id: str,
    request: GoalCreateRequest,
    *,
    autonomy_level: int,
    project_agent_limit: int = 32,
) -> dict[str, Any]:
    owner = _owner()
    steps = request.steps or [
        "Clarify the desired outcome and constraints.",
        "Review available project sources and current state.",
        "Prepare the next bounded action for operator review.",
    ]
    now = datetime.now(UTC).replace(microsecond=0)
    deadline = now + timedelta(minutes=request.budget_minutes)
    with _LOCK:
        payload = _load(project_id, owner)
        active_count = sum(
            1
            for item in payload.get("goals", [])
            if item.get("status") in {"draft", "active", "paused"}
        )
        if active_count >= max(0, int(project_agent_limit)):
            raise ProjectCapabilityError(
                "The effective managed-profile Project/Agent ceiling is exhausted."
            )
        goal = {
            "goal_id": new_id("goal"),
            "goal": request.goal,
            "exact_scope": request.exact_scope or request.goal,
            "status": "draft",
            "autonomy_level": autonomy_level,
            "budget_steps": request.budget_steps,
            "budget_minutes": request.budget_minutes,
            "max_tool_calls": request.max_tool_calls,
            "max_network_requests": request.max_network_requests,
            "tool_calls_used": 0,
            "network_requests_used": 0,
            "deadline_at_utc": deadline.isoformat().replace("+00:00", "Z"),
            "checkpoint_interval_steps": request.checkpoint_interval_steps,
            "stop_condition": request.stop_condition,
            "steps_used": 0,
            "steps": [
                {"step_id": new_id("goal_step"), "sequence": index, "description": text, "status": "pending"}
                for index, text in enumerate(steps[: request.budget_steps], start=1)
            ],
            "checkpoints": [],
            "receipts": [],
            "created_at_utc": now.isoformat().replace("+00:00", "Z"),
            "updated_at_utc": now.isoformat().replace("+00:00", "Z"),
            "restart_resume_required": False,
            "runtime_instance_id": None,
            "policy": {
                "hidden_execution": False,
                "shell_allowed": False,
                "push_allowed": False,
                "publication_allowed": False,
                "external_mutation_requires_exact_approval": True,
                "external_mutation_approval_present": False,
                "authority_self_increase_allowed": False,
                "operator_stop_always_available": True,
            },
        }
        payload["goals"].append(goal)
        _write(payload)
        return _public({"project_id": project_id, "goal": goal})


def transition_goal(project_id: str, goal_id: str, request: GoalTransitionRequest) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        payload = _load(project_id, owner)
        goal = next((item for item in payload["goals"] if item["goal_id"] == goal_id), None)
        if goal is None:
            raise ProjectCapabilityError("Goal not found.")
        action = request.action
        try:
            deadline = datetime.fromisoformat(str(goal["deadline_at_utc"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            created = datetime.fromisoformat(str(goal["created_at_utc"]).replace("Z", "+00:00"))
            deadline = created + timedelta(minutes=int(goal.get("budget_minutes") or 30))
            goal["deadline_at_utc"] = deadline.isoformat().replace("+00:00", "Z")
        if datetime.now(UTC) >= deadline and action not in {"stop", "emergency_stop"}:
            goal["status"] = "timed_out"
            goal.setdefault("receipts", []).append({
                "action": "deadline_exhausted",
                "created_at_utc": _now(),
                "status": "timed_out",
                "content_free": True,
            })
            _write(payload)
            raise ProjectCapabilityError("Goal deadline is exhausted; create a newly bounded goal to continue.")
        allowed = {
            "draft": {"start", "stop", "emergency_stop"},
            "active": {"pause", "complete_step", "stop", "emergency_stop"},
            "paused": {"resume", "stop", "emergency_stop"},
            "completed": set(),
            "stopped": set(),
            "emergency_stopped": set(),
            "timed_out": set(),
        }
        if action not in allowed.get(goal["status"], set()):
            raise ProjectCapabilityError(f"Action {action} is not allowed while goal is {goal['status']}.")
        if action == "start" or action == "resume":
            goal["status"] = "active"
            goal["runtime_instance_id"] = _RUNTIME_INSTANCE_ID
            goal["restart_resume_required"] = False
        elif action == "pause":
            goal["status"] = "paused"
        elif action in {"stop", "emergency_stop"}:
            goal["status"] = "emergency_stopped" if action == "emergency_stop" else "stopped"
        elif action == "complete_step":
            step = next((item for item in goal["steps"] if item["step_id"] == request.step_id), None)
            if step is None or step["status"] != "pending":
                raise ProjectCapabilityError("A pending step_id is required.")
            if goal["steps_used"] >= goal["budget_steps"]:
                raise ProjectCapabilityError("Goal step budget is exhausted.")
            step["status"] = "completed"
            step["completed_at_utc"] = _now()
            goal["steps_used"] += 1
            goal["checkpoints"].append({
                "checkpoint_id": new_id("goal_checkpoint"),
                "step_id": step["step_id"],
                "note": request.checkpoint_note or "Operator confirmed bounded step completion.",
                "created_at_utc": _now(),
            })
            if all(item["status"] == "completed" for item in goal["steps"]):
                goal["status"] = "completed"
        goal["updated_at_utc"] = _now()
        goal["receipts"].append({"action": action, "created_at_utc": _now(), "status": goal["status"]})
        _write(payload)
        return _public({"project_id": project_id, "goal": goal})


def emergency_stop_all_goals() -> int:
    """Stop persisted sustained workflows without exposing their content."""
    root = _store_root()
    if not root.exists():
        return 0
    stopped = 0
    with _LOCK:
        for path in root.glob("*/*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            changed = False
            for goal in payload.get("goals", []):
                if goal.get("status") in {"active", "paused", "draft"}:
                    goal["status"] = "emergency_stopped"
                    goal["runtime_instance_id"] = None
                    goal["restart_resume_required"] = False
                    goal.setdefault("receipts", []).append({
                        "action": "system_emergency_stop",
                        "created_at_utc": _now(),
                        "status": "emergency_stopped",
                        "content_free": True,
                    })
                    changed = True
                    stopped += 1
            if changed:
                _write(payload)
    return stopped


def update_canvas(project_id: str, request: CanvasUpdateRequest) -> dict[str, Any]:
    owner = _owner()
    with _LOCK:
        payload = _load(project_id, owner)
        payload["canvas"] = {
            "title": request.title,
            "elements": [element.model_dump(mode="json") for element in request.elements],
            "updated_at_utc": _now(),
        }
        _write(payload)
        return _public({"project_id": project_id, "canvas": payload["canvas"]})


__all__ = (
    "CanvasUpdateRequest",
    "GoalCreateRequest",
    "GoalTransitionRequest",
    "ProjectCapabilityError",
    "ProjectSourceAttachRequest",
    "QuizAnswerRequest",
    "QuizGenerateRequest",
    "ResearchIterationRequest",
    "ResearchTransitionRequest",
    "StudyPlanRequest",
    "StudyModuleReviewRequest",
    "answer_quiz",
    "attach_project_source",
    "create_goal",
    "create_study_plan",
    "generate_quiz",
    "get_workbench",
    "emergency_stop_all_goals",
    "record_research_iteration",
    "review_study_module",
    "transition_research",
    "transition_goal",
    "update_canvas",
)
