"""Start a private local MinIO using credentials from this experiment's .env."""
import os
import shutil
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_api.config import Settings


def main():
    settings = Settings.load()
    executable = shutil.which('minio') or '/opt/homebrew/bin/minio'
    if not Path(executable).is_file():
        raise SystemExit('Chưa cài MinIO. Cài: brew install minio')
    if settings.minio_endpoint not in ('localhost:9000', '127.0.0.1:9000') or settings.minio_secure:
        raise SystemExit('Script này chỉ khởi động MinIO HTTP local:9000; không thay cấu hình server khác.')
    for port in (9000, 9001):
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise SystemExit(f'Cổng {port} đang được dùng; không khởi động thêm MinIO.')
    if not settings.minio_access_key.get_secret_value() or not settings.minio_secret_key.get_secret_value():
        raise SystemExit('Chạy scripts/init_config.py hoặc điền MinIO credentials trong .env')
    data = settings.data_dir / 'minio'
    data.mkdir(parents=True, exist_ok=True)
    env = os.environ | {'MINIO_ROOT_USER': settings.minio_access_key.get_secret_value(),
                       'MINIO_ROOT_PASSWORD': settings.minio_secret_key.get_secret_value(),
                       'MINIO_BROWSER_REDIRECT_URL': 'http://127.0.0.1:9001'}
    print('MinIO API: http://127.0.0.1:9000', flush=True)
    print('MinIO Console: http://127.0.0.1:9001', flush=True)
    print('Credentials nằm trong experiment/.env; dữ liệu trong experiment/data/minio.', flush=True)
    log_fd = os.open(settings.data_dir / 'minio.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)
    os.close(log_fd)
    os.execvpe(executable, [executable, '--quiet', 'server', '--address', '127.0.0.1:9000',
                          '--console-address', '127.0.0.1:9001', str(data)], env)


if __name__ == '__main__':
    main()
