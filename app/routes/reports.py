"""Vieša klaidos pateikimo forma. Prisijungimo nereikia, kiti pranešimai nerodomi."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import get_connection, init_db
from app.routes.issues import get_database_path, get_predictor
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
    title: str = "",
    description: str = "",
    errors: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    context = {
        "title": title,
        "description": description,
        "errors": errors or {},
        "title_max_length": TITLE_MAX_LENGTH,
        "description_max_length": DESCRIPTION_MAX_LENGTH,
    }
    return templates.TemplateResponse(
        request, "report_form.html", context, status_code=status_code
    )


@router.get("/report", response_class=HTMLResponse)
def report_form(request: Request) -> HTMLResponse:
    return _render_form(request)


@router.post("/report", response_model=None)
def submit_report(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    database_path: Path = Depends(get_database_path),
    predictor: Predictor = Depends(get_predictor),
) -> HTMLResponse | RedirectResponse:
    title = clean_text(title)
    description = clean_text(description)
    errors = validate_report(title, description)
    if errors:
        return _render_form(request, title, description, errors, status_code=400)

    with get_connection(database_path) as conn:
        init_db(conn)
        report_id = create_bug_report(conn, title, description)
        # Automatinė klasifikacija vietiniais modeliais. Pranešimas jau išsaugotas, todėl bet kokia
        # klasifikavimo klaida klientui nerodoma ir pranešimo nepraranda.
        try:
            classify_report(conn, predictor, report_id)
        except Exception:
            logger.exception("Pranešimo #%s automatinė klasifikacija nepavyko", report_id)

    # Post/Redirect/Get: atnaujinus patvirtinimo puslapį forma nepateikiama dar kartą.
    return RedirectResponse("/report/submitted", status_code=303)


@router.get("/report/submitted", response_class=HTMLResponse)
def report_submitted(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "report_submitted.html")
