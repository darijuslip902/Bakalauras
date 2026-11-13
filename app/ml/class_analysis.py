"""Klasių pasiskirstymo analizė visoms trims užduotims ir bandomojo rinkinio DI kokybė.

Klasės niekada nepriskiriamos dirbtinai: skaičiuojamos tik tos žymos, kurias nustatė
žmogus arba DI. Jei klasei pavyzdžių trūksta, tai aiškiai parodoma ataskaitoje.
"""

import sqlite3
from collections import Counter

from app.ml.collection import Source
from app.ml.training import FIELDS, classification_metrics, load_datasets
from app.services.annotation_service import LABEL_FIELDS

DEFAULT_TARGET_PER_CLASS = 40


def class_overview(
    conn: sqlite3.Connection, ai_model: str, prompt_version: str, target: int = DEFAULT_TARGET_PER_CLASS
) -> dict[str, object]:
    """Kiekvienos klasės mokymo (be testavimo rinkinio) ir žmogaus testo pavyzdžių skaičius."""
    train, human_test, _, stats = load_datasets(conn, ai_model, prompt_version)
    fields: dict[str, list[dict[str, object]]] = {}
    for field in FIELDS:
        train_counts = Counter(example.labels[field] for example in train)
        test_counts = Counter(example.labels[field] for example in human_test)
        fields[field] = [
            {
                "value": value,
                "name": name,
                "train": train_counts[value],
                "test": test_counts[value],
                "missing": max(0, target - train_counts[value]),
            }
            for value, name in LABEL_FIELDS[field].items()
        ]
    return {"target": target, "dataset": stats, "fields": fields}


def deficits(overview: dict[str, object]) -> list[tuple[str, str, int]]:
    """(laukas, klasė, kiek trūksta iki tikslo) visoms trims užduotims."""
    return [
        (field, item["value"], item["missing"])
        for field, items in overview["fields"].items()
        for item in items
        if item["missing"] > 0
    ]


def augmentation_plan(
    shortages: list[tuple[str, str, int]], augment: dict[tuple[str, str], list[Source]]
) -> tuple[list[Source], list[tuple[str, str]]]:
    """Šaltiniai trūkstamoms klasėms ir klasės, kurioms šaltinio nėra.

    Šaltinis tik nurodo, kur ieškoti daugiau įrašų; klasę po importo vis tiek nustato DI / žmogus,
    todėl papildymas negarantuoja, kad trūkumas išnyks.
    """
    selected: list[Source] = []
    without_source: list[tuple[str, str]] = []
    for field, value, _ in shortages:
        sources = augment.get((field, value), [])
        if not sources:
            without_source.append((field, value))
        for source in sources:
            if source not in selected:
                selected.append(source)
    return selected, without_source


def pilot_agreement(conn: sqlite3.Connection, ai_model: str, prompt_version: str) -> dict[str, object]:
    """DI žymų sutapimas su žmogaus žymomis bandomajame rinkinyje (modelio pasirinkimui)."""
    rows = conn.execute(
        """
        SELECT g.training_suitability AS human_suitability,
               g.category_label AS h_category_label, g.complexity_label AS h_complexity_label,
               g.priority_label AS h_priority_label,
               a.training_suitability AS ai_suitability,
               a.category_label AS a_category_label, a.complexity_label AS a_complexity_label,
               a.priority_label AS a_priority_label
        FROM github_issues g
        JOIN ai_annotations a ON a.github_issue_id = g.id AND a.model = ? AND a.prompt_version = ?
                              AND a.status = 'ok'
        WHERE g.is_pilot_set = 1 AND g.training_suitability != 'unreviewed'
        """,
        (ai_model, prompt_version),
    ).fetchall()
    pilot_total = conn.execute("SELECT COUNT(*) FROM github_issues WHERE is_pilot_set = 1").fetchone()[0]
    result: dict[str, object] = {"pilot_total": pilot_total, "compared": len(rows), "fields": {}}
    if not rows:
        result["suitability"] = None
        return result
    human = [row["human_suitability"] for row in rows]
    ai = [row["ai_suitability"] for row in rows]
    result["suitability"] = classification_metrics(human, ai, ["suitable", "unsuitable"])
    for field in FIELDS:
        pairs = [
            (row[f"h_{field}"], row[f"a_{field}"])
            for row in rows
            if row["human_suitability"] == "suitable" and row[f"h_{field}"] and row[f"a_{field}"]
        ]
        if pairs:
            truth, predicted = zip(*pairs)
            result["fields"][field] = classification_metrics(list(truth), list(predicted), sorted(set(truth) | set(predicted)))
        else:
            result["fields"][field] = None
    return result
