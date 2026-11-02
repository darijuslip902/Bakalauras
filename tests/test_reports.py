import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routes.issues import get_database_path
from app.services.bug_report_service import DESCRIPTION_MAX_LENGTH, TITLE_MAX_LENGTH


class ReportApp:
    """Programa su laikina SQLite DB viešos formos testams."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        app = create_app()
        app.dependency_overrides[get_database_path] = lambda: db_path
        self.client = TestClient(app)

    def submit(self, title: str, description: str, follow_redirects: bool = True) -> httpx.Response:
        return self.client.post(
            "/report",
            data={"title": title, "description": description},
            follow_redirects=follow_redirects,
        )

    def rows(self) -> list[sqlite3.Row]:
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute("SELECT * FROM bug_reports ORDER BY id").fetchall()
        finally:
            conn.close()


@pytest.fixture
def report_app(tmp_path: Path) -> ReportApp:
    return ReportApp(tmp_path / "reports.sqlite3")


def test_report_form_is_public(report_app: ReportApp) -> None:
    response = report_app.client.get("/report")

    assert response.status_code == 200
    assert 'name="title"' in response.text
    assert 'name="description"' in response.text
    assert "<button" in response.text


def test_valid_report_is_saved_and_confirmed(report_app: ReportApp) -> None:
    response = report_app.submit("  Neveikia mygtukas  ", "  Paspaudus „Saugoti“ nieko neįvyksta.  ", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/report/submitted"

    confirmation = report_app.client.get(response.headers["location"])
    assert confirmation.status_code == 200
    assert "Pranešimas gautas" in confirmation.text

    rows = report_app.rows()
    assert len(rows) == 1
    assert rows[0]["title"] == "Neveikia mygtukas"
    assert rows[0]["description"] == "Paspaudus „Saugoti“ nieko neįvyksta."


def test_new_report_gets_status_and_timestamps(report_app: ReportApp) -> None:
    report_app.submit("Klaida", "Aprašymas")

    row = report_app.rows()[0]
    assert row["status"] == "new"
    assert row["created_at"]
    assert row["updated_at"] == row["created_at"]
    assert row["resolved_at"] is None
    for label in ("category_label", "complexity_label", "priority_label"):
        assert row[label] is None


def test_windows_line_endings_are_normalized(report_app: ReportApp) -> None:
    report_app.submit("Klaida", "Pirma eilutė\r\nAntra eilutė")

    assert report_app.rows()[0]["description"] == "Pirma eilutė\nAntra eilutė"


@pytest.mark.parametrize(
    ("title", "description", "expected_message"),
    [
        ("", "Aprašymas", "Įveskite klaidos pavadinimą."),
        ("   ", "Aprašymas", "Įveskite klaidos pavadinimą."),
        ("Klaida", "", "Įveskite išsamų klaidos aprašymą."),
        ("Klaida", " \n\t ", "Įveskite išsamų klaidos aprašymą."),
        ("x" * (TITLE_MAX_LENGTH + 1), "Aprašymas", "Pavadinimas per ilgas"),
        ("Klaida", "x" * (DESCRIPTION_MAX_LENGTH + 1), "Aprašymas per ilgas"),
    ],
)
def test_invalid_report_is_rejected_with_clear_message(
    report_app: ReportApp, title: str, description: str, expected_message: str
) -> None:
    response = report_app.submit(title, description)

    assert response.status_code == 400
    assert "Pranešimas neišsiųstas" in response.text
    assert expected_message in response.text
    assert report_app.rows() == []


def test_maximum_lengths_are_accepted(report_app: ReportApp) -> None:
    report_app.submit("x" * TITLE_MAX_LENGTH, "y" * DESCRIPTION_MAX_LENGTH)

    assert len(report_app.rows()) == 1


def test_invalid_form_keeps_entered_values(report_app: ReportApp) -> None:
    response = report_app.submit("Mano pavadinimas", "")

    assert 'value="Mano pavadinimas"' in response.text

    response = report_app.submit("", "Mano aprašymas")

    assert ">Mano aprašymas</textarea>" in response.text


def test_public_routes_do_not_show_other_reports(report_app: ReportApp) -> None:
    report_app.submit("Kito naudotojo slapta klaida", "Kito naudotojo aprašymas")

    pages = [
        report_app.client.get("/"),
        report_app.client.get("/report"),
        report_app.client.get("/report/submitted"),
        report_app.submit("Mano klaida", "Mano aprašymas"),
        report_app.submit("", "Neteisinga forma"),
    ]
    for page in pages:
        assert "Kito naudotojo" not in page.text

    # Viešo sąrašo, detalių ar redagavimo maršrutų nėra.
    for path in ("/reports", "/report/1", "/bug_reports", "/report/1/edit"):
        assert report_app.client.get(path).status_code == 404
    assert report_app.client.post("/report/1", data={"title": "x", "description": "y"}).status_code in (404, 405)
    assert report_app.rows()[0]["title"] == "Kito naudotojo slapta klaida"


def test_html_and_javascript_are_escaped(report_app: ReportApp) -> None:
    script = "<script>alert('xss')</script>"

    response = report_app.submit(script, "")

    assert script not in response.text
    assert "&lt;script&gt;" in response.text

    response = report_app.submit("", "</textarea>" + script)

    assert script not in response.text
    assert "&lt;/textarea&gt;" in response.text

    report_app.submit(script, script)

    # Tekstas išsaugomas pažodžiui, o ne vykdomas ar keičiamas.
    assert report_app.rows()[0]["title"] == script
