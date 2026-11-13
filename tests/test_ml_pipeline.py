"""5B etapas: rinkimas pagal šaltinius, bandomasis / testavimo rinkiniai, klasių analizė,
papildymas, ataskaita. GitHub ir Claude API visada imituojami – jokių tinklo ar mokamų užklausų.
"""

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

import httpx
import pytest

from app.db import connect, init_db
from app.ml import ai_labeling, class_analysis, data_quality, training
from app.ml.collection import Source, SourcesError, check_sources, import_sources, load_sources
from app.ml.reporting import markdown_report
from app.services.annotation_service import next_unlabeled_id, save_annotation
from app.services.import_service import save_issues
from tests.test_ml import GOOD, MODEL, FakeClient, Response, _add_labelled, conn, ids, make_issue  # noqa: F401
from tools import ai_label, class_report, collect, pipeline, select_test_set

PROJECT_SOURCES = Path(__file__).resolve().parent.parent / "tools" / "sources.json"


class FakeGitHub:
    """Imituotas GitHub: kiekvienai (repozitorija, etiketė) – paruoštas issues sąrašas."""

    def __init__(self, data: dict[tuple[str, str | None], list[dict]] | None = None,
                 status: dict[str, int] | None = None) -> None:
        self.data = data or {}
        self.status = status or {}
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        repository = "/".join(request.url.path.split("/")[2:4])
        if repository in self.status:
            code = self.status[repository]
            headers = {"x-ratelimit-remaining": "0"} if code == 403 else {}
            return httpx.Response(code, headers=headers)
        assert "authorization" not in request.headers  # be GitHub autentifikacijos
        issues = self.data.get((repository, request.url.params.get("labels")), [])
        page = int(request.url.params["page"])
        per_page = int(request.url.params["per_page"])
        return httpx.Response(200, json=issues[(page - 1) * per_page: page * per_page])


def issues_for(repository: str, numbers: range, label: str = "bug", **extra) -> list[dict]:
    return [
        {**make_issue(n, f"{repository} problem {n}", f"Detailed description of defect {n} in {repository}."),
         "html_url": f"https://github.com/{repository}/issues/{n}",
         "labels": [{"name": label}], **extra}
        for n in numbers
    ]


def write_sources(tmp_path: Path, base: list[dict], augment: dict | None = None) -> Path:
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"base": base, "augment": augment or {}}), encoding="utf-8")
    return path


# --- Schema ir importo kilmė --------------------------------------------------


def test_old_database_gets_pilot_and_source_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(db_path)
    old.execute("CREATE TABLE github_issues (id INTEGER PRIMARY KEY, title TEXT, is_test_set INTEGER DEFAULT 0)")
    old.execute("INSERT INTO github_issues (id, title, is_test_set) VALUES (1, 'Senas', 1)")
    old.commit()
    old.close()

    conn = connect(db_path)
    init_db(conn)
    row = conn.execute("SELECT title, is_test_set, is_pilot_set, source_kind FROM github_issues").fetchone()
    conn.close()

    assert tuple(row) == ("Senas", 1, 0, "base")


def test_source_kind_is_set_only_for_new_issues(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(1)])
    save_issues(conn, "owner/repo", [make_issue(1), make_issue(2)], source_kind="augmentation")

    kinds = dict(conn.execute("SELECT issue_number, source_kind FROM github_issues"))
    assert kinds == {1: "base", 2: "augmentation"}
    with pytest.raises(ValueError):
        save_issues(conn, "owner/repo", [make_issue(3)], source_kind="other")


# --- Kokybės filtras ------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "excluded"),
    [("enhancement", True), ("Type: Feature Request", True), ("question", True), ("duplicate", True),
     ("wontfix", True), ("status: invalid", True), ("bug", False), ("documentation", False),
     ("kind/bug", False), ("Performance", False)],
)
def test_non_bug_labels_are_excluded_before_ai(conn: sqlite3.Connection, label: str, excluded: bool) -> None:
    save_issues(conn, "owner/repo", [{**make_issue(1), "labels": [{"name": "bug"}, {"name": label}]}])

    result = data_quality.check_quality(conn)

    assert (result.excluded_label_ids == ids(conn)) is excluded
    assert (result.ok_ids == ids(conn)) is not excluded


@pytest.mark.parametrize(
    "label",
    ["feature: files", "Feature:ES|QL", "Needs Discussion", "under-discussion", "OS-unsupported", "unsupported"],
)
def test_benign_extra_labels_do_not_exclude_real_bugs(label: str) -> None:
    assert data_quality.excluded_label(json.dumps(["bug", label])) is None


@pytest.mark.parametrize(
    "label",
    ["enhancement", "feature request", "Type: Feature", "feature", "question", "Duplicate Report",
     "duplicate", "wontfix", "invalid", "support", "proposal", "discussion", "not a bug", "Discussion: feature"],
)
def test_real_non_bug_labels_still_excluded(label: str) -> None:
    assert data_quality.excluded_label(json.dumps(["bug", label])) == label


def test_mixed_labels_exclude_only_for_the_real_non_bug_label() -> None:
    assert data_quality.excluded_label(json.dumps(["feature: files", "Needs Discussion", "bug"])) is None
    assert data_quality.excluded_label(json.dumps(["feature: files", "enhancement"])) == "enhancement"
    assert data_quality.excluded_label(json.dumps(["Needs Discussion", "question"])) == "question"
    assert data_quality.excluded_label(None) is None
    assert data_quality.excluded_label("not json") is None


# --- Bandomasis ir testavimo rinkiniai -----------------------------------------


def _three_repositories(conn: sqlite3.Connection) -> None:
    save_issues(conn, "aaa/big", issues_for("aaa/big", range(1, 61)))
    save_issues(conn, "bbb/mid", issues_for("bbb/mid", range(1, 31)))
    save_issues(conn, "ccc/small", issues_for("ccc/small", range(1, 11)))


def test_test_set_is_proportional_by_repository(conn: sqlite3.Connection) -> None:
    _three_repositories(conn)

    assert data_quality.select_test_set(conn, 20, seed=42) == 20

    counts = dict(conn.execute(
        "SELECT repository_full_name, COUNT(*) FROM github_issues WHERE is_test_set = 1 GROUP BY 1"))
    assert counts == {"aaa/big": 12, "bbb/mid": 6, "ccc/small": 2}


