import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app import config

# Du atskiri srautai: sistemos pranešimai (bug_reports) ir iš GitHub importuoti
# mokymo įrašai (github_issues). Pakartotinis vykdymas saugus (IF NOT EXISTS).
SCHEMA = """
CREATE TABLE IF NOT EXISTS bug_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'in_progress', 'resolved')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    category_label TEXT,
    complexity_label TEXT,
    priority_label TEXT
);

-- 6A: vienos organizacijos naudotojų paskyros. Viešai registruojantis visada `tester`.
-- Vardas ir el. paštas unikalūs nepriklausomai nuo raidžių dydžio; slaptažodis tik PBKDF2 maiša.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'tester'
        CHECK (role IN ('tester', 'developer', 'admin')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS github_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_full_name TEXT NOT NULL COLLATE NOCASE,
    issue_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL,
    html_url TEXT NOT NULL,
    labels_json TEXT NOT NULL DEFAULT '[]',
    github_created_at TEXT,
    github_updated_at TEXT,
    is_pull_request INTEGER NOT NULL DEFAULT 0 CHECK (is_pull_request IN (0, 1)),
    imported_at TEXT NOT NULL,
    category_label TEXT,
    complexity_label TEXT,
    priority_label TEXT,
    annotation_source TEXT,
    annotated_at TEXT,
    training_suitability TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (training_suitability IN ('unreviewed', 'suitable', 'unsuitable')),
    is_test_set INTEGER NOT NULL DEFAULT 0 CHECK (is_test_set IN (0, 1)),
    is_pilot_set INTEGER NOT NULL DEFAULT 0 CHECK (is_pilot_set IN (0, 1)),
    source_kind TEXT NOT NULL DEFAULT 'base' CHECK (source_kind IN ('base', 'augmentation')),
    UNIQUE (repository_full_name, issue_number)
);

-- DI (išorinio API) sugeneruotos žymos mokymo duomenims (5A etapas). Laikomos
-- atskirai nuo žmogaus žymų github_issues lentelėje ir jų niekada neperrašo.
CREATE TABLE IF NOT EXISTS ai_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_issue_id INTEGER NOT NULL REFERENCES github_issues(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'invalid')),
    training_suitability TEXT CHECK (training_suitability IN ('suitable', 'unsuitable')),
    category_label TEXT,
    complexity_label TEXT,
    priority_label TEXT,
    reason TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 1,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_input_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (github_issue_id, model, prompt_version)
);

-- Tęstinis rinkimas (5B): visiškai apdoroti šaltiniai (repozitorija + etiketės filtras).
-- Ta pati repozitorija su skirtingomis etiketėmis turi atskirus įrašus. Šaltinis įrašomas
-- tik po sėkmingo viso importo, todėl nutrūkęs (pvz. dėl API limito) šaltinis kitą kartą
-- renkamas iš naujo, o baigti praleidžiami.
CREATE TABLE IF NOT EXISTS collection_progress (
    repository_full_name TEXT NOT NULL COLLATE NOCASE,
    label TEXT NOT NULL DEFAULT '',
    completed_limit INTEGER NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (repository_full_name, label)
);

-- Automatinės ML prognozės (5C): istorija, viena eilutė vienam laukui per klasifikavimo
-- paleidimą. Žmogaus patvirtintos žymos lieka bug_reports stulpeliuose ir niekada
-- neperrašomos. status: ok | model_unavailable (nėra / neįkeliamas modelis) | error.
CREATE TABLE IF NOT EXISTS prediction_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bug_report_id INTEGER NOT NULL REFERENCES bug_reports(id) ON DELETE CASCADE,
    field TEXT NOT NULL CHECK (field IN ('category_label', 'complexity_label', 'priority_label')),
    status TEXT NOT NULL CHECK (status IN ('ok', 'model_unavailable', 'error')),
    predicted_label TEXT,
    score REAL,
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    method TEXT,
    model_version TEXT,
    message TEXT,
    created_at TEXT NOT NULL,
    input_language TEXT,
    translation_method TEXT
);
CREATE INDEX IF NOT EXISTS idx_prediction_runs_report
    ON prediction_runs (bug_report_id, field, id);

-- Programuotojo klasifikacijos patvirtinimai / pataisymai (5C): kas, kada ir kokias reikšmes
-- nustatė (istorija nekeičiama). Galiojančios reikšmės yra bug_reports stulpeliuose;
-- čia dar saugoma ankstesnė patvirtinta reikšmė ir tuo metu buvusi ML prognozė.
CREATE TABLE IF NOT EXISTS classification_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bug_report_id INTEGER NOT NULL REFERENCES bug_reports(id) ON DELETE CASCADE,
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    category_label TEXT NOT NULL,
    complexity_label TEXT NOT NULL,
    priority_label TEXT NOT NULL,
    previous_category TEXT,
    previous_complexity TEXT,
    previous_priority TEXT,
    predicted_category TEXT,
    predicted_complexity TEXT,
    predicted_priority TEXT
);
CREATE INDEX IF NOT EXISTS idx_classification_confirmations_report
    ON classification_confirmations (bug_report_id, id);

-- 6B: programuotojų specializacijos (kategorijų eilės). Vienas programuotojas – kelios kategorijos,
-- viena kategorija – keli programuotojai. Kategorijų reikšmės tikrinamos pagal config.CATEGORY_LABELS
-- (app.services.user_service.set_developer_categories); konkretus klaidos priskyrimas žmogui nekuriamas.
CREATE TABLE IF NOT EXISTS developer_categories (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, category_label)
);
CREATE INDEX IF NOT EXISTS idx_developer_categories_category
    ON developer_categories (category_label, user_id);
"""

