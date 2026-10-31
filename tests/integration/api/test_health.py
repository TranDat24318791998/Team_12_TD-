"""Kiểm thử HTTP qua ứng dụng FastAPI thực."""

from fastapi.testclient import TestClient

from app.main import app, create_app


def test_health_and_static_page():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        page = client.get("/")
        assert page.status_code == 200
        assert "sàn·demo đang dựng" in page.text


def test_static_serving_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/media/replay/.gitkeep").status_code == 200
        assert client.get("/media/missing.mp4").status_code == 404


def test_app_instances_keep_runtime_state_separate():
    first = create_app()
    second = create_app()
    first.state.session_marker = "first"
    assert not hasattr(second.state, "session_marker")
    with TestClient(second) as client:
        assert client.get("/health").json() == {"ok": True}
