import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db import add_casefold_function

STATUSES = ("new", "in_progress", "resolved")
TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 10000

_INSERT_SQL = """
INSERT INTO bug_reports (title, description, status, created_at, updated_at, reporter_user_id)
VALUES (?, ?, 'new', ?, ?, ?)
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    """Pašalina tarpus pradžioje / pabaigoje ir suvienodina eilučių pabaigas."""
    return value.replace("\r\n", "\n").strip()


def validate_report(title: str, description: str) -> dict[str, str]:
    """Grąžina klaidų pranešimus pagal lauką; tuščias žodynas reiškia teisingą formą."""
    errors: dict[str, str] = {}
    if not title:
        errors["title"] = "Įveskite klaidos pavadinimą."
    elif len(title) > TITLE_MAX_LENGTH:
        errors["title"] = (
            f"Pavadinimas per ilgas: leidžiama iki {TITLE_MAX_LENGTH} simbolių, "
            f"įvesta {len(title)}."
        )
    if not description:
        errors["description"] = "Įveskite išsamų klaidos aprašymą."
    elif len(description) > DESCRIPTION_MAX_LENGTH:
        errors["description"] = (
            f"Aprašymas per ilgas: leidžiama iki {DESCRIPTION_MAX_LENGTH} simbolių, "
            f"įvesta {len(description)}."
        )
    return errors


def create_bug_report(
    conn: sqlite3.Connection, title: str, description: str, reporter_user_id: int | None = None
) -> int:
    """Išsaugo naują pranešimą su būsena `new` ir grąžina jo ID.

    `reporter_user_id` – tik prisijungusio naudotojo pranešimui (6A); svečio pranešimas – NULL.
    """
    now = _utc_now()
    with conn:  # commit sėkmės atveju, kitaip rollback
        cursor = conn.execute(_INSERT_SQL, (title, description, now, now, reporter_user_id))
    return cursor.lastrowid


def list_reports_by_reporter(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    """Tik nurodyto naudotojo pateikti pranešimai (6A „Mano pranešimai“), naujausi pirmi."""
    return conn.execute(
        "SELECT id, title, status, created_at, updated_at, resolved_at FROM bug_reports"
        " WHERE reporter_user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()


def get_report_of_reporter(conn: sqlite3.Connection, report_id: int, user_id: int) -> sqlite3.Row | None:
    """Pranešimas tik jei jį pateikė šis naudotojas; svetimas ar neegzistuojantis – None."""
    return conn.execute(
        "SELECT id, title, description, status, created_at, updated_at, resolved_at FROM bug_reports"
        " WHERE id = ? AND reporter_user_id = ?",
        (report_id, user_id),
    ).fetchone()


# --- Vidinė klaidų valdymo aplinka (3 etapas) -------------------------------

# Filtro reikšmė įrašams, kurių žyma dar nenustatyta (NULL).
UNSET = "unset"
_LABEL_COLUMNS = ("category_label", "priority_label", "complexity_label")


@dataclass(frozen=True)
class ReportFilters:
    """Sąrašo filtrai; tuščia reikšmė reiškia „visi“."""

    search: str = ""
    status: str = ""
    category_label: str = ""
    priority_label: str = ""
    complexity_label: str = ""


def _auto_label_sql(column: str) -> str:
    """Naujausia sėkminga automatinė prognozė (stulpelio pavadinimas fiksuotas, ne iš naudotojo)."""
    return (f"(SELECT p.predicted_label FROM prediction_runs p WHERE p.bug_report_id = b.id "
            f"AND p.field = '{column}' AND p.status = 'ok' ORDER BY p.id DESC LIMIT 1)")


def list_bug_reports(conn: sqlite3.Connection, filters: ReportFilters) -> list[sqlite3.Row]:
    """Grąžina pranešimus (naujausi viršuje), įskaitant išspręstus, pagal filtrus.

    Kategorijos / prioriteto / sudėtingumo filtras ir rodoma reikšmė: žmogaus patvirtinta žyma,
    o jei jos nėra – automatinė prognozė (`auto_<laukas>`, rodoma sąraše su žyma „auto“).
    """
    add_casefold_function(conn)
    conditions: list[str] = []
    params: list[object] = []
    if filters.search:
        conditions.append(
            "(instr(py_casefold(title), ?) > 0 OR instr(py_casefold(description), ?) > 0)"
        )
        needle = filters.search.casefold()
        params += [needle, needle]
    if filters.status:
        conditions.append("status = ?")
        params.append(filters.status)
    for column in _LABEL_COLUMNS:  # stulpelių pavadinimai fiksuoti, ne iš naudotojo
        value = getattr(filters, column)
        effective = f"COALESCE(b.{column}, {_auto_label_sql(column)})"
        if value == UNSET:
            conditions.append(f"{effective} IS NULL")
        elif value:
            conditions.append(f"{effective} = ?")
            params.append(value)

    auto_columns = ", ".join(f"{_auto_label_sql(c)} AS auto_{c}" for c in _LABEL_COLUMNS)
    sql = f"SELECT b.*, {auto_columns} FROM bug_reports b"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY b.created_at DESC, b.id DESC"
    return conn.execute(sql, params).fetchall()


def get_bug_report(conn: sqlite3.Connection, report_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()


def update_status(conn: sqlite3.Connection, report_id: int, new_status: str) -> bool:
    """Pakeičia būseną. Grąžina False, jei būsena jau tokia (nieko nekeičiama).

    `resolved_at` užpildomas perėjus į `resolved` ir išvalomas klaidą atidarius iš
    naujo, todėl jis visada atitinka dabartinę būseną. Įrašai niekada netrinami.
    """
    if new_status not in STATUSES:
        raise ValueError("neleistina būsena")
    now = _utc_now()
    with conn:
        current = conn.execute(
            "SELECT status FROM bug_reports WHERE id = ?", (report_id,)
        ).fetchone()
        if current is None:
            raise LookupError("pranešimas nerastas")
        if current["status"] == new_status:
            return False
        resolved_at = now if new_status == "resolved" else None
        conn.execute(
            "UPDATE bug_reports SET status = ?, updated_at = ?, resolved_at = ? WHERE id = ?",
            (new_status, now, resolved_at, report_id),
        )
    return True
