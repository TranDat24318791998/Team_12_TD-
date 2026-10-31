"""Artifact availability is distinct from proof of live calls or replay fidelity."""

import hashlib
import json
from conftest import headers
from growth_data.harness import HttpHarness


def test_recording_manifest_requires_ready_scoped_artifacts_and_never_claims_player(client,service):
    h=HttpHarness(client,service.issue_token);h.get("/api/state")
    pair=h.post("/api/v1/comparisons",{})
    r=pair["run_on"];o=h.token(r,"orchestrator")
    response=h.upload(r,o,b"# Fixture response; no provider call\n",kind="document",product=None,purpose="replay_recording")
    exported=h.get(f"/api/v1/runs/{r}/events/export",o)
    cursor=json.loads(exported.splitlines()[-1])["seq"]
    manifest={"version":1,"run_id":r,"source":"fixture","complete":True,"events_through":cursor,"model":"fake-model","prompt_version":"fixture-v1","calls":[{"call_id":"fixture-call-1","request_sha256":hashlib.sha256(b'fixture-request').hexdigest(),"response_asset_id":response}]}
    aid=h.upload(r,o,json.dumps(manifest).encode(),kind="document",product=None,purpose="replay_recording")
    result=h.post(f"/internal/v1/runs/{r}/replay/export",{"recording_asset_id":aid},o)
    assert result["recording"]["manifest"]["source"]=="fixture"
    assert not result["faithful_llm_replay"] and not result["player_available"]
    assert client.get(f"/api/v1/runs/{r}/assets/{response}/download").status_code==404
    learner=h.token(r,"learning_worker","D")
    assert client.get(f"/api/v1/runs/{r}/assets/{response}/download",headers=headers(learner)).status_code==404


def test_trace_url_needs_backend_allowlist_and_seller_scope(client,service,monkeypatch):
    h=HttpHarness(client,service.issue_token)
    r=h.post("/api/reset",{"execution_profile":"external"})["run_id"]
    o=h.token(r,"orchestrator")
    op=h.post(f"/api/v1/runs/{r}/days/start",{"expected_day":1,"expected_version":1},o)
    claim=h.post(f"/internal/v1/runs/{r}/operations/{op['operation_id']}/claim",{"expected_version":op["version"]},o)
    url=f"/internal/v1/runs/{r}/operations/{op['operation_id']}/result"
    body={"expected_version":claim["version"],"status":"running","trace_url":"https://traces.example.test/fixture"}
    assert client.post(url,json=body,headers=headers(o,"unconfigured")).status_code==422
    monkeypatch.setenv("GROWTH_TRACE_HOSTS","traces.example.test")
    internal=h.post(url,body,o)
    assert not h.get("/api/state")["capabilities"]["trace"]
    seller_op=h.get(f"/api/v1/runs/{r}/operations/{op['operation_id']}")
    assert "trace_url" not in seller_op["result"]
    unsafe={**body,"expected_version":internal["version"],"trace_url":"https://traces.example.test/fixture?api_key=hidden"}
    assert client.post(url,json=unsafe,headers=headers(o,"credential-url")).status_code==422
    safe=h.post(url,{**body,"expected_version":internal["version"],"trace_shop_id":"D"},o)
    assert h.get("/api/state")["links"]["trace"]==body["trace_url"]
