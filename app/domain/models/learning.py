"""Các record và projection có scope cho knowledge."""

import json
from typing import Annotated, Literal
from pydantic import StringConstraints, model_validator
from app.domain.models.skills import (Id, Hash, Positive, Nonnegative, EvolvableSkillId, FactKind,
    PolicyAction, EvidenceFact, SkillBundle, PlatformSkillView, PolicyStep, check_pair, canonical, digest)
from pydantic import Field
from app.domain.models.shops import StrictModel, ShopRules
from app.domain.models.packages import Package


class Preference(StrictModel):
    pref_id: str
    shop_id: str
    field: Literal["content_style", "voucher_max_pct"]
    value: str
    status: Literal["candidate", "asked", "confirmed", "declined"]
    evidence_seqs: list[int] = Field(default_factory=list)
    asked_day: int | None = None
    declined_until: int | None = None

    @property
    def observation_count(self) -> int:
        return len(set(self.evidence_seqs))


class Calibration(StrictModel):
    category: str
    ratios: list[float] = Field(default_factory=list, max_length=30)
    factor: float = 1.0
    q_low: float = 1.0
    q_high: float = 1.0


class LessonOp(StrictModel):
    op: Literal["ADD", "UPVOTE", "DOWNVOTE", "EDIT"]
    lesson_id: str | None
    text_vi: str
    scope: str
    evidence: list[str]


class NightSummary(StrictModel):
    day: int
    history_updates: list[str]
    pref_candidates: list[str]
    calibration: dict[str, float | int | None]
    lesson_ops: list[LessonOp]
    rejected_ops: int
    memory_md_path: str | None = None


class PublicOutcome(StrictModel):
    orders: int
    revenue: int
    ads_spend: int
    roas: float | None


class PublicHistory(StrictModel):
    negotiation_id: str
    shop_id: str
    day: int
    kind: str
    status: Literal["agreed", "failed", "warning_only"]
    rounds: int
    proposed_package: Package | None = None
    agreed_package: Package | None = None
    approved_package: Package | None = None
    seller_action: str | None = None
    ads_paused: bool = False
    outcome: PublicOutcome | None = None
    evidence_seqs: list[int] = Field(default_factory=list)
    version: int = 1


class CalibrationSample(StrictModel):
    sample_id: str
    prediction_id: str
    shop_id: str
    target_day: int
    raw_point: float
    actual_orders: int
    ratio: float
    evidence_seqs: list[int]


class CalibrationRecord(StrictModel):
    category: str
    value: Calibration
    samples: list[CalibrationSample]
    version: int


class PublicLesson(StrictModel):
    lesson_id: str
    scope: str
    text_vi: str
    score: int
    evidence: list[str]
    created_day: int
    updated_day: int
    version: int


class PlatformMemoryView(StrictModel):
    history: list[PublicHistory]
    calibration: Calibration | None
    lessons: list[PublicLesson]
    knowledge_revision: int
    skill: PlatformSkillView | None = None


class ShopMemoryView(StrictModel):
    rules: ShopRules
    rules_version: int
    rules_evidence_seqs: list[int]
    preferences: list[Preference]
    knowledge_revision: int


class ContentMemoryView(StrictModel):
    confirmed_style_notes: list[str]
    rules_version: int
    preference_ids: list[str]


class PublicEvidence(StrictModel):
    seq: int
    type: str
    negotiation_id: str | None = None
    text_vi: str = ""
    package: Package | None = None
    seller_action: str | None = None
    feedback_vi: str | None = None
    outcome: PublicOutcome | None = None


class LearningEvidence(StrictModel):
    day: int
    from_seq: int
    through_seq: int
    events: list[PublicEvidence]
    existing_lessons: list[PublicLesson]
    valid_negotiation_ids: list[str]
    knowledge_revision: int
    skill_facts: list[EvidenceFact] = Field(default_factory=list)
    skill_bundles: list[SkillBundle] = Field(default_factory=list, max_length=2)

    @model_validator(mode='after')
    def bundle_targets(self):
        ids = [b.skill.skill_id for b in self.skill_bundles]
        if len(set(ids)) != len(ids) or any(i not in ('platform_offer', 'platform_renew') for i in ids):
            raise ValueError('LEARNING_BUNDLE_TARGETS')
        return self


class LessonBatch(StrictModel):
    ops: list[LessonOp] = Field(max_length=3)


class MemoryUpdateBatch(StrictModel):
    day: int
    through_seq: int
    history: list[PublicHistory]
    preferences: list[Preference]
    calibration: list[CalibrationRecord]
    lesson_ops: list[LessonOp]
    valid_negotiation_ids: list[str]


