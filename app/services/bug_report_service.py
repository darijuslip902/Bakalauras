import sqlite3
from datetime import datetime, timezone

TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 10000

_INSERT_SQL = """
INSERT INTO bug_reports (title, description, status, created_at, updated_at)
VALUES (?, ?, 'new', ?, ?)
"""


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
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:  # commit sėkmės atveju, kitaip rollback
        cursor = conn.execute(_INSERT_SQL, (title, description, now, now))
    return cursor.lastrowid
