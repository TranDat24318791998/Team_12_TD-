"""Headless integration uses real routes, isolated principals and fake workers."""

import pytest
from growth_data.harness import HttpHarness
from growth_data.storage import many


@pytest.mark.parametrize("policy",["good","bad"])
def test_seven_day_http_agents_workers_and_measured_comparison(client,service,policy):
    harness=HttpHarness(client,service.issue_token)
    report=harness.comparison(policy=policy)
    pair=report["comparison"]
    first=next(x for x in report["proof"]["metrics"] if x["key"]=="first_round_accept")
    assert first["on"]>first["off"] if policy=="good" else first["on"]<first["off"]
    assert report["http_calls"]>200 and report["gate_b"]=="PENDING"
    for r in (pair["run_on"],pair["run_off"]):
        with service.store.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=?",(r,)).fetchone()[0]==35
            assert c.execute("SELECT COUNT(*) FROM daily_metrics WHERE run_id=? AND source='simulated'",(r,)).fetchone()[0]==70
            assert not c.execute("PRAGMA foreign_key_check").fetchall()
    # Creating comparison cohorts must not replace the interactive seller run.
    assert client.get("/api/state").json()["run_id"] not in {pair["run_on"],pair["run_off"]}
