from fastapi.testclient import TestClient
from conftest import headers,role


def test_health_bootstrap_and_openapi(client):
    assert client.get("/health").json()["storage"]=="sqlite_local"
    assert client.get("/api/v1/runs/missing").status_code==401
    response=client.get("/api/state")
    assert response.status_code==200 and "HttpOnly" in response.headers["set-cookie"]
    schema=client.get("/openapi.json")
    assert schema.status_code==200
    assert "/api/v1/runs/{r}/decisions" in schema.json()["paths"]


def test_platform_and_shop_projections(client,service,run):
    platform=role(service,run,"platform_agent",("*",))
    result=client.get(f"/api/v1/runs/{run}/shops/D/context",headers=headers(platform))
    assert result.status_code==200,result.text
    text=result.text
    for secret in ("unit_cost","min_profit_per_unit","private_evaluation","owner_name","persona","noise"):
        assert secret not in text
    for resource in ("costs","rules","inventory","rule-questions"):
        assert client.get(f"/api/v1/runs/{run}/shops/D/{resource}",headers=headers(platform)).status_code==403
    shop=role(service,run,"shop_agent")
    private=client.get(f"/api/v1/runs/{run}/shops/D/context",headers=headers(shop)).json()["data"]
    assert private["private"]["unit_cost"]==115000
    assert client.get(f"/api/v1/runs/{run}/shops/A/costs",headers=headers(shop)).status_code==404
    assert client.get(f"/api/v1/runs/{run}/market/observations",headers=headers(shop)).status_code==403


def test_session_and_run_isolation(app,client,service,run):
    with TestClient(app) as other:
        r2=other.get("/api/state").json()["run_id"]
        assert r2!=run
        assert other.get(f"/api/v1/runs/{run}").status_code==404
        token=role(service,run,"shop_agent")
        assert other.get(f"/api/v1/runs/{r2}/shops/D/context",headers=headers(token)).status_code==404


def test_future_data_and_bound_cursor(client,service,run):
    token=role(service,run,"platform_agent",("*",));h=headers(token)
    assert client.get(f"/api/v1/runs/{run}/market/observations?to_date=2026-11-07",headers=h).status_code==422
    result=client.get(f"/api/v1/runs/{run}/shops/D/metrics?limit=2",headers=h).json()
    assert len(result["data"])==2
    cursor=result["meta"]["next_cursor"]
    second=client.get(f"/api/v1/runs/{run}/shops/D/metrics",params={"limit":2,"cursor":cursor},headers=h).json()
    assert second["data"]!=result["data"]
    assert client.get(f"/api/v1/runs/{run}/shops/A/metrics",params={"cursor":cursor},headers=h).status_code==422
    assert client.get(f"/api/v1/runs/{run}/shops/D/metrics?limit=1000",headers=h).status_code==422


def test_idempotency_and_csrf(client,run):
    first=client.post("/api/day/start",json={},headers={"Idempotency-Key":"start"})
    assert first.status_code==200,first.text
    assert client.post("/api/day/start",json={},headers={"Idempotency-Key":"start"}).json()==first.json()
    assert client.post("/api/day/start",json={"actor":"admin"},headers={"Idempotency-Key":"start"}).status_code==409
    assert client.post("/api/reset",json={},headers={"Idempotency-Key":"csrf","Origin":"https://evil.example"}).status_code==403
    assert client.post("/api/reset",json={}).status_code==400


def test_body_cannot_authorize_role(client,service,run):
    token=role(service,run,"platform_agent")
    response=client.post(f"/api/v1/runs/{run}/decisions",json={"target_type":"proposal","target_id":"made_up","target_version":1,"action":"approve","actor":"seller"},headers=headers(token))
    assert response.status_code==422
    assert "actor" not in response.json().get("data",{})


def test_event_scanned_cursor_advances_over_invisible(service,client,run):
    with service.store.connect(write=True) as c:
        service.event(c,run,1,"code_check","orchestrator","D",{"unit_cost":115000},visibility="shop_private")
        service.event(c,run,1,"opportunity","platform_agent",payload={"chosen":["D"]})
    token=role(service,run,"platform_agent",("*",))
    first=client.get(f"/api/v1/runs/{run}/events?limit=1",headers=headers(token)).json()
    assert first["data"]==[] and first["meta"]["next_cursor"]==1 and first["meta"]["has_more"]
    second=client.get(f"/api/v1/runs/{run}/events?after_seq=1",headers=headers(token)).json()
    assert len(second["data"])==1 and "unit_cost" not in str(second)
