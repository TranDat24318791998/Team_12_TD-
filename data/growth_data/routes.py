"""Additive v2 integration endpoints. Existing seller routes remain available."""

from fastapi import BackgroundTasks, Request
from fastapi.responses import StreamingResponse

from . import models as M
from .errors import require
from .errors import Fault
from .storage import dumps, many, one


def register_integration_routes(app, service, facade, identity, respond):
    def command(request,p,r,body,fn):
        require(request.headers.get("X-Request-ID"),"REQUEST_ID_REQUIRED","Cần X-Request-ID",400)
        return service.command(p,r or p.session_id or p.principal_id,request.url.path,request.headers.get("Idempotency-Key"),body,fn,request.method)

    @app.get("/api/v1/runs/{r}/operations")
    def operations(request:Request,r:str,status:str|None=None,kind:str|None=None):
        p=identity(request)
        with service.store.connect() as c:
            service.scope(c,p,r,roles={"seller","orchestrator","data_admin"})
            rows=many(c,"SELECT * FROM operations WHERE run_id=? ORDER BY rowid",(r,))
            if status:rows=[x for x in rows if x["status"]==status]
            if kind:rows=[x for x in rows if x["kind"]==kind]
            return respond(request,p,[service.operation_view(x,p.role) for x in rows])

    @app.post("/internal/v1/runs/{r}/operations/{oid}/claim")
    def claim(request:Request,r:str,oid:str,body:M.Version):
        p=identity(request);b=body.model_dump()
        return respond(request,p,command(request,p,r,b,lambda c:service.operation_claim(c,p,r,oid,b)))

    @app.post("/internal/v1/runs/{r}/operations/{oid}/result")
    def result(request:Request,r:str,oid:str,body:M.OperationResult):
        p=identity(request);b=body.model_dump()
        return respond(request,p,command(request,p,r,b,lambda c:service.operation_result(c,p,r,oid,b)))

    def learning_route(action):
        def control(request:Request,r:str,day:int,body:M.LearningControl):
            p=identity(request);b=body.model_dump()
            return respond(request,p,command(request,p,r,b,lambda c:service.learning_control(c,p,r,day,action,b)))
        return control
    for action in ("retry","skip"):
        app.add_api_route(f"/api/v1/runs/{{r}}/days/{{day}}/learning/{action}",learning_route(action),methods=["POST"])

    @app.get("/api/v1/runs/{r}/shops/{s}/night-summary")
    def night_summary(request:Request,r:str,s:str,day:int):
        p=identity(request)
        with service.store.connect() as c:return respond(request,p,service.night_view(c,p,r,s,day))

    @app.post("/api/v1/runs/{r}/content/{cid}/restore")
    def restore(request:Request,r:str,cid:str,body:M.Restore):
        p=identity(request);b=body.model_dump()
        return respond(request,p,command(request,p,r,b,lambda c:service.restore_content(c,p,r,cid,b)))

    @app.post("/api/content/undo")
    async def undo(request:Request):
        p=identity(request)
        require(p.role=="seller","FORBIDDEN","Cần seller",403)
        require(request.headers.get('X-Request-ID'),'REQUEST_ID_REQUIRED','Cần X-Request-ID',400)
        try:body=await request.json()
        except (ValueError,UnicodeDecodeError):raise Fault("VALIDATION_ERROR","JSON không hợp lệ",422)
        b=M.LegacyRestore.model_validate(body).model_dump();cid=b.pop("target_content_id")
        with service.store.connect() as c:r=facade.current(c,p)["run_id"]
        result=service.command(p,r,request.url.path,request.headers.get("Idempotency-Key"),{"target_content_id":cid,**b},lambda c:service.restore_content(c,p,r,cid,b))
        return respond(request,p,result,legacy=True)

    @app.post('/api/negotiation/restore')
    def restore_offer(request:Request,body:M.OfferRestore):
        p=identity(request)
        require(p.role=='seller' and p.session_id,'FORBIDDEN','Cần phiên người bán',403)
        with service.store.connect() as c:r=facade.current(c,p)['run_id']
        b=body.model_dump()
        result=command(request,p,r,b,lambda c:service.restore_failed_offer(c,p,r,b))
        return respond(request,p,result,legacy=True)

    @app.post("/api/v1/comparisons")
    def create_comparison(request:Request,background:BackgroundTasks,body:M.ComparisonCreate):
        p=identity(request);b=body.model_dump()
        result=command(request,p,None,b,lambda c:service.comparison_create(c,p,b))
        if body.execution_profile=="reference":background.add_task(service.drive_comparison,result["comparison_id"])
        return respond(request,p,result,status=202)

    @app.post("/api/v1/comparisons/attach")
    def attach_comparison(request:Request,body:M.ComparisonAttach):
        p=identity(request);b=body.model_dump()
        return respond(request,p,command(request,p,None,b,lambda c:service.comparison_attach(c,p,b)),status=201)

    @app.get("/api/v1/comparisons/{gid}")
    def comparison(request:Request,gid:str):
        p=identity(request)
        with service.store.connect() as c:return respond(request,p,service.comparison_view(c,p,gid))

    @app.post("/internal/v1/runs/{r}/events")
    def external_event(request:Request,r:str,body:M.ExternalEvent):
        p=identity(request);b=body.model_dump()
        return respond(request,p,command(request,p,r,b,lambda c:service.ingest_event(c,p,r,b)))

    @app.get("/api/v1/runs/{r}/events/export")
    def export(request:Request,r:str,format:str="jsonl"):
        p=identity(request)
        require(format=="jsonl","QUERY_INVALID","Chỉ hỗ trợ jsonl",422)
        with service.store.connect() as c:
            service.scope(c,p,r,roles={"seller","orchestrator","evaluator","data_admin"})
            # Freeze the upper cursor; subsequent events belong to the next export.
            end=c.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE run_id=?",(r,)).fetchone()[0]
        def stream():
            cursor=0
            while cursor<end:
                with service.store.connect() as c:rows,next_cursor,more=service.events(c,p,r,cursor,100)
                for row in rows:
                    if row["seq"]<=end:yield dumps(row)+"\n"
                if next_cursor<=cursor:break
                cursor=next_cursor
        return StreamingResponse(stream(),media_type="application/x-ndjson",headers={"Content-Disposition":f'attachment; filename="events-{r}.jsonl"',"Cache-Control":"private, no-store"})
