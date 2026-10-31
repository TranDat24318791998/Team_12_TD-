"""Seller-controlled staged media uses Data's durable drafts and publishing rules."""

import asyncio
import hashlib
import io

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.infrastructure.data_content import DataContentBridge
from data.growth_data.api import create_app
from data.growth_data.storage import one


def headers(key):
    return {'Idempotency-Key': key, 'X-Request-ID': key}


def binding(draft):
    return {'card_id': draft['card_id'], 'expected_brief_version': draft['brief_version'],
            'expected_draft_version': draft['version'], 'expected_job_id': draft['job_id'],
            'expected_content_id': draft['content_id']}


def create_staged_job(client, service):
    # Exercise the reference negotiation without invoking a model, then enable the
    # same native staged profile used by the application before seller approval.
    run = client.get('/api/state').json()['run_id']
    assert client.post('/api/day/start', json={}, headers=headers('start')).status_code == 200
    with service.store.connect(write=True) as c:
        c.execute("UPDATE runs SET config_json=json_set(config_json, '$.driver.agent_version', 'native', '$.driver.media_wizard', 'staged'), brief_version=1 WHERE run_id=?", (run,))
    card = client.get('/api/state').json()['pending_card']
    decision = {'card_id': card['card_id'], 'action': 'accept', 'expected_card_version': card['version'],
                'expected_brief_version': card['brief_version']}
    response = client.post('/api/decision', json=decision, headers=headers('accept'))
    assert response.status_code == 200, response.text
    return run, client.get('/api/state').json()


def image_bytes(color):
    buffer = io.BytesIO()
    Image.new('RGB', (16, 16), color).save(buffer, 'JPEG')
    return buffer.getvalue()


