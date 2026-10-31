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
    scoped_shop=run['demo_shop_id']
    service.scope(c,p,g['run_on_id'],scoped_shop)
    service.scope(c,p,g['run_off_id'],scoped_shop)
    def metrics(rid):
        neg=many(c,"SELECT * FROM negotiations WHERE run_id=? AND shop_id=? AND day BETWEEN 4 AND 6 AND status!='running'",(rid,scoped_shop))
        first=100*sum(x["status"] in {"agreed","warning_only"} and x["platform_rounds"]==1 for x in neg)/len(neg) if neg else None
        cards=many(c,"SELECT * FROM cards WHERE run_id=? AND shop_id=? AND day BETWEEN 4 AND 6 AND kind='offer' AND status='resolved'",(rid,scoped_shop))
        edits=c.execute("SELECT COUNT(*) FROM decisions d JOIN proposals p ON p.run_id=d.run_id AND p.proposal_id=d.target_id JOIN negotiations n ON n.run_id=p.run_id AND n.negotiation_id=p.negotiation_id WHERE d.run_id=? AND d.shop_id=? AND n.day BETWEEN 4 AND 6 AND d.edited_package_json IS NOT NULL",(rid,scoped_shop)).fetchone()[0]
        rows=many(c,"SELECT * FROM daily_metrics WHERE run_id=? AND shop_id=? AND day BETWEEN 1 AND ? AND source='simulated'",(rid,scoped_shop,horizon))
        wasted=0;errors=[]
        for m in rows:
            if m["channel"]=="paid" and m["ad_spend_vnd"]:
                campaign=service.entity(c,"campaigns",rid,"campaign_id",m["campaign_id"])
                public=service.public(c,rid,m["shop_id"])
                cost=service.current_cost(c,rid,m["shop_id"],version=m["cost_version"])
                fees,_=service.fee_config(c,rid,m["fee_policy_version"],m["day"])
                be=financials(public["price"],cost["unit_cost_vnd"]+cost["other_unit_cost_vnd"],campaign["package_snapshot"]["voucher_pct"],fees)["break_even_roas"]
                if be is not None and m["realized_roas"]<be:wasted+=m["ad_spend_vnd"]
        for sid in [scoped_shop]:
            for day in range(4,7):
                actual=sum(x["orders"] for x in rows if x["shop_id"]==sid and x["day"]==day)
                f=one(c,"SELECT * FROM daily_predictions WHERE run_id=? AND shop_id=? AND day=?",(rid,sid,day))
                if f and actual>0:errors.append(abs(f['payload']['issued_point']-actual)/actual)
        return [first,100*edits/len(cards) if cards else None,100*sum(errors)/len(errors) if errors else None,wasted,sum(x["contribution_vnd"] for x in rows)]
    on,off=metrics(g["run_on_id"]),metrics(g["run_off_id"])
    definitions=[("first_round_accept","Chốt ngay lượt đầu ngày 4–6","higher","%"),("seller_edit_rate","Người bán sửa thẻ ngày 4–6","lower","%"),("forecast_mape","Sai số dự báo ngày 4–6","lower","%"),("wasted_ads","Chi ads vào ngày dưới hòa vốn","lower","đ"),("seller_profit","Lãi sau phí và quảng cáo","higher","đ")]
    return {"seed":g["seed"],"days":horizon,"shop_id":scoped_shop,"run_on":g["run_on_id"],"run_off":g["run_off_id"],"metrics":[dict(key=k,label_vi=label,better=better,unit=unit,on=on[i],off=off[i]) for i,(k,label,better,unit) in enumerate(definitions)],
            'comparison_days':comparison_days(service,c,g,scoped_shop,horizon),
            "source":run["config"].get("source","simulation"),"execution_profile":run["execution_profile"],
            "note_vi":f"Dữ liệu giả lập; seed {g['seed']}; {horizon} ngày; shop {scoped_shop}; nguồn {run['config'].get('source','simulation')}, profile {run['execution_profile']}. Không tự suy ra agent tiến bộ từ fixture/reference. Null nghĩa là không đủ mẫu; loại MAPE ngày có actual=0 hoặc thiếu forecast. Các chi phí vận hành chưa mô hình hóa được loại trừ."}


