from typing import Literal
from pydantic import Field, model_validator
from app.domain.models.packages import Package
from app.domain.models.shops import StrictModel
from app.domain.models.metrics import Forecast


class Violation(StrictModel):
    code: str
    side: Literal["platform", "shop", "final"]
    field: str
    message_vi: str


class PlatformTurn(StrictModel):
    action: Literal["propose", "accept", "withdraw"]
    package: Package | None
    message_vi: str

    @model_validator(mode="after")
    def require_package(self):
        if self.action in {"propose", "accept"} and self.package is None:
            raise ValueError("package required")
        return self


class ShopTurn(StrictModel):
    action: Literal["accept", "counter", "reject"]
    package: Package | None
    message_vi: str
    private_note_vi: str = ""

    @model_validator(mode="after")
    def require_package(self):
        if self.action in {"accept", "counter"} and self.package is None:
            raise ValueError("package required")
        return self


class PublicTurn(StrictModel):
    turn_id: str
    actor: Literal["platform", "shop"]
    round: int
    action: str
    package: Package | None
    message_vi: str


class RefereeDecision(StrictModel):
    action: Literal["continue", "refocus", "ask_human", "stop"]
    reason_vi: str
    evidence_refs: list[str] = Field(default_factory=list)
    unresolved_terms: list[str] = Field(default_factory=list)
    next_actor: Literal["platform", "shop", "seller"] | None = None
    focused_question: str | None = None


class NegotiationResult(StrictModel):
    negotiation_id: str
    shop_id: str
    day: int
    kind: Literal["propose", "renew"]
    status: Literal["agreed", "failed", "warning_only"]
    rounds: int
    final_package: Package | None
    forecast: Forecast | None
    warning_vi: str | None = None
