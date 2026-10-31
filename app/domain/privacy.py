"""Chặn dữ liệu tài chính riêng trong chữ từ shop ra transcript công khai."""

import math
import re
from app.domain.finance import breakeven_roas, profit_per_unit


def leak_guard(text, shop, priv, fees):
    sensitive_phrase = r'giá\s*vốn|vốn\s*nhập|lãi\s*(?:tối\s*thiểu|mỗi\s*đơn|trên\s*mỗi\s*đơn)|(?:roas\s*)?hòa\s*vốn|(?:roas\s*)?hoà\s*vốn|private[_\s-]*note'
    if (priv.owner_name and re.search(r'(?<!\w)' + re.escape(priv.owner_name) + r'(?!\w)', text, re.IGNORECASE)) or re.search(sensitive_phrase, text, re.IGNORECASE):
        return 'Shop đề xuất điều chỉnh gói để phù hợp với quy tắc đã đặt.', True
    amounts = {priv.unit_cost, priv.rules.min_profit_per_unit}
    amounts.update(profit_per_unit(shop, priv, v, fees) for v in range(31))
    variants = set()
    for value in amounts:
        if value <= 0:
            continue
        variants.update({str(value), f'{value:,}', f'{value:,}'.replace(',', '.'), f'{value:,}'.replace(',', ' ')})
        if value >= 1000 and value % 1000 == 0:
            variants.update({f'{value // 1000}k', f'{value // 1000} nghìn'})
    for voucher in range(31):
        value = breakeven_roas(shop, priv, voucher, fees)
        if math.isfinite(value):
            for precision in (3, 4, 5):
                decimal = f'{value:.{precision}f}'
                variants.add(decimal)
                variants.add(decimal.replace('.', ','))
    pattern = '|'.join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
    if pattern and re.search(r'(?<![\w\d])(?:' + pattern + r')(?![\w\d])', text, re.IGNORECASE):
        return 'Shop đề xuất điều chỉnh gói để phù hợp với quy tắc đã đặt.', True
    return text, False
