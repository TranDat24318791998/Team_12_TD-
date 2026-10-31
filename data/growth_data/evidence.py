"""Headless reference scenarios and evidence calculated solely from stored outcomes."""

from .service import Principal
from .facade import Facade
from .storage import many, one, insert, now, uid
from .errors import require
from .finance import financials
from .seed import world


def run_scenario(service, *, seed=42, memory=True, days=7, seller=None):
    p=seller or service.bootstrap()
    with service.store.connect(write=True) as c:
        created=service.create_run(c,p,{"seed":seed,"memory_enabled":memory,"simulation_days":days})
    r=created["run_id"];facade=Facade(service)
    for day in range(1,days+1):
        with service.store.connect(write=True) as c:
            run=service.run(c,p,r)
            service.operation(c,p,r,"start_day",dict(expected_day=day,expected_version=run["version"]))
            card=one(c,"SELECT * FROM cards WHERE run_id=? AND shop_id='D' AND status='pending'",(r,))
            if card:
                facade.decide(c,p,r,{"card_id":card["card_id"],"action":"accept",**({"rule_answer":True} if card["question_id"] else {})})
                state=facade.state(c,p)
                if state["step"]=="content_review":
                    if not any("sáng" in v for v in state["content_draft"]["style_notes"]):facade.retry(c,p,r,{"feedback_vi":"Ảnh nền tối quá, làm sáng hơn giúp chị."})
                    facade.use_content(c,p,r,{"cover_option":"B"})
            facade.night(c,p,r)
    return r,p


def compare(service,p,run_on,run_off):
    with service.store.connect(write=True) as c:
        return service.comparison_attach(c,p,{"run_on":run_on,"run_off":run_off})["comparison_id"]


def proof(service,c,p,r,gid,variant="full_7d"):
    service.require_comparison_role(p)
    run=service.run(c,p,r)
    g=one(c,"SELECT * FROM comparison_groups WHERE group_id=?",(gid,))
    require(g and r in {g["run_on_id"],g["run_off_id"]},"NOT_FOUND","Không tìm thấy đối chứng",404)
    service.run(c,p,g["run_on_id"]);service.run(c,p,g["run_off_id"])
    require(service.comparison_view(c,p,gid)["status"]=="ready","PROOF_NOT_READY","Đối chứng chưa hoàn tất",409)
    require(variant in {"full_7d","legacy_6d"},"VARIANT_INVALID","Variant không hợp lệ",422)
    horizon=6 if variant=="legacy_6d" else g["days"]
    def metrics(rid):
        neg=many(c,"SELECT * FROM negotiations WHERE run_id=? AND day BETWEEN 4 AND 6 AND status!='running'",(rid,))
        first=100*sum(x["status"] in {"agreed","warning_only"} and x["platform_rounds"]==1 for x in neg)/len(neg) if neg else None
        cards=many(c,"SELECT * FROM cards WHERE run_id=? AND day BETWEEN 4 AND 6 AND kind='offer' AND status='resolved'",(rid,))
        edits=c.execute("SELECT COUNT(*) FROM decisions d JOIN proposals p ON p.run_id=d.run_id AND p.proposal_id=d.target_id JOIN negotiations n ON n.run_id=p.run_id AND n.negotiation_id=p.negotiation_id WHERE d.run_id=? AND n.day BETWEEN 4 AND 6 AND d.edited_package_json IS NOT NULL",(rid,)).fetchone()[0]
        rows=many(c,"SELECT * FROM daily_metrics WHERE run_id=? AND day BETWEEN 1 AND ? AND source='simulated'",(rid,horizon))
        wasted=0;errors=[]
        for m in rows:
            if m["channel"]=="paid" and m["ad_spend_vnd"]:
                campaign=service.entity(c,"campaigns",rid,"campaign_id",m["campaign_id"])
                public=service.public(c,rid,m["shop_id"])
                cost=service.current_cost(c,rid,m["shop_id"],version=m["cost_version"])
                fees,_=service.fee_config(c,rid,m["fee_policy_version"],m["day"])
                be=financials(public["price"],cost["unit_cost_vnd"]+cost["other_unit_cost_vnd"],campaign["package_snapshot"]["voucher_pct"],fees)["break_even_roas"]
                if be is not None and m["realized_roas"]<be:wasted+=m["ad_spend_vnd"]
        for sid in "ABCDE":
            for day in range(4,7):
                actual=sum(x["orders"] for x in rows if x["shop_id"]==sid and x["day"]==day)
                f=one(c,"SELECT f.* FROM forecasts f JOIN proposals p ON p.run_id=f.run_id AND p.proposal_id=f.proposal_id JOIN campaigns a ON a.run_id=p.run_id AND a.proposal_id=p.proposal_id WHERE f.run_id=? AND p.shop_id=? AND f.as_of_day<=? AND f.period_start_day<=? AND f.period_end_day>=? ORDER BY f.as_of_day DESC,f.created_at DESC LIMIT 1",(rid,sid,day,day,day))
                if f and actual>0:errors.append(abs(f["daily_point_units"][day-f["period_start_day"]]-actual)/actual)
        return [first,100*edits/len(cards) if cards else None,100*sum(errors)/len(errors) if errors else None,wasted,sum(x["contribution_vnd"] for x in rows)]
    on,off=metrics(g["run_on_id"]),metrics(g["run_off_id"])
    definitions=[("first_round_accept","Chốt ngay lượt đầu ngày 4–6","higher","%"),("seller_edit_rate","Người bán sửa thẻ ngày 4–6","lower","%"),("forecast_mape","Sai số dự báo ngày 4–6","lower","%"),("wasted_ads","Chi ads vào ngày dưới hòa vốn","lower","đ"),("seller_profit","Lãi sau phí và quảng cáo","higher","đ")]
    return {"seed":g["seed"],"days":horizon,"run_on":g["run_on_id"],"run_off":g["run_off_id"],"metrics":[dict(key=k,label_vi=label,better=better,unit=unit,on=on[i],off=off[i]) for i,(k,label,better,unit) in enumerate(definitions)],
            "source":run["config"].get("source","simulation"),"execution_profile":run["execution_profile"],
            "note_vi":f"Dữ liệu giả lập; seed {g['seed']}; {horizon} ngày; nguồn {run['config'].get('source','simulation')}, profile {run['execution_profile']}. Data API chưa nối/không sở hữu thuật toán học; worker báo cáo kết quả. Không tự suy ra agent tiến bộ từ fixture/reference. Null nghĩa là không đủ mẫu; loại MAPE ngày có actual=0 hoặc thiếu forecast. Các chi phí vận hành chưa mô hình hóa được loại trừ."}


