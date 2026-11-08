"""5A etapas: duomenų kokybė, DI žymėjimas (be tikro API) ir modelių mokymas.

Visi API atsakymai čia imituojami; testai nesiunčia mokamų užklausų ir nenaudoja tinklo.
Mokymo testuose naudojami dirbtiniai tekstai – jie tikrina tik mechaniką, ne modelio kokybę.
"""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import anthropic
import httpx
import httpx2
import pytest

from app.db import connect, init_db
from app.ml import ai_labeling, data_quality, training
from app.ml.ai_labeling import (
    OUTPUT_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_request,
    parse_response,
    run_labelling,
    usage_cost_usd,
)
from app.services.annotation_service import save_annotation
from app.services.github_client import fetch_issues
from app.services.import_service import save_issues
from tools import ai_label, check_data, import_issues, select_test_set, train_models

MODEL = "claude-haiku-5-5"


def make_issue(number: int, title: str | None = None, body: str | None = None, labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "title": title or f"Issue {number}",
        "state": "open",
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "body": body if body is not None else f"Steps to reproduce problem number {number} in detail here.",
        "labels": [{"name": name} for name in labels or []],
    }


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "ml.sqlite3")
    init_db(connection)
    yield connection
    connection.close()


def ids(conn: sqlite3.Connection) -> list[int]:
    return [row[0] for row in conn.execute("SELECT id FROM github_issues ORDER BY id")]


# --- Imituotas Claude API ---------------------------------------------------


class Block:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text


class Usage:
    def __init__(self, input_tokens=400, output_tokens=60, cache_creation_input_tokens=0,
                 cache_read_input_tokens=750) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class Response:
    def __init__(self, payload: object, stop_reason: str = "end_turn", usage: Usage | None = None,
                 thinking: bool = True) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.content = ([Block("thinking")] if thinking else []) + [Block("text", text)]
        self.stop_reason = stop_reason
        self.usage = usage or Usage()


GOOD = {
    "reason": "The page crashes when clicking save.",
    "training_suitability": "suitable",
    "category": "ui",
    "complexity": "low",
    "priority": "P2_medium",
}


