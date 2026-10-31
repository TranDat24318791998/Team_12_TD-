"""Compile policy data and apply it to a proposal seed."""

from __future__ import annotations

import hashlib
from app.domain.models.skills import (PAIRS, CompiledSkill, EvidenceFact, PolicyStep,
                                      PolicyUse, SeedResult, SkillBundle, canonical)
from app.domain.models.packages import Package


def canonical_bytes(value: object) -> bytes:
    return canonical(value)


def compile_skill(skill_id, base_text: str, steps: list[PolicyStep]) -> CompiledSkill:
    if not base_text.strip():
        raise ValueError('EMPTY_BASE_SKILL')
    return CompiledSkill(skill_id=skill_id, base_hash=hashlib.sha256(base_text.encode('utf-8')).hexdigest(),
                         learned_steps=sorted((s.model_copy(deep=True) for s in steps),
                                              key=lambda s: PAIRS[s.action][1]))


def dump_skill(skill: CompiledSkill) -> bytes:
    return canonical_bytes(skill.model_dump(mode='json'))


def load_skill(blob: bytes, *, expected_hash: str) -> CompiledSkill:
    if hashlib.sha256(blob).hexdigest() != expected_hash:
        raise ValueError('ARTIFACT_HASH_MISMATCH')
    parsed = CompiledSkill.model_validate_json(blob)
    if dump_skill(parsed) != blob:
        raise ValueError('NON_CANONICAL_ARTIFACT')
    return parsed


def apply_skill(base_seed: Package, bundle: SkillBundle, facts: list[EvidenceFact], *,
                run_id: str, shop_id: str, category: str, day: int, kind: str,
                memory_enabled: bool) -> SeedResult:
    if (bundle.run_id, bundle.shop_id, bundle.category) != (run_id, shop_id, category):
        raise ValueError('SKILL_SCOPE_MISMATCH')
    if kind not in ('propose', 'renew') or bundle.skill.skill_id != ('platform_offer' if kind == 'propose' else 'platform_renew'):
        raise ValueError('SKILL_KIND_MISMATCH')
    if hashlib.sha256(dump_skill(bundle.skill)).hexdigest() != bundle.artifact_hash:
        raise ValueError('ARTIFACT_HASH_MISMATCH')
    package = base_seed.model_copy(deep=True)
    if not memory_enabled or day < bundle.effective_from_day:
        return SeedResult(package=package)
    usable = [f for f in facts if (f.run_id, f.shop_id, f.category) == (run_id, shop_id, category) and f.day <= day]
    def latest(items):
        return max(items, key=lambda f: (f.package_applied_seq, f.support_seq, f.fact_id), default=None)
    approved = latest(f for f in usable if f.kind == 'approved_package')
    edited = latest(f for f in usable if f.kind == 'seller_approved_voucher_edit')
    paused = latest(f for f in usable if f.kind == 'ads_auto_paused' and approved
                    and f.package_applied_seq == approved.package_applied_seq and f.card_id == approved.card_id)
    by_kind = {'approved_package': approved, 'seller_approved_voucher_edit': edited, 'ads_auto_paused': paused}
    uses = []
    for step in bundle.skill.learned_steps:
        fact = by_kind[step.trigger]
        if fact is None:
            continue
        values = package.model_dump()
        if step.action == 'seed_last_approved':
            values = fact.package.model_dump()
        elif step.action == 'seed_approved_voucher':
            values['voucher_pct'] = fact.package.voucher_pct
        else:
            values.update(ads_daily_budget=0, stop_roas_below=None)
        package = Package.model_validate(values)
        uses.append(PolicyUse(policy_id=step.policy_id, fact_id=fact.fact_id))
    return SeedResult(package=package, uses=uses)


