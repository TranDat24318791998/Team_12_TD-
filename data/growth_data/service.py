"""Authorized business queries and atomic commands for the local Data API."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3

from . import models as M
from .finance import check, financials, redact, safe_package, violation_message
from .seed import ATTRIBUTES, world, seed_shared, seed_run
from .simulation import aggregate, business_date, channel_metrics, forecast, trend
from .storage import Store, dumps, fingerprint, insert, many, now, one, timestamps, uid
from .errors import Fault, require
from .media import MediaMixin
from .integration import IntegrationMixin
from .comparisons import ComparisonMixin


@dataclass(frozen=True)
class Principal:
    principal_id: str
    role: str
    session_id: str | None
    allowed_run_ids: tuple = ()
    allowed_shop_ids: tuple = ()
    allowed_job_ids: tuple = ("*",)


WRITERS = {"orchestrator","simulator","monitor","content_worker","learning_worker","evaluator","knowledge_admin","data_admin"}
PRIVATE = {"shop_agent","seller","simulated_seller","orchestrator","simulator","learning_worker","evaluator","data_admin"}


class DataService(IntegrationMixin, ComparisonMixin, MediaMixin):
    @staticmethod
    def brief_preset(run):
        if run['demo_shop_id']!='D' or run['config'].get('driver',{}).get('agent_version')!='native':return None
        return M.BriefConfirm.model_validate(run['config'].get('brief_preset',M.DEMO_D_BRIEF)).model_dump()

    def __init__(self, home, *, content_mode="local", learning_mode="skip",calibration_provider=None,product_image_path=None):
        require(content_mode in {"local","worker"} and learning_mode in {"skip","external"},"CONFIG_INVALID","Profile local không hợp lệ",422)
        self.content_mode=content_mode
        self.learning_mode=learning_mode
        self.calibration_provider=calibration_provider
        self.product_image_path=product_image_path or os.environ.get('DEMO_PRODUCT_IMAGE_PATH') or None
        self.knowledge_callbacks=None
        self.home=Path(home).resolve()
        self.home.mkdir(parents=True,exist_ok=True)
        self.store=Store(self.home/"growth.db")
        self.objects=self.home/"objects"
        with self.store.connect(write=True) as c:
            seed_shared(c,self.objects)

    def bootstrap(self):
        sid=uid("sid")
        with self.store.connect(write=True) as c:
            insert(c,"sessions",session_id=sid,created_at=now())
        return Principal(sid,"seller",sid,(),("D",))

    def issue_token(self, role, *, runs=("*",), shops=("*",), jobs=("*",), session_id=None):
        allowed=WRITERS|{"platform_agent","shop_agent","seller","simulated_seller"}
        require(role in allowed,"ROLE_INVALID","Vai trò không hỗ trợ",422)
        token=secrets.token_urlsafe(32)
        with self.store.connect(write=True) as c:
            insert(c,"principals",token_hash=hashlib.sha256(token.encode()).hexdigest(),principal_id=uid("principal"),
                   role=role,session_id=session_id,allowed_run_ids_json=list(runs),allowed_shop_ids_json=list(shops),allowed_job_ids_json=list(jobs))
        return token

    def authenticate(self, token=None, sid=None):
        with self.store.connect() as c:
            if token:
                row=one(c,"SELECT * FROM principals WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
                if row:
                    return Principal(row["principal_id"],row["role"],row["session_id"],tuple(row["allowed_run_ids"]),tuple(row["allowed_shop_ids"]),tuple(row["allowed_job_ids"]))
            elif sid and one(c,"SELECT * FROM sessions WHERE session_id=?",(sid,)):
                return Principal(sid,"seller",sid,(),("D",))
        raise Fault("UNAUTHENTICATED","Cần phiên đăng nhập hoặc service token",401)

    def run(self,c,p,r):
        run=one(c,"SELECT * FROM runs WHERE run_id=?",(r,))
        grant=one(c,"SELECT run_id FROM run_grants WHERE run_id=? AND principal_id=?",(r,p.principal_id))
        require(run is not None and (p.session_id==run["session_id"] or "*" in p.allowed_run_ids or r in p.allowed_run_ids or grant),"NOT_FOUND","Không tìm thấy đối tượng",404)
        return run

    def scope(self,c,p,r,s=None,roles=None):
        run=self.run(c,p,r)
        if roles:
            require(p.role in roles,"FORBIDDEN","Vai trò không được thực hiện thao tác này",403)
        if s:
            require(s in p.allowed_shop_ids or "*" in p.allowed_shop_ids,"NOT_FOUND","Không tìm thấy đối tượng",404)
            require(one(c,"SELECT * FROM shops WHERE run_id=? AND shop_id=?",(r,s)),"NOT_FOUND","Không tìm thấy shop",404)
        return run

    def entity(self,c,table,r,key,value):
        row=one(c,f"SELECT * FROM {table} WHERE run_id=? AND {key}=?",(r,value))
        require(row is not None,"NOT_FOUND","Không tìm thấy đối tượng",404)
        return row

    def rules(self,c,r,s):
        row=one(c,"SELECT * FROM shop_rules WHERE run_id=? AND shop_id=? ORDER BY rules_version DESC LIMIT 1",(r,s))
        return {"allow_ads":bool(row["allow_ads"]),"ads_daily_max":row["ads_cap_daily_vnd"],"voucher_max_pct":row["voucher_max_pct"],
                "min_profit_per_unit":row["min_profit_per_unit_vnd"],"max_breakeven_roas":row["max_breakeven_roas"],
                "require_stop_condition":bool(row["require_stop_condition"]),"content_style_notes":row["content_style_notes"]},row["rules_version"]

    def product(self,c,r,s):
        row=one(c,"SELECT * FROM products WHERE run_id=? AND shop_id=?",(r,s))
        require(row is not None,"NOT_FOUND","Không tìm thấy sản phẩm",404)
        return row

    def public(self,c,r,s):
        prod=self.product(c,r,s)
        shop=self.entity(c,"shops",r,"shop_id",s)
        inv=self.entity(c,"inventory",r,"product_id",prod["product_id"])
        content=self.entity(c,"content_versions",r,"content_id",prod["active_content_id"])
        active=one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'",(r,s))
        return {"shop_id":s,"name":shop["name"],"category":shop["category"],"price":prod["list_price_vnd"],"stock":inv["available_units"],
                "listing_quality":prod["listing_quality"],"search_rank_page":prod["search_rank_page"],"rating":prod["rating"],
                "base_impressions":prod["base_impressions"],"title":content["title"],"description":content["description"],
                "attributes":[v["text_vi"] for v in prod["facts"]["verified_claims"]],
                "images":[f"/api/v1/runs/{r}/assets/{content['cover_asset_id']}/download"] if content["cover_asset_id"] else [],
                "video":f"/api/v1/runs/{r}/assets/{content['video_asset_id']}/download" if content["video_asset_id"] else None,
                "active_voucher_pct":active["package_snapshot"]["voucher_pct"] if active else 0}

    def evaluation(self,c,r,s,pkg):
        prod=self.product(c,r,s)
        inv=self.entity(c,"inventory",r,"product_id",prod["product_id"])
        cost=self.current_cost(c,r,s)
        rules,rv=self.rules(c,r,s)
        fees,policy=self.fee_config(c,r)
        result=check(pkg,prod["list_price_vnd"],cost["unit_cost_vnd"]+cost["other_unit_cost_vnd"],rules,inv["available_units"],fees)
        return result,dict(rules_version=rv,cost_version=cost["cost_version"],inventory_version=inv["version"],fee_policy_version=policy)

    def check_details(self,c,r,s,result,versions):
        rules,rv=self.rules(c,r,s)
        require(rv==versions['rules_version'],'RULES_CHANGED','Luật đã thay đổi')
        rule_text={
            'VOUCHER_OVER_CAP':f"Voucher tối đa {rules['voucher_max_pct']}%.",
            'ADS_NOT_ALLOWED':'Đối chiếu quyền chạy quảng cáo đã đặt.',
            'ADS_OVER_CAP':f"Ngân sách ngày tối đa {rules['ads_daily_max']:,}đ.".replace(',','.'),
            'PROFIT_BELOW_MIN':'Đối chiếu lãi mỗi đơn với mức tối thiểu đã đặt.',
            'BREAKEVEN_TOO_HIGH':'Đối chiếu ROAS hòa vốn với giới hạn đã đặt.',
        }
        passed_text={
            'VOUCHER_OVER_CAP':'Voucher trong giới hạn shop.',
            'ADS_NOT_ALLOWED':'Quyền chạy quảng cáo phù hợp.',
            'ADS_OVER_CAP':'Ngân sách trong giới hạn shop.',
            'STOCK_TOO_LOW_FOR_ADS':'Tồn kho đáp ứng điều kiện quảng cáo.',
            'PROFIT_BELOW_MIN':'Gói đạt lãi tối thiểu.',
            'LOSS_MAKING':'Gói không gây lỗ theo phép tính.',
            'BREAKEVEN_TOO_HIGH':'ROAS hòa vốn trong giới hạn shop.',
            'STOP_BELOW_BREAKEVEN':'Ngưỡng dừng bảo vệ shop theo hòa vốn.',
        }
        finance_codes={'PROFIT_BELOW_MIN','LOSS_MAKING','BREAKEVEN_TOO_HIGH','STOP_BELOW_BREAKEVEN'}
        run=self.entity(c,'runs',r,'run_id',r)
        policy=one(c,'SELECT * FROM run_policies WHERE run_id=?',(r,))
        guide=one(c,"""SELECT * FROM knowledge_documents WHERE document_id='fee_calculation_guide_demo'
            AND collection_scope='shared' AND index_status='ready' AND knowledge_release=?
            AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY document_version DESC LIMIT 1""",
            (policy['knowledge_release'],business_date(run['current_day']),business_date(run['current_day'])))
        # The demo guide describes this pinned fee policy; it is reference material, not an input to the calculation.
        guide_ref=None
        fees,_=self.fee_config(c,r,version=versions['fee_policy_version'])
        if guide and versions['fee_policy_version']=='demo-fees-v1' and fees=={'rate_bps':1450,'per_order':3000}:
            try:
                path=self.object_path(guide['source_object_key'])
                if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==guide['checksum']:
                    guide_ref={'kind':'reference_document','title_vi':'Tài liệu tham khảo phí giả lập','version':guide['document_version'],
                               'document_id':guide['document_id'],'download_url':f"/api/v1/runs/{r}/knowledge/documents/{guide['document_id']}?version={guide['document_version']}"}
            except (Fault,OSError):pass
        details=[]
        for item in result['checks']:
            code=item['code'];sources=[]
            if code in rule_text:
                sources.append({'kind':'shop_rules','title_vi':'Quy tắc shop','version':versions['rules_version'],'excerpt_vi':rule_text[code]})
            if code in finance_codes:
                sources.extend([{'kind':'product_cost','title_vi':'Giá vốn sản phẩm','version':versions['cost_version']},
                                {'kind':'fee_policy','title_vi':'Chính sách phí áp dụng','version':versions['fee_policy_version']}])
                if guide_ref:sources.append(guide_ref)
            if code=='STOP_BELOW_BREAKEVEN':
                sources.append({'kind':'calculation','title_vi':'Điều kiện dừng theo hòa vốn trong code',
                                'excerpt_vi':'Ngưỡng dừng không thấp hơn ROAS hòa vốn, làm tròn lên bậc 0,5.'})
            if code=='STOCK_TOO_LOW_FOR_ADS':
                sources.extend([{'kind':'inventory','title_vi':'Tồn kho','version':versions['inventory_version']},
                                {'kind':'calculation','title_vi':'Điều kiện tồn kho trong code','excerpt_vi':'Cần ít nhất 30 sản phẩm để chạy quảng cáo.'}])
            details.append({**item,'message_vi':passed_text[code] if item['ok'] else violation_message(code),'sources':sources})
        return details

    def event(self,c,r,day,kind,role,s=None,payload=None,visibility="shared",text="Đã cập nhật trạng thái",eid=""):
        seq=c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?",(r,)).fetchone()[0]
        insert(c,"events",run_id=r,seq=seq,day=day,type=kind,actor_role=role,shop_id=s,entity_type="business",entity_id=eid,
               visibility=visibility,payload_json=payload or {},text_vi=text,recorded_at=now(),simulated_at=business_date(day)+"T09:00:00+07:00")
        return seq

    def command(self,p,scope,path,key,body,fn,method="POST"):
        require(bool(key) and len(key)<=200,"IDEMPOTENCY_KEY_REQUIRED","Cần Idempotency-Key hợp lệ",400)
        digest=fingerprint(body)
        with self.store.connect(write=True) as c:
            if scope.startswith("run_"):
                self.run(c,p,scope)
            record=one(c,"SELECT * FROM idempotency_records WHERE principal_id=? AND run_scope=? AND method=? AND path=? AND key=?",(p.principal_id,scope,method,path,key))
            if record:
                require(record["request_hash"]==digest,"IDEMPOTENCY_CONFLICT","Key đã dùng với nội dung khác")
                return record["response"]
            result=fn(c)
            insert(c,"idempotency_records",principal_id=p.principal_id,run_scope=scope,method=method,path=path,key=key,request_hash=digest,
                   status="completed",operation_id=None,lease_until=None,response_status=200,response_json=result,created_at=now(),updated_at=now())
            return result

    def create_run(self,c,p,body,select=True):
        require(p.role in {"seller","orchestrator","data_admin","evaluator"},"FORBIDDEN","Không được tạo run",403)
        b=M.RunCreate.model_validate(body)
        require(b.scenario_version=="demo-v1","SCENARIO_UNKNOWN","Dataset chưa cài",422)
        require(b.mode!="live" or b.execution_profile=="external","PROVIDER_NOT_CONFIGURED","Live cần external worker; Data API không tự gọi model",503)
        require(set(b.driver_config)<={"agent_version","model","prompt_version","seller_policy","media_wizard"},"CONFIG_INVALID","Driver config chỉ chứa version/model, không chứa credentials",422)
        require(b.driver_config.get('media_wizard') in {None,'staged'},'CONFIG_INVALID','Chế độ media không hợp lệ',422)
        sid=p.session_id or uid("service_session")
        c.execute("INSERT OR IGNORE INTO sessions VALUES (?,?)",(sid,now()))
        rid=uid("run")
        product_source_hash=hashlib.sha256(Path(self.product_image_path).read_bytes()).hexdigest() if self.product_image_path else None
        config={"driver":b.driver_config,"execution_profile":b.execution_profile,"content_mode":b.content_mode or self.content_mode,"learning_mode":b.learning_mode or self.learning_mode,"source":b.data_source,'demo_shop_id':b.demo_shop_id,'product_source_sha256':product_source_hash}
        if b.demo_shop_id=='D' and b.driver_config.get('agent_version')=='native':config['brief_preset']=M.DEMO_D_BRIEF.copy()
        insert(c,"runs",run_id=rid,session_id=sid,scenario_version=b.scenario_version,schema_version=4,simulator_version="market-v2",seed=b.seed,
               mode=b.mode,memory_enabled=b.memory_enabled,history_days=14,simulation_days=b.simulation_days,start_date="2026-11-01",current_day=1,phase="ready",source_run_id=None,
               execution_profile=b.execution_profile,content_mode=config["content_mode"],learning_mode=config["learning_mode"],initial_snapshot_hash=fingerprint(world()),config_json=config,created_by=p.principal_id,demo_shop_id=b.demo_shop_id,**timestamps())
        insert(c,"run_grants",run_id=rid,principal_id=p.principal_id)
        if select:
            c.execute("INSERT INTO active_runs VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET run_id=excluded.run_id",(sid,rid))
        seed_run(c,rid,self.objects,b.seed,self.product_image_path)
        return {"run_id":rid,"day":1,"phase":"ready","mode":b.mode,"simulation_days":b.simulation_days,"version":1}

    def safe_run(self,row):
        return {**{k:row[k] for k in ("run_id","current_day","simulation_days","phase","mode","memory_enabled","version","execution_profile","content_mode","learning_mode")},"data_source":row["config"].get("source","simulation")}

    def context(self,c,p,r,s):
        run=self.scope(c,p,r,s,{"platform_agent","shop_agent","seller","simulated_seller","orchestrator","data_admin"})
        public=self.public(c,r,s)
        runtime=self.entity(c,"shop_runtime",r,"shop_id",s)
        active=one(c,"SELECT campaign_id FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'",(r,s))
        product=self.product(c,r,s)
        result={"run_id":r,"day":run["current_day"],"shop":public,"product_id":product["product_id"],"shop_version":runtime["version"],"active_content_id":product["active_content_id"],
                "eligibility":self.eligibility(c,r,s),
                "policies":self.policies(c,r),"market_summary":self.market_summary(c,r,run),
                "recent_metrics":self.metric_rows(c,p,r,s),"shared_history":self.history(c,p,r,s)}
        if p.role!="platform_agent":
            rules,version=self.rules(c,r,s)
            prod=self.product(c,r,s)
            cost=self.current_cost(c,r,s,run['current_day'])
            inv=self.entity(c,"inventory",r,"product_id",prod["product_id"])
            result.update(private={"owner_name":world()["shops"][s]["private"]["owner_name"],"unit_cost":cost["unit_cost_vnd"],"rules":rules},
                          rules_version=version,cost_version=cost["cost_version"],inventory_version=inv["version"],
                          pending_rule_questions=many(c,"SELECT * FROM rule_questions WHERE run_id=? AND shop_id=? AND status='pending'",(r,s)))
        return result

    def policies(self,c,r=None):
        policy=one(c,"SELECT * FROM run_policies WHERE run_id=?",(r,)) if r else None
        return {"fees":many(c,"SELECT * FROM fee_rules WHERE policy_version=?",(policy["fee_policy_version"] if policy else "demo-fees-v1",)),"platform":many(c,"SELECT * FROM platform_rules WHERE policy_version=?",(policy["platform_policy_version"] if policy else "demo-policy-v1",))}

    def market_summary(self,c,r,run):
        row=one(c,"SELECT * FROM market_daily WHERE run_id=? AND date<=? ORDER BY date DESC LIMIT 1",(r,business_date(run["current_day"])))
        past=one(c,"SELECT * FROM market_daily WHERE run_id=? AND date<=? ORDER BY date DESC LIMIT 1",(r,business_date((date.fromisoformat(row["date"])-date.fromisoformat(business_date(1))).days+1-7)))
        growth=100*(row["search_volume"]/past["search_volume"]-1) if past and past["search_volume"] else None
        return {"keyword":row["keyword"],"growth_7d_pct":round(growth,2) if growth is not None else None,"as_of_date":row["date"],"benchmark_cpc_vnd":row["benchmark_cpc_vnd"]}

    def metric_rows(self,c,p,r,s):
        run=self.scope(c,p,r,s,{"platform_agent"}|PRIVATE)
        rows=many(c,"SELECT * FROM daily_metrics WHERE run_id=? AND shop_id=? AND day<=? ORDER BY date,channel",(r,s,run["current_day"]))
        allowed={"run_id","product_id","date","day","shop_id","channel","impressions","clicks","orders","units","net_revenue_vnd","ad_spend_vnd","realized_roas","source"}
        return [{k:v for k,v in row.items() if p.role!="platform_agent" or k in allowed} for row in rows]

    def shared_proposal(self,c,p,r,row):
        self.scope(c,p,r,row["shop_id"],{"platform_agent"}|PRIVATE)
        fields=("proposal_id","negotiation_id","shop_id","product_id","parent_proposal_id","proposal_version","round","package","shared_reason","stance","status","version","forecast_id")
        result={k:row[k] for k in fields}
        if p.role in PRIVATE:
            result["private_evaluation"]=one(c,"SELECT * FROM proposal_private_evaluations WHERE run_id=? AND proposal_id=? ORDER BY evaluation_version DESC LIMIT 1",(r,row["proposal_id"]))
        return result

    def history(self,c,p,r,s):
        rows=many(c,"SELECT * FROM proposals WHERE run_id=? AND shop_id=? ORDER BY created_at",(r,s))
        return [self.shared_proposal(c,p,r,row) for row in rows]

    def events(self,c,p,r,after=0,limit=50):
        self.run(c,p,r)
        rows=many(c,"SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",(r,after,limit))
        output=[]
        for e in rows:
            s=e["shop_id"]
            if s and s not in p.allowed_shop_ids and "*" not in p.allowed_shop_ids:
                continue
            vis=e["visibility"]
            if vis=="internal" and p.role not in WRITERS: continue
            if vis=="shop_private" and p.role not in PRIVATE: continue
            if vis=="platform_private" and p.role not in {"platform_agent","orchestrator","data_admin"}: continue
            if p.role=="content_worker" and e["type"] not in {"content_job","content_applied"}: continue
            output.append(e)
        cursor=rows[-1]["seq"] if rows else after
        return output,cursor,bool(one(c,"SELECT seq FROM events WHERE run_id=? AND seq>? LIMIT 1",(r,cursor)))

    def new_negotiation(self,c,p,r,s,body):
        run=self.scope(c,p,r,s,{"orchestrator","data_admin"})
        b=M.NegotiationCreate.model_validate(body)
        require(run["phase"] not in {"ready","settling","learning","day_closed","complete"} and not one(c,"SELECT settlement_id FROM day_settlements WHERE run_id=? AND shop_id=? AND day=?",(r,s,b.day)),"DAY_CLOSED","Không thương lượng sau evidence boundary")
        state=self.entity(c,"shop_runtime",r,"shop_id",s)
        require(b.day==run["current_day"] and b.expected_shop_version==state["version"])
        require(b.day>=state["cooldown_until_day"],"COOLDOWN","Shop đang trong thời gian chờ")
        require(not one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'",(r,s)),"ACTIVE_PACKAGE","Shop đang chạy gói")
        require(self.public(c,r,s)["stock"]>=30,"STOCK_LOW","Tồn kho chưa đủ",422)
        count=c.execute("SELECT COUNT(*) FROM negotiations WHERE run_id=? AND shop_id=? AND day=?",(r,s,b.day)).fetchone()[0]
        require(count<3,"MAX_RENEGOTIATIONS","Đã đủ hai lần thương lượng thêm")
        if count:
            require(b.source_card_id is not None,"CARD_REQUIRED","Thương lượng thêm cần quyết định trên thẻ")
            card=self.entity(c,"cards",r,"card_id",b.source_card_id)
            require(card["shop_id"]==s and card["day"]==b.day and card["status"]=="resolved")
        nid=uid("neg")
        insert(c,"negotiations",run_id=r,negotiation_id=nid,shop_id=s,day=b.day,kind=b.kind,attempt=count+1,platform_rounds=0,status="running",final_proposal_id=None,warning_vi=None,owner_note_vi=b.owner_note_vi,expected_next_role="platform_agent",created_at=now(),updated_at=now())
        c.execute("UPDATE shop_runtime SET active_negotiation_id=?,version=version+1,updated_at=? WHERE run_id=? AND shop_id=?",(nid,now(),r,s))
        return self.entity(c,"negotiations",r,"negotiation_id",nid)

    def create_proposal(self,c,p,r,s,body):
        run=self.scope(c,p,r,s,{"platform_agent","shop_agent"})
        b=M.ProposalCreate.model_validate(body)
        if b.native_action is not None:
            require((b.native_action=='counter' and p.role=='shop_agent' and b.stance=='propose') or b.native_action==b.stance,'TURN_ACTION_INVALID','Hành động không khớp vai trò',422)
        require(run["phase"] not in {"ready","settling","learning","day_closed","complete"},"DAY_CLOSED","Không thêm proposal sau evidence boundary")
        neg=self.entity(c,"negotiations",r,"negotiation_id",b.negotiation_id)
        require(neg["shop_id"]==s and neg["status"]=="running" and neg["day"]==run["current_day"])
        require(neg["expected_next_role"]==p.role,"TURN_ORDER","Chưa đến lượt agent này")
        prod=self.product(c,r,s)
        require(prod["product_id"]==b.product_id,"NOT_FOUND","Không tìm thấy sản phẩm",404)
        parent=None
        latest=one(c,"SELECT * FROM proposals WHERE run_id=? AND negotiation_id=? ORDER BY rowid DESC LIMIT 1",(r,b.negotiation_id))
        if latest:
            require(b.parent_proposal_id==latest["proposal_id"],"PARENT_REQUIRED","Phải phản hồi đề xuất mới nhất")
            parent=latest
        else: require(b.parent_proposal_id is None)
        require(b.stance in {"reject","withdraw"} or b.package is not None,"PACKAGE_REQUIRED","Cần gói đề xuất",422)
        pkg=b.package.model_dump() if b.package else None
        if b.stance=="accept": require(parent and parent["package"]==pkg,"PACKAGE_CHANGED","Đổi gói phải là phản đề xuất")
        rounds=neg["platform_rounds"]+(p.role=="platform_agent")
        require(rounds<=3,"MAX_ROUNDS","Đã đủ ba lượt sàn")
        rules,rv=self.rules(c,r,s)
        cost=self.current_cost(c,r,s)["unit_cost_vnd"]
        shared=self.safe_text(c,r,b.shared_reason)
        pid=uid("prop")
        result,versions=self.evaluation(c,r,s,pkg) if pkg else ({"passed":False,"violations":[]}, {})
        insert(c,"proposals",run_id=r,proposal_id=pid,negotiation_id=b.negotiation_id,shop_id=s,product_id=b.product_id,parent_proposal_id=b.parent_proposal_id,
               proposal_version=1,author_role=p.role,round=rounds,package_json=pkg,forecast_id=None,shared_reason=shared,stance=b.stance,
               status="validated" if result["passed"] else "submitted",based_on_rules_version=rv,**timestamps())
        if pkg:
            insert(c,"proposal_private_evaluations",run_id=r,proposal_id=pid,evaluation_version=1,**versions,passed=result["passed"],violations_json=result["violations"],unit_contribution_vnd=result["unit_contribution_vnd"],break_even_roas=result["break_even_roas"],evaluated_at=now())
            if result["passed"]:
                fc=self.forecast_values(c,r,s,pkg,run["current_day"])
                calibration_version=fc.pop("calibration_version")
                fid=uid("forecast")
                insert(c,"forecasts",run_id=r,forecast_id=fid,proposal_id=pid,product_id=b.product_id,as_of_day=run["current_day"],period_start_day=run["current_day"],period_end_day=run["current_day"]+pkg["duration_days"]-1,method_version="forecast-v1",raw_daily_units_json=fc.pop("raw_daily_units"),daily_point_units_json=fc.pop("daily_point_units"),**fc,assumptions_json=["Một đơn một sản phẩm","Không bổ sung kho","calibration:"+calibration_version],input_fingerprint=fingerprint({"package":pkg,"versions":versions,"calibration_version":calibration_version}),created_at=now())
                c.execute("UPDATE proposals SET forecast_id=? WHERE run_id=? AND proposal_id=?",(fid,r,pid))
        accepted=b.stance=="accept" and result["passed"]
        failed=b.stance in {"reject","withdraw"} or (p.role=="shop_agent" and rounds==3 and not accepted)
        status="agreed" if accepted else "failed" if failed else "running"
        if accepted and result["unprofitable"]: status="warning_only"
        if run['execution_profile']=='external': status='running'
        c.execute("UPDATE negotiations SET platform_rounds=?,status=?,final_proposal_id=?,expected_next_role=?,version=version+1,updated_at=? WHERE run_id=? AND negotiation_id=?",(rounds,status,pid if accepted else None,"shop_agent" if p.role=="platform_agent" else "platform_agent",now(),r,b.negotiation_id))
        self.event(c,r,run["current_day"],"platform_turn" if p.role=="platform_agent" else "shop_turn",p.role,s,{"negotiation_id":neg["negotiation_id"],"proposal_id":pid,"parent_proposal_id":b.parent_proposal_id,"turn_id":b.turn_id,"round":rounds,"package":pkg,"stance":b.stance,"action":b.native_action or b.stance,"message_vi":shared},text=shared or "Agent gửi đề xuất",eid=pid)
        if pkg is not None:
            self.event(c,r,run["current_day"],"code_check","orchestrator",s,{"negotiation_id":neg["negotiation_id"],"proposal_id":pid,"round":rounds,"ok":result["passed"],"passed":result["passed"],"checks":self.check_details(c,r,s,result,versions)},visibility="shop_private",text="Code kiểm tra luật shop",eid=pid)
        return self.shared_proposal(c,p,r,self.entity(c,"proposals",r,"proposal_id",pid))

    def finalize_negotiation(self,c,p,r,nid,body):
        neg=self.entity(c,'negotiations',r,'negotiation_id',nid)
        run=self.scope(c,p,r,neg['shop_id'],{'orchestrator'})
        b=M.NegotiationFinalize.model_validate(body)
        require(run['execution_profile']=='external' and run['current_day']==neg['day'], 'DAY_CLOSED', 'Thương lượng không còn thuộc ngày hiện tại')
        require(neg['status']=='running' and neg['version']==b.expected_version, 'NEGOTIATION_TERMINAL', 'Thương lượng đã kết thúc hoặc version đã đổi')
        require(neg['platform_rounds']==b.rounds, 'ROUND_MISMATCH', 'Sai số lượt thương lượng')
        if b.status=='agreed':
            require(b.referee_action=='continue' and b.final_proposal_id==neg['final_proposal_id'] and b.final_proposal_id is not None, 'REFEREE_REQUIRED', 'Cần Referee xác nhận gói đã chấp nhận')
            prop=self.entity(c,'proposals',r,'proposal_id',b.final_proposal_id)
            require(prop['negotiation_id']==nid and prop['stance']=='accept' and prop['status']=='validated' and self.evaluation(c,r,neg['shop_id'],prop['package'])[0]['passed'], 'CHECK_FAILED', 'Gói cuối chưa hợp lệ')
            if run['config'].get('driver',{}).get('agent_version')=='native':
                turn=one(c,"SELECT seq FROM events WHERE run_id=? AND entity_id=? AND type IN ('platform_turn','shop_turn')",(r,b.final_proposal_id))
                review=one(c,"SELECT * FROM events WHERE run_id=? AND entity_id=? AND type='referee_review' ORDER BY seq DESC LIMIT 1",(r,nid))
                require(turn and review and review['seq']>turn['seq'] and review['payload'].get('action')=='continue','REFEREE_REQUIRED','Thiếu verdict sau lượt chấp nhận')
                refs=review['payload'].get('evidence_refs',[])
                require(bool(refs) and all(one(c,"SELECT seq FROM events WHERE run_id=? AND seq=? AND json_extract(payload_json,'$.negotiation_id')=? AND type IN ('platform_turn','shop_turn')",(r,seq,nid)) for seq in refs),'EVIDENCE_INVALID','Bằng chứng Referee sai lượt')
        else:
            require(b.final_proposal_id is None, 'FINAL_PROPOSAL_INVALID', 'Thương lượng thất bại không có gói cuối')
        receipt=b.model_dump()
        c.execute("UPDATE negotiations SET status=?,final_proposal_id=?,terminal_receipt_json=?,terminal_hash=?,version=version+1,updated_at=? WHERE run_id=? AND negotiation_id=?",(b.status,b.final_proposal_id,dumps(receipt),fingerprint(receipt),now(),r,nid))
        source=self.negotiation_operation(c,r,neg)
        self.event(c,r,neg['day'],'negotiation_finished','orchestrator',neg['shop_id'],{'negotiation_id':nid,'source_card_id':source['result'].get('source_card_id') if source and source['result'] else None,'kind':neg['kind'],'status':b.status,'proposal_id':b.final_proposal_id,'package':prop['package'] if b.status=='agreed' else None,'rounds':b.rounds,'reason_vi':self.safe_text(c,r,b.reason_vi),'referee_action':b.referee_action},text='Thương lượng đã kết thúc')
        return self.entity(c,'negotiations',r,'negotiation_id',nid)

    def persist_copy(self,c,table,row,**changes):
        row={**row,**changes}
        columns=[x[1] for x in c.execute(f"PRAGMA table_info({table})")]
        insert(c,table,**{col:row.get(col[:-5] if col.endswith("_json") else col) for col in columns})

    def present(self,c,p,r,pid,version):
        prop=self.entity(c,"proposals",r,"proposal_id",pid)
        run=self.scope(c,p,r,prop["shop_id"],{"orchestrator","data_admin"})
        require(prop["version"]==version and prop["status"]=="validated")
        neg=self.entity(c,"negotiations",r,"negotiation_id",prop["negotiation_id"])
        require(neg["status"] in {"agreed","warning_only"} and neg["final_proposal_id"]==pid)
        ev,_=self.evaluation(c,r,prop["shop_id"],prop["package"])
        require(ev["passed"],"CHECK_FAILED","Gói chưa qua luật shop",422)
        q=one(c,"SELECT * FROM rule_questions WHERE run_id=? AND shop_id=? AND status='pending' ORDER BY created_at LIMIT 1",(r,prop["shop_id"]))
        card=self.make_card(c,r,prop["shop_id"],run["current_day"],prop,q)
        c.execute("UPDATE proposals SET status='awaiting_seller',version=version+1,updated_at=? WHERE run_id=? AND proposal_id=?",(now(),r,pid))
        if prop["shop_id"]==run['demo_shop_id']: c.execute("UPDATE runs SET phase='awaiting_seller' WHERE run_id=?",(r,))
        return card

    def make_card(self,c,r,s,day,prop=None,question=None):
        card_id=uid("card")
        insert(c,"cards",run_id=r,card_id=card_id,shop_id=s,day=day,kind="offer" if prop else "question",proposal_id=prop["proposal_id"] if prop else None,
               question_id=question["question_id"] if question else None,forecast_id=prop["forecast_id"] if prop else None,
               reasons_json=["Trend quạt mini tăng; người bán là người quyết định"],warnings_json=[],notices_json=["Dữ liệu giả lập"],status="pending",**timestamps())
        c.execute("UPDATE shop_runtime SET pending_card_id=?,version=version+1 WHERE run_id=? AND shop_id=?",(card_id,r,s))
        run=self.entity(c,'runs',r,'run_id',r)
        if question and run['config'].get('driver',{}).get('agent_version')=='native':
            require(self.knowledge_callbacks is not None,'KNOWLEDGE_UNAVAILABLE','Chưa có repository sở thích',503)
            self.knowledge_callbacks.mark_preference_asked_tx(c,run_id=r,shop_id=s,pref_id=question['external_pref_id'],question_id=question['question_id'],card_id=card_id,day=day)
        card=self.entity(c,"cards",r,"card_id",card_id)
        from .facade import Facade
        self.event(c,r,day,"card_sent","orchestrator",s,{"card_id":card_id,"proposal_id":prop['proposal_id'] if prop else None,"negotiation_id":prop['negotiation_id'] if prop else None,"brief_version":run['brief_version'],"card":Facade(self).card(c,r,card)},visibility='shop_private',text="Đã gửi thẻ cho người bán")
        return card

    def decision(self,c,p,r,body):
        b=M.DecisionCreate.model_validate(body)
        table,key={"proposal":("proposals","proposal_id"),"content":("content_versions","content_id"),"rule_question":("rule_questions","question_id")}[b.target_type]
        target=self.entity(c,table,r,key,b.target_id)
        s=target.get("shop_id") or self.entity(c,"products",r,"product_id",target["product_id"])["shop_id"]
        run=self.scope(c,p,r,s,{"seller","simulated_seller"})
        if p.role=="seller" and run["execution_profile"]=="external":
            require(not one(c,"SELECT operation_id FROM operations WHERE run_id=? AND status IN ('queued','running') AND (kind='start_day' OR kind LIKE 'renegotiate:%')",(r,)),"BUSY","Đang chờ orchestrator hoàn tất tác vụ")
        require(b.target_version==target.get("version",1))
        require(not one(c,"SELECT * FROM decisions WHERE run_id=? AND target_type=? AND target_id=? AND target_version=?",(r,b.target_type,b.target_id,b.target_version)),"ALREADY_DECIDED","Đối tượng đã được quyết định")
        card=one(c,'SELECT * FROM cards WHERE run_id=? AND '+('proposal_id' if b.target_type=='proposal' else 'question_id')+'=? ORDER BY rowid DESC LIMIT 1',(r,b.target_id)) if b.target_type in {'proposal','rule_question'} else None
        negotiation_id=target.get('negotiation_id') if b.target_type=='proposal' else None
        if b.target_type=="proposal":
            require(target["status"]=="awaiting_seller")
        elif b.target_type=="content":
            require(target["status"]=="validated" or (target["status"]=="superseded" and target["published_day"] is not None))
            require(b.action!="approve" or b.cover_option in {"A","B","C"})
            require(b.edited_package is None and b.rule_answer is None)
        else:
            require(target["status"]=="pending" and b.action in {"approve","reject"} and b.rule_answer==(b.action=="approve"))
            require(b.edited_package is None and b.cover_option is None)
        if b.edited_package:
            require(b.target_type=="proposal" and b.action=="approve")
            ev,_=self.evaluation(c,r,s,b.edited_package)
            require(ev["passed"],"CHECK_FAILED","Gói chỉnh sửa chưa hợp lệ",422)
            child=uid("prop")
            self.persist_copy(c,"proposals",target,proposal_id=child,parent_proposal_id=target["proposal_id"],package=b.edited_package.model_dump(),status="awaiting_seller",version=1,created_at=now(),updated_at=now(),forecast_id=None,author_role=p.role)
            target=self.entity(c,"proposals",r,"proposal_id",child)
            self.snapshot_forecast(c,r,s,target,run["current_day"])
            target=self.entity(c,"proposals",r,"proposal_id",child)
        did=uid("decision")
        rules,_=self.rules(c,r,s)
        prod=self.product(c,r,s)
        shared=self.safe_text(c,r,b.feedback_shared or "")
        insert(c,"decisions",run_id=r,decision_id=did,shop_id=s,target_type=b.target_type,target_id=target[key],target_version=target.get("version",1),action=b.action,
               edited_package_json=b.edited_package.model_dump() if b.edited_package else None,cover_option=b.cover_option,rule_answer=b.rule_answer,
               actor_type=p.role,actor_id=p.principal_id,feedback_private=b.feedback_private,feedback_shared=shared,created_at=now())
        if b.target_type=="rule_question":
            _,rv=self.rules(c,r,s)
            require(rv==target["based_on_rules_version"])
            c.execute("UPDATE rule_questions SET status='answered',answer=?,decision_id=? WHERE run_id=? AND question_id=?",(b.rule_answer,did,r,target["question_id"]))
            if b.rule_answer: self.confirm_rule(c,r,s,target,did,p.principal_id)
            if run['config'].get('driver',{}).get('agent_version')=='native':
                require(self.knowledge_callbacks is not None,'KNOWLEDGE_UNAVAILABLE','Chưa có repository sở thích',503)
                self.knowledge_callbacks.record_preference_answer_tx(c,run_id=r,shop_id=s,pref_id=target['external_pref_id'],question_id=target['question_id'],decision_id=did,yes=b.rule_answer,day=run['current_day'])
        elif b.target_type=="content" and b.action!="approve":
            c.execute("UPDATE content_versions SET status='rejected',version=version+1 WHERE run_id=? AND content_id=?",(r,target[key]))
            c.execute("UPDATE proposals SET status='rejected',version=version+1 WHERE run_id=? AND proposal_id IN (SELECT proposal_id FROM content_jobs WHERE run_id=? AND product_id=?) AND status='accepted'",(r,r,target["product_id"]))
            if s==run['demo_shop_id']:c.execute("UPDATE runs SET phase='negotiating',version=version+1 WHERE run_id=?",(r,))
        elif b.target_type=="proposal":
            c.execute("UPDATE proposals SET status=?,version=version+1,updated_at=? WHERE run_id=? AND proposal_id=?",("accepted" if b.action=="approve" else "rejected",now(),r,target[key]))
            c.execute("UPDATE cards SET status='resolved',version=version+1 WHERE run_id=? AND proposal_id=? AND status='pending'",(r,b.target_id))
            if b.action=="reject":
                c.execute("UPDATE shop_runtime SET cooldown_until_day=? WHERE run_id=? AND shop_id=?",(run["current_day"]+3,r,s))
            if b.edited_package:
                c.execute("UPDATE proposals SET status='superseded' WHERE run_id=? AND proposal_id=?",(r,b.target_id))
            if s==run['demo_shop_id']:
                c.execute("UPDATE runs SET phase=?,version=version+1 WHERE run_id=?",("content_review" if b.action=="approve" and target["package"]["content_refresh"] else "negotiating",r))
        if b.target_type=="rule_question":
            c.execute("UPDATE cards SET status='resolved' WHERE run_id=? AND question_id=? AND kind='question'",(r,target[key]))
        action='edit' if b.edited_package else {'approve':'accept','reject':'reject','request_changes':'negotiate'}[b.action]
        self.event(c,r,run["current_day"],"seller_decision",p.role,s,{"decision_id":did,"card_id":card['card_id'] if card else None,"negotiation_id":negotiation_id,"target_type":b.target_type,"target_id":target[key],"action":action,"rule_answer":b.rule_answer,"edited_package":b.edited_package.model_dump() if b.edited_package else None,"feedback_shared":shared,"note_vi":shared},text="Người bán đã đưa ra quyết định")
        return self.entity(c,"decisions",r,"decision_id",did)

    def snapshot_forecast(self,c,r,s,proposal,day):
        result,versions=self.evaluation(c,r,s,proposal["package"])
        require(result["passed"],"CHECK_FAILED","Không thể dự báo gói vi phạm luật",422)
        f=self.forecast_values(c,r,s,proposal["package"],day)
        calibration_version=f.pop("calibration_version")
        fid=uid("forecast")
        insert(c,"forecasts",run_id=r,forecast_id=fid,proposal_id=proposal["proposal_id"],product_id=proposal["product_id"],as_of_day=day,period_start_day=day,period_end_day=day+proposal["package"]["duration_days"]-1,method_version="forecast-v1",raw_daily_units_json=f.pop("raw_daily_units"),daily_point_units_json=f.pop("daily_point_units"),**f,assumptions_json=["Một đơn một sản phẩm","Không bổ sung kho","calibration:"+calibration_version],input_fingerprint=fingerprint({"package":proposal["package"],"versions":versions,"calibration_version":calibration_version}),created_at=now())
        c.execute("UPDATE proposals SET forecast_id=? WHERE run_id=? AND proposal_id=?",(fid,r,proposal["proposal_id"]))

    def forecast_values(self,c,r,s,package,day):
        """Read-only in-process adapter: memory owns the calibration, not this DB."""
        run=self.entity(c,"runs",r,"run_id",r)
        public=self.public(c,r,s)
        calibration=None
        if self.calibration_provider is not None and run["memory_enabled"]:
            value=self.calibration_provider(r,s,day)
            if value is not None:
                view=M.CalibrationView.model_validate(value)
                require(view.as_of_day<day,"FUTURE_UNAVAILABLE","Hiệu chỉnh chứa thông tin tương lai",422)
                if view.points>=5 and view.as_of_day>=1:calibration=view
        f=forecast(public,package,day,factor=calibration.factor if calibration else 1.0)
        if calibration:
            raw=sum(f["raw_daily_units"])
            f["low"]=min(f["point"],round(raw*calibration.q_low))
            f["high"]=min(public["stock"],max(f["point"],round(raw*calibration.q_high)))
        f["calibration_version"]=calibration.version if calibration else "prior-v1"
        return f

    def confirm_rule(self,c,r,s,q,did,actor):
        rules,rv=self.rules(c,r,s)
        require(rv==q["based_on_rules_version"])
        old=one(c,"SELECT * FROM shop_rules WHERE run_id=? AND shop_id=? AND rules_version=?",(r,s,rv))
        if q['field']=='voucher_max_pct': require(int(q['value'])<=rules['voucher_max_pct'],'RULE_INCREASE','Chỉ được giảm giới hạn voucher',422)
        updates={"voucher_max_pct":int(q["value"])} if q["field"]=="voucher_max_pct" else {"content_style_notes":list(dict.fromkeys(rules["content_style_notes"]+[str(q["value"])]))}
        self.persist_copy(c,"shop_rules",old,**updates,rules_version=rv+1,effective_day=self.entity(c,"runs",r,"run_id",r)["current_day"],confirmed_by=actor,confirmed_at=now(),confirmation_decision_id=did)
        return rv+1

    def question(self,c,p,r,s,body):
        run=self.scope(c,p,r,s,{"learning_worker","orchestrator"})
        require(bool(run["memory_enabled"]),"MEMORY_OFF","Run đã tắt học sở thích",403)
        b=M.RuleQuestionCreate.model_validate(body)
        rules,rv=self.rules(c,r,s)
        require(rv==b.based_on_rules_version)
        if b.field=='voucher_max_pct': require(int(b.value)<=rules['voucher_max_pct'],'RULE_INCREASE','Chỉ được giảm giới hạn voucher',422)
        old=one(c,"SELECT * FROM rule_questions WHERE run_id=? AND shop_id=? AND field=? AND value_json=? ORDER BY created_at DESC LIMIT 1",(r,s,b.field,dumps(b.value)))
        if old:
            if run['config'].get('driver',{}).get('agent_version')=='native': require(old['external_pref_id']==b.external_pref_id,'PREFERENCE_CONFLICT','Sở thích không khớp câu hỏi đã có')
            if old["status"]=="pending": return old
            # A run is at most seven days, so a declined preference's fourteen-day
            # silence cannot expire inside it; repeated confirmed questions are no-ops.
            require(old["answer"],"PREF_SILENCE","Chưa hết thời gian im lặng")
            return old
        if run['config'].get('driver',{}).get('agent_version')=='native':
            require(self.knowledge_callbacks is not None,'KNOWLEDGE_UNAVAILABLE','Chưa có repository sở thích',503)
            self.knowledge_callbacks.validate_preference_tx(c,run_id=r,shop_id=s,pref_id=b.external_pref_id,field=b.field,value=b.value,day=run['current_day'])
        qid=uid("question")
        insert(c,"rule_questions",run_id=r,question_id=qid,shop_id=s,external_pref_id=b.external_pref_id,field=b.field,value_json=b.value,text_vi=b.text_vi,based_on_rules_version=rv,status="pending",answer=None,decision_id=None,created_at=now())
        return self.entity(c,"rule_questions",r,"question_id",qid)

    def apply(self,c,p,r,body):
        b=M.CampaignApply.model_validate(body)
        prop=self.entity(c,"proposals",r,"proposal_id",b.proposal_id)
        run=self.scope(c,p,r,prop["shop_id"],{"orchestrator","data_admin"})
        previous=one(c,"SELECT * FROM campaigns WHERE run_id=? AND proposal_id=?",(r,b.proposal_id))
        if previous:
            require(previous["approval_decision_id"]==b.approval_decision_id)
            return previous
        decision=self.entity(c,"decisions",r,"decision_id",b.approval_decision_id)
        require(decision["target_type"]=="proposal" and decision["target_id"]==b.proposal_id and decision["action"]=="approve" and prop["status"]=="accepted","APPROVAL_REQUIRED","Cần duyệt đúng đề xuất")
        if prop["package"]["content_refresh"]:
            published=one(c,"SELECT cv.content_id FROM content_jobs j JOIN content_versions cv ON cv.run_id=j.run_id AND cv.content_id IN (SELECT value FROM json_each(j.output_content_ids_json)) WHERE j.run_id=? AND j.proposal_id=? AND cv.status='published'",(r,b.proposal_id))
            require(published,"CONTENT_APPROVAL_REQUIRED","Phải duyệt và áp dụng nội dung trước khi kích hoạt gói")
        ev,versions=self.evaluation(c,r,prop["shop_id"],prop["package"])
        require(ev["passed"],"CHECK_FAILED","Gói vi phạm luật hiện hành",422)
        require(versions["rules_version"]==b.expected_rules_version and versions["inventory_version"]==b.expected_inventory_version)
        require(not one(c,"SELECT * FROM campaigns WHERE run_id=? AND product_id=? AND status='active'",(r,prop["product_id"])),"ACTIVE_PACKAGE","Sản phẩm đang chạy gói")
        require(not one(c,"SELECT * FROM day_settlements WHERE run_id=? AND shop_id=? AND day=?",(r,prop["shop_id"],run["current_day"])),"DAY_SETTLED","Ngày đã chốt")
        cid=uid("campaign");pkg=prop["package"]
        insert(c,"campaigns",run_id=r,campaign_id=cid,shop_id=prop["shop_id"],product_id=prop["product_id"],proposal_id=b.proposal_id,approval_decision_id=b.approval_decision_id,
               package_snapshot_json=pkg,start_day=run["current_day"],end_day=run["current_day"]+pkg["duration_days"]-1,approved_total_vnd=pkg["ads_daily_budget"]*pkg["duration_days"],spent_vnd=0,low_roas_streak=0,status="active",ads_status="running" if pkg["ads_daily_budget"] else "disabled",ads_stop_reason=None,**timestamps())
        c.execute("UPDATE proposals SET status='applied',version=version+1 WHERE run_id=? AND proposal_id=?",(r,b.proposal_id))
        applied=self.entity(c,"proposals",r,"proposal_id",b.proposal_id)
        self.snapshot_forecast(c,r,prop["shop_id"],applied,run["current_day"])
        self.event(c,r,run["current_day"],"auto_action","orchestrator",prop["shop_id"],{"campaign_id":cid,"action":"apply_package"},text="Áp dụng đúng gói người bán đã duyệt")
        card=one(c,'SELECT card_id FROM cards WHERE run_id=? AND proposal_id IN (?,?) ORDER BY rowid DESC LIMIT 1',(r,prop['proposal_id'],prop['parent_proposal_id']))
        self.event(c,r,run["current_day"],"package_applied","orchestrator",prop["shop_id"],{"campaign_id":cid,"card_id":card['card_id'] if card else None,"proposal_id":b.proposal_id,"decision_id":b.approval_decision_id,"negotiation_id":prop["negotiation_id"],"package":pkg},text="Gói đã được kích hoạt sau approval")
        if prop["shop_id"]==run['demo_shop_id']:c.execute("UPDATE runs SET phase='negotiating',version=version+1 WHERE run_id=?",(r,))
        return self.entity(c,"campaigns",r,"campaign_id",cid)

    def settle(self,c,p,r,s,body):
        run=self.scope(c,p,r,s,{"simulator","orchestrator","data_admin"})
        b=M.Settle.model_validate(body)
        old=one(c,"SELECT * FROM day_settlements WHERE run_id=? AND shop_id=? AND day=?",(r,s,b.day))
        if old:
            require(b.input_snapshot_hash is None or old["input_snapshot_hash"]==b.input_snapshot_hash,"INPUT_CONFLICT","Snapshot khác lần chốt trước")
            return old
        require(b.day==run["current_day"] and run["phase"] not in {"ready","complete"},"DAY_NOT_STARTED","Chưa bắt đầu ngày")
        native=run['config'].get('driver',{}).get('agent_version')=='native'
        require(not one(c,"SELECT operation_id FROM operations WHERE run_id=? AND day=? AND (kind='start_day' OR kind LIKE 'renegotiate:%') AND status!='succeeded' AND (status!='failed' OR ?=0)",(r,b.day,native)),"OPERATION_PENDING","Tác vụ agent chưa hoàn tất")
        require(not one(c,"SELECT negotiation_id FROM negotiations WHERE run_id=? AND day=? AND status='running'",(r,b.day)),"NEGOTIATION_PENDING","Thương lượng chưa hoàn tất")
        require(not self.pending_offer_restoration(c,r,b.day,s),'OFFER_REVIEW_REQUIRED','Cần xem lại hoặc xử lý đề xuất gốc trước khi kết thúc ngày')
        require(not one(c,"SELECT j.job_id FROM content_jobs j, json_each(j.provider_state_json) slot WHERE j.run_id=? AND j.shop_id=? AND json_extract(slot.value,'$.status') IN ('reserved','running','unknown','outcome_unknown')",(r,s)),"PROVIDER_OUTCOME_UNKNOWN","Còn kết quả media chưa rõ")
        require(not one(c,"SELECT * FROM cards WHERE run_id=? AND shop_id=? AND status='pending'",(r,s)),"PENDING_CARD","Cần người bán xử lý thẻ")
        require(not one(c,"SELECT proposal_id FROM proposals WHERE run_id=? AND shop_id=? AND status='accepted'",(r,s)),"PENDING_APPLY","Gói đã duyệt còn chờ nội dung/kích hoạt")
        require(not one(c,"SELECT cv.content_id FROM content_versions cv JOIN products p ON p.run_id=cv.run_id AND p.product_id=cv.product_id WHERE cv.run_id=? AND p.shop_id=? AND cv.status IN ('draft','validated')",(r,s)),"PENDING_CONTENT","Nội dung chưa được duyệt hoặc từ chối")
        prod=self.product(c,r,s);inv=self.entity(c,"inventory",r,"product_id",prod["product_id"])
        require(inv["version"]==b.expected_inventory_version)
        content=self.entity(c,"content_versions",r,"content_id",prod["active_content_id"])
        campaign=one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'",(r,s))
        rules,rv=self.rules(c,r,s)
        digest=fingerprint({"seed":run["seed"],"day":b.day,"inventory":inv,"campaign":campaign,"content_id":content["content_id"],"rules_version":rv,"simulator":run['simulator_version']})
        require(b.input_snapshot_hash is None or b.input_snapshot_hash==digest,"INPUT_CONFLICT","Snapshot không khớp trạng thái")
        budget,voucher=0,0
        if campaign:
            pkg=campaign["package_snapshot"];voucher=pkg["voucher_pct"]
            if campaign["ads_status"]=="running":
                low=inv["available_units"]<30
                past=many(c,"SELECT day,SUM(orders) n FROM daily_metrics WHERE run_id=? AND shop_id=? AND day>0 AND day<? GROUP BY day ORDER BY day DESC LIMIT 3",(r,s,b.day))
                low=low or (bool(past) and inv["available_units"]<3*sum(v["n"] for v in past)/len(past))
                valid=self.evaluation(c,r,s,pkg)[0]["passed"]
                if low or not valid:
                    c.execute("UPDATE campaigns SET ads_status='paused',ads_stop_reason=?,version=version+1 WHERE run_id=? AND campaign_id=?",("LOW_STOCK" if low else "RULE_TIGHTENED",r,campaign["campaign_id"]))
                    self.event(c,r,b.day,"auto_action","monitor",s,{"action":"pause_ads","campaign_id":campaign['campaign_id'],"effective_day":b.day},text="Điều kiện tồn kho hoặc luật yêu cầu dừng ads")
                else: budget=min(pkg["ads_daily_budget"],campaign["approved_total_vnd"]-campaign["spent_vnd"])
        q=min(.95,prod["listing_quality"]+(content["quality_gain"] if content["published_day"] is not None and b.day>content["published_day"] else 0))
        effective={'content_refresh':False,'ads_daily_budget':budget,'voucher_pct':voucher,'duration_days':1}
        public=self.public(c,r,s);public['listing_quality']=q
        calibration=None
        if self.calibration_provider is not None and run['memory_enabled']:
            value=self.calibration_provider(r,s,b.day)
            if value is not None:
                view=M.CalibrationView.model_validate(value)
                require(view.as_of_day<b.day,'FUTURE_UNAVAILABLE','Hiệu chỉnh chứa thông tin tương lai',422)
                if view.points>=5 and view.as_of_day>=1:calibration=view
        prediction=forecast(public,effective,b.day,factor=calibration.factor if calibration else 1.0)
        pid=uid('prediction')
        payload={'prediction_id':pid,'day':b.day,'shop_id':s,'effective_package':effective,'effective_state_hash':fingerprint({'quality':q,'stock':inv['available_units'],'package':effective}),'raw_point':prediction['raw_daily_units'][0],'issued_point':prediction['daily_point_units'][0],'factor':prediction['factor_used'],'calibration_version':calibration.version if calibration else 'prior-v1','source':'simulation'}
        insert(c,'daily_predictions',run_id=r,shop_id=s,day=b.day,prediction_id=pid,payload_json=payload,payload_hash=fingerprint(payload),created_at=now())
        cost_record=self.current_cost(c,r,s,b.day)
        cost=cost_record["unit_cost_vnd"]+cost_record["other_unit_cost_vnd"]
        fees,fee_version=self.fee_config(c,r)
        rows=channel_metrics(self.public(c,r,s),cost,seed=run["seed"],day=b.day,stock=inv["available_units"],quality=q,voucher=voucher,budget=budget,fees=fees)
        settlement=uid("settlement")
        insert(c,"day_settlements",run_id=r,settlement_id=settlement,shop_id=s,day=b.day,input_snapshot_hash=digest,status="committed",created_at=now())
        for row in rows:
            insert(c,"daily_metrics",run_id=r,product_id=prod["product_id"],date=business_date(b.day),day=b.day,shop_id=s,
                   campaign_id=campaign["campaign_id"] if campaign and row["channel"]=="paid" else None,content_id=content["content_id"],
                   fee_policy_version=fee_version,cost_version=cost_record["cost_version"],settlement_id=settlement,source="simulated",created_at=now(),**row)
        total=aggregate(rows,s,b.day)
        c.execute("UPDATE inventory SET available_units=available_units-?,version=version+1,updated_at=? WHERE run_id=? AND product_id=?",(total["orders"],now(),r,prod["product_id"]))
        if campaign:
            paid=rows[1];streak=campaign["low_roas_streak"]
            if paid["ad_spend_vnd"]: streak=streak+1 if paid["realized_roas"]<campaign["package_snapshot"]["stop_roas_below"] else 0
            paused=streak>=campaign["package_snapshot"]["stop_after_days"]
            finished=b.day>=campaign["end_day"]
            c.execute("UPDATE campaigns SET spent_vnd=spent_vnd+?,low_roas_streak=?,ads_status=CASE WHEN ? THEN 'ended' WHEN ? THEN 'paused' ELSE ads_status END,status=CASE WHEN ? THEN 'completed' ELSE status END,ads_stop_reason=CASE WHEN ? THEN 'LOW_ROAS' ELSE ads_stop_reason END,version=version+1 WHERE run_id=? AND campaign_id=?",(paid["ad_spend_vnd"],streak,finished,paused,finished,paused,r,campaign["campaign_id"]))
            if paused and campaign["ads_status"]=="running": self.event(c,r,b.day,"auto_action","monitor",s,{"action":"pause_ads","campaign_id":campaign['campaign_id'],"effective_day":b.day+1},text="ROAS thấp đủ số ngày, dừng trước chi ngày tiếp")
        # Financial result is private; the separate platform event excludes contribution/fees.
        self.event(c,r,b.day,"market_result","simulator",s,{"metrics":total,"settlement_id":settlement,"prediction_id":pid,"campaign_id":campaign['campaign_id'] if campaign else None},visibility="shop_private",text="Đã chốt kết quả thị trường")
        safe={k:v for k,v in total.items() if k not in {"profit_after_fees","fees"}}
        self.event(c,r,b.day,"market_result","simulator",s,{"metrics":safe,"settlement_id":settlement,"prediction_id":pid,"campaign_id":campaign['campaign_id'] if campaign else None},visibility="platform_private",text="Kết quả traffic và doanh thu công khai")
        return self.entity(c,"day_settlements",r,"settlement_id",settlement)

    def operation(self,c,p,r,kind,body):
        run=self.scope(c,p,r,roles={"seller","orchestrator","data_admin"})
        if kind=='start_day' and run['config'].get('driver',{}).get('agent_version')=='native':
            require(run['brief'] and run['brief'].get('confirmed'),'BRIEF_REQUIRED','Cần xác nhận mục tiêu trước khi bắt đầu')
        b=M.DayCommand.model_validate(body)
        previous=one(c,"SELECT * FROM operations WHERE run_id=? AND day=? AND kind=?",(r,b.expected_day,kind))
        if previous and previous["status"]=="succeeded": return previous
        require(run["current_day"]==b.expected_day and run["version"]==b.expected_version)
        opid=uid("operation")
        insert(c,"operations",run_id=r,operation_id=opid,day=b.expected_day,kind=kind,status="running",result_json=None,error_code=None,lease_until=now(),**timestamps())
        internal=Principal("local_driver","orchestrator",run["session_id"],(r,),("*",))
        if kind=="start_day":
            require(run["phase"]=="ready")
            c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
            insert(c,"market_daily",run_id=r,date=business_date(b.expected_day),keyword="quạt mini cầm tay",search_volume=round(34000*trend(b.expected_day)),qualified_listing_count=5,benchmark_cpc_vnd=1800,benchmark_ctr_bps=250,benchmark_cvr_bps=500,observed_at=business_date(b.expected_day)+"T00:00:00+07:00")
            driver='native' if run['config'].get('driver',{}).get('agent_version')=='native' else 'external' if run['execution_profile']=='external' else 'offline_reference'
            self.event(c,r,b.expected_day,"day_start","orchestrator",payload={"day":b.expected_day,"driver":driver},text="Bắt đầu ngày")
            if run["execution_profile"]=="external":
                c.execute("UPDATE operations SET status='queued',lease_until=NULL WHERE run_id=? AND operation_id=?",(r,opid))
                c.execute("UPDATE runs SET version=version+1,updated_at=? WHERE run_id=?",(now(),r))
                return self.entity(c,"operations",r,"operation_id",opid)
            selected=[sid for sid in "ABCDE" if self.eligibility(c,r,sid)["eligible"]]
            self.event(c,r,b.expected_day,"opportunity","orchestrator",payload={"keyword":"quạt mini cầm tay","growth_7d_pct":self.market_summary(c,r,run)["growth_7d_pct"],"chosen":selected,"excluded":[{"shop_id":sid,"reason_codes":self.eligibility(c,r,sid)["reason_codes"]} for sid in "ABCDE" if sid not in selected]},text="Code đối chiếu trend, tồn kho, listing và trạng thái gói")
            for sid in "ABCDE":
                active=one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'",(r,sid))
                q=one(c,"SELECT * FROM rule_questions WHERE run_id=? AND shop_id=? AND status='pending' ORDER BY created_at LIMIT 1",(r,sid))
                if active:
                    if q:
                        self.make_card(c,r,sid,b.expected_day,question=q)
                        if sid!="D": self.auto_card(c,r,sid)
                    continue
                if not self.eligibility(c,r,sid)["eligible"]: continue
                state=self.entity(c,"shop_runtime",r,"shop_id",sid)
                if b.expected_day<state["cooldown_until_day"]: continue
                self.reference_offer(c,internal,r,sid)
                if sid!="D": self.auto_card(c,r,sid)
            card=one(c,"SELECT * FROM cards WHERE run_id=? AND shop_id='D' AND status='pending'",(r,))
            c.execute("UPDATE runs SET phase=? WHERE run_id=?",("awaiting_seller" if card else "negotiating",r))
        elif kind=="close_day":
            require(run["phase"] not in {"ready","complete"})
            native=run['config'].get('driver',{}).get('agent_version')=='native'
            require(not one(c,"SELECT operation_id FROM operations WHERE run_id=? AND day=? AND (kind='start_day' OR kind LIKE 'renegotiate:%') AND status!='succeeded' AND (status!='failed' OR ?=0)",(r,b.expected_day,native)),"OPERATION_PENDING","Tác vụ agent chưa hoàn tất")
            require(not one(c,"SELECT negotiation_id FROM negotiations WHERE run_id=? AND day=? AND status='running'",(r,b.expected_day)),"NEGOTIATION_PENDING","Thương lượng chưa hoàn tất")
            require(not self.pending_offer_restoration(c,r,b.expected_day,run['demo_shop_id']),'OFFER_REVIEW_REQUIRED','Cần xem lại hoặc xử lý đề xuất gốc trước khi kết thúc ngày')
            require(not one(c,"SELECT j.job_id FROM content_jobs j, json_each(j.provider_state_json) slot WHERE j.run_id=? AND json_extract(slot.value,'$.status') IN ('reserved','running','unknown','outcome_unknown')",(r,)),"PROVIDER_OUTCOME_UNKNOWN","Còn kết quả media chưa rõ")
            require(not one(c,"SELECT * FROM cards WHERE run_id=? AND status='pending'",(r,)),"PENDING_CARD","Cần xử lý thẻ trước khi kết thúc ngày")
            require(not one(c,"SELECT proposal_id FROM proposals WHERE run_id=? AND status='accepted'",(r,)),"PENDING_APPLY","Gói đã duyệt còn chờ áp dụng")
            require(not one(c,"SELECT * FROM content_versions WHERE run_id=? AND status IN ('draft','validated')",(r,)),"PENDING_CONTENT","Cần áp dụng hoặc từ chối bản nội dung")
            c.execute("UPDATE runs SET phase='settling' WHERE run_id=?",(r,))
            for sid in "ABCDE":
                prod=self.product(c,r,sid);inv=self.entity(c,"inventory",r,"product_id",prod["product_id"])
                self.settle(c,internal,r,sid,dict(day=run["current_day"],expected_inventory_version=inv["version"]))
            cursor=self.event(c,r,run["current_day"],"day_closed","orchestrator",visibility="internal",text="Đủ năm settlement, bàn giao học")
            summary={"day":run["current_day"],"history_updates":[],"pref_candidates":[],"calibration":{"factor":1.0,"points":0,"mape_today":None},"lesson_ops":[],"rejected_ops":0,"memory_md_path":""}
            # Local reference deliberately has no learning algorithm; never reports success.
            external=run["learning_mode"]=="external" and bool(run["memory_enabled"])
            insert(c,"learning_handoffs",run_id=r,day=run["current_day"],settlement_cursor=cursor,status="pending" if external else "skipped",night_summary_json=None if external else summary,memory_report_asset_id=None,error_code=None if external else "LEARNING_NOT_CONNECTED" if run["memory_enabled"] else "MEMORY_OFF",lease_until=self.expires(60) if external else None,summary_shop_id=run['demo_shop_id'],created_at=now(),updated_at=now())
            c.execute("UPDATE runs SET phase=? WHERE run_id=?",("learning" if external else "day_closed",r))
        elif kind=="advance_day":
            require(run["phase"]=="day_closed")
            handoff=one(c,"SELECT * FROM learning_handoffs WHERE run_id=? AND day=?",(r,run["current_day"]))
            require(handoff and handoff["status"] in {"completed","skipped"},"LEARNING_PENDING","Chưa hoàn tất bàn giao học")
            complete=run["current_day"]>=run["simulation_days"]
            c.execute("UPDATE runs SET current_day=?,phase=? WHERE run_id=?",(run["current_day"] if complete else run["current_day"]+1,"complete" if complete else "ready",r))
        else: raise Fault("OPERATION_UNKNOWN","Không hỗ trợ thao tác",422)
        c.execute("UPDATE runs SET version=version+1,updated_at=? WHERE run_id=?",(now(),r))
        result=self.safe_run(self.entity(c,"runs",r,"run_id",r))
        c.execute("UPDATE operations SET status='succeeded',result_json=?,lease_until=NULL,updated_at=? WHERE run_id=? AND operation_id=?",(dumps(result),now(),r,opid))
        return self.entity(c,"operations",r,"operation_id",opid)

    def reference_offer(self,c,p,r,s,source_card_id=None,owner_note=None):
        run=self.run(c,p,r);state=self.entity(c,"shop_runtime",r,"shop_id",s)
        neg=self.new_negotiation(c,p,r,s,dict(day=run["current_day"],expected_shop_version=state["version"],kind="renew" if run["current_day"]>1 else "propose",source_card_id=source_card_id,owner_note_vi=owner_note))
        platform=Principal("offline_platform","platform_agent",p.session_id,(r,),(s,))
        shop=Principal("offline_shop","shop_agent",p.session_id,(r,),(s,))
        product=self.product(c,r,s);public=self.public(c,r,s);rules,_=self.rules(c,r,s)
        default={"content_refresh":True,"ads_daily_budget":70000,"voucher_pct":10,"stop_roas_below":4.0,"stop_after_days":2,"duration_days":3}
        first=self.create_proposal(c,platform,r,s,dict(product_id=product["product_id"],negotiation_id=neg["negotiation_id"],package=default,stance="propose"))
        safe=safe_package(public["price"],self.current_cost(c,r,s)["unit_cost_vnd"],rules,public["stock"],fees=self.fee_config(c,r)[0])
        if owner_note:
            import re
            value=re.search(r"(\d+)\s*%",owner_note)
            if value:safe=safe_package(public["price"],self.current_cost(c,r,s)["unit_cost_vnd"],rules,public["stock"],{**safe,"voucher_pct":min(safe["voucher_pct"],int(value[1]))},fees=self.fee_config(c,r)[0])
        counter=self.create_proposal(c,shop,r,s,dict(product_id=product["product_id"],negotiation_id=neg["negotiation_id"],parent_proposal_id=first["proposal_id"],package=safe,stance="propose"))
        accepted=self.create_proposal(c,platform,r,s,dict(product_id=product["product_id"],negotiation_id=neg["negotiation_id"],parent_proposal_id=counter["proposal_id"],package=safe,stance="accept"))
        self.present(c,p,r,accepted["proposal_id"],accepted["version"])

    def auto_card(self,c,r,s):
        p=Principal("offline_seller","simulated_seller",None,(r,),(s,))
        card=one(c,"SELECT * FROM cards WHERE run_id=? AND shop_id=? AND status='pending'",(r,s))
        if not card: return
        if card["question_id"]:
            q=self.entity(c,"rule_questions",r,"question_id",card["question_id"])
            self.decision(c,p,r,dict(target_type="rule_question",target_id=q["question_id"],target_version=1,action="approve",rule_answer=True))
        if card["kind"]=="question": return
        prop=self.entity(c,"proposals",r,"proposal_id",card["proposal_id"])
        edited={**prop["package"],"voucher_pct":5} if s=="A" and prop["package"]["voucher_pct"]>5 else None
        decision=self.decision(c,p,r,dict(target_type="proposal",target_id=prop["proposal_id"],target_version=prop["version"],action="approve",edited_package=edited))
        internal=Principal("offline_driver","orchestrator",None,(r,),(s,))
        current=self.entity(c,"proposals",r,"proposal_id",decision["target_id"])
        _,versions=self.evaluation(c,r,s,current["package"])
        if current["package"]["content_refresh"]:
            job=self.content_create(c,internal,r,s,dict(proposal_id=current["proposal_id"],product_id=current["product_id"]),force_local=True)
            content=self.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
            d=self.decision(c,p,r,dict(target_type="content",target_id=content["content_id"],target_version=content["version"],action="approve",cover_option="B"))
            self.publish(c,internal,r,content["content_id"],dict(approval_decision_id=d["decision_id"],expected_active_content_id=self.product(c,r,s)["active_content_id"],skip_video=True))
        else:
            self.apply(c,internal,r,dict(proposal_id=current["proposal_id"],approval_decision_id=decision["decision_id"],expected_inventory_version=versions["inventory_version"],expected_rules_version=versions["rules_version"]))

    def recover(self):
        """Expire leases without resubmitting paid jobs or inventing learning success."""
        recovered={"content_jobs":0,"learning_handoffs":0,"operations":0}
        with self.store.connect(write=True) as c:
            for job in many(c,"SELECT * FROM content_jobs WHERE status IN ('queued','running') AND lease_until IS NOT NULL AND lease_until<?",(now(),)):
                p=Principal("lease_recovery","content_worker",None,(job["run_id"],),(job["shop_id"],),(job["job_id"],))
                self.content_result(c,p,job["run_id"],job["job_id"],dict(expected_job_version=job["version"],status="timed_out",provider_job_id=job["provider_job_id"],fallback_used=True,error_code="WORKER_LEASE_EXPIRED"))
                recovered["content_jobs"]+=1
            for h in many(c,"SELECT * FROM learning_handoffs WHERE status IN ('pending','running') AND lease_until IS NOT NULL AND lease_until<?",(now(),)):
                c.execute("UPDATE learning_handoffs SET status='failed',error_code='LEARNING_TIMEOUT',lease_until=NULL,version=version+1,updated_at=? WHERE run_id=? AND day=?",(now(),h["run_id"],h["day"]))
                self.event(c,h["run_id"],h["day"],"operation_failed","orchestrator",visibility="internal",payload={"error_code":"LEARNING_TIMEOUT","partial_writes_unknown":True},text="Học quá thời hạn; không tuyên bố học thành công")
                recovered["learning_handoffs"]+=1
                self.finish_night_tx(c,h["run_id"],h["day"])
            for op in many(c,"SELECT * FROM operations WHERE status='running' AND lease_until IS NOT NULL AND lease_until<?",(now(),)):
                c.execute("UPDATE operations SET status='failed',error_code='LEASE_EXPIRED_RESULT_UNKNOWN',lease_until=NULL,version=version+1 WHERE run_id=? AND operation_id=?",(op["run_id"],op["operation_id"]))
                recovered["operations"]+=1
            for h in many(c,"SELECT * FROM learning_handoffs WHERE auto_advance=1 AND status IN ('completed','skipped')"):
                self.finish_night_tx(c,h["run_id"],h["day"])
            groups=[x["group_id"] for x in many(c,"SELECT * FROM comparison_groups WHERE status IN ('queued','running')")]
        for gid in groups:self.drive_comparison(gid)
        return recovered

    def pause(self,c,p,r,cid,version,reason):
        campaign=self.entity(c,"campaigns",r,"campaign_id",cid)
        run=self.scope(c,p,r,campaign["shop_id"],{"seller","orchestrator","monitor"})
        require(campaign["version"]==version and campaign["status"]=="active")
        if p.role!="seller":
            require(reason in {"LOW_ROAS","LOW_STOCK","RULE_TIGHTENED"},"EVIDENCE_REQUIRED","Monitor phải dẫn điều kiện dừng")
            require((reason=="LOW_ROAS" and campaign["low_roas_streak"]>=campaign["package_snapshot"]["stop_after_days"]) or
                    (reason=="LOW_STOCK" and self.public(c,r,campaign["shop_id"])["stock"]<30) or
                    (reason=="RULE_TIGHTENED" and not self.evaluation(c,r,campaign["shop_id"],campaign["package_snapshot"])[0]["passed"]),"EVIDENCE_REQUIRED","Chưa có bằng chứng dừng")
        c.execute("UPDATE campaigns SET ads_status='paused',ads_stop_reason=?,version=version+1 WHERE run_id=? AND campaign_id=?",(reason,r,cid))
        self.event(c,r,run["current_day"],"auto_action",p.role,campaign["shop_id"],{"action":"pause_ads","reason":reason},text="Đã dừng quảng cáo, giữ voucher và nội dung")
        return self.entity(c,"campaigns",r,"campaign_id",cid)
