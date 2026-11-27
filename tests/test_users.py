"""6A: naudotojų registracija, prisijungimas, rolės, nuosavybė ir migracija.

Visi testai naudoja laikiną SQLite (tikra `data/bakalauras.sqlite3` neliečiama) ir nenaudoja tinklo.
"""

import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import SESSION_COOKIE_NAME, create_session_token, verify_password
from app.db import connect, get_database_path, init_db
from app.main import create_app
from app.services.user_service import (
    AdminBootstrap,
    bootstrap_admin,
    get_user_by_username,
    set_active,
    set_password,
    set_role,
)
from tests.auth_utils import (
    TEST_PASSWORD,
    TEST_SETTINGS,
    TEST_USERNAME,
    csrf_token,
    form_csrf,
    login,
    register,
    submit_report,
    use_test_auth,
)
from tools import users as users_cli

TESTER_PASSWORD = "testuotojo-slaptazodis-1"

# Visi esami administratoriaus maršrutai (GET ir POST), kurių testuotojas pasiekti negali.
ADMIN_ROUTES = [
    ("GET", "/dashboard"),
    ("GET", "/dashboard/reports/1"),
    ("POST", "/dashboard/reports/1/status"),
    ("POST", "/dashboard/reports/1/classify"),
    ("POST", "/dashboard/reports/1/classification"),
    ("GET", "/import"),
    ("POST", "/import"),
    ("GET", "/dashboard/training-data"),
    ("GET", "/dashboard/training-data/next"),
    ("GET", "/dashboard/training-data/1"),
    ("POST", "/dashboard/training-data/1/annotation"),
]


class Site:
    def __init__(self, tmp_path: Path) -> None:
        self.db_path = tmp_path / "users.sqlite3"
        self.app = create_app()
        self.app.dependency_overrides[get_database_path] = lambda: self.db_path
        # Modelių katalogas tuščias (conftest): prognozė `model_unavailable`, pranešimas išsaugomas.
        use_test_auth(self.app)

    def client(self) -> TestClient:
        return TestClient(self.app)

    def tester(self, username: str = "tomas", email: str | None = None) -> TestClient:
        client = self.client()
        assert register(client, username, email or f"{username}@pavyzdys.lt", TESTER_PASSWORD).status_code == 303
        assert login(client, username, TESTER_PASSWORD).status_code == 303
        return client

    def admin(self) -> TestClient:
        client = self.client()
        assert login(client).status_code == 303
        return client

    def db(self) -> sqlite3.Connection:
        conn = connect(self.db_path)
        init_db(conn)
        return conn

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self.db()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def change(self, action, *args) -> None:
        conn = self.db()
        try:
            action(conn, *args)
        finally:
            conn.close()

    def submit(self, client: TestClient, title: str, description: str = "Aprašymas pakankamai ilgas.", **extra):
        return submit_report(client, title, description, **extra)


@pytest.fixture
def site(tmp_path: Path) -> Site:
    return Site(tmp_path)


# --- 1–4. Registracija ------------------------------------------------------------


def test_registration_creates_tester_with_hashed_password(site: Site) -> None:
    client = site.client()

    page = client.get("/register")
    response = register(client, "Tomas_1", "Tomas@Pavyzdys.LT", TESTER_PASSWORD)

    assert page.status_code == 200 and 'name="form_csrf"' in page.text
    assert response.status_code == 303 and response.headers["location"] == "/login?registered=1"
    assert "set-cookie" not in response.headers or SESSION_COOKIE_NAME not in response.headers["set-cookie"]
    (row,) = site.query("SELECT * FROM users WHERE username = 'Tomas_1'")
    assert row["role"] == "tester" and row["is_active"] == 1
    assert row["email"] == "tomas@pavyzdys.lt"
    assert row["password_hash"].startswith("pbkdf2_sha256:600000:")
    assert TESTER_PASSWORD not in row["password_hash"]
    assert verify_password(TESTER_PASSWORD, row["password_hash"])
    assert "Paskyra sukurta" in client.get("/login?registered=1").text

    logged_in = login(client, "tomas_1", TESTER_PASSWORD)  # vardas nejautrus raidžių dydžiui
    assert logged_in.status_code == 303 and logged_in.headers["location"] == "/my/reports"


