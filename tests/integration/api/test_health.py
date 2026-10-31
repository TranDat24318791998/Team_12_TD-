"""Kiểm thử HTTP qua ứng dụng FastAPI thực."""

from fastapi.testclient import TestClient
import pytest

from app.core.settings import Settings
from app.main import create_app


@pytest.fixture
def offline_settings(monkeypatch):
    monkeypatch.setattr('app.core.settings.Settings', lambda: Settings(_env_file=None, llm_mode='offline', media_mode='offline'))


def test_health_and_static_page(tmp_path, offline_settings):
    app = create_app(home=tmp_path)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="root"' in page.text
        assert 'type="module"' in page.text
        assert client.get("/js/app.js").status_code == 200
        assert client.get("/css/app.css").status_code == 200
        for name in ("demo", "updated", "night", "proof"):
            assert client.get(f"/{name}.html").status_code == 200


def test_static_serving_does_not_depend_on_working_directory(tmp_path, monkeypatch, offline_settings):
    monkeypatch.chdir(tmp_path)
    app = create_app(home=tmp_path/'data')
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/media/replay/.gitkeep").status_code == 200
        assert client.get("/media/missing.mp4").status_code == 404


def test_app_instances_keep_runtime_state_separate(tmp_path, offline_settings):
    first = create_app(home=tmp_path/'first')
    second = create_app(home=tmp_path/'second')
    first.state.session_marker = "first"
    assert not hasattr(second.state, "session_marker")
    with TestClient(second) as client:
        assert client.get("/health").json() == {"ok": True}
