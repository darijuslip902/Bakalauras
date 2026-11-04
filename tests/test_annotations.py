import json
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import connect, init_db
from app.main import create_app
from app.routes.issues import get_database_path, get_github_transport
from app.services import annotation_service
from app.services.annotation_service import (
    PER_PAGE,
    annotation_stats,
    next_unlabeled_id,
    save_annotation,
    validate_annotation,
)
from app.services.import_service import save_issues
from tests.auth_utils import csrf_token, login, use_test_auth

URL = "/dashboard/training-data"


def make_issue(number: int, title: str | None = None, body: str = "Aprašymas", **extra: object) -> dict:
    issue = {
        "number": number,
        "title": title or f"Issue {number}",
        "state": "open",
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "body": body,
        "labels": [],
        "created_at": f"2024-01-{number:02d}T10:00:00Z",
    }
    issue.update(extra)
    return issue


class TrainingApp:
    """Prisijungęs administratorius, laikina DB ir imituotas GitHub (be tinklo)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = connect(db_path)
        init_db(self.conn)
        self.github_issues: list[dict] = []
        app = create_app()
        app.dependency_overrides[get_database_path] = lambda: db_path
        app.dependency_overrides[get_github_transport] = lambda: httpx.MockTransport(
            lambda request: httpx.Response(
                200, json=self.github_issues if request.url.params["page"] == "1" else []
            )
        )
        use_test_auth(app)
        self.client = TestClient(app)
        login(self.client)
        self.csrf_token = csrf_token(self.client)

    def add(self, *issues: dict, repository: str = "owner/repo") -> list[int]:
        save_issues(self.conn, repository, list(issues))
        rows = self.conn.execute(
            "SELECT id FROM github_issues WHERE repository_full_name = ? ORDER BY id", (repository,)
        ).fetchall()
        return [row[0] for row in rows][-len(issues):]

    def row(self, issue_id: int) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM github_issues WHERE id = ?", (issue_id,)).fetchone()

    def annotate(self, issue_id: int, follow: bool = False, token: str | None = None, **fields: str):
        data = {"csrf_token": self.csrf_token if token is None else token, **fields}
        return self.client.post(f"{URL}/{issue_id}/annotation", data=data, follow_redirects=follow)


@pytest.fixture
def training(tmp_path: Path) -> Iterator[TrainingApp]:
    app = TrainingApp(tmp_path / "training.sqlite3")
    yield app
    app.conn.close()


def _titles(html: str) -> list[str]:
    return re.findall(r'href="/dashboard/training-data/\d+">([^<]+)</a>', html)


ALL_LABELS = {"category_label": "ui", "complexity_label": "low", "priority_label": "P2_medium"}


# --- Prieiga ----------------------------------------------------------------


def test_training_pages_require_login(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))
    anonymous = TestClient(training.client.app)

    for path in (URL, f"{URL}/{issue_id}", f"{URL}/next"):
        response = anonymous.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login")

    response = anonymous.post(
        f"{URL}/{issue_id}/annotation",
        data={**ALL_LABELS, "csrf_token": training.csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert training.row(issue_id)["category_label"] is None


def test_navigation_contains_training_data_link(training: TrainingApp) -> None:
    html = training.client.get("/dashboard").text

    assert 'href="/dashboard/training-data"' in html
    assert "Mokymo duomenys" in html


# --- Sąrašas ----------------------------------------------------------------


def test_list_shows_imported_issues(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(7, "Neveikia eksportas"))

    response = training.client.get(URL)

    assert response.status_code == 200
    html = response.text
    assert f'href="{URL}/{issue_id}">Neveikia eksportas</a>' in html
    assert "#7" in html
    assert "owner/repo" in html
    assert 'href="https://github.com/owner/repo/issues/7"' in html
    assert 'rel="noopener noreferrer"' in html
    assert "2024-01-07 10:00 UTC" in html
    assert "Nepažymėta" in html
    assert "Neįvertinta" in html


def test_empty_list_points_to_import(training: TrainingApp) -> None:
    html = training.client.get(URL).text

    assert "Importuotų GitHub issues dar nėra" in html
    assert 'href="/import"' in html


@pytest.fixture
def labelled(training: TrainingApp) -> list[int]:
    ids = training.add(
        make_issue(1, "Mygtukas neveikia", "Paspaudus NIEKO neįvyksta"),
        make_issue(2, "Lėta paieška", "Užklausa trunka 30 s"),
        make_issue(3, "Klausimas apie API", "Kaip naudoti?"),
        make_issue(4, "Šviesos tema", "Spalvos neteisingos"),
    )
    ids += training.add(make_issue(5, "Kito projekto klaida"), repository="other/project")
    save_annotation(training.conn, ids[0], {**ALL_LABELS, "training_suitability": "suitable"})
    save_annotation(
        training.conn, ids[1],
        {"category_label": "performance", "complexity_label": None, "priority_label": None,
         "training_suitability": "unreviewed"},
    )
    save_annotation(
        training.conn, ids[2],
        {"category_label": None, "complexity_label": None, "priority_label": None,
         "training_suitability": "unsuitable"},
    )
    return ids


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", ["Kito projekto klaida", "Šviesos tema", "Klausimas apie API", "Lėta paieška", "Mygtukas neveikia"]),
        ("sort=oldest", ["Mygtukas neveikia", "Lėta paieška", "Klausimas apie API", "Šviesos tema", "Kito projekto klaida"]),
        ("q=mygtukas", ["Mygtukas neveikia"]),
        ("q=nieko", ["Mygtukas neveikia"]),  # aprašyme, kitas raidžių dydis
        ("q=ŠVIESOS", ["Šviesos tema"]),  # lietuviškos raidės
        ("annotation=complete", ["Mygtukas neveikia"]),
        ("annotation=partial", ["Lėta paieška"]),
        ("annotation=unlabeled", ["Kito projekto klaida", "Šviesos tema", "Klausimas apie API"]),
        ("suitability=suitable", ["Mygtukas neveikia"]),
        ("suitability=unsuitable", ["Klausimas apie API"]),
        ("suitability=unreviewed", ["Kito projekto klaida", "Šviesos tema", "Lėta paieška"]),
        ("repository=other/project", ["Kito projekto klaida"]),
        ("repository=owner/repo&annotation=unlabeled&sort=oldest", ["Klausimas apie API", "Šviesos tema"]),
    ],
)
def test_search_filters_and_sorting(training: TrainingApp, labelled: list[int], query: str, expected: list[str]) -> None:
    response = training.client.get(f"{URL}?{query}")

    assert response.status_code == 200
    assert _titles(response.text) == expected
    assert f"Rasta įrašų: <strong>{len(expected)}</strong>" in response.text


def test_invalid_filter_values_are_ignored(training: TrainingApp, labelled: list[int]) -> None:
    response = training.client.get(f"{URL}?annotation=x&suitability=y&repository=evil/repo&sort=z&page=abc")

    assert response.status_code == 200
    assert "Neteisinga filtro reikšmė" in response.text
    assert len(_titles(response.text)) == 5


def test_statistics_show_annotation_progress(training: TrainingApp, labelled: list[int]) -> None:
    html = training.client.get(URL).text

    for value, label in [(5, "Iš viso importuota"), (1, "Visiškai pažymėta"), (1, "Iš dalies pažymėta"),
                         (3, "Nepažymėta"), (1, "Paruošta mokymui")]:
        assert f'<span class="stat-value">{value}</span><span class="stat-label">{label}</span>' in html

    stats = annotation_stats(training.conn)
    assert (stats["total"], stats["complete"], stats["partial"], stats["unlabeled"]) == (5, 1, 1, 3)
    assert (stats["suitable"], stats["unsuitable"], stats["ready_for_training"]) == (1, 1, 1)
    categories = {item["value"]: (item["all"], item["suitable"]) for item in stats["class_counts"]["category_label"]}
    assert categories["ui"] == (1, 1)
    assert categories["performance"] == (1, 0)
    assert categories["security"] == (0, 0)


def test_statistics_on_empty_database(training: TrainingApp) -> None:
    stats = annotation_stats(training.conn)

    assert (stats["total"], stats["complete"], stats["partial"], stats["unlabeled"]) == (0, 0, 0, 0)


def test_pagination(training: TrainingApp) -> None:
    training.add(*[make_issue(number) for number in range(1, PER_PAGE + 6)])

    first = training.client.get(URL).text
    second = training.client.get(f"{URL}?page=2").text
    beyond = training.client.get(f"{URL}?page=99").text

    assert len(_titles(first)) == PER_PAGE
    assert len(_titles(second)) == 5
    assert "puslapis 1 iš 2" in first
    assert 'href="/dashboard/training-data?page=2"' in first
    assert 'href="/dashboard/training-data?page=1"' in second
    assert _titles(beyond) == _titles(second)  # per didelis numeris – paskutinis puslapis
    assert not set(_titles(first)) & set(_titles(second))


def test_pagination_keeps_filters(training: TrainingApp) -> None:
    training.add(*[make_issue(number, f"Klaida {number}") for number in range(1, PER_PAGE + 3)])

    html = training.client.get(f"{URL}?q=klaida&sort=oldest").text

    assert 'href="/dashboard/training-data?q=klaida&amp;sort=oldest&amp;page=2"' in html


# --- Detalės ----------------------------------------------------------------


def test_detail_shows_issue_and_github_labels(training: TrainingApp) -> None:
    (issue_id,) = training.add(
        make_issue(12, "Neveikia prisijungimas", "Pirma eilutė\nAntra eilutė",
                   labels=[{"name": "bug"}, {"name": "priority: high"}])
    )

    response = training.client.get(f"{URL}/{issue_id}")

    assert response.status_code == 200
    html = response.text
    assert "#12" in html and "Neveikia prisijungimas" in html
    assert "Pirma eilutė\nAntra eilutė" in html
    assert "owner/repo" in html
    assert 'href="https://github.com/owner/repo/issues/12"' in html
    assert '<span class="chip">bug</span>' in html
    assert '<span class="chip">priority: high</span>' in html
    assert "Dar nežymėta" in html
    assert 'name="csrf_token"' in html
    # GitHub etiketės automatiškai netampa žymomis.
    assert training.row(issue_id)["priority_label"] is None
    assert '<option value="" selected' not in html  # tuščia reikšmė – numatytoji
    assert '<option value="P1_high" selected' not in html


def test_missing_issue_returns_404(training: TrainingApp) -> None:
    response = training.client.get(f"{URL}/999")

    assert response.status_code == 404
    assert "Įrašas nerastas" in response.text


def test_issue_text_is_escaped(training: TrainingApp) -> None:
    script = "<script>alert('xss')</script>"
    (issue_id,) = training.add(
        make_issue(1, script, script + '<img src=x onerror="alert(1)">', labels=[{"name": script}])
    )

    for path in (URL, f"{URL}/{issue_id}", f"{URL}?q={script}"):
        html = training.client.get(path).text
        assert script not in html, path
        assert "<img src=x" not in html, path
        assert "&lt;script&gt;" in html, path


# --- Žymėjimas --------------------------------------------------------------


def test_save_all_three_labels_and_edit_them(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))

    response = training.annotate(issue_id, **ALL_LABELS, training_suitability="suitable")

    assert response.status_code == 303
    assert response.headers["location"] == f"{URL}/{issue_id}?message=saved"
    row = training.row(issue_id)
    assert (row["category_label"], row["complexity_label"], row["priority_label"]) == ("ui", "low", "P2_medium")
    assert row["training_suitability"] == "suitable"
    assert row["annotation_source"] == "manual"
    assert row["annotated_at"]

    page = training.client.get(response.headers["location"]).text
    assert "Žymos išsaugotos" in page
    assert '<option value="ui" selected>' in page
    assert '<option value="low" selected>' in page
    assert '<option value="P2_medium" selected>' in page
    assert 'value="suitable" checked' in page
    assert "Pažymėta</span>" in page

    training.annotate(issue_id, category_label="security", complexity_label="high",
                      priority_label="P0_critical", training_suitability="suitable")
    row = training.row(issue_id)
    assert (row["category_label"], row["complexity_label"], row["priority_label"]) == (
        "security", "high", "P0_critical")


def test_partial_annotation_keeps_empty_fields_null(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))

    training.annotate(issue_id, category_label="backend_api", complexity_label="", priority_label="")

    row = training.row(issue_id)
    assert row["category_label"] == "backend_api"
    assert row["complexity_label"] is None
    assert row["priority_label"] is None
    assert row["training_suitability"] == "unreviewed"
    assert "Iš dalies pažymėta" in training.client.get(f"{URL}/{issue_id}").text


def test_editing_one_field_keeps_others(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))
    training.annotate(issue_id, **ALL_LABELS, training_suitability="suitable")

    # Forma visada pateikia esamas reikšmes; keičiamas tik prioritetas.
    training.annotate(issue_id, **{**ALL_LABELS, "priority_label": "P1_high"}, training_suitability="suitable")

    row = training.row(issue_id)
    assert (row["category_label"], row["complexity_label"], row["priority_label"]) == ("ui", "low", "P1_high")


def test_label_can_be_cleared_back_to_null(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))
    training.annotate(issue_id, **ALL_LABELS)

    training.annotate(issue_id, **{**ALL_LABELS, "category_label": ""})

    assert training.row(issue_id)["category_label"] is None


def test_unchanged_annotation_is_reported(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))
    training.annotate(issue_id, **ALL_LABELS)
    annotated_at = training.row(issue_id)["annotated_at"]

    response = training.annotate(issue_id, **ALL_LABELS, follow=True)

    assert "Pakeitimų nebuvo" in response.text
    assert training.row(issue_id)["annotated_at"] == annotated_at


@pytest.mark.parametrize(
    "fields",
    [
        {"category_label": "frontend"},
        {"complexity_label": "extreme"},
        {"priority_label": "P5"},
        {"priority_label": "p0_critical"},
        {"category_label": "ui' OR 1=1 --"},
        {"training_suitability": "maybe"},
    ],
)
def test_invalid_values_are_rejected(training: TrainingApp, fields: dict) -> None:
    (issue_id,) = training.add(make_issue(1))
    before = dict(training.row(issue_id))

    response = training.annotate(issue_id, **{**ALL_LABELS, **fields})

    assert response.status_code == 400
    assert "Žymos neišsaugotos" in response.text
    assert "Neleistina" in response.text
    assert dict(training.row(issue_id)) == before


@pytest.mark.parametrize("token", ["", "neteisingas"])
def test_annotation_requires_csrf_token(training: TrainingApp, token: str) -> None:
    (issue_id,) = training.add(make_issue(1))

    response = training.annotate(issue_id, token=token, **ALL_LABELS)

    assert response.status_code == 403
    assert training.row(issue_id)["category_label"] is None


def test_annotation_for_missing_issue_returns_404(training: TrainingApp) -> None:
    assert training.annotate(999, **ALL_LABELS).status_code == 404


def test_validate_annotation_maps_empty_to_none() -> None:
    values, errors = validate_annotation({"category_label": " ", "complexity_label": "low"})

    assert errors == {}
    assert values == {"category_label": None, "complexity_label": "low", "priority_label": None,
                      "training_suitability": "unreviewed"}


# --- Tinkamumas mokymui -----------------------------------------------------


def test_suitability_defaults_to_unreviewed_and_can_be_changed(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))
    assert training.row(issue_id)["training_suitability"] == "unreviewed"

    training.annotate(issue_id, training_suitability="unsuitable")
    assert training.row(issue_id)["training_suitability"] == "unsuitable"
    # Tinkamumas nekeičia klasifikavimo laukų.
    assert training.row(issue_id)["category_label"] is None

    training.annotate(issue_id, **ALL_LABELS, training_suitability="suitable")
    row = training.row(issue_id)
    assert row["training_suitability"] == "suitable"
    assert row["category_label"] == "ui"


def test_database_rejects_invalid_suitability(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))

    with pytest.raises(sqlite3.IntegrityError):
        training.conn.execute(
            "UPDATE github_issues SET training_suitability = 'maybe' WHERE id = ?", (issue_id,)
        )


# --- Kitas nepažymėtas ------------------------------------------------------


def test_next_unlabeled_skips_complete_and_unsuitable(training: TrainingApp) -> None:
    first, second, third, fourth = training.add(*[make_issue(number) for number in range(1, 5)])
    save_annotation(training.conn, second, {**ALL_LABELS, "training_suitability": "suitable"})
    save_annotation(training.conn, third, {"category_label": None, "complexity_label": None,
                                           "priority_label": None, "training_suitability": "unsuitable"})

    assert next_unlabeled_id(training.conn) == first
    assert next_unlabeled_id(training.conn, first) == fourth
    assert next_unlabeled_id(training.conn, fourth) == first  # pradedama iš pradžių

    response = training.client.get(f"{URL}/next?after={first}", follow_redirects=False)
    assert response.headers["location"] == f"{URL}/{fourth}"


def test_save_and_next_goes_to_next_issue(training: TrainingApp) -> None:
    first, second = training.add(make_issue(1), make_issue(2))

    response = training.annotate(first, **ALL_LABELS, training_suitability="suitable", action="next", follow=True)

    assert str(response.url).endswith(f"{URL}/{second}?message=saved_next")
    assert "Ankstesnio įrašo žymos išsaugotos" in response.text
    assert training.row(first)["category_label"] == "ui"


def test_next_when_everything_is_labelled(training: TrainingApp) -> None:
    (issue_id,) = training.add(make_issue(1))
    save_annotation(training.conn, issue_id, {**ALL_LABELS, "training_suitability": "suitable"})

    response = training.client.get(f"{URL}/next", follow_redirects=True)

    assert "Nepažymėtų įrašų nebeliko" in response.text


# --- Integracija su importu ir klientų pranešimais ---------------------------


def test_reimport_keeps_human_annotations(training: TrainingApp) -> None:
    training.github_issues = [make_issue(1, "Senas pavadinimas", labels=[{"name": "bug"}])]
    import_token = csrf_token(training.client, "/import")
    training.client.post("/import", data={"repository": "owner/repo", "limit": "10", "csrf_token": import_token})
    issue_id = training.conn.execute("SELECT id FROM github_issues").fetchone()[0]
    training.annotate(issue_id, **ALL_LABELS, training_suitability="suitable")
    annotated = dict(training.row(issue_id))

    training.github_issues = [make_issue(1, "Naujas pavadinimas", labels=[{"name": "enhancement"}])]
    response = training.client.post(
        "/import", data={"repository": "owner/repo", "limit": "10", "csrf_token": import_token}
    )

    assert "<dt>Atnaujinta esamų</dt><dd>1</dd>" in response.text
    row = training.row(issue_id)
    assert row["title"] == "Naujas pavadinimas"
    assert json.loads(row["labels_json"]) == ["enhancement"]
    for column in ("category_label", "complexity_label", "priority_label", "training_suitability",
                   "annotation_source", "annotated_at"):
        assert row[column] == annotated[column], column


def test_github_issues_do_not_appear_in_customer_reports(training: TrainingApp) -> None:
    training.add(make_issue(1, "GitHub mokymo įrašas"))
    training.client.post("/report", data={"title": "Kliento klaida", "description": "Tekstas"})

    dashboard = training.client.get("/dashboard").text
    training_list = training.client.get(URL).text

    assert "GitHub mokymo įrašas" not in dashboard
    assert "Kliento klaida</a>" in dashboard
    assert "GitHub mokymo įrašas</a>" in training_list
    assert "Kliento klaida" not in training_list
    assert training.conn.execute("SELECT COUNT(*) FROM github_issues").fetchone()[0] == 1


# --- Schemos migracija --------------------------------------------------------


def test_existing_database_gets_suitability_column_without_data_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(db_path)
    # 1–3 etapų schema be training_suitability stulpelio.
    old.executescript(
        """
        CREATE TABLE github_issues (
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
        INSERT INTO github_issues (repository_full_name, issue_number, title, state, html_url,
                                   imported_at, category_label)
        VALUES ('owner/repo', 1, 'Senas įrašas', 'open', 'https://github.com/owner/repo/issues/1',
                '2026-10-28T10:00:00+00:00', 'ui');
        """
    )
    old.commit()
    old.close()

    conn = connect(db_path)
    init_db(conn)
    init_db(conn)  # pakartotinai saugu

    row = conn.execute("SELECT * FROM github_issues").fetchone()
    assert row["title"] == "Senas įrašas"
    assert row["category_label"] == "ui"
    assert row["training_suitability"] == "unreviewed"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE github_issues SET training_suitability = 'maybe'")
    conn.close()


def test_annotation_service_has_no_automatic_labelling() -> None:
    # Tinkamumą ir žymas nustato tik žmogus: servise nėra GitHub etikečių susiejimo.
    source = Path(annotation_service.__file__).read_text(encoding="utf-8")

    assert "labels_json" not in source.split("def github_labels")[0]
