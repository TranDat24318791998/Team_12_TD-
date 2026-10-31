"""Validated business DTOs; amounts are integer VND, vouchers whole percents."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Package(Strict):
    content_refresh: bool
    ads_daily_budget: int = Field(ge=0)
    voucher_pct: int = Field(ge=0, le=30)
    stop_roas_below: float | None = Field(default=None, gt=0)
    stop_after_days: int = Field(default=2, ge=1, le=14)
    duration_days: int = Field(default=3, ge=2, le=14)

    @model_validator(mode="after")
    def valid(self):
        if self.ads_daily_budget and (self.ads_daily_budget < 10000 or self.stop_roas_below is None):
            raise ValueError("Quảng cáo cần ít nhất 10.000đ/ngày và điều kiện dừng")
        if not (self.content_refresh or self.ads_daily_budget or self.voucher_pct):
            raise ValueError("Gói không được rỗng")
        return self


class ShopRules(Strict):
    allow_ads: bool
    ads_daily_max: int = Field(ge=0)
    voucher_max_pct: int = Field(ge=0, le=30)
    min_profit_per_unit: int = Field(ge=0)
    max_breakeven_roas: float = Field(default=6.5, gt=0)
    require_stop_condition: bool = True
    content_style_notes: list[str] = Field(default_factory=list)


class RunCreate(Strict):
    scenario_version: str = "demo-v1"
    seed: int = 42
    mode: Literal["offline", "replay", "live"] = "offline"
    memory_enabled: bool = True
    simulation_days: Literal[6, 7] = 7
    execution_profile: Literal["reference", "external"] = "reference"
    content_mode: Literal["local", "worker"] | None = None
    learning_mode: Literal["skip", "external"] | None = None
    driver_config: dict[str, str] = Field(default_factory=dict)
    data_source: Literal["simulation","fixture","replay"] = "simulation"


class Version(Strict):
    expected_version: int = Field(ge=1)


class DayCommand(Version):
    expected_day: int = Field(ge=1, le=7)


class NegotiationCreate(Strict):
    day: int = Field(ge=1, le=7)
    kind: Literal["propose", "renew"] = "propose"
    expected_shop_version: int = Field(ge=1)
    owner_note_vi: str | None = Field(default=None, max_length=2000)
    source_card_id: str | None = None


class CheckRequest(Strict):
    product_id: str
    package: Package


class ProposalCreate(Strict):
    product_id: str
    negotiation_id: str
    parent_proposal_id: str | None = None
    package: Package | None
    shared_reason: str = Field(default="", max_length=2000)
    stance: Literal["propose", "accept", "reject", "withdraw"] = "propose"


class DecisionCreate(Strict):
    target_type: Literal["proposal", "content", "rule_question"]
    target_id: str
    target_version: int = Field(ge=1)
    action: Literal["approve", "reject", "request_changes"]
    edited_package: Package | None = None
    cover_option: Literal["A", "B", "C"] | None = None
    rule_answer: bool | None = None
    feedback_private: str | None = Field(default=None, max_length=2000)
    feedback_shared: str | None = Field(default=None, max_length=2000)


class CampaignApply(Strict):
    proposal_id: str
    approval_decision_id: str
    expected_inventory_version: int = Field(ge=1)
    expected_rules_version: int = Field(ge=1)


class Pause(Version):
    reason_code: Literal["SELLER_REQUEST", "LOW_ROAS", "LOW_STOCK", "RULE_TIGHTENED"]


class RuleQuestionCreate(Strict):
    external_pref_id: str
    field: Literal["voucher_max_pct", "content_style"]
    value: str = Field(min_length=1, max_length=200)
    text_vi: str = Field(min_length=1, max_length=500)
    based_on_rules_version: int = Field(ge=1)

    @model_validator(mode="after")
    def valid(self):
        if self.field == "voucher_max_pct" and (not self.value.isdigit() or not 0 <= int(self.value) <= 30):
            raise ValueError("Voucher phải là phần trăm nguyên từ 0 đến 30")
        return self


class RulesUpdate(Strict):
    rules: ShopRules
    expected_rules_version: int = Field(ge=1)
    confirmation_decision_id: str


class ContentCreate(Strict):
    proposal_id: str
    product_id: str
    input_asset_ids: list[str] = Field(default_factory=list)
    feedback_vi: str | None = Field(default=None, max_length=2000)
    expected_current_attempt: int | None = Field(default=None, ge=1, le=3)
    retry_scope: Literal["images", "text", "all"] = "images"


class ContentResult(Strict):
    expected_job_version: int = Field(ge=1)
    status: Literal["running", "succeeded", "failed", "timed_out"]
    provider_job_id: str | None = None
    content_candidates: dict | None = None
    fallback_used: bool = False
    error_code: str | None = None

    @model_validator(mode="after")
    def candidate_shape(self):
        if self.content_candidates is not None:
            WorkerCandidate.model_validate(self.content_candidates)
        return self


class Publish(Strict):
    approval_decision_id: str
    expected_active_content_id: str


class UploadCreate(Strict):
    product_id: str | None = None
    kind: Literal["image", "video", "document"]
    mime_type: Literal["image/png", "image/jpeg", "image/webp", "video/mp4", "text/markdown", "application/pdf"]
    size_bytes: int = Field(gt=0, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_id: str | None = None
    purpose: Literal["product_media", "learning_report", "knowledge_source", "replay_recording"] = "product_media"


class CompleteUpload(Strict):
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class KnowledgeSearch(Strict):
    query: str = Field(min_length=1, max_length=2000)
    document_types: list[str] | None = None
    product_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class KnowledgeCreate(Strict):
    document_id: str
    document_version: int = Field(ge=1)
    type: str
    title: str
    collection_scope: Literal["shared", "shop_private"]
    owner_run_id: str | None = None
    owner_shop_id: str | None = None
    source_object_key: str | None = None
    source_asset_id: str | None = None
    source_run_id: str | None = None
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    knowledge_release: str = "knowledge-v1"
    effective_from: str
    effective_to: str | None = None
    is_simulated: bool = True
    source_url: str | None = None
    source_collected_at: str | None = None

    @model_validator(mode="after")
    def source_and_dates(self):
        from datetime import date
        start=date.fromisoformat(self.effective_from)
        if self.effective_to and date.fromisoformat(self.effective_to)<start:raise ValueError("Khoảng hiệu lực không hợp lệ")
        if bool(self.source_asset_id)==bool(self.source_object_key):raise ValueError("Chọn đúng một nguồn document")
        if self.source_asset_id and not self.source_run_id:raise ValueError("Cần source_run_id")
        if self.collection_scope=="shared" and (self.owner_run_id or self.owner_shop_id):raise ValueError("Shared không có private owner")
        if self.collection_scope=="shop_private" and not (self.owner_run_id and self.owner_shop_id):raise ValueError("Private cần owner")
        return self


class CalibrationSummary(Strict):
    factor: float = Field(ge=0)
    points: int = Field(ge=0)
    mape_today: float | None = Field(default=None,ge=0)


class CalibrationView(Strict):
    version: str = Field(min_length=1)
    as_of_day: int = Field(ge=0,le=7)
    points: int = Field(ge=0)
    factor: float = Field(gt=0)
    q_low: float = Field(ge=0)
    q_high: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if not self.q_low<=self.factor<=self.q_high:raise ValueError("Phân vị phải bao quanh hệ số hiệu chỉnh")
        return self


class LessonOp(Strict):
    op: Literal["ADD","UPVOTE","DOWNVOTE","EDIT"]
    lesson_id: str | None = None
    text_vi: str
    scope: str
    evidence: list[str]


class NightSummary(Strict):
    day: int = Field(ge=1,le=7)
    history_updates: list[str]
    pref_candidates: list[str]
    calibration: CalibrationSummary
    lesson_ops: list[LessonOp] = Field(max_length=5)
    rejected_ops: int = Field(ge=0)
    memory_md_path: str = ""


class LearningResult(Strict):
    day: int = Field(ge=1, le=7)
    settlement_cursor: int = Field(ge=0)
    status: Literal["running", "completed", "failed"]
    night_summary: NightSummary | None = None
    memory_report_asset_id: str | None = None
    error_code: str | None = None
    shop_id: str = "D"
    expected_version: int = Field(default=1, ge=1)
    receipt_id: str | None = None
    lesson_scores: dict[str, int] = Field(default_factory=dict)


class Settle(Strict):
    day: int = Field(ge=1, le=7)
    expected_inventory_version: int = Field(ge=1)
    input_snapshot_hash: str | None = None


class OperationResult(Version):
    status: Literal["running", "succeeded", "failed"]
    error_code: str | None = None
    trace_url: str | None = Field(default=None,max_length=2000)
    trace_shop_id: Literal["D"] | None = None


class LearningControl(Version):
    reason_vi: str = Field(min_length=1, max_length=500)


class Restore(Strict):
    expected_active_content_id: str
    expected_content_version: int = Field(ge=1)


class LegacyRestore(Restore):
    target_content_id: str


class ComparisonCreate(RunCreate):
    pass


class ComparisonAttach(Strict):
    run_on: str
    run_off: str


class ExternalEvent(Strict):
    external_id: str = Field(min_length=1, max_length=200)
    type: Literal["opportunity", "memory_read", "memory_write", "referee_review", "agent_telemetry"]
    shop_id: str
    day: int = Field(ge=1, le=7)
    entity_id: str | None = None
    text_vi: str = Field(default="", max_length=2000)
    data: dict

    @model_validator(mode="after")
    def payload(self):
        payloads={"opportunity":OpportunityEvent,"memory_read":MemoryReadEvent,"memory_write":MemoryWriteEvent,"referee_review":RefereeEvent,"agent_telemetry":TelemetryEvent}
        self.data=payloads[self.type].model_validate(self.data).model_dump(exclude_unset=True)
        return self


class ExcludedShop(Strict):
    shop_id: str
    reason_codes: list[str]


class OpportunityEvent(Strict):
    chosen: list[str]
    excluded: list[ExcludedShop] = Field(default_factory=list)
    keyword: str
    growth_7d_pct: float | None = None


class MemoryReadEvent(Strict):
    who: Literal["platform", "shop"]
    items: list[str]
    memory_revision: str | int | None = None


class MemoryWriteEvent(Strict):
    compartment: Literal["history", "preferences", "calibration", "lessons"]
    receipt_id: str
    memory_revision: str | int | None = None


class RefereeEvent(Strict):
    negotiation_id: str
    round: int = Field(ge=1,le=3)
    action: Literal["continue","refocus","ask_human","stop"]
    reason_vi: str = ""
    evidence_refs: list[int] = Field(default_factory=list)
    unresolved_terms: list[str] = Field(default_factory=list)
    next_actor: Literal["platform_agent","shop_agent","seller"] | None = None
    focused_question: str | None = None


class TelemetryEvent(Strict):
    negotiation_id: str
    task_id: str
    round: int = Field(ge=1,le=3)
    phase: Literal["proposal","validation","response","referee"]
    status: Literal["running","done","failed","stopped"]
    label_vi: str


class LegacyDecision(Strict):
    card_id: str
    action: Literal["accept","edit","reject","negotiate"]
    note_vi: str = Field(default="",max_length=2000)
    edited_package: Package | None = None
    rule_answer: bool | None = None


class WorkerImage(Strict):
    option: Literal["A","B","C"]
    status: Literal["done","cached"]
    asset_id: str
    path: str | None = None
    prompt: str = Field(default="",max_length=4000)


class WorkerVideo(Strict):
    status: Literal["pending","running","done","failed","cached"]
    asset_id: str | None = None
    path: str | None = None
    job_id: str | None = None
    prompt: str = Field(default="",max_length=4000)
    error: str | None = Field(default=None,max_length=1000)

    @model_validator(mode="after")
    def ready_asset(self):
        if self.status in {"done","cached"} and not self.asset_id:
            raise ValueError("Video ready cần asset_id")
        return self


class WorkerCandidate(Strict):
    title: str = Field(min_length=1,max_length=120)
    description: str = Field(min_length=1,max_length=5000)
    images: list[WorkerImage] = Field(min_length=3,max_length=3)
    video: WorkerVideo
    content_id: str | None = None
    content_version: int | None = None
    feedback_history: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)


class RecordingCall(Strict):
    call_id: str
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_asset_id: str


class RecordingManifest(Strict):
    version: Literal[1]
    run_id: str
    source: Literal["fixture","provider_recording"]
    complete: Literal[True]
    events_through: int = Field(ge=0)
    model: str = Field(min_length=1,max_length=100)
    prompt_version: str = Field(min_length=1,max_length=100)
    calls: list[RecordingCall] = Field(min_length=1,max_length=1000)
