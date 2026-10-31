from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient
from conftest import headers,role
from growth_data.api import create_app
from growth_data.service import Principal
from growth_data.storage import one
from growth_data.errors import Fault
from test_workflow import start,accept


def test_concurrent_apply_different_keys_has_one_business_effect(client,service,run):
    card=start(client)
    with service.store.connect() as c:prop=service.entity(c,"proposals",run,"proposal_id",one(c,"SELECT * FROM cards WHERE run_id=? AND card_id=?",(run,card["card_id"]))["proposal_id"])
    # This case exercises direct campaign activation without a content workflow.
    # Content-refresh packages now require publication first (separate tests).
    response=client.post(f"/api/v1/runs/{run}/decisions",json={"target_type":"proposal","target_id":prop["proposal_id"],"target_version":prop["version"],"action":"approve","edited_package":{**prop["package"],"content_refresh":False}},headers={"Idempotency-Key":"approve","X-Request-ID":"approve"})
    assert response.status_code==201,response.text
    decision=response.json()["data"]
    p=Principal("test_orchestrator","orchestrator",None,(run,),("D",))
    body={"proposal_id":decision["target_id"],"approval_decision_id":decision["decision_id"],"expected_inventory_version":1,"expected_rules_version":1}
    def apply(key):return service.command(p,run,"/apply",key,body,lambda c:service.apply(c,p,run,body))
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(apply,["key-1","key-2"]))
    assert results[0]["campaign_id"]==results[1]["campaign_id"]
    with service.store.connect() as c:assert c.execute("SELECT COUNT(*) FROM campaigns WHERE run_id=? AND shop_id='D'",(run,)).fetchone()[0]==1


def test_worker_valid_result_is_saved_and_approved_explicitly(tmp_path):
    app=create_app(tmp_path/"worker",content_mode="worker");s=app.state.service
    with TestClient(app) as client:
        r=client.get("/api/state").json()["run_id"];card=start(client);accept(client,card)
        with s.store.connect() as c:
            job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D'",(r,))
            draft=s.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
        token=s.issue_token("content_worker",runs=(r,),shops=("D",),jobs=(job["job_id"],))
        candidate={"title":draft["title"],"description":draft["description"],"images":draft["cover_options"],"video":draft["video_job"],"checks":["Thuộc tính từ seed"]}
        result=client.post(f"/internal/v1/runs/{r}/content-jobs/{job['job_id']}/result",json={"expected_job_version":1,"status":"succeeded","content_candidates":candidate},headers=headers(token,"result"))
        assert result.status_code==200,result.text
        with s.store.connect() as c:assert s.product(c,r,"D")["active_content_id"]!=draft["content_id"]
        published=client.post("/api/content/apply",json={"cover_option":"B"},headers={"Idempotency-Key":"publish"})
        assert published.status_code==200,published.text
        with s.store.connect() as c:assert s.product(c,r,"D")["active_content_id"]==draft["content_id"]


def test_failed_settlement_transaction_rolls_back_inventory(client,service,run):
    card=start(client)
    client.post("/api/decision",json={"card_id":card["card_id"],"action":"reject"},headers={"Idempotency-Key":"reject"}).raise_for_status()
    p=Principal("sim_test","simulator",None,(run,),("D",))
    with service.store.connect() as c:inv=service.entity(c,"inventory",run,"product_id","SP004")
    def fail(c):
        service.settle(c,p,run,"D",{"day":1,"expected_inventory_version":inv["version"]})
        raise Fault("ROLLBACK_TEST","Giả lập lỗi sau ghi settlement")
    with pytest.raises(Fault):service.command(p,run,"/settle","failure",{},fail)
    with service.store.connect() as c:
        assert service.entity(c,"inventory",run,"product_id","SP004")==inv
        assert not one(c,"SELECT * FROM day_settlements WHERE run_id=? AND shop_id='D'",(run,))
        assert c.execute("SELECT COUNT(*) FROM daily_metrics WHERE run_id=? AND shop_id='D' AND source='simulated'",(run,)).fetchone()[0]==0


def test_four_pdf_guides_and_manifest_checksums():
    import hashlib
    import pypdfium2 as pdfium
    root=Path(__file__).resolve().parents[1]/"datasets"
    pdfs=sorted((root/"pdf").glob("*.pdf"))
    assert len(pdfs)==4
    for path in pdfs:
        doc=pdfium.PdfDocument(path)
        assert len(doc)==1
        text=doc[0].get_textpage().get_text_range()
        assert "Simulation material" in text
        doc.close()
    manifest=json.loads((root/"manifest.json").read_text())
    for relative,entry in manifest["files"].items():
        assert hashlib.sha256((root/relative).read_bytes()).hexdigest()==entry["sha256"]
