"""6B: programuotojų specializacijos, naudotojų administravimas ir klaidų paskirstymas pagal kategorijas.

Visi testai naudoja laikiną SQLite (tikra `data/bakalauras.sqlite3` neliečiama), be tinklo ir be
tikrų modelių: automatinės prognozės įrašomos tiesiai į `prediction_runs`.
"""

import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect, init_db
from app.services.bug_report_service import create_bug_report, get_routed_report
from app.services.prediction_service import FieldPrediction, save_predictions
from app.services.user_service import (
    InvalidSpecialization,
    LastAdminError,
    change_active,
    change_role,
    developer_categories,
    get_user_by_username,
    set_developer_categories,
    set_role,
)
from tests.auth_utils import TEST_USERNAME, csrf_token, login, register
from tests.test_users import TESTER_PASSWORD, Site
from tools import users as users_cli


class RoutingSite(Site):
    def user_id(self, username: str) -> int:
        conn = self.db()
        try:
            return get_user_by_username(conn, username).id
        finally:
            conn.close()

    def developer(self, username: str, categories: list[str] | None = None) -> TestClient:
        """Registruojasi kaip testuotojas, administratorius (servisas) suteikia rolę ir kategorijas."""
        assert register(self.client(), username, f"{username}@pavyzdys.lt", TESTER_PASSWORD).status_code == 303
        self.change(set_role, username, "developer")
        if categories:
            self.change(set_developer_categories, self.user_id(username), categories)
        client = self.client()
        assert login(client, username, TESTER_PASSWORD).status_code == 303
        return client

    def report(
        self,
        title: str,
        predicted: str | None = None,
        needs_review: bool = False,
        confirmed: str | None = None,
        prediction_status: str = "ok",
    ) -> int:
        """Pranešimas su (neprivaloma) automatine kategorijos prognoze ir / ar žmogaus kategorija."""
        conn = self.db()
        try:
            report_id = create_bug_report(conn, title, "Aprašymas pakankamai ilgas.")
            if predicted is not None or prediction_status != "ok":
                save_predictions(conn, report_id, [FieldPrediction(
                    "category_label", prediction_status, predicted if prediction_status == "ok" else None,
                    0.9 if prediction_status == "ok" else None, needs_review, "test-version",
                )])
            if confirmed is not None:
                with conn:
                    conn.execute("UPDATE bug_reports SET category_label = ?, complexity_label = 'low',"
                                 " priority_label = 'P2_medium' WHERE id = ?", (confirmed, report_id))
            return report_id
        finally:
            conn.close()

    def routing(self, report_id: int) -> sqlite3.Row:
        conn = self.db()
        try:
            return get_routed_report(conn, report_id)
        finally:
            conn.close()


@pytest.fixture
def site(tmp_path: Path) -> RoutingSite:
    return RoutingSite(tmp_path)


def _ids(html: str, prefix: str = "/developer/reports/") -> set[int]:
    return {int(value) for value in re.findall(re.escape(prefix) + r"(\d+)\"", html)}


# --- DB migracija ------------------------------------------------------------------------------


def test_migration_creates_developer_categories_and_is_repeatable(tmp_path: Path) -> None:
    path = tmp_path / "6a.sqlite3"
    conn = connect(path)
    init_db(conn)
    conn.execute("DROP TABLE developer_categories")  # DB, sukurta iki 6B
    conn.execute("INSERT INTO users (username, email, password_hash, role, created_at, updated_at)"
                 " VALUES ('jonas', 'j@p.lt', 'x', 'developer', 't', 't')")
    report_id = create_bug_report(conn, "Senas", "Aprašymas", None)
    conn.commit()

    init_db(conn)
    conn.execute("INSERT INTO developer_categories (user_id, category_label, created_at) VALUES (1, 'ui', 't')")
    conn.commit()
    init_db(conn)  # pakartotinai – nieko nepraranda
    init_db(conn)

    assert conn.execute("SELECT username FROM users").fetchall()[0][0] == "jonas"
    assert conn.execute("SELECT title FROM bug_reports WHERE id = ?", (report_id,)).fetchone()[0] == "Senas"
    assert [tuple(row) for row in conn.execute("SELECT user_id, category_label FROM developer_categories")] == [(1, "ui")]
    with pytest.raises(sqlite3.IntegrityError):  # unikali (user_id, category_label) pora
        conn.execute("INSERT INTO developer_categories (user_id, category_label, created_at) VALUES (1, 'ui', 't')")
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(developer_categories)")}
    assert "idx_developer_categories_category" in indexes
    foreign = conn.execute("PRAGMA foreign_key_list(developer_categories)").fetchall()
    assert [(row["table"], row["from"]) for row in foreign] == [("users", "user_id")]
    conn.close()


