"""Học từ sự kiện đã xảy ra; chỉ backend xác minh và ghi memory."""

from hashlib import sha256
from statistics import median
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.runner import run_agent
from app.agents.tools import bind_role_tools
from app.domain.models.learning import (Calibration, CalibrationRecord, CalibrationSample, LessonBatch,
    LessonOp, MemoryUpdateBatch, NightSummary, Preference, PublicHistory, PublicOutcome)
from app.domain.models.packages import Package
from app.domain.policies import CALIBRATION_MIN_POINTS, CALIBRATION_WINDOW
from app.memory.prompts import LEARNING_SYSTEM


def _id(*parts):
    return sha256(':'.join(map(str, parts)).encode()).hexdigest()[:16]


def _package(value):
    try:
        return Package.model_validate(value) if value else None
    except ValueError:
        return None


def _quantile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    low = int(index); high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (index - low)


def _derive_history(session, snapshot, shop_id, all_events):
    history_by_id = {item.negotiation_id: item for item in session.memory.get_history(shop_id)}
    new_ids = {e.negotiation_id for e in snapshot.events if e.seq >= snapshot.from_seq and e.negotiation_id and e.type in
               {'platform_turn','shop_turn','seller_decision','package_applied','market_result','negotiation_finished'}}
    result = []
    for negotiation_id in sorted(new_ids & set(snapshot.valid_negotiation_ids)):
        events = [e for e in all_events if e.shop_id == shop_id and e.data.get('negotiation_id') == negotiation_id]
        prior = history_by_id.get(negotiation_id)
        proposed = next((_package(e.data.get('package')) for e in events if e.type == 'platform_turn' and e.data.get('action') == 'propose'), None)
        agreed = next((_package(e.data.get('package')) for e in reversed(events) if e.type in {'platform_turn','shop_turn'} and e.data.get('action') == 'accept'), None)
        applied = next((_package(e.data.get('package')) for e in reversed(events) if e.type == 'package_applied'), None)
        seller = next((e.data.get('action') for e in reversed(events) if e.type == 'seller_decision'), None)
        market = next((e for e in reversed(events) if e.type == 'market_result' and isinstance(e.data.get('metrics'),dict)), None)
        finished = next((e for e in reversed(events) if e.type == 'negotiation_finished'), None)
        outcome = None
        if market:
            data = market.data['metrics']
            outcome = PublicOutcome.model_validate({k:data[k] for k in ('orders','revenue','ads_spend','roas')})
        relevant = [e.seq for e in events if e.type in {'platform_turn','shop_turn','seller_decision','package_applied','market_result','negotiation_finished'}]
        if not relevant:
            continue
        applied_event = next((e for e in reversed(events) if e.type == 'package_applied'), None)
        paused = bool(applied_event and any(e.type == 'auto_action' and e.data.get('action') == 'pause_ads'
            and e.shop_id == shop_id and e.seq > applied_event.seq
            and (e.data.get('negotiation_id') == negotiation_id or
                 (e.data.get('card_id') and e.data.get('card_id') == applied_event.data.get('card_id')))
            for e in all_events))
        result.append(PublicHistory(negotiation_id=negotiation_id,shop_id=shop_id,
            day=prior.day if prior else min(e.day for e in events),
            kind=finished.data['kind'] if finished else prior.kind if prior else 'propose',
            status=finished.data['status'] if finished else prior.status if prior else 'agreed' if agreed or applied else 'failed',
            rounds=max((e.data.get('round',0) for e in events if e.type=='platform_turn'),default=0),
            proposed_package=proposed or (prior.proposed_package if prior else None),
            agreed_package=agreed or (prior.agreed_package if prior else None),
            approved_package=applied or (prior.approved_package if prior else None),
            seller_action=seller or (prior.seller_action if prior else None),
            ads_paused=paused,
            outcome=outcome or (prior.outcome if prior else None),
            evidence_seqs=sorted(set(relevant + (prior.evidence_seqs if prior else []))),
            version=(prior.version+1 if prior else 1)))
    return result


