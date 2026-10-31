from typing import Literal
from pydantic import Field
from app.domain.models.shops import StrictModel
from app.domain.models.packages import Package
from app.domain.models.metrics import Forecast


class RuleQuestion(StrictModel):
    pref_id: str
    field: Literal["voucher_max_pct", "content_style"]
    value: str
    text_vi: str


class Card(StrictModel):
    card_id: str
    shop_id: str
    day: int
    kind: Literal["offer", "question"]
    package: Package | None = None
    forecast: Forecast | None = None
    profit_after_fees_per_unit: int | None = None
    breakeven_roas_display: float | None = None
    reasons_vi: list[str] = Field(default_factory=list)
    warnings_vi: list[str] = Field(default_factory=list)
    notices_vi: list[str] = Field(default_factory=list)
    rule_question: RuleQuestion | None = None
    version: int = 1
    brief_version: int
    negotiation_id: str | None = None


class SellerDecision(StrictModel):
    card_id: str
    action: Literal["accept", "negotiate", "reject", "edit"]
    expected_card_version: int
    expected_brief_version: int
    note_vi: str = ""
    edited_package: Package | None = None
    rule_answer: bool | None = None