def test_pilot_and_test_sets_are_disjoint_and_exclude_augmentation(conn: sqlite3.Connection) -> None:
    _three_repositories(conn)
    save_issues(conn, "ddd/aug", issues_for("ddd/aug", range(1, 51)), source_kind="augmentation")

    data_quality.select_test_set(conn, 30, seed=1)
    data_quality.select_pilot_set(conn, 30, seed=1)
    data_quality.select_test_set(conn, 40, seed=1)  # vėlesnis papildymas į testą

    rows = conn.execute("SELECT is_test_set, is_pilot_set, source_kind FROM github_issues").fetchall()
    assert sum(r[0] for r in rows) == 40
    assert sum(r[1] for r in rows) == 30
    assert not any(r[0] and r[1] for r in rows)
    assert not any((r[0] or r[1]) and r[2] == "augmentation" for r in rows)


def test_set_selection_is_reproducible(tmp_path: Path) -> None:
    chosen = []
    for name in ("a", "b"):
        connection = connect(tmp_path / f"{name}.sqlite3")
        init_db(connection)
        _three_repositories(connection)
        data_quality.select_test_set(connection, 15, seed=7)
        data_quality.select_pilot_set(connection, 10, seed=7)
        chosen.append(connection.execute(
            "SELECT repository_full_name, issue_number, is_test_set, is_pilot_set FROM github_issues "
            "WHERE is_test_set = 1 OR is_pilot_set = 1 ORDER BY 1, 2").fetchall())
        connection.close()
    assert chosen[0] == chosen[1]


def test_next_unlabeled_offers_pilot_then_test(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 4)])
    first, second, third = ids(conn)
    with conn:
        conn.execute("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", (second,))
        conn.execute("UPDATE github_issues SET is_pilot_set = 1 WHERE id = ?", (third,))

    assert next_unlabeled_id(conn) == third
    save_annotation(conn, third, {"category_label": "ui", "complexity_label": "low",
                                  "priority_label": "P3_low", "training_suitability": "suitable"})
    assert next_unlabeled_id(conn) == second


def test_training_list_filters_pilot_set(tmp_path: Path) -> None:
    from tests.test_annotations import URL, TrainingApp

    app = TrainingApp(tmp_path / "ui.sqlite3")
    save_issues(app.conn, "owner/repo", [make_issue(1, "Bandomasis įrašas"), make_issue(2, "Kitas įrašas")])
    first, _ = ids(app.conn)
    with app.conn:
        app.conn.execute("UPDATE github_issues SET is_pilot_set = 1 WHERE id = ?", (first,))

    pilot_only = app.client.get(f"{URL}?test_set=pilot").text
    others = app.client.get(f"{URL}?test_set=no").text

    assert "Bandomasis įrašas</a>" in pilot_only and "Kitas įrašas" not in pilot_only
    assert "badge pilot-set" in pilot_only
    assert "Kitas įrašas</a>" in others and "Bandomasis įrašas" not in others
    assert "Bandomasis rinkinys" in app.client.get(f"{URL}/{first}").text
    app.conn.close()


# --- DI žymėjimas pagal rinkinį ir faktinė kaina -----------------------------


def test_ai_labelling_can_target_pilot_set_only(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 7)])
    first, second, *_ = ids(conn)
    with conn:
        conn.execute("UPDATE github_issues SET is_pilot_set = 1 WHERE id IN (?, ?)", (first, second))
    client = FakeClient()

    summary = ai_labeling.run_labelling(conn, client, MODEL, 10, 1.0, 10.0, progress=lambda _: None,
                                        subset="pilot")

    assert summary.labelled == 2
    assert {row[0] for row in conn.execute("SELECT github_issue_id FROM ai_annotations")} == {first, second}
    training_only = data_quality.select_for_ai_labelling(conn, MODEL, "v1", 10, 2, "training")
    assert len(training_only) == 4
    with pytest.raises(ValueError):
        data_quality.select_for_ai_labelling(conn, MODEL, "v1", 10, 2, "everything")


def test_measured_cost_comes_from_real_usage(conn: sqlite3.Connection) -> None:
    assert ai_labeling.measured_cost_per_request(conn, MODEL) is None
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 4)])
    ai_labeling.run_labelling(conn, FakeClient(), MODEL, 3, 1.0, 10.0, progress=lambda _: None)

    cost, requests = ai_labeling.measured_cost_per_request(conn, MODEL)

    assert requests == 3
    assert cost == pytest.approx(ai_labeling.total_spent_usd(conn) / 3)
    assert ai_labeling.measured_cost_per_request(conn, "claude-sonnet-5-5") is None


def test_ai_label_cli_subset_dry_run(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "cli.sqlite3"
    connection = connect(db_path)
    init_db(connection)
    save_issues(connection, "owner/repo", [make_issue(n) for n in range(1, 6)])
    with connection:
        connection.execute("UPDATE github_issues SET is_pilot_set = 1 WHERE issue_number IN (1, 2)")
    connection.close()
    monkeypatch.setattr(ai_label, "_create_client", lambda: pytest.fail("dry-run neturi kurti kliento"))

    assert ai_label.main(["--db", str(db_path), "--subset", "pilot"]) == 0

    output = capsys.readouterr().out
    assert "Atrinkta žymėjimui: 2" in output
    assert "Faktinės kainos dar nėra" in output


# --- Šaltinių failas ir rinkimas -------------------------------------------------


def test_project_sources_file_is_valid_and_diverse() -> None:
    sources = load_sources(PROJECT_SOURCES)

    repositories = {source.repository for source in sources.base}
    assert 10 <= len(repositories) <= 15
    assert 2000 <= sum(source.limit for source in sources.base) <= 3500
    assert all(source.label for source in sources.base)
    assert all(field in training.FIELDS for field, _ in sources.augment)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ({"base": [{"repo": "https://evil.example/a/b"}]}, "base[0]"),
        ({"base": [{"repo": "owner/repo", "limit": 5000}]}, "limit"),
        ({"base": [{"repo": "owner/repo", "label": ""}]}, "label"),
        ({"base": [], "augment": {"category_label:frontend": []}}, "nežinoma klasė"),
        ({"base": [], "augment": {"bad": []}}, "nežinoma klasė"),
        ({"augment": {}}, "base"),
    ],
)
def test_invalid_sources_are_rejected(tmp_path: Path, content: dict, message: str) -> None:
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(content), encoding="utf-8")

    with pytest.raises(SourcesError, match=re.escape(message)):
        load_sources(path)


