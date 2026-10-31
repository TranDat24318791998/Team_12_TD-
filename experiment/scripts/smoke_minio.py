"""Real MinIO round trip + API Range playback; deliberately no paid AI calls."""
import io
import json
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_api.config import Settings
from video_api.storage import MinioStorage


def main():
    settings = Settings.load()
    base = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:8010'
    headers = {'Authorization': 'Bearer ' + settings.video_api_token.get_secret_value(), 'X-Owner-ID': 'smoke-test'}
    image = Image.new('RGB', (480, 640), '#E9EEF3')
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 80, 400, 400), fill='#FFFFFF', outline='#315777', width=8)
    for angle in range(0, 360, 45):
        import math
        x, y = 240 + 140 * math.cos(math.radians(angle)), 240 + 140 * math.sin(math.radians(angle))
        draw.line((240, 240, x, y), fill='#315777', width=16)
    draw.rounded_rectangle((220, 400, 260, 540), radius=10, fill='#315777')
    draw.ellipse((160, 520, 320, 560), fill='#315777')
    data = io.BytesIO()
    image.save(data, 'PNG')
    with httpx.Client(base_url=base, headers=headers, timeout=60, trust_env=False) as client:
        readiness = client.get('/v1/readiness')
        readiness.raise_for_status()
        upload = client.post('/v1/assets', files={'file': ('test-fan.png', data.getvalue(), 'image/png')})
        upload.raise_for_status()
        response = client.post('/v1/jobs', headers={'Idempotency-Key': 'smoke-' + str(time.time_ns())}, json={
            'input_asset_id': upload.json()['asset_id'], 'product_name': 'Quạt minh họa - kiểm tra render',
            'mode': 'motion_graphics',
            'tagline': 'Video test local, chưa gọi AI', 'cta': 'Kiểm tra phát video',
            'generate_script': False, 'generate_image': False, 'voice': 'none', 'music': 'synth',
            'duration': 3, 'fps': 12})
        response.raise_for_status()
        job_id = response.json()['job_id']
        for _ in range(120):
            status_response = client.get('/v1/jobs/' + job_id)
            status_response.raise_for_status()
            job = status_response.json()
            if job['status'] in ('done', 'failed'):
                break
            time.sleep(0.5)
        if job['status'] != 'done':
            raise RuntimeError(job.get('error') or 'Job timeout')
        # The path is the same locally and through the tunnel, with signature unchanged.
        from urllib.parse import urlsplit
        url = urlsplit(job['video_url'])
        playback = url.path + '?' + url.query
        full = client.get(playback)
        full.raise_for_status()
        assert full.content[4:8] == b'ftyp'
        partial = client.get(playback, headers={'Range': 'bytes=0-1023'})
        assert partial.status_code == 206 and partial.content == full.content[:1024]
        assert job['result']['storage'] == 'minio'
        remote_size = MinioStorage(settings).stat(job['result']['object_key'])
        assert remote_size == len(full.content)
        (settings.data_dir / 'smoke_video.mp4').write_bytes(full.content)
        report = {'job_id': job_id, 'storage': 'minio', 'bucket': settings.minio_bucket,
                  'bytes': remote_size, 'range_status': partial.status_code, 'openai_calls': 0,
                  'video_url': job['video_url']}
        (settings.data_dir / 'smoke_report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({k: v for k, v in report.items() if k != 'video_url'}, indent=2))


if __name__ == '__main__':
    main()