class FakeClient:
    """Pakeičia `anthropic.Anthropic()`: įrašo užklausas ir grąžina paruoštus atsakymus."""

    def __init__(self, responses: list | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[dict] = []
        self.messages = self

    def create(self, **request: object) -> Response:
        self.requests.append(request)
        item = self.responses.pop(0) if self.responses else Response(GOOD)
        if isinstance(item, Exception):
            raise item
        return item


# --- Schema ir GitHub importas ------------------------------------------------


def test_schema_has_ai_annotations_and_test_set_column(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    columns = {row[1] for row in conn.execute("PRAGMA table_info(github_issues)")}

    assert "ai_annotations" in tables
    assert "is_test_set" in columns


def test_old_database_gets_test_set_column(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(db_path)
    old.execute(
        "CREATE TABLE github_issues (id INTEGER PRIMARY KEY, repository_full_name TEXT, issue_number INTEGER,"
        " title TEXT, body TEXT, state TEXT, html_url TEXT, labels_json TEXT, imported_at TEXT,"
        " category_label TEXT, complexity_label TEXT, priority_label TEXT)"
    )
    old.execute("INSERT INTO github_issues (id, title, category_label) VALUES (1, 'Senas', 'ui')")
    old.commit()
    old.close()

    conn = connect(db_path)
    init_db(conn)
    row = conn.execute("SELECT title, category_label, is_test_set, training_suitability FROM github_issues").fetchone()
    conn.close()

    assert tuple(row) == ("Senas", "ui", 0, "unreviewed")


def test_github_label_filter_is_sent_as_query_parameter() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    fetch_issues("owner/repo", 10, transport=httpx.MockTransport(handler), labels="bug")
    fetch_issues("owner/repo", 10, transport=httpx.MockTransport(handler))

    assert seen[0].url.params["labels"] == "bug"
    assert seen[0].url.host == "api.github.com"
    assert "labels" not in seen[1].url.params
    with pytest.raises(ValueError):
        fetch_issues("owner/repo", 10, transport=httpx.MockTransport(handler), labels="bad\nlabel")


def test_bulk_import_cli_uses_mock_github(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        owner = request.url.path.split("/")[2]
        issues = [make_issue(1, f"{owner} klaida")] if request.url.params["page"] == "1" else []
        return httpx.Response(200, json=issues)

    db_path = tmp_path / "cli.sqlite3"
    code = import_issues.main(
        ["--db", str(db_path), "--repo", "first/repo", "--repo", "second/repo", "--repo", "bad",
         "--limit", "5", "--label", "bug"],
        transport=httpx.MockTransport(handler),
    )

    output = capsys.readouterr().out
    assert code == 1  # viena repozitorija neteisinga
    assert "first/repo: nauji 1" in output
    assert "second/repo: nauji 1" in output
    assert "bad: KLAIDA" in output
    conn = connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM github_issues").fetchone()[0] == 2
    conn.close()


# --- Duomenų kokybė ir atranka -----------------------------------------------


def test_quality_check_flags_short_bodies_and_duplicates(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [
        make_issue(1, "Crash", "The app crashes when saving a file with long name."),
        make_issue(2, "Short", "broken"),
        make_issue(3, "crash", "The  app crashes when saving a file with LONG name."),  # dublikatas
        make_issue(4, "Empty", ""),
    ])
    first, second, third, fourth = ids(conn)

    result = data_quality.check_quality(conn)

    assert result.ok_ids == [first]
    assert result.short_body_ids == [second, fourth]
    assert result.duplicate_ids == [third]


def test_selection_round_robins_repositories_and_skips_done(conn: sqlite3.Connection) -> None:
    save_issues(conn, "aaa/one", [make_issue(n) for n in range(1, 4)])
    save_issues(conn, "bbb/two", [make_issue(n, f"Two {n}") for n in range(1, 4)])
    a1, a2, a3, b1, b2, b3 = ids(conn)

    selected = data_quality.select_for_ai_labelling(conn, MODEL, PROMPT_VERSION, 4, 2)
    assert [row["id"] for row in selected] == [a1, b1, a2, b2]

    run_labelling(conn, FakeClient(), MODEL, 2, 1.0, 10.0, progress=lambda _: None)
    remaining = data_quality.select_for_ai_labelling(conn, MODEL, PROMPT_VERSION, 10, 2)
    assert [row["id"] for row in remaining] == [a2, b2, a3, b3]
    # Kitas modelis turi atskiras žymas.
    other = data_quality.select_for_ai_labelling(conn, "claude-sonnet-5-5", PROMPT_VERSION, 10, 2)
    assert len(other) == 6


def test_select_test_set_is_random_reproducible_and_keeps_existing(tmp_path: Path) -> None:
    results = []
    for name in ("a", "b"):
        conn = connect(tmp_path / f"{name}.sqlite3")
        init_db(conn)
        save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 21)] + [make_issue(99, body="x")])
        assert data_quality.select_test_set(conn, 5, seed=7) == 5
        assert data_quality.select_test_set(conn, 5, seed=7) == 0  # jau pakanka
        assert data_quality.select_test_set(conn, 8, seed=7) == 3
        chosen = [row[0] for row in conn.execute("SELECT issue_number FROM github_issues WHERE is_test_set = 1")]
        results.append(sorted(chosen))
        conn.close()

    assert results[0] == results[1]
    assert len(results[0]) == 8
    assert 99 not in results[0]  # per trumpas aprašymas netenka į testą


# --- DI užklausa ir atsakymo validavimas -------------------------------------


def test_request_is_economical_and_structured(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(1, "Crash", "x" * 9000, labels=["bug", "ui"])])
    issue = conn.execute("SELECT * FROM github_issues").fetchone()

    request = build_request(issue, MODEL)

    assert request["model"] == "claude-haiku-5-5"
    assert request["max_tokens"] == ai_labeling.MAX_OUTPUT_TOKENS
    assert "temperature" not in request
    assert request["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}}
    assert request["system"] == [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    user = request["messages"][0]["content"]
    assert "GitHub labels (hints only): bug, ui" in user
    assert "[truncated]" in user
    assert len(user) < ai_labeling.MAX_BODY_CHARS + 500


def test_system_prompt_is_long_enough_to_cache_and_lists_all_labels() -> None:
    # Haiku 5.5 talpina >= 512 tokenų prefiksą; ~4 simboliai tokenui.
    assert len(SYSTEM_PROMPT) / 4 > 600
    for value in (*ai_labeling.CATEGORIES, *ai_labeling.COMPLEXITIES, *ai_labeling.PRIORITIES):
        assert value in SYSTEM_PROMPT
    assert OUTPUT_SCHEMA["additionalProperties"] is False
    assert set(OUTPUT_SCHEMA["required"]) == set(OUTPUT_SCHEMA["properties"])


def test_parse_valid_response() -> None:
    labels, error = parse_response(Response(GOOD))

    assert error is None
    assert labels == {"training_suitability": "suitable", "category_label": "ui", "complexity_label": "low",
                      "priority_label": "P2_medium", "reason": GOOD["reason"]}


def test_unsuitable_response_stores_no_class_labels() -> None:
    labels, error = parse_response(Response({**GOOD, "training_suitability": "unsuitable"}))

    assert error is None
    assert labels["training_suitability"] == "unsuitable"
    assert labels["category_label"] is labels["complexity_label"] is labels["priority_label"] is None


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (Response({**GOOD, "category": "frontend"}), "category"),
        (Response({**GOOD, "priority": "P5"}), "priority"),
        (Response({k: v for k, v in GOOD.items() if k != "complexity"}), "complexity"),
        (Response({**GOOD, "training_suitability": "maybe"}), "training_suitability"),
        (Response({**GOOD, "reason": 5}), "reason"),
        (Response("ne json"), "JSON"),
        (Response("[1, 2]"), "objektas"),
        (Response(GOOD, stop_reason="refusal"), "refusal"),
        (Response(GOOD, stop_reason="max_tokens"), "max_tokens"),
    ],
)
def test_invalid_responses_are_rejected(response: Response, message: str) -> None:
    labels, error = parse_response(response)

    assert labels is None
    assert message in error


