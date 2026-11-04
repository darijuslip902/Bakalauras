import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect, init_db
from app.main import create_app
from app.routes.issues import get_database_path
from app.services import bug_report_service
from app.services.bug_report_service import create_bug_report, update_status
from tests.auth_utils import csrf_token, login, use_test_auth


class DashboardApp:
    """Prisijungęs programuotojas su laikina SQLite DB."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = connect(db_path)
        init_db(self.conn)
        app = create_app()
        app.dependency_overrides[get_database_path] = lambda: db_path
        use_test_auth(app)
        self.client = TestClient(app)
        login(self.client)
        self.csrf_token = csrf_token(self.client)

    def add(self, title: str, description: str = "Aprašymas", **labels: str) -> int:
        report_id = create_bug_report(self.conn, title, description)
        with self.conn:
            for column, value in labels.items():
                assert column in {"status", "category_label", "priority_label", "complexity_label"}
                self.conn.execute(f"UPDATE bug_reports SET {column} = ? WHERE id = ?", (value, report_id))
        return report_id

    def row(self, report_id: int) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM bug_reports").fetchone()[0]

    def change_status(self, report_id: int, status: str, token: str | None = None, follow: bool = False):
        data = {"status": status, "csrf_token": self.csrf_token if token is None else token}
        return self.client.post(
            f"/dashboard/reports/{report_id}/status", data=data, follow_redirects=follow
        )


@pytest.fixture
def dash(tmp_path: Path) -> Iterator[DashboardApp]:
    app = DashboardApp(tmp_path / "dashboard.sqlite3")
    yield app
    app.conn.close()


def _listed_titles(html: str, titles: list[str]) -> set[str]:
    return {title for title in titles if f">{title}</a>" in html}


# --- Sąrašas ---------------------------------------------------------------


def test_dashboard_lists_all_reports_with_fields(dash: DashboardApp) -> None:
    first = dash.add("Neveikia prisijungimas")
    second = dash.add(
        "Lėtas puslapis",
        category_label="performance",
        priority_label="P1_high",
        complexity_label="medium",
        status="resolved",
    )

    html = dash.client.get("/dashboard").text

    assert f'href="/dashboard/reports/{first}">Neveikia prisijungimas</a>' in html
    assert f'href="/dashboard/reports/{second}">Lėtas puslapis</a>' in html
    assert f"#{first}" in html
    assert "Rasta pranešimų: <strong>2</strong>" in html
    assert "Dar nenustatyta" in html  # pirmas įrašas be žymų
    assert "Našumas" in html and "P1 – aukštas" in html and "Vidutinis" in html
    assert 'class="badge status-new">Nauja' in html
    assert 'class="badge status-resolved">Išspręsta' in html
    assert " UTC" in html


def test_dashboard_without_reports_shows_empty_message(dash: DashboardApp) -> None:
    assert "Pranešimų dar nėra" in dash.client.get("/dashboard").text


def test_dashboard_does_not_invent_labels(dash: DashboardApp) -> None:
    report_id = dash.add("Klaida be žymų")

    dash.client.get("/dashboard")
    dash.client.get(f"/dashboard/reports/{report_id}")

    row = dash.row(report_id)
    assert (row["category_label"], row["priority_label"], row["complexity_label"]) == (None, None, None)


# --- Paieška ir filtrai ----------------------------------------------------


@pytest.fixture
def filter_data(dash: DashboardApp) -> list[str]:
    dash.add("Mygtukas neveikia", "Paspaudus nieko neįvyksta", category_label="ui", priority_label="P2_medium")
    dash.add("Duomenų bazės klaida", "Lentelė ŠVIESA neranda įrašų", category_label="database_data",
             complexity_label="high", status="in_progress")
    dash.add("Saugumo spraga", "Galima apeiti 100% patikrą", category_label="security",
             priority_label="P0_critical", complexity_label="high", status="resolved")
    dash.add("Nežinoma klaida", "Kažkas sugedo")
    return ["Mygtukas neveikia", "Duomenų bazės klaida", "Saugumo spraga", "Nežinoma klaida"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", {"Mygtukas neveikia", "Duomenų bazės klaida", "Saugumo spraga", "Nežinoma klaida"}),
        ("q=mygtukas", {"Mygtukas neveikia"}),  # pavadinime, kitokio dydžio raidės
        ("q=šviesa", {"Duomenų bazės klaida"}),  # aprašyme, lietuviškos raidės
        ("q=100%25", {"Saugumo spraga"}),  # % ieškomas kaip paprastas simbolis
        ("q=_", set()),
        ("q=klaida", {"Duomenų bazės klaida", "Nežinoma klaida"}),
        ("status=new", {"Mygtukas neveikia", "Nežinoma klaida"}),
        ("status=resolved", {"Saugumo spraga"}),
        ("category=ui", {"Mygtukas neveikia"}),
        ("category=unset", {"Nežinoma klaida"}),
        ("priority=P0_critical", {"Saugumo spraga"}),
        ("priority=unset", {"Duomenų bazės klaida", "Nežinoma klaida"}),
        ("complexity=high", {"Duomenų bazės klaida", "Saugumo spraga"}),
        ("complexity=unset", {"Mygtukas neveikia", "Nežinoma klaida"}),
        ("complexity=high&status=in_progress", {"Duomenų bazės klaida"}),
        ("q=klaida&category=unset", {"Nežinoma klaida"}),
    ],
)
def test_search_and_filters(dash: DashboardApp, filter_data: list[str], query: str, expected: set[str]) -> None:
    response = dash.client.get(f"/dashboard?{query}")

    assert response.status_code == 200
    assert _listed_titles(response.text, filter_data) == expected
    assert f"Rasta pranešimų: <strong>{len(expected)}</strong>" in response.text


def test_filters_keep_selected_values(dash: DashboardApp, filter_data: list[str]) -> None:
    html = dash.client.get("/dashboard?q=mygtukas&status=new&category=ui").text

    assert 'value="mygtukas"' in html
    assert '<option value="new" selected>' in html
    assert '<option value="ui" selected>' in html
    assert "Išvalyti" in html


def test_invalid_filter_value_is_ignored_with_message(dash: DashboardApp, filter_data: list[str]) -> None:
    response = dash.client.get("/dashboard?status=deleted&category=' OR 1=1 --")

    assert response.status_code == 200
    assert "Neteisinga filtro reikšmė" in response.text
    assert _listed_titles(response.text, filter_data) == set(filter_data)


def test_filters_require_login(dash: DashboardApp) -> None:
    anonymous = TestClient(dash.client.app)

    response = anonymous.get("/dashboard?status=new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fdashboard%3Fstatus%3Dnew"


# --- Detalės ---------------------------------------------------------------


def test_report_detail_shows_all_fields(dash: DashboardApp) -> None:
    report_id = dash.add(
        "Neveikia eksportas",
        "Pirma eilutė\nAntra eilutė",
        category_label="backend_api",
        complexity_label="low",
    )

    response = dash.client.get(f"/dashboard/reports/{report_id}")

    assert response.status_code == 200
    html = response.text
    assert f"#{report_id}" in html
    assert "Neveikia eksportas" in html
    assert "Pirma eilutė\nAntra eilutė" in html
    assert 'class="badge status-new">Nauja' in html
    assert "Serveris / API" in html  # kategorija
    assert "Mažas" in html  # sudėtingumas
    assert "Dar nenustatyta" in html  # prioritetas
    assert "Neišspręsta" in html
    for label in ("Sukurta", "Atnaujinta", "Išspręsta", "Kategorija", "Sudėtingumas", "Prioritetas"):
        assert f"<dt>{label}</dt>" in html
    assert 'name="csrf_token"' in html


def test_missing_report_returns_404(dash: DashboardApp) -> None:
    response = dash.client.get("/dashboard/reports/999")

    assert response.status_code == 404
    assert "Pranešimas nerastas" in response.text


# --- Būsenų keitimas -------------------------------------------------------


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Valdomas laikas, kad būtų galima patikrinti updated_at / resolved_at."""
    times = [f"2026-11-0{day}T10:00:00+00:00" for day in range(1, 10)]
    monkeypatch.setattr(bug_report_service, "_utc_now", lambda: times.pop(0))
    return times


