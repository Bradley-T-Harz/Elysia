"""Typed contracts for voluntary post-account personal onboarding."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OnboardingPrivacy(str, Enum):
    NORMAL = "normal"
    PRIVATE = "private"
    SEALED = "sealed"


class OnboardingRetention(str, Enum):
    PERSISTENT = "persistent"
    TEMPORARY = "temporary"
    NOT_REMEMBERED = "not_remembered"


class OnboardingAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_id: str = Field(..., pattern=r"^q(?:0[1-9]|[12][0-9]|3[0-3])$")
    exact_answer: str = Field(default="", max_length=12_000)
    proposed_title: str = Field(default="", max_length=240)
    proposed_wording: str = Field(default="", max_length=12_000)
    privacy: OnboardingPrivacy = OnboardingPrivacy.PRIVATE
    retention: OnboardingRetention = OnboardingRetention.PERSISTENT

    @model_validator(mode="after")
    def proposal_defaults(self) -> "OnboardingAnswer":
        if self.exact_answer and not self.proposed_wording:
            self.proposed_wording = self.exact_answer
        return self


class OnboardingDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[OnboardingAnswer] = Field(default_factory=list, max_length=33)

    @model_validator(mode="after")
    def unique_questions(self) -> "OnboardingDraftRequest":
        ids = [answer.question_id for answer in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("Each onboarding question may appear at most once.")
        return self


class OnboardingFinalizeAction(str, Enum):
    IMPORT_ALL = "import_all"
    IMPORT_SELECTED = "import_selected"
    IMPORT_NONE = "import_none"
    RETAIN_DRAFT = "retain_draft"
    DISCARD = "discard"
    SKIP = "skip"


class OnboardingFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: OnboardingFinalizeAction
    selected_question_ids: list[str] = Field(default_factory=list, max_length=33)
    sealed_password: str | None = Field(default=None, min_length=1, max_length=1024)


__all__ = (
    "OnboardingAnswer",
    "OnboardingDraftRequest",
    "OnboardingFinalizeAction",
    "OnboardingFinalizeRequest",
    "OnboardingPrivacy",
    "OnboardingRetention",
)
