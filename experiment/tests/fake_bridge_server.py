"""HTTP media process with fake providers, used only by the bridge integration test."""
import hashlib
import os
from pathlib import Path
import subprocess

import imageio_ffmpeg
from PIL import Image

from video_api.config import Settings
from video_api.image_pipeline import process_image_job
from video_api.main import create_app
from video_api.models import MuseCreativePlan, MuseVisualReview, ProductImageAnalysis
from video_api.muse_pipeline import process_muse_job


class FakeProvider:
    def __init__(self, settings): pass

    def advertisement(self, paths, prompt, output):
        color = tuple(hashlib.sha256(prompt.encode()).digest()[:3])
        Image.new('RGB', (80, 80), color).save(output, 'JPEG')

    def analyze_product_image(self, image, product_kind):
        return ProductImageAnalysis(product_kind=product_kind, product_count=1, product_description='Một quạt',
            logo_text='', logo_location='', brand_colors=[], image_style='studio', background='white', visible_text=[])

    def muse_plan(self, request, image, analysis=None):
        return MuseCreativePlan(product_kind=request.product_kind, product_description='Một quạt',
            presenter_description='Người trưởng thành', setting_description='Phòng sáng',
            narration=request.script, visual_prompt='One fan.')

    def review_muse(self, frames, **kwargs):
        return MuseVisualReview(photorealistic=True, adult_presenter_visible=True,
            single_fan_product=True, consistent_product=True, notes_vi='Kiểm thử')


class FakeMuse:
    def __init__(self, settings): pass

    def generate(self, prompt, *, work, on_task, on_update, **kwargs):
        on_task('fake-task')
        on_update('muse_generating')
        path = work / 'source.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'color=c=white:s=80x80:r=12', '-t', '2', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', str(path)], check=True)
        return path, {'task_id':'fake-task'}


def processor(settings, store, storage, row):
    if '"job_type": "image"' in row['request']:
        return process_image_job(settings, store, storage, row, provider_factory=FakeProvider)
    return process_muse_job(settings, store, storage, row, provider_factory=FakeProvider, muse_factory=FakeMuse)


def create_test_app():
    settings = Settings(data_dir=Path(os.environ['FAKE_MEDIA_HOME']), storage_backend='local',
        openai_api_key='fake-key', muse_api_key='fake-key', video_api_token='fake-media-token-'+'x'*32,
        playback_secret='fake-playback-secret-'+'x'*32,
        public_base_url='http://127.0.0.1:'+os.environ['FAKE_MEDIA_PORT'])
    return create_app(settings, processor=processor)
