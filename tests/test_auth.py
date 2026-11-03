import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth, config
from app.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    AuthSettings,
    create_session_token,
    get_auth_settings,
    hash_password,
    read_session_token,
    safe_next_path,
    verify_password,
)
from app.main import create_app
from app.routes.issues import get_database_path
from tests.auth_utils import (
    TEST_PASSWORD,
    TEST_SETTINGS,
    TEST_USERNAME,
    csrf_token,
    login,
    use_test_auth,
)

# Maršrutai, kurie sąmoningai vieši. Visi kiti turi reikalauti prisijungimo.
PUBLIC_PATHS = {
    "/",
    "/health",
    "/report",
    "/report/submitted",
    "/login",
    "/logout",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_database_path] = lambda: tmp_path / "auth.sqlite3"
    use_test_auth(app)
    return TestClient(app)


# --- Slaptažodžio maišas ir nustatymai ------------------------------------


def test_password_hash_verifies_only_correct_password() -> None:
    stored = hash_password("teisingas-slaptazodis", iterations=1_000)

    assert stored.startswith("pbkdf2_sha256:1000:")
    assert "teisingas-slaptazodis" not in stored
    assert "$" not in stored  # patogu PowerShell / .env
    assert verify_password("teisingas-slaptazodis", stored)
    assert not verify_password("neteisingas", stored)
    assert not verify_password("teisingas-slaptazodis", "sugadintas")
    assert not verify_password("teisingas-slaptazodis", "md5:1:aa:bb")


def test_same_password_gets_different_salt() -> None:
    assert hash_password("x" * 12, iterations=1_000) != hash_password("x" * 12, iterations=1_000)


def _set_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name in ("ADMIN_USERNAME", "ADMIN_PASSWORD_HASH", "SESSION_SECRET_KEY", "SESSION_COOKIE_SECURE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_settings_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    password_hash = hash_password("slaptazodis-1", iterations=1_000)
    _set_env(
        monkeypatch,
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD_HASH=password_hash,
        SESSION_SECRET_KEY="k" * 64,
        SESSION_COOKIE_SECURE="true",
    )

    assert get_auth_settings() == AuthSettings("admin", password_hash, "k" * 64, True)


@pytest.mark.parametrize(
    "values",
    [
        {},  # niekas nenustatyta – numatytojo slaptažodžio nėra
        {"ADMIN_USERNAME": "admin", "SESSION_SECRET_KEY": "k" * 64},
        {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD_HASH": "atviras-slaptazodis", "SESSION_SECRET_KEY": "k" * 64},
        {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD_HASH": "pbkdf2_sha256:1:aa:bb", "SESSION_SECRET_KEY": "per-trumpas"},
        {"ADMIN_PASSWORD_HASH": "pbkdf2_sha256:1:aa:bb", "SESSION_SECRET_KEY": "k" * 64},
    ],
)
def test_incomplete_configuration_disables_login(monkeypatch: pytest.MonkeyPatch, values: dict) -> None:
    _set_env(monkeypatch, **values)

    assert get_auth_settings() is None


def test_env_file_is_loaded_without_overriding_real_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# komentaras\n\nTEST_ENV_A=is-failo\nTEST_ENV_B='kabutese'\nTEST_ENV_C=is-failo\nnetinkama eilute\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TEST_ENV_A", raising=False)
    monkeypatch.delenv("TEST_ENV_B", raising=False)
    monkeypatch.setenv("TEST_ENV_C", "is-aplinkos")

    config.load_env_file(env_file)
    config.load_env_file(tmp_path / "nera.env")  # neegzistuojantis failas ignoruojamas

    import os

    assert os.environ["TEST_ENV_A"] == "is-failo"
    assert os.environ["TEST_ENV_B"] == "kabutese"
    assert os.environ["TEST_ENV_C"] == "is-aplinkos"
    for name in ("TEST_ENV_A", "TEST_ENV_B"):
        monkeypatch.delenv(name)


# --- Pasirašyta sesija ----------------------------------------------------


def test_session_token_roundtrip_and_tampering() -> None:
    token = create_session_token(TEST_SETTINGS, now=1_000)

    session = read_session_token(TEST_SETTINGS, token, now=1_001)
    assert session is not None
    assert session.username == TEST_USERNAME
    assert len(session.csrf_token) >= 32

    payload, signature = token.split(".")
    assert read_session_token(TEST_SETTINGS, payload + "." + "0" * len(signature), now=1_001) is None
    assert read_session_token(TEST_SETTINGS, "x" + token, now=1_001) is None
    assert read_session_token(TEST_SETTINGS, "netinkamas", now=1_001) is None


def test_session_token_expires() -> None:
    token = create_session_token(TEST_SETTINGS, now=1_000)

    assert read_session_token(TEST_SETTINGS, token, now=1_000 + SESSION_MAX_AGE_SECONDS) is not None
    assert read_session_token(TEST_SETTINGS, token, now=1_001 + SESSION_MAX_AGE_SECONDS) is None


def test_session_is_invalid_with_other_key_or_changed_password() -> None:
    token = create_session_token(TEST_SETTINGS, now=1_000)
    other_key = AuthSettings(TEST_USERNAME, TEST_SETTINGS.password_hash, "kitas-raktas-" + "x" * 32)
    new_password = AuthSettings(
        TEST_USERNAME, hash_password("naujas-slaptazodis", iterations=1_000), TEST_SETTINGS.secret_key
    )

    assert read_session_token(other_key, token, now=1_001) is None
    assert read_session_token(new_password, token, now=1_001) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/dashboard/reports/1", "/dashboard/reports/1"),
        ("/dashboard?status=new", "/dashboard?status=new"),
        ("", "/dashboard"),
        (None, "/dashboard"),
        ("https://evil.example/", "/dashboard"),
        ("//evil.example/", "/dashboard"),
        ("/\\evil.example/", "/dashboard"),
        ("dashboard", "/dashboard"),
    ],
)
def test_safe_next_path_prevents_open_redirect(value: str | None, expected: str) -> None:
    assert safe_next_path(value) == expected


# --- Prisijungimas ir atsijungimas per HTTP --------------------------------


def test_login_page_is_public(client: TestClient) -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert 'name="username"' in response.text
    assert 'type="password"' in response.text


def test_login_with_correct_credentials_creates_secure_session(client: TestClient) -> None:
    response = login(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert f"Max-Age={SESSION_MAX_AGE_SECONDS}" in cookie
    assert "Secure" not in cookie  # vietinis HTTP prototipas veikia
    assert TEST_PASSWORD not in cookie

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert TEST_USERNAME in dashboard.text
    assert "Atsijungti" in dashboard.text


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (TEST_USERNAME, "neteisingas-slaptazodis"),
        ("kitas", TEST_PASSWORD),
        ("", ""),
    ],
)
def test_login_with_wrong_credentials_is_rejected(client: TestClient, username: str, password: str) -> None:
    response = login(client, username, password)

    assert response.status_code == 401
    assert "Neteisingas naudotojo vardas arba slaptažodis" in response.text
    assert "set-cookie" not in response.headers
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_login_redirects_back_to_requested_internal_page(client: TestClient) -> None:
    first = client.get("/dashboard/reports/5", follow_redirects=False)
    assert first.headers["location"] == "/login?next=%2Fdashboard%2Freports%2F5"

    form = client.get(first.headers["location"])
    assert 'name="next" value="/dashboard/reports/5"' in form.text

    response = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "next": "/dashboard/reports/5"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/dashboard/reports/5"

    evil = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "next": "https://evil.example/"},
        follow_redirects=False,
    )
    assert evil.headers["location"] == "/dashboard"