def test_duplicate_username_and_email_are_rejected(site: Site) -> None:
    assert register(site.client(), "jonas", "jonas@pavyzdys.lt").status_code == 303

    same_name = register(site.client(), "JONAS", "kitas@pavyzdys.lt")
    same_email = register(site.client(), "petras", "Jonas@Pavyzdys.lt")

    assert same_name.status_code == 400 and "naudotojo vardas jau užimtas" in same_name.text
    assert same_email.status_code == 400 and "el. pašto adresas jau užregistruotas" in same_email.text
    assert 'value="petras"' in same_email.text  # įvesti duomenys išlieka
    assert len(site.query("SELECT id FROM users")) == 1


@pytest.mark.parametrize(
    ("username", "email", "password", "confirm", "message"),
    [
        ("tomas", "tomas@pavyzdys.lt", "trumpas", "trumpas", "bent 10 simbolių"),
        ("tomas", "tomas@pavyzdys.lt", TESTER_PASSWORD, "kitas-slaptazodis-1", "Slaptažodžiai nesutampa"),
        ("t", "tomas@pavyzdys.lt", TESTER_PASSWORD, TESTER_PASSWORD, "3–40 simbolių"),
        ("tomas jonaitis", "tomas@pavyzdys.lt", TESTER_PASSWORD, TESTER_PASSWORD, "tik lotyniškos raidės"),
        ("<script>", "tomas@pavyzdys.lt", TESTER_PASSWORD, TESTER_PASSWORD, "tik lotyniškos raidės"),
        ("tomas", "ne-el-pastas", TESTER_PASSWORD, TESTER_PASSWORD, "teisingą el. pašto adresą"),
        ("tomas", "a@b", TESTER_PASSWORD, TESTER_PASSWORD, "teisingą el. pašto adresą"),
    ],
)
def test_registration_validates_input(site: Site, username, email, password, confirm, message) -> None:
    response = register(site.client(), username, email, password, confirm)

    assert response.status_code == 400
    assert message in response.text
    assert "<script>" not in response.text  # naudotojo įvestis koduojama
    assert site.query("SELECT id FROM users") == []


def test_wrong_password_is_rejected_at_login(site: Site) -> None:
    site.tester("tomas")
    client = site.client()

    response = login(client, "tomas", "neteisingas-slaptazodis")

    assert response.status_code == 401
    assert "Neteisingas naudotojo vardas arba slaptažodis" in response.text
    assert client.get("/my/reports", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("role", ["admin", "developer"])
def test_registration_cannot_grant_privileged_role(site: Site, role: str) -> None:
    response = register(site.client(), "isilauzelis", "x@pavyzdys.lt", role=role, is_active="1", id="1")

    assert response.status_code == 303
    (row,) = site.query("SELECT role FROM users WHERE username = 'isilauzelis'")
    assert row["role"] == "tester"
    client = site.client()
    login(client, "isilauzelis", TESTER_PASSWORD)
    assert client.get("/dashboard", follow_redirects=False).status_code == 403


def test_registration_cannot_take_env_admin_username(site: Site) -> None:
    response = register(site.client(), TEST_USERNAME.upper(), "x@pavyzdys.lt")

    assert response.status_code == 400 and "jau užimtas" in response.text
    assert site.query("SELECT id FROM users") == []
    assert login(site.client()).status_code == 303  # tikrasis administratorius vis tiek prisijungia


# --- 5–7. Prisijungimas, sesijos, išjungtos paskyros --------------------------------


def test_tester_login_and_logout(site: Site) -> None:
    client = site.tester("tomas")

    page = client.get("/my/reports")
    assert page.status_code == 200
    assert "Mano pranešimai" in page.text and "tomas" in page.text and "testuotojas" in page.text
    assert "/dashboard/training-data" not in page.text and "GitHub importas" not in page.text

    token = csrf_token(client, "/my/reports")
    response = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)

    assert response.headers["location"] == "/login?logged_out=1"
    assert client.get("/my/reports", follow_redirects=False).headers["location"].startswith("/login")