class StoreWrite(StrictModel):
    namespace: tuple[str, str, str]
    key: str
    value: PublicHistory | Preference | CalibrationRecord | PublicLesson | None


class MemoryCommit(StrictModel):
    revision: int
    cursor: int
    applied_ids: list[str]
    duplicate: bool


class KnowledgeCommit(StrictModel):
    store: MemoryCommit
    accepted_lesson_ops: list[LessonOp]
    rejected_ops: int


Source = Literal["live", "replay", "offline", "fixture", "skipped"]
RejectionCode = Literal['INVALID_PAIR','SCOPE_DENIED','STALE_SKILL','UNKNOWN_FACT','WRONG_FACT_KIND',
    'NO_FRESH_EVIDENCE','EVIDENCE_MISMATCH','DUPLICATE_EVIDENCE','DUPLICATE_POLICY','MISSING_POLICY',
    'STALE_LESSON','INVALID_LESSON','PRIVATE_VALIDATION_UNAVAILABLE','CANDIDATE_EVAL_FAILED']

class SkillPatchProposal(StrictModel):
    lesson_op: LessonOp
    target_skill: EvolvableSkillId
    trigger: FactKind
    action: PolicyAction
    evidence_fact_ids: list[Hash] = Field(min_length=1, json_schema_extra={'uniqueItems': True})
    base_skill_version: Nonnegative

    @model_validator(mode='after')
    def pair(self):
        check_pair(self.target_skill, self.trigger, self.action)
        if len(set(self.evidence_fact_ids)) != len(self.evidence_fact_ids):
            raise ValueError('DUPLICATE_EVIDENCE')
        return self


class NightReflectionOutput(StrictModel):
    ops: list[LessonOp] = Field(default_factory=list, max_length=3)
    proposals: list[SkillPatchProposal] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def cap(self):
        if len(self.ops) + len(self.proposals) > 3:
            raise ValueError('MAX_THREE_OPERATIONS')
        return self


class SkillVersion(StrictModel):
    bundle: SkillBundle
    parent_version: Nonnegative
    created_day: Positive
    source_through_seq: Nonnegative
    artifact_json: str
    eval_level: Literal['static', 'deterministic', 'provider']
    eval_checks: list[Id] = Field(default_factory=list, json_schema_extra={'uniqueItems': True})

    @model_validator(mode='after')
    def version(self):
        if self.bundle.skill.skill_id not in ('platform_offer', 'platform_renew'):
            raise ValueError('EVOLVE_TARGET_DENIED')
        if self.bundle.version != self.parent_version + 1:
            raise ValueError('PARENT_VERSION_MISMATCH')
        if self.bundle.effective_from_day != self.created_day + 1:
            raise ValueError('EFFECTIVE_DAY_MISMATCH')
        if self.artifact_json.encode('utf-8') != canonical(self.bundle.skill.model_dump(mode='json')):
            raise ValueError('NON_CANONICAL_ARTIFACT')
        if len(set(self.eval_checks)) != len(self.eval_checks):
            raise ValueError('DUPLICATE_EVAL_CHECK')
        return self


class PatchRejection(StrictModel):
    origin: Literal['op', 'proposal']
    index: Nonnegative
    code: RejectionCode
    policy_id: Id | None = None


class NightSnapshot(StrictModel):
    run_id: Id
    shop_id: Id
    category: Id
    day: Positive
    expected_revision: Nonnegative
    expected_cursor: Nonnegative
    through_seq: Nonnegative
    evidence: LearningEvidence
    derived: MemoryUpdateBatch
    calibration_summary: dict[str, float | int | None]
    prior_versions: list[SkillVersion] = Field(default_factory=list, max_length=2)
    base_texts: dict[EvolvableSkillId, str] = Field(min_length=2, max_length=2)
    snapshot_hash: Hash

    @model_validator(mode='after')
    def snapshot(self):
        if self.expected_cursor > self.through_seq:
            raise ValueError('CURSOR_AFTER_CUTOFF')
        if self.derived.lesson_ops:
            raise ValueError('DERIVED_BATCH_HAS_MODEL_OPS')
        if any(x.day != self.day or x.through_seq != self.through_seq for x in (self.evidence, self.derived)):
            raise ValueError('SNAPSHOT_SCOPE_MISMATCH')
        for fact in self.evidence.skill_facts:
            if (fact.run_id, fact.shop_id, fact.category) != (self.run_id, self.shop_id, self.category):
                raise ValueError('FACT_SCOPE_MISMATCH')
            if fact.day > self.day or fact.support_seq > self.through_seq:
                raise ValueError('FUTURE_EVIDENCE')
        for bundle in self.evidence.skill_bundles:
            if (bundle.run_id, bundle.shop_id, bundle.category) != (self.run_id, self.shop_id, self.category):
                raise ValueError('BUNDLE_SCOPE_MISMATCH')
        ids = [v.bundle.skill.skill_id for v in self.prior_versions]
        if len(set(ids)) != len(ids):
            raise ValueError('DUPLICATE_PRIOR_VERSION')
        for version in self.prior_versions:
            b = version.bundle
            if (b.run_id, b.shop_id, b.category) != (self.run_id, self.shop_id, self.category):
                raise ValueError('PRIOR_VERSION_SCOPE_MISMATCH')
            if version.created_day >= self.day or version.source_through_seq > self.through_seq:
                raise ValueError('FUTURE_PRIOR_VERSION')
        value = self.model_dump(mode='json', exclude={'snapshot_hash', 'expected_revision', 'expected_cursor'})
        if self.snapshot_hash != digest(value):
            raise ValueError('SNAPSHOT_HASH_MISMATCH')
        return self