# --- Administratoriaus naudotojų valdymas ------------------------------------------------------


def test_admin_promotes_tester_to_developer_and_assigns_categories_in_browser(site: RoutingSite) -> None:
    tester = site.tester("jonas")
    assert tester.get("/developer/dashboard", follow_redirects=False).status_code == 403
    admin = site.admin()
    token = csrf_token(admin, "/admin/users")
    user_id = site.user_id("jonas")

    role = admin.post(f"/admin/users/{user_id}/role", data={"role": "developer", "csrf_token": token},
                      follow_redirects=False)
    categories = admin.post(f"/admin/users/{user_id}/categories",
                            data={"categories": ["ui", "security"], "csrf_token": token}, follow_redirects=False)

    assert role.status_code == 303 and categories.status_code == 303
    assert site.query("SELECT role FROM users WHERE id = ?", (user_id,))[0]["role"] == "developer"
    assert sorted(r["category_label"] for r in site.query(
        "SELECT category_label FROM developer_categories WHERE user_id = ?", (user_id,))) == ["security", "ui"]
    page = admin.get("/admin/users?message=categories").text
    assert "Specializacijos išsaugotos" in page and "jonas" in page
    # Ta pati sesija iš karto gauna programuotojo darbo aplinką.
    assert tester.get("/developer/dashboard").status_code == 200

    replaced = admin.post(f"/admin/users/{user_id}/categories", data={"categories": "performance", "csrf_token": token})
    assert replaced.status_code == 200
    removed = admin.post(f"/admin/users/{user_id}/categories", data={"csrf_token": token})
    assert removed.status_code == 200
    assert site.query("SELECT * FROM developer_categories") == []


def test_one_category_can_belong_to_several_developers(site: RoutingSite) -> None:
    report_id = site.report("Mygtukas neveikia", confirmed="ui")
    first = site.developer("pirmas", ["ui"])
    second = site.developer("antras", ["ui", "backend_api"])

    assert report_id in _ids(first.get("/developer/dashboard").text)
    assert report_id in _ids(second.get("/developer/dashboard").text)
    assert site.routing(report_id)["developer_count"] == 2
    assert len(site.query("SELECT id FROM bug_reports")) == 1  # paskirstymas pranešimų nedubliuoja


@pytest.mark.parametrize("category", ["neegzistuoja", "other", "UI", ""])
def test_invalid_category_cannot_be_assigned(site: RoutingSite, category: str) -> None:
    site.developer("jonas")
    admin = site.admin()
    token = csrf_token(admin, "/admin/users")

    response = admin.post(f"/admin/users/{site.user_id('jonas')}/categories",
                          data={"categories": category, "csrf_token": token})

    assert response.status_code == 400 and "Neleistina kategorija" in response.text
    assert site.query("SELECT * FROM developer_categories") == []
    conn = site.db()
    with pytest.raises(InvalidSpecialization):
        set_developer_categories(conn, site.user_id("jonas"), [category])
    conn.close()


@pytest.mark.parametrize("role", ["tester", "admin"])
def test_specializations_only_for_developer_role(site: RoutingSite, role: str) -> None:
    site.tester("jonas")
    admin = site.admin()
    if role == "admin":
        site.change(set_role, "jonas", "admin")
    token = csrf_token(admin, "/admin/users")

    response = admin.post(f"/admin/users/{site.user_id('jonas')}/categories",
                          data={"categories": "ui", "csrf_token": token})

    assert response.status_code == 400 and "tik naudotojui su programuotojo role" in response.text
    assert site.query("SELECT * FROM developer_categories") == []