def evaluate_candidate(bundle, *, base_text, facts):
    """Check an artifact and its actual transformation before publication."""
    from copy import deepcopy
    before = (bundle.model_dump(mode='json'), [f.model_dump(mode='json') for f in facts])
    try:
        SkillBundle.model_validate_json(bundle.model_dump_json())
        if hashlib.sha256(base_text.encode('utf-8')).hexdigest() != bundle.skill.base_hash:
            raise ValueError('base changed')
        blob = dump_skill(bundle.skill)
        if load_skill(blob, expected_hash=bundle.artifact_hash) != bundle.skill:
            raise ValueError('round trip failed')
        relevant = [f for f in facts if (f.run_id,f.shop_id,f.category) == (bundle.run_id,bundle.shop_id,bundle.category)]
        by_id = {f.fact_id:f for f in relevant}
        if any(not all(fid in by_id and by_id[fid].kind == s.trigger for fid in s.evidence_fact_ids)
               for s in bundle.skill.learned_steps):
            raise ValueError('source missing')
        seed = Package(content_refresh=True,ads_daily_budget=70000,voucher_pct=10,
                       stop_roas_below=4.0,stop_after_days=2,duration_days=3)
        kind = 'propose' if bundle.skill.skill_id == 'platform_offer' else 'renew'
        args = dict(run_id=bundle.run_id,shop_id=bundle.shop_id,category=bundle.category,kind=kind)
        off = apply_skill(seed,bundle,relevant,day=bundle.effective_from_day,memory_enabled=False,**args)
        if off.package != seed or off.uses:
            raise ValueError('memory off')
        prior = apply_skill(seed,bundle,relevant,day=bundle.effective_from_day-1,memory_enabled=True,**args)
        if prior.package != seed or prior.uses:
            raise ValueError('future policy')
        actual = apply_skill(seed,bundle,relevant,day=bundle.effective_from_day,memory_enabled=True,**args)
        selected = {f.kind:None for f in relevant}
        for f in relevant:
            old = selected[f.kind]
            if old is None or (f.package_applied_seq,f.support_seq,f.fact_id) > (old.package_applied_seq,old.support_seq,old.fact_id):
                selected[f.kind] = f
        approved = selected.get('approved_package')
        pauses = [f for f in relevant if f.kind == 'ads_auto_paused' and approved and
                  f.card_id == approved.card_id and f.package_applied_seq == approved.package_applied_seq]
        selected['ads_auto_paused'] = max(pauses,key=lambda f:(f.package_applied_seq,f.support_seq,f.fact_id),default=None)
        expected = seed.model_dump(); used = []
        for step in bundle.skill.learned_steps:
            fact = selected.get(step.trigger)
            if fact is None:
                continue
            if step.action == 'seed_last_approved': expected = fact.package.model_dump()
            elif step.action == 'seed_approved_voucher': expected['voucher_pct'] = fact.package.voucher_pct
            else: expected.update(ads_daily_budget=0,stop_roas_below=None)
            used.append((step.policy_id,fact.fact_id))
        if actual.package.model_dump() != expected or [(u.policy_id,u.fact_id) for u in actual.uses] != used:
            raise ValueError('policy mismatch')
        if before != (bundle.model_dump(mode='json'), [f.model_dump(mode='json') for f in facts]):
            raise ValueError('input mutated')
    except Exception as exc:
        raise ValueError('CANDIDATE_EVAL_FAILED') from exc
    return ['schema_allowlist','immutable_base','artifact_roundtrip','scope_and_effective_day',
            'memory_off','policy_order','source_values','input_immutability']


def prepare_platform_context(session, shop_id, day, kind, negotiation_id):
    from app.domain.models.tools import PinnedPlatformContext
    from app.domain.models.skills import PlatformSkillView
    from app.domain.policies import DEFAULT_PACKAGE
    from app.memory.base import compose_base_text
    from app.memory.evidence import build_skill_facts
    from app.negotiation.prompts import PLATFORM_SYSTEM
    skill_id = 'platform_offer' if kind == 'propose' else 'platform_renew'
    with session.lock:
        category = session.states[shop_id].public.category
        base_text = compose_base_text(skill_id, PLATFORM_SYSTEM)
        view = session.memory.platform_view(shop_id, category, invocation_id=negotiation_id)
        events = session.log.since(session.run_id, 0)
        through = session.log.last_seq(session.run_id) if hasattr(session.log,'last_seq') else max((e.seq for e in events),default=0)
        bundle = session.memory.skill_bundle(shop_id,skill_id,day,base_text=base_text)
        history = next((h for h in view.history if h.approved_package),None)
        base_seed = history.approved_package if session.memory.enabled and history else Package.model_validate(DEFAULT_PACKAGE)
        facts = build_skill_facts(events,run_id=session.run_id,shop_id=shop_id,category=category,day=day,through_seq=through) if session.memory.enabled else []
        seed = apply_skill(base_seed,bundle,facts,run_id=session.run_id,shop_id=shop_id,category=category,
                           day=day,kind=kind,memory_enabled=session.memory.enabled)
        view.skill = PlatformSkillView(bundle=bundle,seed=seed)
        return PinnedPlatformContext(run_id=session.run_id,shop_id=shop_id,category=category,
            negotiation_id=negotiation_id,day=day,kind=kind,through_seq=through,memory=view,base_text=base_text)
