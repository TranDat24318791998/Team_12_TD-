"""Endpoint sức khoẻ, độc lập với dịch vụ bên ngoài và phiên demo."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
