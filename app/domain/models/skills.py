"""Typed, deterministic policy artifacts and their evidence."""

from __future__ import annotations
import hashlib
import json
from typing import Annotated, Literal
from pydantic import Field, StringConstraints, model_validator
from app.domain.models.shops import StrictModel
from app.domain.models.packages import Package

Id = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Hash = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
Positive = Annotated[int, Field(strict=True, ge=1)]
Nonnegative = Annotated[int, Field(strict=True, ge=0)]
SkillId = Literal['platform_offer', 'platform_renew', 'shop_negotiate', 'content_brief']
EvolvableSkillId = Literal['platform_offer', 'platform_renew']
FactKind = Literal['approved_package', 'seller_approved_voucher_edit', 'ads_auto_paused']
PolicyAction = Literal['seed_last_approved', 'seed_approved_voucher', 'disable_ads_on_renewal']
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


