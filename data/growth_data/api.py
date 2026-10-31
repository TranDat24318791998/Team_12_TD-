"""Standalone FastAPI transport; root application is intentionally untouched."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from . import models as M
from .errors import Fault, require
from .service import DataService, Principal, PRIVATE
from .facade import Facade
from .storage import dumps, fingerprint, insert, many, now, one, uid
from .simulation import business_date
from .evidence import compare, proof, replay_export


def create_app(home=None, *, content_mode=None, learning_mode=None,calibration_provider=None):
    service=DataService(home or os.environ.get("GROWTH_DATA_HOME") or Path(__file__).resolve().parents[1]/"runtime",content_mode=content_mode or os.environ.get("GROWTH_CONTENT_MODE","local"),learning_mode=learning_mode or os.environ.get("GROWTH_LEARNING_MODE","skip"),calibration_provider=calibration_provider)
    facade=Facade(service)
    @asynccontextmanager
    async def lifespan(app):
        service.recover()
        async def sweep():
            while True:
                await asyncio.sleep(1)
                await asyncio.to_thread(service.recover)
        task=asyncio.create_task(sweep())
        try:yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):await task
    application=FastAPI(title="Growth Agents Data API",version="2.0.0",lifespan=lifespan)
    application.state.service=service
    secret_file=service.home/"cursor.secret"
    if not secret_file.exists(): secret_file.write_bytes(secrets.token_bytes(32));secret_file.chmod(0o600)
    cursor_secret=secret_file.read_bytes()

    @application.exception_handler(Fault)
    async def failure(request,exc):
        error={"code":exc.code,"message":exc.message,"request_id":request.headers.get("X-Request-ID") or uid("req")}
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/v1/"):
            error={"code":exc.code,"message_vi":exc.message}
        return JSONResponse({"error":error},status_code=exc.status)

    async def invalid(request,exc):
        return await failure(request,Fault("VALIDATION_ERROR","Dữ liệu gửi lên không đúng schema",422))
    application.add_exception_handler(ValidationError,invalid)
    application.add_exception_handler(RequestValidationError,invalid)
    async def conflict(request,exc):return await failure(request,Fault("CONSTRAINT_CONFLICT","Dữ liệu trùng hoặc liên kết không hợp lệ",409))
    application.add_exception_handler(sqlite3.IntegrityError,conflict)

    def identity(request,bootstrap=False):
        authorization=request.headers.get("authorization","")
        if authorization:
            require(authorization.startswith("Bearer "),"UNAUTHENTICATED","Cần Bearer token",401)
            return service.authenticate(token=authorization[7:])
        sid=request.cookies.get("growth_sid")
        if sid:
            p=service.authenticate(sid=sid)
            if request.method not in {"GET","HEAD","OPTIONS"}:
                origin=request.headers.get("origin")
                require(origin is None or origin.rstrip("/")==str(request.base_url).rstrip("/"),"CSRF_REJECTED","Origin không hợp lệ",403)
            return p
        require(bootstrap,"UNAUTHENTICATED","Cần tạo phiên qua /api/state",401)
        return service.bootstrap()

    def respond(request,p,data,legacy=False,status=200,meta=None):
        output=data if legacy else {"data":data,"meta":{"request_id":request.headers.get("X-Request-ID") or uid("req"),**(meta or {})}}
        result=JSONResponse(output,status_code=status)
        if p.role=="seller" and p.session_id:
            result.set_cookie("growth_sid",p.session_id,httponly=True,secure=request.url.scheme=="https",samesite="lax")
        return result

    def page(request,p,rows,r):
        try:limit=int(request.query_params.get("limit",50))
        except ValueError:raise Fault("QUERY_INVALID","limit phải là số nguyên",422)
        require(1<=limit<=100,"QUERY_INVALID","limit phải từ 1 đến 100",422)
        filters=sorted((k,v) for k,v in request.query_params.multi_items() if k not in {"cursor","limit"})
        binding=fingerprint([request.url.path,p.principal_id,p.role,r,filters])
        offset=0
        if value:=request.query_params.get("cursor"):
            try:
                raw,sig=value.split(".");require(hmac.compare_digest(sig,hmac.new(cursor_secret,raw.encode(),hashlib.sha256).hexdigest()),"CURSOR_INVALID","Cursor không hợp lệ",422)
                payload=json.loads(base64.urlsafe_b64decode(raw+"="*(-len(raw)%4)));require(payload["binding"]==binding,"CURSOR_INVALID","Cursor khác truy vấn",422);offset=int(payload["offset"])
                require(offset>=0,"CURSOR_INVALID","Cursor không hợp lệ",422)
            except (ValueError,KeyError,TypeError):raise Fault("CURSOR_INVALID","Cursor không hợp lệ",422)
        next_cursor=None
        if offset+limit<len(rows):
            raw=base64.urlsafe_b64encode(dumps({"binding":binding,"offset":offset+limit}).encode()).decode().rstrip("=")
            next_cursor=raw+"."+hmac.new(cursor_secret,raw.encode(),hashlib.sha256).hexdigest()
        return rows[offset:offset+limit],{"next_cursor":next_cursor}

    @application.get("/health")
    def health(): return {"ok":True,"service":"growth-data","storage":"sqlite_local","schema_version":2,"providers_called_by_data_api":False}

    async def read(request,tag):
        p=identity(request);params=request.path_params;r=params.get("r");s=params.get("s")
        with service.store.connect() as c:
            run=service.run(c,p,r)
            for name in ("from_date","to_date"):
                value=request.query_params.get(name)
                if value:
                    try:date.fromisoformat(value)
                    except ValueError:raise Fault("QUERY_INVALID","Ngày phải có dạng YYYY-MM-DD",422)
                    require(value<=business_date(run["current_day"]),"FUTURE_UNAVAILABLE","Ngày tương lai không được đọc",422)
            require(not (request.query_params.get("from_date") and request.query_params.get("to_date")) or request.query_params["from_date"]<=request.query_params["to_date"],"QUERY_INVALID","from_date lớn hơn to_date",422)
            meta={}
            if tag=="run":data=service.safe_run(run)
            elif tag=="state":
                sid=request.query_params.get("shop_id","D");service.scope(c,p,r,sid,{"seller","orchestrator"})
                data={"run":service.safe_run(run),"shop":service.public(c,r,sid),"pending_cards":many(c,"SELECT * FROM cards WHERE run_id=? AND shop_id=? AND status='pending'",(r,sid)),"jobs":many(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id=?",(r,sid))}
            elif tag=="shops":
                service.scope(c,p,r,roles={"platform_agent","orchestrator","data_admin"})
                data=[service.context(c,p,r,sid)["shop"] for sid in "ABCDE" if "*" in p.allowed_shop_ids or sid in p.allowed_shop_ids]
                if request.query_params.get("eligible_only") in {"true","1"}:data=[x for x in data if service.context(c,p,r,x["shop_id"])["eligibility"]["eligible"]]
            elif tag=="context":data=service.context(c,p,r,s)
            elif tag in {"products","inventory","costs","rules","metrics","history","campaigns","content","questions","forecasts"}:
                roles={"platform_agent"}|PRIVATE if tag in {"products","metrics","history","campaigns","forecasts"} else PRIVATE|({"content_worker"} if tag=="content" else set())
                service.scope(c,p,r,s,roles)
                prod=service.product(c,r,s)
                if tag=="products":data=[{"product_id":prod["product_id"],"facts":prod["facts"],"listing":service.public(c,r,s)}]
                elif tag=="inventory":data=service.entity(c,"inventory",r,"product_id",prod["product_id"])
                elif tag=="costs":
                    try:day=int(request.query_params.get("as_of_day",run["current_day"]))
                    except ValueError:raise Fault("QUERY_INVALID","as_of_day phải là số nguyên",422)
                    require(-13<=day<=run["current_day"],"FUTURE_UNAVAILABLE","Ngày chưa quan sát",422)
                    data=one(c,"SELECT * FROM product_costs WHERE run_id=? AND product_id=? AND effective_day<=? ORDER BY cost_version DESC LIMIT 1",(r,prod["product_id"],day))
                elif tag=="rules":rules,rv=service.rules(c,r,s);data={"rules":rules,"rules_version":rv}
                elif tag=="metrics":
                    data=service.metric_rows(c,p,r,s)
                    channel=request.query_params.get("channel","all");require(channel in {"all","organic","paid"},"QUERY_INVALID","channel không hợp lệ",422)
                    if channel!="all":data=[x for x in data if x["channel"]==channel]
                elif tag=="history":data=service.history(c,p,r,s)
                elif tag=="campaigns":
                    data=many(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id=? ORDER BY created_at",(r,s))
                    if p.role=="platform_agent":data=[{k:v for k,v in x.items() if k in {"campaign_id","shop_id","product_id","package_snapshot","start_day","end_day","status","ads_status","spent_vnd"}} for x in data]
                elif tag=="content":
                    data=many(c,"SELECT * FROM content_versions WHERE run_id=? AND product_id=? ORDER BY content_version",(r,prod["product_id"]))
                    if p.role=="content_worker":
                        jobs=many(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id=?",(r,s))
                        allowed={cid for job in jobs if "*" in p.allowed_job_ids or job["job_id"] in p.allowed_job_ids for cid in job["output_content_ids"]+[job["source_content_id"]]}
                        data=[row for row in data if row["content_id"] in allowed]
                elif tag=="questions":data=many(c,"SELECT * FROM rule_questions WHERE run_id=? AND shop_id=? ORDER BY created_at",(r,s))
                else:data=many(c,"SELECT * FROM forecasts WHERE run_id=? AND product_id=? ORDER BY created_at",(r,prod["product_id"]))
                if request.query_params.get("status") and isinstance(data,list):data=[x for x in data if x.get("status")==request.query_params["status"]]
                if tag=="forecasts" and request.query_params.get("proposal_id"):data=[x for x in data if x["proposal_id"]==request.query_params["proposal_id"]]
            elif tag=="policies":service.scope(c,p,r,roles={"platform_agent"}|PRIVATE|{"content_worker"});data=service.policies(c,r)
            elif tag in {"market","summary"}:
                service.scope(c,p,r,roles={"platform_agent","orchestrator","data_admin"} if tag=="market" else {"platform_agent"}|PRIVATE)
                data=many(c,"SELECT * FROM market_daily WHERE run_id=? AND date<=? ORDER BY date",(r,business_date(run["current_day"]))) if tag=="market" else service.market_summary(c,r,run)
                if tag=="market" and request.query_params.get("keyword"):data=[x for x in data if x["keyword"]==request.query_params["keyword"]]
            elif tag=="events":
                try:after=int(request.query_params.get("after_seq",0));limit=int(request.query_params.get("limit",50))
                except ValueError:raise Fault("QUERY_INVALID","Cursor sự kiện không hợp lệ",422)
                require(after>=0 and 1<=limit<=100,"QUERY_INVALID","Cursor/limit không hợp lệ",422)
                data,cursor,more=service.events(c,p,r,after,limit);meta={"next_cursor":cursor,"has_more":more}
            elif tag=="proposal":data=service.shared_proposal(c,p,r,service.entity(c,"proposals",r,"proposal_id",params["pid"]))
            elif tag=="job":
                data=service.job_access(c,p,r,params["jid"]);service.scope(c,p,r,data["shop_id"],PRIVATE|{"content_worker"})
            elif tag=="operation":data=service.entity(c,"operations",r,"operation_id",params["oid"]);service.scope(c,p,r,roles={"seller","orchestrator","data_admin"});data=service.operation_view(data,p.role)
            elif tag=="download":
                a=service.asset_access(c,p,r,params["aid"]);require(a["upload_status"]=="ready","ASSET_PENDING","File chưa sẵn sàng")
                require(service.object_path(a["object_key"]).is_file(),"NOT_FOUND","Không tìm thấy file",404)
                return FileResponse(service.object_path(a["object_key"]),media_type=a["mime_type"],headers={"Cache-Control":"private, no-store"})
            elif tag=="document":
                try:version=int(request.query_params.get("version",1))
                except ValueError:raise Fault("QUERY_INVALID","Version không hợp lệ",422)
                doc=one(c,"SELECT * FROM knowledge_documents WHERE document_id=? AND document_version=? AND index_status='ready'",(params["did"],version))
                require(doc and doc["knowledge_release"]=="knowledge-v1","NOT_FOUND","Không tìm thấy tài liệu",404)
                if p.role=="content_worker" and doc["document_id"].startswith("product_"):
                    jobs=many(c,"SELECT * FROM content_jobs WHERE run_id=?",(r,))
                    require(any(doc["document_id"]=="product_"+job["product_id"] and ("*" in p.allowed_job_ids or job["job_id"] in p.allowed_job_ids) and ("*" in p.allowed_shop_ids or job["shop_id"] in p.allowed_shop_ids) for job in jobs),"NOT_FOUND","Tài liệu không thuộc job",404)
                if doc["collection_scope"]=="shop_private":
                    require(doc["owner_run_id"]==r and p.role in PRIVATE,"NOT_FOUND","Không tìm thấy tài liệu",404);service.scope(c,p,r,doc["owner_shop_id"])
                require(doc["effective_from"]<=business_date(run["current_day"]),"NOT_FOUND","Tài liệu chưa hiệu lực",404)
                require(doc["effective_to"] is None or doc["effective_to"]>=business_date(run["current_day"]),"NOT_FOUND","Tài liệu hết hiệu lực",404)
                data={"document_id":doc["document_id"],"document_version":version,"is_simulated":bool(doc["is_simulated"]),"content":service.object_path(doc["source_object_key"]).read_text()}
            elif tag=="learning_input":
                service.scope(c,p,r,roles={"learning_worker"});day=int(request.query_params.get("day",run["current_day"]))
                h=one(c,"SELECT * FROM learning_handoffs WHERE run_id=? AND day=?",(r,day));require(h,"DAY_NOT_SETTLED","Ngày chưa chốt")
                shops=[sid for sid in "ABCDE" if "*" in p.allowed_shop_ids or sid in p.allowed_shop_ids]
                data={"day":day,"settlement_cursor":h["settlement_cursor"],"metrics":{sid:[x for x in service.metric_rows(c,p,r,sid) if x["day"]==day] for sid in shops},"forecasts":[]}
                data.update(status=h["status"],version=h["version"],lease_until=h["lease_until"],attempt=h["attempt"])
                data["history"]={};data["decisions"]={};data["content_feedback"]={}
                for sid in shops:
                    data["forecasts"].extend(many(c,"SELECT f.* FROM forecasts f JOIN products pr ON pr.run_id=f.run_id AND pr.product_id=f.product_id WHERE f.run_id=? AND pr.shop_id=? AND f.as_of_day<=?",(r,sid,day)))
                    rows=many(c,"SELECT pr.* FROM proposals pr JOIN negotiations n ON n.run_id=pr.run_id AND n.negotiation_id=pr.negotiation_id WHERE pr.run_id=? AND pr.shop_id=? AND n.day<=? ORDER BY pr.created_at",(r,sid,day))
                    data["history"][sid]=[service.shared_proposal(c,p,r,row) for row in rows]
                    data["decisions"][sid]=many(c,"SELECT d.* FROM decisions d WHERE d.run_id=? AND d.shop_id=? AND d.decision_id IN (SELECT json_extract(payload_json,'$.decision_id') FROM events WHERE run_id=? AND seq<=? AND type='seller_decision') ORDER BY d.created_at",(r,sid,r,h["settlement_cursor"]))
                    data["content_feedback"][sid]=many(c,"SELECT job_id,attempt,feedback_history_json,style_notes_json FROM content_jobs WHERE run_id=? AND shop_id=? AND job_id IN (SELECT json_extract(payload_json,'$.job_id') FROM events WHERE run_id=? AND seq<=? AND type='content_job') ORDER BY created_at",(r,sid,r,h["settlement_cursor"]))
            elif tag=="proof":data=proof(service,c,p,r,request.query_params.get("group_id"),request.query_params.get("variant","full_7d"))
            else:raise Fault("NOT_FOUND","Route không tồn tại",404)
            from_date=request.query_params.get("from_date");to_date=request.query_params.get("to_date")
            cutoff=business_date(run["current_day"])
            require(not to_date or to_date<=cutoff,"FUTURE_UNAVAILABLE","Ngày tương lai không được đọc",422)
            if isinstance(data,list) and tag!="events":
                if from_date:data=[x for x in data if x.get("date",from_date)>=from_date]
                if to_date:data=[x for x in data if x.get("date",to_date)<=to_date]
                data,meta=page(request,p,data,r)
                if tag in {"metrics","market"}:meta["as_of_date"]=cutoff
            return respond(request,p,data,meta=meta)

    async def write(request,tag,body):
        p=identity(request);params=request.path_params;r=params.get("r");s=params.get("s")
        if hasattr(body,"model_dump"):body=body.model_dump()
        if body is None:body={}
        key=request.headers.get("Idempotency-Key")
        require(request.headers.get("X-Request-ID"),"REQUEST_ID_REQUIRED","Cần X-Request-ID",400)
        def execute(c):
            if tag=="create_run":return service.create_run(c,p,body)
            if tag=="reset":
                run=service.scope(c,p,r,roles={"seller"});require(M.Version.model_validate(body).expected_version==run["version"])
                return service.create_run(c,p,{"seed":run["seed"],"mode":run["mode"],"memory_enabled":bool(run["memory_enabled"]),"simulation_days":run["simulation_days"],"execution_profile":run["execution_profile"],"content_mode":run["content_mode"],"learning_mode":run["learning_mode"],"driver_config":run["config"].get("driver",{}),"data_source":run["config"].get("source","simulation")})
            if tag in {"start_day","close_day","advance_day"}:return service.operation(c,p,r,tag,body)
            if tag=="negotiation":return service.new_negotiation(c,p,r,s,body)
            if tag=="checks":
                service.scope(c,p,r,s,{"platform_agent","shop_agent"});b=M.CheckRequest.model_validate(body);require(service.product(c,r,s)["product_id"]==b.product_id,"NOT_FOUND","Sản phẩm không thuộc shop",404)
                if p.role=="platform_agent":
                    stock=service.public(c,r,s)["stock"]
                    violations=[]
                    if b.package.ads_daily_budget and stock<30:violations.append("STOCK_TOO_LOW_FOR_ADS")
                    return {"passed":not violations,"checks":[{"code":code,"passed":False,"severity":"block","message":"Vi phạm điều kiện công khai của sàn"} for code in violations],"evaluated_at":now(),"input_versions":{"inventory_version":service.entity(c,"inventory",r,"product_id",b.product_id)["version"]}}
                result,versions=service.evaluation(c,r,s,b.package)
                return {**result,"checks":[{"code":v,"passed":False,"severity":"block","message":"Vi phạm luật shop"} for v in result["violations"]],"input_versions":versions,"evaluated_at":now()}
            if tag=="proposal":return service.create_proposal(c,p,r,s,body)
            if tag=="present":return service.present(c,p,r,params["pid"],M.Version.model_validate(body).expected_version)
            if tag=="decision":return service.decision(c,p,r,body)
            if tag=="apply":return service.apply(c,p,r,body)
            if tag=="pause":
                b=M.Pause.model_validate(body);return service.pause(c,p,r,params["cid"],b.expected_version,b.reason_code)
            if tag=="question":return service.question(c,p,r,s,body)
            if tag=="rules":
                service.scope(c,p,r,s,{"seller","simulated_seller"});b=M.RulesUpdate.model_validate(body)
                d=service.entity(c,"decisions",r,"decision_id",b.confirmation_decision_id)
                require(d["target_type"]=="rule_question" and d["shop_id"]==s and d["action"]=="approve")
                current,version=service.rules(c,r,s)
                # Confirmation transaction already applied the one authorized field.
                require(version==b.expected_rules_version+1 and current==b.rules.model_dump())
                return {"rules":current,"rules_version":version}
            if tag=="content_create":return service.content_create(c,p,r,s,body)
            if tag=="content_result":return service.content_result(c,p,r,params["jid"],body)
            if tag=="publish":return service.publish(c,p,r,params["cid"],body)
            if tag=="upload":return service.upload_create(c,p,r,body)
            if tag=="complete_upload":return service.complete_upload(c,p,r,params["aid"],M.CompleteUpload.model_validate(body).checksum)
            if tag=="search":return service.knowledge_search(c,p,r,body)
            if tag=="settle":return service.settle(c,p,r,s,body)
            if tag=="replay":
                if body:service.register_recording(c,p,r,body)
                return replay_export(service,c,p,r)
            if tag=="learning_result":
                return service.learning_result(c,p,r,body)
            if tag in {"knowledge_create","knowledge_revoke"}:
                require(p.role=="knowledge_admin","FORBIDDEN","Cần quyền knowledge_admin",403)
                if tag=="knowledge_revoke":
                    require(set(body)=={"document_version","reason_vi"},"INVALID_FIELDS","Sai trường yêu cầu",422)
                    c.execute("UPDATE knowledge_documents SET index_status='revoked' WHERE document_id=? AND document_version=?",(params["did"],body["document_version"]))
                    return {"document_id":params["did"],"status":"revoked"}
                b=M.KnowledgeCreate.model_validate(body)
                if b.collection_scope=="shop_private":require(b.owner_run_id and b.owner_shop_id);service.scope(c,p,b.owner_run_id,b.owner_shop_id)
                if b.source_asset_id:
                    require(b.source_run_id,"SOURCE_REQUIRED","Cần source_run_id",422)
                    asset=service.asset_access(c,p,b.source_run_id,b.source_asset_id)
                    require(asset["purpose"]=="knowledge_source" and asset["upload_status"]=="ready" and asset["mime_type"]=="text/markdown","SOURCE_INVALID","Local keyword index cần nguồn Markdown đã ready",422)
                    source_key=asset["object_key"]
                else:
                    require(b.source_object_key,"SOURCE_REQUIRED","Cần source_asset_id hoặc nguồn backend",422)
                    source_key=b.source_object_key
                path=service.object_path(source_key)
                require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==b.checksum,"CHECKSUM_INVALID","Nguồn tài liệu không hợp lệ",422)
                values=b.model_dump(exclude={"source_asset_id","source_run_id"});values["source_object_key"]=source_key
                insert(c,"knowledge_documents",**values,provider_file_id=None,vector_store_id=None,index_status="ready",created_at=now())
                return {"document_id":b.document_id,"index_status":"ready","backend":"local_keyword"}
            raise Fault("NOT_FOUND","Route không tồn tại",404)
        result=service.command(p,r or p.session_id or p.principal_id,request.url.path,key,body,execute,request.method)
        status=202 if tag in {"start_day","close_day","advance_day","content_create","knowledge_create"} else 201 if tag in {"create_run","reset","proposal","decision","apply","question","upload","negotiation"} else 200
        return respond(request,p,result,status=status)

    def get_endpoint(tag):
        async def endpoint(request:Request):return await read(request,tag)
        endpoint.__name__="read_"+tag
        return endpoint

    def post_endpoint(tag,model):
        async def endpoint(request:Request,body):return await write(request,tag,body)
        endpoint.__annotations__["body"]=model or dict
        endpoint.__name__="write_"+tag
        return endpoint

    reads={
        "/runs/{r}":"run","/runs/{r}/state":"state","/runs/{r}/shops":"shops","/runs/{r}/policies":"policies",
        "/runs/{r}/market/observations":"market","/runs/{r}/market/summary":"summary","/runs/{r}/events":"events",
        "/runs/{r}/proposals/{pid}":"proposal","/runs/{r}/content-jobs/{jid}":"job","/runs/{r}/operations/{oid}":"operation",
        "/runs/{r}/assets/{aid}/download":"download","/runs/{r}/knowledge/documents/{did}":"document","/runs/{r}/proof":"proof"}
    for resource,tag in (("products","products"),("context","context"),("inventory","inventory"),("costs","costs"),("rules","rules"),("metrics","metrics"),("history","history"),("campaigns","campaigns"),("content","content"),("rule-questions","questions"),("forecasts","forecasts")):
        reads[f"/runs/{{r}}/shops/{{s}}/{resource}"]=tag
    for path,tag in reads.items():application.add_api_route("/api/v1"+path,get_endpoint(tag),methods=["GET"])
    writes=[("/runs","create_run",M.RunCreate),("/runs/{r}/reset","reset",M.Version),
            ("/runs/{r}/shops/{s}/checks","checks",M.CheckRequest),("/runs/{r}/shops/{s}/proposals","proposal",M.ProposalCreate),
            ("/runs/{r}/proposals/{pid}/present","present",M.Version),("/runs/{r}/decisions","decision",M.DecisionCreate),
            ("/runs/{r}/campaigns/apply","apply",M.CampaignApply),("/runs/{r}/campaigns/{cid}/pause","pause",M.Pause),
            ("/runs/{r}/shops/{s}/content-jobs","content_create",M.ContentCreate),("/runs/{r}/content/{cid}/publish","publish",M.Publish),
            ("/runs/{r}/assets/uploads","upload",M.UploadCreate),("/runs/{r}/assets/{aid}/complete","complete_upload",M.CompleteUpload),
            ("/runs/{r}/knowledge/search","search",M.KnowledgeSearch)]
    for operation in ("start","close","advance"):writes.append((f"/runs/{{r}}/days/{operation}",operation+"_day",M.DayCommand))
    for path,tag,model in writes:application.add_api_route("/api/v1"+path,post_endpoint(tag,model),methods=["POST"])
    application.add_api_route("/api/v1/runs/{r}/shops/{s}/rules",post_endpoint("rules",M.RulesUpdate),methods=["PUT"])
    internals=[("/runs/{r}/shops/{s}/negotiations","negotiation",M.NegotiationCreate),("/runs/{r}/shops/{s}/settle-day","settle",M.Settle),
               ("/runs/{r}/shops/{s}/rule-questions","question",M.RuleQuestionCreate),("/runs/{r}/learning-results","learning_result",M.LearningResult),
               ("/runs/{r}/content-jobs/{jid}/result","content_result",M.ContentResult),("/runs/{r}/replay/export","replay",dict),
               ("/knowledge/documents","knowledge_create",M.KnowledgeCreate),("/knowledge/documents/{did}/revoke","knowledge_revoke",dict)]
    for path,tag,model in internals:application.add_api_route("/internal/v1"+path,post_endpoint(tag,model),methods=["POST"])
    application.add_api_route("/internal/v1/runs/{r}/learning-input",get_endpoint("learning_input"),methods=["GET"])

    @application.put("/api/v1/runs/{r}/assets/{aid}/bytes")
    async def bytes_upload(request:Request,r:str,aid:str):
        p=identity(request)
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk);require(len(data)<=50*1024*1024,"FILE_TOO_LARGE","File vượt giới hạn",413)
        return respond(request,p,service.upload_bytes(p,r,aid,bytes(data)))

    async def legacy(request,tag):
        p=identity(request,bootstrap=tag in {"state","reset"})
        require(p.role=="seller","FORBIDDEN","Legacy facade dành cho seller session",403)
        try:body=await request.json() if request.method=="POST" and await request.body() else {}
        except (ValueError,UnicodeDecodeError):raise Fault("VALIDATION_ERROR","JSON không hợp lệ",422)
        require(isinstance(body,dict),"VALIDATION_ERROR","Body phải là JSON object",422)
        with service.store.connect() as c:current=one(c,"SELECT r.* FROM active_runs a JOIN runs r ON r.run_id=a.run_id WHERE a.session_id=?",(p.session_id,))
        if tag=="reset" or current is None:
            require(tag in {"state","reset"},"RUN_REQUIRED","Cần khởi tạo phiên",404)
            require(set(body)<={"memory","seed","simulation_days","execution_profile","content_mode","learning_mode","mode"},"INVALID_FIELDS","Trường reset không hợp lệ",422)
            key=request.headers.get("Idempotency-Key") or ("bootstrap" if tag=="state" else None)
            created=service.command(p,p.session_id,"/api/reset",key,body,lambda c:service.create_run(c,p,{"seed":body.get("seed",42),"memory_enabled":body.get("memory",True),**{k:v for k,v in body.items() if k not in {"memory","seed"}}}))
            with service.store.connect() as c:state=facade.state(c,p)
            if tag=="reset":return respond(request,p,{"run_id":created["run_id"],"day":1,"mode":state["mode"],"state":state},legacy=True)
            current={"run_id":created["run_id"]}
        r=current["run_id"]
        if request.method=="GET":
            with service.store.connect() as c:
                if tag=="state":data=facade.state(c,p)
                elif tag=="events":
                    try:after=int(request.query_params.get("after",0))
                    except ValueError:raise Fault("QUERY_INVALID","after không hợp lệ",422)
                    rows,cursor,_=service.events(c,p,r,after,100)
                    actors={"platform_turn":"platform_agent","opportunity":"platform_agent","shop_turn":"shop_agent","code_check":"code","seller_decision":"seller","content_job":"content_agent","market_result":"market","night_summary":"memory","memory_read":"memory","memory_write":"memory","referee_review":"referee"}
                    data={"events":[{"seq":e["seq"],"run_id":r,"day":e["day"],"ts":e["simulated_at"][11:16],"type":e["type"],"actor":actors.get(e["type"],"system"),"shop_id":e["shop_id"],"text_vi":e["text_vi"],"data":e["payload"]} for e in rows],"last_seq":cursor}
                else:
                    g=one(c,"SELECT * FROM comparison_groups WHERE session_id=? ORDER BY rowid DESC LIMIT 1",(p.session_id,))
                    if g and service.comparison_view(c,p,g["group_id"])["status"]=="ready":
                        data=proof(service,c,p,g["run_on_id"],g["group_id"],request.query_params.get("variant","full_7d"));data["metrics"]=[m for m in data["metrics"] if m["on"] is not None and m["off"] is not None];data["status"]="ready"
                    else:data={"seed":42,"days":7,"run_on":g["run_on_id"] if g else "","run_off":g["run_off_id"] if g else "","metrics":[],"status":"pending" if g else "not_ready","note_vi":"Chưa có hai run hoàn chỉnh trong phiên. Tạo comparison qua /api/v1/comparisons; không dựng số thắng giả."}
            return respond(request,p,data,legacy=True)
        if tag=="night":
            require(not body,"INVALID_FIELDS","Night không nhận trường tùy ý",422)
            op=service.begin_night(p,r,request.headers.get("Idempotency-Key"))
            if op["status"]=="succeeded":return respond(request,p,op["result"],legacy=True)
            return respond(request,p,{"day":op["day"],"step":"day_done","operation_id":op["operation_id"],"status":op["status"],"error_code":op["error_code"]},legacy=True,status=202)
        def execute(c):
            if tag=="start":
                require(not body,"INVALID_FIELDS","Start không nhận trường tùy ý",422)
                run=service.run(c,p,r);service.operation(c,p,r,"start_day",dict(expected_day=run["current_day"],expected_version=run["version"]))
                state=facade.state(c,p);return {"day":state["day"],"step":state["step"]}
            if tag=="decision":return facade.decide(c,p,r,body)
            if tag=="retry":return facade.retry(c,p,r,body)
            if tag=="apply":return facade.use_content(c,p,r,body)
            if tag=="night":return facade.night(c,p,r)
            raise Fault("NOT_FOUND","Không tìm thấy route",404)
        key=request.headers.get("Idempotency-Key")
        require(key,"IDEMPOTENCY_KEY_REQUIRED","Cần Idempotency-Key để retry an toàn",400)
        result=service.command(p,r,request.url.path,key,body,execute)
        return respond(request,p,result,legacy=True)

    def legacy_endpoint(tag):
        async def endpoint(request:Request):return await legacy(request,tag)
        endpoint.__name__="demo_"+tag
        return endpoint
    for path,tag,method in (("/state","state","GET"),("/reset","reset","POST"),("/day/start","start","POST"),("/events","events","GET"),("/decision","decision","POST"),("/content/retry","retry","POST"),("/content/apply","apply","POST"),("/night","night","POST"),("/proof","proof","GET")):
        application.add_api_route("/api"+path,legacy_endpoint(tag),methods=[method])
    from .routes import register_integration_routes
    register_integration_routes(application,service,facade,identity,respond)
    original_openapi=application.openapi
    def openapi():
        schema=original_openapi()
        schema.setdefault("components",{}).setdefault("securitySchemes",{}).update({"BearerAuth":{"type":"http","scheme":"bearer"},"SellerSession":{"type":"apiKey","in":"cookie","name":"growth_sid"}})
        for path,operations in schema["paths"].items():
            if path.startswith(("/api/v1","/internal/v1")):
                for operation in operations.values():
                    if isinstance(operation,dict):operation["security"]=[{"BearerAuth":[]},{"SellerSession":[]}]
            for method,operation in operations.items():
                if method in {"post","put"}:
                    names=["Idempotency-Key"]+(["X-Request-ID"] if path.startswith(("/api/v1/","/internal/v1/")) else [])
                    if path.endswith("/bytes"):names=[]
                    operation.setdefault("parameters",[]).extend({"name":name,"in":"header","required":True,"schema":{"type":"string"}} for name in names)
        return schema
    application.openapi=openapi
    return application
