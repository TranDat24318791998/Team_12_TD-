"""Dữ liệu được phép đưa vào tool theo từng vai trò."""

from app.domain.models.shops import StrictModel, ShopPublic, ShopPrivate
from app.domain.models.intent import IntentBrief
from app.domain.models.packages import Package
from app.domain.models.negotiation import PublicTurn, Violation
from app.domain.models.learning import ContentMemoryView


class PublicContext(StrictModel):
    day: int
    shop: ShopPublic
    brief: IntentBrief
    trend_multiplier: float
    calendar_notes: list[str]
    active_package: Package | None


class ShopContext(StrictModel):
    private: ShopPrivate
    rules_version: int


class PackageCheck(StrictModel):
    input_package: Package
    corrected_package: Package | None
    violations_before: list[Violation]
    violations_after: list[Violation]
    ok: bool
    warnings: list[str]
    changes: list[str]


class FinancialResult(StrictModel):
    profit_per_unit: int
    breakeven_roas: float | None
    min_stop_threshold: float | None
    max_voucher_pct: int
    reason: str | None


class ShopPackageCheck(PackageCheck):
    financials: FinancialResult


class RefereeContext(StrictModel):
    brief: IntentBrief
    turns: list[PublicTurn]
    public_check_codes: list[str]


class ContentContext(StrictModel):
    shop_id: str
    title: str
    description: str
    attributes: list[str]
    images: list[str]
    fact_source_id: str
    memory: ContentMemoryView
    feedback_history: list[str]
    card_id: str
    brief_version: int
    draft_version: int


class CampaignRecord(StrictModel):
    campaign_id: str
    category: str
    title_vi: str
    description_vi: str
    valid_from_day: int
    valid_to_day: int
    min_stock: int
    max_voucher_pct: int
    source_id: str


class CampaignCatalogResult(StrictModel):
    items: list[CampaignRecord]
