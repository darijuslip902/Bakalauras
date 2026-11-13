"""GitHub issues mokymo duomenų peržiūra ir rankinis žmogaus žymėjimas (4 etapas).

GitHub etiketės automatiškai nelaikomos teisingomis žymomis: kategoriją,
sudėtingumą, prioritetą ir tinkamumą mokymui nustato tik žmogus.
"""

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from app import config
from app.db import add_casefold_function

PER_PAGE = 25
ANNOTATION_SOURCE_MANUAL = "manual"
LABEL_FIELDS = {
    "category_label": config.CATEGORY_LABELS,
    "complexity_label": config.COMPLEXITY_LABELS,
    "priority_label": config.PRIORITY_LABELS,
}

# Kiek iš trijų klasifikavimo laukų užpildyta (0–3).
_FILLED_SQL = (
    "((category_label IS NOT NULL) + (complexity_label IS NOT NULL)"
    " + (priority_label IS NOT NULL))"
)
_ANNOTATION_CONDITIONS = {
    "unlabeled": f"{_FILLED_SQL} = 0",
    "partial": f"{_FILLED_SQL} BETWEEN 1 AND 2",
    "complete": f"{_FILLED_SQL} = 3",
}
_SORT_ORDERS = {
    # Įrašai be GitHub datos rodomi gale.
    "newest": "github_created_at IS NULL, github_created_at DESC, id DESC",
    "oldest": "github_created_at IS NULL, github_created_at ASC, id ASC",
}


@dataclass(frozen=True)
class TrainingDataFilters:
    """Sąrašo filtrai; tuščia reikšmė reiškia „visi“."""

    search: str = ""
    annotation: str = ""
    suitability: str = ""
    repository: str = ""
    test_set: str = ""  # "", "yes" (tik testavimo rinkinys) arba "no"
    sort: str = "newest"


@dataclass(frozen=True)
class Page:
    rows: list[sqlite3.Row]
    total: int
    page: int
    pages: int


def annotation_status(issue: sqlite3.Row) -> str:
    filled = sum(issue[field] is not None for field in LABEL_FIELDS)
    if filled == 0:
        return "unlabeled"
    return "complete" if filled == 3 else "partial"


def github_labels(issue: sqlite3.Row) -> list[str]:
    """Originalios GitHub etiketės (tik informacijai, ne mokymo žymos)."""
    try:
        labels = json.loads(issue["labels_json"])
    except (TypeError, ValueError):
        return []
    return [label for label in labels if isinstance(label, str)] if isinstance(labels, list) else []


def list_repositories(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT repository_full_name FROM github_issues ORDER BY repository_full_name"
    )
    return [row[0] for row in rows]


def list_training_issues(
    conn: sqlite3.Connection, filters: TrainingDataFilters, page: int = 1
) -> Page:
    add_casefold_function(conn)
    conditions: list[str] = []
    params: list[object] = []
    if filters.search:
        conditions.append("(instr(py_casefold(title), ?) > 0 OR instr(py_casefold(body), ?) > 0)")
        needle = filters.search.casefold()
        params += [needle, needle]
    if filters.annotation in _ANNOTATION_CONDITIONS:
        conditions.append(_ANNOTATION_CONDITIONS[filters.annotation])
    if filters.suitability:
        conditions.append("training_suitability = ?")
        params.append(filters.suitability)
    if filters.test_set == "yes":
        conditions.append("is_test_set = 1")
    elif filters.test_set == "pilot":
        conditions.append("is_pilot_set = 1")
    elif filters.test_set == "no":
        conditions.append("is_test_set = 0 AND is_pilot_set = 0")
    if filters.repository:
        conditions.append("repository_full_name = ?")
        params.append(filters.repository)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    total = conn.execute(f"SELECT COUNT(*) FROM github_issues{where}", params).fetchone()[0]
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(max(page, 1), pages)
    order = _SORT_ORDERS.get(filters.sort, _SORT_ORDERS["newest"])
    rows = conn.execute(
        f"SELECT * FROM github_issues{where} ORDER BY {order} LIMIT ? OFFSET ?",
        [*params, PER_PAGE, (page - 1) * PER_PAGE],
    ).fetchall()
    return Page(rows=rows, total=total, page=page, pages=pages)


