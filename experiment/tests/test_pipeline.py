import io
import json
import time

from fastapi.testclient import TestClient
from PIL import Image

from video_api.config import Settings
from video_api.main import create_app
from video_api.models import CreativePlan
from video_api.pipeline import process_job
from video_api.render import extract_frame, synth_music


def test_real_renderer_worker_and_playback(tmp_path):
    settings = Settings(data_dir=tmp_path, storage_backend='local', video_api_token='a'*32, playback_secret='b'*32)
    app = create_app(settings)
    headers = {'Authorization': 'Bearer ' + 'a'*32, 'X-Owner-ID':'test'}
    picture = io.BytesIO()
    Image.new('RGB', (200, 300), '#FC6A32').save(picture, 'PNG')
    with TestClient(app) as client:
        asset = client.post('/v1/assets', headers=headers, files={'file':('fan.png',picture.getvalue(),'image/png')}).json()['asset_id']
        response = client.post('/v1/jobs', headers=headers | {'Idempotency-Key':'render-test'}, json={
            'input_asset_id':asset,'product_name':'Quạt để bàn', 'tagline':'Dành cho góc làm việc',
            'mode':'motion_graphics',
            'script':'', 'generate_script':False,'voice':'none','duration':2,'fps':12})
        assert response.status_code == 202, response.text
        job_id = response.json()['job_id']
        for _ in range(150):
            status = client.get('/v1/jobs/'+job_id,headers=headers).json()
            if status['status'] in ('done','failed'):
                break
            time.sleep(0.1)
        assert status['status'] == 'done', status
        result = client.get(status['video_url'])
        assert result.status_code == 200 and result.content[4:8] == b'ftyp'
        assert status['result']['storage'] == 'local'
        rendered = settings.data_dir/'result.mp4'
        rendered.write_bytes(result.content)
        extract_frame(settings, rendered, settings.data_dir/'frame.png')
        # Verify uploaded source video path really works, rather than replacing it with a still.
        video_asset = client.post('/v1/assets',headers=headers,files={'file':('source.mp4',result.content,'video/mp4')}).json()['asset_id']
        response = client.post('/v1/jobs',headers=headers | {'Idempotency-Key':'source-video-test'},json={
            'input_asset_id':video_asset,'product_name':'Quạt để bàn','mode':'source_video',
            'generate_script':False,'voice':'none','music':'none','duration':2,'fps':12})
        source_id=response.json()['job_id']
        for _ in range(150):
            second=client.get('/v1/jobs/'+source_id,headers=headers).json()
            if second['status'] in ('done','failed'):
                break
            time.sleep(0.1)
        assert second['status']=='done',second
        assert second['result']['motion_source']=='uploaded_source_video'


def test_openai_steps_with_fake_provider(tmp_path):
    class FakeProvider:
        calls=[]
        def __init__(self, settings):
            pass
        def plan(self, request, image):
            self.calls.append('plan')
            return CreativePlan(title=request.product_name,tagline='Nội dung thử',narration='Quạt để bàn.',visual_prompt='fan')
        def image(self, original, prompt, output):
            self.calls.append('image')
            output.write_bytes(original.read_bytes())
            return output
        def speech(self, script, output):
            self.calls.append('speech')
            return synth_music(output,1)
    def processor(settings, store, storage, row):
        process_job(settings,store,storage,row,provider_factory=FakeProvider)
    settings=Settings(data_dir=tmp_path,storage_backend='local',openai_api_key='fake-not-a-real-key',
                      video_api_token='a'*32,playback_secret='b'*32)
    app=create_app(settings,processor=processor)
    headers={'Authorization':'Bearer '+'a'*32,'Idempotency-Key':'fake-openai-job'}
    image=io.BytesIO();Image.new('RGB',(100,150),'white').save(image,'PNG')
    with TestClient(app) as client:
        asset=client.post('/v1/assets',headers=headers,files={'file':('p.png',image.getvalue(),'image/png')}).json()['asset_id']
        row=client.post('/v1/jobs',headers=headers,json={'input_asset_id':asset,'product_name':'Quạt','mode':'motion_graphics','voice':'openai','generate_image':True,'duration':2,'fps':12}).json()
        for _ in range(150):
            status=client.get('/v1/jobs/'+row['job_id'],headers=headers).json()
            if status['status'] in ('done','failed'):
                break
            time.sleep(.1)
        assert status['status']=='done',status
        assert FakeProvider.calls==['plan','image','speech']
