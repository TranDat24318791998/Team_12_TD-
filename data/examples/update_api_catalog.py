"""Regenerate the route/role inventory, retaining existing API identifiers."""
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from growth_data.api import create_app


ROOT=Path(__file__).resolve().parents[1]
PRIVATE=set("shop_agent seller simulated_seller orchestrator simulator learning_worker evaluator data_admin".split())
ALL=PRIVATE|set("platform_agent content_worker monitor knowledge_admin".split())
GROUPS={
    "read_run read_events read_download read_document write_complete_upload bytes_upload":ALL,
    "read_state":set("seller orchestrator".split()),
    "read_context":set("platform_agent shop_agent seller simulated_seller orchestrator data_admin".split()),
    "read_shops read_market":set("platform_agent orchestrator data_admin".split()),
    "read_policies":PRIVATE|{"platform_agent","content_worker"},
    "read_summary read_products read_metrics read_history read_campaigns read_forecasts read_proposal":PRIVATE|{"platform_agent"},
    "read_inventory read_costs read_rules read_questions":PRIVATE,
    "read_content read_job":PRIVATE|{"content_worker"},
    "read_learning_input write_learning_result":{"learning_worker"},
    "read_proof write_create_run create_comparison attach_comparison comparison export":set("seller orchestrator evaluator data_admin".split()),
    "read_operation write_start_day write_close_day write_advance_day operations":set("seller orchestrator data_admin".split()),
    "write_reset restore undo":{"seller"},
    "write_checks write_proposal":set("platform_agent shop_agent".split()),
    "write_present write_apply write_negotiation":set("orchestrator data_admin".split()),
    "write_decision write_rules":set("seller simulated_seller".split()),
    "write_pause":set("seller orchestrator monitor".split()),
    "write_content_create control":set("seller orchestrator".split()),
    "write_publish claim result":{"orchestrator"},
    "write_upload":set("seller content_worker learning_worker orchestrator knowledge_admin".split()),
    "write_search":set("platform_agent shop_agent seller content_worker orchestrator learning_worker".split()),
    "write_settle":set("simulator orchestrator data_admin".split()),
    "write_question":set("learning_worker orchestrator".split()),
    "write_content_result":{"content_worker"},
    "write_replay":set("orchestrator evaluator data_admin".split()),
    "write_knowledge_create write_knowledge_revoke":{"knowledge_admin"},
    "night_summary":set("seller shop_agent orchestrator evaluator data_admin".split()),
    "external_event":set("platform_agent shop_agent orchestrator learning_worker".split()),
    "health":set(),
}


def main():
    roles={handler:value for handlers,value in GROUPS.items() for handler in handlers.split()}
    old={}
    for ident,method,path in re.findall(r'^\| (API-\d+) \| `(GET|POST|PUT) ([^`]+)`',(ROOT/'DEMO_DATA_CHECKLIST.md').read_text(),re.M):old[(method,path)]=ident
    catalog=ROOT/'api_catalog.json'
    if catalog.exists():
        for row in json.loads(catalog.read_text())["operations"]:old[(row["method"],row["path"])]=row["id"]
    next_id=max([int(x.split('-')[1]) for x in old.values()]+[61])+1
    rows=[]
    with TemporaryDirectory(prefix="growth-catalog-") as home:
        for route in create_app(home).routes:
            if route.path in {'/openapi.json','/docs','/docs/oauth2-redirect','/redoc'}:continue
            for method in sorted(route.methods & {'GET','POST','PUT','PATCH','DELETE'}):
                ident=old.get((method,route.path))
                if ident is None:ident=f'API-{next_id:03}';next_id+=1
                allowed={'seller'} if route.name.startswith('demo_') else roles[route.name]
                scope=['run'] if '{r}' in route.path else []
                if '{s}' in route.path:scope.append('shop')
                if any(x in route.path for x in ('{pid}','{cid}','{jid}','{aid}')):scope.append('entity_owner_shop')
                if '{jid}' in route.path or route.name in {'read_content','write_upload','bytes_upload','write_complete_upload','read_download'}:scope.append('assigned_job_or_asset_acl')
                if route.name.startswith('demo_') or route.name=='undo':scope=['seller_session','shop_D']
                if 'comparison' in route.name or route.name=='read_proof':scope+=['both_runs','session_or_grant']
                if route.name in {'write_complete_upload','bytes_upload'}:scope.append('upload_owner')
                rows.append({'id':ident,'method':method,'path':route.path,'handler':route.name,'roles':sorted(allowed),'public':route.name=='health','scope':scope})
    rows.sort(key=lambda x:x['id'])
    catalog.write_text(json.dumps({'schema_version':2,'operations':rows},ensure_ascii=False,indent=2)+'\n')
    lines=['# Ma trận quyền Data API v2','','Inventory '+str(len(rows))+' operations. Cột roles là gate vai trò; còn kiểm run/shop/job, visibility, owner, version và state. GET /api/state cho bootstrap seller khi không có credentials; bearer không hợp lệ bị từ chối. Quyền vai trò không cho phép đọc mọi field.','','| ID | Method/path | Vai trò | Scope bổ sung |','| --- | --- | --- | --- |']
    for row in rows:lines.append('| '+row['id']+' | `'+row['method']+' '+row['path']+'` | '+(', '.join(row['roles']) or 'public')+' | '+(', '.join(row['scope']) or 'caller/session or document ACL')+' |')
    lines+=['','Nguồn máy đọc: [api_catalog.json](api_catalog.json). Gate A đối chiếu OpenAPI, yêu cầu ca HTTP thành công cho từng operation; kiểm invalid bearer và vai trò trái quyền từ request hợp lệ. Test scope, field projection, concurrency và fault injection là gate riêng; không suy ra chúng chỉ từ status 2xx.','']
    (ROOT/'API_ACCESS_MATRIX.md').write_text('\n'.join(lines))
    print(f'Catalog: {len(rows)} operations; IDs retained')


if __name__=='__main__':main()
