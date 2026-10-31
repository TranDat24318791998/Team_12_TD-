from decimal import Decimal, ROUND_HALF_UP


def vnd(value):
    return f"{int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)):,}".replace(',', '.') + 'đ'


def dec(value, digits=1):
    return f'{value:.{digits}f}'.replace('.', ',')
