import json
from pathlib import Path
from hashlib import sha256
import pytest
from app.domain.models.events import Event
from app.domain.models.learning import NightSnapshot, NightReflectionOutput
from app.domain.models.packages import Package
from app.domain.models.skills import EvidenceFact, SkillBundle
from app.memory.evidence import build_skill_facts
from app.memory.learning import stage_learning
from app.memory.skills import apply_skill, compile_skill, dump_skill, evaluate_candidate, load_skill


EXAMPLES = json.loads(Path('contracts/self_improve/examples.json').read_text())

def entries(name):
    return [e['payload'] for e in EXAMPLES if e['model']==name]


def test_compile_apply_and_artifact_tampering():
    facts = [EvidenceFact.model_validate(x) for x in entries('EvidenceFact')]
    bundle = SkillBundle.model_validate(entries('SkillBundle')[0])
    base = Package(content_refresh=True,ads_daily_budget=70000,voucher_pct=10,stop_roas_below=4.0,stop_after_days=2,duration_days=3)
    compiled = compile_skill('platform_renew','Platform renew fixture v1',list(reversed(bundle.skill.learned_steps)))
    assert compiled == bundle.skill
    assert load_skill(dump_skill(compiled),expected_hash=bundle.artifact_hash) == compiled
    with pytest.raises(ValueError,match='ARTIFACT_HASH_MISMATCH'):
        load_skill(dump_skill(compiled)+b' ',expected_hash=bundle.artifact_hash)
    args = dict(run_id='r1',shop_id='E',category='quat_mini',kind='renew')
    result = apply_skill(base,bundle,facts,day=4,memory_enabled=True,**args)
    assert (result.package.ads_daily_budget,result.package.voucher_pct,result.package.stop_roas_below) == (0,5,None)
    assert len(result.uses) == 3
    assert apply_skill(base,bundle,facts,day=3,memory_enabled=True,**args).package == base
    assert apply_skill(base,bundle,facts,day=4,memory_enabled=False,**args).uses == []
    assert len(evaluate_candidate(bundle,base_text='Platform renew fixture v1',facts=facts)) == 8


def test_event_join_scope_cutoff_and_approval():
    expected = [EvidenceFact.model_validate(x) for x in entries('EvidenceFact')]
    p1 = expected[0].package.model_dump(mode='json'); p0 = p1 | {'voucher_pct':3}
    def event(seq, day, typ, actor, data, shop='E'):
        return Event(seq=seq,run_id='r1',shop_id=shop,day=day,ts='2026-01-01T00:00:00Z',
                     type=typ,actor=actor,text_vi='public',data=data)
    events = [event(6,1,'negotiation_finished','system',{'negotiation_id':'n1','status':'agreed','package':p0}),
        event(8,1,'card_sent','system',{'card_id':'c1','negotiation_id':'n1'}),
        event(10,1,'seller_decision','seller',{'card_id':'c1','negotiation_id':'n1','action':'edit','edited_package':p1}),
        event(11,1,'package_applied','system',{'card_id':'c1','negotiation_id':'n1','package':p1}),
        event(20,3,'auto_action','system',{'card_id':'c1','action':'pause_ads'})]
    args=dict(run_id='r1',shop_id='E',category='quat_mini',day=3,through_seq=20)
    assert build_skill_facts(list(reversed(events)),**args) == sorted(expected,key=lambda x:(x.support_seq,x.kind,x.fact_id))
    assert build_skill_facts(events[:-1],**args) == sorted(expected[:2],key=lambda x:(x.support_seq,x.kind,x.fact_id))
    assert build_skill_facts([x for x in events if x.type!='seller_decision'],**args) == []
    assert build_skill_facts(events,**(args | {'shop_id':'D'})) == []
    with pytest.raises(ValueError,match='DUPLICATE_EVENT_SEQ'):
        build_skill_facts(events+[events[0].model_copy(update={'text_vi':'different'})],**args)