@pytest.mark.parametrize(('actual_duration','duration_matches'), [(10,True),(5,False),(None,None)])
def test_staged_media_requires_each_seller_action_and_persists_both_assets(tmp_path, actual_duration, duration_matches):
    source = tmp_path / 'product.jpg'
    source.write_bytes(image_bytes('white'))
    app = create_app(tmp_path / 'data', content_mode='worker', product_image_path=str(source))
    service = app.state.service
    with TestClient(app) as client:
        run, state = create_staged_job(client, service)
        original = state['demo_shop']['images'][0]
        draft = state['content_draft']
        assert draft['wizard']['stage'] == 'choose_image'
        assert not state['busy'] and draft['status'] == 'awaiting_image'
        assert all(not image['path'] for image in draft['images'])
        assert client.get(state['demo_shop_original']['images'][0]).content == source.read_bytes()
        with service.store.connect() as c:
            assert not one(c, "SELECT job_id FROM content_jobs WHERE run_id=? AND shop_id='D' AND status IN ('queued','running')", (run,))

        video_request = {**binding(draft), 'output_type': 'chibi_3d', 'duration': 10}
        assert client.post('/api/content/video', json=video_request, headers=headers('early-video')).status_code == 409
        early_apply = {**binding(draft), 'cover_option': 'A', 'skip_video': False, 'video_review_ack': False}
        assert client.post('/api/content/apply', json=early_apply, headers=headers('early-apply')).status_code == 409

        image_request = {**binding(draft), 'background': 'summer_fresh', 'wishes': 'Nền tươi sáng'}
        response = client.post('/api/content/image', json=image_request, headers=headers('image'))
        assert response.status_code == 200, response.text
        assert response.json()['draft']['wizard']['stage'] == 'image_queued'
        assert client.post('/api/content/image', json=image_request, headers=headers('image')).json() == response.json()
        assert client.post('/api/content/image', json={**image_request, 'wishes': 'Khác'}, headers=headers('image')).status_code == 409
        assert client.get('/api/state').json()['demo_shop']['images'][0] == original

        bridge = DataContentBridge(service)
        job_id = draft['job_id']
        snapshot = bridge.snapshot(run, job_id)
        assert snapshot['job']['brief']['wizard']['wishes'] == 'Nền tươi sáng'
        reservation = bridge.reserve_slot(run, job_id, 'A', {'style': 'summer_fresh'})
        assert reservation['can_submit']
        image_id = bridge.import_asset(run, job_id, data=image_bytes('red'), mime_type='image/jpeg', kind='image')
        bridge.update_slot(run, job_id, 'A', {'status': 'done', 'asset_id': image_id,
                           'source_asset_id': 'remote-generated-image', 'source': 'live'})
        current = bridge.snapshot(run, job_id)
        images = [{'option': 'A', 'status': 'done', 'asset_id': image_id, 'source': 'live'},
                  *[{'option': option, 'status': 'failed', 'asset_id': None} for option in 'BC']]
        candidate = {'title': current['content']['title'], 'description': current['content']['description'],
                     'images': images, 'video': {'status': 'pending', 'asset_id': None}}
        bridge.complete(run, job_id, {'expected_job_version': current['job']['version'], 'status': 'succeeded',
                                      'content_candidates': candidate})
        state = client.get('/api/state').json()
        draft = state['content_draft']
        assert draft['wizard']['stage'] == 'image_ready' and draft['wizard']['output_type'] is None
        assert draft['video']['status'] == 'pending'
        assert client.get(draft['images'][0]['path']).content == image_bytes('red')
        assert state['demo_shop']['images'][0] == original and state['demo_shop']['video'] is None
        assert client.post('/api/content/apply', json={**binding(draft), 'cover_option': 'A', 'skip_video': False},
                           headers=headers('video-required')).status_code == 409

        video_request = {**binding(draft), 'output_type': 'chibi_3d', 'duration': 10}
        response = client.post('/api/content/video', json=video_request, headers=headers('video'))
        assert response.status_code == 200, response.text
        assert response.json()['draft']['wizard']['stage'] == 'video_queued'
        current = bridge.snapshot(run, job_id)
        assert current['job']['brief']['wizard']['output_type'] == 'chibi_3d'
        assert current['job']['brief']['wizard']['duration'] == 10
        assert current['provider_state']['A']['source_asset_id'] == 'remote-generated-image'
        bridge.reserve_slot(run, job_id, 'video', {'reference': 'remote-generated-image'})
        raw_video = b'1234ftypfake-video'
        video_id = bridge.import_asset(run, job_id, data=raw_video, mime_type='video/mp4', kind='video')
        bridge.update_slot(run, job_id, 'video', {'status': 'done', 'asset_id': video_id,
                           'source': 'live', 'review_passed': True, 'duration_seconds': actual_duration,
                           'short_description': 'Video giới thiệu quạt'})
        current = bridge.snapshot(run, job_id)
        candidate = {'title': current['content']['title'], 'description': current['content']['description'],
                     'images': current['content']['cover_options'],
                     'video': {'status': 'done', 'asset_id': video_id, 'source': 'live',
                               'reference_asset_id': image_id, 'reference_job_id': job_id,
                               'reference_attempt': current['job']['attempt'], 'review_passed': True,
                               'duration_seconds': actual_duration, 'requested_duration_seconds': 10,
                               'duration_matches_requested': True, 'short_description': 'Video giới thiệu quạt'}}
        bridge.complete(run, job_id, {'expected_job_version': current['job']['version'], 'status': 'succeeded',
                                      'content_candidates': candidate})
        state = client.get('/api/state').json()
        draft = state['content_draft']
        assert draft['wizard']['stage'] == 'video_ready'
        assert draft['video']['short_description'] == 'Video giới thiệu quạt'
        assert draft['video']['requested_duration_seconds'] == 10
        assert draft['video']['duration_matches_requested'] is duration_matches
        assert state['demo_shop']['images'][0] == original and state['demo_shop']['video'] is None
        body = {**binding(draft), 'cover_option': 'A', 'skip_video': False, 'video_review_ack': False}
        if duration_matches is not True:
            rejected = client.post('/api/content/apply', json=body, headers=headers('duration-unacknowledged'))
            assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'VIDEO_DURATION_ACK_REQUIRED'
            body['video_review_ack']=True
        applied = client.post('/api/content/apply', json=body, headers=headers('apply'))
        assert applied.status_code == 200, applied.text
        state = client.get('/api/state').json()
        assert client.get(state['demo_shop']['images'][0]).content == image_bytes('red')
        assert client.get(state['demo_shop']['video']).content == raw_video
        cookie = client.cookies.get('growth_sid')

    reopened = create_app(tmp_path / 'data', content_mode='worker', product_image_path=str(source))
    with TestClient(reopened) as client:
        client.cookies.set('growth_sid', cookie)
        state = client.get('/api/state').json()
        assert state['run_id'] == run and state['content_draft'] is None
        assert client.get(state['demo_shop']['images'][0]).content == image_bytes('red')
        assert client.get(state['demo_shop']['video']).content == raw_video


