from app.domain.models.shops import StrictModel
from app.domain.models.packages import Package


class Forecast(StrictModel):
    low: int
    point: int
    high: int
    factor_used: float
    stock_warning: bool


class ForecastSnapshot(StrictModel):
    prediction_id: str
    shop_id: str
    target_day: int
    raw_point: float
    issued_point: int
    factor_used: float
    package: Package


class DayMetrics(StrictModel):
    shop_id: str
    day: int
    impressions: int
    clicks: int
    orders: int
    revenue: int
    ads_spend: int
    roas: float | None
    fees: int
    profit_after_fees: int


class ProofMetric(StrictModel):
    key: str
    label_vi: str
    better: str
    on: float
    off: float
    unit: str


class ProofReport(StrictModel):
    seed: int
    days: int
    run_on: str
    run_off: str
    metrics: list[ProofMetric]
    note_vi: str