@pytest.mark.parametrize('action,has_edit,matches,has_apply,voucher_change,expected', [
    ('edit', True, True, True, True, {'approved_package', 'seller_approved_voucher_edit'}),
    ('accept', True, True, True, True, {'approved_package', 'seller_approved_voucher_edit'}),
    ('accept', False, True, True, True, {'approved_package'}),
    ('edit', False, True, True, True, set()),
    ('edit', True, False, True, True, set()),
    ('accept', True, False, True, True, set()),
    ('edit', True, True, False, True, set()),
    ('accept', True, True, False, True, set()),
    ('edit', True, True, True, False, {'approved_package'}),
    ('accept', True, True, True, False, {'approved_package'}),
])
def test_voucher_edit_requires_matching_applied_package(action, has_edit, matches, has_apply, voucher_change, expected):
    package = entries('EvidenceFact')[0]['package']
    original = package | {'voucher_pct': 3 if voucher_change else package['voucher_pct'], 'ads_daily_budget': 10000}
    edited = package if matches else package | {'ads_daily_budget': 60000}
    def event(seq, kind, actor, data):
        return Event(seq=seq,run_id='r1',shop_id='E',day=1,ts='2026-01-01T00:00:00Z',
                     type=kind,actor=actor,text_vi='private sentinel',data=data | {'unit_cost':'private sentinel'})
    decision = {'card_id':'c1','negotiation_id':'n1','action':action}
    if has_edit:
        decision['edited_package'] = edited
    events = [event(6,'negotiation_finished','system',{'negotiation_id':'n1','status':'agreed','package':original}),
              event(8,'card_sent','system',{'card_id':'c1','negotiation_id':'n1'}),
              event(10,'seller_decision','seller',decision)]
    if has_apply:
        events.append(event(11,'package_applied','system',{'card_id':'c1','negotiation_id':'n1','package':package}))
    facts = build_skill_facts(events,run_id='r1',shop_id='E',category='quat_mini',day=1,through_seq=11)
    assert {fact.kind for fact in facts} == expected
    assert all('private sentinel' not in fact.model_dump_json() for fact in facts)
    edited_fact = next((fact for fact in facts if fact.kind == 'seller_approved_voucher_edit'), None)
    if edited_fact:
        assert edited_fact.source_seqs == [6,8,10,11]
        assert edited_fact.package.model_dump(mode='json') == package


def test_stage_policy_templates_and_freshness():
    s = NightSnapshot.model_validate_json(json.dumps(entries('NightSnapshot')[0]))
    reflection = NightReflectionOutput.model_validate_json(json.dumps(entries('NightReflectionOutput')[0]))
    stage = stage_learning(s,reflection,current_lessons=[],current_versions=[],current_records=s.derived)
    assert len(stage.steps)==len(stage.accepted_ops)==len(stage.writes)==3
    assert [x.score for x in stage.lessons] == [2,2,2]
    assert not stage.rejections
    stale = s.model_copy(update={'expected_cursor':20})
    rejected = stage_learning(stale,reflection,current_lessons=[],current_versions=[],current_records=s.derived)
    assert [r.code for r in rejected.rejections] == ['NO_FRESH_EVIDENCE']*3
    assert not rejected.steps


def test_offline_night_publishes_d_plus_one_and_retries():
    from app.core.settings import Settings
    from app.infrastructure.eventlog import EventLog
    from app.memory.night import run_night
    from app.runtime.session import Session
    from tests.fakes.market import FakeMarket
    session = Session.new(Settings(_env_file=None,llm_mode='offline',demo_shop='E'),market=FakeMarket(),log=EventLog())
    from app.domain.models.intent import IntentBrief
    session.brief = IntentBrief(brief_id='b',version=1,shop_id='E',intent='increase_orders',goal_vi='Tăng đơn',allow_ads=True,ads_daily_cap=None,content_refresh=True,duration_days=3,confirmed=True)
    run = session.run_id
    package = entries('EvidenceFact')[0]['package']; before = package | {'voucher_pct':3}
    session.log.add(run,1,'negotiation_finished','system','E','Kết thúc',{'negotiation_id':'n1','status':'agreed','kind':'propose','package':before})
    session.log.add(run,1,'card_sent','system','E','Thẻ',{'card_id':'c1','negotiation_id':'n1'})
    session.log.add(run,1,'seller_decision','seller','E','Duyệt',{'card_id':'c1','negotiation_id':'n1','action':'edit','edited_package':package})
    session.log.add(run,1,'package_applied','system','E','Áp dụng',{'card_id':'c1','negotiation_id':'n1','package':package})
    session.log.add(run,3,'auto_action','system','E','Tạm dừng',{'card_id':'c1','action':'pause_ads'})
    session.day=3; session.settled_days.add(3)
    summary = run_night(session,3)
    assert len(summary.lesson_ops)==3 and summary.rejected_ops==0
    versions = session.store.list_skill_versions(run,'E','platform_renew')
    assert len(versions)==1 and versions[0].bundle.effective_from_day==4
    assert session.store.get_reflection(run,3).source=='offline'
    revision = session.knowledge_revision
    session.night_summaries.clear()
    assert run_night(session,3)==summary and session.knowledge_revision==revision