def test_staged_image_can_publish_without_requesting_video(tmp_path):
    source = tmp_path/'product.jpg'
    source.write_bytes(image_bytes('white'))
    app = create_app(tmp_path/'data', content_mode='worker', product_image_path=str(source))
    with TestClient(app) as client:
        run, state = create_staged_job(client, app.state.service)
        draft = state['content_draft']
        body = {**binding(draft), 'background':'clean_white', 'wishes':''}
        assert client.post('/api/content/image', json=body, headers=headers('image')).status_code == 200
        waiting=client.get('/api/state').json()['content_draft']
        assert waiting['text_ready'] is False
        rejected=client.post('/api/content/apply', json={**binding(waiting),'cover_option':'A','skip_video':True},headers=headers('too-early'))
        assert rejected.status_code==409
        bridge = DataContentBridge(app.state.service)
        job_id = draft['job_id']
        bridge.reserve_slot(run, job_id, 'A', {'fake':'image'})
        asset = bridge.import_asset(run, job_id, data=image_bytes('red'), mime_type='image/jpeg', kind='image')
        bridge.update_slot(run, job_id, 'A', {'status':'done', 'asset_id':asset, 'source_asset_id':'remote-image', 'source':'live'})
        snapshot = bridge.snapshot(run, job_id)
        candidate = {'title':snapshot['content']['title'], 'description':snapshot['content']['description'],
            'images':[{'option':'A','status':'done','asset_id':asset,'source':'live'},
                      *[{'option':slot,'status':'pending','asset_id':None} for slot in 'BC']],
            'video':{'status':'pending','asset_id':None}}
        bridge.complete(run, job_id, {'expected_job_version':snapshot['job']['version'],'status':'succeeded','content_candidates':candidate})
        draft = client.get('/api/state').json()['content_draft']
        assert draft['wizard']['stage']=='image_ready' and draft['text_ready']
        applied = client.post('/api/content/apply', json={**binding(draft),'cover_option':'A','skip_video':True},headers=headers('skip'))
        assert applied.status_code == 200, applied.text
        assert applied.json()['listing']['video'] is None
        assert client.get(applied.json()['listing']['images'][0]).content == image_bytes('red')


