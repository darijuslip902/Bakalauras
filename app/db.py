import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

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
"""

# Stulpeliai, pridėti vėlesniuose etapuose. Senoms DB jie pridedami ALTER TABLE
# komanda, todėl esami įrašai ir žymos išlieka.
_ADDED_COLUMNS = {
    ("github_issues", "training_suitability"): (
        "TEXT NOT NULL DEFAULT 'unreviewed' "
        "CHECK (training_suitability IN ('unreviewed', 'suitable', 'unsuitable'))"
    ),
    # Žmogaus patikrinto testavimo rinkinio narystė (5A etapas).
    ("github_issues", "is_test_set"): (
        "INTEGER NOT NULL DEFAULT 0 CHECK (is_test_set IN (0, 1))"
    ),
}


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


def add_casefold_function(conn: sqlite3.Connection) -> None:
    """SQL funkcija `py_casefold`: SQLite lower()/LIKE neveikia su lietuviškomis raidėmis."""
    conn.create_function(
        "py_casefold", 1, lambda value: value.casefold() if value is not None else None,
        deterministic=True,
    )
