"""6A: naudotojų paskyros (vienos organizacijos), registracija ir administratoriaus perkėlimas.

Visos SQL užklausos parametrizuotos. Slaptažodžiai saugomi tik kaip PBKDF2-SHA256 maiša.
Viešai registruojantis visada sukuriama `tester` rolė; `developer` / `admin` suteikiami tik
administratoriaus veiksmu (6B: puslapis `/admin/users` arba `python -m tools.users`).
"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from app import config
from app.auth import (
    MIN_PASSWORD_LENGTH,
    AuthSettings,
    hash_password,
    verify_password,
)

ROLES = ("tester", "developer", "admin")
ROLE_LABELS = {"tester": "Testuotojas", "developer": "Programuotojas", "admin": "Administratorius"}
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 40
EMAIL_MAX_LENGTH = 254
PASSWORD_MAX_LENGTH = 200  # apsauga nuo itin ilgų įvesčių PBKDF2 skaičiavimui

_USERNAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# Paprastas, bet griežtas patikrinimas: vienas @, domene bent vienas taškas, be tarpų.
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")
# Laiko išlyginimas: neegzistuojančiam vardui vis tiek atliekamas PBKDF2 skaičiavimas.
_DUMMY_HASH = hash_password("vartotojo-nera-laiko-islyginimas", iterations=1_000)

_USER_COLUMNS = "id, username, email, password_hash, role, is_active, created_at, updated_at"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class User:
    id: int
    username: str
    email: str | None
    password_hash: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str


def _to_user(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(
        id=row["id"], username=row["username"], email=row["email"],
        password_hash=row["password_hash"], role=row["role"], is_active=bool(row["is_active"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def get_user(conn: sqlite3.Connection, user_id: int) -> User | None:
    return _to_user(conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone())


def get_user_by_username(conn: sqlite3.Connection, username: str) -> User | None:
    # Stulpelis COLLATE NOCASE: vardas lyginamas nepriklausomai nuo raidžių dydžio.
    row = conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE username = ?", (username.strip(),)).fetchone()
    return _to_user(row)


def list_users(conn: sqlite3.Connection) -> list[User]:
    return [_to_user(row) for row in conn.execute(f"SELECT {_USER_COLUMNS} FROM users ORDER BY id")]


# --- Registracija ------------------------------------------------------------


@dataclass(frozen=True)
class RegistrationForm:
    username: str
    email: str
    password: str
    password_confirm: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_registration(
    form: RegistrationForm, reserved_username: str = ""
) -> dict[str, str]:
    """Serverio pusės validacija. Grąžina laukas -> klaidos pranešimas."""
    errors: dict[str, str] = {}
    username = form.username.strip()
    if not USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH:
        errors["username"] = (
            f"Naudotojo vardas turi būti {USERNAME_MIN_LENGTH}–{USERNAME_MAX_LENGTH} simbolių."
        )
    elif not _USERNAME_RE.fullmatch(username):
        errors["username"] = (
            "Naudotojo varde leidžiamos tik lotyniškos raidės, skaičiai ir simboliai . _ -"
        )
    elif reserved_username and username.casefold() == reserved_username.strip().casefold():
        errors["username"] = "Šis naudotojo vardas jau užimtas."
    email = normalize_email(form.email)
    if not email or len(email) > EMAIL_MAX_LENGTH or not _EMAIL_RE.fullmatch(email):
        errors["email"] = "Įveskite teisingą el. pašto adresą."
    if len(form.password) < MIN_PASSWORD_LENGTH:
        errors["password"] = f"Slaptažodis turi būti bent {MIN_PASSWORD_LENGTH} simbolių."
    elif len(form.password) > PASSWORD_MAX_LENGTH:
        errors["password"] = f"Slaptažodis negali būti ilgesnis nei {PASSWORD_MAX_LENGTH} simbolių."
    elif form.password != form.password_confirm:
        errors["password_confirm"] = "Slaptažodžiai nesutampa."
    return errors


class DuplicateUserError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field  # "username" arba "email"


def _create_user(
    conn: sqlite3.Connection, username: str, email: str | None, password_hash: str, role: str
) -> User:
    if role not in ROLES:
        raise ValueError("neleistina rolė")
    now = _utc_now()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (username, email, password_hash, role, is_active, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 1, ?, ?)",
                (username, email, password_hash, role, now, now),
            )
    except sqlite3.IntegrityError as error:
        field = "email" if "users.email" in str(error) else "username"
        raise DuplicateUserError(field) from None
    return get_user(conn, cursor.lastrowid)


def register_tester(
    conn: sqlite3.Connection, form: RegistrationForm, iterations: int | None = None
) -> User:
    """Viešos registracijos vienintelis kelias: rolė visada `tester` (jokio rolės parametro)."""
    password_hash = hash_password(form.password) if iterations is None else hash_password(form.password, iterations)
    return _create_user(conn, form.username.strip(), normalize_email(form.email), password_hash, "tester")


# --- Prisijungimas ir esamo administratoriaus perkėlimas -----------------------


class AdminBootstrap(Enum):
    CREATED = "created"
    EXISTS = "exists"            # admin jau perkeltas – niekas nekeičiama
    CONFLICT = "conflict"        # vardas užimtas ne administratoriaus paskyros – nieko neperrašome
    NOT_CONFIGURED = "not_configured"


def bootstrap_admin(conn: sqlite3.Connection, settings: AuthSettings | None) -> AdminBootstrap:
    """Idempotentiškai perkelia `.env` administratorių (ADMIN_USERNAME, ADMIN_PASSWORD_HASH) į `users`.

    Saugo tą patį vardą ir tą pačią maišą (slaptažodis nepasikeičia). Esama paskyra niekada
    neperrašoma; numatytojo slaptažodžio nėra.
    """
    if settings is None or not settings.username or not settings.password_hash:
        return AdminBootstrap.NOT_CONFIGURED
    existing = get_user_by_username(conn, settings.username)
    if existing is not None:
        return AdminBootstrap.EXISTS if existing.role == "admin" else AdminBootstrap.CONFLICT
    try:
        _create_user(conn, settings.username.strip(), None, settings.password_hash, "admin")
    except DuplicateUserError:  # lygiagretus sukūrimas – rezultatą nustatome iš naujo
        return bootstrap_admin(conn, settings)
    return AdminBootstrap.CREATED


class LoginResult(Enum):
    OK = "ok"
    INVALID = "invalid"
    INACTIVE = "inactive"
    ADMIN_CONFLICT = "admin_conflict"


def authenticate(
    conn: sqlite3.Connection, settings: AuthSettings, username: str, password: str
) -> tuple[LoginResult, User | None]:
    """Patikrina prisijungimą. Jei `.env` administratorius dar neperkeltas į `users`, perkelia jį
    tik tada, kai įvestas teisingas jo slaptažodis (taip niekas negali „užimti“ jo paskyros)."""
    username = username.strip()
    if len(password) > PASSWORD_MAX_LENGTH:
        return LoginResult.INVALID, None
    user = get_user_by_username(conn, username) if username else None
    if user is None:
        is_env_admin = bool(settings.username) and username.casefold() == settings.username.strip().casefold()
        if is_env_admin and verify_password(password, settings.password_hash):
            if bootstrap_admin(conn, settings) is AdminBootstrap.CONFLICT:
                return LoginResult.ADMIN_CONFLICT, None
            user = get_user_by_username(conn, username)
            return (LoginResult.OK, user) if user and user.is_active else (LoginResult.INACTIVE, None)
        verify_password(password, _DUMMY_HASH)  # vienodas atsakymo laikas
        return LoginResult.INVALID, None
    if not verify_password(password, user.password_hash):
        return LoginResult.INVALID, None
    if not user.is_active:
        return LoginResult.INACTIVE, None
    return LoginResult.OK, user


# --- Administratoriaus veiksmai (svetainė `/admin/users` ir CLI `tools.users`) ---------
#
# Visi rolės / aktyvumo / specializacijų pakeitimai eina per šias funkcijas, todėl apsaugos
# (paskutinis administratorius, specializacijos tik programuotojui) galioja abiem keliais.
# Sesijos kiekvienos užklausos metu skaito rolę ir aktyvumą iš DB – pakeitimai galioja iš karto.

# Specializacijomis priskiriamos visos kategorijos, išskyrus `other`: „Kita“ visada lieka
# administratoriaus peržiūrai (6B paskirstymo taisyklė), todėl jos eilės programuotojams nėra.
ASSIGNABLE_CATEGORIES = tuple(label for label in config.CATEGORY_LABELS if label != "other")


class LastAdminError(Exception):
    """Veiksmas paliktų sistemą be nė vieno aktyvaus administratoriaus."""


class InvalidSpecialization(ValueError):
    """Neleistina kategorija arba naudotojas nėra programuotojas."""


# Atominė sąlyga vienoje UPDATE užklausoje: paskutinio aktyvaus administratoriaus pakeisti negalima.
_NOT_LAST_ACTIVE_ADMIN = (
    "NOT (role = 'admin' AND is_active = 1 AND "
    "(SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1) <= 1)"
)


def count_active_admins(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]


def change_role(conn: sqlite3.Connection, user_id: int, role: str) -> User | None:
    """Pakeičia rolę. Palikus `developer` rolę, jo specializacijos pašalinamos toje pačioje transakcijoje.

    None – naudotojas nerastas; LastAdminError – tai paskutinis aktyvus administratorius.
    """
    if role not in ROLES:
        raise ValueError("neleistina rolė")
    user = get_user(conn, user_id)
    if user is None:
        return None
    if user.role == role:
        return user
    guard = f" AND {_NOT_LAST_ACTIVE_ADMIN}" if role != "admin" else ""
    with conn:
        cursor = conn.execute(
            f"UPDATE users SET role = ?, updated_at = ? WHERE id = ?{guard}", (role, _utc_now(), user_id)
        )
        if cursor.rowcount == 0:
            raise LastAdminError()
        if role != "developer":
            conn.execute("DELETE FROM developer_categories WHERE user_id = ?", (user_id,))
    return get_user(conn, user_id)


def change_active(conn: sqlite3.Connection, user_id: int, active: bool) -> User | None:
    """Aktyvuoja / išjungia paskyrą (specializacijos išlieka, bet neaktyvus naudotojas jų nemato)."""
    user = get_user(conn, user_id)
    if user is None:
        return None
    if user.is_active == active:
        return user
    guard = "" if active else f" AND {_NOT_LAST_ACTIVE_ADMIN}"
    with conn:
        cursor = conn.execute(
            f"UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?{guard}",
            (1 if active else 0, _utc_now(), user_id),
        )
        if cursor.rowcount == 0:
            raise LastAdminError()
    return get_user(conn, user_id)


def developer_categories(conn: sqlite3.Connection, user_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT category_label FROM developer_categories WHERE user_id = ? ORDER BY category_label", (user_id,)
    )
    return [row["category_label"] for row in rows]


def all_developer_categories(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """Naudotojo ID -> jo specializacijos (administravimo puslapiui)."""
    result: dict[int, list[str]] = {}
    for row in conn.execute("SELECT user_id, category_label FROM developer_categories ORDER BY category_label"):
        result.setdefault(row["user_id"], []).append(row["category_label"])
    return result


def set_developer_categories(conn: sqlite3.Connection, user_id: int, labels: list[str]) -> list[str]:
    """Pakeičia visą programuotojo specializacijų sąrašą (tuščias sąrašas – visas pašalina)."""
    clean = sorted({label.strip() for label in labels})
    invalid = [label for label in clean if label not in ASSIGNABLE_CATEGORIES]
    if invalid:
        raise InvalidSpecialization("neleistina kategorija")
    user = get_user(conn, user_id)
    if user is None or user.role != "developer":
        raise InvalidSpecialization("specializacijas galima priskirti tik programuotojui")
    now = _utc_now()
    with conn:
        conn.execute("DELETE FROM developer_categories WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO developer_categories (user_id, category_label, created_at) VALUES (?, ?, ?)",
            [(user_id, label, now) for label in clean],
        )
    return clean


def _by_username(conn: sqlite3.Connection, username: str) -> int | None:
    user = get_user_by_username(conn, username)
    return user.id if user else None


def set_role(conn: sqlite3.Connection, username: str, role: str) -> User | None:
    """CLI: kaip `change_role`, tik pagal naudotojo vardą."""
    if role not in ROLES:
        raise ValueError("neleistina rolė")
    user_id = _by_username(conn, username)
    return None if user_id is None else change_role(conn, user_id, role)


def set_active(conn: sqlite3.Connection, username: str, active: bool) -> User | None:
    """CLI: kaip `change_active`, tik pagal naudotojo vardą."""
    user_id = _by_username(conn, username)
    return None if user_id is None else change_active(conn, user_id, active)


def set_password(conn: sqlite3.Connection, username: str, password: str) -> User | None:
    """Pakeitus slaptažodį, visos senos to naudotojo sesijos tampa negaliojančios."""
    if not MIN_PASSWORD_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ValueError("netinkamas slaptažodžio ilgis")
    with conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
            (hash_password(password), _utc_now(), username.strip()),
        )
    return get_user_by_username(conn, username)