@pytest.mark.parametrize('stage', ['queued', 'preflight', 'running', 'running_restore', 'ready', 'failed'])
def test_staged_skip_preserves_listing_when_video_finishes_or_fails(tmp_path, stage):
    from app.content.service import ContentService
    from app.core.settings import Settings
    from app.infrastructure.media_gateway import MediaError
    from tests.integration.api.test_media_bridge import NativeContent

    source = tmp_path/'product.jpg'
    source.write_bytes(image_bytes('white'))
    app = create_app(tmp_path/'data', content_mode='worker', product_image_path=str(source))
    with TestClient(app) as client:
        run, state = create_staged_job(client, app.state.service)
        draft = state['content_draft']
        assert client.post('/api/content/image', json={**binding(draft),'background':'clean_white','wishes':''}, headers=headers('image')).status_code==200

        async def exercise():
            started, release = asyncio.Event(), asyncio.Event()
            requests = []

            class Media:
                async def preflight(self, kind, *, video=True):
                    if video and stage=='preflight':
                        started.set()
                        await release.wait()
                async def upload(self, run_id, data): return 'original-product'
                async def submit(self, run_id, slot, body, key):
                    requests.append(slot)
                    if slot=='video': started.set()
                    return {'job_id':slot,'status':'running'}
                async def wait(self, run_id, remote, deadline):
                    if remote['job_id']=='A':
                        return {'job_id':'A','status':'done','result':{'asset_id':'remote-image'}}
                    await release.wait()
                    if stage=='failed': raise MediaError('MEDIA_JOB_FAILED')
                    return {'job_id':'video','status':'done','result':{'duration_seconds':5,
                        'visual_review_passed':True,'media_text_vision_calls_completed':3}}
                async def download(self, run_id, result, *, video=False):
                    return b'1234ftypfake-video' if video else image_bytes('red')
                async def close(self): pass

            bridge = DataContentBridge(app.state.service)
            worker = ContentService(bridge, Settings(_env_file=None, media_mode='live', demo_logo_image_path=''), NativeContent(), media_client=Media())
            task = None
            try:
                await worker.process_job(run, draft['job_id'])
                current = client.get('/api/state').json()['content_draft']
                assert current['wizard']['stage']=='image_ready' and current['text_ready']
                response = client.post('/api/content/video', json={**binding(current),'output_type':'realistic_human','duration':5}, headers=headers('video'))
                assert response.status_code==200, response.text
                if stage!='queued':
                    task = asyncio.create_task(worker.process_job(run, draft['job_id']))
                    await asyncio.wait_for(started.wait(), 2)
                    if stage in {'ready','failed'}:
                        release.set()
                        await asyncio.wait_for(task, 2)
                current = client.get('/api/state').json()['content_draft']
                assert current['text_ready'] and current['images'][0]['status']=='done'
                body = {**binding(current),'cover_option':'A','skip_video':True,'video_review_ack':False}
                rejected = client.post('/api/content/apply', json={**body,'expected_job_id':'wrong'}, headers=headers('stale'))
                assert rejected.status_code==409 and rejected.json()['error']['code']=='STALE_DRAFT'
                if stage=='running':
                    with app.state.service.store.connect() as c:
                        job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,draft['job_id']))
                        asset=app.state.service.entity(c,'assets',run,'asset_id',job['provider_state']['A']['asset_id'])
                    path=app.state.service.object_path(asset['object_key'])
                    raw=path.read_bytes()
                    path.write_bytes(b'broken')
                    invalid=client.post('/api/content/apply', json=body, headers=headers('bad-image'))
                    assert invalid.status_code==422 and invalid.json()['error']['code']=='ASSET_INVALID'
                    path.write_bytes(raw)
                applied = client.post('/api/content/apply', json=body, headers=headers('skip'))
                assert applied.status_code==200, applied.text
                listing = applied.json()['listing']
                assert listing['video'] is None and client.get(listing['images'][0]).content==image_bytes('red')
                if stage=='running_restore':
                    with app.state.service.store.connect() as c:
                        job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,draft['job_id']))
                        previous=app.state.service.entity(c,'content_versions',run,'content_id',job['source_content_id'])
                    restored=client.post(f"/api/v1/runs/{run}/content/{previous['content_id']}/restore",
                        json={'expected_active_content_id':draft['content_id'],'expected_content_version':previous['version']},headers=headers('restore'))
                    assert restored.status_code==200, restored.text
                    listing=restored.json()['data']['listing']
                if stage=='queued':
                    await worker.process_job(run, draft['job_id'])
                    assert requests==['A']
                elif stage in {'preflight','running','running_restore'}:
                    release.set()
                    await asyncio.wait_for(task, 2)
                    if stage=='preflight': assert requests==['A']
                with app.state.service.store.connect() as c:
                    job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run,draft['job_id']))
                    content=app.state.service.entity(c,'content_versions',run,'content_id',draft['content_id'])
                    assert job['status'] not in {'queued','running'}
                    assert content['video_asset_id'] is None and content['video_job']['status']=='skipped'
                    assert app.state.service.public(c,run,'D')==listing
            finally:
                release.set()
                await worker.close()

        asyncio.run(exercise())


