"""Vienos vidinės paskyros prisijungimas, pasirašyta sesija ir CSRF apsauga.

Naudojama tik standartinė biblioteka:
- slaptažodis saugomas tik kaip PBKDF2-SHA256 maišas (ADMIN_PASSWORD_HASH);
- sesija laikoma slapuke, pasirašytame HMAC-SHA256 su SESSION_SECRET_KEY;
- kiekviena sesija turi atsitiktinį CSRF žetoną, tikrinamą visuose POST veiksmuose.

Maišui ir raktui sugeneruoti: `python -m app.auth`.
"""

import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, Request

SESSION_COOKIE_NAME = "bakalauras_session"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
PASSWORD_HASH_ITERATIONS = 600_000
MIN_SECRET_KEY_LENGTH = 32
MIN_PASSWORD_LENGTH = 10
_HASH_ALGORITHM = "pbkdf2_sha256"


class LoginRequired(Exception):
    """Vidinis maršrutas pasiektas neprisijungus."""


class CsrfError(Exception):
    """Trūksta CSRF žetono arba jis neteisingas."""


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password_hash: str
    secret_key: str
    cookie_secure: bool = False


@dataclass(frozen=True)
class Session:
    username: str
    csrf_token: str


# --- Slaptažodžio maišas ---------------------------------------------------


def hash_password(password: str, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    """Grąžina `pbkdf2_sha256:iteracijos:druska:maišas` (be `$`, kad būtų patogu Windows)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations)
    return f"{_HASH_ALGORITHM}:{iterations}:{salt}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split(":")
        if algorithm != _HASH_ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), expected)


def check_credentials(settings: AuthSettings, username: str, password: str) -> bool:
    # Slaptažodis tikrinamas visada, kad atsakymo laikas neišduotų, ar vardas teisingas.
    password_ok = verify_password(password, settings.password_hash)
    username_ok = hmac.compare_digest(username.encode(), settings.username.encode())
    return password_ok and username_ok


# --- Nustatymai iš aplinkos ------------------------------------------------


def get_auth_settings() -> AuthSettings | None:
    """Grąžina nustatymus arba None, jei prisijungimas nesukonfigūruotas.

    Numatytojo slaptažodžio nėra: be visų kintamųjų prisijungti neįmanoma.
    """
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    secret_key = os.environ.get("SESSION_SECRET_KEY", "").strip()
    if not username or not password_hash.startswith(f"{_HASH_ALGORITHM}:"):
        return None
    if len(secret_key) < MIN_SECRET_KEY_LENGTH:
        return None
    cookie_secure = os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return AuthSettings(username, password_hash, secret_key, cookie_secure)


# --- Pasirašyta sesija -----------------------------------------------------


def _sign(secret_key: str, payload: str) -> str:
    return hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _password_fingerprint(settings: AuthSettings) -> str:
    # Pakeitus slaptažodį, visos senos sesijos tampa negaliojančios.
    return hashlib.sha256(settings.password_hash.encode()).hexdigest()[:16]


def create_session_token(settings: AuthSettings, now: float | None = None) -> str:
    issued = time.time() if now is None else now
    data = {
        "user": settings.username,
        "csrf": secrets.token_urlsafe(32),
        "exp": int(issued) + SESSION_MAX_AGE_SECONDS,
        "pw": _password_fingerprint(settings),
    }
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return f"{payload}.{_sign(settings.secret_key, payload)}"


def read_session_token(
    settings: AuthSettings, token: str, now: float | None = None
) -> Session | None:
    """Patikrina parašą, galiojimą ir naudotoją; kitu atveju grąžina None."""
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(signature, _sign(settings.secret_key, payload)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        expires = int(data["exp"])
        username, csrf, fingerprint = data["user"], data["csrf"], data["pw"]
    except (ValueError, KeyError, TypeError):
        return None
    current = time.time() if now is None else now
    if expires < current:
        return None
    if username != settings.username or fingerprint != _password_fingerprint(settings):
        return None
    return Session(username=username, csrf_token=csrf)


def get_current_session(
    request: Request, settings: AuthSettings | None = Depends(get_auth_settings)
) -> Session | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if settings is None or not token:
        return None
    return read_session_token(settings, token)


def require_login(session: Session | None = Depends(get_current_session)) -> Session:
    """Priklausomybė visiems vidiniams maršrutams (taip pat 4–6 etapų)."""
    if session is None:
        raise LoginRequired()
    return session


def check_csrf(session: Session, submitted_token: str) -> None:
    if not submitted_token or not hmac.compare_digest(submitted_token, session.csrf_token):
        raise CsrfError()


def is_secure_request(request: Request, settings: AuthSettings) -> bool:
    """`Secure` slapukas, kai įjungta konfigūracijoje arba užklausa atėjo per HTTPS."""
    return settings.cookie_secure or request.url.scheme == "https"


def safe_next_path(value: str | None) -> str:
    """Leidžia grįžti tik į vidinį kelią šioje svetainėje (apsauga nuo open redirect)."""
    if value and value.startswith("/") and not value.startswith(("//", "/\\")):
        return value
    return "/dashboard"


# --- Komandinė eilutė: maišo ir rakto generavimas -------------------------


def main() -> None:
    print("Vidinės paskyros slaptažodžio maišo ir sesijos rakto generavimas.")
    password = getpass.getpass("Naujas slaptažodis: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Slaptažodis per trumpas: reikia bent {MIN_PASSWORD_LENGTH} simbolių.")
    if getpass.getpass("Pakartokite slaptažodį: ") != password:
        raise SystemExit("Slaptažodžiai nesutampa.")
    print()
    print("Įrašykite šias eilutes į .env failą (ne į .env.example ir ne į GitHub):")
    print(f"ADMIN_PASSWORD_HASH={hash_password(password)}")
    print(f"SESSION_SECRET_KEY={secrets.token_hex(32)}")


if __name__ == "__main__":
    main()
