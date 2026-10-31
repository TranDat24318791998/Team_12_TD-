"""Real Data lifecycle with native fake transport; no paid providers."""

import asyncio
import io
import json
import shutil
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from PIL import Image

from app.core.settings import Settings
from app.main import create_app
from app.runtime.data_worker import DataWorker
from data.growth_data.api import create_app as data_app
from data.growth_data.models import DEMO_D_BRIEF
from data.growth_data.storage import one
from data.growth_data.errors import Fault
import pytest


def headers(key):
    return {'Idempotency-Key':key,'X-Request-ID':key}


def tool(name,args,ident):
    return {'name':name,'args':args,'id':ident}


class NativeTransport:
    is_fixture=True
    def __init__(self, settings, seen, initial_offer=None):
        self.settings=settings
        self.seen=seen
        self.initial_offer=initial_offer

    def invoke_tools(self, messages, **kwargs):
        name=kwargs['run_name']
        role=next(role for role in ('platform','shop','referee','learning') if f':{role}:' in name)
        returned=[m for m in messages if isinstance(m,ToolMessage)]
        if returned: self.seen.add(role)
        initial=next((m for m in messages if isinstance(m,HumanMessage)),None)
        if role=='platform':
            request=json.loads(initial.content);turns=request['turns']
            package=turns[-1]['package'] if turns and turns[-1]['action']=='counter' else self.initial_offer or {'content_refresh':True,'ads_daily_budget':45000,'voucher_pct':3,'stop_roas_below':6.5,'stop_after_days':2,'duration_days':3}
            if not returned:
                calls=[tool('get_public_context',{},'public'),tool('read_memory',{},'memory'),tool('search_campaign_catalog',{'query':''},'catalog'),tool('validate_platform_package',{'package':package},'validate')]
            elif not any(m.name=='forecast_package' for m in returned): calls=[tool('forecast_package',{'package':package},'forecast')]
            else: calls=[tool('finish_platform',{'action':'accept' if turns and turns[-1]['action']=='counter' else 'propose','package':package,'message_vi':'Đề xuất gói phù hợp.'},'finish')]
        elif role=='shop':
            package=json.loads(initial.content)['proposal']
            if not returned: calls=[tool('get_shop_private_context',{},'private'),tool('read_memory',{},'memory'),tool('evaluate_shop_package',{'package':package},'evaluate')]
            else:
                checked=json.loads(next(m.content for m in returned if m.name=='evaluate_shop_package'))
                corrected=checked['corrected_package']
                action='accept' if checked['ok'] else 'counter' if corrected else 'reject'
                calls=[tool('finish_shop',{'action':action,'package':package if action=='accept' else corrected,'message_vi':'Shop đã kiểm tra gói.','private_note_vi':''},'finish')]
        elif role=='referee':
            if not returned: calls=[tool('get_referee_context',{},'context')]
            else:
                ctx=json.loads(returned[-1].content)
                calls=[tool('finish_referee',{'action':'continue','reason_vi':'Có thể tiếp tục.','evidence_refs':[ctx['turns'][-1]['turn_id']],'unresolved_terms':[],'next_actor':None,'focused_question':None},'finish')]
        else:
            calls=[tool('read_learning_evidence',{},'evidence')] if not returned else [tool('finish_learning',{'ops':[],'proposals':[]},'finish')]
        return AIMessage(content='',tool_calls=calls)


class FakeContent:
    def __init__(self,bridge,settings,llm): self.bridge=bridge
    async def close(self): pass
    async def process_job(self,run_id,job_id):
        snap=self.bridge.snapshot(run_id,job_id)
        self.bridge.heartbeat(run_id,job_id,snap['job']['version'])
        images=[]
        for index,option in enumerate('ABC'):
            buf=io.BytesIO();Image.new('RGB',(8,8),(index*70,40,90)).save(buf,'PNG')
            aid=self.bridge.import_asset(run_id,job_id,data=buf.getvalue(),mime_type='image/png',kind='image')
            images.append({'option':option,'status':'done','asset_id':aid,'source':'fixture'})
        current=self.bridge.snapshot(run_id,job_id)
        self.bridge.complete(run_id,job_id,{'expected_job_version':current['job']['version'],'status':'succeeded','fallback_used':True,
            'content_candidates':{'title':current['content']['title'],'description':current['content']['description'],
                                  'images':images,'video':{'status':'failed','error':'fixture'}}})


def wait_for(client, predicate):
    for _ in range(200):
        state=client.get('/api/state').json()
        if predicate(state): return state
        time.sleep(.05)
    raise AssertionError(state)


def all_events(client,run_id):
    events=[];after=0
    while True:
        response=client.get('/api/events',params={'run_id':run_id,'after':after})
        assert response.status_code==200,response.text
        page=response.json();events.extend(page['events'])
        if not page['has_more']:return events
        assert page['last_seq']>after
        after=page['last_seq']