def test_seller_wishes_are_sanitized_before_worker_snapshot(tmp_path):
    source = tmp_path / 'product.jpg'
    source.write_bytes(image_bytes('white'))
    app = create_app(tmp_path / 'data', content_mode='worker', product_image_path=str(source))
    with TestClient(app) as client:
        run, state = create_staged_job(client, app.state.service)
        draft = state['content_draft']
        body = {**binding(draft), 'background': 'clean_white', 'wishes': 'Nền sáng; giá vốn bí mật'}
        assert client.post('/api/content/image', json=body, headers=headers('image')).status_code == 200
        snapshot = DataContentBridge(app.state.service).snapshot(run, draft['job_id'])
        assert snapshot['job']['brief']['wizard']['wishes'] == 'Nền sáng'


@pytest.mark.parametrize('active_valid', [True, False])
def test_wizard_preview_and_input_use_same_current_cover_or_verified_original(tmp_path, active_valid):
    source = tmp_path / 'product.jpg'
    source.write_bytes(image_bytes('white'))
    app = create_app(tmp_path / 'data', content_mode='worker', product_image_path=str(source))
    service = app.state.service
    with TestClient(app) as client:
        run, state = create_staged_job(client, service)
        original = state['demo_shop']['images'][0]
        cover_bytes = image_bytes('green')
        with service.store.connect(write=True) as c:
            product = service.product(c, run, 'D')
            current = service.entity(c, 'content_versions', run, 'content_id', product['active_content_id'])
            asset = service.entity(c, 'assets', run, 'asset_id', current['cover_asset_id'])
            cover_key = f'test/{run}/new-cover.jpg'
            path = service.object_path(cover_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(cover_bytes if active_valid else b'damaged')
            service.persist_copy(c, 'assets', asset, asset_id='asset_current_cover', object_key=cover_key,
                                 mime_type='image/jpeg', size_bytes=len(cover_bytes), sha256=hashlib.sha256(cover_bytes).hexdigest(),
                                 origin='generated', source_reference='worker_upload', visibility='published', job_id=None)
            service.persist_copy(c, 'content_versions', current, content_id='content_current', content_version=99,
                                 cover_asset_id='asset_current_cover', status='published')
            c.execute("UPDATE content_versions SET status='superseded' WHERE run_id=? AND content_id=?", (run,current['content_id']))
            c.execute("UPDATE products SET active_content_id='content_current' WHERE run_id=? AND shop_id='D'", (run,))
        state = client.get('/api/state').json()
        draft = state['content_draft']
        assert (draft['input_image'] == state['demo_shop']['images'][0]) is active_valid
        assert client.get(draft['input_image']).content == (cover_bytes if active_valid else source.read_bytes())
        response = client.post('/api/content/image', json={**binding(draft), 'background':'clean_white', 'wishes':''}, headers=headers('image'))
        assert response.status_code == 200, response.text
        queued = response.json()['draft']
        assert queued['input_image'] == draft['input_image']
        bridge = DataContentBridge(service)
        selected = bridge.input_asset(run,draft['job_id'])
        assert selected['bytes'] == (cover_bytes if active_valid else source.read_bytes())
        if active_valid:
            # The input is pinned at the seller's click even if the listing changes later.
            with service.store.connect(write=True) as c:
                c.execute("UPDATE products SET active_content_id=? WHERE run_id=? AND shop_id='D'", (current['content_id'],run))
            assert client.get('/api/state').json()['content_draft']['input_image'] == queued['input_image']
            assert bridge.input_asset(run,draft['job_id'])['bytes'] == cover_bytes
        else:
            assert draft['input_image'] == original


@pytest.mark.parametrize(('mode','staged'), [('offline',False),('live',True)])
def test_app_enables_staged_wizard_only_for_live_media(tmp_path, monkeypatch, mode, staged):
    from app.core.settings import Settings
    from app.main import create_app as composed_app

    class IdleWorker:
        async def start(self):pass
        async def close(self):pass

    monkeypatch.setattr('app.core.settings.Settings',lambda:Settings(_env_file=None,media_mode=mode))
    app = composed_app(home=tmp_path, worker_factory=lambda service:IdleWorker())
    with TestClient(app) as client:
        run = client.get('/api/state').json()['run_id']
        with app.state.service.store.connect() as c:
            driver = app.state.service.entity(c,'runs',run,'run_id',run)['config']['driver']
        assert (driver.get('media_wizard') == 'staged') is staged


def test_wizard_rejects_geometric_placeholder_before_starting_image(tmp_path):
    app = create_app(tmp_path / 'data', content_mode='worker')
    with TestClient(app) as client:
        _, state = create_staged_job(client, app.state.service)
        draft = state['content_draft']
        assert draft['input_image'] is None
        response = client.post('/api/content/image', json={**binding(draft), 'background':'clean_white', 'wishes':''}, headers=headers('image'))
        assert response.status_code == 409 and response.json()['error']['code'] == 'MEDIA_INPUT_MISSING'
        assert client.get('/api/state').json()['content_draft']['status'] == 'awaiting_image'


def test_real_worker_only_submits_requested_stage_with_fake_media(tmp_path):
    from app.content.service import ContentService
    from app.core.settings import Settings
    from tests.integration.api.test_media_bridge import NativeContent

    class Media:
        def __init__(self):
            self.requests = []
            self.preflights = []

        async def preflight(self, kind, *, video=True):
            self.preflights.append((kind, video))

        async def upload(self, run, data):
            return 'original-product'

        async def submit(self, run, slot, body, key):
            self.requests.append((slot, body))
            return {'job_id': slot, 'status': 'running'}

        async def wait(self, run, remote, deadline):
            if remote['job_id'] == 'A':
                return {'job_id': 'A', 'status': 'done', 'image_url': 'https://media.example/image',
                        'image_url_expires_at': 123, 'result': {'asset_id': 'image-in-minio'}}
            return {'job_id': 'video', 'status': 'done', 'video_url': 'https://media.example/video',
                    'video_url_expires_at': 456, 'result': {'duration_seconds': 10,
                    'visual_review_passed': True, 'visual_review': {'notes_vi': 'Đạt'},
                    'short_description': 'Quạt trên bàn', 'media_text_vision_calls_completed': 3}}

        async def download(self, run, result, *, video=False):
            return b'1234ftypfake-video' if video else image_bytes('blue')

        async def close(self):
            pass

    source = tmp_path / 'product.jpg'
    source.write_bytes(image_bytes('white'))
    app = create_app(tmp_path / 'data', content_mode='worker', product_image_path=str(source))
    media = Media()
    settings = Settings(_env_file=None, media_mode='live', demo_logo_image_path='')
    with TestClient(app) as client:
        run, state = create_staged_job(client, app.state.service)
        draft = state['content_draft']
        worker = ContentService(DataContentBridge(app.state.service), settings, NativeContent(), media_client=media)
        assert not media.requests
        request = {**binding(draft), 'background': 'pastel_lifestyle', 'wishes': 'Nền bàn làm việc'}
        assert client.post('/api/content/image', json=request, headers=headers('image')).status_code == 200
        asyncio.run(worker.process_job(run, draft['job_id']))
        draft = client.get('/api/state').json()['content_draft']
        assert draft['wizard']['stage'] == 'image_ready', draft
        assert [slot for slot, _ in media.requests] == ['A']
        assert media.requests[0][1]['style'] == 'pastel_lifestyle'
        assert 'Nền bàn làm việc' in media.requests[0][1]['seller_wishes']
        assert draft['video']['status'] == 'pending'
        assert media.preflights == [('desktop_fan', False)]
        body = {**binding(draft), 'output_type': 'realistic_human', 'duration': 15}
        assert client.post('/api/content/video', json=body, headers=headers('video')).status_code == 200
        asyncio.run(worker.process_job(run, draft['job_id']))
        draft = client.get('/api/state').json()['content_draft']
        assert draft['wizard']['stage'] == 'video_ready', draft
        assert [slot for slot, _ in media.requests] == ['A', 'video']
        request = media.requests[1][1]
        assert (request['input_asset_id'], request['output_type'], request['duration']) == ('image-in-minio', 'realistic_human', 15)
        assert media.preflights[-1] == ('desktop_fan', True)
        assert draft['video']['short_description'] == 'Quạt trên bàn'
        assert (draft['video']['duration_seconds'], draft['video']['requested_duration_seconds'],
                draft['video']['duration_matches_requested'], draft['video']['review_passed']) == (10, 15, False, False)
        assert client.get(draft['video']['path']).content == b'1234ftypfake-video'
        with app.state.service.store.connect() as c:
            job = one(c, 'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?', (run, draft['job_id']))
        assert job['provider_state']['A']['public_url'] == 'https://media.example/image'
        assert job['provider_state']['video']['public_url'] == 'https://media.example/video'
        assert job['provider_state']['video']['duration_matches_requested'] is False
        asyncio.run(worker.close())


def test_failed_stage_can_start_new_draft_but_unknown_result_cannot_be_retried(tmp_path):
    from app.content.service import ContentService
    from app.core.settings import Settings
    from tests.integration.api.test_media_bridge import NativeContent

    source = tmp_path / 'product.jpg'
    source.write_bytes(image_bytes('white'))
    app = create_app(tmp_path / 'data', content_mode='worker', product_image_path=str(source))
    with TestClient(app) as client:
        run, state = create_staged_job(client, app.state.service)
        draft = state['content_draft']
        request = {**binding(draft), 'background': 'clean_white', 'wishes': ''}
        assert client.post('/api/content/image', json=request, headers=headers('image')).status_code == 200
        bridge = DataContentBridge(app.state.service)
        worker = ContentService(bridge, Settings(_env_file=None, media_mode='offline'), NativeContent())
        asyncio.run(worker.process_job(run, draft['job_id']))
        asyncio.run(worker.close())
        failed = client.get('/api/state').json()['content_draft']
        assert failed['wizard']['stage'] == 'failed' and failed['error_code'] == 'MEDIA_OFFLINE'
        request = {**binding(failed), 'feedback_vi': 'Thử lại', 'retry_scope': 'all'}
        response = client.post('/api/content/retry', json=request, headers=headers('retry'))
        assert response.status_code == 200, response.text
        retry = response.json()['draft']
        assert retry['wizard']['stage'] == 'choose_image' and retry['version'] == 2
        request = {**binding(retry), 'background': 'clean_white', 'wishes': ''}
        assert client.post('/api/content/image', json=request, headers=headers('image-2')).status_code == 200
        bridge.reserve_slot(run, retry['job_id'], 'A', {'style': 'clean_white'})
        bridge.update_slot(run, retry['job_id'], 'A', {'status': 'unknown', 'error': 'MEDIA_OUTCOME_UNKNOWN'})
        current = bridge.snapshot(run, retry['job_id'])
        bridge.complete(run, retry['job_id'], {'expected_job_version': current['job']['version'],
                                              'status': 'failed', 'error_code': 'MEDIA_OUTCOME_UNKNOWN'})
        unknown = client.get('/api/state').json()['content_draft']
        assert unknown['outcome_unknown'] and unknown['wizard']['stage'] == 'failed'
        request = {**binding(unknown), 'feedback_vi': 'Thử lại', 'retry_scope': 'all'}
        response = client.post('/api/content/retry', json=request, headers=headers('retry-unknown'))
        assert response.status_code == 409 and response.json()['error']['code'] == 'PROVIDER_OUTCOME_UNKNOWN'
