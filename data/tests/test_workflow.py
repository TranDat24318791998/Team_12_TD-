import hashlib
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from conftest import headers,role
from growth_data.service import DataService,Principal
from growth_data.errors import Fault
from growth_data.storage import one,many
from growth_data.evidence import run_scenario,compare,proof
from growth_data.seed import placeholder_png


def start(client):
    response=client.post("/api/day/start",json={},headers={"Idempotency-Key":"start"})
    assert response.status_code==200,response.text
    return client.get("/api/state").json()["pending_card"]


def accept(client,card):
    response=client.post("/api/decision",json={"card_id":card["card_id"],"action":"accept"},headers={"Idempotency-Key":"accept"})
    assert response.status_code==200,response.text


def test_legacy_day_one_to_two(client,service,run):
    card=start(client)
    assert card["package"]["ads_daily_budget"]==45000
    assert card["package"]["voucher_pct"]==3 and card["breakeven_roas_display"]==6.5
    accept(client,card)
    assert client.get("/api/state").json()["step"]=="content_review"
    retry=client.post("/api/content/retry",json={"feedback_vi":"Ảnh nền tối quá, làm sáng hơn"},headers={"Idempotency-Key":"retry1"})
    assert retry.status_code==200,retry.text
    assert retry.json()["draft"]["version"]==2
    used=client.post("/api/content/apply",json={"cover_option":"B"},headers={"Idempotency-Key":"use"})
    assert used.status_code==200,used.text
    night=client.post("/api/night",json={},headers={"Idempotency-Key":"night"})
    assert night.status_code==200,night.text
    assert night.json()["next_day"]==2 and night.json()["summary"]["lesson_ops"]==[]
    assert client.post("/api/night",json={},headers={"Idempotency-Key":"night"}).json()==night.json()
    assert client.get("/api/state").json()["step"]=="idle"
    with service.store.connect() as c:
        assert one(c,"SELECT * FROM learning_handoffs WHERE run_id=?",(run,))["error_code"]=="LEARNING_NOT_CONNECTED"


def test_retry_limits_and_old_card(client,run):
    card=start(client);accept(client,card)
    assert client.post("/api/decision",json={"card_id":card["card_id"],"action":"accept"},headers={"Idempotency-Key":"different"}).status_code==404
    for i in range(2):
        response=client.post("/api/content/retry",json={"feedback_vi":"Sáng hơn"},headers={"Idempotency-Key":f"retry{i}"})
        assert response.status_code==200,response.text
    assert client.post("/api/content/retry",json={"feedback_vi":"Sáng nữa"},headers={"Idempotency-Key":"over"}).status_code==409
    assert client.post("/api/night",json={},headers={"Idempotency-Key":"pending"}).status_code==409


def test_negotiate_and_reject(client,run):
    card=start(client)
    reply=client.post("/api/decision",json={"card_id":card["card_id"],"action":"negotiate","note_vi":"giảm voucher còn 2%"},headers={"Idempotency-Key":"negotiate"})
    assert reply.status_code==200,reply.text
    assert reply.json()["card"]["package"]["voucher_pct"]==2
    new=reply.json()["card"]
    rejected=client.post("/api/decision",json={"card_id":new["card_id"],"action":"reject"},headers={"Idempotency-Key":"reject"})
    assert rejected.status_code==200,rejected.text


def test_atomic_rollback_and_concurrent_events(service,client,run):
    p=service.authenticate(sid=client.cookies.get("growth_sid"))
    with service.store.connect() as c:before=c.execute("SELECT COUNT(*) FROM events WHERE run_id=?",(run,)).fetchone()[0]
    def broken(c):
        service.event(c,run,1,"auto_action","orchestrator","D")
        raise Fault("FAIL","Kiểm thử rollback")
    with pytest.raises(Fault):service.command(p,run,"/test","broken",{},broken)
    with service.store.connect() as c:assert c.execute("SELECT COUNT(*) FROM events WHERE run_id=?",(run,)).fetchone()[0]==before
    def write(i):
        with service.store.connect(write=True) as c:service.event(c,run,1,"auto_action","orchestrator","D",{"i":i})
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(write,range(80)))
    with service.store.connect() as c:
        assert c.execute("SELECT COUNT(DISTINCT seq) FROM events WHERE run_id=?",(run,)).fetchone()[0]==before+80
        assert not c.execute("PRAGMA foreign_key_check").fetchall()


def test_seven_day_reproducibility_and_no_fake_learning(service):
    a,p=run_scenario(service)
    b,_=run_scenario(service,seller=p,memory=False)
    gid=compare(service,p,a,b)
    with service.store.connect() as c:
        for r in (a,b):
            assert c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=?",(r,)).fetchone()[0]==35
            assert c.execute("SELECT COUNT(*) FROM daily_metrics WHERE run_id=? AND source='simulated'",(r,)).fetchone()[0]==70
            assert service.run(c,p,r)["current_day"]==7 and service.run(c,p,r)["phase"]=="complete"
            assert min(x["available_units"] for x in many(c,"SELECT * FROM inventory WHERE run_id=?",(r,)))>=0
        columns="day,shop_id,channel,orders,net_revenue_vnd,ad_spend_vnd,fees_vnd,contribution_vnd,realized_roas"
        assert many(c,f"SELECT {columns} FROM daily_metrics WHERE run_id=? ORDER BY day,shop_id,channel",(a,))==many(c,f"SELECT {columns} FROM daily_metrics WHERE run_id=? ORDER BY day,shop_id,channel",(b,))
        report=proof(service,c,p,a,gid)
        assert report["days"]==7 and len(report["metrics"])==5
        assert all(m["on"]==m["off"] for m in report["metrics"])
        assert "reference" in report["note_vi"]
        assert proof(service,c,p,a,gid,"legacy_6d")["days"]==6
    reopened=DataService(service.home)
    with reopened.store.connect() as c:assert reopened.run(c,p,a)["phase"]=="complete"


def test_upload_authorization_checksum_and_traversal(client,service,run):
    reset=client.post("/api/reset",json={"content_mode":"worker"},headers={"Idempotency-Key":"worker-reset"})
    assert reset.status_code==200,reset.text
    run=reset.json()["run_id"]
    card=start(client);accept(client,card)
    job=client.get(f"/api/v1/runs/{run}/state").json()["data"]["jobs"][0]
    token=role(service,run,"content_worker")
    content=placeholder_png(1);sha=hashlib.sha256(content).hexdigest()
    body={"product_id":"SP004","job_id":job["job_id"],"kind":"image","mime_type":"image/png","size_bytes":len(content),"sha256":sha}
    created=client.post(f"/api/v1/runs/{run}/assets/uploads",json=body,headers=headers(token,"upload"))
    assert created.status_code==201,created.text
    asset=created.json()["data"]["asset_id"]
    assert client.put(f"/api/v1/runs/{run}/assets/{asset}/bytes",content=b"wrong",headers=headers(token)).status_code==422
    assert client.put(f"/api/v1/runs/{run}/assets/{asset}/bytes",content=content,headers=headers(token)).status_code==200
    completed=client.post(f"/api/v1/runs/{run}/assets/{asset}/complete",json={"checksum":sha},headers=headers(token,"complete"))
    assert completed.status_code==200,completed.text
    assert client.get(f"/api/v1/runs/{run}/assets/{asset}/download",headers=headers(token)).content==content
    platform=role(service,run,"platform_agent")
    assert client.get(f"/api/v1/runs/{run}/assets/{asset}/download",headers=headers(platform)).status_code==404
    with pytest.raises(Fault):service.object_path("../../outside")
