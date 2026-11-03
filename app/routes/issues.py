from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.auth import Session, check_csrf, require_login
from app.db import get_connection, init_db
from app.services.github_client import GitHubError, InvalidRepositoryError, parse_repository
from app.services.import_service import run_import

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def get_database_path() -> Path:
    return config.database_path()


def get_github_transport() -> httpx.BaseTransport | None:
    """Gamyboje None (tikras tinklas); testuose pakeičiamas imituotu transportu."""
    return None


def _render(
    request: Request,
    session: Session,
    repository: str,
    limit: str,
    status_code: int = 200,
    **extra: object,
) -> HTMLResponse:
    context = {
        "session": session,
        "active": "import",
        "repository": repository,
        "limit": limit,
        "max_limit": config.max_import_limit(),
        **extra,
    }
    return templates.TemplateResponse(
        request, "import.html", context, status_code=status_code
    )


@router.get("/import", response_class=HTMLResponse)
def import_form(request: Request, session: Session = Depends(require_login)) -> HTMLResponse:
    return _render(request, session, "", str(config.max_import_limit()))


@router.post("/import", response_class=HTMLResponse)
def import_issues(
    request: Request,
    repository: str = Form(""),
    limit: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
    transport: httpx.BaseTransport | None = Depends(get_github_transport),
) -> HTMLResponse:
    check_csrf(session, csrf_token)
    max_limit = config.max_import_limit()
    limit_text = limit.strip()
    if not (limit_text.isascii() and limit_text.isdigit() and 1 <= int(limit_text) <= max_limit):
        error = f"Importo kiekis turi būti sveikasis skaičius nuo 1 iki {max_limit}."
        return _render(request, session, repository, limit, 400, error=error)

    try:
        full_name = parse_repository(repository)
        with get_connection(database_path) as conn:
            init_db(conn)
            result = run_import(
                conn, full_name, int(limit_text), config.github_token(), transport
            )
    except InvalidRepositoryError as exc:
        return _render(request, session, repository, limit, 400, error=str(exc))
    except GitHubError as exc:
        return _render(request, session, repository, limit, exc.status_code, error=exc.message)

    return _render(request, session, full_name, limit, result=result, imported_repository=full_name)
