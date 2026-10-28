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
    UNIQUE (repository_full_name, issue_number)
);
"""


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
