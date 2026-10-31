"""Positive business assertions for the read/admin/monitor/export interfaces."""

import hashlib
from conftest import headers,role
from test_workflow import start,accept
from growth_data.harness import HttpHarness
from growth_data.storage import one


def test_agent_catalog_queries_and_knowledge_upload_read_revoke(client,service,run):
    h=HttpHarness(client,service.issue_token)
    p=h.token(run,"platform_agent");shop=h.token(run,"shop_agent","D")
    base=f"/api/v1/runs/{run}"
    policies=h.get(base+"/policies",p)
    assert sum(x["rate_bps"] or 0 for x in policies["fees"])==1450
    assert len(h.get(base+"/market/observations?limit=100",p))==14
    assert h.get(base+"/shops/D/costs?as_of_day=1",shop)["unit_cost_vnd"]==115000
    product=h.get(base+"/shops/D/products",p)[0]
    assert product["facts"]["battery_capacity_mah"]==2000
    assert len(product["facts"]["colors"])==3
    card=start(client)
    summary=h.get(base+"/market/summary",p)
    assert summary["growth_7d_pct"]==240 and summary["as_of_date"]=="2026-11-01"
    forecasts=h.get(base+"/shops/D/forecasts",shop)
    assert forecasts and all(sum(x["daily_point_units"])==x["point"] for x in forecasts)
    events=h.get("/api/events?after=0")
    turns=[x for x in events["events"] if x["type"] in {"platform_turn","shop_turn"}]
    assert turns and all(x["data"]["negotiation_id"] and x["data"]["round"]>=1 for x in turns)
    accept(client,card)
    h.post("/api/content/apply",{"cover_option":"B"})
    campaigns=h.get(base+"/shops/D/campaigns",shop)
    assert len(campaigns)==1 and campaigns[0]["package_snapshot"]["voucher_pct"]==3
    public=h.get(base+"/shops/D/campaigns",p)[0]
    assert "low_roas_streak" not in public and "approval_decision_id" not in public
    admin=h.token(run,"knowledge_admin")
    source=b"# Fixture public policy\nAds budget from verified policy.\n"
    aid=h.upload(run,admin,source,kind="document",product=None,purpose="knowledge_source")
    metadata={"document_id":"fixture_uploaded_guide","document_version":1,"type":"ads_guide","title":"Fixture uploaded guide","collection_scope":"shared","source_asset_id":aid,"source_run_id":run,"checksum":hashlib.sha256(source).hexdigest(),"effective_from":"2026-10-18"}
    saved=h.post("/internal/v1/knowledge/documents",metadata,admin)
    assert saved["index_status"]=="ready"
    doc=h.get(base+"/knowledge/documents/fixture_uploaded_guide",p)
    assert doc["content"].encode()==source
    hits=h.post(base+"/knowledge/search",{"query":"verified policy"},p)
    assert any(x["document_id"]=="fixture_uploaded_guide" for x in hits)
    h.post("/internal/v1/knowledge/documents/fixture_uploaded_guide/revoke",{"document_version":1,"reason_vi":"Fixture hết hiệu lực"},admin)
    assert client.get(base+"/knowledge/documents/fixture_uploaded_guide",headers=headers(p)).status_code==404


def test_browser_reference_comparison_attach_proof_and_replay(client,service):
    h=HttpHarness(client,service.issue_token)
    original=h.get("/api/state")["run_id"]
    first=h.get("/api/proof")
    assert first["status"]=="not_ready" and first["metrics"]==[]
    group=h.post("/api/v1/comparisons",{})
    status=h.get(f"/api/v1/comparisons/{group['comparison_id']}")
    assert status["status"]=="ready"
    proof=h.get("/api/proof")
    assert proof["status"]=="ready" and proof["run_on"]==group["run_on"]
    assert all(x["on"]==x["off"] for x in proof["metrics"])
    attached=h.post("/api/v1/comparisons/attach",{"run_on":group["run_on"],"run_off":group["run_off"]})
    assert attached["comparison_id"]!=group["comparison_id"]
    o=h.token(group["run_on"],"orchestrator")
    exported=h.post(f"/internal/v1/runs/{group['run_on']}/replay/export",{},o)
    assert not exported["faithful_llm_replay"] and exported["events"]
    assert all("object_key" not in a for a in exported["assets"])
    platform=h.token(group["run_on"],"platform_agent")
    assert client.get(f"/api/v1/runs/{group['run_on']}/proof?group_id={group['comparison_id']}",headers=headers(platform)).status_code==403
    assert h.get("/api/state")["run_id"]==original
    # Cohorts must be authorized together; a token for only one arm cannot read proof.
    evaluator=h.token(group["run_on"],"evaluator")
    assert client.get(f"/api/v1/runs/{group['run_on']}/proof?group_id={group['comparison_id']}",headers=headers(evaluator)).status_code==404


def test_no_content_apply_pause_and_explicit_simulator_settlement(client,service,run):
    h=HttpHarness(client,service.issue_token)
    card=start(client)
    o=h.token(run,"orchestrator");m=h.token(run,"simulator","D")
    raw=h.get(f"/api/v1/runs/{run}/state",o)["pending_cards"][0]
    prop=h.get(f"/api/v1/runs/{run}/proposals/{raw['proposal_id']}",o)
    approval=h.post(f"/api/v1/runs/{run}/decisions",{"target_type":"proposal","target_id":prop["proposal_id"],"target_version":prop["version"],"action":"approve","edited_package":{**prop["package"],"content_refresh":False}})
    applied=h.post(f"/api/v1/runs/{run}/campaigns/apply",{"proposal_id":approval["target_id"],"approval_decision_id":approval["decision_id"],"expected_inventory_version":1,"expected_rules_version":1},o)
    assert applied["ads_status"]=="running"
    assert h.get("/api/state")["demo_shop"]["title"]==h.get("/api/state")["demo_shop_original"]["title"]
    paused=h.post(f"/api/v1/runs/{run}/campaigns/{applied['campaign_id']}/pause",{"expected_version":applied["version"],"reason_code":"SELLER_REQUEST"})
    assert paused["ads_status"]=="paused"
    settled=h.post(f"/internal/v1/runs/{run}/shops/D/settle-day",{"day":1,"expected_inventory_version":1},m)
    inv=h.get(f"/api/v1/runs/{run}/shops/D/inventory",o)
    again=h.post(f"/internal/v1/runs/{run}/shops/D/settle-day",{"day":1,"expected_inventory_version":1},m)
    assert again["settlement_id"]==settled["settlement_id"]
    assert h.get(f"/api/v1/runs/{run}/shops/D/inventory",o)==inv
    metrics=h.get(f"/api/v1/runs/{run}/shops/D/metrics?from_date=2026-11-01&channel=paid",o)
    assert metrics[0]["ad_spend_vnd"]==0 and metrics[0]["realized_roas"] is None
    assert h.get("/api/state")["demo_shop"]["active_voucher_pct"]==3
