"""Real Data and media HTTP boundary, with fake model/providers and valid bytes."""
import asyncio
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from PIL import Image

from app.content.service import ContentService
from app.core.settings import Settings
from app.infrastructure.data_content import DataContentBridge
from app.infrastructure.media_gateway import MediaError, MediaGateway
from app.infrastructure.llm import LLMClient
from app.domain.models.content import ContentText
from data.growth_data.api import create_app
from data.growth_data.storage import one
from data.growth_data.errors import Fault

ROOT = Path(__file__).resolve().parents[3]
TOKEN = 'fake-media-token-' + 'x' * 32


class NativeContent:
    is_fixture = True
    def __init__(self, suffix=''):
        self.saw_tool = False
        self.calls = 0
        self.suffix = suffix
    def invoke_tools(self, messages, **kwargs):
        self.calls += 1
        if not any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content='', tool_calls=[{'name':'get_content_context','args':{},'id':'ctx'}])
        context = json.loads(next(message.content for message in messages if isinstance(message, ToolMessage)))
        self.saw_tool = True
        return AIMessage(content='', tool_calls=[{'name':'finish_content','args':{
            'title':context['title'],'description':context['description'] + self.suffix,'checks':[]},'id':'done'}])


def headers(key):
    return {'Idempotency-Key':key, 'X-Request-ID':key}


def make_job(client, service):
    run = client.get('/api/state').json()['run_id']
    response = client.post('/api/day/start', json={}, headers=headers('start'))
    assert response.status_code == 200, response.text
    card = client.get('/api/state').json()['pending_card']
    response = client.post('/api/decision', json={'card_id':card['card_id'],'action':'accept'}, headers=headers('accept'))
    assert response.status_code == 200, response.text
    with service.store.connect() as c:
        job = one(c, "SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D' ORDER BY rowid DESC LIMIT 1", (run,))
    return run, job['job_id']


