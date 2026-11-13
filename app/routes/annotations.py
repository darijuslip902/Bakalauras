"""Mokymo duomenų (GitHub issues) peržiūra ir rankinis žymėjimas – tik prisijungus."""

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import config
from app.auth import Session, check_csrf, require_login
from app.db import get_connection, init_db
from app.routes.dashboard import SEARCH_MAX_LENGTH, base_context, templates
from app.routes.issues import get_database_path
from app.services.annotation_service import (
    LABEL_FIELDS,
    TrainingDataFilters,
    annotation_stats,
    annotation_status,
    get_issue,
    github_labels,
    list_repositories,
    list_training_issues,
    next_unlabeled_id,
    save_annotation,
    validate_annotation,
)

router = APIRouter()

LIST_URL = "/dashboard/training-data"
_MESSAGES = {
    "saved": "Žymos išsaugotos.",
    "saved_next": "Ankstesnio įrašo žymos išsaugotos. Rodomas kitas nepažymėtas įrašas.",
    "unchanged": "Pakeitimų nebuvo – žymos jau buvo tokios.",
    "all_done": "Nepažymėtų įrašų nebeliko (neskaičiuojant pažymėtų „Netinka mokymui“).",
}
_SORT_LABELS = {"newest": "Naujausi viršuje", "oldest": "Seniausi viršuje"}
_TEST_SET_LABELS = {
    "": "Visi",
    "pilot": "Tik bandomasis rinkinys",
    "yes": "Tik testavimo rinkinys",
    "no": "Be bandomojo ir testavimo",
}


def _context(session: Session) -> dict[str, object]:
    context = base_context(session, "training")
    context.update(
        suitability_labels=config.TRAINING_SUITABILITY_LABELS,
        annotation_labels=config.ANNOTATION_STATUS_LABELS,
        label_fields=LABEL_FIELDS,
    )
    return context


@router.get(LIST_URL, response_class=HTMLResponse)
def training_data_list(
    request: Request,
    q: str = Query(""),
    annotation: str = Query(""),
    suitability: str = Query(""),
    repository: str = Query(""),
    test_set: str = Query(""),
    sort: str = Query("newest"),
    page: str = Query("1"),
    message: str = Query(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    with get_connection(database_path) as conn:
        init_db(conn)
        repositories = list_repositories(conn)
        # Neteisingos filtro reikšmės ignoruojamos (rodomas pranešimas).
        invalid = False
        if annotation not in ("", *config.ANNOTATION_STATUS_LABELS):
            annotation, invalid = "", True
        if suitability not in ("", *config.TRAINING_SUITABILITY_LABELS):
            suitability, invalid = "", True
        if test_set not in _TEST_SET_LABELS:
            test_set, invalid = "", True
        if repository not in ("", *repositories):
            repository, invalid = "", True
        if sort not in _SORT_LABELS:
            sort, invalid = "newest", True
        page_number = int(page) if page.isascii() and page.isdigit() else 1
        filters = TrainingDataFilters(
            search=q.strip()[:SEARCH_MAX_LENGTH],
            annotation=annotation,
            suitability=suitability,
            repository=repository,
            test_set=test_set,
            sort=sort,
        )
        result = list_training_issues(conn, filters, page_number)
        stats = annotation_stats(conn)

    # Filtrai, kurie išlaikomi pereinant tarp puslapių (tuščios reikšmės praleidžiamos).
    query = {
        "q": filters.search,
        "annotation": filters.annotation,
        "suitability": filters.suitability,
        "repository": filters.repository,
        "test_set": filters.test_set,
        "sort": "" if filters.sort == "newest" else filters.sort,
    }
    base_query = {key: value for key, value in query.items() if value}

    context = _context(session)
    context.update(
        page=result,
        issues=[(row, annotation_status(row)) for row in result.rows],
        stats=stats,
        filters=filters,
        repositories=repositories,
        sort_labels=_SORT_LABELS,
        test_set_labels=_TEST_SET_LABELS,
        filters_active=bool(base_query),
        invalid_filter=invalid,
        message=_MESSAGES.get(message),
        page_url=lambda number: f"{LIST_URL}?{urlencode({**base_query, 'page': number})}",
    )
    return templates.TemplateResponse(request, "training_list.html", context)


@router.get(f"{LIST_URL}/next")
def next_unlabeled(
    after: str = Query("0"),
    message: str = Query(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> RedirectResponse:
    after_id = int(after) if after.isascii() and after.isdigit() else 0
    with get_connection(database_path) as conn:
        init_db(conn)
        issue_id = next_unlabeled_id(conn, after_id)
    if issue_id is None:
        return RedirectResponse(f"{LIST_URL}?message=all_done", status_code=303)
    suffix = "?message=saved_next" if message == "saved" else ""
    return RedirectResponse(f"{LIST_URL}/{issue_id}{suffix}", status_code=303)


def _render_detail(
    request: Request,
    session: Session,
    issue: object,
    values: dict[str, object] | None = None,
    message: str | None = None,
    errors: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    context = _context(session)
    if issue is not None:
        context.update(
            status=annotation_status(issue),
            labels=github_labels(issue),
            # Formoje rodomos išsaugotos reikšmės arba ką tik pateiktos (klaidos atveju).
            values=values or {key: issue[key] for key in (*LABEL_FIELDS, "training_suitability")},
        )
    context.update(issue=issue, message=message, errors=errors or {})
    return templates.TemplateResponse(
        request, "training_detail.html", context, status_code=status_code
    )


@router.get(f"{LIST_URL}/{{issue_id}}", response_class=HTMLResponse)
def training_data_detail(
    request: Request,
    issue_id: int,
    message: str = Query(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse:
    with get_connection(database_path) as conn:
        init_db(conn)
        issue = get_issue(conn, issue_id)
    if issue is None:
        return _render_detail(request, session, None, status_code=404)
    return _render_detail(request, session, issue, message=_MESSAGES.get(message))


@router.post(f"{LIST_URL}/{{issue_id}}/annotation", response_model=None)
def save_training_annotation(
    request: Request,
    issue_id: int,
    category_label: str = Form(""),
    complexity_label: str = Form(""),
    priority_label: str = Form(""),
    training_suitability: str = Form(""),
    action: str = Form("save"),
    csrf_token: str = Form(""),
    session: Session = Depends(require_login),
    database_path: Path = Depends(get_database_path),
) -> HTMLResponse | RedirectResponse:
    check_csrf(session, csrf_token)
    submitted = {
        "category_label": category_label,
        "complexity_label": complexity_label,
        "priority_label": priority_label,
        "training_suitability": training_suitability,
    }
    values, errors = validate_annotation(submitted)
    with get_connection(database_path) as conn:
        init_db(conn)
        issue = get_issue(conn, issue_id)
        if issue is None:
            return _render_detail(request, session, None, status_code=404)
        if errors:
            # Neteisingi laukai išvalomi, teisingi paliekami kaip pateikti.
            shown = {key: (None if key in errors else value) for key, value in values.items()}
            return _render_detail(request, session, issue, shown, errors=errors, status_code=400)
        changed = save_annotation(conn, issue_id, values)

    # Post/Redirect/Get: atnaujinus puslapį forma nepateikiama dar kartą.
    if action == "next":
        return RedirectResponse(
            f"{LIST_URL}/next?after={issue_id}&message=saved", status_code=303
        )
    message = "saved" if changed else "unchanged"
    return RedirectResponse(f"{LIST_URL}/{issue_id}?message={message}", status_code=303)
