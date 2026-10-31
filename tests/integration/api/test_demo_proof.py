"""The hosted saved proof is scoped, immutable and integrity-checked."""

import copy
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from data.growth_data.demo_proof import DemoProof, _hash


class NoWorker:
    async def start(self): pass
    async def close(self): pass


def example_artifact():
    brief={'intent':'increase_orders','goal_vi':'Tăng đơn','allow_ads':True,'ads_daily_cap':None,
           'content_refresh':True,'duration_days':3,'version':1,'shop_id':'D'}
    refs={'on':{'brief_id':'brief-on','event_seq':1},'off':{'brief_id':'brief-off','event_seq':1}}
    day={'day':1,'request_vi':'Tăng đơn','request_version':1,'request_refs':refs,
         'situation_vi':'Mục tiêu đã xác nhận.','takeaway_vi':'Dữ liệu từ hai run.',
         'on':{'run_id':'run-on','messages':[{'id':'run-on:2','actor':'platform_agent','text_vi':'Đề xuất.','event_seq':2}],
               'memory_used':[],'result_vi':'Đã chốt.'},
         'off':{'run_id':'run-off','messages':[{'id':'run-off:2','actor':'platform_agent','text_vi':'Đề xuất.','event_seq':2}],
                'memory_used':[],'result_vi':'Đã chốt.'}}
    report={'seed':42,'days':1,'shop_id':'D','run_on':'run-on','run_off':'run-off',
            'metrics':[{'key':'seller_profit','label_vi':'Lãi sau phí','better':'higher','unit':'đ','on':100,'off':90}],
            'comparison_days':[day],'source':'precomputed_offline_simulation','execution_profile':'external',
            'note_vi':'Dữ liệu mô phỏng.','status':'ready'}
    evidence={}
    for arm in ('on','off'):
        rid='run-'+arm
        evidence[arm]=[{'run_id':rid,'seq':1,'day':1,'type':'brief_confirmed','actor':'seller','text_vi':'Đã xác nhận.'},
                       {'run_id':rid,'seq':2,'day':1,'type':'platform_turn','actor':'platform_agent','text_vi':'Đề xuất.'}]
    checks={'input_snapshot_sha256':'a'*64,'config_sha256':'b'*64,'report_sha256':_hash(report),
            'on_evidence_sha256':_hash(evidence['on']),'off_evidence_sha256':_hash(evidence['off'])}
    manifest={'comparison_id':'group-one','shop_id':'D','run_on':'run-on','run_off':'run-off','seed':42,'days':1,
        'source':'precomputed_offline_simulation','provider_eval':'not_run','brief':brief,'brief_refs':refs,
        'data_schema_version':4,'simulator_version':'market-v2','source_checksums':checks,
        'input_assets':{'on':{'kind':'simulated_placeholder','sha256':'c'*64},'off':{'kind':'simulated_placeholder','sha256':'c'*64}},
        'source_counts':{'on':{'offline':1},'off':{'offline':1}},'skill_versions':{'on':[],'off':[]}}
    payload={'schema_version':'demo-proof.v1','manifest':manifest,'report':report,'evidence':evidence}
    manifest['artifact_sha256']=_hash(payload)
    return DemoProof.model_validate(payload).model_dump(mode='json')


def seal(payload):
    payload['manifest']['source_checksums']['report_sha256']=_hash(payload['report'])
    for arm in ('on','off'):
        payload['manifest']['source_checksums'][arm+'_evidence_sha256']=_hash(payload['evidence'][arm])
    payload['manifest'].pop('artifact_sha256',None)
    payload['manifest']['artifact_sha256']=_hash(payload)
    return payload