def test_unknown_user_and_invalid_role_are_rejected(site: RoutingSite) -> None:
    site.tester("jonas")
    admin = site.admin()
    token = csrf_token(admin, "/admin/users")
    user_id = site.user_id("jonas")

    assert admin.post("/admin/users/999/role", data={"role": "developer", "csrf_token": token}).status_code == 404
    assert admin.post(f"/admin/users/{user_id}/role", data={"role": "superadmin", "csrf_token": token}).status_code == 400
    assert admin.post(f"/admin/users/{user_id}/active", data={"active": "x", "csrf_token": token}).status_code == 400
    assert tuple(site.query("SELECT role, is_active FROM users WHERE id = ?", (user_id,))[0]) == ("tester", 1)


def test_role_change_away_from_developer_removes_specializations(site: RoutingSite) -> None:
    report_id = site.report("Lėtas puslapis", confirmed="performance")
    developer = site.developer("jonas", ["performance", "ui"])
    assert report_id in _ids(developer.get("/developer/dashboard").text)

    site.change(set_role, "jonas", "tester")

    assert site.query("SELECT * FROM developer_categories") == []
    assert developer.get("/developer/dashboard", follow_redirects=False).status_code == 403
    assert developer.get(f"/developer/reports/{report_id}", follow_redirects=False).status_code == 403
    site.change(set_role, "jonas", "developer")  # grąžinus rolę senos specializacijos neatsiranda
    assert report_id not in _ids(developer.get("/developer/dashboard").text)


def test_last_active_admin_cannot_be_demoted_or_deactivated(site: RoutingSite, capsys) -> None:
    site.admin()  # .env administratorius perkeliamas į users – vienintelis administratorius
    admin_id = site.user_id(TEST_USERNAME)
    conn = site.db()
    try:
        for action in (lambda: change_role(conn, admin_id, "developer"),
                       lambda: change_role(conn, admin_id, "tester"),
                       lambda: change_active(conn, admin_id, False)):
            with pytest.raises(LastAdminError):
                action()
    finally:
        conn.close()
    db = ["--db", str(site.db_path)]
    assert users_cli.main([*db, "set-role", TEST_USERNAME, "tester"]) == 2
    assert users_cli.main([*db, "deactivate", TEST_USERNAME]) == 2
    assert "paskutinis aktyvus administratorius" in capsys.readouterr().out
    assert tuple(site.query("SELECT role, is_active FROM users WHERE id = ?", (admin_id,))[0]) == ("admin", 1)

    # Atsiradus antram aktyviam administratoriui, pirmąjį jau galima pakeisti (bet ne abu).
    site.tester("antras")
    site.change(set_role, "antras", "admin")
    conn = site.db()
    try:
        change_active(conn, admin_id, False)
        with pytest.raises(LastAdminError):
            change_role(conn, site.user_id("antras"), "tester")
    finally:
        conn.close()


def test_admin_cannot_demote_or_deactivate_own_account_in_browser(site: RoutingSite) -> None:
    admin = site.admin()
    token = csrf_token(admin, "/admin/users")
    admin_id = site.user_id(TEST_USERNAME)

    demote = admin.post(f"/admin/users/{admin_id}/role", data={"role": "tester", "csrf_token": token})
    deactivate = admin.post(f"/admin/users/{admin_id}/active", data={"active": "0", "csrf_token": token})

    assert demote.status_code == 400 and deactivate.status_code == 400
    assert "Savo paskyros" in demote.text
    assert admin.get("/admin/users").status_code == 200


def test_admin_can_deactivate_and_reactivate_other_admin(site: RoutingSite) -> None:
    admin = site.admin()
    site.tester("antras")
    site.change(set_role, "antras", "admin")
    token = csrf_token(admin, "/admin/users")
    other_id = site.user_id("antras")

    assert admin.post(f"/admin/users/{other_id}/active", data={"active": "0", "csrf_token": token},
                      follow_redirects=False).status_code == 303
    assert site.query("SELECT is_active FROM users WHERE id = ?", (other_id,))[0][0] == 0
    assert admin.post(f"/admin/users/{other_id}/active", data={"active": "1", "csrf_token": token},
                      follow_redirects=False).status_code == 303
    assert site.query("SELECT is_active FROM users WHERE id = ?", (other_id,))[0][0] == 1