class ReflectionReceipt(StrictModel):
    run_id: Id
    shop_id: Id
    day: Positive
    snapshot_hash: Hash
    owner_token: Id
    status: Literal['reserved', 'completed', 'failed', 'unknown']
    output: NightReflectionOutput | None
    source: Source
    error_code: str | None

    @model_validator(mode='after')
    def terminal(self):
        if (self.status == 'completed') != (self.output is not None):
            raise ValueError('REFLECTION_OUTPUT_STATUS_MISMATCH')
        if self.status == 'reserved' and (self.source != 'skipped' or self.error_code is not None):
            raise ValueError('REFLECTION_RESERVED_INVALID')
        if self.status in ('failed', 'unknown') and (self.source != 'skipped' or not self.error_code):
            raise ValueError('REFLECTION_ERROR_REQUIRED')
        if self.status == 'completed' and (self.source == 'skipped' or self.error_code is not None):
            raise ValueError('REFLECTION_SOURCE_INVALID')
        return self


class StagedLearning(StrictModel):
    writes: list[StoreWrite] = Field(default_factory=list)
    lessons: list[PublicLesson] = Field(default_factory=list)
    steps: list[PolicyStep] = Field(default_factory=list)
    accepted_ops: list[LessonOp] = Field(default_factory=list)
    rejections: list[PatchRejection] = Field(default_factory=list)


class NightPublication(StrictModel):
    run_id: Id
    shop_id: Id
    day: Positive
    snapshot_hash: Hash
    through_seq: Nonnegative
    writes: list[StoreWrite] = Field(default_factory=list)
    versions: list[SkillVersion] = Field(default_factory=list, max_length=2)
    summary: NightSummary
    rejections: list[PatchRejection] = Field(default_factory=list)
    source: Source

    @model_validator(mode='after')
    def publication(self):
        if self.summary.day != self.day or self.summary.rejected_ops != len(self.rejections):
            raise ValueError('SUMMARY_MISMATCH')
        if any(w.namespace[0] != self.run_id or w.namespace[1] not in
               ('history', 'preferences', 'calibration', 'lessons') for w in self.writes):
            raise ValueError('WRITE_SCOPE_DENIED')
        ids = [v.bundle.skill.skill_id for v in self.versions]
        if len(set(ids)) != len(ids):
            raise ValueError('DUPLICATE_SKILL_VERSION')
        for version in self.versions:
            if (version.bundle.run_id, version.bundle.shop_id) != (self.run_id, self.shop_id):
                raise ValueError('VERSION_SCOPE_MISMATCH')
            if version.created_day != self.day or version.source_through_seq != self.through_seq:
                raise ValueError('VERSION_CUTOFF_MISMATCH')
            if version.eval_level != 'deterministic':
                raise ValueError('NIGHT_CANNOT_SELF_CERTIFY_PROVIDER')
        return self


class NightCommit(StrictModel):
    run_id: Id
    shop_id: Id
    day: Positive
    snapshot_hash: Hash
    publication_hash: Hash
    knowledge: KnowledgeCommit
    summary: NightSummary
    versions: list[SkillVersion] = Field(default_factory=list)
    rejections: list[PatchRejection] = Field(default_factory=list)
    source: Source

    @model_validator(mode='after')
    def summary_matches(self):
        if self.summary.day != self.day or self.summary.rejected_ops != len(self.rejections):
            raise ValueError('SUMMARY_MISMATCH')
        if self.knowledge.accepted_lesson_ops != self.summary.lesson_ops or self.knowledge.rejected_ops != len(self.rejections):
            raise ValueError('COMMIT_SUMMARY_MISMATCH')
        return self