def _derive_preferences(session, snapshot, shop_id, all_events):
    prior = {p.pref_id:p for p in session.store.list((session.run_id,'preferences',shop_id))}
    changed = {}
    for event in all_events:
        if event.seq < snapshot.from_seq or event.day != snapshot.day or event.shop_id != shop_id:
            continue
        value = field = None
        feedback = event.data.get('feedback_vi')
        if event.type == 'content_job' and feedback and ('sáng' in feedback.casefold() or 'tối' in feedback.casefold()):
            field, value = 'content_style', 'ảnh nền sáng'
        elif event.type == 'seller_decision' and event.data.get('edited_package'):
            edited = _package(event.data['edited_package'])
            if edited is not None:
                field, value = 'voucher_max_pct', str(edited.voucher_pct)
        if not field:
            continue
        pref_id = _id(session.run_id,shop_id,field,value)
        pref = changed.get(pref_id) or prior.get(pref_id) or Preference(pref_id=pref_id,shop_id=shop_id,
            field=field,value=value,status='candidate',evidence_seqs=[])
        if event.seq not in pref.evidence_seqs:
            pref.evidence_seqs.append(event.seq)
        changed[pref_id] = pref
    return list(changed.values())


def _derive_calibration(session, day, shop_id, all_events):
    state=session.states[shop_id]; category=state.public.category
    record=session.store.get((session.run_id,'calibration',category),category)
    snapshot=session.forecast_snapshots.get((shop_id,day)); actual=state.metrics.get(day)
    event=next((e for e in reversed(all_events) if e.type=='market_result' and e.shop_id==shop_id and e.day==day),None)
    if not snapshot or not actual or not event or snapshot.raw_point <= 0:
        return [], record.value if record else Calibration(category=category), None
    samples=list(record.samples) if record else []
    sample_id=_id(shop_id,day,snapshot.prediction_id)
    if sample_id not in {s.sample_id for s in samples}:
        samples.append(CalibrationSample(sample_id=sample_id,prediction_id=snapshot.prediction_id,shop_id=shop_id,
            target_day=day,raw_point=snapshot.raw_point,actual_orders=actual.orders,
            ratio=actual.orders/snapshot.raw_point,evidence_seqs=[event.seq]))
    samples=sorted(samples,key=lambda s:(s.target_day,s.sample_id))[-CALIBRATION_WINDOW:]
    ratios=[s.ratio for s in samples]
    value=Calibration(category=category,ratios=ratios,
        factor=median(ratios) if len(ratios)>=CALIBRATION_MIN_POINTS else 1.0,
        q_low=_quantile(ratios,.1) if len(ratios)>=CALIBRATION_MIN_POINTS else 1.0,
        q_high=_quantile(ratios,.9) if len(ratios)>=CALIBRATION_MIN_POINTS else 1.0)
    updated=CalibrationRecord(category=category,value=value,samples=samples,version=(record.version+1 if record else 1))
    mape=abs(snapshot.issued_point-actual.orders)/actual.orders if actual.orders else None
    return [updated],value,mape


