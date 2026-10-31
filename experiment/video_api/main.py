import asyncio
import fcntl
import hashlib
import hmac
import json
import logging
import re
import threading
import time
from html import escape
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError

from .config import ROOT, Settings
from .models import VideoRequest, ImageRequest, ImageStyle
from .pipeline import process_job
from .storage import create_storage
from .store import Conflict, QueueFull, Store

LOG = logging.getLogger('video_api')
Image.MAX_IMAGE_PIXELS = 16_000_000


def parse_range(value, size):
    if not value:
        return 0, size - 1, False
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError('Invalid range')
    left, right = match.groups()
    if left:
        start, end = int(left), min(int(right), size - 1) if right else size - 1
        if start >= size or start > end:
            raise ValueError('Unsatisfiable range')
    else:
        if int(right) == 0:
            raise ValueError('Invalid suffix')
        start, end = max(0, size - int(right)), size - 1
    return start, end, True


def playback_signature(settings, job_id, expires):
    return hmac.new(settings.playback_secret.get_secret_value().encode(),
                    f'play:{job_id}:{expires}'.encode(), hashlib.sha256).hexdigest()


def create_app(settings=None, storage=None, processor=process_job, worker_enabled=True):
    settings = settings or Settings.load()
    store = Store(settings.data_dir)
    storage = storage or create_storage(settings)
    stopping = threading.Event()

    def work():
        while not stopping.is_set():
            row = store.claim()
            if not row:
                stopping.wait(0.25)
                continue
            try:
                processor(settings, store, storage, row)
            except Exception as exc:
                # Only local logs contain stack information; no provider response/keys sent to clients.
                LOG.error('Video job %s failed (%s)', row['id'], type(exc).__name__)
                status_code = getattr(exc, 'status_code', None)
                safe_hint = f' Provider HTTP {status_code}.' if isinstance(status_code, int) else f' Loại lỗi: {type(exc).__name__}.'
                store.update(row['id'], status='failed', stage='failed', error=(
                    'Không hoàn tất video. Kiểm tra cấu hình model, quyền API, MinIO và media đầu vào. '
                    'Không tự gọi lại OpenAI; có thể tạo yêu cầu mới sau khi kiểm tra.' + safe_hint))

    @asynccontextmanager
    async def lifespan(app):
        if len(settings.video_api_token.get_secret_value()) < 24 or len(settings.playback_secret.get_secret_value()) < 24:
            raise RuntimeError('Chạy python scripts/init_config.py để tạo token và playback secret trước khi mở API')
        lock = None
        thread = None
        if worker_enabled:
            lock = (settings.data_dir / 'worker.lock').open('a')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                raise RuntimeError('Chỉ chạy một worker/API process cho mỗi DATA_DIR')
            store.recover()
            thread = threading.Thread(target=work, name='video-worker', daemon=True)
            thread.start()
        try:
            yield
        finally:
            stopping.set()
            if thread:
                await asyncio.to_thread(thread.join, 5)
            if lock:
                # Keep process lock until a running job finishes or process exits.
                if thread and thread.is_alive():
                    app.state.worker_lock = lock
                else:
                    lock.close()

    app = FastAPI(title='Video Marketing Experiment', version='0.1.0', lifespan=lifespan)
    app.state.store, app.state.settings, app.state.storage = store, settings, storage


    @app.middleware('http')
    async def request_boundary(request, call_next):
        # Authenticate before parsing multipart bodies. Public playback uses a separate short-lived signature.
        path = request.url.path
        public_media = bool(re.fullmatch(r'/v1/jobs/[a-f0-9]{32}/play|/v1/images/[a-f0-9]{32}/view', path))
        if request.method != 'OPTIONS' and path.startswith('/v1/') and not public_media:
            expected = settings.video_api_token.get_secret_value()
            token = request.headers.get('authorization', '')
            if not expected or not hmac.compare_digest(token, 'Bearer ' + expected):
                return JSONResponse({'detail': 'Không có quyền truy cập'}, status_code=401)
        if path in ('/v1/assets', '/v1/images', '/v1/videos'):
            length = request.headers.get('content-length')
            limit = settings.max_upload_mb * 1024 * 1024 * (3 if path == '/v1/images' else 1) + 1024 * 1024
            try:
                if length is None or int(length) > limit:
                    return JSONResponse({'detail': 'Cần Content-Length trong giới hạn upload'}, status_code=413)
            except ValueError:
                return JSONResponse({'detail': 'Content-Length không hợp lệ'}, status_code=400)
        return await call_next(request)

    # Outer CORS layer also covers authentication and upload-limit responses.
    app.add_middleware(CORSMiddleware,
                       allow_origins=[o.strip() for o in settings.cors_origins.split(',') if o.strip()],
                       allow_methods=['*'],
                       allow_headers=['*'], allow_credentials=False,
                       expose_headers=['Content-Range', 'Accept-Ranges', 'Content-Length', 'Content-Disposition', 'Retry-After'])

    bearer = HTTPBearer(auto_error=False, scheme_name='VideoApiToken', description='VIDEO_API_TOKEN, không phải OpenAI/Muse key')

    def owner(x_owner_id: str = Header(default='local-demo'),
              credential: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', x_owner_id):
            raise HTTPException(400, 'X-Owner-ID không hợp lệ')
        # Trusted Sites server derives this from its authenticated user; never trust browser-supplied owner IDs there.
        return x_owner_id

    def find_job(job_id, identity):
        row = store.job(job_id, identity)
        if not row:
            raise HTTPException(404, 'Không tìm thấy job')
        return row

    def job_view(row, request):
        result = json.loads(row['result']) if row['result'] else None
        response = {'job_id': row['id'], 'status': row['status'], 'stage': row['stage'],
                    'error': row['error'], 'result': result, 'created_at': row['created'], 'updated_at': row['updated']}
        if row['status'] == 'done':
            expires = int(time.time()) + settings.playback_ttl_seconds
            base = (settings.public_base_url or str(request.base_url)).rstrip('/')
            signature = playback_signature(settings, row['id'], expires)
            if result.get('media_type') == 'image/jpeg':
                response.update(image_url=f"{base}/v1/images/{row['id']}/view?expires={expires}&signature={signature}",
                                image_url_expires_at=expires, asset_id=result['asset_id'])
                return response
            response.update(video_url=f"{base}/v1/jobs/{row['id']}/play?expires={expires}&signature={signature}",
                            watch_url=f"{base}/watch/{row['id']}?expires={expires}&signature={signature}",
                            video_url_expires_at=expires)
        return response

    @app.get('/health')
    def health():
        return {'ok': True, 'openai_configured': bool(settings.openai_api_key.get_secret_value()),
                'muse_configured': bool(settings.muse_api_key.get_secret_value()),
                'storage': settings.storage_backend, 'storage_configured': settings.storage_ready(),
                'local_motion_enabled': settings.local_motion_enabled}

    @app.get('/')
    def lab():
        return FileResponse(ROOT / 'web/index.html')

    @app.get('/v1/readiness')
    def readiness(identity=Depends(owner)):
        try:
            if not settings.storage_ready():
                raise RuntimeError('Missing storage configuration')
            if hasattr(storage, 'check'):
                storage.check()
        except Exception:
            raise HTTPException(503, 'MinIO chưa sẵn sàng; kiểm tra endpoint, credentials, bucket')
        return {'ready': True, 'storage': settings.storage_backend,
                'openai_configured': bool(settings.openai_api_key.get_secret_value()),
                'muse_configured': bool(settings.muse_api_key.get_secret_value())}

    @app.post('/v1/assets', status_code=201)
    async def upload(file: UploadFile = File(...), identity=Depends(owner)):
        asset_id = uuid4().hex
        path = settings.data_dir / 'assets' / f'{asset_id}.upload'
        size = 0
        try:
            with path.open('wb') as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, 'File vượt giới hạn upload')
                    output.write(chunk)
            with path.open('rb') as stream:
                signature = stream.read(16)
            kind = None
            if signature.startswith((b'\x89PNG', b'\xff\xd8\xff')) or (signature[:4] == b'RIFF' and signature[8:12] == b'WEBP'):
                normalized = path.with_suffix('.png')
                try:
                    with Image.open(path) as image:
                        image.load()
                        if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                            raise HTTPException(413, 'Ảnh quá lớn')
                        image = __import__('PIL.ImageOps', fromlist=['exif_transpose']).exif_transpose(image)
                        image.thumbnail((1600, 1600))
                        image.convert('RGB').save(normalized)
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                    raise HTTPException(415, 'File ảnh không hợp lệ')
                path.unlink()
                path, kind = normalized, 'image'
            elif signature[4:8] == b'ftyp':
                normalized = path.with_suffix('.mp4')
                path.rename(normalized)
                path, kind = normalized, 'video'
                # Decode one frame now to reject broken containers before queueing a paid job.
                from .render import extract_frame
                try:
                    await asyncio.to_thread(extract_frame, settings, path, path.with_suffix('.check.png'))
                except Exception:
                    raise HTTPException(415, 'Video MP4/MOV không giải mã được')
                finally:
                    path.with_suffix('.check.png').unlink(missing_ok=True)
            elif signature.startswith((b'ID3', b'RIFF', b'fLaC')) or (len(signature) > 1 and signature[0] == 255 and signature[1] & 224 == 224):
                normalized = path.with_suffix('.audio')
                path.rename(normalized)
                path, kind = normalized, 'audio'
            else:
                raise HTTPException(415, 'Chỉ nhận PNG/JPEG/WebP, MP4/MOV, WAV/MP3/FLAC')
            store.add_asset(asset_id, identity, kind, path)
            return {'asset_id': asset_id, 'kind': kind, 'size_bytes': path.stat().st_size}
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.post('/v1/jobs', status_code=202)
    def submit(payload: VideoRequest, request: Request,
               idempotency_key: str = Header(..., min_length=8, max_length=120), identity=Depends(owner)):
        primary = store.asset(payload.input_asset_id, identity) if payload.input_asset_id else None
        if payload.input_asset_id and not primary:
            raise HTTPException(404, 'Không tìm thấy asset đầu vào')
        required_kind = 'video' if payload.mode == 'source_video' else 'image'
        if primary and primary['kind'] != required_kind:
            raise HTTPException(422, f'mode={payload.mode} cần asset loại {required_kind}')
        for asset_id in (payload.voice_asset_id, payload.music_asset_id):
            if asset_id:
                asset = store.asset(asset_id, identity)
                if not asset or asset['kind'] != 'audio':
                    raise HTTPException(422, 'Không tìm thấy audio asset thuộc người dùng')
        if not settings.storage_ready():
            raise HTTPException(503, 'Điền cấu hình MinIO trước khi tạo job')
        if (payload.generate_script or payload.generate_image or payload.voice == 'openai') and not settings.openai_api_key.get_secret_value():
            raise HTTPException(503, 'Chưa cấu hình OPENAI_API_KEY trong experiment/.env')
        if payload.mode == 'muse' and not settings.muse_api_key.get_secret_value():
            raise HTTPException(503, 'Chưa cấu hình MUSE_API_KEY trong experiment/.env hoặc experiment/muse/.env')
        if payload.mode == 'local_i2v' and (not settings.local_motion_enabled or not (settings.local_motion_model / 'model_index.json').is_file()):
            raise HTTPException(503, 'Model chuyển động local chưa được bật/cài; không tự thay bằng ảnh zoom')
        data = payload.model_dump()
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        try:
            row, created = store.create(identity, idempotency_key, digest, data, settings.max_pending_jobs)
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except QueueFull as exc:
            raise HTTPException(429, str(exc), headers={'Retry-After': '10'})
        return job_view(row, request) | {'reused': not created}

    @app.get('/v1/image-styles')
    def image_styles(identity=Depends(owner)):
        from .image_pipeline import STYLES
        return {'styles': [{'id': key, **value} for key, value in STYLES.items()]}

    @app.post('/v1/image-jobs', status_code=202)
    def submit_image(payload: ImageRequest, request: Request,
                     idempotency_key: str = Header(..., min_length=8, max_length=120), identity=Depends(owner)):
        for asset_id in (payload.logo_asset_id, payload.product_asset_id, payload.style_asset_id):
            if asset_id:
                asset = store.asset(asset_id, identity)
                if not asset or asset['kind'] != 'image':
                    raise HTTPException(422, 'Logo/sản phẩm/style cần là ảnh thuộc người dùng')
        if not settings.openai_api_key.get_secret_value() or not settings.storage_ready():
            raise HTTPException(503, 'Cần cấu hình OpenAI và MinIO')
        data = payload.model_dump()
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        try:
            row, created = store.create(identity, idempotency_key, digest, data, settings.max_pending_jobs)
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except QueueFull as exc:
            raise HTTPException(429, str(exc))
        return job_view(row, request) | {'reused': not created}

    @app.post('/v1/images', summary='Upload logo + sản phẩm + style → tạo JPG và lưu MinIO')
    async def generate_image(request: Request, logo: UploadFile = File(...), product: UploadFile = File(...),
                             style: ImageStyle = Form(...), style_reference: UploadFile | None = File(None),
                             wait: bool = True,
                             idempotency_key: str = Header(..., min_length=8, max_length=120), identity=Depends(owner)):
        # Check before uploading again: never turn a client retry into another paid generation.
        import hashlib as hashes
        files = [logo, product] + ([style_reference] if style_reference else [])
        contents = []
        try:
            for file in files:
                content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
                if len(content) > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, 'File vượt giới hạn upload')
                contents.append(content)
                await file.seek(0)
            fingerprint = hashes.sha256(style.encode() + b''.join(hashes.sha256(x).digest() for x in contents)).hexdigest()
            # Store original content hashes, not randomized upload IDs, for multipart idempotency.
            existing = store.existing(identity, idempotency_key)
            if existing:
                if json.loads(existing['request']).get('upload_fingerprint') != fingerprint:
                    raise HTTPException(409, 'Idempotency-Key đã dùng với nội dung khác')
                row = existing
            else:
                ids = []
                for file in files:
                    asset = await upload(file, identity)
                    if asset['kind'] != 'image':
                        raise HTTPException(422, 'Chỉ nhận file ảnh')
                    ids.append(asset['asset_id'])
                payload = ImageRequest(logo_asset_id=ids[0], product_asset_id=ids[1], style=style,
                                       style_asset_id=ids[2] if len(ids) > 2 else None)
                data = payload.model_dump() | {'upload_fingerprint': fingerprint}
                if not settings.openai_api_key.get_secret_value() or not settings.storage_ready():
                    raise HTTPException(503, 'Cần cấu hình OpenAI và MinIO')
                try:
                    row, _ = store.create(identity, idempotency_key, fingerprint, data, settings.max_pending_jobs)
                except Conflict as exc:
                    raise HTTPException(409, str(exc))
                except QueueFull as exc:
                    raise HTTPException(429, str(exc))
            deadline = time.monotonic() + (80 if wait else 0)
            while row['status'] not in ('done', 'failed') and time.monotonic() < deadline:
                await asyncio.sleep(0.3)
                row = store.job(row['id'], identity)
            return JSONResponse(job_view(row, request), status_code=200 if row['status'] == 'done' else 202)
        finally:
            for file in files:
                await file.close()

    @app.api_route('/v1/images/{job_id}/view', methods=['GET', 'HEAD'])
    def view_image(job_id: str, request: Request, expires: int, signature: str):
        if expires < time.time() or not hmac.compare_digest(signature, playback_signature(settings, job_id, expires)):
            raise HTTPException(403, 'Link ảnh hết hạn hoặc không hợp lệ')
        row = store.job(job_id)
        result = json.loads(row['result']) if row and row['result'] else {}
        if not row or row['status'] != 'done' or result.get('media_type') != 'image/jpeg':
            raise HTTPException(404, 'Ảnh chưa sẵn sàng')
        key = result['object_key']
        try:
            size = storage.stat(key)
        except Exception:
            raise HTTPException(503, 'Không đọc được ảnh từ storage')
        headers = {'Content-Length': str(size), 'Cache-Control': 'private, no-store',
                   'Referrer-Policy': 'no-referrer', 'Content-Disposition': 'inline; filename="image.jpg"'}
        if request.method == 'HEAD':
            return Response(headers=headers, media_type='image/jpeg')
        return StreamingResponse(storage.chunks(key, 0, size), headers=headers, media_type='image/jpeg')

    @app.get('/v1/jobs')
    def list_jobs(request: Request, identity=Depends(owner)):
        return {'jobs': [job_view(row, request) for row in store.jobs(identity)]}

    @app.post('/v1/videos', status_code=202, summary='Upload một ảnh quảng cáo → GPT phân tích và Muse tạo video')
    async def create_video(request: Request, image: UploadFile = File(...),
                           output_type: Literal['chibi_3d', 'realistic_human'] = Form(...),
                           duration: int = Form(5, description='5, 10 hoặc 15 giây'),
                           product_name: str = Form('Quạt để bàn', max_length=90),
                           idempotency_key: str = Header(..., min_length=8, max_length=120), identity=Depends(owner)):
        if duration not in (5, 10, 15):
            raise HTTPException(422, 'Thời lượng chỉ nhận 5, 10 hoặc 15 giây')
        # Normalize before hashing: uploads use random IDs, their content is stable across retries.
        import io
        from PIL.ImageOps import exif_transpose
        content = await image.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, 'File vượt giới hạn upload')
        try:
            with Image.open(io.BytesIO(content)) as source:
                source.load()
                if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                    raise HTTPException(413, 'Ảnh quá lớn')
                normalized = exif_transpose(source).convert('RGB')
                normalized.thumbnail((1600, 1600))
                buffer = io.BytesIO()
                normalized.save(buffer, format='PNG')
                normalized_bytes = buffer.getvalue()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(415, 'Cần upload một ảnh JPEG/PNG/WebP hợp lệ')
        finally:
            await image.close()
        old = store.existing(identity, idempotency_key)
        if old:
            previous = json.loads(old['request'])
            asset = store.asset(previous.get('input_asset_id'), identity)
            same_image = asset and hashlib.sha256(Path(asset['path']).read_bytes()).digest() == hashlib.sha256(normalized_bytes).digest()
            if not same_image or any(previous.get(k) != v for k, v in {
                'output_type': output_type, 'duration': duration, 'product_name': product_name}.items()):
                raise HTTPException(409, 'Idempotency-Key đã dùng với nội dung khác')
            return job_view(old, request) | {'reused': True}
        asset_id = uuid4().hex
        path = settings.data_dir / 'assets' / f'{asset_id}.png'
        path.write_bytes(normalized_bytes)
        store.add_asset(asset_id, identity, 'image', path)
        payload = VideoRequest(input_asset_id=asset_id, output_type=output_type,
                               duration=duration, product_name=product_name)
        return submit(payload, request, idempotency_key, identity)

    @app.get('/v1/jobs/{job_id}')
    def status(job_id: str, request: Request, identity=Depends(owner)):
        return job_view(find_job(job_id, identity), request)

    @app.get('/watch/{job_id}', response_class=HTMLResponse)
    def watch(job_id: str, expires: int, signature: str):
        if expires < time.time() or not hmac.compare_digest(signature, playback_signature(settings, job_id, expires)):
            raise HTTPException(403, 'Link xem video không hợp lệ hoặc hết hạn')
        row = store.job(job_id)
        if not row or row['status'] != 'done':
            raise HTTPException(404, 'Video chưa sẵn sàng')
        result = json.loads(row['result'])
        video = f'/v1/jobs/{job_id}/play?expires={expires}&signature={signature}'
        script = escape(result.get('script', ''))
        label = 'GPT viết kịch bản · Muse tạo video · MinIO lưu trữ' if result.get('mode') == 'muse' else 'Video thử nghiệm'
        html = ('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta name="referrer" content="no-referrer"><title>Video quảng cáo quạt để bàn</title>'
                '<style>body{font:17px system-ui;background:#102037;color:white;margin:0;padding:32px}'
                'main{max-width:1000px;margin:auto}video{width:100%;height:70vh;background:#000;border-radius:16px}'
                'p{line-height:1.6;color:#dae3ef}a{color:#95cdfa}</style>'
                f'<main><h1>Video marketing: một sản phẩm quạt để bàn</h1><p>{label}</p>'
                f'<video controls playsinline preload="metadata" src="{escape(video, quote=True)}"></video>'
                f'<p><strong>Script:</strong> {script}</p>'
                f'<p>Thời lượng thực tế: {result.get("duration_seconds", "?")} giây. Bản demo cần người bán duyệt.</p>'
                f'<p><a href="{escape(video, quote=True)}">Mở MP4 trực tiếp</a></p></main></html>')
        return HTMLResponse(html, headers={'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer'})

    @app.api_route('/v1/jobs/{job_id}/play', methods=['GET', 'HEAD'])
    def play(job_id: str, request: Request, expires: int, signature: str):
        if expires < time.time() or not hmac.compare_digest(signature, playback_signature(settings, job_id, expires)):
            raise HTTPException(403, 'Link video không hợp lệ hoặc đã hết hạn')
        row = store.job(job_id)
        if not row or row['status'] != 'done':
            raise HTTPException(404, 'Video chưa sẵn sàng')
        key = json.loads(row['result'])['object_key']
        try:
            size = storage.stat(key)
        except Exception:
            raise HTTPException(503, 'Không đọc được video từ storage')
        try:
            start, end, partial = parse_range(request.headers.get('range'), size)
        except ValueError:
            return Response(status_code=416, headers={'Content-Range': f'bytes */{size}'})
        headers = {'Accept-Ranges': 'bytes', 'Content-Length': str(end - start + 1),
                   'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer',
                   'Content-Disposition': 'inline; filename="video.mp4"'}
        if partial:
            headers['Content-Range'] = f'bytes {start}-{end}/{size}'
        if request.method == 'HEAD':
            return Response(status_code=206 if partial else 200, headers=headers, media_type='video/mp4')
        return StreamingResponse(storage.chunks(key, start, end - start + 1),
                                 status_code=206 if partial else 200, headers=headers, media_type='video/mp4')

    return app


app = create_app()
