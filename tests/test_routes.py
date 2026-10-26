from fastapi.testclient import TestClient

from app.main import create_app


def test_app_starts_and_serves_index() -> None:
    # Context manager vykdo programos startup/shutdown ciklą.
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<h1>" in response.text


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