def test_real_http_bridge_runs_native_content_and_imports_same_attempt_media(tmp_path):
    source = tmp_path/'original.jpg'
    Image.new('RGB',(80,80),'white').save(source,'JPEG')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(FAKE_MEDIA_HOME=str(tmp_path/'media'), FAKE_MEDIA_PORT=str(port),
               PYTHONPATH=str(ROOT/'experiment')+os.pathsep+str(ROOT/'experiment/tests'))
    process = subprocess.Popen([str(ROOT/'experiment/.venv/bin/python'),'-m','uvicorn',
        'fake_bridge_server:create_test_app','--factory','--host','127.0.0.1','--port',str(port),'--no-access-log'],
        cwd=ROOT/'experiment', env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import httpx
        for _ in range(100):
            try:
                if httpx.get(f'http://127.0.0.1:{port}/health',timeout=.2).status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(.05)
        else: raise AssertionError('fake media failed to start')
        app = create_app(tmp_path/'data', content_mode='worker', product_image_path=str(source))
        with TestClient(app) as client:
            run, job_id = make_job(client, app.state.service)
            settings = Settings(_env_file=None, media_mode='live', media_api_token=TOKEN,
                media_api_base_url=f'http://127.0.0.1:{port}', media_poll_seconds=.02,
                media_draft_timeout_seconds=30, demo_product_image_path=str(source),
                demo_logo_image_path=str(ROOT/'frontend/img/shoppilot-ai.png'))
            llm = NativeContent(' cho sản phẩm')
            worker = ContentService(DataContentBridge(app.state.service),settings,llm)
            async def run_worker():
                await worker.process_job(run,job_id)
                await worker.close()
            asyncio.run(run_worker())
            with app.state.service.store.connect() as c:
                job = one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
                content = app.state.service.entity(c,'content_versions',run,'content_id',job['output_content_ids'][0])
                assert job['status']=='succeeded', job['error_code']
                assert llm.saw_tool
                assert content['description'].endswith(' cho sản phẩm')
                assert all(image['status']=='done' for image in content['cover_options'])
                assert content['video_job']['status']=='done'
                assert content['video_job']['reference_asset_id']==content['cover_options'][0]['asset_id']
                assert content['video_job']['review_passed'] is True
                assert job['provider_state']['video']['media_text_vision_calls_reserved']==3
                assert job['provider_state']['video']['media_text_vision_calls_completed']==3
                logo_id=job['provider_state']['inputs']['logo_asset_id']
                assert logo_id and logo_id!=job['provider_state']['inputs']['source_asset_id']
                assert all(app.state.service.object_path(app.state.service.entity(c,'assets',run,'asset_id',image['asset_id'])['object_key']).is_file() for image in content['cover_options'])
            with sqlite3.connect(tmp_path/'media/jobs.sqlite3') as db:
                jobs = [(json.loads(row[0]), json.loads(row[1])) for row in db.execute('SELECT request,result FROM jobs ORDER BY created')]
                logo_file = Path(db.execute('SELECT path FROM assets WHERE id=?',(logo_id,)).fetchone()[0])
            with Image.open(logo_file) as uploaded, Image.open(ROOT/'frontend/img/shoppilot-ai.png') as supplied:
                assert uploaded.convert('RGB').tobytes()==supplied.convert('RGB').tobytes()
            requests = [request for request, _ in jobs]
            assert sorted(request.get('job_type','video') for request in requests) == ['image','image','image','video']
            assert all(request['product_kind']=='desktop_fan' for request in requests)
            assert all(request['logo_asset_id']==logo_id for request in requests if request.get('job_type')=='image')
            reference = next(result['asset_id'] for request, result in jobs if request.get('style') == 'clean_white')
            assert next(request['input_asset_id'] for request in requests if request.get('job_type') != 'image') == reference
            video_request, video_result = next((request, result) for request, result in jobs if request.get('job_type') != 'image')
            assert video_result['requested_duration_seconds'] == video_request['duration']
            assert video_result['duration_seconds'] == pytest.approx(video_request['duration'], abs=0.5)
            assert video_result['duration_matches_requested'] is True
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_missing_input_fails_before_model_or_provider(tmp_path):
    app = create_app(tmp_path/'data', content_mode='worker')
    with TestClient(app) as client:
        run, job_id = make_job(client, app.state.service)
        settings = Settings(_env_file=None, media_mode='live', media_api_token=TOKEN,
            demo_product_image_path=str(tmp_path/'missing.jpg'))
        llm = NativeContent()
        worker = ContentService(DataContentBridge(app.state.service),settings,llm)
        async def run_worker():
            await worker.process_job(run,job_id)
            await worker.close()
        asyncio.run(run_worker())
        with app.state.service.store.connect() as c:
            job = one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
        assert job['status']=='failed' and job['error_code']=='MEDIA_INPUT_MISSING'
        assert not job['provider_state'] and not llm.saw_tool


class FakeGateway:
    def __init__(self): self.calls=[]
    async def preflight(self, kind): self.calls.append('preflight')
    async def upload(self, run, data): self.calls.append('upload'); return 'a'*32
    async def close(self): pass


def test_images_overlap_and_video_starts_when_a_finishes(tmp_path):
    source = tmp_path/'source.jpg'
    Image.new('RGB', (20, 20), 'white').save(source, 'JPEG')
    app = create_app(tmp_path/'data', content_mode='worker', product_image_path=str(source))
    with TestClient(app) as client:
        run, job_id = make_job(client, app.state.service)

        async def exercise():
            import io

            started = {slot: asyncio.Event() for slot in ('A', 'B', 'C', 'video')}
            release = {slot: asyncio.Event() for slot in ('A', 'B', 'C', 'video')}
            submissions = []

            class ControlledGateway(FakeGateway):
                async def submit(self, run_id, slot, body, key):
                    submissions.append((slot, body, key))
                    started[slot].set()
                    return {'job_id': slot, 'status': 'running'}

                async def wait(self, run_id, remote, deadline):
                    slot = remote['job_id']
                    await release[slot].wait()
                    return {'job_id': slot, 'status': 'done', 'result': {
                        'asset_id': f'remote-{slot}', 'visual_review_passed': True,
                        'visual_review': {'notes_vi': 'Đạt'}, 'duration_seconds': 5,
                        'media_text_vision_calls_completed': 3}}

                async def download(self, run_id, remote, *, video=False):
                    if video:
                        return b'1234ftypfake-video'
                    output = io.BytesIO()
                    Image.new('RGB', (20, 20), {'A':'red', 'B':'green', 'C':'blue'}[remote['job_id']]).save(output, 'JPEG')
                    return output.getvalue()

            bridge = DataContentBridge(app.state.service)
            worker = ContentService(bridge, Settings(_env_file=None, media_mode='live'), NativeContent(), media_client=ControlledGateway())
            task = asyncio.create_task(worker.process_job(run, job_id))
            try:
                await asyncio.wait_for(asyncio.gather(*(started[slot].wait() for slot in 'ABC')), 1)
                assert not started['video'].is_set()
                release['A'].set()
                await asyncio.wait_for(started['video'].wait(), 1)
                slots = bridge.snapshot(run, job_id)['provider_state']
                assert slots['A']['status'] == 'done' and slots['A']['asset_id']
                assert slots['B']['status'] == slots['C']['status'] == 'running'
                video_body = next(body for slot, body, _ in submissions if slot == 'video')
                assert video_body['input_asset_id'] == slots['A']['source_asset_id'] == 'remote-A'
                assert not release['B'].is_set() and not release['C'].is_set()
                for slot in ('B', 'C', 'video'):
                    release[slot].set()
                await asyncio.wait_for(task, 2)
                with app.state.service.store.connect() as c:
                    job = one(c, 'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?', (run, job_id))
                    content = app.state.service.entity(c, 'content_versions', run, 'content_id', job['output_content_ids'][0])
                assert job['status'] == 'succeeded', job['error_code']
                assert all(image['status'] == 'done' for image in content['cover_options'])
                assert content['video_job']['reference_asset_id'] == content['cover_options'][0]['asset_id']
                assert [slot for slot, _, _ in submissions].count('video') == 1
                assert len({key for _, _, key in submissions}) == 4
            finally:
                await worker.close()

        asyncio.run(exercise())


@pytest.mark.parametrize('failed_slot,unknown', [('A', False), ('B', False), ('B', True)])
def test_slot_failure_is_isolated_and_unknown_is_not_retried(tmp_path, failed_slot, unknown):
    import io

    source = tmp_path/'source.jpg'
    Image.new('RGB', (20, 20), 'white').save(source, 'JPEG')
    app = create_app(tmp_path/'data', content_mode='worker', product_image_path=str(source))
    with TestClient(app) as client:
        run, job_id = make_job(client, app.state.service)
        submissions = []

        class FailingGateway(FakeGateway):
            async def submit(self, run_id, slot, body, key):
                submissions.append(slot)
                if slot == failed_slot:
                    raise MediaError('MEDIA_SUBMIT_UNKNOWN' if unknown else 'MEDIA_JOB_FAILED', unknown=unknown)
                return {'job_id':slot, 'status':'running'}

            async def wait(self, run_id, remote, deadline):
                return {'job_id':remote['job_id'], 'status':'done', 'result':{
                    'asset_id':f"remote-{remote['job_id']}", 'visual_review_passed':True,
                    'visual_review':{'notes_vi':'Đạt'}, 'duration_seconds':5,
                    'media_text_vision_calls_completed':3}}

            async def download(self, run_id, remote, *, video=False):
                if video:
                    return b'1234ftypfake-video'
                output = io.BytesIO()
                Image.new('RGB', (20, 20), {'A':'red', 'B':'green', 'C':'blue'}[remote['job_id']]).save(output, 'JPEG')
                return output.getvalue()

        async def exercise():
            worker = ContentService(DataContentBridge(app.state.service), Settings(_env_file=None, media_mode='live'),
                                    NativeContent(), media_client=FailingGateway())
            await worker.process_job(run, job_id)
            await worker.process_job(run, job_id)
            await worker.close()

        asyncio.run(exercise())
        with app.state.service.store.connect() as c:
            job = one(c, 'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?', (run, job_id))
            content = app.state.service.entity(c, 'content_versions', run, 'content_id', job['output_content_ids'][0])
        assert submissions.count(failed_slot) == 1
        assert submissions.count('video') == (0 if failed_slot == 'A' else 1)
        assert job['provider_state'][failed_slot]['status'] == ('unknown' if unknown else 'failed')
        assert all(job['provider_state'][slot]['status'] == 'done' for slot in 'ABC' if slot != failed_slot)
        if unknown:
            assert job['status'] == 'failed' and job['provider_state']['video']['status'] == 'done'
            response = client.post('/api/content/retry', json={'feedback_vi':'Ảnh sáng hơn', 'retry_scope':'all'}, headers=headers('retry-unknown'))
            assert response.status_code == 409 and response.json()['error']['code'] == 'PROVIDER_OUTCOME_UNKNOWN'
            assert submissions == ['A', 'B', 'C', 'video']
        else:
            assert job['status'] == 'succeeded'
            assert next(image for image in content['cover_options'] if image['option'] == failed_slot)['status'] == 'failed'
            assert content['video_job']['status'] == ('failed' if failed_slot == 'A' else 'done')


@pytest.mark.parametrize('lease', [None, '2000-01-01T00:00:00+00:00'])
def test_expired_content_lease_fences_slots_and_heartbeat(tmp_path, lease):
    app=create_app(tmp_path/'data',content_mode='worker')
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        service=app.state.service;bridge=DataContentBridge(service)
        first=bridge.reserve_slot(run,job_id,'A',{'frozen':True})
        assert first['can_submit'] is True
        assert bridge.reserve_slot(run,job_id,'A',{'frozen':True})['can_submit'] is False
        with pytest.raises(Fault) as conflict:bridge.reserve_slot(run,job_id,'A',{'frozen':False})
        assert conflict.value.code=='REQUEST_CONFLICT'
        with service.store.connect(write=True) as c:
            c.execute('UPDATE content_jobs SET lease_until=? WHERE run_id=? AND job_id=?',(lease,run,job_id))
            before=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
        for call in (lambda:bridge.reserve_slot(run,job_id,'B',{'new':True}),
                     lambda:bridge.update_slot(run,job_id,'A',{'status':'running'}),
                     lambda:bridge.heartbeat(run,job_id,before['version']),
                     lambda:bridge.import_asset(run,job_id,data=b'bad',mime_type='image/png',kind='image')):
            with pytest.raises(Fault) as failure:call()
            assert failure.value.code=='LEASE_EXPIRED'
        with service.store.connect() as c:
            after=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
        assert after['provider_state']==before['provider_state'] and after['lease_until']==lease and after['version']==before['version']


def test_content_worker_never_submits_after_lease_expires(tmp_path,monkeypatch):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        service=app.state.service;bridge=DataContentBridge(service);reserve=bridge.reserve_slot
        def expire_before_reserve(*args):
            with service.store.connect(write=True) as c:
                c.execute("UPDATE content_jobs SET lease_until='2000-01-01' WHERE run_id=? AND job_id=?",(run,job_id))
            return reserve(*args)
        monkeypatch.setattr(bridge,'reserve_slot',expire_before_reserve)
        class CountingGateway(FakeGateway):
            async def submit(self,*args):
                self.calls.append('submit')
                raise AssertionError('expired worker must not submit')
        media=CountingGateway();worker=ContentService(bridge,Settings(_env_file=None,media_mode='live'),NativeContent(),media_client=media)
        async def process():
            await worker.process_job(run,job_id)
            await worker.close()
        asyncio.run(process())
        assert 'submit' not in media.calls
        with service.store.connect() as c:
            job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
            assert 'A' not in job['provider_state']


def test_media_cap_survives_reopen_and_terminal_or_superseded_jobs_are_fenced(tmp_path):
    app=create_app(tmp_path/'data',content_mode='worker')
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        service=app.state.service
        with service.store.connect(write=True) as c:
            old=c.execute("SELECT job_id FROM content_jobs WHERE run_id=? AND shop_id!='D' ORDER BY shop_id",(run,)).fetchall()
            assert len(old)>=3
            slots={slot:{'status':'done'} for slot in 'ABC'}
            for row in old[:3]:
                c.execute('UPDATE content_jobs SET provider_state_json=? WHERE run_id=? AND job_id=?',(json.dumps(slots),run,row['job_id']))
        bridge=DataContentBridge(create_app(tmp_path/'data',content_mode='worker').state.service)
        with pytest.raises(Fault) as exhausted:bridge.reserve_slot(run,job_id,'A',{'attempt':1})
        assert exhausted.value.code=='MEDIA_BUDGET_EXHAUSTED'
        with service.store.connect(write=True) as c:
            c.execute('UPDATE content_jobs SET provider_state_json=? WHERE run_id=? AND job_id=?',(json.dumps({'A':{'status':'done'},'B':{'status':'done'}}),run,old[0]['job_id']))
        assert bridge.reserve_slot(run,job_id,'A',{'attempt':1})['can_submit']
        with pytest.raises(Fault) as exhausted:bridge.reserve_slot(run,job_id,'B',{'attempt':1})
        assert exhausted.value.code=='MEDIA_BUDGET_EXHAUSTED'
        with service.store.connect(write=True) as c:
            c.execute("UPDATE content_jobs SET status='failed' WHERE run_id=? AND job_id=?",(run,job_id))
        with pytest.raises(Fault) as terminal:bridge.reserve_slot(run,job_id,'B',{'attempt':1})
        assert terminal.value.code=='STALE_DRAFT'
        with service.store.connect(write=True) as c:
            c.execute("UPDATE content_jobs SET status='queued' WHERE run_id=? AND job_id=?",(run,job_id))
            current=service.entity(c,'content_jobs',run,'job_id',job_id)
            service.persist_copy(c,'content_jobs',current,job_id='job_new_attempt',attempt=2)
        with pytest.raises(Fault) as stale:bridge.reserve_slot(run,job_id,'B',{'attempt':1})
        assert stale.value.code=='STALE_DRAFT'


def test_budget_fault_terminalizes_without_reinvoking_model(tmp_path, monkeypatch):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        bridge=DataContentBridge(app.state.service)
        def exhausted(*args): raise Fault('MEDIA_BUDGET_EXHAUSTED','out of budget')
        monkeypatch.setattr(bridge,'reserve_slot',exhausted)
        llm=NativeContent();media=FakeGateway()
        worker=ContentService(bridge,Settings(_env_file=None,media_mode='live'),llm,media_client=media)
        async def run_worker():
            await worker.process_job(run,job_id)
            await worker.process_job(run,job_id)
            await worker.close()
        asyncio.run(run_worker())
        with app.state.service.store.connect() as c:
            job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
        assert job['status']=='failed' and job['error_code']=='MEDIA_BUDGET_EXHAUSTED'
        assert llm.calls==2 and media.calls==['preflight','upload']


def test_reserved_job_restart_never_resubmits_or_reinvokes_model(tmp_path):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        bridge=DataContentBridge(app.state.service)
        bridge.update_slot(run,job_id,'inputs',{'source_asset_id':'a'*32,'logo_asset_id':None})
        bridge.reserve_slot(run,job_id,'A',{'frozen':True})
        llm=NativeContent();media=FakeGateway()
        worker=ContentService(bridge,Settings(_env_file=None,media_mode='live'),llm,media_client=media)
        async def run_worker():
            await worker.process_job(run,job_id)
            await worker.close()
        asyncio.run(run_worker())
        with app.state.service.store.connect() as c:
            job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
        assert job['status']=='failed' and job['error_code']=='CONTENT_RESTART_UNKNOWN'
        assert job['provider_state']['inputs']['status']=='unknown'
        assert llm.calls==0 and media.calls==[]


def enable_native_review(service, run):
    with service.store.connect(write=True) as c:
        c.execute("UPDATE runs SET config_json=json_set(config_json,'$.driver.agent_version','native'),brief_version=1 WHERE run_id=?",(run,))


def test_offline_original_is_explicitly_cached_and_requires_video_skip(tmp_path):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        enable_native_review(app.state.service,run)
        llm=NativeContent();media=FakeGateway()
        bridge=DataContentBridge(app.state.service)
        original_asset_id=bridge.input_asset(run,job_id)['asset_id']
        worker=ContentService(bridge,Settings(_env_file=None,media_mode='offline',llm_mode='live'),llm,media_client=media)
        async def run_worker():
            await worker.process_job(run,job_id)
            await worker.close()
        asyncio.run(run_worker())
        state=client.get('/api/state').json();draft=state['content_draft']
        with app.state.service.store.connect() as c:
            job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
            content=app.state.service.entity(c,'content_versions',run,'content_id',job['output_content_ids'][0])
            events=c.execute("SELECT count(*) FROM events WHERE run_id=? AND type='agent_completed' AND json_extract(payload_json,'$.source')='fixture'",(run,)).fetchone()[0]
        assert job['status']=='succeeded' and job['fallback_used'] and job['provider_state']=={}
        assert llm.calls==2 and llm.saw_tool and media.calls==[] and events>0
        assert {image['asset_id'] for image in content['cover_options']}=={original_asset_id}
        assert all(image['status']=='cached' and image['source']=='cache' and client.get(image['path']).status_code==200 for image in draft['images'])
        assert draft['video']['status']=='failed' and 'Ngoại tuyến' in ' '.join(draft['checks'])
        binding={'card_id':draft['card_id'],'expected_brief_version':draft['brief_version'],
                 'expected_draft_version':draft['version'],'expected_job_id':draft['job_id'],
                 'expected_content_id':draft['content_id'],'cover_option':'A','video_review_ack':False}
        rejected=client.post('/api/content/apply',json={**binding,'skip_video':False},headers=headers('no-skip'))
        assert rejected.status_code==409 and rejected.json()['error']['code']=='VIDEO_SKIP_REQUIRED'
        accepted=client.post('/api/content/apply',json={**binding,'skip_video':True},headers=headers('skip'))
        assert accepted.status_code==200,accepted.text
        assert accepted.json()['listing']['video'] is None
        night=client.post('/api/night',json={},headers=headers('night'))
        assert night.status_code in (200,202),night.text


def test_offline_corrupt_original_stays_unavailable(tmp_path):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        enable_native_review(app.state.service,run)
        bridge=DataContentBridge(app.state.service)
        original=next(asset for asset in bridge.snapshot(run,job_id)['assets'] if asset['source_reference'].startswith('local_import:sha256:'))
        app.state.service.object_path(original['object_key']).write_bytes(b'corrupt')
        llm=NativeContent();media=FakeGateway()
        worker=ContentService(bridge,Settings(_env_file=None,media_mode='offline'),llm,media_client=media)
        async def run_worker():
            await worker.process_job(run,job_id)
            await worker.close()
        asyncio.run(run_worker())
        draft=client.get('/api/state').json()['content_draft']
        assert draft['error_code']=='MEDIA_INPUT_MISSING'
        assert all(image['status']=='failed' and not image.get('path') for image in draft['images'])
        assert llm.calls==0 and media.calls==[]


def test_offline_llm_and_media_make_no_provider_calls(tmp_path):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        calls=[];media=FakeGateway()
        settings=Settings(_env_file=None,media_mode='offline',llm_mode='offline',openai_api_key='test-key',llm_model='test-model')
        llm=LLMClient(settings,model_factory=lambda **kw:calls.append(kw))
        worker=ContentService(DataContentBridge(app.state.service),settings,llm,media_client=media)
        async def run_worker():
            await worker.process_job(run,job_id)
            await worker.close()
        asyncio.run(run_worker())
        with app.state.service.store.connect() as c:
            job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
            events=c.execute("SELECT count(*) FROM events WHERE run_id=? AND type='agent_completed' AND json_extract(payload_json,'$.source')='offline'",(run,)).fetchone()[0]
        assert job['status']=='succeeded' and job['fallback_used']
        assert calls==[] and media.calls==[] and events>0


def test_offline_images_only_retry_retains_prior_text_and_video(tmp_path):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        media=FakeGateway();llm=NativeContent();settings=Settings(_env_file=None,media_mode='offline')
        async def process(jid):
            worker=ContentService(DataContentBridge(app.state.service),settings,llm,media_client=media)
            await worker.process_job(run,jid)
            await worker.close()
        asyncio.run(process(job_id))
        original=client.get('/api/state').json()['content_draft']
        response=client.post('/api/content/retry',json={'feedback_vi':'Ảnh nền sáng hơn','retry_scope':'images'},headers=headers('images-only'))
        assert response.status_code==200,response.text
        asyncio.run(process(response.json()['draft']['job_id']))
        retried=client.get('/api/state').json()['content_draft']
        assert retried['version']==2
        assert (retried['title'],retried['description'],retried['video'])==(original['title'],original['description'],original['video'])
        assert all(image['status']=='cached' and image['source']=='cache' for image in retried['images'])
        assert llm.calls==4 and media.calls==[]


def fake_transport(handler):
    def respond(request):
        if request.url.path == '/v1/readiness':
            return httpx.Response(200,json={'ready':True,'openai_configured':True,'muse_configured':True,
                'contract_version':'growth-media.v1','supported_product_kinds':['desktop_fan'],
                'optional_logo':True,'bright_background':True})
        if request.url.path == '/v1/assets':
            return httpx.Response(201,json={'asset_id':'a'*32})
        return handler(request)
    return httpx.MockTransport(respond)


def test_private_feedback_stays_in_audit_but_not_native_tool_or_media_request(tmp_path):
    from data.growth_data.service import Principal
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,first_job_id=make_job(client,app.state.service)
        service=app.state.service;bridge=DataContentBridge(service)
        with service.store.connect() as c:
            first=service.entity(c,'content_jobs',run,'job_id',first_job_id)
            session_id=service.entity(c,'runs',run,'run_id',run)['session_id']
        bridge.complete(run,first_job_id,{'expected_job_version':first['version'],'status':'failed','error_code':'FIXTURE'})
        learner=Principal('test_learner','learning_worker',None,(run,),('D',))
        seller=Principal(session_id,'seller',session_id,(),('D',))
        style='Ảnh nền sáng tự nhiên'
        private_style='Giá vốn 115.000đ của chị Lan; phong cách tối giản'
        with service.store.connect(write=True) as c:
            for index,value in enumerate((style,private_style),1):
                question=service.question(c,learner,run,'D',{'external_pref_id':f'pref-{index}','field':'content_style','value':value,
                    'text_vi':'Xác nhận phong cách?','based_on_rules_version':index})
                service.decision(c,seller,run,{'target_type':'rule_question','target_id':question['question_id'],
                    'target_version':1,'action':'approve','rule_answer':True})
        raw='Giá vốn 115.000đ của chị Lan; 115.000đ; 115000; 115 000; chị Lan; làm nền sáng.'
        retry=client.post('/api/content/retry',json={'feedback_vi':raw,'retry_scope':'all'},headers=headers('private-retry'))
        assert retry.status_code==200,retry.text
        job_id=retry.json()['draft']['job_id']
        snapshot=bridge.snapshot(run,job_id)
        projected=json.dumps(snapshot,ensure_ascii=False,default=str).casefold()
        assert all(value not in projected for value in ('115.000','115000','115 000','chị lan','giá vốn'))
        assert snapshot['job']['feedback_history']==['làm nền sáng.']
        assert style in snapshot['rules']['content_style_notes']
        assert 'phong cách tối giản' in snapshot['rules']['content_style_notes']
        assert set(snapshot['rules'])=={'content_style_notes'}
        with service.store.connect() as c:
            stored=service.entity(c,'content_jobs',run,'job_id',job_id)
            draft=service.entity(c,'content_versions',run,'content_id',stored['output_content_ids'][0])
            rules,_=service.rules(c,run,'D')
            assert stored['feedback_history']==[raw] and draft['feedback_history']==[raw]
            assert private_style in rules['content_style_notes']
            assert c.execute("SELECT COUNT(*) FROM decisions WHERE run_id=? AND target_type='rule_question' AND action='approve'",(run,)).fetchone()[0]==2
        class RecordingContent(NativeContent):
            tool_payload=None
            def invoke_tools(self,messages,**kwargs):
                self.tool_payload=next((message.content for message in messages if isinstance(message,ToolMessage)),self.tool_payload)
                return super().invoke_tools(messages,**kwargs)
        llm=RecordingContent();requests=[]
        def fail_image(request):
            requests.append(json.loads(request.content))
            return httpx.Response(400,json={'detail':'offline test provider'})
        settings=Settings(_env_file=None,media_mode='live',media_api_token=TOKEN,media_api_base_url='http://media.test')
        async def process():
            async with httpx.AsyncClient(transport=fake_transport(fail_image),base_url='http://media.test') as http:
                worker=ContentService(bridge,settings,llm,media_client=MediaGateway(settings,client=http))
                await worker.process_job(run,job_id)
                await worker.close()
        asyncio.run(process())
        assert llm.saw_tool and llm.tool_payload and requests
        tool=json.loads(llm.tool_payload)
        assert tool['feedback_history']==['làm nền sáng.']
        assert style in tool['memory']['confirmed_style_notes']
        assert all(request['background_preference']=='bright' for request in requests)
        outbound=(llm.tool_payload+json.dumps(requests,ensure_ascii=False)).casefold()
        assert all(value not in outbound for value in ('115.000','115000','115 000','chị lan','giá vốn'))


@pytest.mark.parametrize('invalid', ['long', 'facts'])
def test_invalid_text_is_rejected_before_paid_reservation(tmp_path, monkeypatch, invalid):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        def invalid_text(context, *args):
            description = context.description + (' cho sản phẩm'*600 if invalid=='long' else ' chống nước')
            return SimpleNamespace(value=ContentText(title=context.title,description=description,checks=[]))
        monkeypatch.setattr('app.content.service.generate_content_from_context',invalid_text)
        paid=[]
        transport=fake_transport(lambda request: paid.append(request) or httpx.Response(500))
        settings=Settings(_env_file=None,media_mode='live',media_api_token=TOKEN,media_api_base_url='http://media.test')
        async def run_worker():
            async with httpx.AsyncClient(transport=transport,base_url='http://media.test') as http:
                worker=ContentService(DataContentBridge(app.state.service),settings,NativeContent(),media_client=MediaGateway(settings,client=http))
                await worker.process_job(run,job_id)
                await worker.close()
        asyncio.run(run_worker())
        with app.state.service.store.connect() as c:
            job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
        assert job['status']=='failed' and job['error_code']=='CLAIM_INVALID'
        assert set(job['provider_state'])=={'inputs'} and paid==[]


@pytest.mark.parametrize('responses', [
    [b'accepted but broken json', b'accepted but broken json'],
    [b'{"status":"queued"}', b'{"job_id":"bad","status":"queued"}'],
    [b'accepted but broken json', None],
])
def test_malformed_accepted_job_is_unknown_and_blocks_new_attempt(tmp_path, responses):
    source=tmp_path/'source.jpg';Image.new('RGB',(20,20),'white').save(source,'JPEG')
    app=create_app(tmp_path/'data',content_mode='worker',product_image_path=str(source))
    with TestClient(app) as client:
        run,job_id=make_job(client,app.state.service)
        submitted=[]
        def accept_malformed(request):
            assert request.url.path=='/v1/image-jobs'
            style=json.loads(request.content)['style']
            submitted.append((style,request.headers['Idempotency-Key'],request.content))
            if style!='clean_white':
                return httpx.Response(400,content=b'known rejection')
            reply=responses[sum(value[0]=='clean_white' for value in submitted)-1]
            return httpx.Response(400 if reply is None else 202,content=reply or b'no')
        settings=Settings(_env_file=None,media_mode='live',media_api_token=TOKEN,media_api_base_url='http://media.test')
        async def run_worker():
            async with httpx.AsyncClient(transport=fake_transport(accept_malformed),base_url='http://media.test') as http:
                worker=ContentService(DataContentBridge(app.state.service),settings,NativeContent(),media_client=MediaGateway(settings,client=http))
                await worker.process_job(run,job_id)
                await worker.close()
        asyncio.run(run_worker())
        with app.state.service.store.connect() as c:
            job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,job_id))
        assert job['status']=='failed' and job['provider_state']['A']['status']=='unknown'
        a_submissions=[value for value in submitted if value[0]=='clean_white']
        assert len(a_submissions)==2 and a_submissions[0]==a_submissions[1]
        assert a_submissions[0][1]==job['provider_state']['A']['idempotency_key']
        assert len(submitted)==4 and all(job['provider_state'][slot]['status']=='failed' for slot in 'BC')
        response=client.post('/api/content/retry',json={'feedback_vi':'Ảnh nền sáng hơn','retry_scope':'all'},headers=headers('retry'))
        assert response.status_code==409 and response.json()['error']['code']=='PROVIDER_OUTCOME_UNKNOWN'
        with app.state.service.store.connect() as c:
            assert c.execute("SELECT count(*) FROM content_jobs WHERE run_id=? AND shop_id='D'",(run,)).fetchone()[0]==1
        assert len(submitted)==4
