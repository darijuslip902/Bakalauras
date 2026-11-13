"""5C: vietinių ML modelių įkėlimas, prognozės, saugojimas ir rodymas. Jokių DI API ar tinklo užklausų.

Modeliai šiuose testuose – maži, čia pat išmokyti scikit-learn Pipeline (ne projekto `models/`).
"""

import sqlite3
from pathlib import Path

import joblib
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app import config
from app.db import connect, init_db
from app.ml.data_quality import issue_text
from app.services import prediction_service
from app.services.bug_report_service import UNSET, ReportFilters, create_bug_report, list_bug_reports
from app.services.prediction_service import (
    FIELDS,
    Predictor,
    classify_report,
    default_predictor,
    latest_predictions,
)

# Aiškūs, lengvai atskiriami pavyzdžiai kiekvienai klasei.
TRAINING = {
    "category_label": {
        "ui": "button layout css page rendering screen",
        "backend_api": "server endpoint api request response",
        "database_data": "sql query table migration database",
    },
    "complexity_label": {"low": "typo small trivial simple", "high": "architecture rewrite many components"},
    "priority_label": {"P1_high": "crash outage data loss urgent", "P3_low": "cosmetic minor rare"},
}
UI_TEXT = "The button layout and css rendering on the page are broken"


def make_models(directory: Path, fields: tuple[str, ...] = FIELDS) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for field in fields:
        texts, labels = [], []
        for label, words in TRAINING[field].items():
            for _ in range(4):
                texts.append(words)
                labels.append(label)
        pipeline = Pipeline([("tfidf", TfidfVectorizer()), ("clf", LogisticRegression(max_iter=300))])
        pipeline.fit(texts, labels)
        joblib.dump({"pipeline": pipeline, "field": field, "model_version": "test-v1"}, directory / f"{field}.joblib")
    return directory


@pytest.fixture
def conn(tmp_path: Path):
    connection = connect(tmp_path / "pred.sqlite3")
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def models(tmp_path: Path) -> Path:
    return make_models(tmp_path / "models")


def by_field(predictions) -> dict:
    return {p.field: p for p in predictions}


def test_predictor_returns_valid_labels_scores_and_version(models: Path) -> None:
    predictions = by_field(Predictor(models).predict("Page broken", UI_TEXT))

    assert set(predictions) == set(FIELDS)
    assert all(p.status == "ok" and p.model_version == "test-v1" for p in predictions.values())
    assert predictions["category_label"].label == "ui"
    assert predictions["category_label"].label in config.CATEGORY_LABELS
    assert predictions["complexity_label"].label in config.COMPLEXITY_LABELS
    assert predictions["priority_label"].label in config.PRIORITY_LABELS
    assert all(0 < p.score <= 1 for p in predictions.values())


@pytest.mark.parametrize(("threshold", "expected"), [(1.1, True), (0.0, False)])
def test_review_flag_follows_threshold(models: Path, monkeypatch: pytest.MonkeyPatch, threshold: float,
                                       expected: bool) -> None:
    monkeypatch.setattr(prediction_service, "REVIEW_THRESHOLDS", {field: threshold for field in FIELDS})

    predictions = Predictor(models).predict("Page broken", UI_TEXT)

    assert all(p.needs_review is expected for p in predictions)


def test_missing_models_give_clear_message_and_do_not_raise(tmp_path: Path) -> None:
    predictions = Predictor(tmp_path / "does-not-exist").predict("Title", "Description of the problem")

    assert [p.status for p in predictions] == ["model_unavailable"] * 3
    assert all(p.label is None and p.score is None for p in predictions)
    assert all("train_models" in p.message and p.field in p.message for p in predictions)


def test_one_missing_model_does_not_block_the_others(tmp_path: Path) -> None:
    models = make_models(tmp_path / "partial", ("category_label", "priority_label"))

    predictions = by_field(Predictor(models).predict("Page broken", UI_TEXT))

    assert predictions["category_label"].status == "ok"
    assert predictions["priority_label"].status == "ok"
    assert predictions["complexity_label"].status == "model_unavailable"


def test_corrupt_or_wrong_model_files_are_reported_not_raised(models: Path) -> None:
    (models / "category_label.joblib").write_bytes(b"this is not a joblib file")
    joblib.dump({"pipeline": object(), "field": "complexity_label"}, models / "complexity_label.joblib")

    predictions = by_field(Predictor(models).predict("Page broken", UI_TEXT))

    assert predictions["category_label"].status == "model_unavailable"
    assert "nepavyko įkelti" in predictions["category_label"].message
    assert predictions["complexity_label"].status == "model_unavailable"
    assert predictions["priority_label"].status == "ok"


def test_model_for_another_field_is_rejected(models: Path) -> None:
    (models / "priority_label.joblib").write_bytes((models / "category_label.joblib").read_bytes())

    prediction = by_field(Predictor(models).predict("Page broken", UI_TEXT))["priority_label"]

    assert prediction.status == "model_unavailable"


def test_unknown_class_in_model_gives_error_status(tmp_path: Path) -> None:
    models = make_models(tmp_path / "m")
    pipeline = Pipeline([("tfidf", TfidfVectorizer()), ("clf", LogisticRegression())])
    pipeline.fit(["alpha beta gamma", "delta epsilon zeta"], ["frontend", "other_unknown"])  # klasių nėra sistemos žymų sąraše
    joblib.dump({"pipeline": pipeline, "field": "category_label", "model_version": "x"}, models / "category_label.joblib")

    prediction = by_field(Predictor(models).predict("alpha beta", "gamma alpha"))["category_label"]

    assert prediction.status == "error" and prediction.label is None


