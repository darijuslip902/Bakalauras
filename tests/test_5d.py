"""5D: papildomo importo paruošimas – šaltinių failas, Search API skaičiai, didesni limitai,
DB atsarginė kopija ir artimų dublikatų apsauga. GitHub visada imituojamas (jokio tinklo)."""

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.db import connect, init_db
from app.ml import training
from app.ml.collection import MAX_LIMIT_PER_SOURCE, Source, SourcesError, check_sources, load_sources
from app.ml.leakage import near_duplicate_indices
from app.services.github_client import GitHubError, count_issues, fetch_issues
from tests.test_ml import MODEL, _add_labelled, conn, make_issue  # noqa: F401
from tests.test_ml_pipeline import FakeGitHub, issues_for, write_sources
from tools import collect
from tools._common import backup_database

ROOT = Path(__file__).resolve().parent.parent
SOURCES_5D = ROOT / "tools" / "sources_5d.json"
CATEGORIES = ("ui", "backend_api", "database_data", "security", "performance",
              "build_deployment", "documentation", "other")


# --- Šaltinių failas ------------------------------------------------------------


def test_sources_5d_file_is_valid_and_large_enough() -> None:
    sources = load_sources(SOURCES_5D)
    raw = json.loads(SOURCES_5D.read_text(encoding="utf-8"))["base"]

    assert sum(s.limit for s in sources.base) >= 15_000
    pairs = [(s.repository, s.label) for s in sources.base]
    assert len(pairs) == len(set(pairs))
    hints = {item["hint"] for item in raw}
    assert set(CATEGORIES) <= hints and "P0" in hints  # kiekviena kategorija ir P0 turi šaltinių
    assert all(item["hint"] in {*CATEGORIES, "P0"} for item in raw)


def test_sources_5d_does_not_repeat_existing_repository_label_pairs() -> None:
    old = {(s.repository, s.label) for s in load_sources(ROOT / "tools" / "sources.json").base}
    new = {(s.repository, s.label) for s in load_sources(SOURCES_5D).base}
    assert not old & new


def test_source_limit_up_to_3000_is_accepted_and_above_is_rejected(tmp_path: Path) -> None:
    assert MAX_LIMIT_PER_SOURCE == 3000
    ok = write_sources(tmp_path, [{"repo": "a/b", "label": "bug", "limit": 3000}])
    assert load_sources(ok).base[0].limit == 3000
    bad = write_sources(tmp_path, [{"repo": "a/b", "label": "bug", "limit": 3001}])
    with pytest.raises(SourcesError):
        load_sources(bad)


# --- Puslapiavimas iki 3000 -----------------------------------------------------


def test_fetch_issues_reads_more_than_ten_pages() -> None:
    fake = FakeGitHub({("a/b", "bug"): issues_for("a/b", range(1, 2601))})

    result = fetch_issues("a/b", 2500, transport=fake.transport(), labels="bug")

    assert len(result.issues) == 2500
    assert len(fake.requests) == 25


# --- Search API skaičiai --------------------------------------------------------


def _search_transport(total: int, seen: list[httpx.Request] | None = None, status: int = 200):
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path == "/search/issues":
            return httpx.Response(status, json={"total_count": total, "items": []})
        repository_issues = [issues_for("a/b", range(1, 2))[0]]
        return httpx.Response(200, json=repository_issues)
    return httpx.MockTransport(handle)


def test_count_issues_builds_fixed_host_query_and_returns_total() -> None:
    seen: list[httpx.Request] = []

    total = count_issues("a/b", "kind/bug", transport=_search_transport(1234, seen))

    assert total == 1234
    request = seen[0]
    assert request.url.host == "api.github.com" and request.url.path == "/search/issues"
    assert request.url.params["q"] == 'repo:a/b is:issue label:"kind/bug"'


@pytest.mark.parametrize(("repo", "label"), [("not a repo", "bug"), ("a/b", 'bad"label'), ("a/b", "x\ny")])
def test_count_issues_rejects_bad_input(repo: str, label: str) -> None:
    with pytest.raises(ValueError):
        count_issues(repo, label, transport=_search_transport(1))


def test_count_issues_reports_rate_limit() -> None:
    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"})

    with pytest.raises(GitHubError) as error:
        count_issues("a/b", "bug", transport=httpx.MockTransport(limited))
    assert "limitas" in error.value.message


def test_check_sources_with_counts_shows_total_and_warns_when_below_limit() -> None:
    pauses: list[int] = []
    sources = [Source("a/b", "bug", 100), Source("c/d", "bug", 5000)]

    results = check_sources(sources, transport=_search_transport(300), with_counts=True,
                            pause=lambda: pauses.append(1))

    assert [r["status"] for r in results] == ["ok", "ok"]
    assert results[0]["message"] == "iš viso issues (be PR): 300"
    assert "mažiau nei limit 5000" in results[1]["message"]
    assert pauses == [1]  # pauzė tik tarp Search užklausų


