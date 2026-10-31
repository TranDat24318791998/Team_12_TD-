"""Phục vụ API sức khoẻ, trang tĩnh và media của Growth Agents."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT

app = FastAPI(title="Growth Agents · sàn·demo")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


# Đăng ký API trước mount / để các route không bị trang tĩnh che khuất.
app.mount("/media", StaticFiles(directory=PROJECT_ROOT / "media"), name="media")
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "static", html=True), name="static")