def test_replaced_model_file_is_reloaded(tmp_path: Path) -> None:
    models = make_models(tmp_path / "m")
    predictor = Predictor(models)
    assert by_field(predictor.predict("t", UI_TEXT))["category_label"].status == "ok"

    (models / "category_label.joblib").write_bytes(b"broken")
    assert by_field(predictor.predict("t", UI_TEXT))["category_label"].status == "model_unavailable"

    make_models(models, ("category_label",))  # modelis atkurtas – svetainės perkrauti nereikia
    assert by_field(predictor.predict("t", UI_TEXT))["category_label"].status == "ok"


def test_classify_report_saves_history_and_keeps_human_labels(conn: sqlite3.Connection, models: Path) -> None:
    report_id = create_bug_report(conn, "Page broken", UI_TEXT)
    with conn:
        conn.execute("UPDATE bug_reports SET category_label = 'security' WHERE id = ?", (report_id,))
    predictor = Predictor(models)

    classify_report(conn, predictor, report_id)
    classify_report(conn, predictor, report_id)

    assert conn.execute("SELECT COUNT(*) FROM prediction_runs").fetchone()[0] == 6  # istorija nekeičiama
    latest = latest_predictions(conn, report_id)
    assert set(latest) == set(FIELDS) and latest["category_label"]["predicted_label"] == "ui"
    row = latest["category_label"]
    assert (row["status"], row["model_version"], row["needs_review"] in (0, 1)) == ("ok", "test-v1", True)
    assert row["method"] and 0 < row["score"] <= 1
    # Žmogaus patvirtinta žyma neperrašyta, prognozė saugoma atskirai.
    assert conn.execute("SELECT category_label FROM bug_reports").fetchone()[0] == "security"


def test_classify_without_models_stores_status_message(conn: sqlite3.Connection, tmp_path: Path) -> None:
    report_id = create_bug_report(conn, "Title", "Description")

    classify_report(conn, Predictor(tmp_path / "none"), report_id)

    rows = conn.execute("SELECT status, predicted_label, score, message FROM prediction_runs").fetchall()
    assert [r["status"] for r in rows] == ["model_unavailable"] * 3
    assert all(r["predicted_label"] is None and r["score"] is None and r["message"] for r in rows)


def test_classify_unknown_report_raises(conn: sqlite3.Connection, models: Path) -> None:
    with pytest.raises(LookupError):
        classify_report(conn, Predictor(models), 999)


def test_init_db_adds_prediction_table_to_existing_database_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE bug_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
        " description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL, resolved_at TEXT, category_label TEXT, complexity_label TEXT,"
        " priority_label TEXT);"
        "INSERT INTO bug_reports (title, description, created_at, updated_at) VALUES ('Old', 'Old report', 'n', 'n');"
    )
    old.commit()
    old.close()

    connection = connect(path)
    init_db(connection)

    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "prediction_runs" in tables
    assert connection.execute("SELECT title FROM bug_reports").fetchone()[0] == "Old"
    connection.close()


def _titles(conn: sqlite3.Connection, **filters: str) -> set[str]:
    return {row["title"] for row in list_bug_reports(conn, ReportFilters(**filters))}


def test_list_uses_confirmed_label_first_then_prediction(conn: sqlite3.Connection, models: Path) -> None:
    predicted = create_bug_report(conn, "predicted", UI_TEXT)
    confirmed = create_bug_report(conn, "confirmed", UI_TEXT)
    create_bug_report(conn, "untouched", "nothing classified yet")
    with conn:
        conn.execute("UPDATE bug_reports SET category_label = 'security' WHERE id = ?", (confirmed,))
    for report_id in (predicted, confirmed):
        classify_report(conn, Predictor(models), report_id)

    assert _titles(conn, category_label="ui") == {"predicted"}  # patvirtinta „security“ turi pirmenybę
    assert _titles(conn, category_label="security") == {"confirmed"}
    assert _titles(conn, category_label=UNSET) == {"untouched"}
    rows = {r["title"]: r for r in list_bug_reports(conn, ReportFilters())}
    assert rows["predicted"]["auto_category_label"] == "ui" and rows["predicted"]["category_label"] is None
    assert rows["untouched"]["auto_category_label"] is None


def test_failed_predictions_do_not_become_labels(conn: sqlite3.Connection, tmp_path: Path) -> None:
    create_bug_report(conn, "no model", "Description")
    classify_report(conn, Predictor(tmp_path / "none"), 1)

    assert _titles(conn, category_label=UNSET) == {"no model"}
    assert list_bug_reports(conn, ReportFilters())[0]["auto_category_label"] is None


def test_default_predictor_uses_models_dir_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "custom"))

    first = default_predictor()

    assert first.models_dir == tmp_path / "custom" and default_predictor() is first
    monkeypatch.delenv("MODELS_DIR")
    assert config.models_dir() == config.PROJECT_DIR / "models"


@pytest.mark.skipif(not (config.PROJECT_DIR / "models" / "category_label.joblib").exists(),
                    reason="projekto apmokytų modelių (models/) nėra")
def test_project_trained_models_can_classify() -> None:
    predictions = Predictor(config.PROJECT_DIR / "models").predict(
        "Crash on startup", "The application crashes with a stack trace when the configuration file is missing."
    )

    assert [p.status for p in predictions] == ["ok"] * 3
    assert predictions[0].label in config.CATEGORY_LABELS
    assert predictions[1].label in config.COMPLEXITY_LABELS
    assert predictions[2].label in config.PRIORITY_LABELS


@pytest.mark.parametrize(("title", "description"), [
    ("Title", "Body text"), ("  Spaces  ", "\n  padded body \n"), ("Only title", ""),
])
def test_model_input_text_matches_training_text(title: str, description: str) -> None:
    assert prediction_service.model_text(title, description) == issue_text(title, description)
