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


def use_test_auth(app: FastAPI, settings: AuthSettings | None = TEST_SETTINGS) -> None:
    app.dependency_overrides[get_auth_settings] = lambda: settings


def login(
    client: TestClient, username: str = TEST_USERNAME, password: str = TEST_PASSWORD
) -> httpx.Response:
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def csrf_token(client: TestClient, path: str = "/dashboard") -> str:
    match = _CSRF_RE.search(client.get(path).text)
    assert match, f"CSRF žetonas nerastas puslapyje {path}"
    return match.group(1)
