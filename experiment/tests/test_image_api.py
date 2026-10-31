import io,json,time
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pydantic import ValidationError
from video_api.config import Settings
from video_api.main import create_app
from video_api.models import ImageRequest, VideoRequest
from video_api.image_pipeline import process_image_job
from video_api.storage import LocalStorage
from video_api.store import Store

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

@pytest.mark.parametrize('with_logo,kind',[(False,'handheld_fan'),(True,'desktop_fan')])
def test_product_roles_bright_style_and_checksum(tmp_path,with_logo,kind):
 import hashlib
 settings=Settings(data_dir=tmp_path,storage_backend='local')
 store=Store(tmp_path);storage=LocalStorage(tmp_path);captured={}
 for index in range(3):
  path=tmp_path/f'{index}.png';Image.new('RGB',(20,20),'white').save(path)
  store.add_asset(str(index+1)*32,'owner','image',path)
 class Provider:
  def __init__(self,settings):pass
  def advertisement(self,paths,prompt,out):captured.update(paths=paths,prompt=prompt);Image.new('RGB',(40,40),'green').save(out,'JPEG')
 request=ImageRequest(logo_asset_id='1'*32 if with_logo else None,product_asset_id='2'*32,style_asset_id='3'*32,
   style='premium_studio',background_preference='bright',product_kind=kind,product_name='Quạt')
 row,_=store.create('owner','test-role-123','digest',request.model_dump(),4)
 process_image_job(settings,store,storage,row,Provider)
 result=json.loads(store.job(row['id'])['result']);prompt=captured['prompt']
 assert f"Input image {2 if with_logo else 1} is the sole product" in prompt
 assert f"Input image {3 if with_logo else 2} is a mood/style" in prompt
 assert ('handle' in prompt)==(kind=='handheld_fan')
 assert ('do not invent a logo' in prompt)==(not with_logo)
 assert 'charcoal' not in prompt and result['style']=='summer_fresh'
 assert result['product_kind']==kind and result['minio_path'] is None
 assert result['sha256']==hashlib.sha256((tmp_path/'jobs'/row['id']/'image.jpg').read_bytes()).hexdigest()