def test_check_sources_reports_empty_labels_and_errors() -> None:
    github = FakeGitHub({("good/repo", "bug"): issues_for("good/repo", range(1, 3))}, {"missing/repo": 404})
    sources = [Source("good/repo", "bug", 10), Source("good/repo", "Bug", 10), Source("missing/repo", "bug", 10)]

    results = check_sources(sources, transport=github.transport())

    assert [item["status"] for item in results] == ["ok", "empty", "error"]
    assert all(request.url.host == "api.github.com" for request in github.requests)


def test_import_sources_continues_after_error_and_stops_on_rate_limit(conn: sqlite3.Connection) -> None:
    github = FakeGitHub({("a/one", "bug"): issues_for("a/one", range(1, 4)),
                         ("c/three", "bug"): issues_for("c/three", range(1, 4))},
                        {"b/two": 404, "d/limited": 403})
    sources = [Source("a/one", "bug", 10), Source("b/two", "bug", 10), Source("d/limited", "bug", 10),
               Source("c/three", "bug", 10)]
    messages: list[str] = []

    totals = import_sources(conn, sources, "base", transport=github.transport(), progress=messages.append)

    assert totals == {"imported": 3, "updated": 0, "skipped_sources": 0, "failed_sources": 2}
    assert any("limitas" in message for message in messages)
    assert not any(request.url.path.startswith("/repos/c/three") for request in github.requests)


# --- Tęstinis rinkimas: baigti šaltiniai praleidžiami -----------------------------


def _repo_paths(github: FakeGitHub) -> list[str]:
    return [request.url.path for request in github.requests]


def _issue_count(connection: sqlite3.Connection) -> tuple[int, int]:
    """(visų eilučių, skirtingų (repozitorija, numeris) porų) skaičius."""
    return tuple(connection.execute(  # type: ignore[return-value]
        "SELECT COUNT(*), COUNT(DISTINCT lower(repository_full_name) || '#' || issue_number) FROM github_issues"
    ).fetchone())


def test_import_sources_skips_completed_and_resumes_after_rate_limit(conn: sqlite3.Connection) -> None:
    sources = [Source("a/one", "bug", 10), Source("d/limited", "bug", 10), Source("c/three", "bug", 10)]
    first = FakeGitHub({("a/one", "bug"): issues_for("a/one", range(1, 4)),
                        ("c/three", "bug"): issues_for("c/three", range(1, 4))}, {"d/limited": 403})

    totals = import_sources(conn, sources, "base", transport=first.transport(), progress=lambda _: None)

    assert totals == {"imported": 3, "updated": 0, "skipped_sources": 0, "failed_sources": 1}
    assert not any(path.startswith("/repos/c/three") for path in _repo_paths(first))

    second = FakeGitHub({("a/one", "bug"): issues_for("a/one", range(1, 4)),
                         ("d/limited", "bug"): issues_for("d/limited", range(1, 3)),
                         ("c/three", "bug"): issues_for("c/three", range(1, 4))})
    messages: list[str] = []
    totals = import_sources(conn, sources, "base", transport=second.transport(), progress=messages.append)

    assert totals == {"imported": 5, "updated": 0, "skipped_sources": 1, "failed_sources": 0}
    assert not any(path.startswith("/repos/a/one") for path in _repo_paths(second))  # baigtas – nelieskite
    assert any("a/one [bug]: praleistas" in message for message in messages)
    assert _issue_count(conn) == (8, 8)


def test_failed_source_is_retried_next_time(conn: sqlite3.Connection) -> None:
    source = Source("b/two", "bug", 10)
    broken = FakeGitHub(status={"b/two": 404})
    import_sources(conn, [source], "base", transport=broken.transport(), progress=lambda _: None)
    assert conn.execute("SELECT COUNT(*) FROM collection_progress").fetchone()[0] == 0

    fixed = FakeGitHub({("b/two", "bug"): issues_for("b/two", range(1, 3))})
    totals = import_sources(conn, [source], "base", transport=fixed.transport(), progress=lambda _: None)

    assert totals["imported"] == 2 and totals["skipped_sources"] == 0
    assert conn.execute("SELECT COUNT(*) FROM collection_progress").fetchone()[0] == 1


def test_same_repository_with_different_labels_is_tracked_separately(conn: sqlite3.Connection) -> None:
    bug = Source("r/x", "bug", 10)
    security = Source("r/x", "security", 10)
    data = {("r/x", "bug"): issues_for("r/x", range(1, 4)),
            ("r/x", "security"): issues_for("r/x", range(11, 14), label="security")}
    import_sources(conn, [bug], "base", transport=FakeGitHub(data).transport(), progress=lambda _: None)

    second = FakeGitHub(data)
    totals = import_sources(conn, [bug, security], "base", transport=second.transport(), progress=lambda _: None)

    assert totals["skipped_sources"] == 1 and totals["imported"] == 3
    assert [request.url.params.get("labels") for request in second.requests] == ["security"]
    assert conn.execute("SELECT COUNT(*) FROM collection_progress WHERE repository_full_name = 'r/x'").fetchone()[0] == 2
    assert _issue_count(conn) == (6, 6)


def test_source_without_label_filter_is_tracked_separately_from_labelled(conn: sqlite3.Connection) -> None:
    labelled = Source("r/x", "bug", 3)
    unlabelled = Source("r/x", None, 5)
    data = {("r/x", "bug"): issues_for("r/x", range(1, 4)), ("r/x", None): issues_for("r/x", range(1, 6))}
    import_sources(conn, [labelled], "base", transport=FakeGitHub(data).transport(), progress=lambda _: None)

    github = FakeGitHub(data)
    totals = import_sources(conn, [labelled, unlabelled], "base", transport=github.transport(), progress=lambda _: None)

    assert totals["skipped_sources"] == 1
    assert len(github.requests) == 1 and "labels" not in github.requests[0].url.params


