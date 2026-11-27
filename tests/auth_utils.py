"""Bendri testų įrankiai prisijungimui (be tikrų slaptažodžių ir be tinklo)."""

import re

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import AuthSettings, get_auth_settings, hash_password

TEST_USERNAME = "programuotojas"
TEST_PASSWORD = "testinis-slaptazodis-123"
# Mažas iteracijų skaičius tik tam, kad testai būtų greiti.
TEST_SETTINGS = AuthSettings(
    username=TEST_USERNAME,
    password_hash=hash_password(TEST_PASSWORD, iterations=1_000),
    secret_key="testams-skirtas-sesijos-raktas-0123456789",
)

_CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
_FORM_CSRF_RE = re.compile(r'name="form_csrf" value="([^"]+)"')


def use_test_auth(app: FastAPI, settings: AuthSettings | None = TEST_SETTINGS) -> None:
    app.dependency_overrides[get_auth_settings] = lambda: settings


def form_csrf(client: TestClient, path: str = "/login") -> str:
    """6A: prisijungimo / registracijos formos CSRF žetonas (kartu nustatomas ir slapukas)."""
    match = _FORM_CSRF_RE.search(client.get(path).text)
    return match.group(1) if match else ""  # nesukonfigūruotoje sistemoje formos nėra


def login(
    client: TestClient,
    username: str = TEST_USERNAME,
    password: str = TEST_PASSWORD,
    next_path: str | None = None,
) -> httpx.Response:
    """Prisijungia kaip naršyklė: atidaro formą (CSRF slapukas + žetonas) ir ją pateikia."""
    data = {"username": username, "password": password, "form_csrf": form_csrf(client)}
    if next_path is not None:
        data["next"] = next_path
    return client.post("/login", data=data, follow_redirects=False)


def register(
    client: TestClient,
    username: str,
    email: str,
    password: str = "testuotojo-slaptazodis-1",
    password_confirm: str | None = None,
    **extra: str,
) -> httpx.Response:
    data = {
        "username": username,
        "email": email,
        "password": password,
        "password_confirm": password if password_confirm is None else password_confirm,
        "form_csrf": form_csrf(client, "/register"),
        **extra,
    }
    return client.post("/register", data=data, follow_redirects=False)


def csrf_token(client: TestClient, path: str = "/dashboard") -> str:
    match = _CSRF_RE.search(client.get(path).text)
    assert match, f"CSRF žetonas nerastas puslapyje {path}"
    return match.group(1)