def test_users_page_lists_accounts_without_password_hashes(site: RoutingSite) -> None:
    site.tester("jonas", "jonas@pavyzdys.lt")
    admin = site.admin()

    page = admin.get("/admin/users").text

    assert "jonas" in page and "jonas@pavyzdys.lt" in page and "Testuotojas" in page and "Aktyvi" in page
    assert "pbkdf2" not in page and TESTER_PASSWORD not in page
    for (password_hash,) in site.query("SELECT password_hash FROM users"):
        assert password_hash not in page


# --- Programuotojo darbo aplinka ir paskirstymas --------------------------------------------------


def test_developer_sees_only_reports_of_own_categories(site: RoutingSite) -> None:
    ui_report = site.report("UI klaida", predicted="ui")
    security_report = site.report("Saugumo klaida", confirmed="security")
    backend_report = site.report("API klaida", predicted="backend_api")
    developer = site.developer("jonas", ["ui", "security"])

    page = developer.get("/developer/dashboard").text

    assert _ids(page) == {ui_report, security_report}
    assert "Rasta pranešimų: <strong>2</strong>" in page
    assert "API klaida" not in page
    assert backend_report not in _ids(developer.get("/developer/dashboard?q=klaida").text)
    # Filtras pagal svetimą kategoriją nieko neatskleidžia ir laikomas neteisingu.
    foreign = developer.get("/developer/dashboard?category=backend_api").text
    assert "API klaida" not in foreign and "Neteisinga filtro reikšmė" in foreign
    assert _ids(developer.get("/developer/dashboard?category=security").text) == {security_report}


def test_developer_dashboard_shows_required_columns(site: RoutingSite) -> None:
    site.report("Mygtukas neveikia", confirmed="ui")
    developer = site.developer("jonas", ["ui"])

    page = developer.get("/developer/dashboard").text

    for text in ("Mygtukas neveikia", "Naudotojo sąsaja", "P2 – vidutinis", "Mažas", "Nauja", "UTC"):
        assert text in page


def test_developer_without_categories_sees_notice_and_no_reports(site: RoutingSite) -> None:
    report_id = site.report("UI klaida", confirmed="ui")
    developer = site.developer("jonas")

    page = developer.get("/developer/dashboard").text

    assert "nepriskirta nė viena kategorija" in page
    assert "UI klaida" not in page and _ids(page) == set()
    assert developer.get(f"/developer/reports/{report_id}").status_code == 404


def test_developer_cannot_open_or_change_foreign_report(site: RoutingSite) -> None:
    foreign = site.report("Svetima klaida", confirmed="database_data")
    unrouted = site.report("Neaiški klaida")  # be kategorijos – administratoriaus peržiūrai
    developer = site.developer("jonas", ["ui"])
    token = csrf_token(developer, "/developer/dashboard")

    for report_id in (foreign, unrouted, 999):
        page = developer.get(f"/developer/reports/{report_id}")
        change = developer.post(f"/developer/reports/{report_id}/status",
                                data={"status": "resolved", "csrf_token": token})
        assert page.status_code == 404 and "Svetima klaida" not in page.text
        assert change.status_code == 404
    assert {r["status"] for r in site.query("SELECT status FROM bug_reports")} == {"new"}


def test_developer_can_change_status_of_own_category_report(site: RoutingSite) -> None:
    report_id = site.report("UI klaida", predicted="ui")
    developer = site.developer("jonas", ["ui"])
    token = csrf_token(developer, f"/developer/reports/{report_id}")

    response = developer.post(f"/developer/reports/{report_id}/status",
                              data={"status": "resolved", "csrf_token": token}, follow_redirects=False)
    invalid = developer.post(f"/developer/reports/{report_id}/status", data={"status": "closed", "csrf_token": token})

    assert response.status_code == 303
    assert response.headers["location"] == f"/developer/reports/{report_id}?message=status_updated"
    (row,) = site.query("SELECT status, resolved_at FROM bug_reports WHERE id = ?", (report_id,))
    assert row["status"] == "resolved" and row["resolved_at"]
    assert invalid.status_code == 400 and "Neleistina būsena" in invalid.text
    detail = developer.get(response.headers["location"]).text
    assert "Būsena sėkmingai pakeista" in detail
    assert "/classification" not in detail and "/classify" not in detail  # klasifikacija – administratoriui


