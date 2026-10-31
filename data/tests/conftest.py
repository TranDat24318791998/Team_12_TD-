"""Isolated local database and authenticated clients; never calls providers."""
import pytest
from fastapi.testclient import TestClient
from growth_data.api import create_app
from growth_data.service import Principal
from growth_data.storage import one


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
