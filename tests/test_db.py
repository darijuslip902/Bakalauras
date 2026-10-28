import sqlite3
from pathlib import Path

import pytest

from app.db import connect, get_connection, init_db

INSERT_ISSUE = (
    "INSERT INTO github_issues (repository_full_name, issue_number, title, state, "
    "html_url, imported_at) VALUES (?, ?, 'T', 'open', 'https://github.com/o/r/issues/1', 'now')"
)


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_init_db_creates_separate_tables(tmp_path: Path) -> None:
    with get_connection(tmp_path / "nested" / "test.sqlite3") as conn:
        init_db(conn)
        assert {"bug_reports", "github_issues"} <= _tables(conn)


def test_init_db_is_safe_to_repeat_and_keeps_data(tmp_path: Path) -> None:
    with get_connection(tmp_path / "test.sqlite3") as conn:
        init_db(conn)
        with conn:
            conn.execute(INSERT_ISSUE, ("o/r", 1))
        init_db(conn)
        assert conn.execute("SELECT COUNT(*) FROM github_issues").fetchone()[0] == 1


def test_issue_is_unique_per_repository_and_number_case_insensitive(tmp_path: Path) -> None:
    conn = connect(tmp_path / "test.sqlite3")
    init_db(conn)
    conn.execute(INSERT_ISSUE, ("Owner/Repo", 1))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(INSERT_ISSUE, ("owner/repo", 1))
    conn.execute(INSERT_ISSUE, ("owner/repo", 2))  # kitas numeris leidžiamas
    conn.close()
