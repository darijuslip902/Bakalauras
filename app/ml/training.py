"""Trijų klasifikatorių (kategorija, sudėtingumas, prioritetas) mokymas ir vertinimas.

Metodika (docs/EVALUATION_PLAN.md):
- mokymo žyma: žmogaus žyma, jei ji yra, kitaip sėkminga DI žyma;
- mokymui imami tik „Tinka mokymui“ įrašai su visomis trimis žymomis;
- žmogaus testavimo rinkinio (is_test_set = 1) įrašai į mokymą niekada nepatenka;
- dublikatai pašalinami prieš dalijimą, taip pat tekstai, sutampantys su testo įrašais;
- stratifikuotas train/validation dalijimas atliekamas prieš Pipeline fit (fiksuotas seed);
- lyginama su daugumos klasės baseline tuo pačiu dalijimu;
- galutinis vertinimas – su žmogaus patikrintu testavimo rinkiniu.
"""

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from app.ml.data_quality import check_quality, issue_text, text_fingerprint

FIELDS = ("category_label", "complexity_label", "priority_label")
DEFAULT_SEED = 42
DEFAULT_VALIDATION_SIZE = 0.2
DEFAULT_MIN_SAMPLES = 30
MIN_CLASS_SAMPLES = 5
SMALL_TEST_SET_WARNING = 30
REPORT_FILE = "training_report.json"


@dataclass(frozen=True)
class Example:
    issue_id: int
    text: str
    fingerprint: str
    labels: dict[str, str]


def _effective_rows(conn: sqlite3.Connection, ai_model: str, prompt_version: str) -> list[sqlite3.Row]:
    """Kiekvienam issue: žmogaus žymos ir (jei yra) sėkminga DI žyma."""
    return conn.execute(
        """
        SELECT g.id, g.title, g.body, g.is_test_set,
               g.training_suitability AS human_suitability,
               g.category_label AS human_category_label,
               g.complexity_label AS human_complexity_label,
               g.priority_label AS human_priority_label,
               a.training_suitability AS ai_suitability,
               a.category_label AS ai_category_label,
               a.complexity_label AS ai_complexity_label,
               a.priority_label AS ai_priority_label
        FROM github_issues g
        LEFT JOIN ai_annotations a
            ON a.github_issue_id = g.id AND a.model = ? AND a.prompt_version = ?
               AND a.status = 'ok'
        ORDER BY g.id
        """,
        (ai_model, prompt_version),
    ).fetchall()


def load_datasets(
    conn: sqlite3.Connection, ai_model: str, prompt_version: str
) -> tuple[list[Example], list[Example], list[Example], dict[str, int]]:
    """Grąžina (mokymo pavyzdžiai, žmogaus testas, testas su DI žymomis, statistika).

    Trečiasis sąrašas – tie patys testo įrašai su DI žymomis: pagal jį vertinama,
    kiek DI žymos sutampa su žmogaus žymomis.
    """
    quality_ok = set(check_quality(conn).ok_ids)
    train: list[Example] = []
    human_test: list[Example] = []
    ai_on_test: list[Example] = []
    stats = Counter()
    for row in _effective_rows(conn, ai_model, prompt_version):
        text = issue_text(row["title"], row["body"])
        fingerprint = text_fingerprint(row["title"], row["body"])
        human = {field: row[f"human_{field}"] for field in FIELDS}
        ai = {field: row[f"ai_{field}"] for field in FIELDS}
        if row["is_test_set"]:
            # Testui – tik žmogaus žymos; DI žymos naudojamos tik palyginimui.
            if row["human_suitability"] == "suitable" and all(human.values()):
                human_test.append(Example(row["id"], text, fingerprint, human))
                if row["ai_suitability"] == "suitable" and all(ai.values()):
                    ai_on_test.append(Example(row["id"], text, fingerprint, ai))
            stats["test_set_rows"] += 1
            continue
        if row["id"] not in quality_ok:
            stats["excluded_quality"] += 1
            continue
        suitability = (
            row["human_suitability"] if row["human_suitability"] != "unreviewed" else row["ai_suitability"]
        )
        labels = {field: human[field] or ai[field] for field in FIELDS}
        if suitability is None:
            stats["excluded_not_labelled_yet"] += 1
            continue
        if suitability != "suitable":
            stats["excluded_not_suitable"] += 1
            continue
        if not all(labels.values()):
            stats["excluded_incomplete_labels"] += 1
            continue
        if any(human.values()):
            stats["human_labelled_used"] += 1
        train.append(Example(row["id"], text, fingerprint, labels))

    # Mokymo tekstai, sutampantys su testo tekstais, pašalinami (apsauga nuo nutekėjimo).
    test_fingerprints = {example.fingerprint for example in human_test}
    before = len(train)
    train = [example for example in train if example.fingerprint not in test_fingerprints]
    stats["excluded_test_duplicates"] = before - len(train)
    stats["train_rows"] = len(train)
    stats["human_test_rows"] = len(human_test)
    return train, human_test, ai_on_test, dict(stats)


def build_pipeline(seed: int) -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(
                lowercase=True, ngram_range=(1, 2), min_df=2, max_features=50_000, sublinear_tf=True,
            )),
            ("classifier", LogisticRegression(
                max_iter=2000, class_weight="balanced", random_state=seed,
            )),
        ]
    )


