"""Vidinė programuotojo / koordinatoriaus klaidų valdymo aplinka (reikia prisijungti)."""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.auth import Session, check_csrf, require_login
from app.db import get_connection, init_db
from app.routes.issues import get_database_path, get_predictor
from app.services.bug_report_service import (
    STATUSES,
    UNSET,
    ReportFilters,
    get_bug_report,
    list_bug_reports,
    update_status,
)
from app.services.classification_service import (
    confirm_classification,
    confirmation_history,
    form_values,
    is_confirmed,
    validate_classification,
)
from app.services.prediction_service import (
    METHOD,
    REVIEW_THRESHOLDS,
    FIELDS,
    Predictor,
    classify_report,
    latest_predictions,
)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

SEARCH_MAX_LENGTH = 200
_MESSAGES = {
    "status_updated": "Būsena sėkmingai pakeista.",
    "status_unchanged": "Būsena nepakeista: pasirinkta ta pati būsena.",
    "classified": "Automatinė klasifikacija atnaujinta. Patvirtintos žymos nepakeistos.",
    "confirmed": "Klasifikacija patvirtinta.",
    "confirm_unchanged": "Klasifikacija nepakeista: pasirinktos tos pačios reikšmės.",
}


def format_datetime(value: str | None) -> str:
    """`2026-11-02T10:38:45+00:00` -> `2026-11-02 10:38 UTC`."""
    if not value:
        return "—"
    return value[:16].replace("T", " ") + " UTC"


templates.env.filters["datetime"] = format_datetime


def base_context(session: Session, active: str) -> dict[str, object]:
    return {
        "session": session,
        "active": active,
        "status_labels": config.STATUS_LABELS,
        "category_labels": config.CATEGORY_LABELS,
        "priority_labels": config.PRIORITY_LABELS,
        "complexity_labels": config.COMPLEXITY_LABELS,
    }