def test_larger_limit_collects_again_but_same_limit_does_not(conn: sqlite3.Connection) -> None:
    data = {("a/one", "bug"): issues_for("a/one", range(1, 8))}
    import_sources(conn, [Source("a/one", "bug", 3)], "base", transport=FakeGitHub(data).transport(),
                   progress=lambda _: None)

    same = FakeGitHub(data)
    import_sources(conn, [Source("a/one", "bug", 3)], "base", transport=same.transport(), progress=lambda _: None)
    larger = FakeGitHub(data)
    totals = import_sources(conn, [Source("a/one", "bug", 7)], "base", transport=larger.transport(),
                            progress=lambda _: None)

    assert same.requests == []
    assert totals["imported"] == 4 and totals["updated"] == 3
    assert conn.execute("SELECT completed_limit FROM collection_progress").fetchone()[0] == 7
    assert _issue_count(conn) == (7, 7)


def test_skip_completed_false_collects_everything_again(conn: sqlite3.Connection) -> None:
    data = {("a/one", "bug"): issues_for("a/one", range(1, 4))}
    source = Source("a/one", "bug", 10)
    import_sources(conn, [source], "base", transport=FakeGitHub(data).transport(), progress=lambda _: None)

    github = FakeGitHub(data)
    totals = import_sources(conn, [source], "base", transport=github.transport(), progress=lambda _: None,
                            skip_completed=False)

    assert totals == {"imported": 0, "updated": 3, "skipped_sources": 0, "failed_sources": 0}
    assert github.requests


def test_existing_database_rows_count_as_already_collected(conn: sqlite3.Connection) -> None:
    """DB, sukurta prieš tęstinio rinkimo funkciją: pakanka jau esamų įrašų, būsenos lentelė tuščia."""
    save_issues(conn, "A/One", issues_for("a/one", range(1, 6)))
    assert conn.execute("SELECT COUNT(*) FROM collection_progress").fetchone()[0] == 0
    github = FakeGitHub({("a/one", "bug"): issues_for("a/one", range(1, 7))})
    sources = [Source("a/one", "bug", 5), Source("a/one", None, 5), Source("a/one", "security", 1),
               Source("a/one", "bug", 6)]

    totals = import_sources(conn, sources, "base", transport=github.transport(), progress=lambda _: None)

    # Pirmi du (limitas 5, yra 5) praleisti; kitos etiketės ir didesnis limitas renkami.
    assert totals["skipped_sources"] == 2
    assert [request.url.params.get("labels") for request in github.requests] == ["security", "bug"]
    assert _issue_count(conn) == (6, 6)