# Stulpeliai, pridėti vėlesniuose etapuose. Senoms DB jie pridedami ALTER TABLE
# komanda, todėl esami įrašai ir žymos išlieka.
_ADDED_COLUMNS = {
    # 5C: lietuviško teksto apdorojimas prieš klasifikavimą (kalba ir vertimo būdas).
    ("prediction_runs", "input_language"): "TEXT",
    ("prediction_runs", "translation_method"): "TEXT",
    ("github_issues", "training_suitability"): (
        "TEXT NOT NULL DEFAULT 'unreviewed' "
        "CHECK (training_suitability IN ('unreviewed', 'suitable', 'unsuitable'))"
    ),
    # Žmogaus patikrinto testavimo rinkinio narystė (5A etapas).
    ("github_issues", "is_test_set"): (
        "INTEGER NOT NULL DEFAULT 0 CHECK (is_test_set IN (0, 1))"
    ),
    # 5B: bandomasis DI kokybės / kainos rinkinys (atskiras nuo galutinio testo) ir
    # įrašo kilmė: pagrindinis rinkimas ar tikslinis klasių papildymas.
    ("github_issues", "is_pilot_set"): (
        "INTEGER NOT NULL DEFAULT 0 CHECK (is_pilot_set IN (0, 1))"
    ),
    ("github_issues", "source_kind"): (
        "TEXT NOT NULL DEFAULT 'base' CHECK (source_kind IN ('base', 'augmentation'))"
    ),
    # 6A: kas pateikė pranešimą (tik prisijungus). Seni ir svečių pranešimai lieka NULL.
    ("bug_reports", "reporter_user_id"): "INTEGER REFERENCES users(id)",
}

# Indeksai stulpeliams, kurie gali būti pridėti tik per ALTER (vykdomi po _ADDED_COLUMNS).
_POST_MIGRATION_SQL = """
CREATE INDEX IF NOT EXISTS idx_bug_reports_reporter ON bug_reports (reporter_user_id, id);
"""


def get_database_path() -> Path:
    """FastAPI priklausomybė; testuose pakeičiama laikina DB (`dependency_overrides`)."""
    return config.database_path()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection(path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    with conn:
        for (table, column), definition in _ADDED_COLUMNS.items():
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.executescript(_POST_MIGRATION_SQL)


def add_casefold_function(conn: sqlite3.Connection) -> None:
    """SQL funkcija `py_casefold`: SQLite lower()/LIKE neveikia su lietuviškomis raidėmis."""
    conn.create_function(
        "py_casefold", 1, lambda value: value.casefold() if value is not None else None,
        deterministic=True,
    )
