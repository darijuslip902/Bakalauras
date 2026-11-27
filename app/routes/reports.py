"""Vieša klaidos pateikimo forma. Prisijungimo nereikia, kiti pranešimai nerodomi.

6A: jei naudotojas prisijungęs, pranešimas susiejamas su jo paskyra (`reporter_user_id`) ir
matomas jo „Mano pranešimuose“. Svečio pranešimas lieka anoniminis.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    AuthSettings,
    Session,
    check_form_csrf,
    form_csrf_secret,
    form_csrf_token,
    get_auth_settings,
    get_current_session,
    set_form_csrf_cookie,
)
from app.db import get_connection, get_database_path, init_db
from app.routes.issues import get_predictor
from app.services.bug_report_service import (
    DESCRIPTION_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    clean_text,
    create_bug_report,
    validate_report,
)
from app.services.prediction_service import Predictor, classify_report

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _render_form(
    request: Request,
    session: Session | None = None,
    title: str = "",
    description: str = "",
    errors: dict[str, str] | None = None,
    status_code: int = 200,
    settings: AuthSettings | None = None,
) -> HTMLResponse:
    # Formų CSRF (dvigubo pateikimo slapukas) – tiek svečiui, tiek prisijungusiam naudotojui.
    csrf, cookie_value = form_csrf_token(request, form_csrf_secret(request, settings))
    context = {
        "form_csrf": csrf,
        "session": session,
        "title": title,
        "description": description,
        "errors": errors or {},
        "title_max_length": TITLE_MAX_LENGTH,
        "description_max_length": DESCRIPTION_MAX_LENGTH,
    }
    response = templates.TemplateResponse(
        request, "report_form.html", context, status_code=status_code
    )
    set_form_csrf_cookie(response, request, cookie_value)
    return response


@router.get("/report", response_class=HTMLResponse)
def report_form(
    request: Request,
    session: Session | None = Depends(get_current_session),
    settings: AuthSettings | None = Depends(get_auth_settings),
) -> HTMLResponse:
    return _render_form(request, session, settings=settings)


@router.post("/report", response_model=None)
def submit_report(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    form_csrf: str = Form(""),
    database_path: Path = Depends(get_database_path),
    predictor: Predictor = Depends(get_predictor),
    session: Session | None = Depends(get_current_session),
    settings: AuthSettings | None = Depends(get_auth_settings),
) -> HTMLResponse | RedirectResponse:
    # Tikrinama prieš bet kokį įrašymą: be galiojančio žetono pranešimas neišsaugomas (403).
    check_form_csrf(request, form_csrf_secret(request, settings), form_csrf)
    title = clean_text(title)
    description = clean_text(description)
    errors = validate_report(title, description)
    if errors:
        return _render_form(request, session, title, description, errors, status_code=400, settings=settings)

    # Savininkas imamas tik iš patikrintos sesijos, niekada iš formos laukų.
    reporter_user_id = session.user_id if session is not None else None
    with get_connection(database_path) as conn:
        init_db(conn)
        report_id = create_bug_report(conn, title, description, reporter_user_id)
        # Automatinė klasifikacija vietiniais modeliais. Pranešimas jau išsaugotas, todėl bet kokia
        # klasifikavimo klaida klientui nerodoma ir pranešimo nepraranda.
        try:
            classify_report(conn, predictor, report_id)
        except Exception:
            logger.exception("Pranešimo #%s automatinė klasifikacija nepavyko", report_id)

    # Post/Redirect/Get: atnaujinus patvirtinimo puslapį forma nepateikiama dar kartą.
    return RedirectResponse("/report/submitted", status_code=303)


@router.get("/report/submitted", response_class=HTMLResponse)
def report_submitted(
    request: Request, session: Session | None = Depends(get_current_session)
) -> HTMLResponse:
    return templates.TemplateResponse(request, "report_submitted.html", {"session": session})
