import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.services.github_client import fetch_issues, parse_repository

# Atnaujinami tik šaltinio metaduomenys. category_label, complexity_label,
# priority_label, annotation_source ir annotated_at čia sąmoningai nekeičiami,
# todėl žmogaus patvirtintos žymos pakartotinio importo metu išsaugomos.
_UPSERT_SQL = """
INSERT INTO github_issues (
    repository_full_name, issue_number, title, body, state, html_url,
    labels_json, github_created_at, github_updated_at, is_pull_request,
    imported_at
) VALUES (
    :repository, :number, :title, :body, :state, :html_url,
    :labels_json, :created_at, :updated_at, 0, :imported_at
)
ON CONFLICT (repository_full_name, issue_number) DO UPDATE SET
    title = excluded.title,
    body = excluded.body,
    state = excluded.state,
    html_url = excluded.html_url,
    labels_json = excluded.labels_json,
    github_created_at = excluded.github_created_at,
    github_updated_at = excluded.github_updated_at,
    imported_at = excluded.imported_at
"""
_EXISTS_SQL = (
    "SELECT 1 FROM github_issues "
    "WHERE repository_full_name = ? AND issue_number = ?"
)


@dataclass
class ImportResult:
    imported: int = 0
    updated: int = 0
    skipped_pull_requests: int = 0
    failed: int = 0


def run_import(
    conn: sqlite3.Connection,
    repository: str,
    limit: int,
    token: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    full_name = parse_repository(repository)
    fetched = fetch_issues(full_name, limit, token=token, transport=transport)
    return save_issues(conn, full_name, fetched.issues, fetched.skipped_pull_requests)


def save_issues(
    conn: sqlite3.Connection,
    repository: str,
    issues: list[object],
    skipped_pull_requests: int = 0,
) -> ImportResult:
    result = ImportResult(skipped_pull_requests=skipped_pull_requests)
    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:  # viena transakcija: commit sėkmės atveju, kitaip rollback
        for issue in issues:
            try:
                row = _normalize(issue)
            except ValueError:
                result.failed += 1
                continue
            row.update(repository=repository, imported_at=imported_at)
            exists = conn.execute(_EXISTS_SQL, (repository, row["number"])).fetchone()
            conn.execute(_UPSERT_SQL, row)
            if exists:
                result.updated += 1
            else:
                result.imported += 1
    return result


def _normalize(issue: object) -> dict[str, object]:
    if not isinstance(issue, dict):
        raise ValueError("issue nėra objektas")
    number = issue.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError("neteisingas issue numeris")
    title = issue.get("title")
    state = issue.get("state")
    html_url = issue.get("html_url")
    body = issue.get("body") or ""
    if not all(isinstance(value, str) for value in (title, state, html_url, body)):
        raise ValueError("trūksta privalomų tekstinių laukų")
    if not html_url.startswith("https://github.com/"):
        raise ValueError("neleistina issue nuoroda")

    labels = [
        label["name"]
        for label in issue.get("labels") or []
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    ]
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": state,
        "html_url": html_url,
        "labels_json": json.dumps(labels, ensure_ascii=False),
        "created_at": _optional_text(issue.get("created_at")),
        "updated_at": _optional_text(issue.get("updated_at")),
    }


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None
