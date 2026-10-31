"""Pure staging of model suggestions into bounded, evidence-backed writes."""

from hashlib import sha256
from app.domain.models.learning import PatchRejection, PublicLesson, StagedLearning, StoreWrite
from app.domain.models.skills import PolicyStep, PAIRS
from app.domain.policies import LESSON_CAP_PER_SCOPE

TEMPLATES = {
    ('platform_offer', 'seed_last_approved'): 'Khi tạo đề xuất mới, dùng gói đã duyệt gần nhất làm điểm khởi đầu.',
    ('platform_renew', 'seed_last_approved'): 'Khi gia hạn, dùng gói đã duyệt gần nhất làm điểm khởi đầu.',
    ('platform_offer', 'seed_approved_voucher'): 'Khi tạo đề xuất mới, dùng voucher được người bán sửa và duyệt gần nhất.',
    ('platform_renew', 'seed_approved_voucher'): 'Khi gia hạn, dùng voucher được người bán sửa và duyệt gần nhất.',
    ('platform_renew', 'disable_ads_on_renewal'): 'Khi gia hạn, bỏ quảng cáo nếu gói gần nhất đã bị tự động tạm dừng quảng cáo.',
}


def stage_learning(snapshot, reflection, *, current_lessons, current_versions, current_records, text_rejections=()):
    lessons = {(x.scope,x.lesson_id): x.model_copy(deep=True) for x in current_lessons}
    old_lessons = {(x.scope,x.lesson_id): x for x in snapshot.evidence.existing_lessons}
    versions = {v.bundle.skill.skill_id:v for v in current_versions}
    steps = {s.policy_id:s.model_copy(deep=True) for v in current_versions for s in v.bundle.skill.learned_steps}
    facts = {f.fact_id:f for f in snapshot.evidence.skill_facts}
    rejections = list(text_rejections)
    blocked = {(r.origin,r.index) for r in rejections}
    accepted, changed = [], {}
    writes = []
    for compartment, records, key_field, scope_field in (
        ('history', snapshot.derived.history, 'negotiation_id', 'shop_id'),
        ('preferences', snapshot.derived.preferences, 'pref_id', 'shop_id'),
        ('calibration', snapshot.derived.calibration, 'category', 'category')):
        prior = {getattr(x,key_field):x for x in getattr(current_records, compartment)}
        for record in records:
            current = prior.get(getattr(record,key_field))
            if compartment == 'preferences' and current:
                record = record.model_copy(update={'status':current.status,'asked_day':current.asked_day,
                    'declined_until':current.declined_until,
                    'evidence_seqs':sorted(set(current.evidence_seqs + record.evidence_seqs))}, deep=True)
            elif compartment == 'history' and current and any(seq > snapshot.through_seq for seq in current.evidence_seqs):
                continue
            elif compartment == 'calibration' and current:
                # Rebase is safe only if the frozen samples still include every current sample.
                fresh = {s.sample_id:s for s in record.samples}
                if any(s.sample_id not in fresh or fresh[s.sample_id] != s for s in current.samples):
                    raise ValueError('CALIBRATION_REBASE_CONFLICT')
            writes.append(StoreWrite(namespace=(snapshot.run_id,compartment,getattr(record,scope_field)),
                                     key=getattr(record,key_field),value=record))

    def reject(origin,index,code,policy_id=None):
        rejections.append(PatchRejection(origin=origin,index=index,code=code,policy_id=policy_id))

    def apply_op(op, origin, index, policy=None, proposal=None):
        if op.scope not in ('strategy',snapshot.category):
            return 'SCOPE_DENIED'
        if not op.evidence or not set(op.evidence) <= set(snapshot.evidence.valid_negotiation_ids):
            return 'INVALID_LESSON'
        bound = next((s for s in steps.values() if s.lesson_id == op.lesson_id), None) if op.lesson_id else None
        if origin == 'op' and bound:
            return 'INVALID_LESSON'
        if op.op == 'ADD':
            if op.lesson_id is not None or not op.text_vi.strip() or len(op.text_vi) > 500:
                return 'INVALID_LESSON'
            normalized = ' '.join(op.text_vi.casefold().split())
            lesson_id = sha256(f'{snapshot.run_id}:{op.scope}:{normalized}'.encode()).hexdigest()[:16]
            if (op.scope,lesson_id) in lessons or any(x.scope == op.scope and ' '.join(x.text_vi.casefold().split()) == normalized for x in lessons.values()):
                return 'INVALID_LESSON'
            lesson = PublicLesson(lesson_id=lesson_id,scope=op.scope,text_vi=op.text_vi,score=2,
                evidence=list(dict.fromkeys(op.evidence)),created_day=snapshot.day,updated_day=snapshot.day,version=1)
        else:
            lesson = lessons.get((op.scope,op.lesson_id))
            old = old_lessons.get((op.scope,op.lesson_id))
            if not lesson:
                return 'INVALID_LESSON'
            if old is None or old.version != lesson.version:
                return 'STALE_LESSON'
            if origin == 'op' and set(op.evidence) <= set(lesson.evidence):
                return 'DUPLICATE_EVIDENCE'
            updates = {'score':lesson.score + (-1 if op.op == 'DOWNVOTE' else 1),
                       'evidence':list(dict.fromkeys(lesson.evidence + op.evidence)),
                       'updated_day':snapshot.day,'version':lesson.version+1}
            if op.op == 'EDIT':
                updates['text_vi'] = op.text_vi
            lesson = lesson.model_copy(update=updates,deep=True)
        key = (lesson.scope,lesson.lesson_id)
        if lesson.score <= 0:
            lessons.pop(key,None)
            changed[key] = None
        else:
            lessons[key] = lesson
            changed[key] = lesson
        if proposal:
            if op.op == 'ADD':
                steps[policy] = PolicyStep(policy_id=policy,lesson_id=lesson.lesson_id,
                    target_skill=proposal.target_skill,trigger=proposal.trigger,action=proposal.action,
                    evidence_fact_ids=sorted(proposal.evidence_fact_ids))
            elif op.op == 'EDIT':
                if bound:
                    steps.pop(bound.policy_id,None)
                steps[policy] = PolicyStep(policy_id=policy,lesson_id=lesson.lesson_id,
                    target_skill=proposal.target_skill,trigger=proposal.trigger,action=proposal.action,
                    evidence_fact_ids=sorted(proposal.evidence_fact_ids))
            elif policy in steps:
                step = steps[policy]
                steps[policy] = step.model_copy(update={'evidence_fact_ids':sorted(set(step.evidence_fact_ids + proposal.evidence_fact_ids))},deep=True)
        accepted.append(op)
        return None

    for index, op in enumerate(reflection.ops):
        if ('op',index) not in blocked:
            code = apply_op(op,'op',index)
            if code:
                reject('op',index,code)
    for index, proposal in enumerate(reflection.proposals):
        if ('proposal',index) in blocked:
            continue
        policy = f'{proposal.target_skill}:{proposal.action}'
        op = proposal.lesson_op
        code = None
        current = versions.get(proposal.target_skill)
        if op.scope not in ('strategy',snapshot.category):
            code = 'SCOPE_DENIED'
        elif proposal.base_skill_version != (current.bundle.version if current else 0):
            code = 'STALE_SKILL'
        elif any(fid not in facts for fid in proposal.evidence_fact_ids):
            code = 'UNKNOWN_FACT'
        elif any(facts[fid].kind != proposal.trigger for fid in proposal.evidence_fact_ids):
            code = 'WRONG_FACT_KIND'
        elif not any(facts[fid].support_seq > snapshot.expected_cursor for fid in proposal.evidence_fact_ids):
            code = 'NO_FRESH_EVIDENCE'
        elif set(op.evidence) != {facts[fid].negotiation_id for fid in proposal.evidence_fact_ids}:
            code = 'EVIDENCE_MISMATCH'
        elif op.op == 'ADD' and policy in steps:
            code = 'DUPLICATE_POLICY'
        elif op.op in ('UPVOTE','DOWNVOTE') and (policy not in steps or steps[policy].lesson_id != op.lesson_id):
            code = 'MISSING_POLICY'
        elif op.op == 'EDIT' and (not any(s.target_skill == proposal.target_skill and s.lesson_id == op.lesson_id for s in steps.values())
                                  or (policy in steps and steps[policy].lesson_id != op.lesson_id)):
            code = 'MISSING_POLICY'
        elif policy in steps and set(proposal.evidence_fact_ids) <= set(steps[policy].evidence_fact_ids):
            code = 'DUPLICATE_EVIDENCE'
        if not code:
            op = op.model_copy(update={'text_vi':TEMPLATES[(proposal.target_skill,proposal.action)]},deep=True)
            code = apply_op(op,'proposal',index,policy,proposal)
        if code:
            reject('proposal',index,code,policy)
    for scope in ('strategy',snapshot.category):
        bucket = [x for x in lessons.values() if x.scope == scope]
        while len(bucket) > LESSON_CAP_PER_SCOPE:
            victim = min(bucket,key=lambda x:(x.score,x.updated_day,x.lesson_id))
            bucket.remove(victim)
            lessons.pop((scope,victim.lesson_id),None)
            changed[(scope,victim.lesson_id)] = None
    live_ids = {x.lesson_id for x in lessons.values()}
    steps = {key:value for key,value in steps.items() if value.lesson_id in live_ids}
    for (scope, key), value in changed.items():
        writes.append(StoreWrite(namespace=(snapshot.run_id,'lessons',scope),key=key,value=value))
    return StagedLearning(writes=writes, lessons=list(lessons.values()),
        steps=sorted(steps.values(),key=lambda s:(s.target_skill,PAIRS[s.action][1])),
        accepted_ops=accepted,rejections=rejections)
