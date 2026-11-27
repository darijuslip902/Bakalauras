"""Prisijungimas, pasirašyta sesija, rolės ir CSRF apsauga (6A: naudotojų paskyros DB).

Naudojama tik standartinė biblioteka:
- slaptažodžiai saugomi tik kaip PBKDF2-SHA256 maiša (`users.password_hash`; pradinis
  administratorius – iš ADMIN_PASSWORD_HASH, žr. `app.services.user_service.bootstrap_admin`);
- sesija laikoma slapuke, pasirašytame HMAC-SHA256 su SESSION_SECRET_KEY. Slapuke tik stabilus
  naudotojo ID, CSRF žetonas ir slaptažodžio maišos „pirštų atspaudas“; rolė ir aktyvumas
  kiekvienos užklausos metu skaitomi iš DB, todėl jų pakeitimas galioja iš karto;
- kiekviena sesija turi atsitiktinį CSRF žetoną, tikrinamą visuose POST veiksmuose; prisijungimo
  ir registracijos formos (dar be sesijos) saugomos dvigubo pateikimo CSRF slapuku.

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
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, Request

from app.db import get_connection, get_database_path, init_db

SESSION_COOKIE_NAME = "bakalauras_session"
FORM_CSRF_COOKIE_NAME = "bakalauras_form_csrf"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
PASSWORD_HASH_ITERATIONS = 600_000
MIN_SECRET_KEY_LENGTH = 32
MIN_PASSWORD_LENGTH = 10
_HASH_ALGORITHM = "pbkdf2_sha256"


class LoginRequired(Exception):
    """Vidinis maršrutas pasiektas neprisijungus."""


class CsrfError(Exception):
    """Trūksta CSRF žetono arba jis neteisingas."""


class Forbidden(Exception):
    """Naudotojas prisijungęs, bet jo rolė neleidžia šio veiksmo (HTTP 403)."""


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password_hash: str
    secret_key: str
    cookie_secure: bool = False


@dataclass(frozen=True)
class Session:
    """Prisijungęs naudotojas. Rolė ir aktyvumas jau patikrinti DB šios užklausos metu."""

    user_id: int
    username: str
    role: str
    csrf_token: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass(frozen=True)
class SessionClaims:
    """Pasirašyto slapuko turinys (dar nepatikrintas su DB)."""

    user_id: int
    csrf_token: str
    password_fingerprint: str


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


def password_fingerprint(password_hash: str) -> str:
    # Pakeitus slaptažodį, visos senos to naudotojo sesijos tampa negaliojančios.
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_session_token(
    settings: AuthSettings, user_id: int, password_hash: str, now: float | None = None
) -> str:
    issued = time.time() if now is None else now
    data = {
        "uid": int(user_id),
        "csrf": secrets.token_urlsafe(32),
        "exp": int(issued) + SESSION_MAX_AGE_SECONDS,
        "pw": password_fingerprint(password_hash),
    }
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return f"{payload}.{_sign(settings.secret_key, payload)}"


def read_session_token(
    settings: AuthSettings, token: str, now: float | None = None
) -> SessionClaims | None:
    """Patikrina parašą ir galiojimą; kitu atveju grąžina None. Naudotojas tikrinamas DB atskirai."""
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(signature, _sign(settings.secret_key, payload)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        expires = int(data["exp"])
        user_id, csrf, fingerprint = int(data["uid"]), str(data["csrf"]), str(data["pw"])
    except (ValueError, KeyError, TypeError):
        return None
    current = time.time() if now is None else now
    if expires < current:
        return None
    return SessionClaims(user_id=user_id, csrf_token=csrf, password_fingerprint=fingerprint)


def session_for_user(claims: SessionClaims, user: object | None) -> Session | None:
    """Sesija galioja tik esamam, aktyviam naudotojui su nepakeistu slaptažodžiu."""
    if user is None or not getattr(user, "is_active", False):
        return None
    if not hmac.compare_digest(claims.password_fingerprint, password_fingerprint(user.password_hash)):
        return None
    return Session(user_id=user.id, username=user.username, role=user.role, csrf_token=claims.csrf_token)


def get_current_session(
    request: Request,
    settings: AuthSettings | None = Depends(get_auth_settings),
    database_path: Path = Depends(get_database_path),
) -> Session | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if settings is None or not token:
        return None
    claims = read_session_token(settings, token)
    if claims is None:
        return None
    from app.services.user_service import get_user  # vengiama ciklinio importo

    with get_connection(database_path) as conn:
        init_db(conn)
        return session_for_user(claims, get_user(conn, claims.user_id))


def require_login(session: Session | None = Depends(get_current_session)) -> Session:
    """Bet kuris prisijungęs aktyvus naudotojas (pvz. „Mano pranešimai“)."""
    if session is None:
        raise LoginRequired()
    return session


def require_role(*roles: str):
    """Centralizuotas rolių tikrinimas serverio pusėje: neprisijungus – į /login, kitaip 403."""

    def dependency(session: Session = Depends(require_login)) -> Session:
        if session.role not in roles:
            raise Forbidden()
        return session

    return dependency


# Esami vidiniai maršrutai (klaidų valdymas, importas, mokymo duomenys) – tik administratoriui.
# Programuotojo prieiga pagal kategorijas – 6B etapas.
require_admin = require_role("admin")


def check_csrf(session: Session, submitted_token: str) -> None:
    if not submitted_token or not hmac.compare_digest(submitted_token, session.csrf_token):
        raise CsrfError()


def is_secure_request(request: Request, settings: AuthSettings) -> bool:
    """`Secure` slapukas, kai įjungta konfigūracijoje arba užklausa atėjo per HTTPS."""
    return settings.cookie_secure or request.url.scheme == "https"


def safe_next_path(value: str | None, default: str = "/dashboard") -> str:
    """Leidžia grįžti tik į vidinį kelią šioje svetainėje (apsauga nuo open redirect)."""
    if value and value.startswith("/") and not value.startswith(("//", "/\\")):
        return value
    return default


def home_path(role: str) -> str:
    """Pradinis puslapis po prisijungimo pagal rolę."""
    return "/dashboard" if role == "admin" else "/my/reports"


# --- CSRF formoms be sesijos (prisijungimas, registracija) -------------------


def form_csrf_token(request: Request, settings: AuthSettings) -> tuple[str, str | None]:
    """Grąžina (žetonas formai, nauja slapuko reikšmė arba None, jei esamas slapukas tinka)."""
    cookie = request.cookies.get(FORM_CSRF_COOKIE_NAME, "")
    token, _, signature = cookie.partition(".")
    if token and hmac.compare_digest(signature, _sign(settings.secret_key, "form:" + token)):
        return token, None
    token = secrets.token_urlsafe(32)
    return token, f"{token}.{_sign(settings.secret_key, 'form:' + token)}"


def check_form_csrf(request: Request, settings: AuthSettings, submitted_token: str) -> None:
    """Dvigubas pateikimas: formos žetonas turi sutapti su pasirašytu slapuku."""
    cookie = request.cookies.get(FORM_CSRF_COOKIE_NAME, "")
    token, _, signature = cookie.partition(".")
    valid_cookie = bool(token) and hmac.compare_digest(signature, _sign(settings.secret_key, "form:" + token))
    if not valid_cookie or not submitted_token or not hmac.compare_digest(submitted_token, token):
        raise CsrfError()


# --- Prisijungimo bandymų ribojimas (be papildomos infrastruktūros) ------------

LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 15 * 60


class LoginRateLimiter:
    """Atmintyje laikomas nesėkmingų bandymų skaitiklis pagal (IP, vardas). Vienam procesui."""

    def __init__(self, max_failures: int = LOGIN_MAX_FAILURES, window: int = LOGIN_WINDOW_SECONDS) -> None:
        self.max_failures = max_failures
        self.window = window
        self._failures: dict[tuple[str, str], deque[float]] = {}

    def _recent(self, key: tuple[str, str], now: float) -> deque[float]:
        attempts = self._failures.setdefault(key, deque())
        while attempts and attempts[0] <= now - self.window:
            attempts.popleft()
        return attempts

    def is_blocked(self, key: tuple[str, str], now: float | None = None) -> bool:
        return len(self._recent(key, time.time() if now is None else now)) >= self.max_failures

    def record_failure(self, key: tuple[str, str], now: float | None = None) -> None:
        current = time.time() if now is None else now
        self._recent(key, current).append(current)

    def reset(self, key: tuple[str, str]) -> None:
        self._failures.pop(key, None)


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