def test_init_db_adds_progress_table_to_old_database_and_keeps_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    first = connect(db_path)
    init_db(first)
    save_issues(first, "owner/repo", [make_issue(1), make_issue(2)])
    first.execute("UPDATE github_issues SET category_label = 'backend' WHERE issue_number = 1")
    first.commit()
    first.execute("DROP TABLE collection_progress")  # senos versijos DB neturi šios lentelės
    first.commit()
    first.close()

    reopened = connect(db_path)
    init_db(reopened)
    init_db(reopened)  # pakartotinis inicializavimas saugus

    tables = {row[0] for row in reopened.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    rows = reopened.execute("SELECT issue_number, category_label FROM github_issues ORDER BY issue_number").fetchall()
    reopened.close()
    assert "collection_progress" in tables
    assert [tuple(row) for row in rows] == [(1, "backend"), (2, None)]


def test_collect_cli_resumes_after_rate_limit(tmp_path: Path, capsys) -> None:
    path = write_sources(tmp_path, [{"repo": "a/one", "label": "bug", "limit": 10},
                                    {"repo": "b/two", "label": "bug", "limit": 10},
                                    {"repo": "c/three", "label": "bug", "limit": 10}])
    db_path = tmp_path / "resume.sqlite3"
    data = {("a/one", "bug"): issues_for("a/one", range(1, 4)),
            ("b/two", "bug"): issues_for("b/two", range(1, 4)),
            ("c/three", "bug"): issues_for("c/three", range(1, 4))}
    args = ["--db", str(db_path), "--sources", str(path)]

    limited = FakeGitHub(data, {"b/two": 403})
    assert collect.main(args, transport=limited.transport()) == 1
    assert "Paleiskite tą pačią komandą vėliau" in capsys.readouterr().out

    resumed = FakeGitHub(data)
    assert collect.main(args, transport=resumed.transport()) == 0
    output = capsys.readouterr().out
    assert "a/one [bug]: praleistas – jau surinktas" in output
    assert "praleistų (jau surinktų) šaltinių: 1" in output
    assert not any(p.startswith("/repos/a/one") for p in _repo_paths(resumed))

    refreshed = FakeGitHub(data)
    assert collect.main([*args, "--refresh"], transport=refreshed.transport()) == 0
    assert {p.split("/")[2] for p in _repo_paths(refreshed)} == {"a", "b", "c"}

    connection = connect(db_path)
    assert _issue_count(connection) == (9, 9)  # jokių dublikatų
    connection.close()


def test_collect_cli_check_and_base_import(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "turi-buti-nenaudojamas")
    github = FakeGitHub({("a/one", "bug"): issues_for("a/one", range(1, 6)),
                         ("b/two", "kind/bug"): issues_for("b/two", range(1, 4))})
    path = write_sources(tmp_path, [{"repo": "a/one", "label": "bug", "limit": 5},
                                    {"repo": "b/two", "label": "kind/bug", "limit": 3}])
    db_path = tmp_path / "collect.sqlite3"

    assert collect.main(["--sources", str(path), "--check"], transport=github.transport()) == 0
    assert "Visi šaltiniai tinkami" in capsys.readouterr().out
    assert collect.main(["--db", str(db_path), "--sources", str(path)], transport=github.transport()) == 0

    connection = connect(db_path)
    assert connection.execute("SELECT COUNT(*) FROM github_issues WHERE source_kind = 'base'").fetchone()[0] == 8
    connection.close()


def test_collect_cli_check_follows_github_301_redirect(tmp_path: Path, capsys) -> None:
    """facebook/react: /repos/... -> 301 -> /repositories/<id>/issues turi būti sėkmingai patikrintas."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/repos/facebook/react/issues":
            return httpx.Response(301, headers={"location": "https://api.github.com/repositories/10270250/issues"})
        assert request.url.path == "/repositories/10270250/issues"
        assert request.url.params["labels"] == "Type: Bug"
        assert "authorization" not in request.headers
        return httpx.Response(200, json=issues_for("facebook/react", range(1, 3), label="Type: Bug"))

    path = write_sources(tmp_path, [{"repo": "facebook/react", "label": "Type: Bug", "limit": 5}])

    assert collect.main(["--sources", str(path), "--check"], transport=httpx.MockTransport(handler)) == 0

    output = capsys.readouterr().out
    assert "OK facebook/react [Type: Bug]" in output
    assert "Visi šaltiniai tinkami" in output
    assert len(requests) == 2


def test_collect_cli_reports_bad_source_file(tmp_path: Path, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")

    assert collect.main(["--sources", str(path), "--check"]) == 2
    assert "KLAIDA" in capsys.readouterr().out


# --- Klasių analizė ir papildymas -------------------------------------------------


def test_class_overview_covers_all_three_fields(conn: sqlite3.Connection) -> None:
    _add_labelled(conn, 30)

    overview = class_analysis.class_overview(conn, MODEL, "v1", target=8)

    assert set(overview["fields"]) == set(training.FIELDS)
    categories = {item["value"]: item for item in overview["fields"]["category_label"]}
    assert categories["ui"]["train"] == 10 and categories["ui"]["missing"] == 0
    assert categories["security"]["train"] == 0 and categories["security"]["missing"] == 8
    priorities = {item["value"]: item["train"] for item in overview["fields"]["priority_label"]}
    assert priorities == {"P0_critical": 0, "P1_high": 15, "P2_medium": 0, "P3_low": 15}
    shortages = class_analysis.deficits(overview)
    assert ("complexity_label", "low", 0) not in shortages
    assert {(f, v) for f, v, _ in shortages} >= {("category_label", "security"), ("priority_label", "P0_critical")}


def test_class_analysis_never_assigns_labels(conn: sqlite3.Connection) -> None:
    _add_labelled(conn, 12)
    before = conn.execute("SELECT * FROM ai_annotations ORDER BY id").fetchall()
    human_before = conn.execute("SELECT category_label, complexity_label, priority_label FROM github_issues").fetchall()

    class_analysis.class_overview(conn, MODEL, "v1", target=100)

    assert conn.execute("SELECT * FROM ai_annotations ORDER BY id").fetchall() == before
    assert conn.execute(
        "SELECT category_label, complexity_label, priority_label FROM github_issues").fetchall() == human_before


def test_augmentation_plan_lists_classes_without_source() -> None:
    augment = {("category_label", "security"): [Source("s/sec", "security", 50)]}
    shortages = [("category_label", "security", 10), ("complexity_label", "high", 5)]

    selected, without_source = class_analysis.augmentation_plan(shortages, augment)

    assert selected == [Source("s/sec", "security", 50)]
    assert without_source == [("complexity_label", "high")]


def test_collect_augment_imports_only_deficient_classes(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "aug.sqlite3"
    connection = connect(db_path)
    init_db(connection)
    _add_labelled(connection, 30)
    connection.close()
    github = FakeGitHub({("s/sec", "security"): issues_for("s/sec", range(1, 6), label="security"),
                         ("u/ui", "ui"): issues_for("u/ui", range(1, 6), label="ui")})
    path = write_sources(tmp_path, [{"repo": "a/one", "label": "bug"}], {
        "category_label:security": [{"repo": "s/sec", "label": "security", "limit": 5}],
        "category_label:ui": [{"repo": "u/ui", "label": "ui", "limit": 5}],  # ui netrūksta
    })

    code = collect.main(["--db", str(db_path), "--sources", str(path), "--augment", "--target", "8"],
                        transport=github.transport())

    output = capsys.readouterr().out
    assert code == 0
    assert "complexity_label" not in output or "šaltinio nėra" in output
    connection = connect(db_path)
    rows = connection.execute("SELECT repository_full_name, source_kind FROM github_issues "
                              "WHERE source_kind = 'augmentation'").fetchall()
    connection.close()
    assert {row[0] for row in rows} == {"s/sec"}
    assert len(rows) == 5
    assert all("/repos/u/ui" not in str(request.url) for request in github.requests)


def test_collect_augment_requires_existing_labels(tmp_path: Path, capsys) -> None:
    path = write_sources(tmp_path, [{"repo": "a/one", "label": "bug"}])

    assert collect.main(["--db", str(tmp_path / "x.sqlite3"), "--sources", str(path), "--augment"]) == 2
    assert "pirmiausia atlikite DI žymėjimą" in capsys.readouterr().out


def test_pilot_agreement_compares_ai_with_human(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 5)])
    issue_ids = ids(conn)
    with conn:
        conn.executemany("UPDATE github_issues SET is_pilot_set = 1 WHERE id = ?", [(i,) for i in issue_ids])
    human = [("ui", "low", "P2_medium", "suitable"), ("security", "high", "P0_critical", "suitable"),
             (None, None, None, "unsuitable"), ("ui", "low", "P2_medium", "unreviewed")]
    for issue_id, (category, complexity, priority, suitability) in zip(issue_ids, human):
        save_annotation(conn, issue_id, {"category_label": category, "complexity_label": complexity,
                                         "priority_label": priority, "training_suitability": suitability})
    ai_labeling.run_labelling(conn, FakeClient(), MODEL, 10, 1.0, 10.0, progress=lambda _: None,
                              subset="pilot")  # DI visiems atsako GOOD (ui, low, P2_medium, suitable)

    result = class_analysis.pilot_agreement(conn, MODEL, "v1")

    assert (result["pilot_total"], result["compared"]) == (4, 3)  # neįvertintas neskaičiuojamas
    assert result["suitability"]["accuracy"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["fields"]["category_label"]["accuracy"] == 0.5
    assert result["fields"]["category_label"]["samples"] == 2


def test_class_report_cli(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "report.sqlite3"
    connection = connect(db_path)
    init_db(connection)
    _add_labelled(connection, 30)
    connection.close()

    assert class_report.main(["--db", str(db_path), "--target", "8"]) == 0

    output = capsys.readouterr().out
    for title in ("Kategorija", "Sudėtingumas", "Prioritetas"):
        assert title in output
    assert "TRŪKSTA 8" in output
    assert "nepriskiriamos dirbtinai" in output
    assert "Palyginimo dar nėra" in output


# --- Mokymas: bandomasis rinkinys, CI ir ataskaita -------------------------------


def test_pilot_set_is_used_for_training_but_not_for_final_test(conn: sqlite3.Connection) -> None:
    train_ids = _add_labelled(conn, 40)
    with conn:
        conn.execute("UPDATE github_issues SET is_pilot_set = 1 WHERE id = ?", (train_ids[0],))

    train, human_test, _, _ = training.load_datasets(conn, MODEL, "v1")

    assert train_ids[0] in {example.issue_id for example in train}
    assert train_ids[0] not in {example.issue_id for example in human_test}


def _with_human_test(conn: sqlite3.Connection, count: int, start: int = 500) -> list[int]:
    test_ids = _add_labelled(conn, count, start=start, repository="test/repo")
    with conn:
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in test_ids])
    for issue_id in test_ids:
        row = conn.execute("SELECT category_label, complexity_label, priority_label FROM ai_annotations "
                           "WHERE github_issue_id = ?", (issue_id,)).fetchone()
        save_annotation(conn, issue_id, {"category_label": row[0], "complexity_label": row[1],
                                         "priority_label": row[2], "training_suitability": "suitable"})
    return test_ids


def test_report_has_ci_and_flags_missing_test_classes(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _add_labelled(conn, 90)
    _with_human_test(conn, 6)

    report = training.train_all(conn, tmp_path / "models", MODEL, "v1")

    test = report["fields"]["category_label"]["human_test"]
    low, high = test["ci95"]["accuracy"]
    assert 0 <= low <= test["model"]["accuracy"] <= high <= 1
    assert test["class_support"] == {"backend_api": 2, "database_data": 2, "ui": 2}
    assert test["classes_with_few_test_samples"] == ["backend_api", "database_data", "ui"]
    complexity = report["fields"]["complexity_label"]["human_test"]
    assert set(complexity["classes_without_test_samples"]) | set(complexity["class_support"]) == {"low", "medium", "high"}


def test_macro_f1_ignores_classes_absent_from_evaluated_sample() -> None:
    metrics = training.classification_metrics(["a", "a", "b"], ["a", "a", "b"], ["a", "b", "c"])

    assert metrics["macro_f1"] == 1.0
    assert metrics["confusion_matrix"]["labels"] == ["a", "b", "c"]


def test_bootstrap_ci_is_deterministic() -> None:
    truth = ["a", "b", "a", "b", "a", "a", "b", "b"]
    predicted = ["a", "b", "b", "b", "a", "a", "a", "b"]

    assert training.bootstrap_ci(truth, predicted, 42) == training.bootstrap_ci(truth, predicted, 42)


def test_markdown_report_contains_required_sections(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _add_labelled(conn, 90)
    _with_human_test(conn, 9)
    save_issues(conn, "aug/repo", [make_issue(1)], source_kind="augmentation")

    training.train_all(conn, tmp_path / "models", MODEL, "v1")
    text = (tmp_path / "models" / training.MARKDOWN_REPORT_FILE).read_text(encoding="utf-8")

    for heading in ("## Duomenų kilmė", "## DI žymėjimo metodika", "## Kategorija", "## Sudėtingumas",
                    "## Prioritetas", "## Apribojimai"):
        assert heading in text
    for phrase in ("Accuracy", "Macro-F1", "Precision", "Recall", "daugumos klasės baseline",
                   "klaidų matrica", "95 % CI", "claude-haiku-5-5", "aug/repo", "Tikra \\ Prognozė"):
        assert phrase in text, phrase
    assert "mokymo duomenyse visai nėra klasių" in text  # pvz. security
    assert "Bandomojo rinkinio įrašai" in text


def test_markdown_report_explains_insufficient_data() -> None:
    report = {
        "model_version": "v", "trained_at": "t", "seed": 42, "validation_size": 0.2, "method": "m",
        "ai_labels": {"model": MODEL, "prompt_version": "v1"}, "dataset": {}, "provenance": [],
        "ai_labelling_summary": {},
        "fields": {field: {"status": "insufficient_data", "message": "Reikia bent 30 pavyzdžių",
                           "class_distribution": {}, "excluded_classes_below_min": {}, "min_class_samples": 5}
                   for field in training.FIELDS},
    }

    text = markdown_report(report)

    assert text.count("Modelis neapmokytas") == 3
    assert "modelis neapmokytas – Reikia bent 30 pavyzdžių" in text


# --- Visa nemokama eiga viena komanda --------------------------------------------


def test_pipeline_runs_all_free_steps(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_label, "_create_client", lambda: pytest.fail("pipeline neturi kviesti DI API"))
    github = FakeGitHub({("a/one", "bug"): issues_for("a/one", range(1, 41)),
                         ("b/two", "bug"): issues_for("b/two", range(1, 21))
                         + issues_for("b/two", range(21, 25), label="enhancement")})
    path = write_sources(tmp_path, [{"repo": "a/one", "label": "bug", "limit": 40},
                                    {"repo": "b/two", "label": "bug", "limit": 24}])
    monkeypatch.setattr(collect, "DEFAULT_SOURCES", path)
    db_path = tmp_path / "pipeline.sqlite3"

    assert pipeline.main(["--db", str(db_path), "--test-size", "12", "--pilot-size", "6"],
                         transport=github.transport()) == 0

    output = capsys.readouterr().out
    assert "ne klaidų etiketės: 4" in output
    assert "Bandomasis: 6" in output and "testavimo: 12" in output
    assert "Faktinės kainos dar nėra" in output
    assert "--subset pilot" in output
    connection = connect(db_path)
    assert connection.execute("SELECT COUNT(*) FROM ai_annotations").fetchone()[0] == 0
    counts = Counter(row[0] for row in connection.execute(
        "SELECT repository_full_name FROM github_issues WHERE is_test_set = 1"))
    connection.close()
    assert counts == {"a/one": 8, "b/two": 4}

    # Pakartotinis paleidimas nekeičia jau atrinktų rinkinių.
    assert pipeline.main(["--db", str(db_path), "--skip-import", "--test-size", "12", "--pilot-size", "6"]) == 0
    assert "(nauji 0)" in capsys.readouterr().out


def test_select_test_set_cli_creates_both_sets(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "sets.sqlite3"
    connection = connect(db_path)
    init_db(connection)
    save_issues(connection, "owner/repo", [make_issue(n) for n in range(1, 21)])
    connection.close()

    assert select_test_set.main(["--db", str(db_path), "--size", "8", "--pilot-size", "5"]) == 0

    output = capsys.readouterr().out
    assert "Iš viso testavimo rinkinyje: 8" in output
    assert "Iš viso bandomajame rinkinyje: 5" in output


# --- 5C: masinis DI žymėjimas: klaidos, tęstinumas, lygiagretumas ------------------


def api_error(status: int | None = None) -> Exception:
    """Imituota API klaida; `status_code` nustato, ar tai įrašo, ar bendra (raktas, limitas) klaida."""
    error = anthropic_error("boom")
    if status is not None:
        error.status_code = status
    return error


def anthropic_error(message: str) -> Exception:
    import anthropic

    return anthropic.APIError(message, httpx.Request("POST", "https://api.anthropic.com/v1/messages"), body=None)


def cycling_responses(count: int) -> list[Response]:
    categories, complexities, priorities = list(ai_labeling.CATEGORIES), list(ai_labeling.COMPLEXITIES), \
        list(ai_labeling.PRIORITIES)
    return [
        Response({**GOOD, "category": categories[n % 3], "complexity": complexities[(n // 3) % 3],
                  "priority": priorities[n % 2]})
        for n in range(count)
    ]


def run(conn: sqlite3.Connection, client: FakeClient, limit: int = 100, **kwargs):
    return ai_labeling.run_labelling(conn, client, MODEL, limit, 1.0, 10.0, progress=lambda _: None, **kwargs)


def test_item_error_marks_only_that_issue_and_run_continues(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 5)])
    client = FakeClient([Response(GOOD), api_error(400), Response(GOOD), Response(GOOD)])

    summary = run(conn, client)

    assert (summary.labelled, summary.invalid, summary.stopped_reason) == (3, 1, None)
    rows = conn.execute("SELECT status, error, cost_usd FROM ai_annotations ORDER BY github_issue_id").fetchall()
    assert [r["status"] for r in rows] == ["ok", "invalid", "ok", "ok"]
    assert "400" in rows[1]["error"] and rows[1]["cost_usd"] == 0
    assert len(client.requests) == 4


@pytest.mark.parametrize("status", [None, 401, 429, 500, 529])
def test_general_api_errors_stop_the_whole_run(conn: sqlite3.Connection, status: int | None) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 6)])
    client = FakeClient([Response(GOOD), api_error(status), Response(GOOD)])

    summary = run(conn, client)

    assert summary.stopped_reason == "API klaida: APIError"
    assert len(client.requests) == 2  # po klaidos naujos užklausos nebesiunčiamos
    assert conn.execute("SELECT COUNT(*) FROM ai_annotations").fetchone()[0] == 1  # klaidos įrašas neišsaugomas


def test_consecutive_failures_stop_run_and_retry_later(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 11)])
    client = FakeClient([api_error(400) for _ in range(10)])  # pvz. pasibaigę API kreditai

    summary = run(conn, client)

    assert len(client.requests) == ai_labeling.MAX_CONSECUTIVE_FAILURES
    assert "nesėkmingų užklausų iš eilės" in summary.stopped_reason
    # Nesėkmingi įrašai dar turi bandymų, todėl kitame paleidime bus bandomi iš naujo.
    again = data_quality.select_for_ai_labelling(conn, MODEL, "v1", 100, ai_labeling.MAX_ATTEMPTS)
    assert len(again) == 10


def test_success_resets_failure_streak(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 13)])
    errors = [api_error(400)] * (ai_labeling.MAX_CONSECUTIVE_FAILURES - 1)
    client = FakeClient(errors + [Response(GOOD)] + errors + [Response(GOOD)] * 3)

    summary = run(conn, client)

    assert summary.stopped_reason is None
    assert len(client.requests) == 12


def test_interrupted_run_keeps_saved_labels_and_resumes(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 6)])
    seen: list[str] = []

    def interrupt_after_second(message: str) -> None:  # Ctrl+C pagrindinėje gijoje po antro įrašo
        seen.append(message)
        if len(seen) == 2:
            raise KeyboardInterrupt

    summary = ai_labeling.run_labelling(conn, FakeClient(), MODEL, 100, 1.0, 10.0, progress=interrupt_after_second)

    assert "Ctrl+C" in summary.stopped_reason
    assert conn.execute("SELECT COUNT(*) FROM ai_annotations WHERE status = 'ok'").fetchone()[0] == 2
    second_client = FakeClient()
    resumed = run(conn, second_client)
    assert resumed.labelled == 3 and len(second_client.requests) == 3  # pažymėti du nekartojami
    assert conn.execute("SELECT COUNT(*) FROM ai_annotations").fetchone()[0] == 5


def test_concurrent_run_labels_every_issue_once(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 21)])
    client = FakeClient(cycling_responses(20))

    summary = run(conn, client, workers=4)

    assert (summary.labelled, summary.invalid, summary.stopped_reason) == (20, 0, None)
    assert len(client.requests) == 20
    rows = conn.execute("SELECT github_issue_id FROM ai_annotations").fetchall()
    assert len({r[0] for r in rows}) == 20
    assert summary.run_cost_usd == pytest.approx(ai_labeling.total_spent_usd(conn))


def test_concurrent_run_never_exceeds_run_budget(conn: sqlite3.Connection) -> None:
    from tests.test_ml import Usage

    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 11)])
    issue = conn.execute("SELECT * FROM github_issues").fetchone()
    worst = ai_labeling.worst_case_cost_usd(MODEL, issue)
    price = ai_labeling.PRICES_USD_PER_MTOK[MODEL]
    # Atsakymas, kainuojantis (beveik) tiek, kiek blogiausias atvejis: be talpyklos nuolaidos, maksimali išvestis.
    write_tokens = int((worst * 1_000_000 - ai_labeling.MAX_OUTPUT_TOKENS * price["output"]) / price["cache_write"])
    client = FakeClient([Response(GOOD, usage=Usage(0, ai_labeling.MAX_OUTPUT_TOKENS, write_tokens, 0))
                         for _ in range(10)])

    summary = ai_labeling.run_labelling(conn, client, MODEL, 10, worst * 2.5, 10.0, progress=lambda _: None,
                                        workers=4)

    assert summary.stopped_reason.startswith("pasiekta šio paleidimo riba")
    assert len(client.requests) == 2  # trečia netelpa: dviejų vykdomų užklausų rezervas įskaičiuotas
    assert summary.run_cost_usd <= worst * 2.5


def test_concurrent_fatal_error_still_saves_finished_requests(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 9)])
    client = FakeClient([Response(GOOD), api_error(429)] + cycling_responses(6))

    summary = run(conn, client, workers=3)

    assert summary.stopped_reason == "API klaida: APIError"
    saved = conn.execute("SELECT COUNT(*) FROM ai_annotations").fetchone()[0]
    assert saved == summary.labelled >= 1
    assert len(client.requests) <= 3  # nauji darbai po klaidos nebepaleidžiami


def test_subset_status_counts_only_quality_ok_records(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 8)] + [make_issue(8, "Short", "tiny")])
    all_ids = ids(conn)
    with conn:
        conn.execute("UPDATE github_issues SET is_pilot_set = 1 WHERE id = ?", (all_ids[0],))
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in all_ids[1:3]])
    run(conn, FakeClient(), limit=2, subset="pilot")
    run(conn, FakeClient(), limit=1, subset="test")

    status = ai_labeling.subset_status(conn, MODEL, "v1")

    assert status["pilot"] == {"total": 1, "labelled": 1, "failed": 0, "remaining": 0}
    assert status["test"] == {"total": 2, "labelled": 1, "failed": 0, "remaining": 1}
    assert status["training"] == {"total": 4, "labelled": 0, "failed": 0, "remaining": 4}  # trumpas neįtrauktas


def test_ai_label_cli_validates_workers_and_prints_status(tmp_path: Path, capsys,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "w.sqlite3"
    connection = connect(db_path)
    init_db(connection)
    save_issues(connection, "owner/repo", [make_issue(n) for n in range(1, 5)])
    connection.close()
    monkeypatch.setattr(ai_label, "_create_client", lambda: pytest.fail("be --execute klientas nekuriamas"))

    with pytest.raises(SystemExit):
        ai_label.main(["--db", str(db_path), "--workers", "0"])
    assert ai_label.main(["--db", str(db_path), "--workers", "3"]) == 0

    output = capsys.readouterr().out
    assert "Pažanga" in output and "training" in output and "DRY-RUN" in output

    client = FakeClient()
    assert ai_label.main(["--db", str(db_path), "--execute", "--yes", "--workers", "3"], client=client) == 0
    assert len(client.requests) == 4
    assert "liko     0" in capsys.readouterr().out


# --- 5C: testavimo rinkinys su DI žymomis ir pilnas kelias iki mokymo ----------------


def test_test_set_with_ai_labels_only_is_reference_and_stays_out_of_training(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    train_ids = _add_labelled(conn, 90)
    test_ids = _add_labelled(conn, 12, start=300, repository="test/repo")
    with conn:
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in test_ids])
        conn.execute("UPDATE ai_annotations SET training_suitability = 'unsuitable' WHERE github_issue_id = ?",
                     (test_ids[0],))

    train, test, ai_on_test, stats = training.load_datasets(conn, MODEL, "v1")

    assert {e.issue_id for e in train} == set(train_ids)
    assert {e.issue_id for e in test} == set(test_ids[1:])  # DI „netinka“ įrašas į testą neįtrauktas
    assert {e.label_source for e in test} == {"ai"} and ai_on_test == []
    assert (stats["test_labels_ai"], stats["test_set_not_usable"]) == (11, 1)

    report = training.train_all(conn, tmp_path / "models", MODEL, "v1")
    field = report["fields"]["category_label"]["human_test"]
    assert field["reference"] == "ai" and field["reference_counts"] == {"ai": 11}
    text = (tmp_path / "models" / training.MARKDOWN_REPORT_FILE).read_text(encoding="utf-8")
    assert "DI žymos" in text and "atitikimą DI žymoms" in text


def test_human_test_labels_override_ai_in_test_set(conn: sqlite3.Connection) -> None:
    _add_labelled(conn, 40)
    test_ids = _add_labelled(conn, 3, start=300, repository="test/repo")
    with conn:
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in test_ids])
    save_annotation(conn, test_ids[0], {"category_label": "security", "complexity_label": "high",
                                        "priority_label": "P0_critical", "training_suitability": "suitable"})
    save_annotation(conn, test_ids[1], {"category_label": None, "complexity_label": None,
                                        "priority_label": None, "training_suitability": "unsuitable"})

    _, test, ai_on_test, _ = training.load_datasets(conn, MODEL, "v1")

    by_id = {e.issue_id: e for e in test}
    assert by_id[test_ids[0]].labels["category_label"] == "security" and by_id[test_ids[0]].label_source == "human"
    assert test_ids[1] not in by_id  # žmogus pažymėjo „netinka“ – DI nepaisoma
    assert by_id[test_ids[2]].label_source == "ai"
    assert [e.issue_id for e in ai_on_test] == [test_ids[0]]


def test_claude_labels_flow_from_issue_to_training_without_test_leakage(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Visas kelias: issues → DI žymos (training, po to test) → mokymas tik iš DI žymų."""
    categories = {c: w for c, w in zip(ai_labeling.CATEGORIES, ("alpha", "bravo", "charlie", "delta", "echo"))}
    save_issues(conn, "owner/repo", [
        make_issue(n, f"Problem {n} {categories[ai_labeling.CATEGORIES[n % 3]]}",
                   f"{categories[ai_labeling.CATEGORIES[n % 3]]} defect description number {n} in detail")
        for n in range(1, 111)
    ])
    all_ids = ids(conn)
    test_ids, pilot_ids = all_ids[:12], all_ids[12:15]
    with conn:
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in test_ids])
        conn.executemany("UPDATE github_issues SET is_pilot_set = 1 WHERE id = ?", [(i,) for i in pilot_ids])

    run(conn, FakeClient(cycling_responses(3)), limit=3, subset="pilot")
    run(conn, FakeClient(cycling_responses(100)), limit=100, subset="training", workers=3)
    assert conn.execute("SELECT COUNT(*) FROM ai_annotations a JOIN github_issues g ON g.id = a.github_issue_id "
                        "WHERE g.is_test_set = 1").fetchone()[0] == 0  # test dar nežymėtas
    run(conn, FakeClient(cycling_responses(12)), limit=12, subset="test")

    train, test, _, stats = training.load_datasets(conn, MODEL, "v1")
    report = training.train_all(conn, tmp_path / "models", MODEL, "v1")

    assert {e.issue_id for e in test} == set(test_ids)
    assert not {e.issue_id for e in train} & set(test_ids)
    assert pilot_ids[0] in {e.issue_id for e in train}  # pilot žymos mokymui tinka
    assert len(train) == 98
    for field in ("category_label", "complexity_label", "priority_label"):
        assert report["fields"][field]["status"] == "trained", field
        assert report["fields"][field]["human_test"]["reference"] == "ai"
