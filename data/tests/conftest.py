"""Isolated local database and authenticated clients; never calls providers."""
import pytest
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from fastapi.testclient import TestClient
from growth_data.api import create_app
from growth_data.service import Principal
from growth_data.storage import one


_http_coverage={}
_passed=[]
_samples={}


def pytest_addoption(parser):
    parser.addoption("--gate-a-report",default=None,help="Write a sanitized HTTP route/acceptance report")


def pytest_sessionstart(session):
    output=session.config.getoption("--gate-a-report")
    if output:
        path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({"gate_a":"RUNNING","gate_b":"PENDING"})+"\n")


@pytest.fixture(scope="session",autouse=True)
def track_http_contracts():
    original=TestClient.request
    def request(self,method,url,*args,**kwargs):
        response=original(self,method,url,*args,**kwargs)
        path=urlsplit(str(url)).path
        for route in self.app.routes:
            template=getattr(route,"path","")
            if method.upper() not in (getattr(route,"methods",None) or set()):continue
            pattern=re.sub(r"\{[^}]+\}","[^/]+",template)
            if re.fullmatch(pattern,path):
                key=method.upper()+" "+template
                _http_coverage.setdefault(key,set()).add(response.status_code)
                if 200<=response.status_code<300 and key not in _samples:
                    _samples[key]=(self.app,str(url),args,dict(kwargs))
                break
        return response
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(TestClient,"request",request)
        yield


def pytest_runtest_logreport(report):
    if report.when=="call" and report.passed:_passed.append(report.nodeid)


def pytest_sessionfinish(session,exitstatus):
    output=session.config.getoption("--gate-a-report")
    if not output:return
    with TemporaryDirectory(prefix="growth-gate-inventory-") as home:
        schema=create_app(home).openapi()
    expected={method.upper()+" "+path for path,methods in schema["paths"].items() for method in methods if method in {"get","post","put","patch","delete"}}
    missing=sorted(key for key in expected if not any(200<=status<300 for status in _http_coverage.get(key,set())))
    catalog=json.loads((Path(__file__).parents[1]/"api_catalog.json").read_text())["operations"]
    catalog_paths={row["method"]+" "+row["path"] for row in catalog}
    auth_failures=[];auth_checked=0;role_checked=0
    all_roles=set().union(*(set(row["roles"]) for row in catalog))
    for row in catalog:
        key=row["method"]+" "+row["path"]
        if row["public"] or key not in _samples:continue
        application,url,args,kwargs=_samples[key]
        # Replay a known-valid shape with invalid identity. No business writes
        # should execute; not accepting 422 prevents schema errors hiding ACL bugs.
        kwargs={**kwargs,"headers":{k:v for k,v in (kwargs.get("headers") or {}).items() if k.lower()!="authorization"}}
        kwargs["headers"]["Authorization"]="Bearer invalid-fixture-token"
        with TestClient(application) as anonymous:
            response=anonymous.request(row["method"],url,*args,**kwargs)
            auth_checked+=1
            if response.status_code!=401:auth_failures.append({"api":row["id"],"case":"invalid_bearer","status":response.status_code})
            disallowed=sorted(all_roles-set(row["roles"]))
            if disallowed:
                token=application.state.service.issue_token(disallowed[0],runs=("*",),shops=("*",),jobs=("*",))
                kwargs["headers"]["Authorization"]="Bearer "+token
                response=anonymous.request(row["method"],url,*args,**kwargs)
                role_checked+=1
                if response.status_code not in {403,404}:auth_failures.append({"api":row["id"],"case":"disallowed_role","role":disallowed[0],"status":response.status_code})
    passed=exitstatus==0 and not missing and not auth_failures and catalog_paths==expected
    report={"gate_a":"PASS" if passed else "FAIL","gate_b":"PENDING","source":"isolated HTTP fixtures; no paid providers","operations":len(expected),"catalog_matches_openapi":catalog_paths==expected,"covered_successfully":len(expected)-len(missing),"missing_success_cases":missing,"invalid_bearer_cases":auth_checked,"disallowed_role_cases":role_checked,"auth_failures":auth_failures,"tests_passed":len(_passed),"tests":_passed,"http_statuses":{key:sorted(value) for key,value in sorted(_http_coverage.items()) if key in expected}}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    if not passed and exitstatus==0:session.exitstatus=1


@pytest.fixture
def app(tmp_path):return create_app(tmp_path/"runtime")


@pytest.fixture
def client(app):
    with TestClient(app) as client:yield client


@pytest.fixture
def service(app):return app.state.service


@pytest.fixture
def run(client):
    result=client.get("/api/state")
    assert result.status_code==200,result.text
    return result.json()["run_id"]


def headers(token,key="test"):
    return {"Authorization":"Bearer "+token,"Idempotency-Key":key,"X-Request-ID":"pytest"}


def role(service,r,name,shops=("D",)):
    return service.issue_token(name,runs=(r,),shops=shops)
