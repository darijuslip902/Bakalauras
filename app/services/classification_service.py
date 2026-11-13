"""Programuotojo klasifikacijos patvirtinimas / pataisymas (5C).

Galiojančios žmogaus žymos saugomos `bug_reports` stulpeliuose; kiekvienas realus pakeitimas
papildomai įrašomas į `classification_confirmations` (kas, kada, ankstesnė reikšmė, tuo metu
buvusi ML prognozė). Automatinis klasifikavimas šių stulpelių niekada nekeičia.
"""

import sqlite3
from datetime import datetime, timezone

from app import config
from app.services.prediction_service import FIELDS, latest_predictions

ALLOWED = {
    "category_label": config.CATEGORY_LABELS,
    "complexity_label": config.COMPLEXITY_LABELS,
    "priority_label": config.PRIORITY_LABELS,
}
FIELD_TITLES = {
    "category_label": "Kategorija",
    "complexity_label": "Sudėtingumas",
    "priority_label": "Prioritetas",
}
SHORT = {"category_label": "category", "complexity_label": "complexity", "priority_label": "priority"}


def validate_classification(values: dict[str, str]) -> dict[str, str]:
    """Grąžina laukas -> klaidos pranešimas (tuščias žodynas, jei viskas gerai)."""
    errors = {}
    for field in FIELDS:
        value = (values.get(field) or "").strip()
        if not value:
            errors[field] = f"Pasirinkite lauką „{FIELD_TITLES[field]}“."
        elif value not in ALLOWED[field]:
            errors[field] = f"Neleistina reikšmė laukui „{FIELD_TITLES[field]}“."
    return errors


def confirm_classification(
    conn: sqlite3.Connection, report_id: int, values: dict[str, str], username: str
) -> bool:
    """Išsaugo patvirtintas žymas. False – reikšmės nepasikeitė (istorijos įrašas nekuriamas).

    Reikšmes būtina prieš tai patikrinti `validate_classification`; čia tikrinama dar kartą.
    """
    if validate_classification(values):
        raise ValueError("neleistinos klasifikacijos reikšmės")
    clean = {field: values[field].strip() for field in FIELDS}
    row = conn.execute(
        "SELECT category_label, complexity_label, priority_label FROM bug_reports WHERE id = ?",
        (report_id,),
    ).fetchone()
    if row is None:
        raise LookupError("pranešimas nerastas")
    if all(row[field] == clean[field] for field in FIELDS):
        return False
    predicted = latest_predictions(conn, report_id)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def predicted_value(field: str) -> str | None:
        item = predicted.get(field)
        return item["predicted_label"] if item is not None and item["status"] == "ok" else None

    with conn:
        conn.execute(
            "UPDATE bug_reports SET category_label = ?, complexity_label = ?, priority_label = ?,"
            " updated_at = ? WHERE id = ?",
            (clean["category_label"], clean["complexity_label"], clean["priority_label"], now, report_id),
        )
        conn.execute(
            "INSERT INTO classification_confirmations (bug_report_id, confirmed_by, confirmed_at,"
            " category_label, complexity_label, priority_label,"
            " previous_category, previous_complexity, previous_priority,"
            " predicted_category, predicted_complexity, predicted_priority)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (report_id, username, now, clean["category_label"], clean["complexity_label"],
             clean["priority_label"], row["category_label"], row["complexity_label"],
             row["priority_label"], predicted_value("category_label"),
             predicted_value("complexity_label"), predicted_value("priority_label")),
        )
    return True


def confirmation_history(conn: sqlite3.Connection, report_id: int) -> list[sqlite3.Row]:
    """Patvirtinimų istorija, naujausi pirmi."""
    return conn.execute(
        "SELECT * FROM classification_confirmations WHERE bug_report_id = ? ORDER BY id DESC",
        (report_id,),
    ).fetchall()


def is_confirmed(report: sqlite3.Row) -> bool:
    """Patvirtinta, kai nustatytos visos trys žymos."""
    return all(report[field] for field in FIELDS)


def form_values(report: sqlite3.Row, predictions: dict[str, sqlite3.Row]) -> dict[str, str]:
    """Formos pradinės reikšmės: patvirtinta žyma, kitaip naujausia ok ML prognozė, kitaip tuščia."""
    values = {}
    for field in FIELDS:
        prediction = predictions.get(field)
        auto = prediction["predicted_label"] if prediction is not None and prediction["status"] == "ok" else ""
        values[field] = report[field] or auto or ""
    return values
