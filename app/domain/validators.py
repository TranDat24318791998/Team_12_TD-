"""Kiểm gói ở cả hai phía trước khi người bán phê duyệt."""

import math
from app.domain.finance import breakeven_roas, loss_warning, max_voucher_for, profit_per_unit, stop_threshold
from app.domain.models.negotiation import Violation
from app.domain.models.packages import Package
from app.domain.policies import ADS_MIN_DAILY, MIN_STOCK


def _violation(code, side, field, message):
    return Violation(code=code, side=side, field=field, message_vi=message)


def platform_side_check(pkg, shop):
    errors = []
    if pkg.ads_daily_budget and shop.stock < MIN_STOCK:
        errors.append(_violation('LOW_STOCK', 'platform', 'ads_daily_budget', 'Tồn kho chưa đủ để chạy quảng cáo.'))
    if 0 < pkg.ads_daily_budget < ADS_MIN_DAILY:
        errors.append(_violation('ADS_BELOW_MINIMUM', 'platform', 'ads_daily_budget', 'Ngân sách dưới mức tối thiểu.'))
    if pkg.ads_daily_budget and pkg.stop_roas_below is None:
        errors.append(_violation('STOP_REQUIRED', 'platform', 'stop_roas_below', 'Cần ngưỡng dừng quảng cáo.'))
    if not pkg.ads_daily_budget and pkg.stop_roas_below is not None:
        errors.append(_violation('STOP_WITHOUT_ADS', 'platform', 'stop_roas_below', 'Không cần ngưỡng dừng khi không chạy quảng cáo.'))
    if not pkg.content_refresh and not pkg.ads_daily_budget and not pkg.voucher_pct:
        errors.append(_violation('EMPTY_PACKAGE', 'platform', 'content_refresh', 'Gói chưa có hoạt động.'))
    return errors


def shop_side_check(pkg, shop, priv, fees):
    errors = []
    rules = priv.rules
    if pkg.ads_daily_budget and not rules.allow_ads:
        errors.append(_violation('ADS_DISABLED', 'shop', 'ads_daily_budget', 'Shop không cho chạy quảng cáo.'))
    if pkg.ads_daily_budget > rules.ads_daily_max:
        errors.append(_violation('ADS_OVER_CAP', 'shop', 'ads_daily_budget', 'Ngân sách vượt luật shop.'))
    if pkg.voucher_pct > rules.voucher_max_pct:
        errors.append(_violation('VOUCHER_OVER_CAP', 'shop', 'voucher_pct', 'Voucher vượt luật shop.'))
    profit = profit_per_unit(shop, priv, pkg.voucher_pct, fees)
    # Baseline loss can still be surfaced as a content-only warning.
    if (pkg.ads_daily_budget or pkg.voucher_pct) and profit < rules.min_profit_per_unit:
        errors.append(_violation('PROFIT_TOO_LOW', 'shop', 'voucher_pct', 'Gói không đạt lãi tối thiểu.'))
    if pkg.ads_daily_budget:
        be = breakeven_roas(shop, priv, pkg.voucher_pct, fees)
        if be > rules.max_breakeven_roas:
            errors.append(_violation('BREAKEVEN_TOO_HIGH', 'shop', 'voucher_pct', 'Gói vượt ngưỡng hòa vốn.'))
        if rules.require_stop_condition and (pkg.stop_roas_below is None or pkg.stop_roas_below < stop_threshold(be)):
            errors.append(_violation('STOP_TOO_LOW', 'shop', 'stop_roas_below', 'Ngưỡng dừng chưa bảo vệ shop.'))
    return errors


def clamp_to_platform(pkg, shop, package_days):
    values = pkg.model_dump()
    if shop.stock < MIN_STOCK or 0 < values['ads_daily_budget'] < ADS_MIN_DAILY:
        values['ads_daily_budget'] = 0
        values['stop_roas_below'] = None
    if not values['ads_daily_budget']:
        values['stop_roas_below'] = None
    values['duration_days'] = package_days
    result = Package.model_validate(values)
    return None if platform_side_check(result, shop) else result


def clamp_to_rules(pkg, shop, priv, fees):
    values = pkg.model_dump()
    values['ads_daily_budget'] = min(values['ads_daily_budget'], priv.rules.ads_daily_max) if priv.rules.allow_ads else 0
    if values['ads_daily_budget'] < ADS_MIN_DAILY or shop.stock < MIN_STOCK:
        values['ads_daily_budget'] = 0
    if loss_warning(shop, priv, fees):
        values['ads_daily_budget'] = 0
        values['voucher_pct'] = 0
    else:
        values['voucher_pct'] = min(values['voucher_pct'], max_voucher_for(shop, priv, bool(values['ads_daily_budget']), fees))
    if values['ads_daily_budget']:
        threshold = stop_threshold(breakeven_roas(shop, priv, values['voucher_pct'], fees))
        if not math.isfinite(threshold):
            return None
        values['stop_roas_below'] = max(values['stop_roas_below'] or 0, threshold)
    else:
        values['stop_roas_below'] = None
    result = Package.model_validate(values)
    return None if platform_side_check(result, shop) or shop_side_check(result, shop, priv, fees) else result


def final_check(pkg, shop, priv, fees):
    return [v.model_copy(update={'side': 'final'}) for v in platform_side_check(pkg, shop) + shop_side_check(pkg, shop, priv, fees)]
