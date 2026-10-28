import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.db import connect, init_db
from app.services.import_service import run_import, save_issues
from tests.test_github_client import make_issue, transport_for


@pytest.fixture
def conn(tmp_path: Path):
    connection = connect(tmp_path / "test.sqlite3")
    init_db(connection)
    yield connection
    connection.close()


def _count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM github_issues").fetchone()[0]


def test_run_import_saves_issues_and_skips_pull_requests(conn: sqlite3.Connection) -> None:
    pages = {1: [make_issue(1), make_issue(2, pull_request=True), make_issue(3)]}

    result = run_import(conn, "o/r", 10, transport=transport_for(pages))

    assert (result.imported, result.updated, result.skipped_pull_requests, result.failed) == (2, 0, 1, 0)
    assert _count(conn) == 2
    row = conn.execute("SELECT * FROM github_issues WHERE issue_number = 1").fetchone()
    assert row["repository_full_name"] == "o/r"
    assert row["is_pull_request"] == 0
    assert row["category_label"] is None


def test_labels_are_stored_as_json(conn: sqlite3.Connection) -> None:
    issue = make_issue(1) | {"labels": [{"name": "bug"}, {"name": "ui"}, "ignored"]}

    save_issues(conn, "o/r", [issue])

    stored = conn.execute("SELECT labels_json FROM github_issues").fetchone()[0]
    assert json.loads(stored) == ["bug", "ui"]


def test_reimport_does_not_create_duplicates(conn: sqlite3.Connection) -> None:
    pages = {1: [make_issue(1), make_issue(2)]}

    first = run_import(conn, "o/r", 10, transport=transport_for(pages))
    second = run_import(conn, "O/R", 10, transport=transport_for(pages))

    assert (first.imported, first.updated) == (2, 0)
    assert (second.imported, second.updated) == (0, 2)
    assert _count(conn) == 2


def test_reimport_updates_source_fields_but_keeps_human_labels(conn: sqlite3.Connection) -> None:
    save_issues(conn, "o/r", [make_issue(1)])
    with conn:
        conn.execute(
            "UPDATE github_issues SET category_label = ?, complexity_label = ?, "
            "priority_label = ?, annotation_source = ?, annotated_at = ?",
            ("bug", "medium", "high", "human", "2026-10-28T10:00:00+00:00"),
        )

    changed = make_issue(1) | {"title": "Renamed", "state": "closed"}
    result = save_issues(conn, "o/r", [changed])

    row = conn.execute("SELECT * FROM github_issues").fetchone()
    assert result.updated == 1
    assert (row["title"], row["state"]) == ("Renamed", "closed")
    assert (row["category_label"], row["complexity_label"], row["priority_label"]) == ("bug", "medium", "high")
    assert (row["annotation_source"], row["annotated_at"]) == ("human", "2026-10-28T10:00:00+00:00")


def test_malformed_items_are_counted_as_failed_and_do_not_stop_import(conn: sqlite3.Connection) -> None:
    bad_items = [
        "not an object",
        {"number": "1", "title": "x", "state": "open", "html_url": "https://github.com/o/r/issues/1"},
        make_issue(5) | {"html_url": "javascript:alert(1)"},
        make_issue(6) | {"title": None},
    ]

    result = save_issues(conn, "o/r", [*bad_items, make_issue(2)])

    assert (result.imported, result.failed) == (1, 4)
    assert _count(conn) == 1


def test_sql_injection_text_is_stored_literally(conn: sqlite3.Connection) -> None:
    title = "x'); DROP TABLE github_issues; --"

    save_issues(conn, "o/r", [make_issue(1) | {"title": title}])

    assert conn.execute("SELECT title FROM github_issues").fetchone()[0] == title


def test_github_error_leaves_database_unchanged(conn: sqlite3.Connection) -> None:
    from app.services.github_client import GitHubError

    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    with pytest.raises(GitHubError):
        run_import(conn, "o/r", 10, transport=transport)
    assert _count(conn) == 0
