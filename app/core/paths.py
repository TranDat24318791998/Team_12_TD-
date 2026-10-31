"""Đường dẫn ổn định theo repo, không phụ thuộc thư mục đang chạy lệnh."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
CONTRACTS_DIR = PROJECT_ROOT / "contracts"
REPLAY_DIR = PROJECT_ROOT / "replay"
MEDIA_DIR = PROJECT_ROOT / "media"
RUNS_DIR = PROJECT_ROOT / "runs"
