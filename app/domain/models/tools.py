"""Dữ liệu được phép đưa vào tool theo từng vai trò."""

from app.domain.models.shops import StrictModel, ShopPublic, ShopPrivate
from app.domain.models.intent import IntentBrief
from app.domain.models.packages import Package
from app.domain.models.negotiation import PublicTurn, Violation
from app.domain.models.metrics import Forecast
from typing import Literal
from hashlib import sha256
from pydantic import Field, model_validator
from app.domain.models.learning import ContentMemoryView, PlatformMemoryView


class PinnedPlatformContext(StrictModel):
    run_id: str
    shop_id: str
    category: str
    negotiation_id: str
    day: int
    kind: Literal['propose', 'renew']
    through_seq: int
    memory: PlatformMemoryView
    base_text: str

    @model_validator(mode='after')
    def binding(self):
        if self.day < 1 or self.through_seq < 0 or not self.memory.skill:
            raise ValueError('invalid pinned platform context')
        bundle=self.memory.skill.bundle
        if (bundle.run_id,bundle.shop_id,bundle.category)!=(self.run_id,self.shop_id,self.category) or bundle.effective_from_day>self.day:
            raise ValueError('skill scope or effective day mismatch')
        if bundle.skill.skill_id != ('platform_offer' if self.kind=='propose' else 'platform_renew') or bundle.skill.base_hash != sha256(self.base_text.encode('utf-8')).hexdigest():
            raise ValueError('skill or base text mismatch')
        return self


class ReferenceDocument(StrictModel):
    document_id: str
    document_version: int
    source_reference: str
    checksum: str
    is_simulated: bool
    text_vi: str = Field(max_length=1800)


class PublicContext(StrictModel):
    day: int
    shop: ShopPublic
    brief: IntentBrief
    trend_multiplier: float
    calendar_notes: list[str]
    active_package: Package | None
    references: list[ReferenceDocument] = Field(default_factory=list)


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
    forecast: Forecast | None = None
    forecast_turn_id: str | None = None


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
    references: list[ReferenceDocument] = Field(default_factory=list)


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
