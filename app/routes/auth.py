"""Prisijungimas ir atsijungimas vienai vidinei paskyrai."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    AuthSettings,
    Session,
    check_credentials,
    check_csrf,
    create_session_token,
    get_auth_settings,
    get_current_session,
    is_secure_request,
    safe_next_path,
)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _render_login(
    request: Request,
    next_path: str,
    username: str = "",
    error: str | None = None,
    info: str | None = None,
    configured: bool = True,
    status_code: int = 200,
) -> HTMLResponse:
    context = {
        "next_path": safe_next_path(next_path),
        "username": username,
        "error": error,
        "info": info,
        "configured": configured,
    }
    return templates.TemplateResponse(request, "login.html", context, status_code=status_code)


@router.get("/login", response_model=None)
def login_form(
    request: Request,
    next_path: str = Query("", alias="next"),
    logged_out: str = Query(""),
    settings: AuthSettings | None = Depends(get_auth_settings),
    session: Session | None = Depends(get_current_session),
) -> HTMLResponse | RedirectResponse:
    if session is not None:
        return RedirectResponse(safe_next_path(next_path), status_code=303)
    if settings is None:
        return _render_login(request, next_path, configured=False, status_code=503)
    info = "Atsijungėte." if logged_out else None
    return _render_login(request, next_path, info=info)


@router.post("/login", response_model=None)
def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next_path: str = Form("", alias="next"),
    settings: AuthSettings | None = Depends(get_auth_settings),
) -> HTMLResponse | RedirectResponse:
    if settings is None:
        return _render_login(request, next_path, configured=False, status_code=503)
    username = username.strip()
    if not check_credentials(settings, username, password):
        error = "Neteisingas naudotojo vardas arba slaptažodis."
        return _render_login(request, next_path, username, error=error, status_code=401)

    response = RedirectResponse(safe_next_path(next_path), status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(settings),
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        httponly=True,  # JavaScript negali perskaityti slapuko
        samesite="lax",  # kitų svetainių POST užklausos slapuko negauna
        secure=is_secure_request(request, settings),
    )
    return response


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
