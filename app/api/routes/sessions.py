"""Route /reset và /state; nối SessionManager ở task API."""

from fastapi import APIRouter

router = APIRouter(tags=["sessions"])