def test_check_without_counts_does_not_call_search() -> None:
    seen: list[httpx.Request] = []
    check_sources([Source("a/b", "bug", 10)], transport=_search_transport(9, seen))
    assert all(r.url.path != "/search/issues" for r in seen)


def test_collect_cli_check_counts(tmp_path: Path, capsys) -> None:
    path = write_sources(tmp_path, [{"repo": "a/b", "label": "bug", "limit": 10}])

    code = collect.main(["--sources", str(path), "--check", "--counts"], transport=_search_transport(42))

    assert code == 0 and "iš viso issues (be PR): 42" in capsys.readouterr().out


# --- DB atsarginė kopija ----------------------------------------------------------


def test_backup_database_copies_data_and_leaves_original_untouched(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "bakalauras.sqlite3"
    db_path.parent.mkdir()
    original = connect(db_path)
    init_db(original)
    with original:
        original.execute("INSERT INTO bug_reports (title, description, status, created_at, updated_at)"
                         " VALUES ('t', 'd', 'new', 'x', 'x')")
    original.close()
    before = db_path.read_bytes()

    backup = backup_database(db_path)

    assert backup is not None and backup.parent == db_path.parent / "backups" and backup != db_path
    copy = sqlite3.connect(backup)
    assert copy.execute("SELECT title FROM bug_reports").fetchall() == [("t",)]
    copy.close()
    assert db_path.read_bytes() == before


def test_backup_database_returns_none_when_db_missing(tmp_path: Path) -> None:
    assert backup_database(tmp_path / "nera.sqlite3") is None
    assert not (tmp_path / "backups").exists()


def test_collect_backs_up_existing_db_before_import_and_can_skip(tmp_path: Path, capsys) -> None:
    path = write_sources(tmp_path, [{"repo": "a/one", "label": "bug", "limit": 5}])
    db_path = tmp_path / "x.sqlite3"
    data = {("a/one", "bug"): issues_for("a/one", range(1, 4))}
    args = ["--db", str(db_path), "--sources", str(path)]

    collect.main(args, transport=FakeGitHub(data).transport())  # DB dar nėra – kopijos nėra
    assert not (tmp_path / "backups").exists()
    collect.main([*args, "--refresh"], transport=FakeGitHub(data).transport())
    assert len(list((tmp_path / "backups").glob("x-*.sqlite3"))) == 1
    assert "DB atsarginė kopija" in capsys.readouterr().out

    collect.main([*args, "--refresh", "--no-backup"], transport=FakeGitHub(data).transport())
    assert len(list((tmp_path / "backups").glob("x-*.sqlite3"))) == 1


# --- Artimi dublikatai ---------------------------------------------------------------


def test_near_duplicate_indices_finds_templated_copies_only() -> None:
    reference = ["Crash on startup\n\nTraceback most recent call last File main.py line 10 KeyError config"]
    candidates = [
        "Crash on startup\n\nTraceback most recent call last File main.py line 12 KeyError config",  # beveik tas pats
        "Slow query\n\nThe report page takes thirty seconds to load with many rows in the table",
    ]

    assert near_duplicate_indices(candidates, reference) == [0]
    assert near_duplicate_indices([], reference) == [] and near_duplicate_indices(candidates, []) == []


def test_training_drops_near_duplicates_of_test_texts_but_keeps_test(conn: sqlite3.Connection) -> None:
    train_ids = _add_labelled(conn, 30)
    test_ids = _add_labelled(conn, 3, start=500, repository="test/repo")
    twin = "Persistent failure of the export job\n\nThe nightly export job fails with timeout after ten minutes of work on large tables"
    with conn:
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in test_ids])
        conn.execute("UPDATE github_issues SET title = ?, body = ? WHERE id = ?",
                     (twin.split("\n\n")[0], twin.split("\n\n")[1], test_ids[0]))
        conn.execute("UPDATE github_issues SET title = ?, body = ? WHERE id = ?",
                     (twin.split("\n\n")[0], twin.split("\n\n")[1] + " today", train_ids[0]))

    train, test, _, stats = training.load_datasets(conn, MODEL, "v1")

    assert train_ids[0] not in {e.issue_id for e in train}
    assert stats["excluded_test_near_duplicates"] == 1
    assert {e.issue_id for e in test} == set(test_ids)  # testo rinkinys nekeičiamas
    assert {e.issue_id for e in train} == set(train_ids) - {train_ids[0]}
