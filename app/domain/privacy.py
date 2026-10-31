"""Chặn dữ liệu tài chính riêng trong chữ từ shop ra transcript công khai."""

import math
import re
from decimal import Decimal, InvalidOperation
from app.domain.finance import breakeven_roas, profit_per_unit


_NUMBER = re.compile(
    r'(?<!\w)[+-]?\d(?:[\d.,\u00a0 ]*\d)?(?:\s*(?:nghìn|ngàn|triệu|k|đ|vnd))?(?!\w)',
    re.IGNORECASE,
)
_UNIT = re.compile(r'\s*(nghìn|ngàn|triệu|k|đ|vnd)$', re.IGNORECASE)


def _numeric_values(token):
    unit_match = _UNIT.search(token)
    unit = unit_match.group(1).casefold() if unit_match else ''
    amount = token[:unit_match.start()] if unit_match else token
    amount = amount.replace(' ', '').replace('\u00a0', '')
    multiplier = Decimal(1000000 if unit == 'triệu' else 1000 if unit in {'nghìn', 'ngàn', 'k'} else 1)
    candidates = set()
    try:
        # A lone separator can denote either decimal or thousands, so retain both.
        if ',' in amount and '.' in amount:
            separator = ',' if amount.rfind(',') > amount.rfind('.') else '.'
            other = '.' if separator == ',' else ','
            candidates.add(Decimal(amount.replace(other, '').replace(separator, '.')) * multiplier)
        elif ',' in amount or '.' in amount:
            separator = ',' if ',' in amount else '.'
            parts = amount.split(separator)
            if len(parts) == 2:
                candidates.add(Decimal(amount.replace(separator, '.')) * multiplier)
            if all(len(group) == 3 for group in parts[1:]):
                candidates.add(Decimal(''.join(parts)) * multiplier)
        else:
            candidates.add(Decimal(amount) * multiplier)
    except InvalidOperation:
        return set(), 0
    precision = len(re.split(r'[.,]', amount)[-1]) if '.' in amount or ',' in amount else 0
    return candidates, precision


def leak_guard(text, shop, priv, fees):
    safe = 'Shop đề xuất điều chỉnh gói để phù hợp với quy tắc đã đặt.'
    sensitive_phrase = r'giá\s*vốn|vốn\s*nhập|lãi\s*(?:tối\s*thiểu|mỗi\s*đơn|trên\s*mỗi\s*đơn)|(?:roas\s*)?hòa\s*vốn|(?:roas\s*)?hoà\s*vốn|private[_\s-]*note'
    if (priv.owner_name and re.search(r'(?<!\w)' + re.escape(priv.owner_name) + r'(?!\w)', text, re.IGNORECASE)) or re.search(sensitive_phrase, text, re.IGNORECASE):
        return safe, True
    amounts = {Decimal(priv.unit_cost), Decimal(priv.rules.min_profit_per_unit)}
    amounts.update(Decimal(profit_per_unit(shop, priv, voucher, fees)) for voucher in range(31))
    breakevens = [breakeven_roas(shop, priv, voucher, fees) for voucher in range(31)]
    for match in _NUMBER.finditer(text):
        token = match.group()
        # A comma can separate two numbers as well as mark a decimal; inspect both interpretations.
        fragments = [token, *re.split(r'\s*,\s*', token), *re.split(r'\s+(?=\d)', token)]
        for fragment in fragments:
            fragment = fragment.strip().strip('.,')
            if not fragment:
                continue
            values, precision = _numeric_values(fragment)
            if any(value in amounts and value > 0 for value in values):
                return safe, True
            if precision >= 3:
                tolerance = max(0.5 * 10 ** (-min(precision, 15)), 1e-12)
                if any(math.isfinite(be) and abs(float(value) - be) <= tolerance for value in values for be in breakevens):
                    return safe, True
    return text, False
