"""6B: programuotojo darbo aplinka – tik jo specializacijų (kategorijų eilių) klaidos.

Prieiga tikrinama serveryje kiekvienoje užklausoje: rolė `developer` ir aktyvumas skaitomi iš DB
(`require_role`), o kategorijų priklausomybė – SQL užklausoje (`developer_id`). Svetimos
kategorijos ar neegzistuojanti klaida grąžina tą patį 404 (apsauga nuo IDOR). Klasifikacijos
patvirtinimas ir taisymas lieka administratoriui; programuotojas keičia tik būseną.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import config
from app.auth import Session, check_csrf, require_role
from app.db import get_connection, get_database_path, init_db
from app.routes.dashboard import SEARCH_MAX_LENGTH, _allowed, base_context, templates
from app.services.bug_report_service import (
    STATUSES,
    UNSET,
    ReportFilters,
    get_routed_report,
    list_bug_reports,
    update_status,
)
from app.services.user_service import developer_categories

router = APIRouter()
require_developer = require_role("developer")

_MESSAGES = {
    "status_updated": "Būsena sėkmingai pakeista.",
    "status_unchanged": "Būsena nepakeista: pasirinkta ta pati būsena.",
}


def _context(session: Session, categories: list[str], **extra: object) -> dict[str, object]:
    context = base_context(session, "developer")
    context.update(
        my_categories=categories,
        my_category_labels={label: config.CATEGORY_LABELS[label] for label in categories},
        **extra,
    )
    return context


@router.get("/developer/dashboard", response_class=HTMLResponse)
def developer_dashboard(
    request: Request,
    q: str = Query(""),
    status: str = Query(""),
    category: str = Query(""),
    priority: str = Query(""),
    complexity: str = Query(""),
    session: Session = Depends(require_developer),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    with get_connection(database_path) as conn:
        init_db(conn)
        categories = developer_categories(conn, session.user_id)
        own = {label: config.CATEGORY_LABELS[label] for label in categories}
        status, status_ok = _allowed(status, config.STATUS_LABELS, allow_unset=False)
        # Kategorijos filtras – tik savo kategorijos (eilėje esanti klaida visada turi kategoriją).
        category, category_ok = _allowed(category, own, allow_unset=False)
        priority, priority_ok = _allowed(priority, config.PRIORITY_LABELS)
        complexity, complexity_ok = _allowed(complexity, config.COMPLEXITY_LABELS)
        filters = ReportFilters(
            search=q.strip()[:SEARCH_MAX_LENGTH], status=status, category_label=category,
            priority_label=priority, complexity_label=complexity,
        )
        reports = list_bug_reports(conn, filters, developer_id=session.user_id) if categories else []

    context = _context(
        session, categories, reports=reports, filters=filters, unset=UNSET,
        filters_active=any(vars(filters).values()),
        invalid_filter=not (status_ok and category_ok and priority_ok and complexity_ok),
    )
    return templates.TemplateResponse(request, "developer_dashboard.html", context)


def _render_detail(request, session, categories, report, message=None, error=None, status_code=200):
    context = _context(session, categories, report=report, statuses=STATUSES, message=message, error=error)
    return templates.TemplateResponse(request, "developer_report_detail.html", context, status_code=status_code)


@router.get("/developer/reports/{report_id}", response_class=HTMLResponse)
def developer_report_detail(
    request: Request,
    report_id: int,
    message: str = Query(""),
    session: Session = Depends(require_developer),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    with get_connection(database_path) as conn:
        init_db(conn)
        categories = developer_categories(conn, session.user_id)
        report = get_routed_report(conn, report_id, developer_id=session.user_id)
    if report is None:
        return _render_detail(request, session, categories, None, status_code=404)
    return _render_detail(request, session, categories, report, message=_MESSAGES.get(message))


@router.post("/developer/reports/{report_id}/status", response_model=None)
def developer_change_status(
    request: Request,
    report_id: int,
    status: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(require_developer),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    check_csrf(session, csrf_token)
    with get_connection(database_path) as conn:
        init_db(conn)
        categories = developer_categories(conn, session.user_id)
        report = get_routed_report(conn, report_id, developer_id=session.user_id)
        if report is None:
            return _render_detail(request, session, categories, None, status_code=404)
        if status not in STATUSES:
            error = "Neleistina būsena. Pasirinkite: Nauja, Taisoma arba Išspręsta."
            return _render_detail(request, session, categories, report, error=error, status_code=400)
        changed = update_status(conn, report_id, status)
    message = "status_updated" if changed else "status_unchanged"
    return RedirectResponse(f"/developer/reports/{report_id}?message={message}", status_code=303)