DEVELOPER_ROUTES = [
    ("GET", "/developer/dashboard"),
    ("GET", "/developer/reports/1"),
    ("POST", "/developer/reports/1/status"),
]
USER_ADMIN_ROUTES = [
    ("GET", "/admin/users"),
    ("POST", "/admin/users/1/role"),
    ("POST", "/admin/users/1/active"),
    ("POST", "/admin/users/1/categories"),
]


@pytest.mark.parametrize(("method", "path"), USER_ADMIN_ROUTES)
def test_developer_cannot_reach_user_administration(site: RoutingSite, method: str, path: str) -> None:
    developer = site.developer("jonas", ["ui"])
    token = csrf_token(developer, "/developer/dashboard")

    response = developer.request(method, path, data={"csrf_token": token, "role": "admin", "categories": "ui",
                                                     "active": "1"}, follow_redirects=False)

    assert response.status_code == 403
    assert site.query("SELECT role FROM users WHERE username = 'jonas'")[0][0] == "developer"


@pytest.mark.parametrize(("method", "path"), DEVELOPER_ROUTES + USER_ADMIN_ROUTES)
def test_tester_cannot_reach_developer_or_admin_routes(site: RoutingSite, method: str, path: str) -> None:
    site.report("UI klaida", confirmed="ui")
    tester = site.tester("tomas")
    token = csrf_token(tester, "/my/reports")

    response = tester.request(method, path, data={"csrf_token": token, "status": "resolved"}, follow_redirects=False)

    assert response.status_code == 403
    assert site.query("SELECT status FROM bug_reports")[0][0] == "new"


@pytest.mark.parametrize(("method", "path"), DEVELOPER_ROUTES + USER_ADMIN_ROUTES)
def test_guest_is_sent_to_login(site: RoutingSite, method: str, path: str) -> None:
    response = site.client().request(method, path, follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_admin_has_no_developer_workspace_but_sees_all_reports(site: RoutingSite) -> None:
    ids = {site.report("A", predicted="ui"), site.report("B"), site.report("C", confirmed="other")}
    admin = site.admin()

    assert admin.get("/developer/dashboard", follow_redirects=False).status_code == 403
    assert _ids(admin.get("/dashboard").text, "/dashboard/reports/") == ids


# --- Paskirstymo taisyklės -----------------------------------------------------------------------


def test_human_confirmed_category_wins_over_prediction(site: RoutingSite) -> None:
    report_id = site.report("Klaida", predicted="ui", confirmed="backend_api")
    ui_developer = site.developer("ui_dev", ["ui"])
    api_developer = site.developer("api_dev", ["backend_api"])

    assert report_id not in _ids(ui_developer.get("/developer/dashboard").text)
    assert report_id in _ids(api_developer.get("/developer/dashboard").text)
    assert site.routing(report_id)["routed_category"] == "backend_api"


@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # neklasifikuota
        {"predicted": "other"},
        {"predicted": "ui", "needs_review": True},  # žemas įvertis arba nepatikimas vertimas
        {"prediction_status": "model_unavailable"},
        {"prediction_status": "error"},
        {"predicted": "ui", "confirmed": "other"},  # žmogus patvirtino „Kita“
    ],
)
def test_unreliable_other_and_unset_categories_go_to_admin_review(site: RoutingSite, kwargs: dict) -> None:
    report_id = site.report("Neaiški klaida", **kwargs)
    developer = site.developer("jonas", ["ui", "backend_api", "security"])
    admin = site.admin()

    assert site.routing(report_id)["routing_state"] == "review"
    assert report_id not in _ids(developer.get("/developer/dashboard").text)
    review = admin.get("/dashboard?routing=review").text
    assert report_id in _ids(review, "/dashboard/reports/")
    assert "Reikia administratoriaus peržiūros" in admin.get(f"/dashboard/reports/{report_id}").text


