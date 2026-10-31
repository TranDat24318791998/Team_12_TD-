"""Create local secrets without printing them, and never overwrite existing values."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / '.env'
if path.exists():
    print('Giữ nguyên .env hiện có; không ghi đè secrets.')
else:
    text = (ROOT / '.env.example').read_text()
    text = text.replace('VIDEO_API_TOKEN=\n', f'VIDEO_API_TOKEN={secrets.token_urlsafe(32)}\n')
    text = text.replace('PLAYBACK_SECRET=\n', f'PLAYBACK_SECRET={secrets.token_urlsafe(48)}\n')
    text = text.replace('MINIO_ACCESS_KEY=\n', 'MINIO_ACCESS_KEY=video-lab\n')
    text = text.replace('MINIO_SECRET_KEY=\n', f'MINIO_SECRET_KEY={secrets.token_urlsafe(36)}\n')
    text = text.replace('MINIO_CREATE_BUCKET=false', 'MINIO_CREATE_BUCKET=true')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(text)
    print('Đã tạo experiment/.env (quyền 600). Điền OPENAI_API_KEY và credentials MinIO trên máy.')