def run_night(session, day, *, through_seq=None, publish=None):
    """Freeze, claim, reflect and publish once; integrated publication is injected."""
    from uuid import uuid4
    from app.domain.models.learning import (NightSnapshot, NightReflectionOutput, SkillPatchProposal,
        SkillVersion, NightPublication, PatchRejection)
    from app.domain.models.skills import SkillBundle
    from app.infrastructure.store import StoreConflict
    from app.memory.base import compose_base_text
    from app.memory.evidence import build_skill_facts
    from app.memory.learning import stage_learning, TEMPLATES
    from app.memory.skills import canonical_bytes, compile_skill, dump_skill, evaluate_candidate
    from app.negotiation.prompts import PLATFORM_SYSTEM
    from app.domain.privacy import leak_guard

    run_id = session.run_id
    stored = session.store.get_night_commit(run_id, day)
    if stored:
        return stored.summary.model_copy(deep=True)
    if day not in session.settled_days:
        raise ValueError('day must be settled before learning')
    shop_id = session.settings.demo_shop
    if not session.memory.enabled:
        summary = NightSummary(day=day,history_updates=[],pref_candidates=[],
            calibration={'factor':1.0,'points':0,'mape_today':None},lesson_ops=[],rejected_ops=0)
        session.night_summaries[day] = summary.model_copy(deep=True)
        return summary
    category = session.states[shop_id].public.category
    source = session.memory.source
    snapshot = session.store.get_night_snapshot(run_id,day)
    if snapshot is None:
        expected_revision, expected_cursor = session.store.metadata(run_id)
        evidence = session.memory.freeze_learning_evidence(day,through_seq=through_seq)
        cutoff = evidence.through_seq
        if source is not None:
            events, derived, cal_summary = source.freeze_night(day=day,through_seq=cutoff,after_seq=expected_cursor,
                prior_history=session.store.list((run_id,'history',shop_id)),
                prior_preferences=session.store.list((run_id,'preferences',shop_id)),
                prior_calibration=session.store.list((run_id,'calibration',category)))
        else:
            events = [e for e in session.log.since(run_id,0) if e.seq <= cutoff]
            history = _derive_history(session,evidence,shop_id,events)
            preferences = _derive_preferences(session,evidence,shop_id,events)
            calibrations, calibration, mape = _derive_calibration(session,day,shop_id,events)
            derived = MemoryUpdateBatch(day=day,through_seq=cutoff,history=history,preferences=preferences,
                calibration=calibrations,lesson_ops=[],valid_negotiation_ids=evidence.valid_negotiation_ids)
            cal_summary = {'factor':calibration.factor,'points':len(calibration.ratios),'mape_today':mape}
        facts = build_skill_facts(events,run_id=run_id,shop_id=shop_id,category=category,day=day,through_seq=cutoff)
        ids = sorted(set(evidence.valid_negotiation_ids) | {f.negotiation_id for f in facts})
        evidence.valid_negotiation_ids = ids
        derived.valid_negotiation_ids = ids
        evidence.skill_facts = facts
        base_texts = {skill:compose_base_text(skill,PLATFORM_SYSTEM) for skill in ('platform_offer','platform_renew')}
        prior = []
        evidence.skill_bundles = []
        for skill in ('platform_offer','platform_renew'):
            versions = [v for v in session.store.list_skill_versions(run_id,shop_id,skill) if v.created_day < day]
            if versions:
                prior.append(versions[-1])
            evidence.skill_bundles.append(session.memory.skill_bundle(shop_id,skill,day,base_text=base_texts[skill]))
        fields = dict(run_id=run_id,shop_id=shop_id,category=category,day=day,expected_revision=expected_revision,
            expected_cursor=expected_cursor,through_seq=cutoff,evidence=evidence,derived=derived,
            calibration_summary=cal_summary,prior_versions=prior,base_texts=base_texts)
        hash_fields = {k:(v.model_dump(mode='json') if hasattr(v,'model_dump') else
                         [x.model_dump(mode='json') for x in v] if isinstance(v,list) else v)
                       for k,v in fields.items() if k not in ('expected_revision','expected_cursor')}
        fields['snapshot_hash'] = sha256(canonical_bytes(hash_fields)).hexdigest()
        candidate = NightSnapshot(**fields)
        try:
            snapshot = session.store.save_night_snapshot(candidate)
        except StoreConflict as exc:
            if str(exc) != 'NIGHT_SNAPSHOT_CONFLICT':
                raise
            snapshot = session.store.get_night_snapshot(run_id,day)
    session.memory._learning_snapshot = snapshot.evidence.model_copy(deep=True)
    owner = uuid4().hex
    previous = session.store.get_reflection(run_id,day)
    receipt = session.store.claim_reflection(run_id,day,snapshot.snapshot_hash,owner)
    if receipt.status == 'reserved':
        if previous is not None or receipt.owner_token != owner:
            raise StoreConflict('NIGHT_BUSY')
        tools = bind_role_tools(session,'learning',shop_id,invocation_id=f'{run_id}:learning:{day}')
        def fallback(dispatch):
            evidence = dispatch('read_learning_evidence',{})
            choices = [('ads_auto_paused','platform_renew','disable_ads_on_renewal'),
                ('seller_approved_voucher_edit','platform_offer','seed_approved_voucher'),
                ('seller_approved_voucher_edit','platform_renew','seed_approved_voucher'),
                ('approved_package','platform_offer','seed_last_approved'),
                ('approved_package','platform_renew','seed_last_approved')]
            proposals = []
            bundles = {b.skill.skill_id:b for b in evidence.skill_bundles}
            for fact_kind, target, action in choices:
                matching = [f for f in evidence.skill_facts if f.kind == fact_kind and f.support_seq > snapshot.expected_cursor]
                if not matching: continue
                fact = max(matching,key=lambda f:(f.package_applied_seq,f.support_seq,f.fact_id))
                bundle = bundles[target]
                policy = next((s for s in bundle.skill.learned_steps if s.action == action),None)
                if policy and fact.fact_id in policy.evidence_fact_ids: continue
                lesson = next((x for x in evidence.existing_lessons if policy and x.lesson_id == policy.lesson_id),None)
                if policy and lesson is None: continue
                op = LessonOp(op='UPVOTE' if policy else 'ADD',lesson_id=policy.lesson_id if policy else None,
                    text_vi=TEMPLATES[(target,action)],scope=lesson.scope if lesson else category,evidence=[fact.negotiation_id])
                proposals.append(SkillPatchProposal(lesson_op=op,target_skill=target,trigger=fact_kind,action=action,
                    evidence_fact_ids=[fact.fact_id],base_skill_version=bundle.version))
                if len(proposals) == 3: break
            if proposals: return NightReflectionOutput(proposals=proposals)
            if not evidence.valid_negotiation_ids: return NightReflectionOutput()
            feedback_id = next((e.negotiation_id for e in evidence.events if e.feedback_vi and e.negotiation_id in evidence.valid_negotiation_ids),None)
            text = 'Ưu tiên nội dung dễ đọc khi người bán có góp ý.' if feedback_id else 'Ưu tiên nội dung rõ ràng.'
            return NightReflectionOutput(ops=[LessonOp(op='ADD',lesson_id=None,text_vi=text,scope='strategy',
                evidence=[feedback_id or evidence.valid_negotiation_ids[0]])])
        def emit(type,data):
            safe={k:v for k,v in data.items() if k in {'role','tool_name','tool_call_id','requested_by','status','source','error_code','invocation_id','record_refs'}}
            session.log.add(run_id,day,type,'learning',shop_id,'Learning xử lý evidence.',safe)
        try:
            from app.negotiation.agents import replay_context_for
            run = run_agent('learning',llm=session.llm,tools=tools,messages=[SystemMessage(content=LEARNING_SYSTEM),
                HumanMessage(content=f'Ngày {day}: xem evidence được cấp và đề xuất lesson.')],
                output_schema=NightReflectionOutput,fallback=fallback,emit=emit,run_name=f'{run_id}:learning:{day}',
                replay_context=replay_context_for(session,'learning',shop_id))
            receipt = session.store.finish_reflection(receipt.model_copy(update={'status':'completed','output':run.value,
                'source':run.source,'error_code':None},deep=True))
        except Exception:
            receipt = session.store.finish_reflection(receipt.model_copy(update={'status':'failed','output':None,
                'source':'skipped','error_code':'REFLECTION_FAILED'},deep=True))
    reflection = receipt.output or NightReflectionOutput()

    def make_publication():
        current_lessons = session.store.list((run_id,'lessons','strategy')) + session.store.list((run_id,'lessons',category))
        current_versions = []
        for skill in ('platform_offer','platform_renew'):
            versions = session.store.list_skill_versions(run_id,shop_id,skill)
            if versions: current_versions.append(versions[-1])
        current_records = MemoryUpdateBatch(day=day,through_seq=snapshot.through_seq,
            history=session.store.list((run_id,'history',shop_id)),preferences=session.store.list((run_id,'preferences',shop_id)),
            calibration=session.store.list((run_id,'calibration',category)),lesson_ops=[],valid_negotiation_ids=[])
        rejected = []
        state = session.states.get(shop_id)
        for origin, items in (('op',reflection.ops),('proposal',reflection.proposals)):
            for i, item in enumerate(items):
                op = item if origin == 'op' else item.lesson_op
                if not state or not getattr(state,'private',None):
                    rejected.append(PatchRejection(origin=origin,index=i,code='PRIVATE_VALIDATION_UNAVAILABLE')); continue
                _, unsafe = leak_guard(op.text_vi,state.public,state.private,session.world.fees)
                if origin == 'proposal':
                    _, template_unsafe = leak_guard(TEMPLATES[(item.target_skill,item.action)],state.public,state.private,session.world.fees)
                    unsafe = unsafe or template_unsafe
                else:
                    from app.memory.gateway import _has_number
                    if _has_number(op.text_vi) or len(op.text_vi)>500 or not op.text_vi.strip() or (op.op in ('ADD','EDIT') and not session.memory._lesson_grounded(op,snapshot.evidence)):
                        unsafe = True
                if unsafe:
                    rejected.append(PatchRejection(origin=origin,index=i,code='INVALID_LESSON'))
        staged = stage_learning(snapshot,reflection,current_lessons=current_lessons,current_versions=current_versions,
                                current_records=current_records,text_rejections=rejected)
        versions = []
        try:
            for skill_id in ('platform_offer','platform_renew'):
                previous_version = next((v for v in current_versions if v.bundle.skill.skill_id == skill_id),None)
                compiled = compile_skill(skill_id,snapshot.base_texts[skill_id],[s for s in staged.steps if s.target_skill == skill_id])
                artifact = dump_skill(compiled)
                old_artifact = previous_version.artifact_json.encode('utf-8') if previous_version else dump_skill(compile_skill(skill_id,snapshot.base_texts[skill_id],[]))
                if artifact == old_artifact: continue
                parent = previous_version.bundle.version if previous_version else 0
                bundle = SkillBundle(run_id=run_id,shop_id=shop_id,category=category,version=parent+1,
                    effective_from_day=day+1,skill=compiled,artifact_hash=sha256(artifact).hexdigest())
                checks = evaluate_candidate(bundle,base_text=snapshot.base_texts[skill_id],facts=snapshot.evidence.skill_facts)
                versions.append(SkillVersion(bundle=bundle,parent_version=parent,created_day=day,
                    source_through_seq=snapshot.through_seq,artifact_json=artifact.decode('utf-8'),
                    eval_level='deterministic',eval_checks=checks))
        except ValueError:
            rejected = [PatchRejection(origin=origin,index=i,code='CANDIDATE_EVAL_FAILED')
                for origin, items in (('op',reflection.ops),('proposal',reflection.proposals)) for i,_ in enumerate(items)]
            staged = stage_learning(snapshot,NightReflectionOutput(),current_lessons=current_lessons,
                current_versions=current_versions,current_records=current_records)
            staged.rejections = rejected
            versions = []
        summary = NightSummary(day=day,history_updates=[x.negotiation_id for x in snapshot.derived.history],
            pref_candidates=[x.pref_id for x in snapshot.derived.preferences],calibration=snapshot.calibration_summary,
            lesson_ops=staged.accepted_ops,rejected_ops=len(staged.rejections))
        return NightPublication(run_id=run_id,shop_id=shop_id,day=day,snapshot_hash=snapshot.snapshot_hash,
            through_seq=snapshot.through_seq,writes=staged.writes,versions=versions,summary=summary,
            rejections=staged.rejections,source=receipt.source)
    commit_fn = publish or session.store.commit_night
    for attempt in range(2):
        revision,cursor = session.store.metadata(run_id)
        try:
            publication = make_publication()
            commit = commit_fn(publication,expected_revision=revision,expected_cursor=cursor)
            break
        except StoreConflict as exc:
            if str(exc) != 'STALE_KNOWLEDGE' or attempt:
                raise
    session.night_summaries[day] = commit.summary.model_copy(deep=True)
    session.memory._learning_snapshot = None
    if source is None:
        key = f'night:{run_id}:{day}'
        existing = session.log.since(run_id,0)
        if not any(e.type == 'memory_write' and e.data.get('commit_key') == key for e in existing):
            session.log.add(run_id,day,'memory_write','memory',shop_id,'Đã cập nhật bộ nhớ có evidence.',
                {'revision':commit.knowledge.store.revision,'items':commit.knowledge.store.applied_ids,'source':receipt.source,'commit_key':key})
        if not any(e.type == 'night_summary' and e.data.get('commit_key') == key for e in existing):
            session.log.add(run_id,day,'night_summary','memory',shop_id,'Hoàn tất học ban đêm.',
                {'summary':commit.summary.model_dump(mode='json'),'source':receipt.source,'commit_key':key})
    return commit.summary.model_copy(deep=True)
