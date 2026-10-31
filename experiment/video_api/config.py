import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    openai_api_key: SecretStr = SecretStr('')
    openai_text_model: str = 'gpt-6-luna'
    openai_image_model: str = 'gpt-image-2.5-flare'
    openai_tts_model: str = 'gpt-4o-mini-tts'
    openai_tts_voice: str = 'coral'
    muse_api_key: SecretStr = SecretStr('')
    muse_api_base_url: str = 'https://muse-api.butterflyro.space'
    muse_video_model: str = 'muse-video'
    muse_timeout_seconds: int = Field(default=300, ge=30, le=1800)
    muse_poll_seconds: float = Field(default=5, ge=1, le=30)
    video_api_token: SecretStr = SecretStr('')
    playback_secret: SecretStr = SecretStr('')
    public_base_url: str = ''
    cors_origins: str = '*'
    storage_backend: Literal['minio', 'local'] = 'minio'
    minio_endpoint: str = 'localhost:9000'
    minio_secure: bool = False
    minio_access_key: SecretStr = SecretStr('')
    minio_secret_key: SecretStr = SecretStr('')
    minio_bucket: str = 'marketing-videos'
    minio_create_bucket: bool = False
    data_dir: Path = ROOT / 'data'
    max_upload_mb: int = Field(default=40, ge=1, le=100)
    max_pending_jobs: int = Field(default=4, ge=1, le=20)
    playback_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    ffmpeg_binary: str = ''
    font_path: str = '/System/Library/Fonts/Supplemental/Arial.ttf'
    local_motion_enabled: bool = False
    local_motion_model: Path = ROOT / 'models/ltx-video'
    local_motion_device: Literal['mps', 'cuda', 'cpu'] = 'mps'
    local_motion_timeout: int = Field(default=1200, ge=30, le=7200)

    @classmethod
    def load(cls):
        # The supplied client already uses muse/.env. Keep its key server-side;
        # explicit experiment/.env and environment values take precedence.
        env = {}
        for source in (dotenv_values(ROOT / 'muse/.env'), dotenv_values(ROOT / '.env'), os.environ):
            env.update({k: v for k, v in source.items() if v not in (None, '')})
        if 'MUSE_BASE_URL' in env and 'MUSE_API_BASE_URL' not in env:
            env['MUSE_API_BASE_URL'] = env['MUSE_BASE_URL']
        values = {name: env[name.upper()] for name in cls.model_fields
                  if env.get(name.upper()) not in (None, '')}
        for name in ('data_dir', 'local_motion_model'):
            if name in values and not Path(values[name]).is_absolute():
                values[name] = ROOT / values[name]
        return cls(**values)

    def storage_ready(self):
        return self.storage_backend == 'local' or bool(
            self.minio_access_key.get_secret_value() and self.minio_secret_key.get_secret_value())
