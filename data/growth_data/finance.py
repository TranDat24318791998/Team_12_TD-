"""Single local reference calculator; never uses an LLM or provider."""

from decimal import Decimal, ROUND_HALF_UP
import math
import re


def money(value):
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def financials(price, cost, voucher=0):
    net = money(Decimal(price) * (100 - Decimal(voucher)) / 100)
    profit = money(Decimal(net) * Decimal(".855") - 3000 - cost)
    be = net / profit if profit > 0 else None
    return {"net_unit_price": net, "unit_contribution_vnd": profit, "break_even_roas": be,
            "stop_threshold": math.ceil(be * 2) / 2 if be is not None else None,
            "unprofitable": profit <= 0}


def check(package, price, cost, rules, stock):
    p = package.model_dump() if hasattr(package, "model_dump") else package
    f = financials(price, cost, p["voucher_pct"])
    violations = []
    def require(ok, code):
        if not ok:
            violations.append(code)
    ads = p["ads_daily_budget"]
    require(p["voucher_pct"] <= rules["voucher_max_pct"], "VOUCHER_OVER_CAP")
    require(not ads or rules["allow_ads"], "ADS_NOT_ALLOWED")
    require(ads <= rules["ads_daily_max"], "ADS_OVER_CAP")
    require(not ads or stock >= 30, "STOCK_TOO_LOW_FOR_ADS")
    if ads or p["voucher_pct"]:
        require(f["unit_contribution_vnd"] >= rules["min_profit_per_unit"], "PROFIT_BELOW_MIN")
        require(not f["unprofitable"], "LOSS_MAKING")
    if ads:
        require(f["break_even_roas"] is not None and f["break_even_roas"] <= rules["max_breakeven_roas"], "BREAKEVEN_TOO_HIGH")
        require(p["stop_roas_below"] is not None and f["stop_threshold"] is not None and p["stop_roas_below"] >= f["stop_threshold"], "STOP_BELOW_BREAKEVEN")
    return {"passed": not violations, "violations": violations, **f}


def safe_package(price, cost, rules, stock, requested=None):
    p = dict(requested or {"content_refresh": True, "ads_daily_budget": 70000, "voucher_pct": 10,
                          "stop_roas_below": 4.0, "stop_after_days": 2, "duration_days": 3})
    if financials(price, cost)["unprofitable"]:
        return {**p, "content_refresh": True, "ads_daily_budget": 0, "voucher_pct": 0, "stop_roas_below": None}
    p["ads_daily_budget"] = min(p["ads_daily_budget"], rules["ads_daily_max"]) if rules["allow_ads"] and stock >= 30 else 0
    if p["ads_daily_budget"] < 10000:
        p["ads_daily_budget"] = 0
    for v in range(min(p["voucher_pct"], rules["voucher_max_pct"]), -1, -1):
        f = financials(price, cost, v)
        if f["unit_contribution_vnd"] >= rules["min_profit_per_unit"] and (not p["ads_daily_budget"] or (f["break_even_roas"] is not None and f["break_even_roas"] <= rules["max_breakeven_roas"])):
            p["voucher_pct"] = v
            p["stop_roas_below"] = max(p["stop_roas_below"] or 0, f["stop_threshold"]) if p["ads_daily_budget"] else None
            return p
    return {**p, "content_refresh": True, "ads_daily_budget": 0, "voucher_pct": 0, "stop_roas_below": None}


def redact(text, price, cost, rules):
    """Defense in depth for shared seller text; projection remains the primary boundary."""
    values = {cost, rules["min_profit_per_unit"]}
    for v in range(31):
        f = financials(price, cost, v)
        values.add(f["unit_contribution_vnd"])
        if f["break_even_roas"] is not None:
            for value in (f'{f["break_even_roas"]:.2f}', f'{f["break_even_roas"]:.3f}'):
                for form in (value, value.replace(".", ",")):
                    text = re.sub(r"(?<!\d)(?<!\d[.,])" + re.escape(form) + r"(?!\d|[.,]\d)", "[ẩn]", text)
    for value in sorted(values, key=lambda v: len(str(v)), reverse=True):
        variants = {str(value), f"{value:,}", f"{value:,}".replace(",", ".")}
        if value % 1000 == 0:
            variants.update(f"{value // 1000}{suffix}" for suffix in ("k", "K", " nghìn", " ngàn"))
        for variant in variants:
            text = re.sub(r"(?<!\d)(?<!\d[.,])" + re.escape(variant) + r"(?!\d|[.,]\d)", "[ẩn]", text)
    return text
