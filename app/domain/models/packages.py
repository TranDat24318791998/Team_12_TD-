"""Gói thương lượng và gói đã được người bán duyệt."""

from pydantic import Field
from app.domain.models.shops import StrictModel


class Package(StrictModel):
    content_refresh: bool
    ads_daily_budget: int = Field(ge=0)
    voucher_pct: int = Field(ge=0, le=30)
    stop_roas_below: float | None = None
    stop_after_days: int = Field(default=2, ge=1)
    duration_days: int = Field(ge=2, le=14)


class ActivePackage(StrictModel):
    package: Package
    start_day: int
    end_day: int
    ads_paused: bool = False
    card_id: str