def replay_export(service,c,p,r):
    service.scope(c,p,r,roles={"data_admin","evaluator","orchestrator"})
    run=service.run(c,p,r)
    shops=[s for s in "ABCDE" if "*" in p.allowed_shop_ids or s in p.allowed_shop_ids]
    public=Principal("replay_public","platform_agent",p.session_id,(r,),tuple(shops))
    events=[];cursor=0
    while True:
        page,cursor,more=service.events(c,public,r,cursor,100)
        events.extend(page)
        if not more:break
    assets=many(c,"SELECT asset_id,shop_id,sha256,mime_type FROM assets WHERE run_id=? AND visibility='published' AND upload_status='ready'",(r,))
    assets=[a for a in assets if a["shop_id"] in shops]
    for asset in assets:asset["url"]=f"/api/v1/runs/{r}/assets/{asset['asset_id']}/download"
    recording=one(c,"SELECT * FROM run_artifacts WHERE run_id=? AND kind='recording'",(r,))
    recording_view={"asset_id":recording["asset_id"],"sha256":recording["sha256"],"manifest":recording["metadata"]} if recording else None
    return {"run_id":r,"scenario_version":run["scenario_version"],"seed":run["seed"],"days":run["simulation_days"],"synthetic":True,"recording_kind":recording["metadata"]["source"] if recording else "reference_offline" if run["execution_profile"]=="reference" else "external_audit","faithful_llm_replay":False,"recording":recording_view,"player_available":False,
            "events":events,"snapshots":[service.public(c,r,s) for s in shops],"assets":assets,
            "note_vi":"Chỉ nhánh driver local; không có recording LLM. Quyết định khác recording cần run offline mới, không tiếp tục các event tương lai."}
