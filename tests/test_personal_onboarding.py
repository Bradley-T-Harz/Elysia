from __future__ import annotations

from pathlib import Path

from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest, AccountLoginRequest
from app.memory.canonical_models import MemoryPrincipal, MemoryQuery
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService
from app.onboarding.schemas import (
    OnboardingAnswer,
    OnboardingDraftRequest,
    OnboardingFinalizeRequest,
)
from app.onboarding.service import PersonalOnboardingService


def _store(root: Path) -> AccountStore:
    identity = root / "data" / "identity"
    return AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )


def test_questionnaire_is_complete_optional_and_non_coercive(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_account(AccountCreateRequest(username="owner", password="owner-password"))
    service = PersonalOnboardingService(store)

    state = service.state()
    questions = [question for section in state["sections"] for question in section["questions"]]
    assert len(questions) == 33
    assert state["status"] == "not_started"
    assert state["may_skip_all"] is True
    assert state["canonical_memory_before_review"] is False
    assert state["external_egress"] is False

    skipped = service.finalize(OnboardingFinalizeRequest(action="skip"))
    assert skipped["status"] == "skipped"
    repository = MemoryRepository(paths=store.elysia_paths)
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    records, total = MemoryFabricService(repository=repository).list(
        principal, MemoryQuery(limit=100)
    )
    assert records == []
    assert total == 0


def test_draft_is_account_encrypted_resumable_and_cross_profile_isolated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    owner_password = "owner-password"
    second_password = "second-password"
    store.create_account(AccountCreateRequest(username="owner", password=owner_password))
    service = PersonalOnboardingService(store)
    canary = "ONBOARDING_PRIVATE_DRAFT_CANARY"
    service.save(
        OnboardingDraftRequest(
            answers=[
                OnboardingAnswer(
                    question_id="q01",
                    exact_answer=canary,
                    proposed_title="How Elysia can help",
                    proposed_wording="Help me finish careful work.",
                    privacy="private",
                )
            ]
        )
    )
    database_bytes = service.database_path.read_bytes()
    assert canary.encode() not in database_bytes
    assert b"Help me finish careful work." not in database_bytes

    store.logout()
    store.login(AccountLoginRequest(username="owner", password=owner_password))
    resumed = PersonalOnboardingService(store).state()
    assert resumed["answers"][0]["exact_answer"] == canary

    store.create_account(AccountCreateRequest(username="second", password=second_password))
    store.logout()
    store.login(AccountLoginRequest(username="second", password=second_password))
    second = PersonalOnboardingService(store).state()
    assert second["status"] == "not_started"
    assert second["answers"] == []


def test_reviewed_selected_import_only_creates_owner_memory_after_confirmation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    password = "owner-password"
    store.create_account(AccountCreateRequest(username="owner", password=password))
    service = PersonalOnboardingService(store)
    service.save(
        OnboardingDraftRequest(
            answers=[
                OnboardingAnswer(
                    question_id="q01",
                    exact_answer="Original answer one",
                    proposed_title="Useful collaboration",
                    proposed_wording="Prefer careful completion over rushed output.",
                    privacy="normal",
                    retention="persistent",
                ),
                OnboardingAnswer(
                    question_id="q02",
                    exact_answer="Temporary answer",
                    proposed_wording="Do not preserve this beyond onboarding.",
                    privacy="private",
                    retention="temporary",
                ),
                OnboardingAnswer(
                    question_id="q03",
                    exact_answer="Unselected answer",
                    proposed_wording="This answer was not selected.",
                    privacy="private",
                    retention="persistent",
                ),
            ]
        )
    )
    repository = MemoryRepository(paths=store.elysia_paths)
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    fabric = MemoryFabricService(repository=repository)
    before, before_total = fabric.list(principal, MemoryQuery(limit=100))
    assert before == []
    assert before_total == 0

    final = service.finalize(
        OnboardingFinalizeRequest(
            action="import_selected",
            selected_question_ids=["q01", "q02"],
        )
    )
    assert final["status"] == "completed"
    assert set(final["imported_memory_ids"]) == {"q01"}
    records, total = fabric.list(principal, MemoryQuery(limit=100))
    assert total == 1
    assert records[0].title == "Useful collaboration"
    assert records[0].body == "Prefer careful completion over rushed output."
    assert records[0].owner_user_id == principal.user_id
    assert records[0].user_confirmed is True
    assert records[0].sources[0]["source_type"] == "onboarding_declaration"
    assert "Temporary answer" not in service.database_path.read_text(
        encoding="latin-1", errors="ignore"
    )


def test_sealed_import_requires_reauthentication_and_relocks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    password = "owner-password"
    store.create_account(AccountCreateRequest(username="owner", password=password))
    service = PersonalOnboardingService(store)
    service.save(
        OnboardingDraftRequest(
            answers=[
                OnboardingAnswer(
                    question_id="q27",
                    exact_answer="Never infer this boundary.",
                    proposed_title="A sealed boundary",
                    proposed_wording="Do not assume private facts about me.",
                    privacy="sealed",
                )
            ]
        )
    )
    try:
        service.finalize(OnboardingFinalizeRequest(action="import_all"))
    except Exception as exc:
        assert "Reauthentication" in str(exc)
    else:
        raise AssertionError("Sealed onboarding import must require reauthentication.")

    state = service.finalize(
        OnboardingFinalizeRequest(action="import_all", sealed_password=password)
    )
    assert state["status"] == "completed"
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    fabric = MemoryFabricService(repository=MemoryRepository(paths=store.elysia_paths))
    record = fabric.get(principal, state["imported_memory_ids"]["q27"])
    assert record.privacy.value == "sealed"
    assert record.content_state == "sealed_locked"
