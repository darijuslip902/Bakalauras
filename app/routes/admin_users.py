"""6B: administratoriaus naudotojų valdymas – rolė, aktyvumas ir programuotojų specializacijos.

Visi veiksmai eina per `app.services.user_service` (tos pačios apsaugos kaip CLI): paskutinio
aktyvaus administratoriaus rolės pakeisti ar paskyros išjungti negalima, specializacijos tik
programuotojui ir tik iš `config.CATEGORY_LABELS`. Slaptažodžiai ir jų maišos nerodomi.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import config
from app.auth import Session, check_csrf, require_admin
from app.db import get_connection, get_database_path, init_db
from app.routes.dashboard import base_context, templates
from app.services.user_service import (
    ASSIGNABLE_CATEGORIES,
    ROLE_LABELS,
    ROLES,
    InvalidSpecialization,
    LastAdminError,
    all_developer_categories,
    change_active,
    change_role,
    get_user,
    list_users,
    set_developer_categories,
)

router = APIRouter()

_MESSAGES = {
    "role": "Rolė pakeista. Pakeitimas galioja iš karto.",
    "active": "Paskyros aktyvumas pakeistas. Pakeitimas galioja iš karto.",
    "categories": "Specializacijos išsaugotos. Klaidų matomumas atnaujintas iš karto.",
}
_LAST_ADMIN = "Negalima: tai paskutinis aktyvus administratorius. Pirmiausia suteikite administratoriaus rolę kitam naudotojui."
_SELF = "Savo paskyros rolės ar aktyvumo čia keisti negalima – tai turi atlikti kitas administratorius."


def _render(request: Request, session: Session, conn, message=None, error=None, status_code=200) -> HTMLResponse:
    users = list_users(conn)
    categories = all_developer_categories(conn)
    # Kategorijų eilės: kiek aktyvių programuotojų turi kiekvieną kategoriją.
    queues = {label: [] for label in ASSIGNABLE_CATEGORIES}
    for user in users:
        if user.role == "developer" and user.is_active:
            for label in categories.get(user.id, []):
                queues.setdefault(label, []).append(user.username)
    context = base_context(session, "users")
    context.update(
        # Šablonui perduodami tik rodomi laukai – ne slaptažodžio maiša.
        users=[{"id": u.id, "username": u.username, "email": u.email, "role": u.role,
                "is_active": u.is_active, "created_at": u.created_at,
                "categories": categories.get(u.id, [])} for u in users],
        roles=ROLES, role_labels=ROLE_LABELS, assignable=ASSIGNABLE_CATEGORIES, queues=queues,
        message=message, error=error,
    )
    return templates.TemplateResponse(request, "admin_users.html", context, status_code=status_code)


@router.get("/admin/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    message: str = Query(""),
    session: Session = Depends(require_admin),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    with get_connection(database_path) as conn:
        init_db(conn)
        return _render(request, session, conn, message=_MESSAGES.get(message))


def _done(kind: str) -> RedirectResponse:
    return RedirectResponse(f"/admin/users?message={kind}", status_code=303)


@router.post("/admin/users/{user_id}/role", response_model=None)
def update_role(
    request: Request,
    user_id: int,
    role: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(require_admin),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    check_csrf(session, csrf_token)
    with get_connection(database_path) as conn:
        init_db(conn)
        if get_user(conn, user_id) is None:
            return _render(request, session, conn, error="Naudotojas nerastas.", status_code=404)
        if role not in ROLES:
            return _render(request, session, conn, error="Neleistina rolė.", status_code=400)
        if user_id == session.user_id:
            return _render(request, session, conn, error=_SELF, status_code=400)
        try:
            change_role(conn, user_id, role)
        except LastAdminError:
            return _render(request, session, conn, error=_LAST_ADMIN, status_code=409)
    return _done("role")


@router.post("/admin/users/{user_id}/active", response_model=None)
def update_active(
    request: Request,
    user_id: int,
    active: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(require_admin),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    check_csrf(session, csrf_token)
    with get_connection(database_path) as conn:
        init_db(conn)
        if get_user(conn, user_id) is None:
            return _render(request, session, conn, error="Naudotojas nerastas.", status_code=404)
        if active not in ("0", "1"):
            return _render(request, session, conn, error="Neleistina aktyvumo reikšmė.", status_code=400)
        if user_id == session.user_id:
            return _render(request, session, conn, error=_SELF, status_code=400)
        try:
            change_active(conn, user_id, active == "1")
        except LastAdminError:
            return _render(request, session, conn, error=_LAST_ADMIN, status_code=409)
    return _done("active")


@router.post("/admin/users/{user_id}/categories", response_model=None)
def update_categories(
    request: Request,
    user_id: int,
    categories: list[str] = Form([]),
    csrf_token: str = Form(""),
    session: Session = Depends(require_admin),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    check_csrf(session, csrf_token)
    with get_connection(database_path) as conn:
        init_db(conn)
        user = get_user(conn, user_id)
        if user is None:
            return _render(request, session, conn, error="Naudotojas nerastas.", status_code=404)
        if any(label not in ASSIGNABLE_CATEGORIES for label in categories):
            return _render(request, session, conn, error="Neleistina kategorija.", status_code=400)
        try:
            set_developer_categories(conn, user_id, categories)
        except InvalidSpecialization:
            error = "Specializacijas galima priskirti tik naudotojui su programuotojo role."
            return _render(request, session, conn, error=error, status_code=400)
    return _done("categories")
