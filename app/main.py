"""Phục vụ API sức khoẻ, trang tĩnh và media của Growth Agents."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import router as api_router
from app.api.routes.health import router as health_router
from app.core.paths import FRONTEND_DIR, MEDIA_DIR

def create_app() -> FastAPI:
    """Lắp các router và tài nguyên của một ứng dụng độc lập."""
    application = FastAPI(title="Growth Agents · sàn·demo")
    application.include_router(health_router)
    application.include_router(api_router)
    # Static / phải đứng cuối để không che các route HTTP.
    application.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
    application.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
    return application


app = create_app()
