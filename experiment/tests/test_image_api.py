import io,json,time
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pydantic import ValidationError
from video_api.config import Settings
from video_api.main import create_app
from video_api.models import VideoRequest
from video_api.image_pipeline import process_image_job

def test_image_upload_generation_idempotency_and_public_link(tmp_path):
 s=Settings(data_dir=tmp_path,storage_backend='local',openai_api_key='fake',video_api_token='a'*32,playback_secret='b'*32)
 class Provider:
  def __init__(self,s):pass
  def advertisement(self,paths,prompt,out):Image.new('RGB',(80,80),'white').save(out,'JPEG')
 def process(s,store,storage,row):process_image_job(s,store,storage,row,Provider)
 b=io.BytesIO();Image.new('RGB',(30,30),'blue').save(b,'PNG');raw=b.getvalue()
 headers={'Authorization':'Bearer '+'a'*32,'Idempotency-Key':'image-test-unique'}
 with TestClient(create_app(s,processor=process)) as c:
  def submit(style='clean_white'):
   return c.post('/v1/images',headers=headers,data={'style':style},files={'logo':('logo.png',raw),'product':('product.png',raw)})
  r=submit();assert r.status_code==200,r.text
  j=r.json();assert j['result']['media_type']=='image/jpeg'
  assert c.get(j['image_url']).headers['content-type']=='image/jpeg'
  assert submit().json()['job_id']==j['job_id']
  assert submit('summer_fresh').status_code==409
  assert c.get(j['image_url'].replace('signature=','signature=x')).status_code==403
  assert c.get('/v1/jobs/'+j['job_id'],headers={'Authorization':'Bearer '+'a'*32,'X-Owner-ID':'other'}).status_code==404

@pytest.mark.parametrize('kind',['chibi_3d','realistic_human'])
def test_video_supported_lengths(kind):
 for duration in (5,10,15):assert VideoRequest(product_name='Quạt',output_type=kind,duration=duration).duration==duration
 with pytest.raises(ValidationError):VideoRequest(product_name='Quạt',output_type=kind,duration=8)
