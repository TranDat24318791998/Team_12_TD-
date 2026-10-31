"""Explicit live GPT -> Muse -> MinIO smoke. Existing report resumes polling, never re-submits."""
import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_api.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--new', action='store_true', help='Explicitly create another paid video')
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--job')
    parser.add_argument('--duration', type=int, default=5)
    args = parser.parse_args()
    settings = Settings.load()
    report_path = settings.data_dir / 'muse_smoke_report.json'
    headers = {'Authorization': 'Bearer ' + settings.video_api_token.get_secret_value(), 'X-Owner-ID': 'local-demo'}
    with httpx.Client(base_url='http://127.0.0.1:8010', headers=headers, timeout=90, trust_env=False) as client:
        job_id = args.job
        if not job_id and report_path.exists() and not args.new:
            job_id = json.loads(report_path.read_text())['job_id']
        if not job_id:
            ready = client.get('/v1/readiness')
            ready.raise_for_status()
            assert ready.json()['muse_configured'] and ready.json()['openai_configured'], 'Thiếu cấu hình API key'
            asset_id = None
            if args.reference:
                response = client.post('/v1/assets', files={'file': (args.reference.name, args.reference.read_bytes(), 'image/webp')})
                response.raise_for_status()
                asset_id = response.json()['asset_id']
            response = client.post('/v1/jobs', headers={'Idempotency-Key': 'gpt-muse-demo-' + str(time.time_ns())}, json={
                'mode': 'muse', 'input_asset_id': asset_id, 'product_name': 'Quạt để bàn màu trắng',
                'product_description': 'Một chiếc quạt để bàn màu trắng, lồng bảo vệ tròn, ba cánh màu trắng, chân đế tròn. Một mẫu và một chiếc duy nhất.',
                'presenter': 'Một phụ nữ Việt Nam trưởng thành khoảng 28 tuổi, áo màu be, giới thiệu tự nhiên, cử chỉ tay chân thực.',
                'setting': 'Góc làm việc tại nhà, bàn gỗ sáng, ánh sáng ban ngày từ cửa sổ, không có bất kỳ quạt hay sản phẩm khác.',
                'verified_facts': [], 'script': '', 'generate_script': True, 'generate_image': False,
                'duration': args.duration, 'aspect': '9:16', 'voice': 'muse', 'music': 'none'})
            response.raise_for_status()
            job_id = response.json()['job_id']
            report_path.write_text(json.dumps({'job_id': job_id, 'status': 'submitted'}, indent=2))
        print('Job:', job_id, flush=True)
        last = None
        deadline = time.monotonic() + settings.muse_timeout_seconds + 300
        while time.monotonic() < deadline:
            response = client.get('/v1/jobs/' + job_id)
            response.raise_for_status()
            job = response.json()
            report_path.write_text(json.dumps(job, ensure_ascii=False, indent=2))
            if job['stage'] != last:
                print('Stage:', job['stage'], flush=True)
                last = job['stage']
            if job['status'] in ('done', 'failed'):
                break
            time.sleep(3)
        if job['status'] != 'done':
            raise SystemExit(job.get('error') or 'Chưa hoàn tất; chạy lại script để tiếp tục theo dõi cùng job')
        link = urlsplit(job['video_url'])
        video = client.get(link.path + '?' + link.query)
        video.raise_for_status()
        (settings.data_dir / 'muse_sample.mp4').write_bytes(video.content)
        seek = client.get(link.path + '?' + link.query, headers={'Range': 'bytes=0-1023'})
        assert seek.status_code == 206
        print(json.dumps({'job_id': job_id, 'status': job['status'], 'bytes': len(video.content),
                          'storage': job['result']['storage'], 'range_status': seek.status_code,
                          'muse_task_id': job['result']['muse_task_id'],
                          'visual_review': job['result']['visual_review'],
                          'watch_url': job['watch_url']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
