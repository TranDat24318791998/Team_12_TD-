from app.domain.finance import breakeven_roas, max_voucher_for, profit_per_unit
from app.domain.models.packages import Package
from app.domain.policies import DEFAULT_PACKAGE
from app.domain.privacy import leak_guard
from app.domain.validators import clamp_to_rules, final_check, shop_side_check
from app.simulation.world import load_world


def test_seed_finance_and_negotiation_safety():
    world = load_world()
    expected = {'A': 48595, 'B': -4705, 'D': 31625, 'E': 21645}
    for sid, profit in expected.items():
        shop = world.shops[sid]
        assert profit_per_unit(shop.public, shop.private, 0, world.fees) == profit
    d = world.shops['D']
    assert profit_per_unit(d.public, d.private, 3, world.fees) == 27136
    assert abs(breakeven_roas(d.public, d.private, 3, world.fees) - 6.2555) < .001
    assert max_voucher_for(d.public, d.private, True, world.fees) == 3
    original = Package(**DEFAULT_PACKAGE)
    assert 'BREAKEVEN_TOO_HIGH' in {v.code for v in shop_side_check(original.model_copy(update={'voucher_pct': 4}), d.public, d.private, world.fees)}
    safe = clamp_to_rules(original, d.public, d.private, world.fees)
    assert (safe.ads_daily_budget, safe.voucher_pct, safe.stop_roas_below) == (45000, 3, 6.5)
    assert not final_check(safe, d.public, d.private, world.fees)
    b = world.shops['B']
    safe_b = clamp_to_rules(original, b.public, b.private, world.fees)
    assert safe_b.content_refresh and safe_b.ads_daily_budget == safe_b.voucher_pct == 0


def test_leak_guard_redacts_private_but_not_offered_budget():
    w = load_world(); shop = w.shops['D']
    for private in ['giá vốn 115.000đ', '115k', 'lãi tối thiểu 18 nghìn', '6,25553']:
        _, redacted = leak_guard(private, shop.public, shop.private, w.fees)
        assert redacted, private
    text = 'Đề xuất 45.000đ mỗi ngày, voucher 3%, dừng ở 6,5.'
    assert leak_guard(text, shop.public, shop.private, w.fees) == (text, False)
