import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from muse.muse_client import MuseError
from video_api.config import Settings
from video_api.main import create_app
from video_api.models import MuseCreativePlan, MuseVisualReview, VideoRequest
from video_api.muse_media import MuseMedia, SafeSession
from video_api.muse_pipeline import build_muse_prompt, process_muse_job
from video_api.render import render_video
from video_api.models import CreativePlan


def test_muse_defaults_and_one_product_prompt():
    request = VideoRequest(product_name='Quạt để bàn')
    assert request.mode == 'muse' and request.voice == 'muse' and request.input_asset_id is None
    plan = MuseCreativePlan(product_kind='desktop_fan', product_description='White circular desk fan',
        presenter_description='An adult woman', setting_description='Home office',
        narration='Quạt để bàn cho góc làm việc.', visual_prompt='The presenter gently holds the fan base.')
    prompt = build_muse_prompt(request, plan)
    assert 'EXACTLY ONE PRODUCT / ONE SKU' in prompt
    assert 'SAME fan model' in prompt and 'Vietnamese line' in prompt
    assert 'may naturally hold or support' in prompt and 'otherwise use another natural gesture' in prompt
    assert 'Preserve the desktop fan base' in prompt and 'do not turn it into a handheld fan' in prompt
    assert 'do not invent dimensions or measurements' in prompt
    assert plan.narration in prompt
    with pytest.raises(ValidationError):
        VideoRequest(product_name='Quạt', generate_script=False)
    with pytest.raises(ValidationError):
        VideoRequest(product_name='Quạt', generate_image=True)


def test_muse_task_persisted_and_no_second_submit(tmp_path):
    settings = Settings(data_dir=tmp_path, muse_poll_seconds=1)
    client = Mock()
    client.create_video.return_value = {'task_id': 'remote-task-123'}
    client.get_video.return_value = {'status': 'completed', 'output': '/v1/media/fan.mp4'}
    adapter = MuseMedia(settings, client=client)
    adapter.download = Mock(return_value=tmp_path/'fan.mp4')
    events = []
    output, task = adapter.generate('one fan', image=None, duration=5, aspect='9:16',
        idempotency_key='stable-key', work=tmp_path, on_task=lambda value: events.append(('saved',value)),
        on_update=lambda value: events.append(('stage',value)))
    assert events[:2] == [('stage','muse_submitting'), ('saved','remote-task-123')]
    assert task['task_id'] == 'remote-task-123'
    client.create_video.assert_called_once()
    assert client.create_video.call_args.kwargs['idempotency_key'] == 'stable-key'


@pytest.mark.parametrize('url', ['https://evil.example/v1/media/x.mp4',
                               'https://muse.example/other/x.mp4',
                               'http://muse.example/v1/media/x.mp4'])
def test_muse_rejects_token_download_to_other_destination(tmp_path,url):
    client = Mock(base_url='https://muse.example')
    client.media_url.return_value = url
    adapter = MuseMedia(Settings(data_dir=tmp_path),client=client)
    with pytest.raises(MuseError):
        adapter.download(url,tmp_path/'video.mp4')
    client.session.get.assert_not_called()


def test_muse_missing_key_fails_before_submit(tmp_path):
    settings=Settings(data_dir=tmp_path,storage_backend='local',openai_api_key='fake',
                      video_api_token='a'*32,playback_secret='b'*32)
    with TestClient(create_app(settings,worker_enabled=False)) as client:
        response=client.post('/v1/jobs',headers={'Authorization':'Bearer '+'a'*32,'Idempotency-Key':'muse-key-check'},
                             json={'product_name':'Quạt để bàn'})
        assert response.status_code==503
        assert 'MUSE_API_KEY' in response.text


@pytest.mark.parametrize(('produced_seconds', 'duration_matches'), [(5, True), (2, False)])
def test_muse_pipeline_checks_the_delivered_duration(tmp_path, produced_seconds, duration_matches):
    import PIL.Image
    from video_api.storage import LocalStorage
    from video_api.store import Store
    settings=Settings(data_dir=tmp_path,storage_backend='local',openai_api_key='fake',
                      muse_api_key='fake-muse',video_api_token='a'*32,playback_secret='b'*32)
    store=Store(tmp_path);storage=LocalStorage(tmp_path)
    image=tmp_path/'input.png';PIL.Image.new('RGB',(100,120),'blue').save(image)
    request=VideoRequest(product_name='Quạt để bàn',duration=5,voice='none')
    row,_=store.create('local-demo','muse-pipeline-test','digest',request.model_dump(),4)
    class Provider:
        def __init__(self,settings): pass
        def muse_plan(self,request,image):
            return MuseCreativePlan(product_kind='desktop_fan',product_description='one white fan',
                presenter_description='one adult',setting_description='real room',narration='Quạt để bàn.',visual_prompt='Live action.')
        def review_muse(self,frames,**kwargs):
            assert len(frames)==3 and all(p.is_file() for p in frames)
            return MuseVisualReview(photorealistic=True,adult_presenter_visible=True,single_fan_product=True,consistent_product=True,notes_vi='fixture')
    class Generator:
        def __init__(self,settings): pass
        def generate(self,prompt,**kw):
            kw['on_task']('remote-id');kw['on_update']('muse_generating')
            legacy=VideoRequest(input_asset_id='a'*32,product_name='fixture',mode='motion_graphics',voice='none',generate_script=False,duration=produced_seconds,fps=12)
            video=render_video(settings,legacy,CreativePlan(title='fixture',tagline='',narration='',visual_prompt=''),
                               image,None,None,None,produced_seconds,kw['work'])
            source=kw['work']/'muse-source.mp4'
            video.rename(source)
            return source,{'task_id':'remote-id'}
    # This module must not call the legacy still compositor for real Muse media.
    process_muse_job(settings,store,storage,row,provider_factory=Provider,muse_factory=Generator)
    done=store.job(row['id']);result=json.loads(done['result'])
    assert done['status']=='done' and result['provider']=='muse'
    assert result['muse_task_id']=='remote-id' and result['visual_review_passed'] is duration_matches
    assert result['requested_duration_seconds']==5 and result['duration_seconds']==pytest.approx(produced_seconds, abs=0.5)
    assert result['duration_matches_requested'] is duration_matches
    assert done['stage']==('done' if duration_matches else 'needs_visual_review')
    assert result['media_text_vision_calls_reserved']==result['media_text_vision_calls_completed']==2
    assert result['motion_source']=='muse_generated_live_action'
