import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routes.issues import get_database_path, get_github_transport
from tests.test_github_client import make_issue


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


class ImportApp:
    """Programa su laikina DB ir imituotu GitHub atsakymu (be tinklo)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.headers: dict[str, str] = {}
        self.issues: list[dict] = []
        app = create_app()
        app.dependency_overrides[get_database_path] = lambda: db_path
        app.dependency_overrides[get_github_transport] = lambda: httpx.MockTransport(self._handle)
        self.client = TestClient(app)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, headers=self.headers)
        page = int(request.url.params["page"])
        return httpx.Response(200, json=self.issues if page == 1 else [])

    def post(self, repository: str, limit: str = "10") -> httpx.Response:
        return self.client.post("/import", data={"repository": repository, "limit": limit})

    def issue_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM github_issues").fetchone()[0]
        finally:
            conn.close()


@pytest.fixture
def import_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ImportApp]:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_IMPORT_LIMIT", raising=False)
    yield ImportApp(tmp_path / "routes.sqlite3")


def test_import_page_shows_form(import_app: ImportApp) -> None:
    response = import_app.client.get("/import")

    assert response.status_code == 200
    assert 'name="repository"' in response.text
    assert 'name="limit"' in response.text
    assert "<button" in response.text


def test_import_shows_result_counts(import_app: ImportApp) -> None:
    import_app.issues = [make_issue(1), make_issue(2, pull_request=True), make_issue(3), {"broken": True}]

    response = import_app.post("https://github.com/owner/repo")

    assert response.status_code == 200
    assert "Importo rezultatas: owner/repo" in response.text
    for label, value in [("Importuota naujų", 2), ("Praleista (pull request)", 1), ("Nepavyko", 1)]:
        assert f"<dt>{label}</dt><dd>{value}</dd>" in response.text
    assert import_app.issue_count() == 2


def test_second_import_reports_updates_not_duplicates(import_app: ImportApp) -> None:
    import_app.issues = [make_issue(1), make_issue(2)]

    import_app.post("owner/repo")
    response = import_app.post("owner/repo")

    assert "<dt>Importuota naujų</dt><dd>0</dd>" in response.text
    assert "<dt>Atnaujinta esamų</dt><dd>2</dd>" in response.text
    assert import_app.issue_count() == 2


@pytest.mark.parametrize(
    "repository",
    ["", "owner", "https://evil.example/owner/repo", "http://github.com/owner/repo", "a/b/c"],
)
def test_invalid_repository_is_rejected_without_github_request(import_app: ImportApp, repository: str) -> None:
    response = import_app.post(repository)

    assert response.status_code == 400
    assert "Neteisingas repozitorijos formatas" in response.text
    assert import_app.requests == []


@pytest.mark.parametrize("limit", ["", "0", "-1", "abc", "1.5", "101"])
def test_invalid_limit_is_rejected(import_app: ImportApp, limit: str) -> None:
    response = import_app.post("owner/repo", limit)

    assert response.status_code == 400
    assert "Importo kiekis" in response.text
    assert import_app.requests == []


def test_repository_input_is_html_escaped(import_app: ImportApp) -> None:
    response = import_app.post('"><script>alert(1)</script>')

    assert "<script>alert(1)</script>" not in response.text


@pytest.mark.parametrize(
    ("status", "headers", "expected_status", "expected_text"),
    [
        (404, {}, 404, "Repozitorija nerasta"),
        (403, {"x-ratelimit-remaining": "0"}, 429, "užklausų limitas"),
        (500, {}, 502, "HTTP 500"),
    ],
)
def test_github_errors_are_shown(
    import_app: ImportApp, status: int, headers: dict, expected_status: int, expected_text: str
) -> None:
    import_app.status = status
    import_app.headers = headers

    response = import_app.post("owner/repo")

    assert response.status_code == expected_status
    assert expected_text in response.text
    assert 'role="alert"' in response.text
    assert import_app.issue_count() == 0
