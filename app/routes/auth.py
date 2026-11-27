"""Prisijungimas, registracija ir atsijungimas (6A: naudotojų paskyros DB)."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    AuthSettings,
    LoginRateLimiter,
    Session,
    check_csrf,
    check_form_csrf,
    create_session_token,
    form_csrf_token,
    get_auth_settings,
    get_current_session,
    home_path,
    is_secure_request,
    next_path_for_role,
    safe_next_path,
    set_form_csrf_cookie,
)
from app.db import get_connection, get_database_path, init_db
from app.services.user_service import (
    EMAIL_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
    DuplicateUserError,
    LoginResult,
    RegistrationForm,
    authenticate,
    register_tester,
    validate_registration,
)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

_LOGIN_ERRORS = {
    LoginResult.INVALID: ("Neteisingas naudotojo vardas arba slaptažodis.", 401),
    LoginResult.INACTIVE: ("Paskyra išjungta. Kreipkitės į administratorių.", 403),
    LoginResult.ADMIN_CONFLICT: (
        "Administratoriaus paskyros perkelti nepavyko: šis vardas jau užimtas kitos paskyros. "
        "Administratorius turi paleisti `python -m tools.users bootstrap-admin` ir išspręsti konfliktą.",
        409,
    ),
}


def _limiter(request: Request) -> LoginRateLimiter:
    state = request.app.state
    if not hasattr(state, "login_limiter"):
        state.login_limiter = LoginRateLimiter()
    return state.login_limiter


def _set_session_cookie(response, request: Request, settings: AuthSettings, user) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(settings, user.id, user.password_hash),
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        httponly=True,  # JavaScript negali perskaityti slapuko
        samesite="lax",  # kitų svetainių POST užklausos slapuko negauna
        secure=is_secure_request(request, settings),
    )


def _render(
    request: Request,
    template: str,
    settings: AuthSettings | None,
    status_code: int = 200,
    **context: object,
) -> HTMLResponse:
    cookie_value = None
    if settings is not None:
        context["form_csrf"], cookie_value = form_csrf_token(request, settings.secret_key)
    context.setdefault("configured", settings is not None)
    response = templates.TemplateResponse(request, template, context, status_code=status_code)
    set_form_csrf_cookie(response, request, cookie_value)
    return response


# --- Prisijungimas -------------------------------------------------------------


def _render_login(request, settings, next_path="", username="", error=None, info=None, status_code=200):
    return _render(
        request, "login.html", settings, status_code,
        next_path=safe_next_path(next_path, ""), username=username, error=error, info=info,
    )


@router.get("/login", response_model=None)
def login_form(
    request: Request,
    next_path: str = Query("", alias="next"),
    logged_out: str = Query(""),
    registered: str = Query(""),
    settings: AuthSettings | None = Depends(get_auth_settings),
    session: Session | None = Depends(get_current_session),
) -> HTMLResponse | RedirectResponse:
    if session is not None:
        return RedirectResponse(next_path_for_role(next_path, session.role), status_code=303)
    if settings is None:
        return _render_login(request, None, next_path, status_code=503)
    info = "Atsijungėte." if logged_out else None
    if registered:
        info = "Paskyra sukurta. Prisijunkite."
    return _render_login(request, settings, next_path, info=info)


@router.post("/login", response_model=None)
def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next_path: str = Form("", alias="next"),
    form_csrf: str = Form(""),
    settings: AuthSettings | None = Depends(get_auth_settings),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    if settings is None:
        return _render_login(request, None, next_path, status_code=503)
    check_form_csrf(request, settings.secret_key, form_csrf)
    username = username.strip()[:USERNAME_MAX_LENGTH * 2]
    key = (request.client.host if request.client else "", username.casefold())
    limiter = _limiter(request)
    if limiter.is_blocked(key):
        error = "Per daug nesėkmingų bandymų. Pabandykite vėliau."
        return _render_login(request, settings, next_path, username, error=error, status_code=429)

    with get_connection(database_path) as conn:
        init_db(conn)
        result, user = authenticate(conn, settings, username, password)
    if result is not LoginResult.OK:
        if result is LoginResult.INVALID:
            limiter.record_failure(key)
        message, status_code = _LOGIN_ERRORS[result]
        return _render_login(request, settings, next_path, username, error=message, status_code=status_code)

    limiter.reset(key)
    response = RedirectResponse(next_path_for_role(next_path, user.role), status_code=303)
    _set_session_cookie(response, request, settings, user)
    return response


# --- Registracija (visada `tester`) ---------------------------------------------


def _render_register(request, settings, values=None, errors=None, status_code=200):
    return _render(
        request, "register.html", settings, status_code,
        values=values or {"username": "", "email": ""}, errors=errors or {},
        username_max_length=USERNAME_MAX_LENGTH, email_max_length=EMAIL_MAX_LENGTH,
    )


@router.get("/register", response_model=None)
def register_form(
    request: Request,
    settings: AuthSettings | None = Depends(get_auth_settings),
    session: Session | None = Depends(get_current_session),
) -> HTMLResponse | RedirectResponse:
    if session is not None:
        return RedirectResponse(home_path(session.role), status_code=303)
    return _render_register(request, settings, status_code=200 if settings else 503)


@router.post("/register", response_model=None)
def register(
    request: Request,
    username: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    form_csrf: str = Form(""),
    settings: AuthSettings | None = Depends(get_auth_settings),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    """Rolės laukas sąmoningai nepriimamas: bet koks `role` formos laukas ignoruojamas."""
    if settings is None:
        return _render_register(request, None, status_code=503)
    check_form_csrf(request, settings.secret_key, form_csrf)
    form = RegistrationForm(username, email, password, password_confirm)
    values = {"username": username.strip(), "email": email.strip()}
    errors = validate_registration(form, reserved_username=settings.username)
    if errors:
        return _render_register(request, settings, values, errors, status_code=400)
    with get_connection(database_path) as conn:
        init_db(conn)
        try:
            register_tester(conn, form)
        except DuplicateUserError as duplicate:
            message = (
                "Šis el. pašto adresas jau užregistruotas."
                if duplicate.field == "email" else "Šis naudotojo vardas jau užimtas."
            )
            return _render_register(request, settings, values, {duplicate.field: message}, status_code=400)
    return RedirectResponse("/login?registered=1", status_code=303)


# --- Atsijungimas -----------------------------------------------------------------


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(""),
    settings: AuthSettings | None = Depends(get_auth_settings),
    session: Session | None = Depends(get_current_session),
) -> RedirectResponse:
    if session is not None:
        check_csrf(session, csrf_token)
    response = RedirectResponse("/login?logged_out=1", status_code=303)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings is not None and is_secure_request(request, settings),
    )
    return response