def test_invalid_and_stale_sessions_are_rejected(site: Site) -> None:
    site.tester("tomas")
    user_id = site.query("SELECT id FROM users WHERE username = 'tomas'")[0]["id"]
    hash_now = site.query("SELECT password_hash FROM users WHERE id = ?", (user_id,))[0]["password_hash"]

    cases = {
        "sugadintas": "netinkamas.slapukas",
        "pasibaigęs": create_session_token(TEST_SETTINGS, user_id, hash_now, now=1_000),
        "nežinomas naudotojas": create_session_token(TEST_SETTINGS, 999, hash_now),
        "kitas slaptažodis": create_session_token(TEST_SETTINGS, user_id, "pbkdf2_sha256:1:aa:bb"),
    }
    for name, value in cases.items():
        client = site.client()
        client.cookies.set(SESSION_COOKIE_NAME, value)
        assert client.get("/my/reports", follow_redirects=False).status_code == 303, name


def test_password_change_revokes_existing_sessions(site: Site) -> None:
    client = site.tester("tomas")
    assert client.get("/my/reports").status_code == 200

    site.change(set_password, "tomas", "visiskai-naujas-slaptazodis")

    assert client.get("/my/reports", follow_redirects=False).status_code == 303
    assert login(site.client(), "tomas", "visiskai-naujas-slaptazodis").status_code == 303


def test_disabled_account_loses_access_immediately_and_cannot_log_in(site: Site) -> None:
    client = site.tester("tomas")

    site.change(set_active, "tomas", False)

    assert client.get("/my/reports", follow_redirects=False).status_code == 303
    response = login(site.client(), "tomas", TESTER_PASSWORD)
    assert response.status_code == 403 and "Paskyra išjungta" in response.text
    assert SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")

    site.change(set_active, "tomas", True)
    assert login(site.client(), "tomas", TESTER_PASSWORD).status_code == 303


def test_repeated_failed_logins_are_rate_limited(site: Site) -> None:
    site.tester("tomas")
    client = site.client()

    for _ in range(10):
        assert login(client, "tomas", "blogas-slaptazodis").status_code == 401
    blocked = login(client, "tomas", TESTER_PASSWORD)

    assert blocked.status_code == 429 and "Per daug nesėkmingų bandymų" in blocked.text
    assert login(site.client(), TEST_USERNAME).status_code == 303  # kitas vardas neblokuojamas


# --- 8–9. Prieigos teisės ir nuosavybė -------------------------------------------------


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_tester_cannot_reach_admin_routes(site: Site, method: str, path: str) -> None:
    client = site.tester("tomas")
    token = csrf_token(client, "/my/reports")

    response = client.request(method, path, data={"csrf_token": token}, follow_redirects=False)

    assert response.status_code == 403
    assert "Prieiga uždrausta" in response.text


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_developer_has_no_access_to_all_reports_before_6b(site: Site, method: str, path: str) -> None:
    site.tester("programuotoja")
    site.change(set_role, "programuotoja", "developer")
    client = site.client()
    login(client, "programuotoja", TESTER_PASSWORD)

    assert client.request(method, path, follow_redirects=False).status_code == 403
    assert "kitame etape" in client.get("/my/reports").text


def test_role_changes_take_effect_immediately(site: Site) -> None:
    client = site.tester("tomas")
    assert client.get("/dashboard", follow_redirects=False).status_code == 403

    site.change(set_role, "tomas", "admin")
    assert client.get("/dashboard").status_code == 200

    site.change(set_role, "tomas", "tester")
    assert client.get("/dashboard", follow_redirects=False).status_code == 403


def test_admin_keeps_access_to_existing_internal_pages(site: Site) -> None:
    client = site.admin()

    for path in ("/dashboard", "/import", "/dashboard/training-data"):
        assert client.get(path).status_code == 200, path
    assert "administratorius" in client.get("/dashboard").text


