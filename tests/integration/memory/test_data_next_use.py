import json
from hashlib import sha256
from langchain_core.messages import ToolMessage
from app.core.settings import Settings
from app.domain.models.learning import (LearningEvidence, MemoryUpdateBatch, NightPublication,
    NightReflectionOutput, NightSnapshot, NightSummary, PublicLesson, SkillVersion, StoreWrite)
from app.domain.models.skills import PolicyStep, SkillBundle
from app.infrastructure.data_agents import load_data_context
from app.infrastructure.sqlite_store import SqliteKnowledgeStore
from app.memory.base import compose_base_text
from app.memory.evidence import build_skill_facts
from app.memory.skills import canonical_bytes, compile_skill, dump_skill, evaluate_candidate, prepare_platform_context
from app.negotiation.agents import decide_platform
from app.negotiation.prompts import PLATFORM_SYSTEM
from data.growth_data.service import DataService
from tests.fakes.llm import FakeLLM, call


def test_reopened_published_skill_changes_next_native_tool_message(tmp_path):
    service=DataService(tmp_path); principal=service.bootstrap()
    with service.store.connect(write=True) as c:
        on=service.create_run(c,principal,{'simulation_days':2,'memory_enabled':True})['run_id']
        off=service.create_run(c,principal,{'simulation_days':2,'memory_enabled':False})['run_id']
        package={'content_refresh':True,'ads_daily_budget':45000,'voucher_pct':3,'stop_roas_below':6.5,'stop_after_days':2,'duration_days':3}
        service.event(c,on,1,'seller_decision','simulated_seller','D',{'card_id':'c1','negotiation_id':'n1','action':'accept','unit_cost':'secret sentinel'})
        cutoff=service.event(c,on,1,'package_applied','orchestrator','D',{'card_id':'c1','negotiation_id':'n1','package':package,'unit_cost':'secret sentinel'})
    settings=Settings(_env_file=None,llm_mode='offline',demo_shop='D')
    brief={'brief_id':'b','version':1,'shop_id':'D','intent':'increase_orders','goal_vi':'Tăng đơn',
           'allow_ads':True,'ads_daily_cap':None,'content_refresh':True,'duration_days':3,'confirmed':True}
    session=load_data_context(service,settings,on,'D',brief=brief)
    category=session.states['D'].public.category
    facts=build_skill_facts(session.memory.source.events(cutoff),run_id=on,shop_id='D',category=category,day=1,through_seq=cutoff)
    assert len(facts)==1
    text=compose_base_text('platform_renew',PLATFORM_SYSTEM)
    lesson=PublicLesson(lesson_id='lesson',scope=category,text_vi='Khi gia hạn, dùng gói đã duyệt gần nhất làm điểm khởi đầu.',
                        score=2,evidence=['n1'],created_day=1,updated_day=1,version=1)
    step=PolicyStep(policy_id='platform_renew:seed_last_approved',lesson_id='lesson',target_skill='platform_renew',
                    trigger='approved_package',action='seed_last_approved',evidence_fact_ids=[facts[0].fact_id])
    compiled=compile_skill('platform_renew',text,[step]); blob=dump_skill(compiled)
    bundle=SkillBundle(run_id=on,shop_id='D',category=category,version=1,effective_from_day=2,skill=compiled,artifact_hash=sha256(blob).hexdigest())
    version=SkillVersion(bundle=bundle,parent_version=0,created_day=1,source_through_seq=cutoff,artifact_json=blob.decode(),
        eval_level='deterministic',eval_checks=evaluate_candidate(bundle,base_text=text,facts=facts))
    evidence=LearningEvidence(day=1,from_seq=1,through_seq=cutoff,events=[],existing_lessons=[],valid_negotiation_ids=['n1'],
                              knowledge_revision=0,skill_facts=facts)
    derived=MemoryUpdateBatch(day=1,through_seq=cutoff,history=[],preferences=[],calibration=[],lesson_ops=[],valid_negotiation_ids=['n1'])
    args={'run_id':on,'shop_id':'D','category':category,'day':1,'expected_revision':0,'expected_cursor':0,'through_seq':cutoff,
          'evidence':evidence,'derived':derived,'calibration_summary':{'factor':1.0,'points':0,'mape_today':None},'prior_versions':[],
          'base_texts':{'platform_offer':compose_base_text('platform_offer',PLATFORM_SYSTEM),'platform_renew':text}}
    digest={k:(v.model_dump(mode='json') if hasattr(v,'model_dump') else v) for k,v in args.items() if k not in ('expected_revision','expected_cursor')}
    snap=NightSnapshot(**args,snapshot_hash=sha256(canonical_bytes(digest)).hexdigest())
    store=SqliteKnowledgeStore(service.store); store.save_night_snapshot(snap)
    receipt=store.claim_reflection(on,1,snap.snapshot_hash,'owner')
    store.finish_reflection(receipt.model_copy(update={'status':'completed','output':NightReflectionOutput(),'source':'fixture'}))
    summary=NightSummary(day=1,history_updates=[],pref_candidates=[],calibration=args['calibration_summary'],lesson_ops=[],rejected_ops=0)
    pub=NightPublication(run_id=on,shop_id='D',day=1,snapshot_hash=snap.snapshot_hash,through_seq=cutoff,
        writes=[StoreWrite(namespace=(on,'lessons',category),key='lesson',value=lesson)],versions=[version],summary=summary,rejections=[],source='fixture')
    store.commit_night(pub,expected_revision=0,expected_cursor=0)
    def choose(run_id,enabled):
        context=load_data_context(service,settings,run_id,'D',brief=brief)
        context.day=2
        pinned=prepare_platform_context(context,'D',2,'renew',f'{run_id}:attempt')
        def check(messages):
            view=json.loads(next(m.content for m in messages if isinstance(m,ToolMessage) and m.name=='read_memory'))
            assert 'secret sentinel' not in json.dumps(view)
            assert view['skill']['bundle']['version']==(1 if enabled else 0)
            seed=view['skill']['seed']['package']
            return [call('validate_platform_package',{'package':seed},'check'),call('forecast_package',{'package':seed},'forecast')]
        def finish(messages):
            result=json.loads(next(m.content for m in messages if isinstance(m,ToolMessage) and m.name=='validate_platform_package'))
            return [call('finish_platform',{'action':'propose','package':result['corrected_package'],'message_vi':'Gói phù hợp.'},'done')]
        context.llm=FakeLLM([[call('get_public_context',{},'context'),call('read_memory',{},'memory')],check,finish])
        result=decide_platform(context,'D',[],None,negotiation_id=f'{run_id}:attempt',platform_context=pinned)
        return result.package.voucher_pct
    assert choose(on,True)==3
    assert choose(off,False)==10
    reopened=load_data_context(service,settings,on,'D',brief=brief)
    assert reopened.memory.skill_bundle('D','platform_renew',2,base_text=text+' changed').version==0
    with service.store.connect(write=True) as c:
        c.execute("UPDATE skill_versions SET payload_json=json_set(payload_json,'$.artifact_json','tampered') WHERE run_id=? AND skill_id='platform_renew'",(on,))
    assert reopened.memory.skill_bundle('D','platform_renew',2,base_text=text).version==0
    with service.store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM events WHERE run_id=? AND type IN ('base_skill_changed','skill_artifact_invalid')",(on,)).fetchone()[0]==2


