import io
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from video_api.config import Settings
from video_api.main import create_app, playback_signature


TOKEN = 'test-service-token-' + 'x' * 32


@pytest.fixture
def api(tmp_path):
    settings = Settings(data_dir=tmp_path, storage_backend='local', video_api_token=TOKEN,
                        playback_secret='test-playback-' + 'y' * 32, public_base_url='https://video.example.com')
    app = create_app(settings, worker_enabled=False)
    with TestClient(app) as client:
        yield client, app


def headers(owner='alice'):
    return {'Authorization': 'Bearer ' + TOKEN, 'X-Owner-ID': owner}


def upload(client, owner='alice'):
    data = io.BytesIO()
    Image.new('RGB', (180, 240), '#ABCDEF').save(data, 'PNG')
    response = client.post('/v1/assets', headers=headers(owner), files={'file': ('product.png', data.getvalue(), 'image/png')})
    assert response.status_code == 201, response.text
    return response.json()['asset_id']


def payload(asset):
    return {'input_asset_id': asset, 'product_name': 'Quạt để bàn', 'generate_script': False,
            'mode': 'motion_graphics',
            'voice': 'none', 'generate_image': False, 'duration': 2, 'fps': 12}


def test_auth_before_upload_and_job_access(api):
    client, _ = api
    assert client.post('/v1/assets', content=b'not multipart').status_code == 401
    assert client.get('/v1/jobs/unknown').status_code == 401
    assert client.get('/health').json()['openai_configured'] is False


def test_local_readiness_probes_storage_without_touching_existing_files(api):
    client,app=api
    root=app.state.storage.root
    other=root/'existing-object';other.write_bytes(b'keep')
    assert client.get('/v1/readiness',headers=headers()).status_code==200
    assert other.read_bytes()==b'keep' and list(root.iterdir())==[other]
    other.unlink();root.rmdir();root.write_bytes(b'not a directory')
    assert client.get('/v1/readiness',headers=headers()).status_code==503
    assert root.read_bytes()==b'not a directory'


def test_idempotency_conflict_owner_scope_and_queue_limit(api):
    client, app = api
    asset = upload(client)
    h = headers() | {'Idempotency-Key': 'request-0001'}
    first = client.post('/v1/jobs', headers=h, json=payload(asset))
    assert first.status_code == 202
    second = client.post('/v1/jobs', headers=h, json=payload(asset))
    assert first.json()['job_id'] == second.json()['job_id']
    assert second.json()['reused'] is True
    assert client.post('/v1/jobs', headers=h, json=payload(asset) | {'cta': 'Khác'}).status_code == 409
    assert client.get('/v1/jobs/' + first.json()['job_id'], headers=headers('bob')).status_code == 404
    assert client.post('/v1/jobs', headers=headers('bob') | {'Idempotency-Key': 'request-bob1'}, json=payload(asset)).status_code == 404
    for i in range(3):
        assert client.post('/v1/jobs', headers=headers() | {'Idempotency-Key': f'request-{i+10}'}, json=payload(asset)).status_code == 202
    assert client.post('/v1/jobs', headers=headers() | {'Idempotency-Key': 'request-full'}, json=payload(asset)).status_code == 429


def test_missing_key_local_model_and_input_validation(api):
    client, _ = api
    asset = upload(client)
    h = headers() | {'Idempotency-Key': 'request-invalid'}
    assert client.post('/v1/jobs', headers=h, json=payload(asset) | {'generate_script': True}).status_code == 503
    assert client.post('/v1/jobs', headers=h, json=payload(asset) | {'mode': 'local_i2v'}).status_code == 503
    assert client.post('/v1/jobs', headers=h, json=payload(asset) | {'mode': 'source_video'}).status_code == 422
    assert client.post('/v1/jobs', headers=h, json=payload(asset) | {'duration': 99}).status_code == 422
    assert client.post('/v1/assets', headers=headers(), files={'file': ('bad.png', b'not-image', 'image/png')}).status_code == 415


def completed(api):
    client, app = api
    asset = upload(client)
    row, _ = app.state.store.create('alice', 'completed-job', 'fingerprint', payload(asset), 4)
    output = app.state.settings.data_dir / 'sample.mp4'
    output.write_bytes(b'0123456789abcdef')
    key = f"videos/alice/{row['id']}/video.mp4"
    app.state.storage.put(key, output)
    app.state.store.update(row['id'], status='done', stage='done', result={'object_key': key})
    response = client.get('/v1/jobs/' + row['id'], headers=headers())
    return row['id'], response.json()['video_url']


@pytest.mark.parametrize('range_header,expected,content_range', [
    ('bytes=2-5', b'2345', 'bytes 2-5/16'),
    ('bytes=10-', b'abcdef', 'bytes 10-15/16'),
    ('bytes=-3', b'def', 'bytes 13-15/16'),
    ('bytes=0-999', b'0123456789abcdef', 'bytes 0-15/16')])
def test_signed_playback_supports_seeking(api, range_header, expected, content_range):
    client, _ = api
    _, url = completed(api)
    path = url.replace('https://video.example.com', '')
    response = client.get(path, headers={'Range': range_header})
    assert response.status_code == 206
    assert response.content == expected
    assert response.headers['content-range'] == content_range
    assert response.headers['content-type'] == 'video/mp4'
    head = client.head(path, headers={'Range': range_header})
    assert head.status_code == 206 and head.content == b''