def test_response_without_text_block_is_rejected() -> None:
    response = Response(GOOD)
    response.content = [Block("thinking")]

    assert parse_response(response) == (None, "atsakyme nėra teksto bloko")


# --- Kaina ir biudžetas ------------------------------------------------------


def test_cost_uses_official_haiku_prices() -> None:
    tokens = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
              "cache_creation_input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000}

    assert usage_cost_usd("claude-haiku-5-5", tokens) == pytest.approx(0.10 + 0.50 + 0.125 + 0.01)
    assert usage_cost_usd("claude-sonnet-5-5", tokens) == pytest.approx(2.00 + 10.00 + 2.50 + 0.10)
    with pytest.raises(ai_labeling.LabellingError):
        usage_cost_usd("claude-unknown", tokens)


def test_estimates_are_conservative(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(1)])
    issue = conn.execute("SELECT * FROM github_issues").fetchone()

    expected = ai_labeling.expected_cost_usd(MODEL, issue)
    worst = ai_labeling.worst_case_cost_usd(MODEL, issue)

    assert 0 < expected < worst < 0.002  # vienas įrašas su Haiku – mažiau nei 0,2 cento


def test_run_stops_before_exceeding_run_budget(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 11)])
    issue = conn.execute("SELECT * FROM github_issues").fetchone()
    worst = ai_labeling.worst_case_cost_usd(MODEL, issue)
    # Brangus atsakymas: ilgas promptas be talpyklos ir maksimali išvestis.
    expensive = Usage(input_tokens=5000, output_tokens=1024, cache_read_input_tokens=0)
    client = FakeClient([Response(GOOD, usage=expensive) for _ in range(10)])

    summary = run_labelling(conn, client, MODEL, 10, max_cost_usd=worst * 2.5, total_budget_usd=10.0,
                            progress=lambda _: None)

    assert summary.stopped_reason.startswith("pasiekta šio paleidimo riba")
    assert 1 <= len(client.requests) < 10
    assert summary.run_cost_usd <= worst * 2.5