def test_skip_and_publication_choose_one_durable_outcome(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.runtime.data_worker import DataWorker
    from data.growth_data.errors import Fault
    from data.growth_data.storage import insert, now
    from tests.contract.test_knowledge_repository import snapshot, publication
    for initial in ('running','failed'):
        service=DataService(tmp_path/initial); principal=service.bootstrap()
        with service.store.connect(write=True) as c:
            run=service.create_run(c,principal,{'simulation_days':2,'execution_profile':'external',
                'driver_config':{'agent_version':'native'}})['run_id']
            c.execute("UPDATE runs SET phase='learning' WHERE run_id=?",(run,))
            insert(c,'learning_handoffs',run_id=run,day=1,settlement_cursor=1,status=initial,
                night_summary_json=None,memory_report_asset_id=None,error_code='FAILED' if initial=='failed' else None,
                lease_until=service.expires(60),summary_shop_id='D',created_at=now(),updated_at=now())
        worker=DataWorker(service,Settings(_env_file=None,llm_mode='offline'))
        snap=snapshot(run); worker.store.save_night_snapshot(snap)
        receipt=worker.store.claim_reflection(run,1,snap.snapshot_hash,'owner')
        worker.store.finish_reflection(receipt.model_copy(update={'status':'completed','output':NightReflectionOutput(),'source':'offline'}))
        gate=Barrier(2)
        def publish():
            gate.wait()
            try:
                worker.publish_night(publication(snap),expected_revision=0,expected_cursor=0)
                return 'published'
            except Fault:
                return 'denied'
        def skip():
            gate.wait()
            try:
                with service.store.connect(write=True) as c:
                    service.learning_control(c,principal,run,1,'skip',{'expected_version':1,'reason_vi':'Bỏ qua'})
                return 'skipped'
            except Fault:
                return 'denied'
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(publish),pool.submit(skip)]
            results=[future.result() for future in futures]
        with service.store.connect() as c:
            state=c.execute('SELECT status FROM learning_handoffs WHERE run_id=? AND day=1',(run,)).fetchone()[0]
        assert (results,state,worker.store.get_night_commit(run,1) is not None) in [
            (['published','denied'],'completed',True),(['denied','skipped'],'skipped',False)]


def test_data_replay_context_normalizes_explicit_backend_bindings(tmp_path):
    from langchain_core.messages import HumanMessage
    from app.infrastructure.replay import build_replay_context, request_hash
    from data.growth_data.service import Principal
    service=DataService(tmp_path); seller=service.bootstrap()
    settings=Settings(_env_file=None,llm_mode='offline',demo_shop='D')
    contexts=[]
    for ordinal in range(2):
        with service.store.connect(write=True) as c:
            run=service.create_run(c,seller,{'simulation_days':2,'memory_enabled':False})['run_id']
            c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(run,))
            actor=Principal('orchestrator','orchestrator',None,(run,),('D',))
            runtime=service.entity(c,'shop_runtime',run,'shop_id','D')
            negotiation=service.new_negotiation(c,actor,run,'D',{'day':1,'kind':'propose','expected_shop_version':runtime['version']})['negotiation_id']
        brief={'brief_id':f'brief-{ordinal}','version':1,'shop_id':'D','intent':'increase_orders',
               'goal_vi':'Tăng đơn','allow_ads':True,'ads_daily_cap':None,'content_refresh':True,'duration_days':3,'confirmed':True}
        session=load_data_context(service,settings,run,'D',negotiation_id=negotiation,brief=brief)
        pin=prepare_platform_context(session,'D',1,'propose',negotiation)
        ctx=build_replay_context(session,role='platform',shop_id='D',negotiation_id=negotiation,platform_context=pin,model_id='fake')
        messages=[HumanMessage(content=json.dumps({'brief':brief,'negotiation_id':negotiation}))]
        contexts.append(request_hash(context=ctx,messages=messages,tools=[],tool_choice='auto',parallel_tool_calls=True))
    assert contexts[0]==contexts[1]