def test_status_change_updates_timestamps_and_keeps_history(dash: DashboardApp, clock: list[str]) -> None:
    report_id = dash.add("Klaida")  # sukurta 11-01
    assert dash.row(report_id)["created_at"] == "2026-11-01T10:00:00+00:00"

    response = dash.change_status(report_id, "in_progress")  # 11-02
    assert response.status_code == 303
    assert response.headers["location"] == f"/dashboard/reports/{report_id}?message=status_updated"
    row = dash.row(report_id)
    assert (row["status"], row["updated_at"], row["resolved_at"]) == (
        "in_progress", "2026-11-02T10:00:00+00:00", None)

    page = dash.change_status(report_id, "resolved", follow=True)  # 11-03
    assert "Būsena sėkmingai pakeista" in page.text
    row = dash.row(report_id)
    assert row["status"] == "resolved"
    assert row["updated_at"] == row["resolved_at"] == "2026-11-03T10:00:00+00:00"
    assert row["created_at"] == "2026-11-01T10:00:00+00:00"

    # Išspręsta klaida lieka DB ir sąraše.
    assert dash.count() == 1
    assert "Klaida</a>" in dash.client.get("/dashboard?status=resolved").text

    dash.change_status(report_id, "new")  # 11-04: atidaroma iš naujo
    row = dash.row(report_id)
    assert (row["status"], row["updated_at"], row["resolved_at"]) == (
        "new", "2026-11-04T10:00:00+00:00", None)