def app_for(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_MODE','offline');monkeypatch.setenv('MEDIA_MODE','offline')
    monkeypatch.setenv('DEMO_PRODUCT_IMAGE_PATH','')
    return create_app(home=tmp_path,worker_factory=lambda service:NoWorker())


def state_snapshot(service):
    with service.store.connect() as c:
        return {table:[tuple(row) for row in c.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()]
                for table in ('runs','events','active_runs','comparison_groups')}


def test_saved_proof_read_does_not_change_current_run(tmp_path,monkeypatch):
    app=app_for(tmp_path,monkeypatch)
    with TestClient(app) as client:
        assert client.get('/api/proof/demo').status_code==401
        assert client.get('/api/state').status_code==200
        before=state_snapshot(app.state.service)
        assert client.get('/api/proof').status_code==409
        missing=client.get('/api/proof/demo')
        assert missing.status_code==404 and missing.json()['error']['code']=='PROOF_NOT_READY'
        artifact=example_artifact()
        (tmp_path/'demo-proof.json').write_text(json.dumps(artifact),encoding='utf-8')
        response=client.get('/api/proof/demo')
        assert response.status_code==200 and response.json()==artifact
        assert response.json()['report']['run_on']=='run-on' and response.json()['manifest']['provider_eval']=='not_run'
        assert state_snapshot(app.state.service)==before
        assert client.get('/api/proof').status_code==409
        token=app.state.service.issue_token('seller',runs=('*',),shops=('E',))
        assert client.get('/api/proof/demo',headers={'Authorization':'Bearer '+token}).status_code==403


def test_saved_proof_rejects_tampering_scope_and_extra_fields(tmp_path,monkeypatch):
    app=app_for(tmp_path,monkeypatch)
    with TestClient(app) as client:
        client.get('/api/state')
        path=tmp_path/'demo-proof.json'
        broken=example_artifact(); broken['report']['metrics'][0]['on']=999
        path.write_text(json.dumps(broken),encoding='utf-8')
        assert client.get('/api/proof/demo').json()['error']['code']=='PROOF_INVALID'
        foreign=example_artifact(); foreign['manifest']['shop_id']='E';foreign['report']['shop_id']='E'
        path.write_text(json.dumps(seal(foreign)),encoding='utf-8')
        assert client.get('/api/proof/demo').status_code==409
        extra=example_artifact();extra['evidence']['on'][0]['raw_private_note']='secret'
        path.write_text(json.dumps(seal(extra)),encoding='utf-8')
        assert client.get('/api/proof/demo').status_code==409
        unsafe=example_artifact();unsafe['evidence']['on'][0]['text_vi']='/Users/example/private-token'
        path.write_text(json.dumps(seal(unsafe)),encoding='utf-8')
        assert client.get('/api/proof/demo').status_code==409


def test_export_real_offline_pair_is_read_only_and_d_scoped(tmp_path,monkeypatch):
    import hashlib
    import sqlite3
    import pytest
    from app.core.settings import Settings
    from app.simulation.runner import run
    from data.growth_data.demo_proof import export_demo_proof
    from data.growth_data.errors import Fault
    from data.growth_data.service import DataService
    monkeypatch.setenv('LLM_MODE','offline');monkeypatch.setenv('MEDIA_MODE','offline')
    monkeypatch.delenv('DEMO_PRODUCT_IMAGE_PATH',raising=False)
    home=tmp_path/'source'
    settings=Settings(_env_file=None,llm_mode='offline',media_mode='offline',demo_shop='D',demo_product_image_path='')
    on=run(settings,1,True,42,home=home)
    with sqlite3.connect(home/'growth.db') as c:
        sid=c.execute('SELECT session_id FROM runs WHERE run_id=?',(on.run_id,)).fetchone()[0]
    off=run(settings,1,False,42,home=home,seller_session_id=sid)
    service=DataService(home,content_mode='worker',learning_mode='external')
    seller=service.authenticate(sid=sid)
    with service.store.connect(write=True) as c:
        from data.growth_data.models import DEMO_D_BRIEF
        for rid in (on.run_id,off.run_id):
            row=service.entity(c,'runs',rid,'run_id',rid)
            assert row['config']['brief_preset']==DEMO_D_BRIEF
            assert {key:row['brief'][key] for key in DEMO_D_BRIEF}==DEMO_D_BRIEF
        group=service.comparison_attach(c,seller,{'run_on':on.run_id,'run_off':off.run_id})['comparison_id']
        service.event(c,on.run_id,1,'content_job','content_worker','D',
            {'feedback_vi':'PRIVATE_SENTINEL sk-12345678901234567890','private_note':'hidden'},
            visibility='shop_private',text='PRIVATE_SENTINEL /Users/example/secret')
        service.event(c,on.run_id,1,'seller_decision','seller','E',{'unit_cost':987654321},
            visibility='shop_private',text='PRIVATE_SENTINEL other shop')
        late_seq=service.event(c,on.run_id,1,'platform_turn','platform_agent','D',{'private_note':'hidden'},
            visibility='shared',text='PRIVATE_SENTINEL sk-12345678901234567890')
    def digest():
        with sqlite3.connect((home/'growth.db').resolve().as_uri()+'?mode=ro',uri=True) as c:
            return hashlib.sha256('\n'.join(c.iterdump()).encode()).hexdigest()
    before=digest()
    artifact=export_demo_proof(home,group)
    assert digest()==before
    assert artifact['manifest']['run_on']==on.run_id and artifact['manifest']['run_off']==off.run_id
    assert artifact['manifest']['source']=='precomputed_offline_simulation'
    assert artifact['manifest']['provider_eval']=='not_run' and artifact['report']['comparison_days']
    serialized=json.dumps(artifact,ensure_ascii=False)
    assert 'PRIVATE_SENTINEL' not in serialized and '987654321' not in serialized and str(home) not in serialized
    assert all(e['run_id']==on.run_id for e in artifact['evidence']['on'])
    assert all(e['seq']!=late_seq for e in artifact['evidence']['on'])
    assert all(m['event_seq']!=late_seq for day in artifact['report']['comparison_days'] for m in day['on']['messages'])
    # Current-session proof must match the active run; exports are bound to both
    # report arms even if another browser tab resets the selected run later.
    from data.growth_data.api import create_app as data_app
    app=data_app(home,bootstrap_defaults={'execution_profile':'external','content_mode':'worker',
        'learning_mode':'external','mode':'offline','driver_config':{'agent_version':'native'}})
    with TestClient(app) as client:
        client.cookies.set('growth_sid',sid)
        current=client.get('/api/state').json()['run_id']
        assert current in {on.run_id,off.run_id}
        report=client.get('/api/proof')
        assert report.status_code==200,report.text
        assert (report.json()['comparison_id'],report.json()['run_on'],report.json()['run_off'])==(group,on.run_id,off.run_id)
        exported=client.get('/api/proof/events',params={'comparison_id':group})
        assert exported.status_code==200,exported.text
        evidence=exported.json()
        assert (evidence['comparison_id'],evidence['run_on'],evidence['run_off'])==(group,on.run_id,off.run_id)
        for arm,rid in (('on',on.run_id),('off',off.run_id)):
            assert isinstance(evidence['cutoffs'][arm],int) and evidence['evidence'][arm]
            assert all(event['run_id']==rid and event['seq']<=evidence['cutoffs'][arm] and event['shop_id'] in (None,'D') for event in evidence['evidence'][arm])
        reset=client.post('/api/reset',json={'memory':True,'seed':42},headers={'Idempotency-Key':'reset','X-Request-ID':'reset'})
        assert reset.status_code==200 and reset.json()['run_id'] not in {on.run_id,off.run_id}
        assert client.get('/api/proof').status_code==409
        assert client.get('/api/proof',params={'comparison_id':group}).status_code==409
        assert client.get('/api/proof/events',params={'comparison_id':group}).json()==evidence
    with TestClient(app) as other:
        assert other.get('/api/proof/events',params={'comparison_id':group}).status_code==401
        other.get('/api/state')
        assert other.get('/api/proof/events',params={'comparison_id':group}).status_code==404
    with service.store.connect(write=True) as c:
        c.execute("UPDATE runs SET demo_shop_id='E' WHERE run_id IN (?,?)",(on.run_id,off.run_id))
    with pytest.raises(Fault) as error:
        export_demo_proof(home,group)
    assert error.value.code=='PROOF_SCOPE_DENIED'


def test_non_demo_shop_simulation_keeps_its_explicit_custom_brief(tmp_path,monkeypatch):
    from app.core.settings import Settings
    from app.simulation.runner import run
    from data.growth_data.service import DataService
    monkeypatch.setenv('LLM_MODE','offline');monkeypatch.setenv('MEDIA_MODE','offline')
    monkeypatch.delenv('DEMO_PRODUCT_IMAGE_PATH',raising=False)
    settings=Settings(_env_file=None,llm_mode='offline',media_mode='offline',demo_shop='E',demo_product_image_path='')
    result=run(settings,1,False,42,home=tmp_path)
    service=DataService(tmp_path)
    with service.store.connect() as c:
        record=service.entity(c,'runs',result.run_id,'run_id',result.run_id)
        assert record['demo_shop_id']=='E' and 'brief_preset' not in record['config']
        assert record['brief']['goal_vi']=='Tăng đơn' and record['brief']['ads_daily_cap'] is None
