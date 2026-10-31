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
    new_ids = {e.negotiation_id for e in snapshot.events if e.negotiation_id and e.type in
               {'platform_turn','shop_turn','seller_decision','package_applied','market_result'}}
    result = []
    for negotiation_id in sorted(new_ids & set(snapshot.valid_negotiation_ids)):
        events = [e for e in all_events if e.shop_id == shop_id and e.data.get('negotiation_id') == negotiation_id]
        prior = history_by_id.get(negotiation_id)
        proposed = next((_package(e.data.get('package')) for e in events if e.type == 'platform_turn' and e.data.get('action') == 'propose'), None)
        agreed = next((_package(e.data.get('package')) for e in reversed(events) if e.type in {'platform_turn','shop_turn'} and e.data.get('action') == 'accept'), None)
        applied = next((_package(e.data.get('package')) for e in reversed(events) if e.type == 'package_applied'), None)
        seller = next((e.data.get('action') for e in reversed(events) if e.type == 'seller_decision'), None)
        market = next((e for e in reversed(events) if e.type == 'market_result' and isinstance(e.data.get('metrics'),dict)), None)
        outcome = None
        if market:
            data = market.data['metrics']
            outcome = PublicOutcome.model_validate({k:data[k] for k in ('orders','revenue','ads_spend','roas')})
        relevant = [e.seq for e in events if e.type in {'platform_turn','shop_turn','seller_decision','package_applied','market_result'}]
        if not relevant:
            continue
        result.append(PublicHistory(negotiation_id=negotiation_id,shop_id=shop_id,
            day=prior.day if prior else min(e.day for e in events),kind=prior.kind if prior else 'propose',
            status='agreed' if agreed or applied else 'failed',
            rounds=max((e.data.get('round',0) for e in events if e.type=='platform_turn'),default=0),
            proposed_package=proposed or (prior.proposed_package if prior else None),
            agreed_package=agreed or (prior.agreed_package if prior else None),
            approved_package=applied or (prior.approved_package if prior else None),
            seller_action=seller or (prior.seller_action if prior else None),
            ads_paused=bool(session.states[shop_id].active and session.states[shop_id].active.ads_paused),
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


def run_night(session, day):
    if day in session.night_summaries:
        return session.night_summaries[day].model_copy(deep=True)
    if day not in session.settled_days:
        raise ValueError('day must be settled before learning')
    shop_id=session.settings.demo_shop
    if not session.memory.enabled:
        summary=NightSummary(day=day,history_updates=[],pref_candidates=[],
            calibration={'factor':1.0,'points':0,'mape_today':None},lesson_ops=[],rejected_ops=0)
        session.night_summaries[day]=summary
        return summary.model_copy(deep=True)
    expected_revision=session.knowledge_revision; expected_cursor=session.memory_cursor
    snapshot=session.memory.freeze_learning_evidence(day)
    events=[e for e in session.log.since(session.run_id,0) if e.seq <= snapshot.through_seq]
    history=_derive_history(session,snapshot,shop_id,events)
    preferences=_derive_preferences(session,snapshot,shop_id,events)
    calibrations,calibration,mape=_derive_calibration(session,day,shop_id,events)
    tools=bind_role_tools(session,'learning',shop_id,invocation_id=f'{session.run_id}:learning:{day}')
    def fallback(dispatch):
        evidence=dispatch('read_learning_evidence',{})
        if not evidence.valid_negotiation_ids:
            return LessonBatch(ops=[])
        op=LessonOp(op='ADD',lesson_id=None,text_vi='Ưu tiên nội dung dễ đọc khi người bán có góp ý.',
                    scope='strategy',evidence=[evidence.valid_negotiation_ids[0]])
        return LessonBatch(ops=[op])
    def emit(type,data):
        safe={k:v for k,v in data.items() if k in {'role','tool_name','tool_call_id','requested_by','status','source','error_code','invocation_id','record_refs'}}
        session.log.add(session.run_id,day,type,'learning',shop_id,'Learning xử lý evidence.',safe)
    run=run_agent('learning',llm=session.llm,tools=tools,messages=[SystemMessage(content=LEARNING_SYSTEM),
        HumanMessage(content=f'Ngày {day}: xem evidence được cấp và đề xuất lesson.')],
        output_schema=LessonBatch,fallback=fallback,emit=emit,run_name=f'{session.run_id}:learning:{day}')
    batch=MemoryUpdateBatch(day=day,through_seq=snapshot.through_seq,history=history,preferences=preferences,
        calibration=calibrations,lesson_ops=run.value.ops,valid_negotiation_ids=snapshot.valid_negotiation_ids)
    result=session.memory.commit_memory_updates(batch,expected_revision=expected_revision,expected_cursor=expected_cursor)
    summary=NightSummary(day=day,history_updates=[x.negotiation_id for x in history],
        pref_candidates=[x.pref_id for x in preferences],calibration={'factor':calibration.factor,
        'points':len(calibration.ratios),'mape_today':mape},lesson_ops=result.accepted_lesson_ops,
        rejected_ops=result.rejected_ops)
    session.night_summaries[day]=summary.model_copy(deep=True)
    session.log.add(session.run_id,day,'memory_write','memory',shop_id,'Đã cập nhật bộ nhớ có evidence.',
        {'revision':result.store.revision,'items':result.store.applied_ids,'source':run.source})
    session.log.add(session.run_id,day,'night_summary','memory',shop_id,'Hoàn tất học ban đêm.',
        {'summary':summary.model_dump(mode='json'),'source':run.source})
    return summary