def comparison_days(service,c,group,shop,horizon):
    on=service.entity(c,'runs',group['run_on_id'],'run_id',group['run_on_id'])
    off=service.entity(c,'runs',group['run_off_id'],'run_id',group['run_off_id'])
    if not on['brief'] or not off['brief']: return []
    fields=('intent','goal_vi','allow_ads','ads_daily_cap','content_refresh','duration_days','version','shop_id')
    if any(on['brief'].get(field)!=off['brief'].get(field) for field in fields): return []
    category=service.entity(c,'shops',on['run_id'],'shop_id',shop)['category']
    confirmations={}
    for run in (on,off):
        event=one(c,"SELECT seq FROM events WHERE run_id=? AND shop_id=? AND type='brief_confirmed' AND json_extract(payload_json,'$.brief_id')=? ORDER BY seq LIMIT 1",(run['run_id'],shop,run['brief']['brief_id']))
        if not event: return []
        confirmations[run['run_id']]=event['seq']

    def branch(run,day,enabled):
        rid=run['run_id']
        rows=many(c,"SELECT * FROM events WHERE run_id=? AND shop_id=? AND day=? AND type IN ('platform_turn','shop_turn','seller_decision','referee_review') ORDER BY seq",(rid,shop,day))
        actors={'platform_turn':'platform_agent','shop_turn':'shop_agent','seller_decision':'seller','referee_review':'system'}
        messages=[{'id':f"{rid}:{row['seq']}",'actor':actors[row['type']],'text_vi':service.safe_text(c,rid,row['payload'].get('note_vi') or row['text_vi']),'event_seq':row['seq']} for row in rows if row['text_vi']]
        used=[]
        if enabled:
            reads=many(c,"SELECT * FROM events WHERE run_id=? AND shop_id=? AND day=? AND type='tool_result' AND json_extract(payload_json,'$.tool_name')='read_memory' AND json_extract(payload_json,'$.status')='ok' ORDER BY seq",(rid,shop,day))
            refs=[ref for row in reads for ref in row['payload'].get('record_refs',[]) if isinstance(ref,dict)]
            for ref in refs:
                record=one(c,'SELECT * FROM knowledge_records WHERE run_id=? AND record_key=? AND scope IN (?,?,?) ORDER BY compartment LIMIT 1',(rid,ref.get('id'),shop,category,'strategy'))
                if not record: continue
                value=record['payload']['value']
                if ref.get('version') is not None and value.get('version')!=ref['version']: continue
                candidates=[]
                for seq in value.get('evidence_seqs',[]):
                    event=one(c,'SELECT * FROM events WHERE run_id=? AND shop_id=? AND seq=? AND day<?',(rid,shop,seq,day))
                    if event: candidates.append(event)
                if not candidates:
                    for nid in value.get('evidence',[]):
                        event=one(c,"SELECT * FROM events WHERE run_id=? AND shop_id=? AND day<? AND type='negotiation_finished' AND json_extract(payload_json,'$.negotiation_id')=? ORDER BY seq DESC LIMIT 1",(rid,shop,day,nid))
                        if event: candidates.append(event)
                if candidates:
                    event=max(candidates,key=lambda x:x['seq'])
                    item={'run_id':rid,'source_day':event['day'],'event_seq':event['seq'],'text_vi':service.safe_text(c,rid,value.get('text_vi') or event['text_vi']),'record_id':ref['id'],'record_version':ref.get('version')}
                    if item not in used: used.append(item)
        result={'run_id':rid,'messages':messages,'memory_used':used,'result_vi':'Đã ghi nhận kết quả ngày này.' if one(c,"SELECT seq FROM events WHERE run_id=? AND shop_id=? AND day=? AND type='market_result'",(rid,shop,day)) else ''}
        return result

    result=[]
    for day in range(1,horizon+1):
        left,right=branch(off,day,False),branch(on,day,True)
        if not left['messages'] or not right['messages']: continue
        result.append({'day':day,'request_vi':on['brief']['goal_vi'],'request_version':on['brief']['version'],
                       'request_refs':{'on':{'brief_id':on['brief']['brief_id'],'event_seq':confirmations[on['run_id']]},'off':{'brief_id':off['brief']['brief_id'],'event_seq':confirmations[off['run_id']]}},
                       'situation_vi':'Mục tiêu đã xác nhận cho hai nhánh.',
                       'takeaway_vi':'Hội thoại và bằng chứng lấy từ từng run tương ứng.',
                       'off':left,'on':right})
    return result


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