def test_tester_sees_only_own_reports(site: Site) -> None:
    anonymous = site.client()
    site.submit(anonymous, "Svečio klaida")
    tomas = site.tester("tomas")
    ona = site.tester("ona")
    site.submit(tomas, "Tomo klaida")
    site.submit(ona, "Onos klaida")
    ids = {row["title"]: row["id"] for row in site.query("SELECT id, title FROM bug_reports")}

    own = tomas.get("/my/reports").text
    assert "Tomo klaida" in own and "Onos klaida" not in own and "Svečio klaida" not in own
    assert tomas.get(f"/my/reports/{ids['Tomo klaida']}").status_code == 200
    for title in ("Onos klaida", "Svečio klaida"):
        response = tomas.get(f"/my/reports/{ids[title]}")
        assert response.status_code == 404 and title not in response.text
    assert tomas.get("/my/reports/999").status_code == 404


def test_my_report_detail_shows_status_but_not_internal_classification(site: Site) -> None:
    tomas = site.tester("tomas")
    site.submit(tomas, "Tomo klaida", "Mygtukas neveikia paspaudus.")
    report_id = site.query("SELECT id FROM bug_reports")[0]["id"]
    admin = site.admin()
    token = csrf_token(admin, f"/dashboard/reports/{report_id}")
    admin.post(f"/dashboard/reports/{report_id}/status", data={"status": "in_progress", "csrf_token": token})

    page = tomas.get(f"/my/reports/{report_id}").text

    assert "Taisoma" in page and "Mygtukas neveikia paspaudus." in page
    assert "Patvirtinti klasifikaciją" not in page and "csrf_token\" value=\"" + token not in page


# --- 10. Vieša forma ir pranešimo savininkas ----------------------------------------------


def test_public_report_form_works_without_account(site: Site) -> None:
    client = site.client()

    assert client.get("/report").status_code == 200
    response = site.submit(client, "Svečio klaida")

    assert response.status_code == 303 and response.headers["location"] == "/report/submitted"
    assert site.query("SELECT reporter_user_id FROM bug_reports")[0]["reporter_user_id"] is None


def test_logged_in_tester_report_is_linked_and_owner_cannot_be_forged(site: Site) -> None:
    site.tester("ona")
    ona_id = site.query("SELECT id FROM users WHERE username = 'ona'")[0]["id"]
    tomas = site.tester("tomas")
    tomas_id = site.query("SELECT id FROM users WHERE username = 'tomas'")[0]["id"]

    assert "susietas su jūsų paskyra" in tomas.get("/report").text
    site.submit(tomas, "Tomo klaida", reporter_user_id=str(ona_id))

    (row,) = site.query("SELECT reporter_user_id FROM bug_reports")
    assert row["reporter_user_id"] == tomas_id
    assert "Mano pranešimai" in tomas.get("/report/submitted").text


# --- 11. Esamo administratoriaus išsaugojimas -------------------------------------------


def test_existing_env_admin_is_migrated_once_with_same_password(site: Site) -> None:
    assert site.query("SELECT id FROM users") == []

    first = login(site.client())
    second = login(site.client())

    assert first.status_code == second.status_code == 303 and first.headers["location"] == "/dashboard"
    (row,) = site.query("SELECT * FROM users")
    assert row["username"] == TEST_USERNAME and row["role"] == "admin" and row["is_active"] == 1
    assert row["password_hash"] == TEST_SETTINGS.password_hash  # ta pati maiša – slaptažodis nepasikeitė
    assert row["email"] is None


def test_admin_bootstrap_never_overwrites_existing_accounts(site: Site) -> None:
    conn = site.db()
    try:
        assert bootstrap_admin(conn, TEST_SETTINGS) is AdminBootstrap.CREATED
        assert bootstrap_admin(conn, TEST_SETTINGS) is AdminBootstrap.EXISTS
        assert bootstrap_admin(conn, None) is AdminBootstrap.NOT_CONFIGURED
        with conn:
            conn.execute("UPDATE users SET role = 'tester', password_hash = 'pbkdf2_sha256:1:aa:bb'")
        assert bootstrap_admin(conn, TEST_SETTINGS) is AdminBootstrap.CONFLICT
        user = get_user_by_username(conn, TEST_USERNAME)
    finally:
        conn.close()
    assert user.role == "tester" and user.password_hash == "pbkdf2_sha256:1:aa:bb"  # nieko neperrašyta

    response = login(site.client())
    assert response.status_code == 401  # be tylaus perrašymo administratorius neatsiranda