def _metrics(y_true: list[str], y_pred: list[str], classes: list[str]) -> dict[str, object]:
    return {
        "samples": len(y_true),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "macro_f1": round(f1_score(y_true, y_pred, labels=classes, average="macro", zero_division=0), 4),
        "weighted_f1": round(
            f1_score(y_true, y_pred, labels=classes, average="weighted", zero_division=0), 4
        ),
        "per_class": classification_report(
            y_true, y_pred, labels=classes, output_dict=True, zero_division=0
        ),
        "confusion_matrix": {
            "labels": classes,
            "matrix": confusion_matrix(y_true, y_pred, labels=classes).tolist(),
        },
    }


def train_field(
    field: str,
    train_examples: list[Example],
    human_test: list[Example],
    ai_on_test: list[Example],
    seed: int = DEFAULT_SEED,
    validation_size: float = DEFAULT_VALIDATION_SIZE,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> tuple[Pipeline | None, dict[str, object]]:
    """Moko vieno lauko modelį. Jei duomenų per mažai – (None, status insufficient_data)."""
    counts = Counter(example.labels[field] for example in train_examples)
    excluded = {label: count for label, count in counts.items() if count < MIN_CLASS_SAMPLES}
    usable = [example for example in train_examples if example.labels[field] not in excluded]
    classes = sorted({example.labels[field] for example in usable})
    report: dict[str, object] = {
        "field": field,
        "class_distribution": dict(sorted(counts.items())),
        "excluded_classes_below_min": excluded,
        "min_class_samples": MIN_CLASS_SAMPLES,
    }
    if len(usable) < min_samples or len(classes) < 2:
        report["status"] = "insufficient_data"
        report["message"] = (
            f"Reikia bent {min_samples} pavyzdžių ir 2 klasių (po >= {MIN_CLASS_SAMPLES}); "
            f"turima {len(usable)} pavyzdžių, {len(classes)} klasių."
        )
        return None, report

    texts = [example.text for example in usable]
    labels = [example.labels[field] for example in usable]
    # Dalijimas atliekamas PRIEŠ fit: TF-IDF žodynas mokomas tik iš mokymo dalies.
    x_train, x_val, y_train, y_val = train_test_split(
        texts, labels, test_size=validation_size, random_state=seed, stratify=labels
    )
    model = build_pipeline(seed).fit(x_train, y_train)
    baseline = DummyClassifier(strategy="most_frequent").fit(x_train, y_train)

    report.update(
        status="trained",
        classes=classes,
        train_samples=len(x_train),
        validation_samples=len(x_val),
        validation_note="Validacijos žymos – daugiausia DI sugeneruotos (ne žmogaus patikrintos).",
        validation={
            "model": _metrics(y_val, list(model.predict(x_val)), classes),
            "majority_baseline": _metrics(y_val, list(baseline.predict(x_val)), classes),
        },
    )

    test = [example for example in human_test if example.labels[field] in classes]
    if test:
        y_test = [example.labels[field] for example in test]
        x_test = [example.text for example in test]
        report["human_test"] = {
            "model": _metrics(y_test, list(model.predict(x_test)), classes),
            "majority_baseline": _metrics(y_test, list(baseline.predict(x_test)), classes),
            "skipped_unknown_classes": len(human_test) - len(test),
        }
        if len(test) < SMALL_TEST_SET_WARNING:
            report["human_test"]["warning"] = (
                f"Maža testo imtis ({len(test)}); metrikos labai svyruoja, interpretuoti atsargiai."
            )
    else:
        report["human_test"] = None

    # Kiek DI žymos sutampa su žmogaus žymomis tuose pačiuose testo įrašuose.
    human_by_id = {example.issue_id: example.labels[field] for example in human_test}
    pairs = [(human_by_id[e.issue_id], e.labels[field]) for e in ai_on_test if e.issue_id in human_by_id]
    if pairs:
        human_labels, ai_labels = zip(*pairs)
        all_classes = sorted(set(human_labels) | set(ai_labels))
        report["ai_vs_human_agreement"] = _metrics(list(human_labels), list(ai_labels), all_classes)
    else:
        report["ai_vs_human_agreement"] = None
    return model, report


def train_all(
    conn: sqlite3.Connection,
    output_dir: Path,
    ai_model: str,
    prompt_version: str,
    seed: int = DEFAULT_SEED,
    validation_size: float = DEFAULT_VALIDATION_SIZE,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict[str, object]:
    """Moko visus tris modelius, išsaugo `<laukas>.joblib` ir `training_report.json`."""
    train, human_test, ai_on_test, stats = load_datasets(conn, ai_model, prompt_version)
    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report: dict[str, object] = {
        "model_version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "TF-IDF (1-2 gramos) + LogisticRegression (class_weight=balanced)",
        "seed": seed,
        "validation_size": validation_size,
        "ai_labels": {"model": ai_model, "prompt_version": prompt_version},
        "dataset": stats,
        "fields": {},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for field in FIELDS:
        model, field_report = train_field(
            field, train, human_test, ai_on_test, seed, validation_size, min_samples
        )
        path = output_dir / f"{field}.joblib"
        if model is not None:
            joblib.dump({"pipeline": model, "field": field, "model_version": version}, path)
            field_report["model_file"] = path.name
        elif path.exists():
            # Senas modelis nebeatitiktų ataskaitos – pašalinamas, kad nebūtų naudojamas.
            path.unlink()
        report["fields"][field] = field_report
    (output_dir / REPORT_FILE).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def load_model(path: Path) -> Pipeline:
    """Išsaugoto modelio įkėlimas (bus naudojamas 5B etape svetainėje)."""
    return joblib.load(path)["pipeline"]
