#!/bin/sh
set -eu
# Tunnel only the FastAPI service; MinIO stays local.
exec cloudflared tunnel --url http://127.0.0.1:8010 --no-autoupdate
