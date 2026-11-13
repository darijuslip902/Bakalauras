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


# --- 5D (2 dalis): .env, apsauga nuo senų įrašų perrašymo, nauji testo įrašai ----------


def test_sources_5d_lists_only_verified_sources_and_respects_known_counts() -> None:
    sources = load_sources(SOURCES_5D).base
    pairs = {(s.repository, s.label): s.limit for s in sources}
    removed = {("microsoft/vscode", "ui-glitch"), ("mui/material-ui", "bug 🐛"), ("vuejs/core", "bug"),
               ("prisma/prisma", "kind/bug"), ("redis/redis", "bug"), ("OWASP/DependencyCheck", "bug"),
               ("flutter/flutter", "severe: performance"), ("docker/compose", "bug"),
               ("obsproject/obs-studio", "Bug"), ("ClickHouse/ClickHouse", "critical bug")}
    assert not removed & set(pairs)
    assert pairs[("nestjs/nest", "type: bug :sob:")] <= 217
    assert pairs[("expressjs/express", "bug")] <= 161
    assert pairs[("rust-lang/rust", "P-critical")] <= 257
    assert pairs[("pingcap/tidb", "severity/critical")] == 1289
    assert sum(pairs.values()) >= 15_000


def test_collect_loads_token_from_env_file_without_printing_it(tmp_path: Path, monkeypatch, capsys) -> None:
    from app import config

    secret = "ghp_testtokenvalue123"
    (tmp_path / ".env").write_text(f"GITHUB_TOKEN={secret}\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_DIR", tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=issues_for("a/b", range(1, 2)))

    path = write_sources(tmp_path, [{"repo": "a/b", "label": "bug", "limit": 5}])
    code = collect.main(["--sources", str(path), "--check", "--use-token"],
                        transport=httpx.MockTransport(handle))

    output = capsys.readouterr().out
    assert code == 0 and seen[0].headers["authorization"] == f"Bearer {secret}"
    assert secret not in output and "autentifikuota" in output and "~60" not in output


