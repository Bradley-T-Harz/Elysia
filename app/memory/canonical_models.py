"""Typed public contracts for the canonical SQLite Memory Fabric."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MemoryScope(str, Enum):
    USER = "user"
    CONVERSATION = "conversation"
    PROJECT = "project"
    RESEARCH = "research"
    OPERATIONAL = "operational"
    SYSTEM = "system"
    SHARED_SPACE = "shared_space"


class MemoryForm(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PROSPECTIVE = "prospective"
    RELATIONAL = "relational"
    PREDICTIVE = "predictive"
    CORRECTIVE = "corrective"
    METACOGNITIVE = "metacognitive"
    AUDIT = "audit"


class MemoryPrivacy(str, Enum):
    NORMAL = "normal"
    PRIVATE = "private"
    SEALED = "sealed"


class MemoryLifecycle(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    WORKING = "working"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"
    BLOCKED = "blocked"
    DELETED = "deleted"


class ActivationTier(str, Enum):
    WORKING = "working"
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    ARCHIVED = "archived"


class SharedSpaceRole(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    CONTRIBUTOR = "contributor"
    READER = "reader"


class SharedSpaceInvitationDecision(str, Enum):
    ACCEPT = "accept"
    DECLINE = "decline"


class CandidateDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"
    SEAL = "seal"


class MemoryTruthChange(str, Enum):
    CORRECTION = "correction"
    REFINEMENT = "refinement"
    CHANGED_REALITY = "changed_reality"
    DIRECT_CONTRADICTION = "direct_contradiction"
    RETRACTION = "retraction"


class MemorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_recording_enabled: bool = True
    storage_resource_profile: str = Field(default="core_local", pattern=r"^(core_local|balanced_local|minimal_local)$")
    default_privacy: MemoryPrivacy = MemoryPrivacy.NORMAL
    candidate_behavior: str = Field(default="review_personal_inference", pattern=r"^(review_all|review_personal_inference|direct_explicit_only)$")
    autonomy_level: int = Field(default=3, ge=1, le=5)
    internet_master_enabled: bool = False
    retrieval_breadth: str = Field(default="balanced", pattern=r"^(focused|balanced|broad)$")
    research_initiative: str = Field(default="balanced", pattern=r"^(manual|balanced|proactive)$")
    safe_search_level: str = Field(default="strict", pattern=r"^(strict|moderate|off)$")
    preferred_reasoning_gear: str = Field(
        default="automatic",
        pattern=r"^(automatic|reflex|quick|standard|deep|deliberative|research_engineering)$",
    )
    autonomy_domain_overrides: dict[str, int] = Field(default_factory=dict)
    compute_preference: str = Field(default="automatic", pattern=r"^(automatic|cpu|gpu)$")
    model_performance_preference: str = Field(
        default="balanced", pattern=r"^(balanced|latency|quality|resource)$"
    )
    background_cognition_enabled: bool = False
    cpu_percent_ceiling: int = Field(default=85, ge=10, le=100)
    ram_mb_ceiling: int = Field(default=16384, ge=512, le=262_144)
    vram_mb_ceiling: int = Field(default=12288, ge=0, le=131_072)
    max_background_jobs: int = Field(default=2, ge=0, le=32)
    memory_storage_profile: str = Field(
        default="balanced", pattern=r"^(efficient|balanced|deep_memory|custom)$"
    )
    storage_budget_mode: str = Field(
        default="absolute_mb", pattern=r"^(absolute_mb|percent)$"
    )
    storage_budget_value: float = Field(default=8192, ge=1, le=10_000_000)
    emergency_free_space_reserve_mb: int = Field(default=2048, ge=256, le=1_000_000)
    consolidation_enabled: bool = True
    consolidation_schedule: str = Field(
        default="daily", pattern=r"^(manual|daily|weekly)$"
    )
    consolidation_resource_percent: int = Field(default=25, ge=5, le=75)
    backup_enabled: bool = False
    backup_schedule: str = Field(default="weekly", pattern=r"^(manual|daily|weekly)$")
    backup_retention_count: int = Field(default=3, ge=1, le=50)
    retention_policy: str = Field(
        default="balanced", pattern=r"^(conservative|balanced|compact)$"
    )
    hot_retention_days: int = Field(default=14, ge=1, le=3650)
    cold_after_days: int = Field(default=180, ge=7, le=36500)
    prospective_notifications_enabled: bool = True

    @model_validator(mode="after")
    def validate_domain_overrides(self) -> "MemorySettings":
        allowed = {
            "memory_capture",
            "scientific_promotion",
            "web_initiative",
            "project_initiative",
            "background_cognition",
            "coding_execution",
            "external_mutations",
        }
        unknown = sorted(set(self.autonomy_domain_overrides) - allowed)
        if unknown:
            raise ValueError(f"Unknown autonomy domain overrides: {', '.join(unknown)}")
        if any(value < 1 or value > 5 for value in self.autonomy_domain_overrides.values()):
            raise ValueError("Autonomy domain overrides must be Levels 1 through 5.")
        # Domain values are narrowing ceilings, never latent grants that become
        # active later when the global level changes.
        self.autonomy_domain_overrides = {
            key: min(int(value), self.autonomy_level)
            for key, value in self.autonomy_domain_overrides.items()
        }
        if self.storage_budget_mode == "percent" and self.storage_budget_value > 95:
            raise ValueError("Percentage storage budget must be at most 95 percent.")
        if self.hot_retention_days >= self.cold_after_days:
            raise ValueError("Cold-memory age must be greater than the hot-retention age.")
        return self


class MemorySourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: str = Field(default="manual_entry", min_length=1, max_length=64)
    source_id: str | None = Field(default=None, max_length=160)
    source_label: str | None = Field(default=None, max_length=200)
    source_time: str | None = Field(default=None, max_length=64)
    source_authority: str = Field(default="user", min_length=1, max_length=64)
    retrieval_method: str | None = Field(default=None, max_length=80)
    provenance_status: str = Field(default="declared", max_length=64)


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=240)
    body: str = Field(..., min_length=1, max_length=64_000)
    why_stored: str = Field(..., min_length=1, max_length=1_000)
    scope: MemoryScope = MemoryScope.USER
    form: MemoryForm = MemoryForm.SEMANTIC
    subtype: str | None = Field(default=None, max_length=100)
    privacy: MemoryPrivacy = MemoryPrivacy.NORMAL
    status: MemoryLifecycle = MemoryLifecycle.ACTIVE
    activation_tier: ActivationTier = ActivationTier.WARM
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    user_confirmed: bool = True
    inference_kind: str | None = Field(default=None, max_length=100)
    observed_at: str | None = Field(default=None, max_length=64)
    valid_from: str | None = Field(default=None, max_length=64)
    valid_until: str | None = Field(default=None, max_length=64)
    conversation_id: str | None = Field(default=None, max_length=160)
    message_id: str | None = Field(default=None, max_length=160)
    project_id: str | None = Field(default=None, max_length=160)
    request_id: str | None = Field(default=None, max_length=160)
    evidence_id: str | None = Field(default=None, max_length=160)
    artifact_id: str | None = Field(default=None, max_length=160)
    space_id: str | None = Field(default=None, max_length=160)
    form_data: dict[str, Any] = Field(default_factory=dict)
    source: MemorySourceInput = Field(default_factory=MemorySourceInput)

    @model_validator(mode="after")
    def validate_scope(self) -> "MemoryCreateRequest":
        required = {
            MemoryScope.CONVERSATION: self.conversation_id,
            MemoryScope.PROJECT: self.project_id,
            MemoryScope.SHARED_SPACE: self.space_id,
        }
        if self.scope in required and not required[self.scope]:
            raise ValueError(f"{self.scope.value} scope requires its stable authority id.")
        if self.privacy != MemoryPrivacy.NORMAL and self.space_id:
            raise ValueError("Private and Sealed memory cannot be created in a shared space.")
        if self.message_id and not self.conversation_id:
            raise ValueError("A linked message requires its stable conversation identifier.")
        if self.status == MemoryLifecycle.CANDIDATE and self.user_confirmed:
            raise ValueError("Candidate memory cannot already be user-confirmed.")
        encoded = str(self.form_data)
        if len(encoded) > 32_000:
            raise ValueError("Memory form data is too large.")
        if any(
            key in self.form_data
            for key in (
                "authority_grant", "permission_grant", "execute_automatically",
                "hidden_reasoning", "policy_override", "credential",
            )
        ):
            raise ValueError("Memory form data cannot grant authority or contain hidden control state.")
        if self.form == MemoryForm.EPISODIC and self.form_data:
            if not self.observed_at and not self.form_data.get("occurred_at"):
                raise ValueError("Episodic memory needs an observed event time.")
            if not any(self.form_data.get(key) for key in ("actors", "context", "outcome")):
                raise ValueError("Episodic memory needs bounded event context.")
        if self.form == MemoryForm.SEMANTIC and self.form_data:
            if not any(self.form_data.get(key) for key in ("confirmation", "claim_kind", "subject")):
                raise ValueError("Semantic memory needs an explicit claim/confirmation descriptor.")
        if self.form == MemoryForm.PROSPECTIVE:
            due = self.form_data.get("due_at") or self.valid_until
            condition = self.form_data.get("condition")
            if self.form_data and not due and not condition:
                raise ValueError("Prospective memory needs a due time or condition.")
            if due:
                try:
                    datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValueError("Prospective due time must be an ISO timestamp.") from exc
        if self.form == MemoryForm.PROCEDURAL and self.form_data:
            steps = self.form_data.get("steps")
            if not isinstance(steps, list) or not steps or not all(
                isinstance(step, str) and step.strip() for step in steps
            ):
                raise ValueError("Procedural memory steps must be a non-empty text list.")
        if self.form == MemoryForm.PREDICTIVE and self.form_data:
            if not str(self.form_data.get("basis") or "").strip():
                raise ValueError("Predictive memory needs a transparent basis.")
            if not str(self.form_data.get("prediction") or "").strip():
                raise ValueError("Predictive memory needs a frozen forecast statement.")
            if any(key in self.form_data for key in ("outcome", "outcome_score", "evaluated_at")):
                raise ValueError("A new prediction cannot already contain its later outcome.")
        if self.form == MemoryForm.RELATIONAL and self.form_data:
            if not str(self.form_data.get("relation") or "").strip() or not str(
                self.form_data.get("target") or ""
            ).strip():
                raise ValueError("Relational memory needs an explicit relation and target.")
        if self.form == MemoryForm.CORRECTIVE and self.form_data:
            if not str(self.form_data.get("change_kind") or "").strip():
                raise ValueError("Corrective memory needs an explicit change kind.")
        if self.form == MemoryForm.METACOGNITIVE and self.form_data:
            if not str(self.form_data.get("metric") or "").strip():
                raise ValueError("Metacognitive memory needs a content-free quality/strategy metric.")
        if self.form == MemoryForm.AUDIT and self.form_data:
            if not str(self.form_data.get("event_code") or "").strip() or self.form_data.get(
                "content_minimized"
            ) is not True:
                raise ValueError("Audit memory needs a content-minimized event code.")
        return self


class MemoryCandidateCreateRequest(MemoryCreateRequest):
    status: MemoryLifecycle = MemoryLifecycle.CANDIDATE
    user_confirmed: bool = False
    candidate_kind: str = Field(default="personal_inference", max_length=100)
    proposed_wording: str | None = Field(default=None, max_length=2_000)
    evidence_summary: str | None = Field(default=None, max_length=2_000)


class CandidateDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: CandidateDecision
    edited_title: str | None = Field(default=None, max_length=240)
    edited_body: str | None = Field(default=None, max_length=64_000)
    reason: str = Field(default="User reviewed memory candidate.", max_length=1_000)
    defer_until: str | None = Field(default=None, max_length=64)


class MemoryFormActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: str = Field(
        ...,
        pattern=r"^(snooze|complete|reopen|dismiss|record_outcome|verify_procedure|invalidate_procedure)$",
    )
    reason: str = Field(..., min_length=1, max_length=1_000)
    due_at: str | None = Field(default=None, max_length=64)
    outcome: str | None = Field(default=None, max_length=4_000)
    outcome_score: float | None = Field(default=None, ge=0.0, le=1.0)


class MemoryTierRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tier: ActivationTier
    reason: str = Field(..., min_length=1, max_length=1_000)
    automatic: bool = False


class MemorySuppressionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    suppressed: bool
    reason: str = Field(..., min_length=1, max_length=1_000)


class MemoryJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_kind: str = Field(
        ...,
        pattern=r"^(conversation_compaction|embedding_rebuild|fts_rebuild|semantic_candidates|duplicate_detection|relation_candidates|contradiction_scan|project_summary_refresh|tier_maintenance|archive_compression|graph_rebuild|object_integrity|projection_rebuild|homeostasis|managed_backup|integrity_check|metacognitive_statistics|consolidation|replay_validation)$",
    )


class MemoryArchiveExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recovery_material: str = Field(..., min_length=12, max_length=1_024)
    archive_kind: str = Field(
        default="portable_export", pattern=r"^(portable_export|managed_backup)$"
    )
    scope: str = Field(
        default="full_account",
        pattern=r"^(full_account|selected_project|selected_space|metadata_audit)$",
    )
    selected_authority_id: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_scope_selection(self) -> "MemoryArchiveExportRequest":
        selected = self.scope in {"selected_project", "selected_space"}
        if selected != bool(self.selected_authority_id):
            raise ValueError("Selected project/space export needs exactly one authority id.")
        return self


class MemoryArchiveRestorePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    archive_base64: str | None = Field(default=None, max_length=256_000_000)
    archive_id: str | None = Field(default=None, max_length=160)
    recovery_material: str = Field(..., min_length=12, max_length=1_024)

    @model_validator(mode="after")
    def validate_source(self) -> "MemoryArchiveRestorePreviewRequest":
        if bool(self.archive_base64) == bool(self.archive_id):
            raise ValueError("Provide exactly one archive source.")
        return self


class MemoryArchiveRestoreApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    restore_plan_id: str = Field(..., min_length=1, max_length=160)
    approval_id: str = Field(..., min_length=1, max_length=160)
    approval_token: str = Field(..., min_length=1, max_length=256)
    recovery_material: str = Field(..., min_length=12, max_length=1_024)


class MemoryCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=240)
    body: str = Field(..., min_length=1, max_length=64_000)
    reason: str = Field(..., min_length=1, max_length=1_000)
    observed_at: str | None = Field(default=None, max_length=64)
    valid_from: str | None = Field(default=None, max_length=64)
    valid_until: str | None = Field(default=None, max_length=64)
    change_kind: MemoryTruthChange = MemoryTruthChange.CORRECTION
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class MemoryRelationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_type: str = Field(
        ..., pattern=r"^(memory|conversation|message|project|request|evidence|artifact)$"
    )
    target_id: str = Field(..., min_length=1, max_length=160)
    relation_type: str = Field(..., min_length=1, max_length=80)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    inferred: bool = False
    provenance_source_id: str | None = Field(default=None, max_length=160)
    valid_from: str | None = Field(default=None, max_length=64)
    valid_until: str | None = Field(default=None, max_length=64)


class MemoryReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(..., min_length=1, max_length=1_000)


class MemoryPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned: bool


class SealedUnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(..., min_length=1, max_length=1_024)
    ttl_seconds: int = Field(default=300, ge=30, le=900)


class ConsequencePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: str = Field(
        ...,
        pattern=r"^(hard_delete|change_privacy|move_to_space|add_space_member|invite_space_member|change_space_member_role|remove_space_member)$",
    )
    target_privacy: MemoryPrivacy | None = None
    target_space_id: str | None = Field(default=None, max_length=160)
    target_user_id: str | None = Field(default=None, max_length=160)
    target_role: SharedSpaceRole | None = None
    reason: str = Field(..., min_length=1, max_length=1_000)


class ConsequenceApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    approval_id: str = Field(..., min_length=1, max_length=160)
    approval_token: str = Field(..., min_length=1, max_length=256)


class SharedSpaceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(..., min_length=1, max_length=160)
    description: str = Field(default="", max_length=1_000)


class SharedSpaceInvitationResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: SharedSpaceInvitationDecision


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search: str | None = Field(default=None, max_length=240)
    scope: MemoryScope | None = None
    form: MemoryForm | None = None
    privacy: MemoryPrivacy | None = None
    status: MemoryLifecycle | None = None
    activation_tier: ActivationTier | None = None
    space_id: str | None = Field(default=None, max_length=160)
    conversation_id: str | None = Field(default=None, max_length=160)
    project_id: str | None = Field(default=None, max_length=160)
    include_archived: bool = False
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=100_000)


class MemoryPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    username: str
    session_id: str
    session_token: str = Field(exclude=True, repr=False)


class MemoryContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str
    why_stored: str
    form_data: dict[str, Any] = Field(default_factory=dict)


class MemoryRecordView(BaseModel):
    model_config = ConfigDict(extra="allow")

    memory_id: str
    owner_user_id: str
    space_id: str | None = None
    scope: MemoryScope
    form: MemoryForm
    subtype: str | None = None
    privacy: MemoryPrivacy
    status: MemoryLifecycle
    title: str
    body: str | None = None
    why_stored: str | None = None
    content_state: str
    current_revision_id: str
    revision_number: int
    importance: float
    confidence: float | None = None
    user_confirmed: bool
    inference_kind: str | None = None
    created_at: str
    updated_at: str
    observed_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    activation_tier: ActivationTier
    pinned: bool
    egress_allowed: bool
    legacy_class: str | None = None
    form_data: dict[str, Any] = Field(default_factory=dict)
    automatic_recall_suppressed: bool = False
    expires_at: str | None = None
    retention_hold: bool = False
    sources: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    candidate_kind: str | None = None
    candidate_proposed_wording: str | None = None
    candidate_evidence_summary: str | None = None
    candidate_deferred_until: str | None = None


__all__ = tuple(name for name in globals() if name.startswith("Memory") or name.startswith("Shared") or name in {"ActivationTier", "CandidateDecision", "CandidateDecisionRequest", "ConsequenceApplyRequest", "ConsequencePreviewRequest", "SealedUnlockRequest"})