def test_run_respects_total_budget_across_runs(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 6)])
    run_labelling(conn, FakeClient(), MODEL, 2, 1.0, 10.0, progress=lambda _: None)
    spent = ai_labeling.total_spent_usd(conn)
    client = FakeClient()

    summary = run_labelling(conn, client, MODEL, 5, max_cost_usd=1.0, total_budget_usd=spent,
                            progress=lambda _: None)

    assert client.requests == []
    assert summary.stopped_reason.startswith("pasiektas bendras biudžetas")


def test_api_error_stops_run_without_more_requests(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 6)])
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    client = FakeClient([Response(GOOD), error, Response(GOOD)])

    summary = run_labelling(conn, client, MODEL, 5, 1.0, 10.0, progress=lambda _: None)

    assert len(client.requests) == 2
    assert summary.labelled == 1
    assert summary.stopped_reason == "API klaida: APIConnectionError"


# --- Išsaugojimas ir pakartotinis paleidimas --------------------------------


def test_labels_and_usage_are_saved_separately_from_human_labels(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(1), make_issue(2)])
    first, second = ids(conn)
    human = {"category_label": "security", "complexity_label": "high", "priority_label": "P0_critical",
             "training_suitability": "suitable"}
    save_annotation(conn, first, human)
    before = dict(conn.execute("SELECT * FROM github_issues WHERE id = ?", (first,)).fetchone())

    summary = run_labelling(conn, FakeClient(), MODEL, 10, 1.0, 10.0, progress=lambda _: None)

    assert summary.labelled == 2
    assert dict(conn.execute("SELECT * FROM github_issues WHERE id = ?", (first,)).fetchone()) == before
    row = conn.execute("SELECT * FROM ai_annotations WHERE github_issue_id = ?", (first,)).fetchone()
    assert (row["status"], row["category_label"], row["model"], row["prompt_version"]) == ("ok", "ui", MODEL, "v1")
    assert (row["input_tokens"], row["output_tokens"], row["cache_read_input_tokens"]) == (400, 60, 750)
    assert row["cost_usd"] == pytest.approx((400 * 0.10 + 60 * 0.50 + 750 * 0.01) / 1_000_000)
    assert row["reason"] == GOOD["reason"]


def test_rerun_does_not_duplicate_or_call_api_again(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(1), make_issue(2)])
    run_labelling(conn, FakeClient(), MODEL, 10, 1.0, 10.0, progress=lambda _: None)
    client = FakeClient()

    summary = run_labelling(conn, client, MODEL, 10, 1.0, 10.0, progress=lambda _: None)

    assert summary.selected == 0
    assert client.requests == []
    assert conn.execute("SELECT COUNT(*) FROM ai_annotations").fetchone()[0] == 2


def test_invalid_answer_is_retried_once_and_cost_accumulates(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(1)])
    run_labelling(conn, FakeClient([Response("ne json")]), MODEL, 1, 1.0, 10.0, progress=lambda _: None)
    first = dict(conn.execute("SELECT * FROM ai_annotations").fetchone())
    assert (first["status"], first["attempts"]) == ("invalid", 1)

    run_labelling(conn, FakeClient([Response("vėl ne json")]), MODEL, 1, 1.0, 10.0, progress=lambda _: None)
    second = dict(conn.execute("SELECT * FROM ai_annotations").fetchone())
    assert (second["status"], second["attempts"]) == ("invalid", 2)
    assert second["cost_usd"] == pytest.approx(first["cost_usd"] * 2)

    client = FakeClient()
    run_labelling(conn, client, MODEL, 1, 1.0, 10.0, progress=lambda _: None)
    assert client.requests == []  # MAX_ATTEMPTS pasiektas – daugiau nemokama


# --- CLI: dry-run ir apsaugos -------------------------------------------------


def _cli_db(tmp_path: Path, count: int = 3) -> Path:
    db_path = tmp_path / "cli.sqlite3"
    conn = connect(db_path)
    init_db(conn)
    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, count + 1)])
    conn.close()
    return db_path


def test_ai_label_cli_is_dry_run_by_default(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_label, "_create_client", lambda: pytest.fail("dry-run neturi kurti kliento"))
    db_path = _cli_db(tmp_path)

    code = ai_label.main(["--db", str(db_path), "--limit", "2"])

    output = capsys.readouterr().out
    assert code == 0
    assert "DRY-RUN" in output
    assert "Atrinkta žymėjimui: 2" in output
    conn = connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM ai_annotations").fetchone()[0] == 0
    conn.close()