class ClaimReflectionRequest(StrictModel):
    run_id: Id
    day: Positive
    snapshot_hash: Hash
    owner_token: Id


class CommitNightRequest(StrictModel):
    publication: NightPublication
    expected_revision: Nonnegative
    expected_cursor: Nonnegative


class ReserveCallRequest(StrictModel):
    run_id: Id
    call_id: Id
    limit: Nonnegative


class CallReservation(StrictModel):
    granted: bool
    reason: Literal['granted', 'already_reserved', 'exhausted']
    used: Nonnegative
    remaining: Nonnegative

    @model_validator(mode='after')
    def reason_matches(self):
        if self.granted != (self.reason == 'granted'):
            raise ValueError('RESERVATION_REASON_MISMATCH')
        return self


class KnowledgeRecord(StrictModel):
    run_id: Id
    compartment: Literal['history', 'preferences', 'calibration', 'lessons']
    scope: Id
    record_key: Id
    value: PublicHistory | Preference | CalibrationRecord | PublicLesson

    @model_validator(mode='after')
    def record(self):
        types = {'history': PublicHistory, 'preferences': Preference,
                 'calibration': CalibrationRecord, 'lessons': PublicLesson}
        if not isinstance(self.value, types[self.compartment]):
            raise ValueError('RECORD_TYPE_MISMATCH')
        if self.compartment == 'history':
            expected = self.value.shop_id, self.value.negotiation_id
        elif self.compartment == 'preferences':
            expected = self.value.shop_id, self.value.pref_id
        elif self.compartment == 'calibration':
            expected = self.value.category, self.value.category
        else:
            expected = self.value.scope, self.value.lesson_id
        if (self.scope, self.record_key) != expected:
            raise ValueError('RECORD_KEY_MISMATCH')
        return self


class KnowledgeMeta(StrictModel):
    run_id: Id
    revision: Nonnegative
    cursor: Nonnegative
    llm_limit: Nonnegative | None


class LegacyCommitReceipt(StrictModel):
    run_id: Id
    receipt_key: Id
    payload_hash: Hash
    result: MemoryCommit


class LLMCallReservationRecord(StrictModel):
    run_id: Id
    call_id: Id
    reserved_at: Annotated[str, StringConstraints(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$')]




Role = Literal["platform", "shop", "referee", "content", "learning"]

class ReplayBinding(StrictModel):
    kind: Literal['run', 'negotiation', 'card', 'prediction', 'fact', 'lesson', 'preference', 'turn', 'tool_call']
    token: Id
    value: Id


class ReplayEntry(StrictModel):
    request_hash: Hash
    role: Role
    shop_id: Id
    visibility: Literal['public', 'shop_private']
    model_id: Id
    response_json: str
    bindings: list[ReplayBinding] = Field(default_factory=list)

    @model_validator(mode='after')
    def cached_reply(self):
        if self.role == 'shop' and self.visibility != 'shop_private':
            raise ValueError('SHOP_REPLY_IS_PRIVATE')
        json.loads(self.response_json)
        return self


class ReplayManifest(StrictModel):
    schema_version: Literal['self-improve.v1']
    source_run_id: Id
    shop_id: Id
    config_hash: Hash
    entries: list[ReplayEntry] = Field(default_factory=list)

    @model_validator(mode='after')
    def replay_scope(self):
        if any(e.shop_id != self.shop_id for e in self.entries):
            raise ValueError('REPLAY_SCOPE_MISMATCH')
        return self




from app.domain.models.metrics import DayMetrics

class RunResult(StrictModel):
    run_id: Id
    shop_id: Id
    seed: int
    days: Annotated[int, Field(strict=True, ge=1, le=7)]
    memory_enabled: bool
    mode: Literal['live', 'replay', 'offline']
    daily_metrics: list[DayMetrics] = Field(default_factory=list)
    forecast_errors: list[float] = Field(default_factory=list)
    negotiation_rounds: list[Nonnegative] = Field(default_factory=list)
    budget_slots_used: Nonnegative
    source_counts: dict[str, Nonnegative] = Field(default_factory=dict)
    skill_versions: dict[str, Nonnegative] = Field(default_factory=dict)
    valid: bool
    invalid_reasons: list[str] = Field(default_factory=list)
    report_path: str | None = None
