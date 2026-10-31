"""Ghép router theo tài nguyên; giữ nguyên URL trong CONTRACT.md."""

from fastapi import APIRouter

from app.api.routes import content, days, events, proof, sessions

router = APIRouter(prefix="/api")
router.include_router(sessions.router)
router.include_router(days.router)
router.include_router(events.router)
router.include_router(content.router)
router.include_router(proof.router)
