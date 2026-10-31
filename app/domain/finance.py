"""Tính tài chính bằng số thập phân; không dùng LLM để tính tiền."""

import math
from decimal import Decimal, ROUND_HALF_UP


def _d(value):
    return Decimal(str(value))


def _rounded(value):
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def profit_per_unit(shop, priv, voucher_pct, fees):
    price = _d(shop.price) * (100 - _d(voucher_pct)) / 100
    price = _d(_rounded(price))
    rate = (_d(fees.fixed_pct) + _d(fees.transaction_pct) + _d(fees.tax_pct)) / 100
    return _rounded(price * (1 - rate) - _d(fees.per_order) - _d(priv.unit_cost))


def breakeven_roas(shop, priv, voucher_pct, fees):
    profit = profit_per_unit(shop, priv, voucher_pct, fees)
    if profit <= 0:
        return math.inf
    price = _rounded(_d(shop.price) * (100 - _d(voucher_pct)) / 100)
    return price / profit


def stop_threshold(breakeven):
    return math.ceil(breakeven * 2) / 2 if math.isfinite(breakeven) else math.inf


def max_voucher_for(shop, priv, ads_enabled, fees):
    candidates = []
    for voucher in range(min(30, priv.rules.voucher_max_pct) + 1):
        profit = profit_per_unit(shop, priv, voucher, fees)
        if profit < priv.rules.min_profit_per_unit:
            continue
        if ads_enabled and breakeven_roas(shop, priv, voucher, fees) > priv.rules.max_breakeven_roas:
            continue
        candidates.append(voucher)
    return max(candidates, default=0)


def loss_warning(shop, priv, fees):
    return 'Giá bán hiện lỗ sau phí; chỉ đề xuất làm mới nội dung.' if profit_per_unit(shop, priv, 0, fees) < 0 else None
