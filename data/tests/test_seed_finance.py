from decimal import Decimal
import hashlib
import json
import pytest
from growth_data.finance import financials,safe_package,check,redact
from growth_data.seed import world,prepare
from growth_data.models import Package
from growth_data.storage import one,many


@pytest.mark.parametrize("sid,profit",[("A",48595),("B",-4705),("D",31625),("E",21645)])
def test_original_financial_examples(sid,profit):
    s=world()["shops"][sid]
    assert financials(s["public"]["price"],s["private"]["unit_cost"])["unit_contribution_vnd"]==profit


def test_d_voucher_finance_not_persona():
    s=world()["shops"]["D"]
    p=safe_package(175000,115000,s["private"]["rules"],300)
    assert (p["ads_daily_budget"],p["voucher_pct"],p["stop_roas_below"])==(45000,3,6.5)
    assert check(p,175000,115000,s["private"]["rules"],300)["passed"]
    assert world()["shops"]["D"]["persona"]["hidden_voucher_comfort_pct"] is None
    assert financials(175000,115000,3)["unit_contribution_vnd"]==27136


def test_units_and_private_redaction():
    with pytest.raises(ValueError):Package(content_refresh=True,ads_daily_budget=0,voucher_pct=300)
    rules=world()["shops"]["D"]["private"]["rules"]
    text=redact("giá vốn 115.000đ, lãi 27136, hòa vốn 6,26; ads 45.000đ",175000,115000,rules)
    assert "115.000" not in text and "27136" not in text and "6,26" not in text
    assert "45.000đ" in text


def test_seed_history_and_no_precomputed_outcomes(service,run):
    with service.store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM daily_metrics WHERE run_id=? AND source='seeded'",(run,)).fetchone()[0]==140
        assert c.execute("SELECT COUNT(*) FROM daily_metrics WHERE run_id=? AND source='simulated'",(run,)).fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM campaigns WHERE run_id=?",(run,)).fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM market_daily WHERE run_id=?",(run,)).fetchone()[0]==14
        assert one(c,"SELECT * FROM inventory WHERE run_id=? AND product_id='SP004'",(run,))["available_units"]==300
        assert all(x["ad_spend_vnd"]==0 and x["realized_roas"] is None for x in many(c,"SELECT * FROM daily_metrics WHERE run_id=? AND channel='paid'",(run,)))


def test_manifest_reproducible(tmp_path):
    a=prepare(tmp_path/"a");b=prepare(tmp_path/"b")
    assert a==b and not a["proof_of_learning"]
    for name,entry in a["files"].items():assert hashlib.sha256((tmp_path/"a"/name).read_bytes()).hexdigest()==entry["sha256"]
