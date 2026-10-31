"""Deterministic local channel simulator and code-generated forecast snapshots."""

from datetime import date, timedelta
from decimal import Decimal
import math
import random
from .finance import financials, money


def noise(seed, day, sid, kind):
    return math.exp(random.Random(f"{seed}:{day}:{sid}:{kind}").gauss(0, .10))


def business_date(day):
    return (date(2026, 11, 1) + timedelta(days=day - 1)).isoformat()


def trend(day):
    return 1.12 ** (min(day, 7) - 1) if day > 0 else 1.0


def channel_metrics(public, cost, *, seed, day, stock, quality, voucher=0, budget=0):
    sid = public["shop_id"]
    ctr = .015 + .02 * quality
    cvr = min(1, (.03 + .03 * quality + .002 * voucher) * noise(seed, day, sid, "cvr"))
    impr = round(public["base_impressions"] * trend(day) * (.5 + quality) * noise(seed, day, sid, "impr"))
    organic_clicks = round(impr * ctr)
    paid_clicks = math.floor(budget / 1800) if stock > 0 else 0
    spend = paid_clicks * 1800
    organic_orders = min(stock, round(organic_clicks * cvr))
    paid_orders = min(stock - organic_orders, round(paid_clicks * cvr))
    f = financials(public["price"], cost, voucher)
    results = []
    for channel, impressions, clicks, orders, ads in (
        ("organic", impr, organic_clicks, organic_orders, 0),
        ("paid", math.ceil(paid_clicks / ctr), paid_clicks, paid_orders, spend),
    ):
        revenue = orders * f["net_unit_price"]
        fees = money(Decimal(revenue) * Decimal(".145") + orders * 3000)
        cogs = orders * cost
        profit = orders * f["unit_contribution_vnd"] - ads
        results.append(dict(channel=channel, impressions=impressions, clicks=clicks, orders=orders,
                            units=orders, net_revenue_vnd=revenue, ad_spend_vnd=ads, fees_vnd=fees,
                            cogs_vnd=cogs, other_cost_vnd=0, contribution_vnd=profit,
                            rounding_adjustment_vnd=profit - (revenue-fees-cogs-ads),
                            realized_roas=revenue / ads if ads else None))
    return results


def forecast(public, package, day, *, factor=1.0):
    raw = []
    for offset in range(package["duration_days"]):
        q = min(.95, public["listing_quality"] + (.25 if package["content_refresh"] and offset else 0))
        impr = public["base_impressions"] * trend(day) * (.5 + q)
        cvr = (.03 + .03*q + .002*package["voucher_pct"]) * 1.5
        raw.append((impr * (.015 + .02*q) + package["ads_daily_budget"] // 1800) * cvr)
    stock = public["stock"]
    points, remaining = [], stock
    for value in raw:
        count = min(remaining, round(value*factor))
        points.append(count)
        remaining -= count
    point = sum(points)
    return {"raw_daily_units": raw, "daily_point_units": points, "point": point,
            "low": min(point, round(sum(raw)*.7)), "high": min(stock, max(point, round(sum(raw)*1.3))),
            "factor_used": factor, "stock_warning": sum(raw)*factor > stock}


def aggregate(rows, sid, day):
    paid = [r for r in rows if r["channel"] == "paid"]
    spend = sum(r["ad_spend_vnd"] for r in paid)
    return {"shop_id": sid, "day": day,
            **{out: sum(r[key] for r in rows) for out,key in (
                ("impressions","impressions"),("clicks","clicks"),("orders","orders"),
                ("revenue","net_revenue_vnd"),("ads_spend","ad_spend_vnd"),
                ("fees","fees_vnd"),("profit_after_fees","contribution_vnd"))},
            "roas": sum(r["net_revenue_vnd"] for r in paid)/spend if spend else None}
