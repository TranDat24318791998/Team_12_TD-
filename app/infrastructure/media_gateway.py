"""Backend-only HTTP bridge to the existing media service."""

import asyncio
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx


class MediaError(Exception):
    def __init__(self, code, *, unknown=False):
        super().__init__(code)
        self.code, self.unknown = code, unknown


class MediaGateway:
    def __init__(self, settings, *, client=None):
        self.settings = settings
        self.base = settings.media_api_base_url.rstrip('/')
        parts = urlsplit(self.base)
        if parts.scheme not in {'http', 'https'} or not parts.netloc or parts.path not in ('', '/'):
            raise ValueError('Invalid media service origin')
        self.client = client or httpx.AsyncClient(base_url=self.base, timeout=30, follow_redirects=False)
        self._owns_client = client is None
        self._uploads = {}

    def headers(self, run_id):
        return {'Authorization': 'Bearer ' + self.settings.media_api_token,
                'X-Owner-ID': 'run-' + hashlib.sha256(run_id.encode()).hexdigest()[:32]}

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def preflight(self, product_kind):
        if self.settings.media_mode != 'live' or not self.settings.media_api_token:
            raise MediaError('MEDIA_OFFLINE')
        try:
            response = await self.client.get('/v1/readiness', headers=self.headers('readiness'))
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise MediaError('MEDIA_UNAVAILABLE') from None
        if not (data.get('ready') and data.get('openai_configured') and data.get('muse_configured')
                and data.get('contract_version') == 'growth-media.v1'
                and product_kind in data.get('supported_product_kinds', [])
                and data.get('optional_logo') is True and data.get('bright_background') is True):
            raise MediaError('MEDIA_CAPABILITY_MISSING')

    @staticmethod
    def read_input(path):
        if not path or not Path(path).is_file():
            raise MediaError('MEDIA_INPUT_MISSING')
        path = Path(path)
        if path.stat().st_size > 10 * 1024 * 1024:
            raise MediaError('MEDIA_INPUT_INVALID')
        data = path.read_bytes()
        if not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n')
                or data[:4] == b'RIFF' and data[8:12] == b'WEBP'):
            raise MediaError('MEDIA_INPUT_INVALID')
        return data

    async def upload(self, run_id, data):
        digest = hashlib.sha256(data).hexdigest()
        key = (run_id, digest)
        if key not in self._uploads:
            try:
                response = await self.client.post('/v1/assets', headers=self.headers(run_id),
                                                  files={'file': ('input', data, 'application/octet-stream')})
                response.raise_for_status()
                asset_id = response.json()['asset_id']
            except (httpx.HTTPError, ValueError, KeyError):
                raise MediaError('MEDIA_UPLOAD_FAILED') from None
            if not re.fullmatch(r'[a-f0-9]{32}', asset_id):
                raise MediaError('MEDIA_UPLOAD_FAILED')
            self._uploads[key] = asset_id
        return self._uploads[key]

    async def submit(self, run_id, slot, body, key):
        path = '/v1/jobs' if slot == 'video' else '/v1/image-jobs'
        headers = self.headers(run_id) | {'Idempotency-Key': key}
        uncertain = False
        for attempt in range(2):
            try:
                response = await self.client.post(path, headers=headers, json=body)
            except httpx.RequestError:
                uncertain = True
                if attempt:
                    raise MediaError('MEDIA_SUBMIT_UNKNOWN', unknown=True) from None
                continue
            if response.status_code >= 500:
                raise MediaError('MEDIA_SUBMIT_UNKNOWN', unknown=True)
            if not response.is_success:
                raise MediaError('MEDIA_SUBMIT_UNKNOWN' if uncertain else 'MEDIA_SUBMIT_REJECTED', unknown=uncertain)
            try:
                result = response.json()
                valid = (isinstance(result, dict) and isinstance(result.get('job_id'), str)
                         and re.fullmatch(r'[a-f0-9]{32}', result['job_id'])
                         and result.get('status') in {'queued', 'running', 'done', 'failed'}
                         and (result.get('status') != 'done' or isinstance(result.get('result'), dict))
                         and ('outcome_unknown' not in result or type(result['outcome_unknown']) is bool))
            except (ValueError, TypeError):
                valid = False
            if valid:
                return result
            uncertain = True
            if attempt:
                raise MediaError('MEDIA_SUBMIT_UNKNOWN', unknown=True)

    async def get_job(self, run_id, job_id):
        try:
            response = await self.client.get('/v1/jobs/' + job_id, headers=self.headers(run_id))
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise MediaError('MEDIA_POLL_UNKNOWN', unknown=True) from None

    async def wait(self, run_id, job, deadline):
        while job.get('status') not in {'done', 'failed'}:
            if asyncio.get_running_loop().time() >= deadline:
                raise MediaError('MEDIA_POLL_UNKNOWN', unknown=True)
            await asyncio.sleep(self.settings.media_poll_seconds)
            job = await self.get_job(run_id, job['job_id'])
        if job.get('outcome_unknown'):
            raise MediaError('MEDIA_OUTCOME_UNKNOWN', unknown=True)
        if job.get('status') != 'done':
            raise MediaError('MEDIA_JOB_FAILED')
        return job

    async def download(self, run_id, job, *, video=False):
        result = job.get('result') or {}
        expected_type = 'video/mp4' if video else 'image/jpeg'
        limit = (50 if video else 10) * 1024 * 1024
        digest = result.get('sha256', '')
        size = result.get('size_bytes')
        if (result.get('media_type') != expected_type or not re.fullmatch(r'[a-f0-9]{64}', digest)
                or not isinstance(size, int) or not 0 < size <= limit):
            raise MediaError('MEDIA_RESULT_INVALID')
        expected_path = f"/v1/jobs/{job['job_id']}/play" if video else f"/v1/images/{job['job_id']}/view"
        for attempt in range(2):
            url = urlsplit(job.get('video_url' if video else 'image_url', ''))
            if url.path != expected_path or not url.query:
                raise MediaError('MEDIA_RESULT_INVALID')
            try:
                async with self.client.stream('GET', expected_path + '?' + url.query) as response:
                    if response.status_code == 403 and attempt == 0:
                        job = await self.get_job(run_id, job['job_id'])
                        continue
                    response.raise_for_status()
                    if response.headers.get('content-type', '').split(';')[0] != expected_type:
                        raise MediaError('MEDIA_RESULT_INVALID')
                    chunks, length = [], 0
                    async for chunk in response.aiter_bytes():
                        length += len(chunk)
                        if length > limit or length > size:
                            raise MediaError('MEDIA_RESULT_INVALID')
                        chunks.append(chunk)
                    data = b''.join(chunks)
            except httpx.HTTPError:
                raise MediaError('MEDIA_DOWNLOAD_FAILED') from None
            magic = data[4:8] == b'ftyp' if video else data.startswith(b'\xff\xd8\xff')
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest or not magic:
                raise MediaError('MEDIA_RESULT_INVALID')
            return data
        raise MediaError('MEDIA_DOWNLOAD_FAILED')
