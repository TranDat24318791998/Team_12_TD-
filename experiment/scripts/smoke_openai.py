"""Explicit paid smoke: one structured plan + one speech call, image generation opt-in."""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_api.config import Settings
from video_api.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path)
    parser.add_argument('--generate-image', action='store_true')
    args = parser.parse_args()
    settings = Settings.load()
    if not settings.openai_api_key.get_secret_value():
        raise SystemExit('Chưa có OPENAI_API_KEY')
    source = args.image
    if not source:
        report = json.loads((settings.data_dir / 'smoke_report.json').read_text())
        store = Store(settings.data_dir)
        previous = store.job(report['job_id'])
        asset = store.asset(json.loads(previous['request'])['input_asset_id'], previous['owner'])
        source = Path(asset['path'])
    headers = {'Authorization': 'Bearer ' + settings.video_api_token.get_secret_value(), 'X-Owner-ID': 'openai-smoke'}
    with httpx.Client(base_url='http://127.0.0.1:8010', headers=headers, timeout=120, trust_env=False) as client:
        asset = client.post('/v1/assets', files={'file': ('reference.png', source.read_bytes(), 'image/png')})
        asset.raise_for_status()
        response = client.post('/v1/jobs', headers={'Idempotency-Key': 'openai-smoke-' + str(time.time_ns())}, json={
            'input_asset_id': asset.json()['asset_id'], 'product_name': 'Quạt để bàn - bản minh họa',
            'mode': 'motion_graphics',
            'verified_facts': [], 'script': 'Một góc làm việc dễ chịu, bắt đầu từ những lựa chọn nhỏ. Khám phá quạt để bàn phù hợp với bạn.',
            'tagline': 'Bản thử nghiệm nội dung và giọng đọc AI', 'cta': 'Tìm hiểu sản phẩm',
            'generate_script': True, 'generate_image': args.generate_image, 'voice': 'openai',
            'music': 'synth', 'duration': 12, 'fps': 24})
        response.raise_for_status()
        job = response.json()
        print('Submitted job', job['job_id'], flush=True)
        last_stage = None
        for _ in range(240):
            result = client.get('/v1/jobs/' + job['job_id'])
            result.raise_for_status()
            job = result.json()
            if job['stage'] != last_stage:
                print('Stage:', job['stage'], flush=True)
                last_stage = job['stage']
            if job['status'] in ('done', 'failed'):
                break
            time.sleep(2)
        report_path = settings.data_dir / 'openai_smoke_report.json'
        report_path.write_text(json.dumps(job, ensure_ascii=False, indent=2))
        if job['status'] != 'done':
            raise SystemExit(job.get('error') or 'Job chưa hoàn tất; xem trạng thái trước khi gửi lại')
        from urllib.parse import urlsplit
        link = urlsplit(job['video_url'])
        video = client.get(link.path + '?' + link.query)
        video.raise_for_status()
        (settings.data_dir / 'openai_sample.mp4').write_bytes(video.content)
        print(json.dumps({'status': job['status'], 'job_id': job['job_id'], 'storage': job['result']['storage'],
                          'bytes': len(video.content), 'ai_voice': job['result']['ai_voice'],
                          'image_generation': args.generate_image}, indent=2))


if __name__ == '__main__':
    main()
