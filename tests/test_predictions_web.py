"""5C: automatinis klasifikavimas svetainėje – pateikimas, išsaugojimas, rodymas, perklasifikavimas.

Naudojami maži laikini modeliai (`tests/test_prediction_service.make_models`), jokių DI API užklausų.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routes import reports
from app.routes.issues import get_database_path, get_predictor
from app.services import prediction_service
from app.services.prediction_service import FIELDS, Predictor
from tests.auth_utils import csrf_token, login, use_test_auth
from tests.test_prediction_service import UI_TEXT, make_models

TITLE = "Page layout broken"


class Site:
    def __init__(self, db_path: Path, models_dir: Path) -> None:
        self.db_path = db_path
        self.predictor = Predictor(models_dir)
        app = create_app()
        app.dependency_overrides[get_database_path] = lambda: db_path
        app.dependency_overrides[get_predictor] = lambda: self.predictor
        use_test_auth(app)
        self.app = app
        self.client = TestClient(app)

    def submit(self, title: str = TITLE, description: str = UI_TEXT):
        return self.client.post("/report", data={"title": title, "description": description},
                                follow_redirects=False)

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        if not self.db_path.exists():  # nesėkmingas pateikimas DB dar nesukuria
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def staff(self) -> TestClient:
        client = TestClient(self.app)
        assert login(client).status_code == 303
        return client


@pytest.fixture
def site(tmp_path: Path) -> Site:
    return Site(tmp_path / "web.sqlite3", make_models(tmp_path / "models"))


@pytest.fixture
def site_without_models(tmp_path: Path) -> Site:
    return Site(tmp_path / "web.sqlite3", tmp_path / "no-models-here")


def test_new_report_is_classified_and_saved_separately(site: Site) -> None:
    response = site.submit()

    assert response.status_code == 303 and response.headers["location"] == "/report/submitted"
    runs = {row["field"]: row for row in site.query("SELECT * FROM prediction_runs")}
    assert set(runs) == set(FIELDS) and all(row["status"] == "ok" for row in runs.values())
    assert runs["category_label"]["predicted_label"] == "ui"
    assert all(row["bug_report_id"] == 1 and row["model_version"] == "test-v1" for row in runs.values())
    report = site.query("SELECT * FROM bug_reports")[0]
    assert report["status"] == "new"
    # Prognozė nerašoma į žmogaus patvirtintų žymų stulpelius.
    assert (report["category_label"], report["complexity_label"], report["priority_label"]) == (None, None, None)


def test_customer_does_not_see_predictions(site: Site) -> None:
    response = site.client.post("/report", data={"title": TITLE, "description": UI_TEXT})

    assert response.status_code == 200 and "Pranešimas gautas" in response.text
    for hidden in ("Naudotojo sąsaja", "Modelio įvertis", "Automatinė klasifikacija"):
        assert hidden not in response.text


def test_report_is_saved_when_models_are_missing(site_without_models: Site) -> None:
    response = site_without_models.submit()

    assert response.status_code == 303
    assert len(site_without_models.query("SELECT * FROM bug_reports")) == 1
    runs = site_without_models.query("SELECT status, message FROM prediction_runs")
    assert [row["status"] for row in runs] == ["model_unavailable"] * 3
    assert all("train_models" in row["message"] for row in runs)


def test_report_is_saved_even_if_classification_crashes(site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("netikėta klaida")

    monkeypatch.setattr(reports, "classify_report", boom)

    response = site.submit()

    assert response.status_code == 303
    assert len(site.query("SELECT * FROM bug_reports")) == 1
    assert site.query("SELECT * FROM prediction_runs") == []


def test_invalid_report_is_not_classified(site: Site) -> None:
    response = site.submit(title="", description="")

    assert response.status_code == 400
    assert site.query("SELECT * FROM bug_reports") == [] and site.query("SELECT * FROM prediction_runs") == []


def test_detail_page_hides_scores_from_main_view_but_keeps_them_in_technical_section(site: Site) -> None:
    site.submit()
    staff = site.staff()

    html = staff.get("/dashboard/reports/1").text

    main, technical = html.split('<details class="tech">', 1)[0], html.split('<details class="tech">', 1)[1]
    assert "Automatinė prognozė" in main and "Naudotojo sąsaja" in main
    assert "Laukia patvirtinimo" in main and "Patvirtinta</span>" not in main
    assert "Modelio įvertis" not in main
    score = site.query("SELECT score FROM prediction_runs WHERE field = 'category_label'")[0]["score"]
    assert f"{score:.2f}" not in main and f"{score:.2f}" in technical
    for text in ("Modelio įvertis", "test-v1", "TF-IDF + LogisticRegression"):
        assert text in technical
    assert "nėra kalibruota tikimybė" in html and "negarantuoja tikslumo" in html
    assert "Dar nenustatyta" in html  # patvirtintos žymos dar nėra


@pytest.mark.parametrize(("threshold", "shown", "hidden"), [
    (1.1, "Prognozė apytikslė", "Prognozės nėra"),
    (0.0, "Automatinė prognozė", "Prognozė apytikslė"),
])
def test_detail_page_marks_low_confidence_for_review(site: Site, monkeypatch: pytest.MonkeyPatch,
                                                     threshold: float, shown: str, hidden: str) -> None:
    monkeypatch.setattr(prediction_service, "REVIEW_THRESHOLDS", {field: threshold for field in FIELDS})
    site.submit()

    html = site.staff().get("/dashboard/reports/1").text

    assert shown in html and hidden not in html


def test_detail_page_explains_missing_models(site_without_models: Site) -> None:
    site_without_models.submit()

    response = site_without_models.staff().get("/dashboard/reports/1")

    assert response.status_code == 200
    assert "Prognozės nėra" in response.text and "category_label.joblib nerastas" in response.text


def test_detail_page_without_any_run_offers_classification(site: Site) -> None:
    site.submit()  # senas įrašas be prognozių: ištriname prognozes
    with sqlite3.connect(site.db_path) as conn:
        conn.execute("DELETE FROM prediction_runs")

    html = site.staff().get("/dashboard/reports/1").text

    assert "dar nebuvo paleista" in html and "Klasifikuoti iš naujo" in html


def test_dashboard_shows_auto_label_and_filters_by_it(site: Site) -> None:
    site.submit()
    site.submit("Other", "server endpoint api request response")  # kita kategorija: backend_api
    staff = site.staff()

    listing = staff.get("/dashboard").text
    filtered = staff.get("/dashboard?category=ui").text

    assert "Naudotojo sąsaja" in listing
    assert 'class="badge auto"' not in listing and listing.count("Laukia patvirtinimo") == 2
    assert f">{TITLE}</a>" in filtered
    assert "Rasta pranešimų: <strong>1</strong>" in filtered
    assert "Rasta pranešimų: <strong>0</strong>" in staff.get("/dashboard?category=security").text
    assert "Rasta pranešimų: <strong>1</strong>" in staff.get("/dashboard?category=backend_api").text


def test_confirmed_label_takes_precedence_in_dashboard(site: Site) -> None:
    site.submit()
    with sqlite3.connect(site.db_path) as conn:
        conn.execute("UPDATE bug_reports SET category_label = 'security'")
    staff = site.staff()

    assert "Rasta pranešimų: <strong>1</strong>" in staff.get("/dashboard?category=security").text
    assert "Rasta pranešimų: <strong>0</strong>" in staff.get("/dashboard?category=ui").text
    assert "Saugumas" in staff.get("/dashboard/reports/1").text


def test_reclassify_adds_new_run_and_keeps_history(site: Site) -> None:
    site.submit()
    staff = site.staff()
    token = csrf_token(staff, "/dashboard/reports/1")

    response = staff.post("/dashboard/reports/1/classify", data={"csrf_token": token}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/reports/1?message=classified"
    assert len(site.query("SELECT * FROM prediction_runs")) == 6
    assert "Automatinė klasifikacija atnaujinta." in staff.get(response.headers["location"]).text


def test_reclassify_works_after_models_appear(site_without_models: Site, tmp_path: Path) -> None:
    site_without_models.submit()
    make_models(site_without_models.predictor.models_dir)  # modeliai sukurti vėliau
    staff = site_without_models.staff()
    token = csrf_token(staff, "/dashboard/reports/1")

    staff.post("/dashboard/reports/1/classify", data={"csrf_token": token})

    assert "Naudotojo sąsaja" in staff.get("/dashboard/reports/1").text


def test_reclassify_requires_login_csrf_and_existing_report(site: Site) -> None:
    site.submit()

    anonymous = site.client.post("/dashboard/reports/1/classify", data={"csrf_token": "x"},
                                 follow_redirects=False)
    assert anonymous.status_code == 303 and anonymous.headers["location"].startswith("/login")

    staff = site.staff()
    assert staff.post("/dashboard/reports/1/classify", data={"csrf_token": "bloga"}).status_code == 403
    token = csrf_token(staff, "/dashboard/reports/1")
    assert staff.post("/dashboard/reports/999/classify", data={"csrf_token": token}).status_code == 404
    assert len(site.query("SELECT * FROM prediction_runs")) == 3  # nieko nepridėta


def test_predictions_are_not_public(site: Site) -> None:
    site.submit()

    response = site.client.get("/dashboard/reports/1", follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_status_change_keeps_prediction(site: Site) -> None:
    site.submit()
    staff = site.staff()
    token = csrf_token(staff, "/dashboard/reports/1")

    staff.post("/dashboard/reports/1/status", data={"status": "resolved", "csrf_token": token})

    assert site.query("SELECT status FROM bug_reports")[0]["status"] == "resolved"
    assert len(site.query("SELECT * FROM prediction_runs")) == 3
    assert "Naudotojo sąsaja" in staff.get("/dashboard/reports/1").text