def test_newest_ok_prediction_decides_routing(site: RoutingSite) -> None:
    report_id = site.report("Klaida", predicted="ui")
    conn = site.db()
    save_predictions(conn, report_id, [FieldPrediction("category_label", "ok", "ui", 0.2, True, "v2")])
    conn.close()
    developer = site.developer("jonas", ["ui"])

    assert site.routing(report_id)["routing_state"] == "review"
    assert report_id not in _ids(developer.get("/developer/dashboard").text)


def test_admin_confirmation_moves_report_between_queues_immediately(site: RoutingSite) -> None:
    report_id = site.report("Klaida", predicted="ui", needs_review=True)
    ui_developer = site.developer("ui_dev", ["ui"])
    db_developer = site.developer("db_dev", ["database_data"])
    admin = site.admin()
    token = csrf_token(admin, f"/dashboard/reports/{report_id}")
    assert report_id not in _ids(ui_developer.get("/developer/dashboard").text)

    def confirm(category: str) -> None:
        response = admin.post(f"/dashboard/reports/{report_id}/classification", data={
            "category_label": category, "complexity_label": "low", "priority_label": "P1_high",
            "csrf_token": token}, follow_redirects=False)
        assert response.status_code == 303

    confirm("ui")
    assert report_id in _ids(ui_developer.get("/developer/dashboard").text)
    assert report_id not in _ids(db_developer.get("/developer/dashboard").text)

    confirm("database_data")
    assert report_id not in _ids(ui_developer.get("/developer/dashboard").text)
    assert ui_developer.get(f"/developer/reports/{report_id}").status_code == 404
    assert report_id in _ids(db_developer.get("/developer/dashboard").text)
    assert len(site.query("SELECT id FROM bug_reports")) == 1


def test_specialization_change_updates_visibility_immediately(site: RoutingSite) -> None:
    report_id = site.report("UI klaida", confirmed="ui")
    developer = site.developer("jonas", ["ui"])
    user_id = site.user_id("jonas")
    assert report_id in _ids(developer.get("/developer/dashboard").text)

    site.change(set_developer_categories, user_id, ["security"])
    assert report_id not in _ids(developer.get("/developer/dashboard").text)
    assert developer.get(f"/developer/reports/{report_id}").status_code == 404

    site.change(set_developer_categories, user_id, ["security", "ui"])
    assert report_id in _ids(developer.get("/developer/dashboard").text)


def test_category_without_developer_stays_visible_to_admin(site: RoutingSite) -> None:
    report_id = site.report("Dokumentacijos klaida", confirmed="documentation")
    site.developer("jonas", ["ui"])
    admin = site.admin()

    assert site.routing(report_id)["routing_state"] == "no_developer"
    page = admin.get("/dashboard?routing=no_developer").text
    assert report_id in _ids(page, "/dashboard/reports/") and "Nėra programuotojo" in page
    assert "Nėra programuotojo" in admin.get("/admin/users").text


def test_admin_dashboard_shows_routing_counts_and_filter(site: RoutingSite) -> None:
    queued = site.report("UI", confirmed="ui")
    lonely = site.report("Docs", confirmed="documentation")
    review = site.report("Neaiški")
    site.developer("jonas", ["ui"])
    admin = site.admin()

    page = admin.get("/dashboard").text

    assert "Programuotojų eilėje: 1" in page and "Nėra programuotojo: 1" in page
    assert "Reikia administratoriaus peržiūros: 1" in page
    assert _ids(admin.get("/dashboard?routing=queue").text, "/dashboard/reports/") == {queued}
    assert _ids(admin.get("/dashboard?routing=no_developer").text, "/dashboard/reports/") == {lonely}
    assert _ids(admin.get("/dashboard?routing=review").text, "/dashboard/reports/") == {review}
    invalid = admin.get("/dashboard?routing=bet-kas").text
    assert "Neteisinga filtro reikšmė" in invalid
    assert _ids(invalid, "/dashboard/reports/") == {queued, lonely, review}