def render_activity(tmp_path,state,events):
    root=Path(__file__).resolve().parents[3]
    node=shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
    if not Path(node).is_file() or not (root/'frontend/node_modules/esbuild').exists():
        pytest.skip('Node and frontend dependencies are required for the cross-boundary React check')
    source="""import {renderToStaticMarkup} from 'react-dom/server';
import {AgentActivity} from './src/components/AgentActivity.jsx';
import {deriveActivity} from './src/activity.js';
const {state,events}=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const activity=deriveActivity(state,events);
console.log(JSON.stringify({check:activity.check,match:activity.checkMatchesLatest,
  referee:activity.referee,html:renderToStaticMarkup(<AgentActivity state={state} events={events} preview={false}/>)}));"""
    builder="""const fs=require('node:fs'), path=require('node:path');
require(path.join(process.cwd(),'frontend/node_modules/esbuild')).buildSync({
  stdin:{contents:fs.readFileSync(0,'utf8'),resolveDir:path.join(process.cwd(),'frontend'),loader:'jsx'},
  bundle:true,platform:'node',format:'esm',jsx:'automatic',outfile:process.argv[1],logLevel:'silent',
  banner:{js:"import {createRequire} from 'node:module';const require=createRequire(import.meta.url);"}});"""
    bundle=tmp_path/'activity.mjs'
    subprocess.run([node,'-e',builder,str(bundle)],input=source,text=True,cwd=root,check=True,capture_output=True)
    result=subprocess.run([node,str(bundle)],input=json.dumps({'state':state,'events':events},ensure_ascii=False),
                          text=True,cwd=root,check=True,capture_output=True)
    return json.loads(result.stdout)


