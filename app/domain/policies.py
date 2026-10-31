"""Hằng số nghiệp vụ giả định từ docs/SEED_DATA.md."""

MIN_STOCK = 30
ADS_MIN_DAILY = 10_000
CPC = 1_800
MAX_ROUNDS = 3
PACKAGE_DAYS = 3
REJECT_COOLDOWN_DAYS = 3
PREF_ASK_THRESHOLD = 1
PREF_DECLINE_SILENCE_DAYS = 14
LESSON_CAP_PER_SCOPE = 30
CALIBRATION_MIN_POINTS = 5
CALIBRATION_WINDOW = 30
PRIOR_CVR_BIAS = 1.5
QUALITY_REFRESH_GAIN = 0.25
MAX_CONTENT_VERSIONS = 3

DEFAULT_PACKAGE = {
    "content_refresh": True,
    "ads_daily_budget": 70_000,
    "voucher_pct": 10,
    "stop_roas_below": 4.0,
    "stop_after_days": 2,
    "duration_days": PACKAGE_DAYS,
}
