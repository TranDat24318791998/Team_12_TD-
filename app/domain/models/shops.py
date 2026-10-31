"""Dữ liệu công khai và quy tắc riêng của mỗi shop."""

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class FeeConfig(StrictModel):
    fixed_pct: float = 8
    transaction_pct: float = 5
    tax_pct: float = 1.5
    per_order: int = 3_000


class ShopPublic(StrictModel):
    shop_id: str
    name: str
    category: str
    price: int = Field(ge=0)
    stock: int = Field(ge=0)
    listing_quality: float = Field(ge=0, le=1)
    search_rank_page: int = Field(ge=1)
    rating: float = Field(ge=0, le=5)
    base_impressions: int = Field(ge=0)
    title: str
    description: str
    attributes: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    video: str | None = None
    active_voucher_pct: int = 0


class ShopRules(StrictModel):
    allow_ads: bool
    ads_daily_max: int = Field(ge=0)
    voucher_max_pct: int = Field(ge=0, le=30)
    min_profit_per_unit: int = Field(ge=0)
    max_breakeven_roas: float = 6.5
    require_stop_condition: bool = True
    content_style_notes: list[str] = Field(default_factory=list)


class ShopPrivate(StrictModel):
    owner_name: str
    unit_cost: int = Field(ge=0)
    rules: ShopRules


class SellerPersona(StrictModel):
    shop_id: str
    hidden_voucher_comfort_pct: int | None = None
    content_style_pref: str | None = None
    accepts_ads: bool = True
