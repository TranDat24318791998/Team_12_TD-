import hashlib
from fastapi.testclient import TestClient
from conftest import headers,role
from growth_data.api import create_app
from growth_data.storage import one
from test_workflow import start,accept


def finish_content(client):
    response=client.post("/api/content/apply",json={"cover_option":"B"},headers={"Idempotency-Key":"use"})
    assert response.status_code==200,response.text


def test_question_confirmation_and_decline_silence(client,service,run):
    card=start(client);accept(client,card);finish_content(client)
    token=role(service,run,"learning_worker")
    question={"external_pref_id":"D-style-bright","field":"content_style","value":"ảnh nền sáng","text_vi":"Lần sau tạo ảnh nền sáng?","based_on_rules_version":1}
    result=client.post(f"/internal/v1/runs/{run}/shops/D/rule-questions",json=question,headers=headers(token,"q"))
    assert result.status_code==201,result.text
    assert client.post("/api/night",json={},headers={"Idempotency-Key":"night"}).status_code==200
    assert client.post("/api/day/start",json={},headers={"Idempotency-Key":"day2"}).status_code==200
    q=client.get("/api/state").json()["pending_card"]
    assert q["kind"]=="question" and q["package"] is None
    answer=client.post("/api/decision",json={"card_id":q["card_id"],"action":"accept","rule_answer":True},headers={"Idempotency-Key":"yes"})
    assert answer.status_code==200,answer.text
    shop=role(service,run,"shop_agent")
    rules=client.get(f"/api/v1/runs/{run}/shops/D/rules",headers=headers(shop)).json()["data"]
    assert rules["rules_version"]==2 and rules["rules"]["content_style_notes"]==["ảnh nền sáng"]


def test_declined_preference_cannot_be_reasked_under_new_id(client,service,run):
    token=role(service,run,"learning_worker")
    body={"external_pref_id":"voucher-1","field":"voucher_max_pct","value":"2","text_vi":"Voucher tối đa 2%?","based_on_rules_version":1}
    q=client.post(f"/internal/v1/runs/{run}/shops/D/rule-questions",json=body,headers=headers(token,"q1")).json()["data"]
    response=client.post(f"/api/v1/runs/{run}/decisions",json={"target_type":"rule_question","target_id":q["question_id"],"target_version":1,"action":"reject","rule_answer":False},headers={"Idempotency-Key":"decline","X-Request-ID":"decline"})
    assert response.status_code==201,response.text
    again=client.post(f"/internal/v1/runs/{run}/shops/D/rule-questions",json={**body,"external_pref_id":"voucher-new-id"},headers=headers(token,"q2"))
    assert again.status_code==409
    with service.store.connect() as c:assert service.rules(c,run,"D")[1]==1


def test_external_learning_blocks_advance_and_accepts_result(tmp_path):
    app=create_app(tmp_path/"external",learning_mode="external");s=app.state.service
    with TestClient(app) as client:
        r=client.get("/api/state").json()["run_id"]
        card=start(client);accept(client,card);finish_content(client)
        token=role(s,r,"orchestrator",("*",))
        current=client.get(f"/api/v1/runs/{r}",headers=headers(token)).json()["data"]
        close=client.post(f"/api/v1/runs/{r}/days/close",json={"expected_day":1,"expected_version":current["version"]},headers=headers(token,"close"))
        assert close.status_code==202,close.text
        current=client.get(f"/api/v1/runs/{r}",headers=headers(token)).json()["data"]
        assert current["phase"]=="learning"
        advance=client.post(f"/api/v1/runs/{r}/days/advance",json={"expected_day":1,"expected_version":current["version"]},headers=headers(token,"blocked"))
        assert advance.status_code==409
        learning=role(s,r,"learning_worker",("*",))
        data=client.get(f"/internal/v1/runs/{r}/learning-input?day=1",headers=headers(learning)).json()["data"]
        summary={"day":1,"history_updates":["Đã xử lý kết quả"],"pref_candidates":[],"calibration":{"factor":1,"points":0,"mape_today":None},"lesson_ops":[],"rejected_ops":0,"memory_md_path":"../../sensitive"}
        result=client.post(f"/internal/v1/runs/{r}/learning-results",json={"day":1,"settlement_cursor":data["settlement_cursor"],"status":"completed","night_summary":summary},headers=headers(learning,"result"))
        assert result.status_code==200,result.text
        with s.store.connect() as c:
            report=one(c,"SELECT * FROM learning_handoffs WHERE run_id=?",(r,))["night_summary"]["memory_md_path"]
        assert report.startswith(f"/api/v1/runs/{r}/assets/") and "sensitive" not in report
        assert client.get(report).status_code==200
        current=client.get(f"/api/v1/runs/{r}",headers=headers(token)).json()["data"]
        assert client.post(f"/api/v1/runs/{r}/days/advance",json={"expected_day":1,"expected_version":current["version"]},headers=headers(token,"advance")).status_code==202


def test_worker_job_assignment_bad_claims_and_lease_recovery(tmp_path):
    app=create_app(tmp_path/"worker",content_mode="worker");s=app.state.service
    with TestClient(app) as client:
        r=client.get("/api/state").json()["run_id"]
        card=start(client);accept(client,card)
        with s.store.connect() as c:job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D' ORDER BY rowid DESC LIMIT 1",(r,))
        token=s.issue_token("content_worker",runs=(r,),shops=("D",),jobs=(job["job_id"],))
        unassigned=s.issue_token("content_worker",runs=(r,),shops=("D",),jobs=())
        assert client.get(f"/api/v1/runs/{r}/content-jobs/{job['job_id']}",headers=headers(unassigned)).status_code==404
        bad={"title":"Quạt pin 5000mAh","description":"Không ồn","images":[],"video":{}}
        result=client.post(f"/internal/v1/runs/{r}/content-jobs/{job['job_id']}/result",json={"expected_job_version":1,"status":"succeeded","content_candidates":bad},headers=headers(token,"bad"))
        assert result.status_code==422
        with s.store.connect(write=True) as c:c.execute("UPDATE content_jobs SET lease_until='2000-01-01T00:00:00+00:00' WHERE job_id=?",(job["job_id"],))
        assert s.recover()["content_jobs"]==1
        assert s.recover()["content_jobs"]==0
        finish_content(client)


def test_memory_off_rejects_preference_writes(client,service):
    r=client.post("/api/reset",json={"memory":False},headers={"Idempotency-Key":"off"}).json()["run_id"]
    token=role(service,r,"learning_worker")
    result=client.post(f"/internal/v1/runs/{r}/shops/D/rule-questions",json={"external_pref_id":"x","field":"content_style","value":"sáng","text_vi":"Sáng?","based_on_rules_version":1},headers=headers(token))
    assert result.status_code==403


def test_local_knowledge_and_revocation(client,service,run):
    token=role(service,run,"platform_agent")
    path=f"/api/v1/runs/{run}/knowledge/search"
    result=client.post(path,json={"query":"quảng cáo ngân sách","top_k":3},headers=headers(token,"search"))
    assert result.status_code==200,result.text
    assert result.json()["data"] and all(x["backend"]=="local_keyword" for x in result.json()["data"])
    admin=role(service,run,"knowledge_admin")
    revoked=client.post("/internal/v1/knowledge/documents/advertising_guide_demo/revoke",json={"document_version":1,"reason_vi":"Kiểm thử thu hồi"},headers=headers(admin,"revoke"))
    assert revoked.status_code==200
    assert client.get(f"/api/v1/runs/{run}/knowledge/documents/advertising_guide_demo",headers=headers(token)).status_code==404
