import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

STATUSES = ("new", "in_progress", "resolved")
TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 10000

_INSERT_SQL = """
INSERT INTO bug_reports (title, description, status, created_at, updated_at)
VALUES (?, ?, 'new', ?, ?)
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


def create_bug_report(conn: sqlite3.Connection, title: str, description: str) -> int:
    """Išsaugo naują pranešimą su būsena `new` ir grąžina jo ID."""
    now = _utc_now()
    with conn:  # commit sėkmės atveju, kitaip rollback
        cursor = conn.execute(_INSERT_SQL, (title, description, now, now))
    return cursor.lastrowid


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


def _casefold(value: str | None) -> str | None:
    return value.casefold() if value is not None else None


def list_bug_reports(conn: sqlite3.Connection, filters: ReportFilters) -> list[sqlite3.Row]:
    """Grąžina pranešimus (naujausi viršuje), įskaitant išspręstus, pagal filtrus."""
    # SQLite LIKE/lower() nepalaiko lietuviškų raidžių didžiųjų/mažųjų lygybės,
    # todėl paieškai naudojama Python casefold funkcija.
    conn.create_function("py_casefold", 1, _casefold, deterministic=True)
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
        if value == UNSET:
            conditions.append(f"{column} IS NULL")
        elif value:
            conditions.append(f"{column} = ?")
            params.append(value)

    sql = "SELECT * FROM bug_reports"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC, id DESC"
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