def test_admin_bootstrap_conflict_with_preexisting_name_is_reported(site: Site) -> None:
    conn = site.db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, role, is_active, created_at, updated_at)"
                " VALUES (?, 'a@b.lt', ?, 'tester', 1, 't', 't')",
                (TEST_USERNAME, "pbkdf2_sha256:1:aa:bb"),
            )
    finally:
        conn.close()

    response = login(site.client())

    assert response.status_code == 401
    assert site.query("SELECT role FROM users")[0]["role"] == "tester"


def test_users_cli_bootstrap_and_role_management(site: Site, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", TEST_USERNAME)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", TEST_SETTINGS.password_hash)
    monkeypatch.setenv("SESSION_SECRET_KEY", TEST_SETTINGS.secret_key)
    db = ["--db", str(site.db_path)]
    site.tester("tomas")

    assert users_cli.main([*db, "bootstrap-admin"]) == 0
    assert users_cli.main([*db, "bootstrap-admin"]) == 0
    assert users_cli.main([*db, "set-role", "tomas", "developer"]) == 0
    assert users_cli.main([*db, "deactivate", "tomas"]) == 0
    assert users_cli.main([*db, "set-role", "nera", "admin"]) == 1
    assert users_cli.main([*db, "list"]) == 0

    output = capsys.readouterr().out
    assert "perkeltas" in output and "jau yra" in output and "DB atsarginė kopija" in output
    assert "pbkdf2" not in output  # maišos nerodomos
    rows = {r["username"]: r for r in site.query("SELECT username, role, is_active FROM users")}
    assert rows[TEST_USERNAME]["role"] == "admin"
    assert rows["tomas"]["role"] == "developer" and rows["tomas"]["is_active"] == 0
    with pytest.raises(SystemExit):
        users_cli.main([*db, "set-role", "tomas", "superadmin"])  # tik leistinos rolės


# --- 12. Migracija ----------------------------------------------------------------------------


def _old_5d_database(path: Path) -> None:
    """Sumažinta 5D schema be users ir be bug_reports.reporter_user_id, su duomenimis."""
    raw = sqlite3.connect(path)
    raw.executescript(
        """
        CREATE TABLE bug_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            resolved_at TEXT, category_label TEXT, complexity_label TEXT, priority_label TEXT);
        INSERT INTO bug_reports (title, description, status, created_at, updated_at, category_label)
            VALUES ('Sena klaida', 'Senas aprašymas', 'resolved', '2026-11-01', '2026-11-02', 'ui');
        INSERT INTO bug_reports (title, description, created_at, updated_at)
            VALUES ('Kita sena', 'Aprašymas', '2026-11-03', '2026-11-03');
        """
    )
    raw.commit()
    raw.close()


def test_migration_is_repeatable_and_keeps_existing_data(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    _old_5d_database(path)
    conn = connect(path)
    init_db(conn)
    with conn:
        conn.execute(
            "INSERT INTO github_issues (repository_full_name, issue_number, title, body, state, html_url,"
            " labels_json, github_created_at, github_updated_at, imported_at)"
            " VALUES ('a/b', 1, 'T', 'B', 'open', 'https://github.com/a/b/issues/1', '[]', 't', 't', 't')"
        )
    before = [tuple(r) for r in conn.execute("SELECT * FROM bug_reports ORDER BY id")]

    for _ in range(3):  # pakartotinis vykdymas saugus
        init_db(conn)

    columns = [r[1] for r in conn.execute("PRAGMA table_info(bug_reports)")]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    after = [tuple(r)[:len(before[0])] for r in conn.execute("SELECT * FROM bug_reports ORDER BY id")]
    reporters = [r[0] for r in conn.execute("SELECT reporter_user_id FROM bug_reports")]
    issues = conn.execute("SELECT COUNT(*) FROM github_issues").fetchone()[0]
    conn.close()
    assert "reporter_user_id" in columns and "users" in tables
    assert after == before and issues == 1
    assert reporters == [None, None]  # seni pranešimai nepriskiriami jokiam naudotojui


def test_new_user_does_not_inherit_old_anonymous_reports(site: Site) -> None:
    _old_5d_database(site.db_path)
    tomas = site.tester("tomas")

    page = tomas.get("/my/reports").text

    assert "Sena klaida" not in page and "Kita sena" not in page
    assert tomas.get("/my/reports/1").status_code == 404


# --- 13. CSRF -----------------------------------------------------------------------------------


def test_login_and_register_forms_require_csrf(site: Site) -> None:
    client = site.client()
    valid = form_csrf(client)

    no_token = client.post("/login", data={"username": TEST_USERNAME, "password": TEST_PASSWORD})
    wrong_token = client.post(
        "/login", data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "form_csrf": valid + "x"}
    )
    foreign = site.client()  # žetonas be atitinkamo slapuko (kita naršyklė)
    no_cookie = foreign.post(
        "/login", data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "form_csrf": valid}
    )
    reg = site.client().post(
        "/register",
        data={"username": "tomas", "email": "t@pavyzdys.lt", "password": TESTER_PASSWORD,
              "password_confirm": TESTER_PASSWORD},
    )

    for response in (no_token, wrong_token, no_cookie, reg):
        assert response.status_code == 403
        assert SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")
    assert site.query("SELECT id FROM users") == []