def test_deactivated_developer_loses_access_and_leaves_queue(site: RoutingSite) -> None:
    report_id = site.report("UI klaida", confirmed="ui")
    developer = site.developer("jonas", ["ui"])
    admin = site.admin()
    token = csrf_token(admin, "/admin/users")
    assert site.routing(report_id)["routing_state"] == "queue"

    admin.post(f"/admin/users/{site.user_id('jonas')}/active", data={"active": "0", "csrf_token": token})

    response = developer.get("/developer/dashboard", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].startswith("/login")
    assert developer.get(f"/developer/reports/{report_id}", follow_redirects=False).status_code == 303
    assert site.routing(report_id)["routing_state"] == "no_developer"
    assert developer_categories(site.db(), site.user_id("jonas")) == ["ui"]  # išlieka aktyvavimui


# --- CSRF ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["", "neteisingas"])
def test_admin_user_forms_require_csrf(site: RoutingSite, token: str) -> None:
    site.developer("jonas")
    admin = site.admin()
    user_id = site.user_id("jonas")

    for path, data in ((f"/admin/users/{user_id}/role", {"role": "admin"}),
                       (f"/admin/users/{user_id}/active", {"active": "0"}),
                       (f"/admin/users/{user_id}/categories", {"categories": "ui"})):
        response = admin.post(path, data={**data, "csrf_token": token})
        assert response.status_code == 403 and "CSRF" in response.text
    (row,) = site.query("SELECT role, is_active FROM users WHERE id = ?", (user_id,))
    assert (row["role"], row["is_active"]) == ("developer", 1)
    assert site.query("SELECT * FROM developer_categories") == []


def test_developer_status_change_requires_csrf(site: RoutingSite) -> None:
    report_id = site.report("UI klaida", confirmed="ui")
    developer = site.developer("jonas", ["ui"])
    other_token = csrf_token(site.developer("kitas", ["ui"]), "/developer/dashboard")

    for token in ("", other_token):
        response = developer.post(f"/developer/reports/{report_id}/status",
                                  data={"status": "resolved", "csrf_token": token})
        assert response.status_code == 403
    assert site.query("SELECT status FROM bug_reports")[0][0] == "new"


# --- Navigacija ir prisijungimas ------------------------------------------------------------------


def test_navigation_depends_on_role(site: RoutingSite) -> None:
    developer = site.developer("jonas", ["ui"])
    tester = site.tester("tomas")
    admin = site.admin()

    developer_page = developer.get("/my/reports").text
    tester_page = tester.get("/my/reports").text
    admin_page = admin.get("/dashboard").text

    assert 'href="/developer/dashboard"' in developer_page and 'href="/report"' in developer_page
    assert 'href="/admin/users"' not in developer_page and 'href="/import"' not in developer_page
    assert 'href="/developer/dashboard"' not in tester_page and 'href="/admin/users"' not in tester_page
    assert 'href="/my/reports"' in tester_page and 'href="/report"' in tester_page
    assert 'href="/admin/users"' in admin_page and 'href="/import"' in admin_page
    assert "Prisijungti" in site.client().get("/report").text or "/login" in site.client().get("/report").text


@pytest.mark.parametrize(
    ("next_path", "expected"),
    [("", "/developer/dashboard"), ("/developer/reports/5", "/developer/reports/5"),
     ("/developer/dashboard?status=new", "/developer/dashboard?status=new"), ("/my/reports", "/my/reports"),
     ("/dashboard", "/developer/dashboard"), ("/admin/users", "/developer/dashboard"),
     ("/developer/reports/../../import", "/developer/dashboard"), ("//evil.example/", "/developer/dashboard")],
)
def test_developer_login_redirects_to_own_workspace(site: RoutingSite, next_path: str, expected: str) -> None:
    site.developer("jonas", ["ui"])

    assert login(site.client(), "jonas", TESTER_PASSWORD, next_path=next_path).headers["location"] == expected


@pytest.mark.parametrize("next_path", ["/developer/dashboard", "/developer/reports/1", "/admin/users"])
def test_tester_is_not_redirected_to_developer_or_user_admin_pages(site: RoutingSite, next_path: str) -> None:
    site.tester("tomas")

    assert login(site.client(), "tomas", TESTER_PASSWORD, next_path=next_path).headers["location"] == "/my/reports"


def test_admin_can_return_to_user_administration(site: RoutingSite) -> None:
    assert login(site.client(), next_path="/admin/users").headers["location"] == "/admin/users"
