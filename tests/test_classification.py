"""5C: programuotojo klasifikacijos patvirtinimas – paslauga ir svetainės forma."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect, init_db
from app.main import create_app
from app.routes.issues import get_database_path, get_predictor
from app.services.bug_report_service import ReportFilters, create_bug_report, list_bug_reports
from app.services.classification_service import (
    confirm_classification,
    confirmation_history,
    form_values,
    is_confirmed,
    validate_classification,
)
from app.services.prediction_service import Predictor, classify_report, latest_predictions
from tests.auth_utils import TEST_USERNAME, csrf_token, login, use_test_auth
from tests.test_prediction_service import UI_TEXT, make_models

GOOD = {"category_label": "security", "complexity_label": "high", "priority_label": "P0_critical"}


@pytest.fixture
def conn(tmp_path: Path):
    connection = connect(tmp_path / "c.sqlite3")
    init_db(connection)
    yield connection
    connection.close()


# --- Paslauga ---------------------------------------------------------------


def test_validation_accepts_all_allowed_values_including_p0() -> None:
    assert validate_classification(GOOD) == {}


@pytest.mark.parametrize("bad", [
    {**GOOD, "category_label": "nezinoma"},
    {**GOOD, "complexity_label": ""},
    {**GOOD, "priority_label": "P9"},
    {"category_label": "ui"},
])
def test_validation_rejects_bad_or_missing_values(bad: dict) -> None:
    assert validate_classification(bad)


def test_confirm_saves_labels_and_history(conn: sqlite3.Connection) -> None:
    report_id = create_bug_report(conn, "T", "D")

    assert confirm_classification(conn, report_id, GOOD, "jonas") is True

    row = conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
    assert (row["category_label"], row["complexity_label"], row["priority_label"]) == tuple(GOOD.values())
    history = confirmation_history(conn, report_id)
    assert len(history) == 1 and history[0]["confirmed_by"] == "jonas" and history[0]["confirmed_at"]
    assert history[0]["previous_category"] is None and is_confirmed(row)


def test_confirm_same_values_creates_no_new_history(conn: sqlite3.Connection) -> None:
    report_id = create_bug_report(conn, "T", "D")
    confirm_classification(conn, report_id, GOOD, "jonas")

    assert confirm_classification(conn, report_id, GOOD, "jonas") is False
    assert len(confirmation_history(conn, report_id)) == 1


def test_correction_keeps_previous_values_in_history(conn: sqlite3.Connection) -> None:
    report_id = create_bug_report(conn, "T", "D")
    confirm_classification(conn, report_id, GOOD, "jonas")
    confirm_classification(conn, report_id, {**GOOD, "priority_label": "P3_low"}, "petras")

    newest, oldest = confirmation_history(conn, report_id)
    assert newest["previous_priority"] == "P0_critical" and newest["priority_label"] == "P3_low"
    assert newest["confirmed_by"] == "petras" and oldest["confirmed_by"] == "jonas"


def test_confirm_rejects_invalid_and_missing_report(conn: sqlite3.Connection) -> None:
    report_id = create_bug_report(conn, "T", "D")
    with pytest.raises(ValueError):
        confirm_classification(conn, report_id, {**GOOD, "category_label": "x"}, "jonas")
    with pytest.raises(LookupError):
        confirm_classification(conn, 999, GOOD, "jonas")
    assert confirmation_history(conn, report_id) == []


def test_history_records_prediction_at_confirmation_time(conn: sqlite3.Connection, tmp_path: Path) -> None:
    report_id = create_bug_report(conn, "Page layout broken", UI_TEXT)
    classify_report(conn, Predictor(make_models(tmp_path / "models")), report_id)

    confirm_classification(conn, report_id, GOOD, "jonas")

    assert confirmation_history(conn, report_id)[0]["predicted_category"] == "ui"


def test_reclassification_never_overwrites_confirmed_labels(conn: sqlite3.Connection, tmp_path: Path) -> None:
    report_id = create_bug_report(conn, "Page layout broken", UI_TEXT)
    confirm_classification(conn, report_id, GOOD, "jonas")

    classify_report(conn, Predictor(make_models(tmp_path / "models")), report_id)

    row = conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
    assert row["category_label"] == "security"  # ML siūlo ui
    assert latest_predictions(conn, report_id)["category_label"]["predicted_label"] == "ui"


def test_form_values_prefer_confirmed_then_prediction(conn: sqlite3.Connection, tmp_path: Path) -> None:
    report_id = create_bug_report(conn, "Page layout broken", UI_TEXT)
    classify_report(conn, Predictor(make_models(tmp_path / "models")), report_id)
    report = conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
    assert form_values(report, latest_predictions(conn, report_id))["category_label"] == "ui"

    confirm_classification(conn, report_id, GOOD, "jonas")
    report = conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
    assert form_values(report, latest_predictions(conn, report_id)) == GOOD


def test_form_values_empty_without_prediction(conn: sqlite3.Connection) -> None:
    report_id = create_bug_report(conn, "T", "D")
    report = conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
    assert form_values(report, {}) == {f: "" for f in GOOD}


def test_confirmed_value_takes_precedence_in_list_filters(conn: sqlite3.Connection, tmp_path: Path) -> None:
    report_id = create_bug_report(conn, "Page layout broken", UI_TEXT)
    classify_report(conn, Predictor(make_models(tmp_path / "models")), report_id)
    confirm_classification(conn, report_id, GOOD, "jonas")

    assert len(list_bug_reports(conn, ReportFilters(category_label="security"))) == 1
    assert list_bug_reports(conn, ReportFilters(category_label="ui")) == []


def test_old_database_gets_new_tables_and_columns(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE prediction_runs (id INTEGER PRIMARY KEY, bug_report_id INTEGER, field TEXT,"
                " status TEXT, predicted_label TEXT, score REAL, needs_review INTEGER, method TEXT,"
                " model_version TEXT, message TEXT, created_at TEXT)")
    raw.commit()
    raw.close()

    connection = connect(path)
    init_db(connection)
    init_db(connection)  # pakartotinis paleidimas saugus
    columns = {r["name"] for r in connection.execute("PRAGMA table_info(prediction_runs)")}
    tables = {r["name"] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert {"input_language", "translation_method"} <= columns
    assert "classification_confirmations" in tables


# --- Svetainė -----------------------------------------------------------------


class Web:
    def __init__(self, tmp_path: Path) -> None:
        self.db_path = tmp_path / "web.sqlite3"
        self.predictor = Predictor(make_models(tmp_path / "models"))
        app = create_app()
        app.dependency_overrides[get_database_path] = lambda: self.db_path
        app.dependency_overrides[get_predictor] = lambda: self.predictor
        use_test_auth(app)
        self.app = app
        self.public = TestClient(app)
        self.staff = TestClient(app)
        assert login(self.staff).status_code == 303

    def submit(self, title: str = "Page layout broken", description: str = UI_TEXT) -> None:
        assert self.public.post("/report", data={"title": title, "description": description},
                                follow_redirects=False).status_code == 303

    def confirm(self, values: dict | None = None, token: str | None = None, client: TestClient | None = None):
        client = client or self.staff
        data = {**(values or GOOD),
                "csrf_token": csrf_token(self.staff, "/dashboard/reports/1") if token is None else token}
        return (client).post("/dashboard/reports/1/classification", data=data, follow_redirects=False)

    def row(self) -> sqlite3.Row:
        conn = connect(self.db_path)
        try:
            return conn.execute("SELECT * FROM bug_reports WHERE id = 1").fetchone()
        finally:
            conn.close()


@pytest.fixture
def web(tmp_path: Path) -> Web:
    return Web(tmp_path)


def test_form_is_prefilled_with_prediction(web: Web) -> None:
    web.submit()

    html = web.staff.get("/dashboard/reports/1").text

    assert "Patvirtinti klasifikaciją" in html and "Laukia patvirtinimo" in html
    assert '<option value="ui" selected>' in html


def test_programmer_confirms_and_sees_confirmed_state(web: Web) -> None:
    web.submit()

    response = web.confirm()

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/reports/1?message=confirmed"
    row = web.row()
    assert (row["category_label"], row["complexity_label"], row["priority_label"]) == tuple(GOOD.values())
    html = web.staff.get(response.headers["location"]).text
    assert "Klasifikacija patvirtinta." in html and 'class="badge state-confirmed">Patvirtinta' in html
    assert f"Patvirtino: {TEST_USERNAME}" in html
    assert '<option value="security" selected>' in html  # forma rodo patvirtintas, ne ML reikšmes
    assert '<option value="ui" selected>' not in html


def test_reclassify_keeps_confirmed_labels_on_site(web: Web) -> None:
    web.submit()
    web.confirm()
    token = csrf_token(web.staff, "/dashboard/reports/1")

    web.staff.post("/dashboard/reports/1/classify", data={"csrf_token": token}, follow_redirects=False)

    assert web.row()["category_label"] == "security"


def test_anonymous_cannot_confirm(web: Web) -> None:
    web.submit()
    anonymous = TestClient(web.app)

    response = web.confirm(token="x", client=anonymous)

    assert response.status_code == 303 and response.headers["location"].startswith("/login")
    assert web.row()["category_label"] is None


def test_confirm_requires_valid_csrf_token(web: Web) -> None:
    web.submit()

    assert web.confirm(token="neteisingas").status_code == 403
    assert web.row()["category_label"] is None


def test_invalid_values_are_rejected_and_resubmitted_form_keeps_input(web: Web) -> None:
    web.submit()

    response = web.confirm({**GOOD, "category_label": "bogus", "priority_label": ""})

    assert response.status_code == 400
    assert "Klasifikacija neišsaugota" in response.text
    assert '<option value="high" selected>' in response.text  # likusios reikšmės išlieka
    assert web.row()["category_label"] is None


def test_confirm_unknown_report_returns_404(web: Web) -> None:
    web.submit()
    token = csrf_token(web.staff, "/dashboard/reports/1")

    response = web.staff.post("/dashboard/reports/99/classification", data={**GOOD, "csrf_token": token})

    assert response.status_code == 404


def test_confirming_same_values_twice_shows_unchanged_message(web: Web) -> None:
    web.submit()
    web.confirm()

    response = web.confirm()

    assert response.headers["location"].endswith("message=confirm_unchanged")


def test_dashboard_shows_one_state_indicator_per_row(web: Web) -> None:
    web.submit()
    before = web.staff.get("/dashboard").text
    assert before.count("Laukia patvirtinimo") == 1 and 'class="badge auto"' not in before

    web.confirm()
    after = web.staff.get("/dashboard").text
    assert after.count('class="badge state-confirmed">Patvirtinta') == 1 and "Laukia patvirtinimo" not in after
    assert "Saugumas" in after


def test_lithuanian_and_english_reports_are_both_classified(web: Web) -> None:
    web.submit("Page layout broken", UI_TEXT)
    web.submit("Mygtukas neveikia", "Paspaudus mygtuką puslapis užstringa ir pasirodo klaida 500.")

    conn = connect(web.db_path)
    try:
        langs = {r["bug_report_id"]: r["input_language"] for r in
                 conn.execute("SELECT bug_report_id, input_language FROM prediction_runs")}
        lt = conn.execute("SELECT title, description FROM bug_reports WHERE id = 2").fetchone()
    finally:
        conn.close()
    assert langs == {1: "en", 2: "lt"}
    assert lt["title"] == "Mygtukas neveikia" and "užstringa" in lt["description"]  # originalas nepakeistas
