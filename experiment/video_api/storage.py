from pathlib import Path
import shutil
import mimetypes
import tempfile

import urllib3
from minio import Minio


class LocalStorage:
    """Explicit offline test mode, not reported as MinIO upload."""
    def __init__(self, root):
        self.root = Path(root) / 'objects'
        self.root.mkdir(exist_ok=True)

    def check(self):
        with tempfile.NamedTemporaryFile(prefix='.readiness-', dir=self.root, mode='w+b') as probe:
            probe.write(b'local-storage-check')
            probe.flush()
            probe.seek(0)
            if probe.read() != b'local-storage-check':
                raise OSError('Local storage probe failed')

    def put(self, key, path):
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)

    def stat(self, key):
        return (self.root / key).stat().st_size

    def chunks(self, key, offset, length):
        with (self.root / key).open('rb') as stream:
            stream.seek(offset)
            remaining = length
            while remaining:
                data = stream.read(min(256 * 1024, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data


class MinioStorage:
    def __init__(self, settings):
        self.bucket = settings.minio_bucket
        self.create_bucket = settings.minio_create_bucket
        self.client = Minio(settings.minio_endpoint,
                            access_key=settings.minio_access_key.get_secret_value(),
                            secret_key=settings.minio_secret_key.get_secret_value(),
                            secure=settings.minio_secure,
                            http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=60), retries=False))

    def check(self):
        if not self.client.bucket_exists(self.bucket):
            if not self.create_bucket:
                raise RuntimeError('Bucket chưa tồn tại; tạo bucket hoặc bật MINIO_CREATE_BUCKET')
            self.client.make_bucket(self.bucket)

    def put(self, key, path):
        self.client.fput_object(self.bucket, key, str(path), content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream')

    def stat(self, key):
        return self.client.stat_object(self.bucket, key).size

    def chunks(self, key, offset, length):
        response = self.client.get_object(self.bucket, key, offset=offset, length=length)
        try:
            yield from response.stream(256 * 1024)
        finally:
            response.close()
            response.release_conn()


def create_storage(settings):
    if settings.storage_backend == 'local':
        return LocalStorage(settings.data_dir)
    return MinioStorage(settings)
