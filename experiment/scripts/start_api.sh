#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec .venv/bin/python -m uvicorn video_api.main:create_app --factory --host 127.0.0.1 --port 8010 --workers 1 --no-access-log
