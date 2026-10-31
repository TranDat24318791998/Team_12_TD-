from typing import Literal
from app.domain.models.shops import StrictModel


class IntentBrief(StrictModel):
    brief_id: str
    version: int
    shop_id: str
    intent: Literal["increase_orders"]
    goal_vi: str
    allow_ads: bool
    ads_daily_cap: int | None
    content_refresh: bool
    duration_days: int
    confirmed: bool
