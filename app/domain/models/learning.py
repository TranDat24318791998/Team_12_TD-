"""Các record và projection có scope cho knowledge."""

from typing import Literal
from pydantic import Field
from app.domain.models.shops import StrictModel, ShopRules
from app.domain.models.packages import Package


class Preference(StrictModel):
    pref_id: str
    shop_id: str
    field: Literal["content_style", "voucher_max_pct"]
    value: str
    status: Literal["candidate", "asked", "confirmed", "declined"]
    evidence_seqs: list[int] = Field(default_factory=list)
    asked_day: int | None = None
    declined_until: int | None = None

    @property
    def observation_count(self) -> int:
        return len(set(self.evidence_seqs))


class Calibration(StrictModel):
    category: str
    ratios: list[float] = Field(default_factory=list, max_length=30)
    factor: float = 1.0
    q_low: float = 1.0
    q_high: float = 1.0


class LessonOp(StrictModel):
    op: Literal["ADD", "UPVOTE", "DOWNVOTE", "EDIT"]
    lesson_id: str | None
    text_vi: str
    scope: str
    evidence: list[str]


class NightSummary(StrictModel):
    day: int
    history_updates: list[str]
    pref_candidates: list[str]
    calibration: dict[str, float | int | None]
    lesson_ops: list[LessonOp]
    rejected_ops: int
    memory_md_path: str | None = None


class PublicOutcome(StrictModel):
    orders: int
    revenue: int
    ads_spend: int
    roas: float | None


class PublicHistory(StrictModel):
    negotiation_id: str
    shop_id: str
    day: int
    kind: str
    status: Literal["agreed", "failed", "warning_only"]
    rounds: int
    proposed_package: Package | None = None
    agreed_package: Package | None = None
    approved_package: Package | None = None
    seller_action: str | None = None
    ads_paused: bool = False
    outcome: PublicOutcome | None = None
    evidence_seqs: list[int] = Field(default_factory=list)
    version: int = 1


class CalibrationSample(StrictModel):
    sample_id: str
    prediction_id: str
    shop_id: str
    target_day: int
    raw_point: float
    actual_orders: int
    ratio: float
    evidence_seqs: list[int]


class CalibrationRecord(StrictModel):
    category: str
    value: Calibration
    samples: list[CalibrationSample]
    version: int


class PublicLesson(StrictModel):
    lesson_id: str
    scope: str
    text_vi: str
    score: int
    evidence: list[str]
    created_day: int
    updated_day: int
    version: int


class PlatformMemoryView(StrictModel):
    history: list[PublicHistory]
    calibration: Calibration | None
    lessons: list[PublicLesson]
    knowledge_revision: int


class ShopMemoryView(StrictModel):
    rules: ShopRules
    rules_version: int
    rules_evidence_seqs: list[int]
    preferences: list[Preference]
    knowledge_revision: int


class ContentMemoryView(StrictModel):
    confirmed_style_notes: list[str]
    rules_version: int
    preference_ids: list[str]


class PublicEvidence(StrictModel):
    seq: int
    type: str
    negotiation_id: str | None = None
    text_vi: str = ""
    package: Package | None = None
    seller_action: str | None = None
    feedback_vi: str | None = None
    outcome: PublicOutcome | None = None


class LearningEvidence(StrictModel):
    day: int
    from_seq: int
    through_seq: int
    events: list[PublicEvidence]
    existing_lessons: list[PublicLesson]
    valid_negotiation_ids: list[str]
    knowledge_revision: int


class LessonBatch(StrictModel):
    ops: list[LessonOp] = Field(max_length=3)


class MemoryUpdateBatch(StrictModel):
    day: int
    through_seq: int
    history: list[PublicHistory]
    preferences: list[Preference]
    calibration: list[CalibrationRecord]
    lesson_ops: list[LessonOp]
    valid_negotiation_ids: list[str]


class StoreWrite(StrictModel):
    namespace: tuple[str, str, str]
    key: str
    value: PublicHistory | Preference | CalibrationRecord | PublicLesson | None


class MemoryCommit(StrictModel):
    revision: int
    cursor: int
    applied_ids: list[str]
    duplicate: bool


class KnowledgeCommit(StrictModel):
    store: MemoryCommit
    accepted_lesson_ops: list[LessonOp]
    rejected_ops: int
