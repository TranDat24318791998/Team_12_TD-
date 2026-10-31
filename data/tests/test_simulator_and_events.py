"""Dedicated invariants beyond simply reaching the last demo day."""

from concurrent.futures import ThreadPoolExecutor
import pytest
from conftest import headers,role
from test_workflow import start,accept
from growth_data.harness import HttpHarness
from growth_data.storage import one,many
from growth_data import simulation


def test_stop_before_third_spend_expiry_and_no_duplicate_stop_event(client,service,run,monkeypatch):
    monkeypatch.setattr(simulation,"noise",lambda *args:.8)
    card=start(client);accept(client,card)
    client.post("/api/content/apply",json={"cover_option":"B"},headers={"Idempotency-Key":"apply"}).raise_for_status()
    for day in (1,2,3):
        if day>1:client.post("/api/day/start",json={},headers={"Idempotency-Key":f"start-{day}"}).raise_for_status()
        client.post("/api/night",json={},headers={"Idempotency-Key":f"night-{day}"}).raise_for_status()
        if day==2:
            campaign=client.get(f"/api/v1/runs/{run}/shops/D/campaigns").json()["data"][0]
            assert campaign["ads_status"]=="paused" and campaign["low_roas_streak"]==2
            assert client.get("/api/state").json()["demo_shop"]["active_voucher_pct"]==3
    paid=client.get(f"/api/v1/runs/{run}/shops/D/metrics?channel=paid&from_date=2026-11-01").json()["data"]
    assert [x["ad_spend_vnd"] for x in paid]==[45000,45000,0]
    assert client.get("/api/state").json()["demo_shop"]["active_voucher_pct"]==0
    with service.store.connect() as c:
        stops=[x for x in many(c,"SELECT * FROM events WHERE run_id=? AND shop_id='D' AND type='auto_action'",(run,)) if x["payload"].get("effective_day")==3]
        assert len(stops)==1


def test_cost_and_fee_versions_used_by_settlement_not_world_seed(client,service,run):
    card=start(client)
    client.post("/api/decision",json={"card_id":card["card_id"],"action":"reject"},headers={"Idempotency-Key":"reject"}).raise_for_status()
    # Fixture administration establishes a new effective policy/cost version.
    with service.store.connect(write=True) as c:
        c.execute("INSERT INTO product_costs VALUES(?,?,?,?,?,?,?)",(run,"SP004",2,110000,2000,1,"fixture"))
        c.execute("INSERT INTO fee_rules VALUES(?,?,?,?,?,?,?,?,?,?)",("fixture-fees-v2","rate","rate",1000,None,"net_item_revenue","quat_mini","2026-10-18",None,1))
        c.execute("INSERT INTO fee_rules VALUES(?,?,?,?,?,?,?,?,?,?)",("fixture-fees-v2","order","fixed_per_order",None,1000,"fulfilled_order","quat_mini","2026-10-18",None,1))
        c.execute("UPDATE run_policies SET fee_policy_version='fixture-fees-v2' WHERE run_id=?",(run,))
    simulator=role(service,run,"simulator")
    result=client.post(f"/internal/v1/runs/{run}/shops/D/settle-day",json={"day":1,"expected_inventory_version":1},headers=headers(simulator,"settle"))
    assert result.status_code==200,result.text
    rows=client.get(f"/api/v1/runs/{run}/shops/D/metrics?from_date=2026-11-01").json()["data"]
    assert all(row["cost_version"]==2 and row["fee_policy_version"]=="fixture-fees-v2" for row in rows)
    organic=next(row for row in rows if row["channel"]=="organic")
    assert organic["cogs_vnd"]==organic["orders"]*112000
    assert organic["fees_vnd"]==round(organic["net_revenue_vnd"]*.1)+organic["orders"]*1000


def test_decline_cooldown_and_external_renegotiation_queue(client,service):
    # Local seller reject has a real cooldown, not merely a hidden button.
    state=client.get("/api/state").json();r=state["run_id"]
    card=start(client)
    client.post("/api/decision",json={"card_id":card["card_id"],"action":"reject"},headers={"Idempotency-Key":"reject"}).raise_for_status()
    for day in (1,2,3):
        if day>1:
            client.post("/api/day/start",json={},headers={"Idempotency-Key":f"start-{day}"}).raise_for_status()
            assert client.get("/api/state").json()["pending_card"] is None
        client.post("/api/night",json={},headers={"Idempotency-Key":f"night-{day}"}).raise_for_status()
    client.post("/api/day/start",json={},headers={"Idempotency-Key":"start-4"}).raise_for_status()
    assert client.get("/api/state").json()["pending_card"] is not None
    h=HttpHarness(client,service.issue_token)
    external=h.post("/api/reset",{"execution_profile":"external"})["run_id"]
    o=h.token(external,"orchestrator")
    op=h.post(f"/api/v1/runs/{external}/days/start",{"expected_day":1,"expected_version":1},o)
    claimed=h.post(f"/internal/v1/runs/{external}/operations/{op['operation_id']}/claim",{"expected_version":op["version"]},o)
    card,nid=h.negotiate(external,"D",o)
    h.post(f"/internal/v1/runs/{external}/operations/{op['operation_id']}/result",{"expected_version":claimed["version"],"status":"succeeded"},o)
    h.post("/api/decision",{"card_id":card["card_id"],"action":"negotiate","note_vi":"Giảm voucher còn 2%"})
    queued=h.get(f"/api/v1/runs/{external}/operations?status=queued",o)[0]
    claim=h.post(f"/internal/v1/runs/{external}/operations/{queued['operation_id']}/claim",{"expected_version":queued["version"]},o)
    new,nid2=h.negotiate(external,"D",o,source_card=card["card_id"],note="Giảm voucher còn 2%")
    h.post(f"/internal/v1/runs/{external}/operations/{queued['operation_id']}/result",{"expected_version":claim["version"],"status":"succeeded"},o)
    assert nid2!=nid
    assert h.get("/api/state")["pending_card"]["package"]["voucher_pct"]==2