def _allowed(value: str, allowed: dict[str, str], allow_unset: bool = True) -> tuple[str, bool]:
    """Grąžina (reikšmė, ar teisinga). Neteisinga reikšmė pakeičiama į „visi“."""
    value = value.strip()
    if not value or value in allowed or (allow_unset and value == UNSET):
        return value, True
    return "", False


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    q: str = Query(""),
    status: str = Query(""),
    category: str = Query(""),
    priority: str = Query(""),
    complexity: str = Query(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    status, status_ok = _allowed(status, config.STATUS_LABELS, allow_unset=False)
    category, category_ok = _allowed(category, config.CATEGORY_LABELS)
    priority, priority_ok = _allowed(priority, config.PRIORITY_LABELS)
    complexity, complexity_ok = _allowed(complexity, config.COMPLEXITY_LABELS)
    filters = ReportFilters(
        search=q.strip()[:SEARCH_MAX_LENGTH],
        status=status,
        category_label=category,
        priority_label=priority,
        complexity_label=complexity,
    )
    with get_connection(database_path) as conn:
        init_db(conn)
        reports = list_bug_reports(conn, filters)

    context = base_context(session, "dashboard")
    context.update(
        reports=reports,
        filters=filters,
        unset=UNSET,
        filters_active=any(vars(filters).values()),
        invalid_filter=not (status_ok and category_ok and priority_ok and complexity_ok),
    )
    return templates.TemplateResponse(request, "dashboard.html", context)


def _render_detail(
    request: Request,
    session: Session,
    report: object,
    message: str | None = None,
    error: str | None = None,
    status_code: int = 200,
    conn: sqlite3.Connection | None = None,
    form: dict[str, str] | None = None,
    field_errors: dict[str, str] | None = None,
) -> HTMLResponse:
    """Detalių puslapis. Su `conn` papildomai įkeliamos prognozės ir patvirtinimų istorija."""
    predictions: dict = {}
    history: list = []
    confirmed = False
    if report is not None and conn is not None:
        predictions = latest_predictions(conn, report["id"])
        history = confirmation_history(conn, report["id"])
        confirmed = is_confirmed(report)
        if form is None:
            form = form_values(report, predictions)
    context = base_context(session, "dashboard")
    context.update(
        report=report, statuses=STATUSES, message=message, error=error,
        predictions=predictions, prediction_fields=FIELDS, prediction_method=METHOD,
        review_thresholds=REVIEW_THRESHOLDS, history=history, confirmed=confirmed,
        last_confirmation=history[0] if history else None,
        form=form or {}, field_errors=field_errors or {},
    )
    return templates.TemplateResponse(
        request, "report_detail.html", context, status_code=status_code
    )


@router.get("/dashboard/reports/{report_id}", response_class=HTMLResponse)
def report_detail(
    request: Request,
    report_id: int,
    message: str = Query(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    with get_connection(database_path) as conn:
        init_db(conn)
        report = get_bug_report(conn, report_id)
        if report is None:
            return _render_detail(request, session, None, status_code=404)
        return _render_detail(request, session, report, message=_MESSAGES.get(message), conn=conn)


@router.post("/dashboard/reports/{report_id}/status", response_model=None)
def change_status(
    request: Request,
    report_id: int,
    status: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    check_csrf(session, csrf_token)
    with get_connection(database_path) as conn:
        init_db(conn)
        report = get_bug_report(conn, report_id)
        if report is None:
            return _render_detail(request, session, None, status_code=404)
        if status not in STATUSES:
            error = "Neleistina būsena. Pasirinkite: Nauja, Taisoma arba Išspręsta."
            return _render_detail(request, session, report, error=error, status_code=400, conn=conn)
        changed = update_status(conn, report_id, status)

    message = "status_updated" if changed else "status_unchanged"
    # Post/Redirect/Get: atnaujinus puslapį būsena nekeičiama dar kartą.
    return RedirectResponse(
        f"/dashboard/reports/{report_id}?message={message}", status_code=303
    )


@router.post("/dashboard/reports/{report_id}/classify", response_model=None)
def reclassify(
    request: Request,
    report_id: int,
    csrf_token: str = Form(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
    predictor: Predictor = Depends(get_predictor),
) -> HTMLResponse | RedirectResponse:
    """Paleidžia vietinius modelius iš naujo (pvz. kai pranešimas gautas, kol modelių dar nebuvo)."""
    check_csrf(session, csrf_token)
    with get_connection(database_path) as conn:
        init_db(conn)
        if get_bug_report(conn, report_id) is None:
            return _render_detail(request, session, None, status_code=404)
        classify_report(conn, predictor, report_id)
    return RedirectResponse(f"/dashboard/reports/{report_id}?message=classified", status_code=303)


@router.post("/dashboard/reports/{report_id}/classification", response_model=None)
def confirm_report_classification(
    request: Request,
    report_id: int,
    category_label: str = Form(""),
    complexity_label: str = Form(""),
    priority_label: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    """Programuotojas patvirtina arba pataiso klasifikaciją (serverio pusės validacija)."""
    check_csrf(session, csrf_token)
    values = {"category_label": category_label.strip(), "complexity_label": complexity_label.strip(),
              "priority_label": priority_label.strip()}
    with get_connection(database_path) as conn:
        init_db(conn)
        report = get_bug_report(conn, report_id)
        if report is None:
            return _render_detail(request, session, None, status_code=404)
        errors = validate_classification(values)
        if errors:
            return _render_detail(
                request, session, report, status_code=400, conn=conn, form=values,
                field_errors=errors, error="Klasifikacija neišsaugota: pataisykite pažymėtus laukus.",
            )
        changed = confirm_classification(conn, report_id, values, session.username)
    message = "confirmed" if changed else "confirm_unchanged"
    return RedirectResponse(f"/dashboard/reports/{report_id}?message={message}", status_code=303)