def annotation_stats(conn: sqlite3.Connection) -> dict[str, object]:
    """Žymėjimo eiga ir kiekvieno lauko klasių skaičiai (visi / tinka mokymui)."""
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS total,
               COALESCE(SUM({_FILLED_SQL} = 3), 0) AS complete,
               COALESCE(SUM({_FILLED_SQL} BETWEEN 1 AND 2), 0) AS partial,
               COALESCE(SUM({_FILLED_SQL} = 0), 0) AS unlabeled,
               COALESCE(SUM(training_suitability = 'suitable'), 0) AS suitable,
               COALESCE(SUM(training_suitability = 'unsuitable'), 0) AS unsuitable,
               COALESCE(SUM(training_suitability = 'suitable' AND {_FILLED_SQL} = 3), 0)
                   AS ready_for_training
        FROM github_issues
        """
    ).fetchone()
    stats: dict[str, object] = dict(row)

    class_counts: dict[str, list[dict[str, object]]] = {}
    for field, labels in LABEL_FIELDS.items():  # stulpelių pavadinimai fiksuoti
        counts = {
            value: (all_count, suitable_count)
            for value, all_count, suitable_count in conn.execute(
                f"""
                SELECT {field}, COUNT(*), SUM(training_suitability = 'suitable')
                FROM github_issues WHERE {field} IS NOT NULL GROUP BY {field}
                """
            )
        }
        class_counts[field] = [
            {"value": value, "name": name, "all": counts.get(value, (0, 0))[0],
             "suitable": counts.get(value, (0, 0))[1]}
            for value, name in labels.items()
        ]
    stats["class_counts"] = class_counts
    return stats


def get_issue(conn: sqlite3.Connection, issue_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM github_issues WHERE id = ?", (issue_id,)).fetchone()


def validate_annotation(values: dict[str, str]) -> tuple[dict[str, str | None], dict[str, str]]:
    """Grąžina (išvalytos reikšmės, klaidos). Tuščia klasifikavimo reikšmė tampa None (NULL)."""
    cleaned: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    for field, labels in LABEL_FIELDS.items():
        value = values.get(field, "").strip()
        if value and value not in labels:
            errors[field] = "Neleistina reikšmė."
        cleaned[field] = value or None
    suitability = values.get("training_suitability", "").strip() or "unreviewed"
    if suitability not in config.TRAINING_SUITABILITY_LABELS:
        errors["training_suitability"] = "Neleistina tinkamumo mokymui reikšmė."
    cleaned["training_suitability"] = suitability
    return cleaned, errors


def save_annotation(
    conn: sqlite3.Connection, issue_id: int, values: dict[str, str | None]
) -> bool:
    """Išsaugo žmogaus žymas. Grąžina False, jei niekas nepasikeitė.

    Saugomi visi keturi laukai kartu, todėl formoje nepakeisti laukai lieka tokie,
    kokie buvo (forma visada rodo esamas reikšmes).
    """
    columns = (*LABEL_FIELDS, "training_suitability")
    with conn:
        current = get_issue(conn, issue_id)
        if current is None:
            raise LookupError("įrašas nerastas")
        if all(current[column] == values[column] for column in columns):
            return False
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            """
            UPDATE github_issues
            SET category_label = ?, complexity_label = ?, priority_label = ?,
                training_suitability = ?, annotation_source = ?, annotated_at = ?
            WHERE id = ?
            """,
            (
                values["category_label"],
                values["complexity_label"],
                values["priority_label"],
                values["training_suitability"],
                ANNOTATION_SOURCE_MANUAL,
                now,
                issue_id,
            ),
        )
    return True


def next_unlabeled_id(conn: sqlite3.Connection, after_id: int = 0) -> int | None:
    """Kitas dar ne visiškai pažymėtas įrašas, kurio žmogus nepažymėjo „Netinka mokymui“.

    Pirmiausia siūlomi bandomojo, tada testavimo rinkinio įrašai (juos žymi žmogus),
    tada visi kiti.
    Ieškoma pagal ID po `after_id`; pasiekus pabaigą pradedama iš pradžių.
    """
    base = f"{_FILLED_SQL} < 3 AND training_suitability != 'unsuitable'"
    for condition in (f"{base} AND is_pilot_set = 1", f"{base} AND is_test_set = 1", base):
        row = conn.execute(
            f"SELECT id FROM github_issues WHERE {condition} AND id > ? ORDER BY id LIMIT 1",
            (after_id,),
        ).fetchone()
        if row is None:
            row = conn.execute(
                f"SELECT id FROM github_issues WHERE {condition} AND id != ? ORDER BY id LIMIT 1",
                (after_id,),
            ).fetchone()
        if row is not None:
            return row[0]
    return None