def test_typed_events_referee_evidence_scope_and_task_terminal(client,service):
    h=HttpHarness(client,service.issue_token)
    r=h.post("/api/reset",{"execution_profile":"external"})["run_id"]
    o=h.token(r,"orchestrator")
    h.post(f"/api/v1/runs/{r}/days/start",{"expected_day":1,"expected_version":1},o)
    context=h.get(f"/api/v1/runs/{r}/shops/D/context",o)
    neg=h.post(f"/internal/v1/runs/{r}/shops/D/negotiations",{"day":1,"expected_shop_version":context["shop_version"]},o)
    nid=neg["negotiation_id"];url=f"/internal/v1/runs/{r}/events"
    data={"negotiation_id":nid,"task_id":"fixture-task","round":1,"phase":"proposal","status":"running","label_vi":"Agent sàn bắt đầu"}
    body={"external_id":"telemetry-1","type":"agent_telemetry","shop_id":"D","day":1,"data":data}
    started=h.post(url,body,o)
    ended=h.post(url,{**body,"external_id":"telemetry-2","data":{**data,"status":"done"}},o)
    assert ended["seq"]>started["seq"]
    assert client.post(url,json={**body,"external_id":"late-running"},headers=headers(o,"late")).status_code==409
    referee={"external_id":"referee-1","type":"referee_review","shop_id":"D","day":1,"data":{"negotiation_id":nid,"round":1,"action":"continue","evidence_refs":[started["seq"]],"next_actor":"shop_agent"}}
    saved=h.post(url,referee,o)
    duplicate=h.post(url,referee,o)
    assert duplicate["seq"]==saved["seq"]
    platform=h.token(r,"platform_agent","D")
    assert client.post(url,json=referee,headers=headers(platform,"wrong-writer")).status_code==403
    bad={"external_id":"bad-memory","type":"memory_read","shop_id":"D","day":1,"data":{"who":"platform","items":[{"unit_cost":115000}]}}
    assert client.post(url,json=bad,headers=headers(platform,"bad-schema")).status_code==422
    with service.store.connect(write=True) as c:
        private=service.event(c,r,1,"code_check","orchestrator","D",visibility="shop_private")
    assert client.post(url,json={**referee,"external_id":"private-evidence","data":{**referee["data"],"evidence_refs":[private]}},headers=headers(o,"private-referee")).status_code==422


def test_empty_outcomes_comparison_preserves_null_and_measured_money(client,service):
    h=HttpHarness(client,service.issue_token)
    h.get("/api/state")
    pair=h.post("/api/v1/comparisons",{"execution_profile":"external","learning_mode":"skip","content_mode":"local","data_source":"fixture"})
    for r in (pair["run_on"],pair["run_off"]):
        o=h.token(r,"orchestrator")
        for day in range(1,8):
            run=h.get(f"/api/v1/runs/{r}",o)
            op=h.post(f"/api/v1/runs/{r}/days/start",{"expected_day":day,"expected_version":run["version"]},o)
            claim=h.post(f"/internal/v1/runs/{r}/operations/{op['operation_id']}/claim",{"expected_version":op["version"]},o)
            # Explicit fixture no-offer policy: no negotiation means no denominator.
            h.post(f"/internal/v1/runs/{r}/operations/{op['operation_id']}/result",{"expected_version":claim["version"],"status":"succeeded"},o)
            run=h.get(f"/api/v1/runs/{r}",o)
            h.post(f"/api/v1/runs/{r}/days/close",{"expected_day":day,"expected_version":run["version"]},o)
            run=h.get(f"/api/v1/runs/{r}",o)
            h.post(f"/api/v1/runs/{r}/days/advance",{"expected_day":day,"expected_version":run["version"]},o)
    report=h.get(f"/api/v1/runs/{pair['run_on']}/proof?group_id={pair['comparison_id']}")
    assert all(row["on"] is None and row["off"] is None for row in report["metrics"][:2])
    assert report['metrics'][2]['on'] is not None and report['metrics'][2]['off'] is not None
    assert report["metrics"][3]["on"]==report["metrics"][3]["off"]==0
    assert client.get('/api/proof').status_code==409