def test_native_learning_receives_frozen_facts_as_tool_message():
    from langchain_core.messages import ToolMessage
    from app.core.settings import Settings
    from app.domain.models.intent import IntentBrief
    from app.infrastructure.eventlog import EventLog
    from app.memory.night import run_night
    from app.runtime.session import Session
    from tests.fakes.llm import FakeLLM, call
    from tests.fakes.market import FakeMarket
    session=Session.new(Settings(_env_file=None,llm_mode='offline',demo_shop='E'),market=FakeMarket(),log=EventLog())
    session.brief=IntentBrief(brief_id='b',version=1,shop_id='E',intent='increase_orders',goal_vi='Tăng đơn',allow_ads=True,ads_daily_cap=None,content_refresh=True,duration_days=3,confirmed=True)
    run=session.run_id; package=entries('EvidenceFact')[0]['package']
    session.log.add(run,1,'seller_decision','seller','E','Duyệt',{'card_id':'c','negotiation_id':'n','action':'accept'})
    session.log.add(run,1,'package_applied','system','E','Áp dụng',{'card_id':'c','negotiation_id':'n','package':package})
    session.day=1; session.settled_days.add(1)
    def read_after_new_event(messages):
        session.log.add(run,1,'auto_action','system','E','sau cutoff',{'card_id':'c','action':'pause_ads'})
        return [call('read_learning_evidence',{},'read')]
    def finish(messages):
        evidence=json.loads(next(m.content for m in messages if isinstance(m,ToolMessage)))
        assert [f['kind'] for f in evidence['skill_facts']]==['approved_package']
        assert len(evidence['skill_bundles'])==2
        assert all(e['seq']<=evidence['through_seq'] for e in evidence['events'])
        return [call('finish_learning',{'ops':[],'proposals':[]},'done')]
    session.llm=FakeLLM([read_after_new_event,finish])
    assert run_night(session,1).rejected_ops==0
    assert session.store.get_reflection(run,1).source=='fixture'


def test_evaluation_failure_discards_lessons_and_keeps_history(monkeypatch):
    from app.core.settings import Settings
    from app.domain.models.intent import IntentBrief
    from app.infrastructure.eventlog import EventLog
    from app.memory.night import run_night
    from app.runtime.session import Session
    from tests.fakes.market import FakeMarket
    session=Session.new(Settings(_env_file=None,llm_mode='offline',demo_shop='E'),market=FakeMarket(),log=EventLog())
    session.brief=IntentBrief(brief_id='b',version=1,shop_id='E',intent='increase_orders',goal_vi='Tăng đơn',allow_ads=True,ads_daily_cap=None,content_refresh=True,duration_days=3,confirmed=True)
    run=session.run_id; package=entries('EvidenceFact')[0]['package']
    session.log.add(run,1,'platform_turn','platform_agent','E','Đề xuất',{'negotiation_id':'n','action':'propose','package':package})
    session.log.add(run,1,'seller_decision','seller','E','Duyệt',{'card_id':'c','negotiation_id':'n','action':'accept'})
    session.log.add(run,1,'package_applied','system','E','Áp dụng',{'card_id':'c','negotiation_id':'n','package':package})
    session.day=1; session.settled_days.add(1)
    def fail(*args,**kwargs): raise ValueError('CANDIDATE_EVAL_FAILED')
    monkeypatch.setattr('app.memory.skills.evaluate_candidate',fail)
    summary=run_night(session,1)
    assert not summary.lesson_ops and summary.rejected_ops==2
    assert session.memory.get_history('E')[0].approved_package.voucher_pct==5
    assert not session.store.list_skill_versions(run,'E','platform_offer')
    assert not session.memory.list_lessons(session.states['E'].public.category)


def test_calibration_uses_daily_raw_prediction_and_thirty_sample_window():
    from types import SimpleNamespace
    from app.core.settings import Settings
    from app.infrastructure.eventlog import EventLog
    from app.memory.night import _derive_calibration
    from app.runtime.session import Session
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),log=EventLog())
    shop='D'; category=session.states[shop].public.category
    for day in range(1,32):
        actual=1 if day==1 else 10
        session.states[shop].metrics[day]=SimpleNamespace(orders=actual)
        session.forecast_snapshots[(shop,day)]=SimpleNamespace(prediction_id=f'p{day}',raw_point=15.0,issued_point=45)
        session.log.add(session.run_id,day,'market_result','market',shop,'Đã chốt',{'prediction_id':f'p{day}'})
        records,value,mape=_derive_calibration(session,day,shop,session.log.since(session.run_id,0))
        record=records[0]
        assert record.samples[-1].ratio==pytest.approx(actual/15)
        if day<5: assert value.factor==1.0
        if day==5: assert value.factor==pytest.approx(2/3)
        session.store.put((session.run_id,'calibration',category),category,record)
    assert len(record.samples)==30 and record.samples[0].target_day==2
    assert value.factor==pytest.approx(2/3) and mape==pytest.approx(3.5)
    duplicate,_,_=_derive_calibration(session,31,shop,session.log.since(session.run_id,0))
    assert len(duplicate[0].samples)==30 and len({s.sample_id for s in duplicate[0].samples})==30