def test_composed_native_lifecycle_and_asset_gate(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_MODE','offline');monkeypatch.setenv('MEDIA_MODE','offline')
    seen=set()
    settings=Settings(_env_file=None,llm_mode='offline',media_mode='offline')
    initial={'content_refresh':True,'ads_daily_budget':45000,'voucher_pct':10,'stop_roas_below':4.0,'stop_after_days':2,'duration_days':3}
    app=create_app(home=tmp_path,bootstrap_defaults={'simulation_days':1},worker_factory=lambda service:DataWorker(service,settings,
        llm_factory=lambda run,settings,store:NativeTransport(settings,seen,initial),content_factory=FakeContent))
    with TestClient(app) as client:
        assert client.get('/ready').json()['worker']=='ready'
        first=client.get('/api/state').json()
        reset=client.post('/api/reset',json={'memory':True,'seed':42},headers=headers('reset'))
        assert reset.status_code==200
        run=reset.json()['run_id'];assert run!=first['run_id']
        assert client.post('/api/day/start',json={},headers=headers('premature')).json()['error']['code']=='BRIEF_REQUIRED'
        brief=DEMO_D_BRIEF.copy()
        assert client.post('/api/brief/confirm',json={**brief,'allow_ads':1},headers=headers('bad-brief')).status_code==422
        assert client.post('/api/brief/confirm',json=brief,headers={'Idempotency-Key':'no-request-id'}).status_code==400
        assert client.post('/api/brief/confirm',json=brief,headers=headers('brief')).status_code==200
        started=client.post('/api/day/start',json={},headers=headers('start'))
        assert started.status_code==202 and started.json()['operation_id']
        state=wait_for(client,lambda s:not s['busy'] and s['pending_card'] is not None)
        card=state['pending_card']
        assert card['package']['voucher_pct']==3 and card['profit_after_fees_per_unit']==27136
        events=all_events(client,run)
        checks=[e for e in events if e['type']=='code_check' and e['shop_id']=='D' and e['data'].get('negotiation_id')==card['negotiation_id']]
        failed=next(e for e in checks if e['data']['ok'] is False)
        assert checks[-1]['data']['ok'] is True and checks[-1]['data']['proposal_id']==card['proposal_id']
        assert isinstance(checks[-1]['data']['round'],int) and isinstance(checks[-1]['data']['checks'],list)
        rendered=render_activity(tmp_path,state,events)
        assert rendered['match'] and rendered['check']['data']['ok'] is True and 'Gói đã qua kiểm tra' in rendered['html']
        rejected=render_activity(tmp_path,state,[e for e in events if e['seq']<=failed['seq']])
        assert rejected['match'] and rejected['check']['data']['ok'] is False and 'Có ràng buộc chưa đạt' in rejected['html']
        stale={'card_id':card['card_id'],'expected_card_version':card['version']+1,'expected_brief_version':card['brief_version'],'action':'accept'}
        assert client.post('/api/decision',json=stale,headers=headers('stale')).status_code==409
        stale['expected_card_version']=card['version']
        assert client.post('/api/decision',json=stale,headers=headers('accept')).status_code==200
        state=wait_for(client,lambda s:s['content_draft'] and s['content_draft']['status']=='succeeded')
        draft=state['content_draft']
        binding={'card_id':draft['card_id'],'expected_brief_version':draft['brief_version'],'expected_draft_version':draft['version'],
                 'expected_job_id':draft['job_id'],'expected_content_id':draft['content_id']}
        retry=client.post('/api/content/retry',json={**binding,'feedback_vi':'Ảnh nền sáng hơn','retry_scope':'all'},headers=headers('retry'))
        assert retry.status_code==200 and retry.json()['draft']['version']==2
        state=wait_for(client,lambda s:s['content_draft'] and s['content_draft']['version']==2 and s['content_draft']['status']=='succeeded')
        draft=state['content_draft']
        binding.update(expected_draft_version=2,expected_job_id=draft['job_id'],expected_content_id=draft['content_id'])
        with app.state.service.store.connect() as c:
            content=app.state.service.entity(c,'content_versions',run,'content_id',draft['content_id'])
            asset=app.state.service.entity(c,'assets',run,'asset_id',content['cover_options'][1]['asset_id'])
            path=app.state.service.object_path(asset['object_key']);raw=path.read_bytes()
        path.unlink()
        body={**binding,'cover_option':'B','skip_video':True,'video_review_ack':False}
        denied=client.post('/api/content/apply',json=body,headers=headers('missing'))
        assert denied.status_code==422 and denied.json()['error']['code']=='ASSET_INVALID'
        with app.state.service.store.connect() as c:
            assert not one(c,"SELECT campaign_id FROM campaigns WHERE run_id=? AND shop_id='D'",(run,))
        path.write_bytes(raw)
        applied=client.post('/api/content/apply',json=body,headers=headers('apply'))
        assert applied.status_code==200
        assert client.post('/api/content/apply',json=body,headers=headers('apply')).json()==applied.json()
        assert client.post('/api/content/apply',json={**body,'cover_option':'C'},headers=headers('apply')).status_code==409
        night=client.post('/api/night',json={'expected_day':1},headers=headers('night'))
        assert night.status_code in (200,202)
        state=wait_for(client,lambda s:s['step']=='complete' or s['learning_status']=='failed')
        assert state['step']=='complete' and state['day']==1
        summary=state['last_night']
        assert summary['history_updates'] and summary['history_refs'] and summary['source'] in {'offline','fixture'}
        assert summary['pref_candidates'] and summary['preference_refs']
        assert 'ảnh nền sáng' in ' '.join(summary['pref_candidates']).casefold()
        assert all(ref['record_id'] not in text for ref,text in zip(summary['history_refs'],summary['history_updates']))
        assert all(ref['evidence_seqs'] for ref in summary['history_refs']+summary['preference_refs'])
        assert {'platform','shop','referee','learning'}<=seen
        with app.state.service.store.connect() as c:
            assert c.execute('SELECT COUNT(*) FROM daily_predictions WHERE run_id=?',(run,)).fetchone()[0]==5
            assert c.execute('SELECT COUNT(*) FROM night_commits WHERE run_id=?',(run,)).fetchone()[0]==1
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert client.get('/api/events?after=-1').status_code==422
        assert client.get('/api/events?run_id='+first['run_id']).json()['error']['code']=='RUN_CHANGED'
        assert client.get('/api/unknown').status_code==404
        schema=client.get('/openapi.json').json()
        assert schema['paths']['/api/brief/confirm']['post']['requestBody']['required']
    reopened=create_app(home=tmp_path,worker_factory=lambda service:DataWorker(service,settings))
    with TestClient(reopened) as client:
        # A new browser session is separate; the old run remains durable.
        with reopened.state.service.store.connect() as c:
            assert one(c,'SELECT phase FROM runs WHERE run_id=?',(run,))['phase']=='complete'
            assert one(c,'SELECT run_id FROM night_commits WHERE run_id=?',(run,))


def test_queued_operation_blocks_night_without_settlement(tmp_path):
    defaults={'execution_profile':'external','content_mode':'worker','learning_mode':'external','driver_config':{'agent_version':'native'}}
    app=data_app(tmp_path,bootstrap_defaults=defaults)
    with TestClient(app) as client:
        run=client.get('/api/state').json()['run_id']
        brief=DEMO_D_BRIEF.copy()
        assert client.post('/api/brief/confirm',json=brief,headers=headers('brief')).status_code==200
        assert client.post('/api/day/start',json={},headers=headers('start')).status_code==202
        result=client.post('/api/night',json={'expected_day':1},headers=headers('night'))
        assert result.status_code==409 and result.json()['error']['code']=='OPERATION_PENDING'
        with app.state.service.store.connect() as c:
            assert not one(c,'SELECT settlement_id FROM day_settlements WHERE run_id=?',(run,))


def test_upgrade_v2_preserves_linked_business_rows(tmp_path,monkeypatch):
    from pathlib import Path
    from data.growth_data.seed import seed_run, seed_shared
    from data.growth_data.storage import Store, dumps, insert, now, timestamps
    migrations=Path(__file__).resolve().parents[3]/'data/growth_data/migrations'
    old=tmp_path/'v2_migrations';old.mkdir()
    for path in sorted(migrations.glob('00[12]_*.sql')): shutil.copy(path,old/path.name)
    db=tmp_path/'growth.db';objects=tmp_path/'objects'
    with monkeypatch.context() as patch:
        patch.setattr(Store,'migrations_path',old)
        store=Store(db)
        with store.connect(write=True) as c:
            c.execute("INSERT INTO sessions VALUES('session-old',?)",(now(),))
            insert(c,'runs',run_id='run_old',session_id='session-old',scenario_version='demo-v1',schema_version=2,
                   simulator_version='market-v2',seed=42,mode='offline',memory_enabled=True,history_days=14,simulation_days=7,
                   start_date='2026-11-01',current_day=1,phase='negotiating',source_run_id=None,execution_profile='external',
                   content_mode='worker',learning_mode='external',initial_snapshot_hash='old',config_json={},created_by='seller',**timestamps())
            insert(c,'run_grants',run_id='run_old',principal_id='seller')
            insert(c,'active_runs',session_id='session-old',run_id='run_old')
            seed_shared(c,objects);seed_run(c,'run_old',objects,42)
            c.execute("INSERT INTO negotiations(run_id,negotiation_id,shop_id,day,kind,attempt,platform_rounds,status,final_proposal_id,warning_vi,owner_note_vi,expected_next_role,created_at,updated_at) VALUES('run_old','neg_old','D',1,'propose',1,1,'agreed','prop_old',NULL,NULL,'shop_agent',?,?)",(now(),now()))
            package={'content_refresh':False,'ads_daily_budget':0,'voucher_pct':3,'stop_roas_below':None,'stop_after_days':2,'duration_days':3}
            insert(c,'proposals',run_id='run_old',proposal_id='prop_old',negotiation_id='neg_old',shop_id='D',product_id='SP004',parent_proposal_id=None,proposal_version=1,author_role='platform_agent',round=1,package_json=package,forecast_id=None,shared_reason='',stance='accept',status='applied',based_on_rules_version=1,**timestamps())
            insert(c,'decisions',run_id='run_old',decision_id='decision_old',shop_id='D',target_type='proposal',target_id='prop_old',target_version=1,action='approve',edited_package_json=None,cover_option=None,rule_answer=None,actor_type='seller',actor_id='seller',feedback_private=None,feedback_shared='',created_at=now())
            insert(c,'campaigns',run_id='run_old',campaign_id='campaign_old',shop_id='D',product_id='SP004',proposal_id='prop_old',approval_decision_id='decision_old',package_snapshot_json=package,start_day=1,end_day=3,approved_total_vnd=0,spent_vnd=0,low_roas_streak=0,status='active',ads_status='disabled',ads_stop_reason=None,**timestamps())
            before={name:c.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ('runs','shops','products','assets','daily_metrics','negotiations','proposals','decisions','campaigns','run_grants')}
    upgraded=Store(db)
    with upgraded.connect() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==4
        assert {name:c.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in before}==before
        assert one(c,"SELECT * FROM campaigns WHERE campaign_id='campaign_old'")['approval_decision_id']=='decision_old'
        assert one(c,"SELECT * FROM runs WHERE run_id='run_old'")['demo_shop_id']=='D'
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_durable_calibration_and_voucher_cap_are_scoped(tmp_path):
    from app.domain.models.learning import Calibration, CalibrationRecord, CalibrationSample
    from data.growth_data.service import Principal
    from data.growth_data.errors import Fault
    import pytest
    app=data_app(tmp_path)
    worker=DataWorker(app.state.service,Settings(_env_file=None,llm_mode='offline'))
    with TestClient(app) as client:
        run=client.get('/api/state').json()['run_id']
        samples=[CalibrationSample(sample_id=f's{i}',prediction_id=f'p{i}',shop_id='D',target_day=i,
                    raw_point=1.0,actual_orders=0,ratio=0.0,evidence_seqs=[i]) for i in range(1,6)]
        record=CalibrationRecord(category='quat_mini',value=Calibration(category='quat_mini',ratios=[0.0]*5,factor=0.0,q_low=0.0,q_high=0.0),samples=samples,version=1)
        worker.store.put((run,'calibration','quat_mini'),'quat_mini',record)
        package={'content_refresh':True,'ads_daily_budget':0,'voucher_pct':0,'stop_roas_below':None,'stop_after_days':2,'duration_days':3}
        with app.state.service.store.connect(write=True) as c:
            forecast=app.state.service.forecast_values(c,run,'D',package,6)
            assert forecast['factor_used']==0 and forecast['point']==0
            assert app.state.service.forecast_values(c,run,'D',package,5)['factor_used']==1
            principal=Principal('learner','learning_worker',None,(run,),('D',))
            with pytest.raises(Fault) as error:
                app.state.service.question(c,principal,run,'D',{'external_pref_id':'raise','field':'voucher_max_pct','value':'30','text_vi':'Tăng voucher?','based_on_rules_version':1})
            assert error.value.code=='RULE_INCREASE'


def test_learning_projection_discards_private_feedback(tmp_path):
    from app.infrastructure.data_agents import load_data_context
    app=data_app(tmp_path)
    with TestClient(app) as client:
        run=client.get('/api/state').json()['run_id']
        body={'intent':'increase_orders','goal_vi':'Tăng đơn','allow_ads':True,'ads_daily_cap':None,'content_refresh':True,'duration_days':3}
        assert client.post('/api/brief/confirm',json=body,headers=headers('brief')).status_code==200
        service=app.state.service
        with service.store.connect(write=True) as c:
            service.event(c,run,1,'content_job','content_worker','D',{'feedback_vi':'Giá vốn 115.000đ của chị Lan'},visibility='shop_private',text='Giá vốn của chị Lan')
        context=load_data_context(service,Settings(_env_file=None,llm_mode='offline'),run,'D')
        evidence=context.memory.source.events()
        assert evidence and 'feedback_vi' not in evidence[-1].data
        assert 'giá vốn' not in evidence[-1].text_vi.casefold() and '115' not in evidence[-1].text_vi


def test_referee_focus_reaches_real_http_and_react_without_private_details(tmp_path,monkeypatch):
    import app.negotiation.graph as graph
    from app.domain.models.negotiation import RefereeDecision
    def referee(brief,turns,**kwargs):
        first=len(turns)==1
        return RefereeDecision(action='refocus' if first else 'continue',reason_vi='Tập trung vào mục tiêu.',
            evidence_refs=[turns[-1].turn_id],unresolved_terms=['Ngân sách quảng cáo','Giá vốn 115.000đ của chị Lan'],
            next_actor='shop' if first else None,
            focused_question='Ngân sách quảng cáo nào cần làm rõ?' if first else 'Giá vốn 115.000đ của chị Lan?')
    monkeypatch.setattr(graph,'review_turn',referee)
    settings=Settings(_env_file=None,llm_mode='offline',media_mode='offline')
    app=create_app(home=tmp_path,worker_factory=lambda service:DataWorker(service,settings,
        llm_factory=lambda run,settings,store:NativeTransport(settings,set()),content_factory=FakeContent))
    with TestClient(app) as client:
        run=client.get('/api/state').json()['run_id']
        brief=DEMO_D_BRIEF.copy()
        assert client.post('/api/brief/confirm',json=brief,headers=headers('brief')).status_code==200
        assert client.post('/api/day/start',json={},headers=headers('start')).status_code==202
        state=wait_for(client,lambda s:not s['busy'] and s['pending_card'] is not None)
        events=all_events(client,run)
        reviews=[e for e in events if e['type']=='referee_review' and e['shop_id']=='D']
        first=reviews[0]['data']
        assert first['action']=='refocus' and first['round']==1 and first['next_actor']=='shop_agent'
        assert first['focused_question']=='Ngân sách quảng cáo nào cần làm rõ?'
        assert first['unresolved_terms']==['Ngân sách quảng cáo'] and all(isinstance(seq,int) for seq in first['evidence_refs'])
        assert all('115.000' not in json.dumps(e,ensure_ascii=False) and 'chị Lan' not in json.dumps(e,ensure_ascii=False) for e in reviews)
        rendered=render_activity(tmp_path,state,[e for e in events if e['seq']<=reviews[0]['seq']])
        assert rendered['referee']['data']['focused_question']==first['focused_question']
        assert first['focused_question'] in rendered['html']


def test_brief_gate_covers_both_start_routes_and_reset_replay(tmp_path):
    defaults={'execution_profile':'external','content_mode':'worker','learning_mode':'external','driver_config':{'agent_version':'native'}}
    app=data_app(tmp_path,bootstrap_defaults=defaults)
    brief=DEMO_D_BRIEF.copy()
    with TestClient(app) as client:
        for route in ('legacy','versioned'):
            created=client.post('/api/reset',json={'seed':42,'memory':True},headers=headers('reset-'+route)).json()
            run=created['run_id']
            legacy=client.post('/api/day/start',json={},headers=headers('no-brief-legacy-'+route))
            versioned=client.post(f'/api/v1/runs/{run}/days/start',json={'expected_day':1,'expected_version':1},headers=headers('no-brief-v1-'+route))
            assert legacy.status_code==versioned.status_code==409
            assert legacy.json()['error']['code']==versioned.json()['error']['code']=='BRIEF_REQUIRED'
            with app.state.service.store.connect() as c:
                assert not one(c,'SELECT operation_id FROM operations WHERE run_id=?',(run,))
                assert not one(c,"SELECT seq FROM events WHERE run_id=? AND type='day_start'",(run,))
                assert one(c,'SELECT phase FROM runs WHERE run_id=?',(run,))['phase']=='ready'
            assert client.post('/api/brief/confirm',json=brief,headers=headers('brief-'+route)).status_code==200
            url='/api/day/start' if route=='legacy' else f'/api/v1/runs/{run}/days/start'
            body={} if route=='legacy' else {'expected_day':1,'expected_version':2}
            assert client.post(url,json=body,headers=headers('started-'+route)).status_code==202
        before=client.post('/api/reset',json={'seed':42,'memory':True},headers=headers('reset-a'))
        after=client.post('/api/reset',json={'seed':43,'memory':False},headers=headers('reset-b'))
        replay=client.post('/api/reset',json={'seed':42,'memory':True},headers=headers('reset-a'))
        assert replay.json()==before.json()
        assert client.get('/api/state').json()['run_id']==after.json()['run_id']
        assert client.post('/api/reset',json={'seed':44,'memory':True},headers=headers('reset-a')).status_code==409
        with app.state.service.store.connect() as c:
            assert c.execute('SELECT COUNT(*) FROM runs WHERE run_id IN (?,?)',(before.json()['run_id'],after.json()['run_id'])).fetchone()[0]==2


def test_demo_preset_is_locked_unconfirmed_and_preserves_existing_briefs(tmp_path):
    defaults={'execution_profile':'external','content_mode':'worker','learning_mode':'external','driver_config':{'agent_version':'native'}}
    app=data_app(tmp_path,bootstrap_defaults=defaults)
    with TestClient(app) as client:
        state=client.get('/api/state').json();run=state['run_id']
        assert state['brief'] is None and state['brief_preset']==DEMO_D_BRIEF and state['brief_editable'] is False
        with app.state.service.store.connect(write=True) as c:
            record=app.state.service.entity(c,'runs',run,'run_id',run)
            assert record['brief'] is None and record['config']['brief_preset']==DEMO_D_BRIEF
            # Older idle native runs did not yet store the new config field.
            c.execute("UPDATE runs SET config_json=json_remove(config_json,'$.brief_preset') WHERE run_id=?",(run,))
        assert client.get('/api/state').json()['brief_preset']==DEMO_D_BRIEF
        assert client.post('/api/day/start',json={},headers=headers('no-confirm')).json()['error']['code']=='BRIEF_REQUIRED'
        for key,body in (('budget',{**DEMO_D_BRIEF,'ads_daily_cap':50000}),
                         ('goal',{**DEMO_D_BRIEF,'goal_vi':'Đạt 30 đơn trong 3 ngày'})):
            response=client.post('/api/brief/confirm',json=body,headers=headers('tamper-'+key))
            assert response.status_code==422 and response.json()['error']['code']=='BRIEF_PRESET_MISMATCH'
        assert client.get('/api/state').json()['brief'] is None
        accepted=client.post('/api/brief/confirm',json=DEMO_D_BRIEF,headers=headers('confirm'))
        assert accepted.status_code==200 and accepted.json()['brief']['confirmed']
        assert {key:accepted.json()['brief'][key] for key in DEMO_D_BRIEF}==DEMO_D_BRIEF
        assert client.post('/api/brief/confirm',json=DEMO_D_BRIEF,headers=headers('confirm')).json()==accepted.json()
        assert client.post('/api/brief/confirm',json=DEMO_D_BRIEF,headers=headers('confirm-again')).json()['error']['code']=='BRIEF_ALREADY_CONFIRMED'
        with app.state.service.store.connect(write=True) as c:
            legacy={**accepted.json()['brief'],'goal_vi':'Mục tiêu cũ đã xác nhận','ads_daily_cap':None}
            c.execute('UPDATE runs SET brief_json=? WHERE run_id=?',(json.dumps(legacy,ensure_ascii=False),run))
        assert client.get('/api/state').json()['brief']==legacy
        assert client.post('/api/brief/confirm',json=DEMO_D_BRIEF,headers=headers('do-not-replace')).json()['error']['code']=='BRIEF_ALREADY_CONFIRMED'
        assert client.get('/api/state').json()['brief']==legacy


def test_edited_approval_binds_original_card_through_content_apply(tmp_path):
    from app.infrastructure.data_content import DataContentBridge
    from data.growth_data.service import Principal
    defaults={'execution_profile':'external','content_mode':'worker','learning_mode':'external','driver_config':{'agent_version':'native'}}
    app=data_app(tmp_path,bootstrap_defaults=defaults)
    service=app.state.service
    settings=Settings(_env_file=None,llm_mode='offline',media_mode='offline',max_live_calls_per_session=7)
    seen=set()
    worker=DataWorker(service,settings,llm_factory=lambda run,settings,store:NativeTransport(settings,seen))
    with TestClient(app) as client:
        run=client.get('/api/state').json()['run_id']
        brief=DEMO_D_BRIEF.copy()
        assert client.post('/api/brief/confirm',json=brief,headers=headers('brief')).status_code==200
        assert client.post('/api/day/start',json={},headers=headers('start')).status_code==202
        with service.store.connect() as c:op=one(c,"SELECT * FROM operations WHERE run_id=? AND kind='start_day'",(run,))
        worker._operation(op)
        card=client.get('/api/state').json()['pending_card']
        assert card and card['package']['voucher_pct']==3
        edit={'card_id':card['card_id'],'expected_card_version':card['version'],'expected_brief_version':card['brief_version'],'action':'edit','edited_package':{**card['package'],'voucher_pct':2}}
        response=client.post('/api/decision',json=edit,headers=headers('edit'))
        assert response.status_code==200,response.text
        with service.store.connect() as c:
            job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D'",(run,))
            children=c.execute('SELECT COUNT(*) FROM proposals WHERE run_id=? AND parent_proposal_id=? AND status=?',(run,card['proposal_id'],'accepted')).fetchone()[0]
            approvals=c.execute("SELECT COUNT(*) FROM decisions WHERE run_id=? AND target_type='proposal' AND target_id=? AND action='approve'",(run,job['proposal_id'])).fetchone()[0]
            assert children==approvals==1
        bridge=DataContentBridge(service);snap=bridge.snapshot(run,job['job_id'])
        assert snap['proposal']['parent_proposal_id']==card['proposal_id']
        assert snap['approval']['target_id']==job['proposal_id'] and snap['card']['card_id']==card['card_id']
        assert client.get('/api/state').json()['content_draft']['card_id']==card['card_id']
        # A different negotiation's otherwise resolved card is never accepted as this approval.
        with service.store.connect(write=True) as c:
            neg=service.entity(c,'negotiations',run,'negotiation_id',snap['proposal']['negotiation_id'])
            parent=service.entity(c,'proposals',run,'proposal_id',card['proposal_id'])
            service.persist_copy(c,'negotiations',neg,negotiation_id='neg_decoy',attempt=2,final_proposal_id=None,status='failed')
            service.persist_copy(c,'proposals',parent,proposal_id='prop_decoy',negotiation_id='neg_decoy',parent_proposal_id=None)
            service.persist_copy(c,'cards',snap['card'],card_id='card_decoy',proposal_id='prop_decoy')
            c.execute("UPDATE events SET payload_json=json_set(payload_json,'$.card_id','card_decoy') WHERE run_id=? AND type='seller_decision' AND json_extract(payload_json,'$.decision_id')=?",(run,snap['approval']['decision_id']))
        with pytest.raises(Fault) as error:bridge.snapshot(run,job['job_id'])
        assert error.value.code=='APPROVAL_REQUIRED'
        with service.store.connect(write=True) as c:
            foreign_card=one(c,"SELECT card_id FROM cards WHERE run_id=? AND shop_id!='D' AND status='resolved' LIMIT 1",(run,))
            assert foreign_card
            c.execute("UPDATE events SET payload_json=json_set(payload_json,'$.card_id',?) WHERE run_id=? AND type='seller_decision' AND json_extract(payload_json,'$.decision_id')=?",(foreign_card['card_id'],run,snap['approval']['decision_id']))
        with pytest.raises(Fault) as error:bridge.snapshot(run,job['job_id'])
        assert error.value.code=='APPROVAL_REQUIRED'
        with service.store.connect(write=True) as c:
            other=service.create_run(c,Principal('other','orchestrator',None,('*',),('*',)),{},select=False)['run_id']
            c.execute("UPDATE events SET payload_json=json_set(payload_json,'$.card_id',?) WHERE run_id=? AND type='seller_decision' AND json_extract(payload_json,'$.decision_id')=?",(card['card_id'],run,snap['approval']['decision_id']))
            c.execute('INSERT INTO llm_call_reservations VALUES(?,?,?)',(run,'reserved-test','2026-01-01'))
        with pytest.raises(Fault) as error:bridge.snapshot(other,job['job_id'])
        assert error.value.code=='NOT_FOUND'
        asyncio.run(FakeContent(bridge,settings,None).process_job(run,job['job_id']))
        draft=client.get('/api/state').json()['content_draft']
        body={'card_id':card['card_id'],'expected_brief_version':draft['brief_version'],'expected_draft_version':draft['version'],'expected_job_id':draft['job_id'],'expected_content_id':draft['content_id'],'cover_option':'A','skip_video':True,'video_review_ack':False}
        response=client.post('/api/content/apply',json=body,headers=headers('apply'))
        assert response.status_code==200,response.text
        assert client.post('/api/content/apply',json=body,headers=headers('apply')).json()==response.json()
        state=client.get('/api/state').json()
        assert state['active_package']['card_id']==card['card_id'] and state['active_package']['package']['voucher_pct']==2
        assert state['live_calls_left']==6
        with service.store.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM campaigns WHERE run_id=? AND shop_id='D'",(run,)).fetchone()[0]==1


def test_expired_native_operation_recovered_on_actual_startup_and_can_close(tmp_path,monkeypatch):
    from data.growth_data.service import Principal
    defaults={'execution_profile':'external','content_mode':'worker','learning_mode':'external','driver_config':{'agent_version':'native'}}
    app=data_app(tmp_path,bootstrap_defaults=defaults);service=app.state.service
    with TestClient(app) as client:
        run=client.post('/api/reset',json={'seed':42,'memory':False},headers=headers('reset')).json()['run_id']
        brief=DEMO_D_BRIEF.copy()
        assert client.post('/api/brief/confirm',json=brief,headers=headers('brief')).status_code==200
        queued=client.post('/api/day/start',json={},headers=headers('start')).json()
        principal=Principal('native_orchestrator','orchestrator',None,(run,),('*',))
        with service.store.connect(write=True) as c:
            op=service.entity(c,'operations',run,'operation_id',queued['operation_id'])
            op=service.operation_claim(c,principal,run,op['operation_id'],{'expected_version':op['version']})
            runtime=service.entity(c,'shop_runtime',run,'shop_id','D')
        body={'day':1,'kind':'propose','expected_shop_version':runtime['version'],'source_card_id':None,'owner_note_vi':None}
        neg=service.command(principal,run,'native/negotiation',f"{op['operation_id']}:D",body,lambda c:service.new_negotiation(c,principal,run,'D',body))
        with service.store.connect(write=True) as c:
            c.execute("UPDATE operations SET lease_until='2000-01-01' WHERE run_id=? AND operation_id=?",(run,op['operation_id']))
        sid=client.cookies.get('growth_sid')
    settings=Settings(_env_file=None,llm_mode='offline',media_mode='offline')
    monkeypatch.setattr('app.core.settings.Settings',lambda:settings)
    reopened=create_app(home=tmp_path,worker_factory=lambda service:DataWorker(service,settings))
    with TestClient(reopened) as client:
        client.cookies.set('growth_sid',sid)
        state=client.get('/api/state').json()
        assert state['active_operation']['status']=='failed' and state['active_operation']['error_code']=='LEASE_EXPIRED_RESULT_UNKNOWN'
        with reopened.state.service.store.connect() as c:
            recovered=one(c,'SELECT * FROM negotiations WHERE run_id=? AND negotiation_id=?',(run,neg['negotiation_id']))
            assert recovered['status']=='failed' and recovered['terminal_receipt']['status']=='failed'
            event=one(c,"SELECT * FROM events WHERE run_id=? AND type='negotiation_finished' AND json_extract(payload_json,'$.negotiation_id')=?",(run,neg['negotiation_id']))
            assert event['payload']['source']=='unknown'
            assert not one(c,'SELECT call_id FROM llm_call_reservations WHERE run_id=?',(run,))
        night=client.post('/api/night',json={'expected_day':1},headers=headers('night'))
        assert night.status_code==200,night.text
        assert night.json()['next_day']==2


def test_pending_renegotiation_and_failed_night_are_truthful(tmp_path):
    defaults={'execution_profile':'external','content_mode':'worker','learning_mode':'external','driver_config':{'agent_version':'native'}}
    app=data_app(tmp_path,bootstrap_defaults=defaults);service=app.state.service
    settings=Settings(_env_file=None,llm_mode='offline',media_mode='offline')
    worker=DataWorker(service,settings,llm_factory=lambda run,settings,store:NativeTransport(settings,set()))
    with TestClient(app) as client:
        run=client.get('/api/state').json()['run_id']
        brief=DEMO_D_BRIEF.copy()
        assert client.post('/api/brief/confirm',json=brief,headers=headers('brief')).status_code==200
        client.post('/api/day/start',json={},headers=headers('start'))
        with service.store.connect() as c:op=one(c,"SELECT * FROM operations WHERE run_id=? AND kind='start_day'",(run,))
        worker._operation(op)
        card=client.get('/api/state').json()['pending_card']
        decision={'card_id':card['card_id'],'expected_card_version':card['version'],'expected_brief_version':card['brief_version'],'action':'negotiate','note_vi':'Đề xuất khác'}
        result=client.post('/api/decision',json=decision,headers=headers('renegotiate'))
        assert result.status_code==202
        state=client.get('/api/state').json()
        assert state['busy'] and state['step']=='negotiating' and state['active_operation']['kind'].startswith('renegotiate:')
        # Terminal failure is visible on replay and does not create another night operation.
        with service.store.connect(write=True) as c:
            c.execute("UPDATE operations SET status='failed',error_code='TEST_TERMINAL' WHERE run_id=? AND operation_id=?",(run,result.json()['operation_id']))
            c.execute("UPDATE content_jobs SET status='failed' WHERE run_id=? AND shop_id!='D'",(run,))
            c.execute("UPDATE content_versions SET status='rejected' WHERE run_id=? AND status IN ('draft','validated')",(run,))
            c.execute("UPDATE proposals SET status='rejected' WHERE run_id=? AND status='accepted'",(run,))
            old_job=one(c,"SELECT job_id FROM content_jobs WHERE run_id=? AND shop_id!='D' LIMIT 1",(run,))
            assert old_job
            c.execute("UPDATE content_jobs SET provider_state_json=? WHERE run_id=? AND job_id=?",(json.dumps({'A':{'status':'unknown'}}),run,old_job['job_id']))
        blocked=client.post('/api/night',json={'expected_day':1},headers=headers('unknown-night'))
        assert blocked.status_code==409 and blocked.json()['error']['code']=='PROVIDER_OUTCOME_UNKNOWN'
        with service.store.connect(write=True) as c:
            c.execute("UPDATE content_jobs SET provider_state_json='{}' WHERE run_id=? AND job_id=?",(run,old_job['job_id']))
        pending=client.post('/api/night',json={'expected_day':1},headers=headers('night'))
        assert pending.status_code==202,pending.text
        night_id=pending.json()['operation_id']
        with service.store.connect(write=True) as c:
            c.execute("UPDATE learning_handoffs SET status='failed',error_code='LEARNING_TIMEOUT' WHERE run_id=? AND day=1",(run,))
            service.finish_night_tx(c,run,1)
        failed=client.post('/api/night',json={'expected_day':1},headers=headers('night'))
        assert failed.status_code==409 and failed.json()['operation_id']==night_id
        assert failed.json()['status']=='failed' and failed.json()['error']['code']=='LEARNING_TIMEOUT'
        retryable=client.get('/api/state').json()
        assert retryable['learning_status']=='failed' and retryable['learning_retry_allowed'] is True
        url=f'/api/v1/runs/{run}/days/1/learning/retry'
        retried=client.post(url,json={'expected_version':retryable['learning_version'],'reason_vi':'Thử lại'},headers=headers('learning-retry'))
        assert retried.status_code==200,retried.text
        with service.store.connect(write=True) as c:
            c.execute("UPDATE learning_handoffs SET status='failed',error_code='UNKNOWN' WHERE run_id=? AND day=1",(run,))
            c.execute("INSERT INTO night_snapshots(run_id,day,shop_id,snapshot_hash,payload_json) VALUES(?,1,'D','fixture','{}')",(run,))
            c.execute("INSERT INTO reflection_receipts(run_id,day,snapshot_hash,owner_token,status,payload_json) VALUES(?,1,'fixture','owner','unknown','{}')",(run,))
        blocked=client.get('/api/state').json()
        assert blocked['learning_status']=='failed' and blocked['learning_retry_allowed'] is False
        response=client.post(url,json={'expected_version':blocked['learning_version'],'reason_vi':'Thử lại'},headers=headers('learning-unknown'))
        assert response.status_code==409 and response.json()['error']['code']=='REFLECTION_UNKNOWN'
        with service.store.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM operations WHERE run_id=? AND kind='night'",(run,)).fetchone()[0]==1
