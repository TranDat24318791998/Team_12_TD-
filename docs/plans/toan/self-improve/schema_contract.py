"""Reference schemas for the handoff, not an application runtime module.

Run from repo root with .venv/bin/python docs/plans/toan/self-improve/schema_contract.py.
Exports a self-contained JSON Schema and fixture envelopes; never imports Settings.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Annotated, Literal, Union

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from pydantic import Field, StringConstraints, TypeAdapter, create_model, model_validator
from app.domain.models.shops import StrictModel
from app.domain.models.packages import Package
from app.domain.models.learning import (
    KnowledgeCommit, LearningEvidence as ExistingLearningEvidence, LessonOp,
    MemoryCommit, MemoryUpdateBatch, NightSummary,
    PlatformMemoryView as ExistingPlatformMemoryView, PublicLesson, StoreWrite,
    PublicHistory, Preference, CalibrationRecord,
)
from app.domain.models.metrics import DayMetrics

Id = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Hash = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
Positive = Annotated[int, Field(strict=True, ge=1)]
Nonnegative = Annotated[int, Field(strict=True, ge=0)]
SkillId = Literal['platform_offer', 'platform_renew', 'shop_negotiate', 'content_brief']
EvolvableSkillId = Literal['platform_offer', 'platform_renew']
FactKind = Literal['approved_package', 'seller_approved_voucher_edit', 'ads_auto_paused']
PolicyAction = Literal['seed_last_approved', 'seed_approved_voucher', 'disable_ads_on_renewal']
Source = Literal['live', 'replay', 'offline', 'fixture', 'skipped']
Role = Literal['platform', 'shop', 'referee', 'content', 'learning']
RejectionCode = Literal[
    'INVALID_PAIR', 'SCOPE_DENIED', 'STALE_SKILL', 'UNKNOWN_FACT',
    'WRONG_FACT_KIND', 'NO_FRESH_EVIDENCE', 'EVIDENCE_MISMATCH',
    'DUPLICATE_EVIDENCE', 'DUPLICATE_POLICY', 'MISSING_POLICY',
    'STALE_LESSON', 'INVALID_LESSON', 'PRIVATE_VALIDATION_UNAVAILABLE',
    'CANDIDATE_EVAL_FAILED',
]
PAIRS = {
    'seed_last_approved': ('approved_package', 1),
    'seed_approved_voucher': ('seller_approved_voucher_edit', 2),
    'disable_ads_on_renewal': ('ads_auto_paused', 3),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def check_pair(target, trigger, action):
    if PAIRS[action][0] != trigger or (action == 'disable_ads_on_renewal' and target != 'platform_renew'):
        raise ValueError('INVALID_PAIR')


class EvidenceFact(StrictModel):
    fact_id: Hash
    run_id: Id
    shop_id: Id
    category: Id
    day: Positive
    kind: FactKind
    negotiation_id: Id
    card_id: Id
    package_applied_seq: Positive
    support_seq: Positive
    source_seqs: list[Positive] = Field(min_length=1, json_schema_extra={'uniqueItems': True})
    package: Package

    @model_validator(mode='after')
    def sources(self):
        if self.source_seqs != sorted(set(self.source_seqs)):
            raise ValueError('source_seqs must be sorted and unique')
        if self.package_applied_seq not in self.source_seqs or self.support_seq != max(self.source_seqs):
            raise ValueError('source_seqs must contain apply and end at support')
        expected = digest([self.run_id, self.shop_id, self.kind, self.card_id,
                           self.negotiation_id, self.package_applied_seq, self.support_seq])
        if self.fact_id != expected:
            raise ValueError('FACT_ID_MISMATCH')
        return self


class PolicyStep(StrictModel):
    policy_id: Id
    lesson_id: Id
    target_skill: EvolvableSkillId
    trigger: FactKind
    action: PolicyAction
    evidence_fact_ids: list[Hash] = Field(min_length=1, json_schema_extra={'uniqueItems': True})

    @model_validator(mode='after')
    def policy(self):
        check_pair(self.target_skill, self.trigger, self.action)
        if self.policy_id != f'{self.target_skill}:{self.action}':
            raise ValueError('POLICY_ID_MISMATCH')
        if len(set(self.evidence_fact_ids)) != len(self.evidence_fact_ids):
            raise ValueError('DUPLICATE_EVIDENCE')
        return self


class CompiledSkill(StrictModel):
    skill_id: SkillId
    base_hash: Hash
    learned_steps: list[PolicyStep] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def steps(self):
        if self.skill_id not in ('platform_offer', 'platform_renew') and self.learned_steps:
            raise ValueError('BASE_ONLY_SKILL')
        if any(s.target_skill != self.skill_id for s in self.learned_steps):
            raise ValueError('SKILL_KIND_MISMATCH')
        order = [PAIRS[s.action][1] for s in self.learned_steps]
        if order != sorted(set(order)):
            raise ValueError('steps must be ordered and unique')
        return self


class SkillBundle(StrictModel):
    run_id: Id
    shop_id: Id
    category: Id
    version: Nonnegative
    effective_from_day: Positive
    skill: CompiledSkill
    artifact_hash: Hash

    @model_validator(mode='after')
    def artifact(self):
        if self.version == 0 and self.skill.learned_steps:
            raise ValueError('BASE_VERSION_HAS_STEPS')
        if self.artifact_hash != digest(self.skill.model_dump(mode='json')):
            raise ValueError('ARTIFACT_HASH_MISMATCH')
        return self


class PolicyUse(StrictModel):
    policy_id: Id
    fact_id: Hash


class SeedResult(StrictModel):
    package: Package
    uses: list[PolicyUse] = Field(default_factory=list)


class PlatformSkillView(StrictModel):
    bundle: SkillBundle
    seed: SeedResult


class PlatformMemoryView(ExistingPlatformMemoryView):
    skill: PlatformSkillView | None = None


class LearningEvidence(ExistingLearningEvidence):
    skill_facts: list[EvidenceFact] = Field(default_factory=list)
    skill_bundles: list[SkillBundle] = Field(default_factory=list, max_length=2)

    @model_validator(mode='after')
    def bundle_targets(self):
        ids = [b.skill.skill_id for b in self.skill_bundles]
        if len(set(ids)) != len(ids) or any(i not in ('platform_offer', 'platform_renew') for i in ids):
            raise ValueError('LEARNING_BUNDLE_TARGETS')
        return self


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


class PinnedPlatformContext(StrictModel):
    run_id: Id
    shop_id: Id
    category: Id
    negotiation_id: Id
    day: Positive
    kind: Literal['propose', 'renew']
    through_seq: Nonnegative
    memory: PlatformMemoryView
    base_text: str

    @model_validator(mode='after')
    def pinned(self):
        if self.memory.skill is None:
            raise ValueError('PINNED_SKILL_REQUIRED')
        bundle = self.memory.skill.bundle
        if (bundle.run_id, bundle.shop_id, bundle.category) != (self.run_id, self.shop_id, self.category):
            raise ValueError('SKILL_SCOPE_MISMATCH')
        expected = 'platform_offer' if self.kind == 'propose' else 'platform_renew'
        if bundle.skill.skill_id != expected or bundle.effective_from_day > self.day:
            raise ValueError('PINNED_SKILL_NOT_EFFECTIVE')
        if hashlib.sha256(self.base_text.encode()).hexdigest() != bundle.skill.base_hash:
            raise ValueError('BASE_HASH_MISMATCH')
        return self


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


MODELS = [EvidenceFact, PolicyStep, CompiledSkill, SkillBundle, PolicyUse, SeedResult,
          PlatformSkillView, PlatformMemoryView, LearningEvidence, SkillPatchProposal,
          NightReflectionOutput, SkillVersion, PatchRejection, NightSnapshot,
          ReflectionReceipt, StagedLearning, NightPublication, NightCommit,
          ClaimReflectionRequest, CommitNightRequest, ReserveCallRequest, CallReservation,
          KnowledgeRecord, KnowledgeMeta, LegacyCommitReceipt, LLMCallReservationRecord,
          PinnedPlatformContext, ReplayBinding, ReplayEntry, ReplayManifest, RunResult]


def examples():
    package = Package(content_refresh=True, ads_daily_budget=50000, voucher_pct=5,
                      stop_roas_below=5.5, stop_after_days=2, duration_days=3)
    facts = []
    for kind, seqs, day in [('approved_package', [10, 11], 1),
                            ('seller_approved_voucher_edit', [6, 8, 10, 11], 1),
                            ('ads_auto_paused', [10, 11, 20], 3)]:
        fid = digest(['r1', 'E', kind, 'c1', 'n1', 11, max(seqs)])
        facts.append(EvidenceFact(fact_id=fid, run_id='r1', shop_id='E', category='quat_mini',
                                 day=day, kind=kind, negotiation_id='n1', card_id='c1',
                                 package_applied_seq=11, support_seq=max(seqs), source_seqs=seqs, package=package))
    texts = [
        'Khi gia hạn, dùng gói đã duyệt gần nhất làm điểm khởi đầu.',
        'Khi gia hạn, dùng voucher được người bán sửa và duyệt gần nhất.',
        'Khi gia hạn, bỏ quảng cáo nếu gói gần nhất đã bị tự động tạm dừng quảng cáo.',
    ]
    ops = [LessonOp(op='ADD', lesson_id=None, text_vi=t, scope='quat_mini', evidence=['n1']) for t in texts]
    lesson_ids = [hashlib.sha256(f'r1:quat_mini:{" ".join(t.casefold().split())}'.encode()).hexdigest()[:16] for t in texts]
    steps, proposals = [], []
    for (action, (trigger, _)), fact, op, lid in zip(PAIRS.items(), facts, ops, lesson_ids):
        steps.append(PolicyStep(policy_id=f'platform_renew:{action}', lesson_id=lid,
                                target_skill='platform_renew', trigger=trigger, action=action,
                                evidence_fact_ids=[fact.fact_id]))
        proposals.append(SkillPatchProposal(lesson_op=op, target_skill='platform_renew',
                                           trigger=trigger, action=action, evidence_fact_ids=[fact.fact_id],
                                           base_skill_version=0))
    bases = {'platform_offer': 'Platform offer fixture v1', 'platform_renew': 'Platform renew fixture v1'}
    compiled = CompiledSkill(skill_id='platform_renew', base_hash=hashlib.sha256(bases['platform_renew'].encode()).hexdigest(), learned_steps=steps)
    bundle = SkillBundle(run_id='r1', shop_id='E', category='quat_mini', version=1,
                         effective_from_day=4, skill=compiled, artifact_hash=digest(compiled.model_dump(mode='json')))
    base_bundles = []
    for skill_id, text in bases.items():
        base = CompiledSkill(skill_id=skill_id, base_hash=hashlib.sha256(text.encode()).hexdigest())
        base_bundles.append(SkillBundle(run_id='r1', shop_id='E', category='quat_mini', version=0,
                                       effective_from_day=1, skill=base, artifact_hash=digest(base.model_dump(mode='json'))))
    evidence = LearningEvidence(day=3, from_seq=1, through_seq=20, events=[], existing_lessons=[],
                                valid_negotiation_ids=['n1'], knowledge_revision=0,
                                skill_facts=facts, skill_bundles=base_bundles)
    derived = MemoryUpdateBatch(day=3, through_seq=20, history=[], preferences=[], calibration=[],
                                lesson_ops=[], valid_negotiation_ids=['n1'])
    calibration = {'factor': 1.0, 'points': 0, 'mape_today': None}
    snapshot_fields = dict(run_id='r1', shop_id='E', category='quat_mini', day=3,
                           through_seq=20, evidence=evidence.model_dump(mode='json'),
                           derived=derived.model_dump(mode='json'), calibration_summary=calibration,
                           prior_versions=[], base_texts=bases)
    snapshot = NightSnapshot(**snapshot_fields, expected_revision=0, expected_cursor=0,
                             snapshot_hash=digest(snapshot_fields))
    output = NightReflectionOutput(proposals=proposals)
    reflection = ReflectionReceipt(run_id='r1', shop_id='E', day=3, snapshot_hash=snapshot.snapshot_hash,
                                   owner_token='worker-fixture-1', status='completed', output=output,
                                   source='fixture', error_code=None)
    lessons = [PublicLesson(lesson_id=lid, scope='quat_mini', text_vi=op.text_vi, score=2,
                            evidence=['n1'], created_day=3, updated_day=3, version=1)
               for lid, op in zip(lesson_ids, ops)]
    writes = [StoreWrite(namespace=('r1', 'lessons', 'quat_mini'), key=x.lesson_id, value=x) for x in lessons]
    version = SkillVersion(bundle=bundle, parent_version=0, created_day=3, source_through_seq=20,
                           artifact_json=canonical(compiled.model_dump(mode='json')).decode(),
                           eval_level='deterministic', eval_checks=['schema_allowlist', 'immutable_base',
                               'artifact_roundtrip', 'scope_and_effective_day', 'memory_off',
                               'policy_order', 'source_values', 'input_immutability'])
    summary = NightSummary(day=3, history_updates=[], pref_candidates=[], calibration=calibration,
                           lesson_ops=ops, rejected_ops=0)
    publication = NightPublication(run_id='r1', shop_id='E', day=3, snapshot_hash=snapshot.snapshot_hash,
                                   through_seq=20, writes=writes, versions=[version], summary=summary,
                                   rejections=[], source='fixture')
    knowledge = KnowledgeCommit(store=MemoryCommit(revision=1, cursor=20, applied_ids=lesson_ids, duplicate=False),
                                 accepted_lesson_ops=ops, rejected_ops=0)
    commit = NightCommit(run_id='r1', shop_id='E', day=3, snapshot_hash=snapshot.snapshot_hash,
                         publication_hash=digest(publication.model_dump(mode='json')), knowledge=knowledge,
                         summary=summary, versions=[version], rejections=[], source='fixture')
    seed = SeedResult(package=Package.model_validate({**package.model_dump(), 'ads_daily_budget': 0, 'stop_roas_below': None}),
                       uses=[PolicyUse(policy_id=s.policy_id, fact_id=f.fact_id) for s, f in zip(steps, facts)])
    view = PlatformSkillView(bundle=bundle, seed=seed)
    memory = PlatformMemoryView(history=[], calibration=None, lessons=lessons, knowledge_revision=1, skill=view)
    binding = ReplayBinding(kind='run', token='RUN', value='r1')
    replay = ReplayEntry(request_hash=digest(['fixture-request']), role='platform', shop_id='E',
                         visibility='public', model_id='fixture-model', response_json=json.dumps({
                             'content': '', 'tool_calls': [{'name': 'read_memory', 'args': {},
                                 'id': 'call-fixture-1', 'type': 'tool_call'}],
                             'invalid_tool_calls': []}), bindings=[binding])
    return [*facts, *steps, compiled, bundle, *seed.uses, seed, view, memory, evidence, *proposals, output,
            version, PatchRejection(origin='proposal', index=0, code='UNKNOWN_FACT'), snapshot,
            reflection, StagedLearning(writes=writes, lessons=lessons, steps=steps, accepted_ops=ops),
            publication, commit,
            ClaimReflectionRequest(run_id='r1', day=3, snapshot_hash=snapshot.snapshot_hash, owner_token='worker-fixture-1'),
            CommitNightRequest(publication=publication, expected_revision=0, expected_cursor=0),
            ReserveCallRequest(run_id='r1', call_id='r1:learning:3:0', limit=64),
            CallReservation(granted=True, reason='granted', used=1, remaining=63),
            KnowledgeRecord(run_id='r1', compartment='lessons', scope='quat_mini',
                            record_key=lessons[0].lesson_id, value=lessons[0]),
            KnowledgeMeta(run_id='r1', revision=1, cursor=20, llm_limit=64),
            LegacyCommitReceipt(run_id='r1', receipt_key='fixture-legacy-1',
                                payload_hash=digest({'fixture': 'legacy'}), result=knowledge.store),
            LLMCallReservationRecord(run_id='r1', call_id='r1:learning:3:0',
                                     reserved_at='2026-10-31T00:00:00Z'),
            PinnedPlatformContext(run_id='r1', shop_id='E', category='quat_mini', negotiation_id='n2', day=4,
                                   kind='renew', through_seq=20, memory=memory, base_text=bases['platform_renew']),
            binding, replay, ReplayManifest(schema_version='self-improve.v1', source_run_id='r1', shop_id='E',
                                            config_hash=digest({'model': 'fixture-model'}), entries=[replay]),
            RunResult(run_id='r1', shop_id='E', seed=42, days=7, memory_enabled=True, mode='offline',
                       budget_slots_used=0, valid=False, invalid_reasons=['EXAMPLE_ONLY'])]


def build_schema():
    wrappers = [create_model(f'{model.__name__}Envelope', __base__=StrictModel,
                             schema_version=(Literal['self-improve.v1'], ...),
                             model=(Literal[model.__name__], ...), source=(Source, ...), payload=(model, ...))
                for model in MODELS]
    envelope = TypeAdapter(Annotated[Union[tuple(wrappers)], Field(discriminator='model')])
    schema = envelope.json_schema()
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$id'] = 'urn:growth-agents:self-improve:v1'
    schema['title'] = 'Growth Agents self improve contract v1'
    combos = []
    for target in ('platform_offer', 'platform_renew'):
        for action, (trigger, _) in PAIRS.items():
            if target == 'platform_offer' and action == 'disable_ads_on_renewal':
                continue
            combos.append({'properties': {'target_skill': {'const': target},
                                           'trigger': {'const': trigger}, 'action': {'const': action}}})
    for name in ('PolicyStep', 'SkillPatchProposal'):
        schema['$defs'][name].setdefault('allOf', []).append({'oneOf': combos})
    schema['$defs']['KnowledgeRecord'].setdefault('allOf', []).append({'oneOf': [
        {'properties': {'compartment': {'const': compartment}, 'value': {'$ref': f'#/$defs/{name}'}}}
        for compartment, name in [('history', 'PublicHistory'), ('preferences', 'Preference'),
                                  ('calibration', 'CalibrationRecord'), ('lessons', 'PublicLesson')]]})
    schema['$defs']['ReflectionReceipt'].setdefault('allOf', []).append({
        'if': {'properties': {'status': {'const': 'completed'}}},
        'then': {'properties': {'output': {'$ref': '#/$defs/NightReflectionOutput'}}},
        'else': {'properties': {'output': {'type': 'null'}}}})
    schema['$defs']['ReplayEntry'].setdefault('allOf', []).append({
        'if': {'properties': {'role': {'const': 'shop'}}},
        'then': {'properties': {'visibility': {'const': 'shop_private'}}}})
    schema['$defs']['CallReservation'].setdefault('allOf', []).append({
        'if': {'properties': {'reason': {'const': 'granted'}}},
        'then': {'properties': {'granted': {'const': True}}},
        'else': {'properties': {'granted': {'const': False}}}})
    schema['$defs']['NightReflectionOutput'].setdefault('allOf', []).append({
        'anyOf': [{'properties': {'ops': {'maxItems': n}, 'proposals': {'maxItems': 3-n}}} for n in range(4)]})
    schema['$defs']['CompiledSkill'].setdefault('allOf', []).extend([
        {'if': {'properties': {'skill_id': {'const': target}}},
         'then': {'properties': {'learned_steps': {'items': {'properties': {'target_skill': {'const': target}}}}}}}
        for target in ('platform_offer', 'platform_renew')])
    schema['$defs']['CompiledSkill']['allOf'].append({
        'if': {'properties': {'skill_id': {'enum': ['shop_negotiate', 'content_brief']}}},
        'then': {'properties': {'learned_steps': {'maxItems': 0}}}})
    schema['$defs']['SkillBundle'].setdefault('allOf', []).append({
        'if': {'properties': {'version': {'const': 0}}},
        'then': {'properties': {'skill': {'properties': {'learned_steps': {'maxItems': 0}}}}}})
    schema['$defs']['SkillVersion'].setdefault('allOf', []).append({
        'properties': {'bundle': {'properties': {'skill': {'properties': {
            'skill_id': {'enum': ['platform_offer', 'platform_renew']}}}}}}})
    return envelope, schema


def main():
    adapter, schema = build_schema()
    instances = examples()
    envelopes = [{'schema_version': 'self-improve.v1', 'model': type(x).__name__,
                   'source': 'fixture', 'payload': x.model_dump(mode='json')} for x in instances]
    for item in envelopes:
        adapter.validate_json(json.dumps(item, ensure_ascii=False))
    negatives = []
    step = next(x for x in envelopes if x['model'] == 'PolicyStep')
    for update in ({'action': 'disable_ads_on_renewal', 'target_skill': 'platform_offer'},
                   {'approved': True}, {'ads_daily_budget': 0}):
        negatives.append({**step, 'payload': {**step['payload'], **update}})
    out = next(x for x in envelopes if x['model'] == 'NightReflectionOutput')
    negatives.append({**out, 'payload': {**out['payload'], 'ops': [out['payload']['proposals'][0]['lesson_op']]}})
    for name, update in [('ReflectionReceipt', {'status': 'unknown'}),
                         ('ReplayEntry', {'role': 'shop', 'visibility': 'public'}),
                         ('CallReservation', {'granted': False}),
                         ('KnowledgeRecord', {'compartment': 'history'})]:
        original = next(x for x in envelopes if x['model'] == name)
        negatives.append({**original, 'payload': {**original['payload'], **update}})
    for item in negatives:
        try:
            adapter.validate_json(json.dumps(item, ensure_ascii=False))
        except ValueError:
            pass
        else:
            raise AssertionError('Negative fixture unexpectedly accepted')
    cross_field_negatives = []
    for name, update in [
        ('EvidenceFact', {'fact_id': '0' * 64}),
        ('PolicyStep', {'policy_id': 'platform_renew:wrong'}),
        ('SkillBundle', {'artifact_hash': '0' * 64}),
        ('SkillVersion', {'parent_version': 5}),
        ('NightSnapshot', {'snapshot_hash': '0' * 64}),
        ('NightSnapshot', {'expected_cursor': 21}),
        ('KnowledgeRecord', {'record_key': 'wrong-key'}),
        ('NightCommit', {'day': 2}),
        ('PinnedPlatformContext', {'day': 3}),
        ('ReplayManifest', {'shop_id': 'D'}),
    ]:
        original = next(x for x in envelopes if x['model'] == name)
        cross_field_negatives.append({**original, 'payload': {**original['payload'], **update}})
    for item in cross_field_negatives:
        try:
            adapter.validate_json(json.dumps(item, ensure_ascii=False))
        except ValueError:
            pass
        else:
            raise AssertionError('Cross-field negative fixture unexpectedly accepted')
    json_schema_checked = False
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        pass
    else:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for item in envelopes:
            validator.validate(item)
        for item in negatives:
            if validator.is_valid(item):
                raise AssertionError('JSON Schema accepted a negative fixture')
        json_schema_checked = True
    output = ROOT / 'contracts' / 'self_improve'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'v1.schema.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2) + '\n')
    (output / 'examples.json').write_text(json.dumps(envelopes, ensure_ascii=False, indent=2) + '\n')
    (output / 'invalid_examples.json').write_text(json.dumps(negatives, ensure_ascii=False, indent=2) + '\n')
    (output / 'invalid_cross_field_examples.json').write_text(json.dumps(cross_field_negatives, ensure_ascii=False, indent=2) + '\n')
    report = {'schema_version': 'self-improve.v1', 'model_count': len(MODELS),
              'positive_examples': len(envelopes), 'negative_examples_rejected': len(negatives),
              'pydantic_cross_field_examples_rejected': len(cross_field_negatives),
              'pydantic_validation': True, 'json_schema_validation': json_schema_checked,
              'schema_sha256': hashlib.sha256((output / 'v1.schema.json').read_bytes()).hexdigest()}
    (output / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