def test_ai_label_cli_requires_confirmation_and_key(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _cli_db(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai_label, "_create_client", lambda: pytest.fail("be rakto klientas nekuriamas"))
    monkeypatch.setattr("app.config.load_env_file", lambda path: None)  # neskaityti tikro .env

    assert ai_label.main(["--db", str(db_path), "--execute"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out

    client = FakeClient()
    assert ai_label.main(["--db", str(db_path), "--execute"], client=client, ask=lambda _: "ne") == 1
    assert client.requests == []

    assert ai_label.main(["--db", str(db_path), "--execute", "--limit", "2"], client=client,
                         ask=lambda _: "taip") == 0
    assert len(client.requests) == 2
    assert "Pažymėta: 2" in capsys.readouterr().out


def test_ai_label_cli_rejects_unknown_model(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        ai_label.main(["--db", str(_cli_db(tmp_path)), "--model", "gpt-4"])


def test_check_data_and_select_test_set_cli(tmp_path: Path, capsys) -> None:
    db_path = _cli_db(tmp_path, 10)

    assert select_test_set.main(["--db", str(db_path), "--size", "4"]) == 0
    assert "Iš viso testavimo rinkinyje: 4" in capsys.readouterr().out
    assert check_data.main(["--db", str(db_path)]) == 0
    output = capsys.readouterr().out
    assert "owner/repo" in output
    assert "IŠ VISO" in output


# --- Mokymas ir vertinimas ----------------------------------------------------

# Dirbtiniai tekstai su aiškiais raktažodžiais – tik mechanikai patikrinti.
_CATEGORY_WORDS = {
    "ui": "button layout css render page click display",
    "backend_api": "api endpoint server response handler request json",
    "database_data": "database query migration table index sql record",
}
_COMPLEXITY_WORDS = {"low": "typo simple small", "medium": "several modules", "high": "architecture redesign"}
_PRIORITY_WORDS = {"P1_high": "many users blocked", "P3_low": "cosmetic minor"}


def _add_labelled(conn: sqlite3.Connection, count: int, start: int = 1, repository: str = "owner/repo") -> list[int]:
    issues, labels = [], []
    categories, complexities, priorities = list(_CATEGORY_WORDS), list(_COMPLEXITY_WORDS), list(_PRIORITY_WORDS)
    for offset in range(count):
        number = start + offset
        category = categories[number % 3]
        complexity = complexities[(number // 3) % 3]
        priority = priorities[number % 2]
        body = (f"{_CATEGORY_WORDS[category]} {_COMPLEXITY_WORDS[complexity]} "
                f"{_PRIORITY_WORDS[priority]} case {number}")
        issues.append(make_issue(number, f"Problem {number} {category}", body))
        labels.append((category, complexity, priority))
    save_issues(conn, repository, issues)
    new_ids = ids(conn)[-count:]
    now = "2026-11-08T10:00:00+00:00"
    with conn:
        for issue_id, (category, complexity, priority) in zip(new_ids, labels):
            conn.execute(
                "INSERT INTO ai_annotations (github_issue_id, model, prompt_version, status, training_suitability,"
                " category_label, complexity_label, priority_label, created_at, updated_at)"
                " VALUES (?, ?, ?, 'ok', 'suitable', ?, ?, ?, ?, ?)",
                (issue_id, MODEL, PROMPT_VERSION, category, complexity, priority, now, now),
            )
    return new_ids


def test_training_creates_three_models_and_report(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _add_labelled(conn, 90)
    output = tmp_path / "models"

    report = training.train_all(conn, output, MODEL, PROMPT_VERSION)

    for field in training.FIELDS:
        field_report = report["fields"][field]
        assert field_report["status"] == "trained"
        assert (output / f"{field}.joblib").exists()
        validation = field_report["validation"]
        assert set(validation) == {"model", "majority_baseline"}
        for key in ("accuracy", "macro_f1", "weighted_f1", "per_class", "confusion_matrix", "samples"):
            assert key in validation["model"]
        assert field_report["human_test"] is None  # testo rinkinio dar nėra
    saved = json.loads((output / training.REPORT_FILE).read_text(encoding="utf-8"))
    assert saved["seed"] == 42
    assert saved["dataset"]["train_rows"] == 90

    model = training.load_model(output / "category_label.joblib")
    assert model.predict(["the api endpoint returns a wrong json response"])[0] == "backend_api"


def test_training_is_deterministic(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _add_labelled(conn, 60)

    first = training.train_all(conn, tmp_path / "a", MODEL, PROMPT_VERSION)
    second = training.train_all(conn, tmp_path / "b", MODEL, PROMPT_VERSION)

    for field in training.FIELDS:
        assert first["fields"][field]["validation"] == second["fields"][field]["validation"]


def test_insufficient_data_is_reported_and_old_model_removed(conn: sqlite3.Connection, tmp_path: Path) -> None:
    output = tmp_path / "models"
    output.mkdir()
    (output / "category_label.joblib").write_text("senas")
    _add_labelled(conn, 12)

    report = training.train_all(conn, output, MODEL, PROMPT_VERSION)

    assert report["fields"]["category_label"]["status"] == "insufficient_data"
    assert not (output / "category_label.joblib").exists()


def test_rare_classes_are_excluded_and_reported(conn: sqlite3.Connection) -> None:
    train_ids = _add_labelled(conn, 60)
    with conn:
        conn.execute("UPDATE ai_annotations SET category_label = 'security' WHERE github_issue_id IN (?, ?)",
                     train_ids[:2])
    train, test, ai_test, _ = training.load_datasets(conn, MODEL, PROMPT_VERSION)

    _, report = training.train_field("category_label", train, test, ai_test)

    assert report["excluded_classes_below_min"] == {"security": 2}
    assert "security" not in report["classes"]


def test_test_set_is_never_used_for_training(conn: sqlite3.Connection, tmp_path: Path) -> None:
    train_ids = _add_labelled(conn, 60)
    test_ids = _add_labelled(conn, 12, start=200, repository="other/repo")
    with conn:
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in test_ids])
    for issue_id in test_ids[:9]:  # žmogus pažymėjo 9 iš 12 testo įrašų
        row = conn.execute("SELECT category_label, complexity_label, priority_label FROM ai_annotations"
                           " WHERE github_issue_id = ?", (issue_id,)).fetchone()
        save_annotation(conn, issue_id, {"category_label": row[0], "complexity_label": row[1],
                                         "priority_label": row[2], "training_suitability": "suitable"})

    train, human_test, ai_on_test, stats = training.load_datasets(conn, MODEL, PROMPT_VERSION)

    assert {example.issue_id for example in train} == set(train_ids)
    assert {example.issue_id for example in human_test} == set(test_ids[:9])
    assert len(ai_on_test) == 9
    assert stats["test_set_rows"] == 12

    report = training.train_all(conn, tmp_path / "models", MODEL, PROMPT_VERSION)
    field = report["fields"]["category_label"]
    assert field["human_test"]["model"]["samples"] == 9
    assert "Maža testo imtis" in field["human_test"]["warning"]
    assert field["ai_vs_human_agreement"]["accuracy"] == 1.0  # DI ir žmogus čia sutapo


def test_human_labels_override_ai_and_unsuitable_is_excluded(conn: sqlite3.Connection) -> None:
    first, second, third = _add_labelled(conn, 3)
    save_annotation(conn, first, {"category_label": "security", "complexity_label": None,
                                  "priority_label": None, "training_suitability": "unreviewed"})
    save_annotation(conn, second, {"category_label": None, "complexity_label": None,
                                   "priority_label": None, "training_suitability": "unsuitable"})
    with conn:
        conn.execute("UPDATE ai_annotations SET training_suitability = 'unsuitable' WHERE github_issue_id = ?",
                     (third,))

    train, _, _, stats = training.load_datasets(conn, MODEL, PROMPT_VERSION)

    assert [(e.issue_id, e.labels["category_label"]) for e in train] == [(first, "security")]
    assert stats["excluded_not_suitable"] == 2
    assert stats["human_labelled_used"] == 1


def test_training_ignores_other_model_and_invalid_ai_rows(conn: sqlite3.Connection) -> None:
    _add_labelled(conn, 5)
    with conn:
        conn.execute("UPDATE ai_annotations SET status = 'invalid' WHERE id = 1")
        conn.execute("UPDATE ai_annotations SET model = 'claude-sonnet-5-5' WHERE id = 2")

    train, _, _, _ = training.load_datasets(conn, MODEL, PROMPT_VERSION)

    assert len(train) == 3


def test_duplicate_of_test_text_is_removed_from_training(conn: sqlite3.Connection) -> None:
    save_issues(conn, "owner/repo", [make_issue(1, "Same", "Identical body text for the duplicate check.")])
    save_issues(conn, "other/repo", [make_issue(1, "same", "Identical  body text for the duplicate check.")])
    first, second = ids(conn)
    with conn:
        conn.execute("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", (second,))
    save_annotation(conn, first, {"category_label": "ui", "complexity_label": "low", "priority_label": "P3_low",
                                  "training_suitability": "suitable"})

    train, _, _, stats = training.load_datasets(conn, MODEL, PROMPT_VERSION)

    # Pirmasis įrašas lieka (jis originalas); antrasis yra testo rinkinyje.
    assert [e.issue_id for e in train] == [first]
    assert stats["test_set_rows"] == 1


def test_train_models_cli(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "train.sqlite3"
    conn = connect(db_path)
    init_db(conn)
    _add_labelled(conn, 60)
    conn.close()

    code = train_models.main(["--db", str(db_path), "--output-dir", str(tmp_path / "models")])

    output = capsys.readouterr().out
    assert code == 0
    assert "category_label: mokymas" in output
    assert "žmogaus testo rinkinio dar nėra" in output
    assert (tmp_path / "models" / training.REPORT_FILE).exists()


# --- Svetainės integracija ------------------------------------------------------


def test_website_does_not_import_ai_or_training_modules() -> None:
    app_dir = Path(__file__).resolve().parent.parent / "app"
    sources = "".join(path.read_text(encoding="utf-8") for path in app_dir.rglob("*.py")
                      if "ml" not in path.relative_to(app_dir).parts)
    assert "def create_app" in sources

    assert "anthropic" not in sources
    assert "app.ml" not in sources


def test_training_list_filters_and_marks_test_set(tmp_path: Path) -> None:
    from tests.test_annotations import URL, TrainingApp

    app = TrainingApp(tmp_path / "ui.sqlite3")
    save_issues(app.conn, "owner/repo", [make_issue(1, "Testo įrašas"), make_issue(2, "Mokymo įrašas")])
    first, second = ids(app.conn)
    with app.conn:
        app.conn.execute("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", (first,))

    only_test = app.client.get(f"{URL}?test_set=yes").text
    without_test = app.client.get(f"{URL}?test_set=no").text
    detail = app.client.get(f"{URL}/{first}").text

    assert "Testo įrašas</a>" in only_test and "Mokymo įrašas" not in only_test
    assert "Mokymo įrašas</a>" in without_test and "Testo įrašas" not in without_test
    assert "badge test-set" in only_test
    assert "Žmogaus testavimo rinkinys" in detail
    assert app.client.get(f"{URL}?test_set=maybe").text.count("Neteisinga filtro reikšmė") == 1
    app.conn.close()


def test_next_unlabeled_offers_test_set_first(conn: sqlite3.Connection) -> None:
    from app.services.annotation_service import next_unlabeled_id

    save_issues(conn, "owner/repo", [make_issue(n) for n in range(1, 5)])
    first, second, third, fourth = ids(conn)
    with conn:
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(second,), (fourth,)])

    assert next_unlabeled_id(conn) == second
    assert next_unlabeled_id(conn, second) == fourth
    save_annotation(conn, second, {"category_label": "ui", "complexity_label": "low",
                                   "priority_label": "P3_low", "training_suitability": "suitable"})
    save_annotation(conn, fourth, {"category_label": None, "complexity_label": None,
                                   "priority_label": None, "training_suitability": "unsuitable"})
    assert next_unlabeled_id(conn, fourth) == first  # testo rinkinys baigtas – toliau kiti
