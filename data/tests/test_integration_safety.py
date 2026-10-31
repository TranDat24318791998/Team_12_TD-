"""Migration, durable lifecycle, publication and scoped presentation contracts."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from conftest import headers,role
from test_workflow import start,accept
from growth_data.api import create_app
from growth_data.service import DataService,Principal
from growth_data.storage import Store,one,many
from growth_data.errors import Fault
from growth_data.harness import HttpHarness


def test_v1_migration_preserves_audit_and_failed_ddl_rolls_back(tmp_path,monkeypatch):
    path=tmp_path/"old.db"
    migration=Path(__file__).parents[1]/"growth_data/migrations/001_initial.sql"
    c=sqlite3.connect(path);c.executescript(migration.read_text())
    c.execute("INSERT INTO schema_migrations VALUES(1,'old')")
    c.execute("INSERT INTO sessions VALUES('historical-session','old')")
    c.execute("PRAGMA user_version=1");c.commit();c.close()
    broken=tmp_path/"broken";broken.mkdir()
    (broken/"001_initial.sql").write_text(migration.read_text())
    (broken/"002_broken.sql").write_text("ALTER TABLE sessions ADD COLUMN never_committed TEXT;\nTHIS IS NOT SQL;\n")
    with monkeypatch.context() as patch:
        patch.setattr(Store,"migrations_path",broken)
        with pytest.raises(sqlite3.OperationalError):Store(path)
    c=sqlite3.connect(path)
    assert c.execute("PRAGMA user_version").fetchone()[0]==1
    assert "never_committed" not in {x[1] for x in c.execute("PRAGMA table_info(sessions)")}
    c.close()
    store=Store(path)
    with store.connect() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0]==4
        assert c.execute("SELECT * FROM sessions").fetchall()[0][0]=="historical-session"
        assert [x[0] for x in c.execute("SELECT version FROM schema_migrations ORDER BY version")]==[1,2,3,4]
    Store(path)  # Idempotent upgrade, no second migration effects.


def test_service_creator_grant_and_v1_reset(client,service):
    token=service.issue_token("orchestrator",runs=(),shops=("D",))
    created=client.post("/api/v1/runs",json={},headers=headers(token,"create"))
    assert created.status_code==201,created.text
    r=created.json()["data"]["run_id"]
    assert client.get(f"/api/v1/runs/{r}",headers=headers(token)).status_code==200
    other=service.issue_token("orchestrator",runs=(),shops=("D",))
    assert client.get(f"/api/v1/runs/{r}",headers=headers(other)).status_code==404
    seller=client.get("/api/state").json()
    reset=client.post(f"/api/v1/runs/{seller['run_id']}/reset",json={"expected_version":1},headers=headers("", "v1-reset") | {"Authorization":""})
    assert reset.status_code==201,reset.text
    assert reset.json()["data"]["run_id"]!=seller["run_id"]


def prepare_external_night(client):
    r=client.post("/api/reset",json={"learning_mode":"external"},headers={"Idempotency-Key":"ext-reset"}).json()["run_id"]
    card=start(client);accept(client,card)
    assert client.get("/api/state").json()["active_package"] is None
    client.post("/api/content/apply",json={"cover_option":"B"},headers={"Idempotency-Key":"apply"}).raise_for_status()
    night=client.post("/api/night",json={},headers={"Idempotency-Key":"night"})
    assert night.status_code==202,night.text
    return r,night.json()


def test_external_legacy_night_survives_restart_and_receipt_advance_once(client,service):
    r,night=prepare_external_night(client)
    with service.store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=?",(r,)).fetchone()[0]==5
        before=one(c,"SELECT * FROM inventory WHERE run_id=? AND product_id='SP004'",(r,))
    restarted=create_app(service.home)
    token=role(service,r,"learning_worker")
    with TestClient(restarted) as worker:
        evidence=worker.get(f"/internal/v1/runs/{r}/learning-input?day=1",headers=headers(token)).json()["data"]
        summary=service.empty_summary(1)
        body={"day":1,"settlement_cursor":evidence["settlement_cursor"],"expected_version":evidence["version"],"status":"completed","night_summary":summary,"receipt_id":"committed-memory-receipt"}
        result=worker.post(f"/internal/v1/runs/{r}/learning-results",json=body,headers=headers(token,"result"))
        assert result.status_code==200,result.text
        assert worker.post(f"/internal/v1/runs/{r}/learning-results",json=body,headers=headers(token,"different-key-same-receipt")).status_code==200
        changed={**body,"night_summary":{**summary,"history_updates":["Different"]}}
        assert worker.post(f"/internal/v1/runs/{r}/learning-results",json=changed,headers=headers(token,"conflict")).status_code==409
    retried=client.post("/api/night",json={},headers={"Idempotency-Key":"night"})
    assert retried.status_code==200 and retried.json()["next_day"]==2
    assert client.get("/api/state").json()["day"]==2
    with service.store.connect() as c:
        assert one(c,"SELECT * FROM inventory WHERE run_id=? AND product_id='SP004'",(r,))==before
        assert c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=?",(r,)).fetchone()[0]==5
    report=client.get("/api/state").json()["last_night"]["memory_md_path"]
    assert client.get(report).status_code==200
    platform=role(service,r,"platform_agent")
    assert client.get(report,headers=headers(platform)).status_code==404


@pytest.mark.parametrize("action",["retry","skip"])
def test_learning_timeout_heartbeat_controls_do_not_resettle(client,service,action):
    r,night=prepare_external_night(client)
    token=role(service,r,"learning_worker")
    evidence=client.get(f"/internal/v1/runs/{r}/learning-input?day=1",headers=headers(token)).json()["data"]
    heartbeat=client.post(f"/internal/v1/runs/{r}/learning-results",json={"day":1,"settlement_cursor":evidence["settlement_cursor"],"expected_version":1,"status":"running"},headers=headers(token,"heartbeat"))
    assert heartbeat.json()["data"]["version"]==2
    with service.store.connect(write=True) as c:c.execute("UPDATE learning_handoffs SET lease_until='2000-01-01' WHERE run_id=?",(r,))
    service.recover()
    state=client.get("/api/state").json()
    assert state["day"]==1 and state["learning_status"]=="failed"
    operation=client.get(f"/api/v1/runs/{r}/operations/{night['operation_id']}").json()["data"]
    assert operation["status"]=="failed"
    current=client.get(f"/internal/v1/runs/{r}/learning-input?day=1",headers=headers(token)).json()["data"]
    controlled=client.post(f"/api/v1/runs/{r}/days/1/learning/{action}",json={"expected_version":current["version"],"reason_vi":"Seller xử lý timeout"},headers={"Idempotency-Key":"control","X-Request-ID":"test"})
    assert controlled.status_code==200,controlled.text
    assert controlled.json()["data"]["settlement_cursor"]==evidence["settlement_cursor"]
    if action=="skip":
        assert client.get("/api/state").json()["day"]==2
        assert controlled.json()["data"]["error_code"]=="SELLER_SKIPPED"
    else:assert client.get("/api/state").json()["learning_status"]=="pending"
    with service.store.connect() as c:assert c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=?",(r,)).fetchone()[0]==5


def test_publish_failure_rolls_back_and_restore_seed_and_previous(client,service,run,monkeypatch):
    card=start(client);accept(client,card)
    original=client.get("/api/state").json()["content_refs"]["active_content_id"]
    with service.store.connect() as c:assert not one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id='D'",(run,))
    normal=service.apply
    def broken(*args,**kwargs):
        normal(*args,**kwargs)
        raise Fault("INJECTED_FAILURE","Lỗi sau campaign trước commit")
    with monkeypatch.context() as patch:
        patch.setattr(service,"apply",broken)
        failed=client.post("/api/content/apply",json={"cover_option":"B"},headers={"Idempotency-Key":"failed-publish"})
        assert failed.status_code==409
    assert client.get("/api/state").json()["content_refs"]["active_content_id"]==original
    with service.store.connect() as c:assert not one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id='D'",(run,))
    applied=client.post("/api/content/apply",json={"cover_option":"B"},headers={"Idempotency-Key":"apply-ok"})
    assert applied.status_code==200,applied.text
    state=client.get("/api/state").json();published=state["content_refs"]["active_content_id"]
    with service.store.connect() as c:
        seed=service.entity(c,"content_versions",run,"content_id",original)
        package=one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id='D'",(run,))
    body={"expected_active_content_id":published,"expected_content_version":seed["version"]}
    restored=client.post(f"/api/v1/runs/{run}/content/{original}/restore",json=body,headers={"Idempotency-Key":"restore-seed","X-Request-ID":"restore"})
    assert restored.status_code==200,restored.text
    assert restored.json()["data"]["listing"]["title"]==state["demo_shop_original"]["title"]
    with service.store.connect() as c:
        old=service.entity(c,"content_versions",run,"content_id",published)
        assert one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id='D'",(run,))==package
    again=client.post("/api/content/undo",json={"target_content_id":published,"expected_active_content_id":restored.json()["data"]["content_id"],"expected_content_version":old["version"]},headers={"Idempotency-Key":"restore-published","X-Request-ID":"restore-published"})
    assert again.status_code==200,again.text
    assert again.json()["listing"]["title"]==state["demo_shop"]["title"]


def test_operation_claim_concurrency_and_expiry_requires_explicit_resume(client,service):
    state=client.post("/api/reset",json={"execution_profile":"external"},headers={"Idempotency-Key":"reset-external"}).json()["state"]
    r=state["run_id"];token=role(service,r,"orchestrator",("*",))
    started=client.post("/api/day/start",json={},headers={"Idempotency-Key":"external-start"})
    assert started.json()["step"]=="negotiating"
    op=client.get(f"/api/v1/runs/{r}/operations?status=queued",headers=headers(token)).json()["data"][0]
    def claim(i):return client.post(f"/internal/v1/runs/{r}/operations/{op['operation_id']}/claim",json={"expected_version":op["version"]},headers=headers(token,f"claim-{i}"))
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(claim,[1,2]))
    assert sorted(x.status_code for x in responses)==[200,409]
    with service.store.connect(write=True) as c:c.execute("UPDATE operations SET lease_until='2000-01-01' WHERE run_id=?",(r,))
    service.recover()
    expired=client.get(f"/api/v1/runs/{r}/operations/{op['operation_id']}",headers=headers(token)).json()["data"]
    assert expired["status"]=="failed" and expired["error_code"]=="LEASE_EXPIRED_RESULT_UNKNOWN"
    assert client.get(f"/api/v1/runs/{r}/shops/D/history",headers=headers(token)).json()["data"]==[]


def test_worker_assignment_source_and_report_private_scope(client,service):
    r=client.post("/api/reset",json={"content_mode":"worker"},headers={"Idempotency-Key":"worker"}).json()["run_id"]
    card=start(client);accept(client,card)
    job=client.get(f"/api/v1/runs/{r}/state").json()["data"]["jobs"][0]
    allowed=service.issue_token("content_worker",runs=(r,),shops=("D",),jobs=(job["job_id"],))
    denied=service.issue_token("content_worker",runs=(r,),shops=("D",),jobs=("other-job",))
    assert client.get(f"/api/v1/runs/{r}/content-jobs/{job['job_id']}",headers=headers(denied)).status_code==404
    assert client.get(f"/api/v1/runs/{r}/shops/D/content",headers=headers(denied)).json()["data"]==[]
    source=job["input_asset_ids"][0]
    assert client.get(f"/api/v1/runs/{r}/assets/{source}/download",headers=headers(allowed)).status_code==200
    assert client.get(f"/api/v1/runs/{r}/assets/{source}/download",headers=headers(denied)).status_code==404
    raw=b"\x89PNG\r\n\x1a\nfixture";body={"product_id":"SP004","job_id":job["job_id"],"kind":"image","mime_type":"image/png","size_bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
    assert client.post(f"/api/v1/runs/{r}/assets/uploads",json=body,headers=headers(denied,"bad-upload")).status_code==404


def test_concurrent_publish_and_night_have_one_business_effect(client,service,run):
    card=start(client);accept(client,card)
    def publish(i):return client.post("/api/content/apply",json={"cover_option":"B"},headers={"Idempotency-Key":"same-publication"})
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(publish,[1,2]))
    assert all(x.status_code==200 for x in responses) and responses[0].json()==responses[1].json()
    def night(i):return client.post("/api/night",json={},headers={"Idempotency-Key":"same-night"})
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(night,[1,2]))
    assert all(x.status_code==200 for x in responses) and responses[0].json()==responses[1].json()
    assert client.get("/api/state").json()["day"]==2
    with service.store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM campaigns WHERE run_id=? AND shop_id='D'",(run,)).fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM events WHERE run_id=? AND shop_id='D' AND type='content_applied'",(run,)).fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=?",(run,)).fetchone()[0]==5


def test_external_memory_receipt_retry_after_data_transaction_failure(client,service,monkeypatch):
    r,night=prepare_external_night(client)
    token=role(service,r,"learning_worker")
    evidence=client.get(f"/internal/v1/runs/{r}/learning-input?day=1",headers=headers(token)).json()["data"]
    # The fake memory owner has committed once before posting its receipt.
    committed={"receipt":"fixture-memory-already-committed","commits":1}
    body={"day":1,"settlement_cursor":evidence["settlement_cursor"],"expected_version":evidence["version"],"status":"completed","night_summary":service.empty_summary(1),"receipt_id":committed["receipt"]}
    def fail(*args):raise Fault("INJECTED_FAILURE","Lỗi sau nhận memory receipt trước advance")
    with monkeypatch.context() as patch:
        patch.setattr(service,"finish_night_tx",fail)
        result=client.post(f"/internal/v1/runs/{r}/learning-results",json=body,headers=headers(token,"memory-result"))
        assert result.status_code==409
    with service.store.connect() as c:assert one(c,"SELECT * FROM learning_handoffs WHERE run_id=?",(r,))["status"]=="pending"
    result=client.post(f"/internal/v1/runs/{r}/learning-results",json=body,headers=headers(token,"memory-result"))
    assert result.status_code==200,result.text
    assert committed["commits"]==1 and client.get("/api/state").json()["day"]==2
    with service.store.connect() as c:assert c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=?",(r,)).fetchone()[0]==5


def test_images_only_retry_preserves_video_and_rejects_text_changes(client,service):
    h=HttpHarness(client,service.issue_token)
    r=h.post("/api/reset",{"content_mode":"worker","data_source":"fixture"} if False else {"content_mode":"worker"})["run_id"]
    card=start(client);accept(client,card)
    job=h.get(f"/api/v1/runs/{r}/state")["jobs"][0]
    token=h.token(r,"content_worker","D",job["job_id"])
    draft=next(x for x in h.get(f"/api/v1/runs/{r}/shops/D/content",token) if x["content_id"] in job["output_content_ids"])
    # Signature-only MP4 fixture; real playback is a separate Gate B requirement.
    aid=h.upload(r,token,b'\x00\x00\x00\x18ftypmp42'+b'\x00'*32,kind="video",product="SP004",job=job["job_id"])
    video={"status":"done","asset_id":aid,"job_id":"fixture-video","prompt":"Fixture, not Muse playback"}
    h.post(f"/internal/v1/runs/{r}/content-jobs/{job['job_id']}/result",{"expected_job_version":job["version"],"status":"succeeded","fallback_used":True,"content_candidates":{"title":draft["title"],"description":draft["description"],"images":draft["cover_options"],"video":video}},token)
    before=h.get("/api/state")["content_draft"]
    after=h.post("/api/content/retry",{"feedback_vi":"Chỉ làm ảnh sáng hơn","retry_scope":"images"})["draft"]
    assert (after["title"],after["description"],after["video"])==(before["title"],before["description"],before["video"])
    new_job=h.get(f"/api/v1/runs/{r}/state")["jobs"][-1]
    assigned=h.token(r,"content_worker","D",new_job["job_id"])
    new_draft=next(x for x in h.get(f"/api/v1/runs/{r}/shops/D/content",assigned) if x["content_id"] in new_job["output_content_ids"])
    changed={"title":"Quạt để bàn","description":after["description"],"images":new_draft["cover_options"],"video":new_draft["video_job"]}
    bad=client.post(f"/internal/v1/runs/{r}/content-jobs/{new_job['job_id']}/result",json={"expected_job_version":new_job["version"],"status":"succeeded","fallback_used":True,"content_candidates":changed},headers=headers(assigned,"changed-text"))
    assert bad.status_code==422 and bad.json()["error"]["code"]=="RETRY_SCOPE"
    assert client.post(f"/internal/v1/runs/{r}/content-jobs/{job['job_id']}/result",json={"expected_job_version":2,"status":"running"},headers=headers(token,"late-result")).status_code==409