def test_same_status_is_reported_and_not_changed(dash: DashboardApp, clock: list[str]) -> None:
    report_id = dash.add("Klaida")
    before = dict(dash.row(report_id))

    page = dash.change_status(report_id, "new", follow=True)

    assert "Būsena nepakeista" in page.text
    assert dict(dash.row(report_id)) == before


@pytest.mark.parametrize("status", ["", "deleted", "closed", "RESOLVED", "new'; DROP TABLE bug_reports; --"])
def test_invalid_status_is_rejected(dash: DashboardApp, status: str) -> None:
    report_id = dash.add("Klaida")
    before = dict(dash.row(report_id))

    response = dash.change_status(report_id, status)

    assert response.status_code == 400
    assert "Neleistina būsena" in response.text
    assert dict(dash.row(report_id)) == before


@pytest.mark.parametrize("token", ["", "neteisingas"])
def test_status_change_requires_csrf_token(dash: DashboardApp, token: str) -> None:
    report_id = dash.add("Klaida")

    response = dash.change_status(report_id, "resolved", token=token)

    assert response.status_code == 403
    assert "CSRF" in response.text
    assert dash.row(report_id)["status"] == "new"


def test_status_change_requires_login(dash: DashboardApp) -> None:
    report_id = dash.add("Klaida")
    anonymous = TestClient(dash.client.app)

    response = anonymous.post(
        f"/dashboard/reports/{report_id}/status",
        data={"status": "resolved", "csrf_token": dash.csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
    assert dash.row(report_id)["status"] == "new"


def test_status_change_for_missing_report_returns_404(dash: DashboardApp) -> None:
    assert dash.change_status(999, "resolved").status_code == 404


def test_update_status_service_validates_input(dash: DashboardApp) -> None:
    report_id = dash.add("Klaida")

    with pytest.raises(ValueError):
        update_status(dash.conn, report_id, "deleted")
    with pytest.raises(LookupError):
        update_status(dash.conn, 999, "resolved")


def test_database_rejects_invalid_status_directly(dash: DashboardApp) -> None:
    report_id = dash.add("Klaida")

    with pytest.raises(sqlite3.IntegrityError):
        dash.conn.execute("UPDATE bug_reports SET status = 'deleted' WHERE id = ?", (report_id,))


# --- Saugumas ir viešos dalies atskyrimas ---------------------------------


def test_user_text_is_escaped_in_list_and_detail(dash: DashboardApp) -> None:
    script = "<script>alert('xss')</script>"
    report_id = dash.add(script, script + '<img src=x onerror="alert(1)">')

    for path in ("/dashboard", f"/dashboard/reports/{report_id}", f"/dashboard?q={script}"):
        html = dash.client.get(path).text
        assert script not in html, path
        assert "<img src=x" not in html, path
        assert "&lt;script&gt;" in html, path


def test_public_report_appears_in_internal_list(dash: DashboardApp) -> None:
    public = TestClient(dash.client.app)

    response = public.post("/report", data={"title": "Iš viešos formos", "description": "Tekstas"})
    assert response.status_code == 200
    assert "Pranešimas gautas" in response.text
    assert public.get("/dashboard", follow_redirects=False).status_code == 303

    assert "Iš viešos formos</a>" in dash.client.get("/dashboard").text
