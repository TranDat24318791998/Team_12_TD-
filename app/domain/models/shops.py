"""ShopPublic, ShopPrivate, ShopRules, SellerPersona và FeeConfig."""

from pydantic import BaseModel


class FeeConfig(BaseModel):
    """Giả định phí dùng cho mô phỏng; không phải biểu phí sàn thật."""

    fixed_pct: float = 8
    transaction_pct: float = 5
    tax_pct: float = 1.5
    per_order: int = 3_000
