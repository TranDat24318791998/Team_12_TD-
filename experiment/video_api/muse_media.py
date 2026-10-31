"""Use the supplied MuseClient; restrict authenticated downloads to its gateway."""
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from muse.muse_client import MuseAPIError, MuseClient, MuseError, MuseTaskFailed
from muse.muse_client import _extract_task_id, file_to_data_url, find_media_urls, task_status


class SafeSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs['allow_redirects'] = False
        response = super().request(method, url, **kwargs)
        if 300 <= response.status_code < 400:
            response.close()
            raise MuseError('Gateway redirect bị chặn; không chuyển Bearer sang địa chỉ khác')
        return response


class MuseMedia:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or MuseClient(
            api_key=settings.muse_api_key.get_secret_value(), base_url=settings.muse_api_base_url,
            request_timeout=20, session=SafeSession())

    def generate(self, prompt, *, image, duration, aspect, idempotency_key, work, on_task, on_update):
        params = dict(model=self.settings.muse_video_model, duration=int(duration), aspect_ratio=aspect,
                      resolution='720p', timeout=self.settings.muse_timeout_seconds,
                      idempotency_key=idempotency_key)
        if image:
            params['image'] = file_to_data_url(image)
        created = self.client.create_video(prompt, **params)
        task_id = _extract_task_id(created)
        if not task_id:
            raise MuseError('Muse không trả task_id; không tự submit lại')
        # Persist the task before polling, so interruption never loses the remote id.
        on_task(task_id)
        on_update('muse_queued')
        deadline = time.monotonic() + self.settings.muse_timeout_seconds + 90
        while True:
            try:
                task = self.client.get_video(task_id)
                state = task_status(task)
                if state in {'completed', 'complete', 'succeeded', 'success', 'done', 'finished'}:
                    break
                if state in {'failed', 'failure', 'error', 'cancelled', 'canceled', 'expired', 'timeout'}:
                    raise MuseTaskFailed(task)
                on_update('muse_generating')
            except MuseAPIError as exc:
                if exc.status_code < 500 and exc.status_code != 429:
                    raise
            except requests.RequestException:
                pass  # Poll GET can retry; the paid POST is never retried here.
            if time.monotonic() + self.settings.muse_poll_seconds >= deadline:
                raise TimeoutError('Muse chưa hoàn tất; giữ task_id để tra cứu, không submit lại')
            time.sleep(self.settings.muse_poll_seconds)
        candidates = find_media_urls(task)
        video_candidates = [value for value in candidates
                            if urlsplit(value).path.lower().endswith(('.mp4', '.mov', '.webm', '.m4v'))]
        candidates = video_candidates or candidates
        if not candidates:
            raise MuseError('Muse completed nhưng không có media; không báo done')
        output = self.download(candidates[0], work / 'muse-source.mp4')
        # Save only known transport fields, never echoed image data / prompts / tokens.
        return output, {'task_id': task_id, 'status': task_status(task)}

    def download(self, name_or_url, output: Path):
        url = self.client.media_url(name_or_url)
        target, origin = urlsplit(url), urlsplit(self.client.base_url)
        if (target.scheme, target.netloc) != (origin.scheme, origin.netloc) or not target.path.startswith('/v1/media/'):
            raise MuseError('Chỉ tải media từ cùng origin Muse Gateway tại /v1/media/')
        temp = output.with_suffix('.part')
        try:
            with self.client.session.get(url, headers=self.client._auth_headers(), stream=True,
                                         timeout=(10, 60), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise MuseAPIError(response.status_code, 'Không tải được media')
                total = 0
                with temp.open('wb') as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        total += len(chunk)
                        if total > 150 * 1024 * 1024:
                            raise MuseError('Media vượt giới hạn 150MB')
                        stream.write(chunk)
            temp.replace(output)
            return output
        finally:
            temp.unlink(missing_ok=True)