def test_collect_use_token_without_token_fails_clearly(tmp_path: Path, monkeypatch, capsys) -> None:
    from app import config

    monkeypatch.setattr(config, "PROJECT_DIR", tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    path = write_sources(tmp_path, [{"repo": "a/b", "label": "bug", "limit": 5}])

    assert collect.main(["--sources", str(path), "--check", "--use-token"]) == 2
    assert "GITHUB_TOKEN nerastas" in capsys.readouterr().out


def test_collect_without_token_says_unauthenticated(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    path = write_sources(tmp_path, [{"repo": "a/b", "label": "bug", "limit": 5}])
    collect.main(["--sources", str(path), "--check"], transport=FakeGitHub(
        {("a/b", "bug"): issues_for("a/b", range(1, 2))}).transport())
    assert "be autentifikacijos" in capsys.readouterr().out


def _protected_conn(tmp_path: Path):
    from app.services.import_service import save_issues

    c = connect(tmp_path / "p.sqlite3")
    init_db(c)
    save_issues(c, "o/r", [make_issue(n, f"Title {n}", f"Original body of issue {n} with details.")
                           for n in range(1, 6)])
    return c, save_issues


def test_reimport_never_overwrites_test_pilot_or_annotated_rows(tmp_path: Path) -> None:
    c, save_issues = _protected_conn(tmp_path)
    ids_ = [r[0] for r in c.execute("SELECT id FROM github_issues ORDER BY id")]
    with c:
        c.execute("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", (ids_[0],))
        c.execute("UPDATE github_issues SET is_pilot_set = 1 WHERE id = ?", (ids_[1],))
        c.execute("INSERT INTO ai_annotations (github_issue_id, model, prompt_version, status, created_at, updated_at)"
                  " VALUES (?, 'm', 'v1', 'ok', 'x', 'x')", (ids_[2],))
        c.execute("UPDATE github_issues SET category_label = 'ui' WHERE id = ?", (ids_[3],))
    before = c.execute("SELECT id, title, body, labels_json, imported_at FROM github_issues ORDER BY id").fetchall()

    result = save_issues(c, "o/r", [make_issue(n, f"CHANGED {n}", f"Edited body {n} on GitHub afterwards.")
                                    for n in range(1, 6)])

    after = c.execute("SELECT id, title, body, labels_json, imported_at FROM github_issues ORDER BY id").fetchall()
    assert [tuple(r) for r in after[:3]] == [tuple(r) for r in before[:3]]  # testo / pilot / DI pažymėti nepakito
    assert after[3]["title"] == "CHANGED 4" and after[4]["title"] == "CHANGED 5"  # kiti atnaujinami
    assert (result.protected, result.updated, result.imported) == (3, 2, 0)
    assert c.execute("SELECT category_label FROM github_issues WHERE id = ?", (ids_[3],)).fetchone()[0] == "ui"
    assert c.execute("SELECT COUNT(*) FROM ai_annotations").fetchone()[0] == 1


def test_overlapping_sources_do_not_duplicate_rows_and_keep_first_import_time(tmp_path: Path) -> None:
    c, save_issues = _protected_conn(tmp_path)
    first = c.execute("SELECT imported_at FROM github_issues WHERE issue_number = 1").fetchone()[0]
    c.execute("UPDATE github_issues SET imported_at = '2026-11-08T10:00:00+00:00'")
    c.commit()

    save_issues(c, "o/r", [make_issue(n, f"Title {n}", f"Original body of issue {n} with details.")
                           for n in range(3, 8)])  # persidengia 3–5, nauji 6–7

    assert c.execute("SELECT COUNT(*) FROM github_issues").fetchone()[0] == 7
    old = c.execute("SELECT imported_at FROM github_issues WHERE issue_number = 4").fetchone()[0]
    assert old == "2026-11-08T10:00:00+00:00" and first
    assert c.execute("SELECT imported_at FROM github_issues WHERE issue_number = 7").fetchone()[0] > old


def test_new_test_selection_uses_only_newly_imported_unlabelled_rows(tmp_path: Path) -> None:
    from app.ml.data_quality import select_test_set
    from app.services.import_service import save_issues

    c = connect(tmp_path / "t.sqlite3")
    init_db(c)
    old_train = _add_labelled(c, 20)                           # seni, pažymėti (mokymui)
    old_tests = _add_labelled(c, 3, start=100, repository="old/test")
    with c:
        c.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in old_tests])
        c.execute("UPDATE github_issues SET imported_at = '2026-11-08T10:00:00+00:00'")
    old_unlabelled = save_issues(c, "old/unlabelled",
                                 [make_issue(300 + n, f"Old {n}", f"Old unlabelled body number {n} long enough here.")
                                  for n in range(5)])
    with c:
        c.execute("UPDATE github_issues SET imported_at = '2026-11-08T10:00:00+00:00'")
    save_issues(c, "new/repo", [make_issue(n, f"New {n} fails", f"Brand new issue body number {n} with long text.")
                                for n in range(1, 31)])
    new_ids = {r[0] for r in c.execute("SELECT id FROM github_issues WHERE repository_full_name = 'new/repo'")}
    snapshot = [tuple(r) for r in c.execute(
        "SELECT id, title, body, is_test_set, is_pilot_set FROM github_issues WHERE id NOT IN (%s)"
        % ",".join(map(str, new_ids)))]

    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    added = select_test_set(c, 3 + 10, seed=7, new_since=today)

    chosen = {r[0] for r in c.execute("SELECT id FROM github_issues WHERE is_test_set = 1")}
    assert added == 10 and len(chosen) == 13
    assert set(old_tests) <= chosen and (chosen - set(old_tests)) <= new_ids  # nauji – tik iš naujų
    assert not chosen & set(old_train)
    after = [tuple(r) for r in c.execute(
        "SELECT id, title, body, is_test_set, is_pilot_set FROM github_issues WHERE id NOT IN (%s)"
        % ",".join(map(str, new_ids)))]
    assert after == snapshot and old_unlabelled.imported == 5  # seni įrašai nepakito


def test_pipeline_refuses_to_grow_existing_test_set_without_new_since(tmp_path: Path, capsys) -> None:
    from tools import pipeline

    db_path = tmp_path / "g.sqlite3"
    c = connect(db_path)
    init_db(c)
    ids_ = _add_labelled(c, 5)
    with c:
        c.execute("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", (ids_[0],))
    c.close()

    assert pipeline.main(["--db", str(db_path), "--skip-import", "--test-size", "50"]) == 2
    assert "--test-new-since" in capsys.readouterr().out
    c = connect(db_path)
    assert c.execute("SELECT COUNT(*) FROM github_issues WHERE is_test_set = 1").fetchone()[0] == 1