def test_logout_and_admin_post_require_session_csrf(site: Site) -> None:
    tomas = site.tester("tomas")
    assert tomas.post("/logout", data={"csrf_token": "neteisingas"}).status_code == 403
    assert tomas.get("/my/reports").status_code == 200

    admin = site.admin()
    site.submit(site.client(), "Svečio klaida")
    response = admin.post("/dashboard/reports/1/status", data={"status": "resolved", "csrf_token": "x"})
    assert response.status_code == 403
    assert site.query("SELECT status FROM bug_reports")[0]["status"] == "new"


def test_form_csrf_cookie_is_http_only_and_not_a_session(site: Site) -> None:
    response = site.client().get("/register")
    cookie = response.headers["set-cookie"]

    assert cookie.startswith("bakalauras_form_csrf=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert re.search(r'name="form_csrf" value="[^"]{30,}"', response.text)



# --- PR #14 peržiūra: CSRF viešoje formoje ---------------------------------------------------


def test_report_form_sets_form_csrf_for_guest_and_user(site: Site) -> None:
    guest = site.client().get("/report")
    tester = site.tester("tomas").get("/report")

    for page in (guest, tester):
        assert page.status_code == 200
        assert re.search(r'name="form_csrf" value="[^"]{30,}"', page.text)
    assert "bakalauras_form_csrf=" in guest.headers["set-cookie"]


@pytest.mark.parametrize("logged_in", [False, True])
def test_report_without_valid_csrf_is_rejected_and_not_saved(site: Site, logged_in: bool) -> None:
    client = site.tester("tomas") if logged_in else site.client()
    valid = form_csrf(client, "/report")
    data = {"title": "Klaida", "description": "Aprašymas pakankamai ilgas."}

    no_token = client.post("/report", data=data, follow_redirects=False)
    wrong = client.post("/report", data={**data, "form_csrf": valid + "x"}, follow_redirects=False)
    other_browser = site.client()  # galiojantis žetonas, bet be atitinkamo slapuko (kita naršyklė)
    if logged_in:
        other_browser.cookies.set(SESSION_COOKIE_NAME, client.cookies.get(SESSION_COOKIE_NAME))
    foreign = other_browser.post("/report", data={**data, "form_csrf": valid}, follow_redirects=False)

    for response in (no_token, wrong, foreign):
        assert response.status_code == 403 and "CSRF" in response.text
    assert site.query("SELECT id FROM bug_reports") == []


def test_report_csrf_cannot_be_forged_to_link_report_to_logged_in_user(site: Site) -> None:
    """Kita svetainė negali pateikti klaidos prisijungusio testuotojo vardu (slapukas siunčiamas,
    bet formos žetono ji nežino)."""
    tomas = site.tester("tomas")

    attack = tomas.post("/report", data={"title": "Suklastota", "description": "Kitos svetainės forma."},
                        follow_redirects=False)
    legit = site.submit(tomas, "Tikra klaida")

    assert attack.status_code == 403 and legit.status_code == 303
    rows = site.query("SELECT title, reporter_user_id FROM bug_reports")
    assert [r["title"] for r in rows] == ["Tikra klaida"] and rows[0]["reporter_user_id"] is not None


def test_report_csrf_works_without_login_configuration(tmp_path: Path) -> None:
    """Vieša forma veikia ir be paskyrų konfigūracijos (atsarginis programos raktas)."""
    app = create_app()
    app.dependency_overrides[get_database_path] = lambda: tmp_path / "no-auth.sqlite3"
    use_test_auth(app, None)
    client = TestClient(app)

    assert submit_report(client, "Svečio klaida", "Aprašymas pakankamai ilgas.").status_code == 303
    rejected = client.post("/report", data={"title": "A", "description": "Aprašymas pakankamai ilgas."})
    assert rejected.status_code == 403


def test_invalid_report_keeps_csrf_token_for_resubmission(site: Site) -> None:
    client = site.client()

    first = submit_report(client, "", "Aprašymas")
    token = re.search(r'name="form_csrf" value="([^"]+)"', first.text).group(1)
    second = client.post("/report", data={"title": "Pataisyta", "description": "Aprašymas", "form_csrf": token},
                         follow_redirects=False)

    assert first.status_code == 400 and second.status_code == 303


# --- PR #14 peržiūra: nukreipimas po prisijungimo pagal rolę ---------------------------------


@pytest.mark.parametrize(
    "next_path",
    ["/dashboard", "/dashboard/reports/1", "/import", "/dashboard/training-data", "/my/reports/../../dashboard",
     "https://evil.example/", "//evil.example/"],
)
def test_tester_is_not_redirected_to_admin_pages_after_login(site: Site, next_path: str) -> None:
    register(site.client(), "tomas", "tomas@pavyzdys.lt", TESTER_PASSWORD)
    client = site.client()

    response = login(client, "tomas", TESTER_PASSWORD, next_path=next_path)

    assert response.status_code == 303 and response.headers["location"] == "/my/reports"


@pytest.mark.parametrize("next_path", ["/my/reports/5", "/my/reports", "/report", "/report/submitted"])
def test_tester_can_return_to_own_allowed_pages(site: Site, next_path: str) -> None:
    register(site.client(), "tomas", "tomas@pavyzdys.lt", TESTER_PASSWORD)

    response = login(site.client(), "tomas", TESTER_PASSWORD, next_path=next_path)

    assert response.headers["location"] == next_path


def test_developer_redirect_is_limited_like_tester(site: Site) -> None:
    register(site.client(), "programuotoja", "p@pavyzdys.lt", TESTER_PASSWORD)
    site.change(set_role, "programuotoja", "developer")

    assert login(site.client(), "programuotoja", TESTER_PASSWORD, next_path="/dashboard").headers["location"] == "/my/reports"


@pytest.mark.parametrize(
    ("next_path", "expected"),
    [("/dashboard/reports/7?message=x", "/dashboard/reports/7?message=x"), ("/import", "/import"),
     ("/dashboard/training-data", "/dashboard/training-data"), ("/my/reports", "/my/reports"),
     ("https://evil.example/", "/dashboard"), ("/my/reports/../../import", "/dashboard"), ("", "/dashboard")],
)
def test_admin_returns_to_legitimate_internal_page(site: Site, next_path: str, expected: str) -> None:
    assert login(site.client(), next_path=next_path).headers["location"] == expected


def test_logged_in_tester_visiting_login_with_admin_next_goes_home(site: Site) -> None:
    client = site.tester("tomas")

    response = client.get("/login?next=%2Fdashboard", follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/my/reports"


def test_tester_redirected_from_admin_page_to_login_lands_on_own_page(site: Site) -> None:
    register(site.client(), "tomas", "tomas@pavyzdys.lt", TESTER_PASSWORD)
    client = site.client()

    first = client.get("/dashboard", follow_redirects=False)  # neprisijungus: /login?next=%2Fdashboard
    assert first.headers["location"] == "/login?next=%2Fdashboard"
    response = login(client, "tomas", TESTER_PASSWORD, next_path="/dashboard")

    assert response.headers["location"] == "/my/reports"
    assert client.get(response.headers["location"]).status_code == 200