def test_cookie_is_secure_when_configured_or_over_https(tmp_path: Path) -> None:
    app = create_app()
    use_test_auth(app, AuthSettings(TEST_USERNAME, TEST_SETTINGS.password_hash, TEST_SETTINGS.secret_key, True))
    assert "Secure" in login(TestClient(app)).headers["set-cookie"]

    https_app = create_app()
    use_test_auth(https_app)
    https_client = TestClient(https_app, base_url="https://testserver")
    assert "Secure" in login(https_client).headers["set-cookie"]


def test_login_not_configured_shows_message_and_blocks_access(tmp_path: Path) -> None:
    app = create_app()
    use_test_auth(app, None)
    client = TestClient(app)

    page = client.get("/login")
    attempt = login(client)

    assert page.status_code == 503
    assert "Prisijungimas nesukonfigūruotas" in page.text
    assert attempt.status_code == 503
    assert "set-cookie" not in attempt.headers
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_logged_in_user_visiting_login_is_redirected(client: TestClient) -> None:
    login(client)

    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_logout_requires_csrf_and_ends_session(client: TestClient) -> None:
    login(client)
    token = csrf_token(client)

    rejected = client.post("/logout", data={"csrf_token": "neteisingas"}, follow_redirects=False)
    assert rejected.status_code == 403
    assert client.get("/dashboard", follow_redirects=False).status_code == 200

    response = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?logged_out=1"
    assert f'{SESSION_COOKIE_NAME}=""' in response.headers["set-cookie"]

    after = client.get("/dashboard", follow_redirects=False)
    assert after.status_code == 303
    assert "Atsijungėte" in client.get("/login?logged_out=1").text


def test_logout_is_not_available_via_get(client: TestClient) -> None:
    login(client)

    assert client.get("/logout").status_code == 405
    assert client.get("/dashboard", follow_redirects=False).status_code == 200


def test_forged_or_foreign_session_cookie_is_rejected(client: TestClient) -> None:
    other = AuthSettings(TEST_USERNAME, TEST_SETTINGS.password_hash, "svetimas-raktas-" + "z" * 32)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(other))

    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_internal_pages_disable_caching_and_framing(client: TestClient) -> None:
    login(client)

    response = client.get("/dashboard")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"


def test_every_non_public_route_requires_login(client: TestClient) -> None:
    """Apsauga ateičiai: naujas vidinis maršrutas be `require_login` čia sugriūtų."""
    checked = 0
    # Vieša OpenAPI schema apima visus įtrauktus maršrutus (taip pat būsimų etapų).
    for route_path, operations in client.app.openapi()["paths"].items():
        if route_path in PUBLIC_PATHS:
            continue
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        for method in operations:
            response = client.request(method.upper(), path, follow_redirects=False)
            assert response.status_code == 303, f"{method} {route_path} pasiekiamas neprisijungus"
            assert response.headers["location"].startswith("/login")
            checked += 1
    assert checked >= 5  # /import (GET, POST), /dashboard, detalės, būsenos keitimas


def test_public_routes_still_work_without_login(client: TestClient) -> None:
    for path in ("/", "/health", "/report", "/report/submitted", "/login"):
        assert client.get(path).status_code == 200, path

    response = client.post(
        "/report", data={"title": "Vieša klaida", "description": "Be prisijungimo"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/report/submitted"


def test_auth_module_has_no_default_password() -> None:
    source = Path(auth.__file__).read_text(encoding="utf-8")

    assert "ADMIN_PASSWORD=" not in source
    assert not re.search(r"pbkdf2_sha256:\d+:[0-9a-f]{32}:[0-9a-f]{64}", source)
