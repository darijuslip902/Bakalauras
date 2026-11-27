"""6A: prisijungusio naudotojo „Mano pranešimai“. Rodomi tik jo paties pateikti pranešimai.

Nuosavybė tikrinama SQL užklausoje (`reporter_user_id = sesijos naudotojas`), todėl tiesioginis
svetimo pranešimo URL grąžina 404 – neatskleidžiama net tai, ar toks pranešimas egzistuoja.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.auth import Session, require_login
from app.db import get_connection, get_database_path, init_db
from app.services.bug_report_service import get_report_of_reporter, list_reports_by_reporter
from app.services.user_service import ROLE_LABELS

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _context(session: Session, **extra: object) -> dict[str, object]:
    return {
        "session": session,
        "active": "my_reports",
        "role_labels": ROLE_LABELS,
        "status_labels": config.STATUS_LABELS,
        **extra,
    }


@router.get("/my/reports", response_class=HTMLResponse)
def my_reports(
    request: Request,
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    with get_connection(database_path) as conn:
        init_db(conn)
        reports = list_reports_by_reporter(conn, session.user_id)
    return templates.TemplateResponse(request, "my_reports.html", _context(session, reports=reports))


@router.get("/my/reports/{report_id}", response_class=HTMLResponse)
def my_report_detail(
    request: Request,
    report_id: int,
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    with get_connection(database_path) as conn:
        init_db(conn)
        report = get_report_of_reporter(conn, report_id, session.user_id)
    status_code = 200 if report is not None else 404
    return templates.TemplateResponse(
        request, "my_report_detail.html", _context(session, report=report), status_code=status_code
    )