def test_expired_tampered_invalid_range_and_full_play(api):
    client, app = api
    job_id, url = completed(api)
    path = url.replace('https://video.example.com', '')
    assert client.get(path).content == b'0123456789abcdef'
    assert client.get(path + 'x').status_code == 403
    expires = int(time.time()) - 1
    signature = playback_signature(app.state.settings, job_id, expires)
    assert client.get(f'/v1/jobs/{job_id}/play?expires={expires}&signature={signature}').status_code == 403
    for value in ['bytes=99-', 'bytes=0-1,5-6', 'bytes=-0', 'invalid']:
        assert client.get(path, headers={'Range': value}).status_code == 416


def test_restart_does_not_repeat_paid_calls(api):
    client, app = api
    asset = upload(client)
    rows = [app.state.store.create('alice', f'recover-job-{i}', 'hash', payload(asset), 4)[0] for i in range(4)]
    for _ in range(3):
        app.state.store.claim()
    app.state.store.recover()
    assert all(app.state.store.job(row['id'])['stage'] == 'interrupted' for row in rows[:3])
    assert app.state.store.job(rows[3]['id'])['status'] == 'queued'
    replay, created = app.state.store.create('alice', 'recover-job-0', 'hash', payload(asset), 4)
    assert not created and replay['id'] == rows[0]['id'] and replay['stage'] == 'interrupted'


def test_worker_runs_three_image_jobs_at_once(tmp_path):
    settings = Settings(data_dir=tmp_path, storage_backend='local', openai_api_key='fake',
                        video_api_token=TOKEN, playback_secret='test-playback-' + 'y' * 32)
    started = set()
    three_started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()

    def processor(settings, store, storage, row):
        with lock:
            started.add(row['id'])
            if len(started) == 3:
                three_started.set()
        release.wait(3)
        store.update(row['id'], status='failed', stage='failed', error='fake provider')

    with TestClient(create_app(settings, processor=processor)) as client:
        try:
            asset = upload(client)
            ids = []
            for index, style in enumerate(('clean_white', 'pastel_lifestyle', 'premium_studio', 'clean_white')):
                response = client.post('/v1/image-jobs', headers=headers() | {'Idempotency-Key': f'parallel-image-{index}'},
                    json={'job_type':'image', 'product_asset_id':asset, 'style':style, 'product_kind':'desktop_fan', 'product_name':'Quạt'})
                assert response.status_code == 202, response.text
                ids.append(response.json()['job_id'])
            assert three_started.wait(1), f'Only {len(started)} image jobs started before any could finish'
            assert started == set(ids[:3])
            assert all(client.get('/v1/jobs/' + job_id, headers=headers()).json()['status'] == 'running' for job_id in ids[:3])
            assert client.get('/v1/jobs/' + ids[3], headers=headers()).json()['status'] == 'queued'
            replay = client.post('/v1/image-jobs', headers=headers() | {'Idempotency-Key':'parallel-image-1'},
                json={'job_type':'image', 'product_asset_id':asset, 'style':'pastel_lifestyle', 'product_kind':'desktop_fan', 'product_name':'Quạt'})
            assert replay.json()['job_id'] == ids[1] and replay.json()['reused'] is True
        finally:
            release.set()


def test_watch_page_requires_signature_and_escapes_script(api):
    client, app = api
    job_id, url = completed(api)
    row = app.state.store.job(job_id)
    result = json.loads(row['result']) | {'script':'<script>alert(1)</script>', 'mode':'muse'}
    app.state.store.update(job_id,result=result)
    path = url.replace('https://video.example.com/v1/jobs/', '/watch/').replace('/play?', '?')
    response = client.get(path)
    assert response.status_code == 200
    assert '&lt;script&gt;' in response.text
    assert '<script>alert(1)</script>' not in response.text
    assert 'Lưu trữ tệp cục bộ' in response.text
    assert 'MinIO' not in response.text
    assert client.get(path+'tampered').status_code == 403


def test_list_jobs_is_owner_scoped(api):
    client, _ = api
    completed(api)
    assert len(client.get('/v1/jobs',headers=headers()).json()['jobs']) == 1
    assert client.get('/v1/jobs',headers=headers('bob')).json()['jobs'] == []


def test_minio_not_ready_rejected_before_job(tmp_path):
    settings = Settings(data_dir=tmp_path, video_api_token=TOKEN, playback_secret='z'*32,
                        minio_access_key='', minio_secret_key='')
    app = create_app(settings, worker_enabled=False)
    with TestClient(app) as client:
        asset = upload(client)
        response = client.post('/v1/jobs', headers=headers() | {'Idempotency-Key':'missing-minio'}, json=payload(asset))
        assert response.status_code == 503


def test_cross_origin_preflight_and_error_responses(api):
    client, _ = api
    origin = 'https://any-shop.example'
    for path in ('/v1/images', '/v1/videos', '/v1/jobs', '/v1/jobs/'+'a'*32+'/play'):
        response = client.options(path, headers={'Origin': origin,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization,content-type,idempotency-key,x-owner-id,range'})
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == '*'
    for path in ('/health', '/v1/jobs', '/v1/images/'+'a'*32+'/view?expires=0&signature=invalid'):
        response = client.get(path, headers={'Origin': origin})
        assert response.headers['access-control-allow-origin'] == '*'
        assert 'access-control-allow-credentials' not in response.headers
